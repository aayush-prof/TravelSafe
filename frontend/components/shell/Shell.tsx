"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, useTransition } from "react";
import {
  BookOpen,
  Check,
  ChevronDown,
  CloudSun,
  FileText,
  Landmark,
  LayoutDashboard,
  MapPin,
  Menu,
  Newspaper,
  PanelLeftClose,
  PanelLeftOpen,
  RotateCw,
  Search,
  ShieldAlert,
  UserRound,
  Wind,
  type LucideIcon,
} from "lucide-react";

import { refreshCity } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { since } from "@/lib/format";
import type { CitiesResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

type NavItem = { href: string; label: string; icon: LucideIcon };
const NAV: { label: string; items: NavItem[] }[] = [
  {
    label: "Assessment",
    items: [
      { href: "/", label: "Overview", icon: LayoutDashboard },
      { href: "/events", label: "Events", icon: Newspaper },
      { href: "/crime", label: "Crime watch", icon: ShieldAlert },
    ],
  },
  {
    label: "Conditions",
    items: [
      { href: "/weather", label: "Weather", icon: CloudSun },
      { href: "/environment", label: "Air & hazards", icon: Wind },
    ],
  },
  { label: "City", items: [{ href: "/insights", label: "City insights", icon: Landmark }] },
  {
    label: "Resources",
    items: [
      { href: "/reports", label: "Reports", icon: FileText },
      { href: "/how-it-works", label: "How it works", icon: BookOpen },
    ],
  },
];

// ---------------------------------------------------------------------------
// "Last updated" – pages report the freshness of the data they show.
// ---------------------------------------------------------------------------
const UpdatedCtx = createContext<(iso: string | null) => void>(() => {});

export function ReportUpdated({ at }: { at: string | null }) {
  const set = useContext(UpdatedCtx);
  useEffect(() => {
    set(at);
    return () => set(null);
  }, [at, set]);
  return null;
}

function useSelection(meta: CitiesResponse | null) {
  const sp = useSearchParams();
  const cityParam = (sp.get("city") ?? "").toLowerCase();
  const city =
    meta?.cities.find((c) => c.name.toLowerCase() === cityParam || c.slug === cityParam)?.name ??
    meta?.default_city ??
    "Delhi";
  const p = sp.get("persona");
  const persona = meta?.personas.some((x) => x.id === p) ? (p as string) : (meta?.default_persona ?? "student");
  return { city, persona, sp };
}

function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <span className="flex items-center gap-2.5">
      <span aria-hidden className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary text-white">
        <MapPin className="size-4" strokeWidth={2.3} />
      </span>
      {compact ? <span className="sr-only">TravelSafe</span> : <span className="text-[17px] font-semibold tracking-tight">TravelSafe</span>}
    </span>
  );
}

function NavLinks({ query, collapsed, onNavigate }: { query: string; collapsed: boolean; onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <nav aria-label="Main" className="space-y-5">
      {NAV.map((g) => (
        <div key={g.label}>
          {collapsed ? (
            <div aria-hidden className="mx-3 mb-2 h-px bg-sidebar-border" />
          ) : (
            <p className="px-3 pb-1.5 text-xs font-medium text-muted-foreground">{g.label}</p>
          )}
          <ul className="space-y-0.5">
            {g.items.map(({ href, label, icon: Icon }) => {
              const active = pathname === href;
              const link = (
                <Link
                  href={`${href}?${query}`}
                  onClick={onNavigate}
                  aria-current={active ? "page" : undefined}
                  aria-label={collapsed ? label : undefined}
                  className={cn(
                    "flex h-9 items-center gap-3 rounded-md px-3 text-[14px] transition-colors",
                    collapsed && "justify-center px-0",
                    active
                      ? "bg-sidebar-accent font-semibold text-sidebar-accent-foreground"
                      : "text-sidebar-foreground hover:bg-secondary",
                  )}
                >
                  <Icon aria-hidden className="size-4.5 shrink-0" strokeWidth={active ? 2.2 : 1.8} />
                  {collapsed ? null : label}
                </Link>
              );
              return (
                <li key={href}>
                  {collapsed ? (
                    <Tooltip>
                      <TooltipTrigger asChild>{link}</TooltipTrigger>
                      <TooltipContent side="right">{label}</TooltipContent>
                    </Tooltip>
                  ) : (
                    link
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function CitySearch({ meta, value, onSelect }: { meta: CitiesResponse; value: string; onSelect: (c: string) => void }) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.key === "k" && (e.metaKey || e.ctrlKey)) || (e.key === "/" && !(e.target instanceof HTMLInputElement))) {
        e.preventDefault();
        setOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const india = meta.cities.filter((c) => c.region === "India");
  const world = meta.cities.filter((c) => c.region !== "India");
  const item = (c: CitiesResponse["cities"][number]) => (
    <CommandItem
      key={c.slug}
      value={`${c.name} ${c.country} ${c.area} ${c.aliases.join(" ")}`}
      onSelect={() => {
        onSelect(c.name);
        setOpen(false);
      }}
    >
      <Check aria-hidden className={cn("size-4", c.name === value ? "opacity-100" : "opacity-0")} />
      <span className="flex-1">{c.name}</span>
      <span className="text-xs text-muted-foreground">{c.region === "India" ? c.area : c.country}</span>
    </CommandItem>
  );
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`City: ${value}. Change city`}
          className="flex h-9 w-full min-w-0 items-center gap-2 rounded-md border border-input bg-card px-3 text-left text-sm shadow-xs hover:bg-secondary/60 focus-visible:ring-[3px] focus-visible:ring-ring/40 focus-visible:outline-none sm:w-72"
        >
          <Search aria-hidden className="size-4 shrink-0 text-muted-foreground" />
          <span className="min-w-0 flex-1 truncate">
            <span className="font-medium">{value}</span>
            <span className="ml-2 text-muted-foreground">Change city</span>
          </span>
          <ChevronDown
            aria-hidden
            className={cn("size-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")}
          />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-[min(92vw,22rem)] p-0">
        <Command>
          <CommandInput placeholder="Search by city, state or country" />
          <CommandList>
            <CommandEmpty>No supported city matches that search.</CommandEmpty>
            <CommandGroup heading="India">{india.map(item)}</CommandGroup>
            <CommandGroup heading="International">{world.map(item)}</CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

function RefreshControl({ city, updated }: { city: string; updated: string | null }) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [result, setResult] = useState<"ok" | "failed" | null>(null);
  const [, tick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => tick((n) => n + 1), 30_000);
    return () => clearInterval(t);
  }, []);
  useEffect(() => {
    if (!result) return;
    const t = setTimeout(() => setResult(null), 6000);
    return () => clearTimeout(t);
  }, [result]);
  const run = () =>
    start(async () => {
      const res = await refreshCity(city);
      setResult(res.ok ? "ok" : "failed");
      router.refresh();
    });
  const status = pending
    ? "Fetching fresh data…"
    : result === "failed"
      ? "Couldn't refresh. Try again shortly."
      : result === "ok"
        ? "Updated with the latest data"
        : updated
          ? `Updated ${since(updated)}`
          : "";
  return (
    <div className="flex items-center gap-2">
      <span
        role="status"
        aria-live="polite"
        className={cn("hidden text-[13px] md:inline", result === "failed" ? "text-elevated" : "text-muted-foreground")}
      >
        {status}
      </span>
      <Button variant="outline" size="sm" onClick={run} disabled={pending} aria-busy={pending}>
        <RotateCw aria-hidden className={cn(pending && "animate-spin")} />
        <span className="hidden sm:inline">{pending ? "Refreshing" : "Refresh"}</span>
        <span className="sr-only sm:hidden">Refresh data</span>
      </Button>
    </div>
  );
}

export function Shell({ meta, children }: { meta: CitiesResponse | null; children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { city, persona, sp } = useSelection(meta);
  const [mobile, setMobile] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [updated, setUpdatedState] = useState<string | null>(null);
  const setUpdated = useCallback((iso: string | null) => setUpdatedState(iso), []);

  useEffect(() => {
    try {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- read a stored UI preference once on mount
      setCollapsed(window.localStorage.getItem("ts-sidebar") === "collapsed");
    } catch {
      /* storage unavailable: keep default */
    }
  }, []);
  const toggle = () => {
    setCollapsed((c) => {
      try {
        window.localStorage.setItem("ts-sidebar", c ? "open" : "collapsed");
      } catch {
        /* ignore */
      }
      return !c;
    });
  };

  const query = useMemo(() => new URLSearchParams({ city, persona }).toString(), [city, persona]);
  const go = (next: { city?: string; persona?: string }) => {
    const p = new URLSearchParams(sp.toString());
    p.set("city", next.city ?? city);
    p.set("persona", next.persona ?? persona);
    p.delete("page");
    router.push(`${pathname}?${p.toString()}`);
  };

  return (
    <TooltipProvider>
      <UpdatedCtx.Provider value={setUpdated}>
        <div className={cn("min-h-screen lg:grid", collapsed ? "lg:grid-cols-[72px_minmax(0,1fr)]" : "lg:grid-cols-[236px_minmax(0,1fr)]")}>
          <aside
            aria-label="Sidebar"
            className="hidden border-r border-sidebar-border bg-sidebar lg:sticky lg:top-0 lg:flex lg:h-screen lg:flex-col lg:py-4"
          >
            <div className={cn("flex h-10 items-center", collapsed ? "justify-center px-2" : "justify-between pr-2 pl-5")}>
              <Link href={`/?${query}`} aria-label="TravelSafe overview">
                <Brand compact={collapsed} />
              </Link>
              {collapsed ? null : (
                <Button variant="ghost" size="icon-sm" onClick={toggle} aria-label="Collapse sidebar">
                  <PanelLeftClose aria-hidden />
                </Button>
              )}
            </div>
            <div className={cn("mt-6 flex-1 overflow-y-auto", collapsed ? "px-3" : "px-3")}>
              <NavLinks query={query} collapsed={collapsed} />
            </div>
            <div className={cn("border-t border-sidebar-border pt-3", collapsed ? "px-3" : "px-5")}>
              {collapsed ? (
                <Button variant="ghost" size="icon" onClick={toggle} aria-label="Expand sidebar" className="mx-auto flex">
                  <PanelLeftOpen aria-hidden />
                </Button>
              ) : (
                <p className="text-xs leading-relaxed text-muted-foreground">
                  An evidence summary for trip research. Not a safety guarantee or an official advisory.
                </p>
              )}
            </div>
          </aside>

          <Sheet open={mobile} onOpenChange={setMobile}>
            <SheetContent side="left" className="px-3 py-4">
              <SheetTitle className="px-2">
                <Brand />
              </SheetTitle>
              <SheetDescription className="sr-only">Main navigation</SheetDescription>
              <div className="flex-1 overflow-y-auto pt-2">
                <NavLinks query={query} collapsed={false} onNavigate={() => setMobile(false)} />
              </div>
              <p className="px-3 text-xs leading-relaxed text-muted-foreground">
                An evidence summary for trip research. Not a safety guarantee or an official advisory.
              </p>
            </SheetContent>
          </Sheet>

          <div className="min-w-0">
            <header className="sticky top-0 z-30 border-b bg-background/90 backdrop-blur-md">
              <div className="mx-auto flex max-w-360 flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3 sm:px-6 lg:px-8">
                <Button
                  variant="ghost"
                  size="icon"
                  className="lg:hidden"
                  onClick={() => setMobile(true)}
                  aria-label="Open menu"
                  aria-expanded={mobile}
                >
                  <Menu aria-hidden />
                </Button>
                <span className="lg:hidden">
                  <Brand />
                </span>
                {meta ? (
                  <div className="order-last flex w-full min-w-0 items-center gap-2 sm:order-0 sm:w-auto sm:flex-1">
                    <CitySearch meta={meta} value={city} onSelect={(c) => go({ city: c })} />
                  </div>
                ) : (
                  <p className="flex-1 text-sm text-muted-foreground">The TravelSafe service isn&apos;t responding.</p>
                )}
                {meta ? (
                  <div className="ml-auto flex items-center gap-2">
                    <RefreshControl city={city} updated={updated} />
                    <Select value={persona} onValueChange={(v) => go({ persona: v })}>
                      <SelectTrigger aria-label="Traveller profile" className="h-8 gap-2 pr-2 pl-1.5">
                        <span aria-hidden className="grid size-6 place-items-center rounded-full bg-brand-soft text-accent-foreground">
                          <UserRound className="size-3.5" />
                        </span>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent align="end">
                        {meta.personas.map((p) => (
                          <SelectItem key={p.id} value={p.id}>
                            {p.name} traveller
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                ) : null}
              </div>
            </header>
            <main id="main" className="mx-auto max-w-360 px-4 py-6 sm:px-6 lg:px-8">
              {children}
            </main>
          </div>
        </div>
      </UpdatedCtx.Provider>
    </TooltipProvider>
  );
}
