"""
Travel briefing report (PDF and print-ready HTML)
=================================================

Both formats are rendered from one ``ReportModel`` built from the same API
responses the app shows (overview + weather), so the report can never
calculate or say something different from the dashboard.

Structure (page count follows the amount of data; nothing is padded):

1. Executive summary – city, profile, dates, overall and personal result,
   data confidence, takeaways, active alerts, one line per factor.
2. Risk factors and recent events – what drives the result and the most
   relevant incidents, with plain reliability notes.
3. Context – practical precautions, weather, air quality, natural hazards,
   sources, attribution and freshness, method
   in brief, limitations.

No raw model values (weights, confidences, impact units, cache data) appear.
"""

from __future__ import annotations

import html
import io
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, List, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (CondPageBreak, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

INK = "#14213D"
SOFT = "#3A4560"
MUTED = "#5D6676"
LINE = "#DCDFD8"
TEAL = "#2F7A78"
LEVEL_COLOURS = {"low": "#3F7D58", "guarded": "#8A5F0E", "elevated": "#B4532A", "high": "#A3332F",
                 "insufficient": "#5D6676", "unknown": "#5D6676"}
LEVEL_WORD = {"low": "Low", "guarded": "Guarded", "elevated": "Elevated", "high": "High",
              "insufficient": "No data", "unknown": "Not assessed"}
STATE_WORD = {"available": "Available", "stale": "Last available update", "broader_region": "Available (wider area)",
              "no_data": "No data for this location", "unavailable": "Unavailable",
              "not_configured": "Not set up", "not_applicable": "Not used for this assessment",
              "sample": "Sample data, not live"}


def _sentence(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def _date(dt: Optional[datetime], with_time: bool = False) -> str:
    if not isinstance(dt, datetime):
        return "Unknown"
    dt = dt.astimezone(timezone.utc)
    s = f"{dt.day} {dt:%b %Y}"
    return s + (f", {dt:%H:%M} UTC" if with_time else "")


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


@dataclass
class ReportEvent:
    title: str
    meta: str
    summary: Optional[str]
    reliability: str
    url: Optional[str]


@dataclass
class ReportModel:
    city: str
    place: str
    persona: str
    generated: str
    period: str
    data_note: str
    is_sample: bool
    general_label: str
    general_level: str
    general_summary: str
    personal_label: str
    personal_level: str
    personal_summary: str
    coverage_label: str
    coverage_summary: str
    takeaways: List[str]
    topics: List[tuple]  # (label, level, note)
    alerts: List[str]
    key_factors: List[str]
    events: List[ReportEvent]
    dos: List[str]
    donts: List[str]
    weather_lines: List[str]
    air_lines: List[str]
    hazard_lines: List[str]
    sources: List[str]
    method: List[str]
    limitations: List[str] = field(default_factory=list)
    disclaimer: str = ""


def build_model(ov: Any, wx: Any) -> ReportModel:
    place = ov.city.country if ov.city.region != "India" else f"{ov.city.area}, India"
    factors = {f.key: f for f in ov.factors}
    takeaways: List[str] = [f"{factors[k.category].label} is {LEVEL_WORD[k.level].lower()}: "
                            f"{factors[k.category].summary[:1].lower()}{factors[k.category].summary[1:]}"
                            for k in ov.key_factors[:2] if k.category in factors]
    if ov.coverage.state == "insufficient":
        takeaways = ["There isn't enough current evidence to assess this city. This is not a sign that it "
                     "is safe or unsafe; check official travel advice."]
    else:
        takeaways.extend(ov.stable_signals[: 3 - len(takeaways)])
        if not takeaways:
            takeaways.append("No assessed factor shows a notable concern.")
    unknown = [f.label.lower() for f in ov.factors if not f.assessed]
    if unknown and ov.coverage.state != "insufficient":
        takeaways.append("Not assessed: " + ", ".join(unknown) + ". Missing data is not treated as good news.")
    events: List[ReportEvent] = []
    for e in ov.recent_events[:6]:
        when = _date(e.published_at) if e.published_at else "Date unknown"
        meta = f"{e.category_label} | {e.severity_label} | {e.source} | {when}"
        rel = [e.confidence_label, e.location_label.lower()]
        if e.report_count > 1:
            rel.append(f"{e.report_count} reports merged as one incident")
        rel.extend(n.lower() for n in e.notes[:2])
        events.append(ReportEvent(e.title, meta, e.summary, _sentence("; ".join(rel)) + ".", e.url))
    weather_lines: List[str] = []
    if wx.current is not None:
        c = wx.current
        def num(v: Any, unit: str) -> str:
            return f"{v:.0f}{unit}" if isinstance(v, (int, float)) else "n/a"
        weather_lines.append(f"Current conditions ({wx.provider}): {c.condition or 'not described'}, "
                             f"{num(c.temperature_c, ' °C')} (feels like {num(c.feels_like_c, ' °C')}), "
                             f"wind {num(c.wind_kmh, ' km/h')}, humidity {num(c.humidity_pct, '%')}.")
        if wx.status == "stale":
            weather_lines.append("The latest refresh failed; these are the last available conditions.")
        if wx.conditions.factors or wx.conditions.forecast_hazards:
            weather_lines.append("Notable: " + "; ".join(f.lower() for f in wx.conditions.factors
                                                         + wx.conditions.forecast_hazards) + ".")
        days = [d for d in wx.daily[:3]]
        if days:
            weather_lines.append("Next days: " + "; ".join(
                f"{d.date}: {d.condition or 'n/a'}, {num(d.temp_min_c, '')}–{num(d.temp_max_c, ' °C')}"
                + (f", {d.precip_mm:.0f} mm" if isinstance(d.precip_mm, (int, float)) and d.precip_mm >= 1 else "")
                for d in days) + ".")
        if wx.alerts:
            weather_lines.append(f"{len(wx.alerts)} official weather alert(s) active: "
                                 + "; ".join(a.event for a in wx.alerts) + ".")
        elif wx.alerts_message:
            weather_lines.append(wx.alerts_message)
        if wx.attribution:
            weather_lines.append(wx.attribution + ".")
    else:
        weather_lines.append(f"Live weather was unavailable: {wx.reason or 'no provider answered.'} "
                             "The weather factor is therefore not assessed.")
    air_lines: List[str] = []
    a = ov.air_now
    if a.measured:
        air_lines.append(f"{a.category or 'Uncategorised'} (indicative) at {a.station}, {a.distance_km:.0f} km away"
                         + (f"; PM2.5 {a.pm25:g} µg/m³." if a.pm25 is not None else "."))
    else:
        air_lines.append((a.message or "No measurements available.") + " Air quality is not assessed.")
    if a.modelled_category:
        air_lines.append(f"Modelled estimate (Open-Meteo, ~45 km grid, context only): {a.modelled_category.lower()}.")
    hz = factors.get("disaster")
    hazard_lines = [hz.summary] if hz else []
    hazard_lines += [ev.text for ev in (hz.evidence if hz else []) if ev.kind == "feed_event"][:3]
    sources = []
    for s in ov.sources:
        line = f"{s.name}: {STATE_WORD.get(s.state, s.state)}"
        if s.provider and s.state not in ("unavailable", "sample", "not_configured"):
            line += f" ({s.provider})"
        if s.updated_at and s.state not in ("unavailable", "not_configured"):
            line += f", retrieved {_date(s.updated_at, True)}"
        if s.message:
            line += f". {s.message}"
        sources.append(line)
    sources += sorted({s.attribution + "." for s in ov.sources if s.attribution and s.state != "not_applicable"})
    data_note = ("Sample headlines for demonstration, not live news" if ov.data_mode == "sample"
                 else ("Live news, weather, air-quality and hazard feeds" if ov.data_mode == "live"
                       else "No news; other feeds where available"))
    alerts = [f"{_sentence(c.level)}: {c.title} ({c.source}{', ' + _date(c.when) if c.when else ''})."
              for c in ov.critical_alerts]
    return ReportModel(
        city=ov.city.name, place=place, persona=ov.persona.name, generated=_date(datetime.now(timezone.utc), True),
        period=f"{_date(ov.period.start)} to {_date(ov.period.end)}", data_note=data_note,
        is_sample=ov.data_mode == "sample",
        general_label=ov.general.label, general_level=ov.general.level, general_summary=ov.general.summary,
        personal_label=ov.personalized.label, personal_level=ov.personalized.level,
        personal_summary=ov.persona_explanation,
        coverage_label=ov.coverage.label,
        coverage_summary=f"{ov.coverage.summary} {ov.coverage.factors_assessed} of {ov.coverage.factors_total} factors assessed.",
        takeaways=takeaways[:4],
        topics=[(f.label, f.level if f.assessed else "unknown", f.summary) for f in ov.factors],
        alerts=alerts, key_factors=[k.text for k in ov.key_factors], events=events,
        dos=ov.precautions.dos[:5], donts=ov.precautions.donts[:4], weather_lines=weather_lines,
        air_lines=air_lines, hazard_lines=hazard_lines, sources=sources,
        method=[
            "Six factors are checked separately: crime and security, civil disruption, transport disruption, "
            "natural hazards, weather and air quality. Each uses its own sources.",
            "News reports are sorted by topic and rated by how serious they are. Reports about other places, "
            "repeated coverage and older events count for less or are left out.",
            "Natural hazards use earthquake (USGS) and disaster-alert (GDACS) feeds by distance from the city; "
            "weather uses live conditions and the 48-hour forecast; air quality uses station measurements only.",
            "A factor without data is marked 'not assessed' and never counts as good news. Serious official alerts "
            "always raise the overall result, whatever the other factors say.",
            "Traveller profiles change how much each factor matters; they never add risk where there is none.",
        ],
        limitations=[
            "News coverage is not the same as how often incidents happen.",
            "Classification is automatic and can misread unusual wording.",
            "Air-quality categories are indicative (latest hourly value, not a 24-hour average).",
            "Official weather alerts are only checked when the installation has an alert-capable weather plan.",
        ],
        disclaimer=ov.disclaimer,
    )


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

_REPL = {"→": "->", "≈": "~", "×": "x", "−": "-", "…": "...", "≥": ">=", "≤": "<=", "“": '"',
         "”": '"', "’": "'", "‘": "'", "²": "2"}


def _t(text: Any) -> str:
    s = "" if text is None else str(text)
    for a, b in _REPL.items():
        s = s.replace(a, b)
    s = s.encode("cp1252", errors="replace").decode("cp1252")
    return html.escape(s)


class _NumberedCanvas(rl_canvas.Canvas):
    """Adds 'Page N of M' and a discreet footer to every page."""

    def __init__(self, *args: Any, city: str = "", **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved: List[dict] = []
        self._city = city

    def showPage(self) -> None:  # noqa: N802 - ReportLab API
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total = len(self._saved)
        for state in self._saved:
            self.__dict__.update(state)
            self.setFont("Helvetica", 8)
            self.setFillColor(colors.HexColor(MUTED))
            self.drawString(20 * mm, 12 * mm, _t(f"TravelSafe travel briefing: {self._city}"))
            self.drawRightString(A4[0] - 20 * mm, 12 * mm, f"Page {self._pageNumber} of {total}")
            self.setStrokeColor(colors.HexColor(LINE))
            self.line(20 * mm, 15 * mm, A4[0] - 20 * mm, 15 * mm)
            super().showPage()
        super().save()


def build_pdf_from_model(m: ReportModel) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=20 * mm,
                            bottomMargin=22 * mm, title=f"TravelSafe briefing - {m.city}", author="TravelSafe")
    body = ParagraphStyle("body", fontName="Helvetica", fontSize=10.5, leading=15, textColor=colors.HexColor(SOFT),
                          alignment=TA_LEFT)
    small = ParagraphStyle("small", parent=body, fontSize=9, leading=12.5, textColor=colors.HexColor(MUTED))
    kicker = ParagraphStyle("kicker", parent=body, fontName="Helvetica-Bold", fontSize=9.5,
                            textColor=colors.HexColor(TEAL), spaceAfter=4)
    title = ParagraphStyle("title", fontName="Times-Bold", fontSize=30, leading=34, textColor=colors.HexColor(INK))
    h2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=13, leading=17, textColor=colors.HexColor(INK),
                        spaceBefore=14, spaceAfter=6, keepWithNext=1)
    label = ParagraphStyle("label", parent=small, spaceAfter=1)
    big = ParagraphStyle("big", fontName="Helvetica-Bold", fontSize=16, leading=20, spaceAfter=3)
    ev_title = ParagraphStyle("evt", parent=body, fontName="Helvetica-Bold", textColor=colors.HexColor(INK))
    bullet = ParagraphStyle("bullet", parent=body, leftIndent=12, bulletIndent=0, spaceAfter=3)

    def bullets(items: List[str]) -> List[Any]:
        return [Paragraph(_t(x), bullet, bulletText="•") for x in items]

    story: List[Any] = [
        Paragraph("TravelSafe travel briefing", kicker),
        Paragraph(_t(m.city), title),
        Spacer(1, 3),
        Paragraph(_t(f"{m.place}. Prepared for {m.persona.lower()} travellers."), body),
        Paragraph(_t(f"Generated {m.generated}. Covers {m.period}. Data: {m.data_note}."), small),
    ]
    if m.is_sample:
        note = Table([[Paragraph(_t("Sample data: this briefing uses synthetic demonstration headlines. It does "
                                    "not describe current conditions."), body)]], colWidths=[170 * mm])
        note.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F6ECD6")),
                                  ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                                  ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        story += [Spacer(1, 8), note]

    def result(heading: str, lbl: str, lvl: str, text: str) -> List[Any]:
        return [Paragraph(_t(heading), label),
                Paragraph(f"<font color='{LEVEL_COLOURS[lvl]}'>{_t(lbl)}</font>", big),
                Paragraph(_t(text), body)]

    pair = Table([[result("Overall assessment", m.general_label, m.general_level, m.general_summary),
                   result(f"For {m.persona.lower()} travellers", m.personal_label, m.personal_level,
                          m.personal_summary)]], colWidths=[85 * mm, 85 * mm])
    pair.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("RIGHTPADDING", (0, 0), (0, 0), 12), ("LEFTPADDING", (1, 0), (1, 0), 12),
                              ("LINEBEFORE", (1, 0), (1, 0), 0.6, colors.HexColor(LINE)),
                              ("TOPPADDING", (0, 0), (-1, -1), 0)]))
    story += [Spacer(1, 14), pair, Spacer(1, 10),
              Paragraph(_t(f"Data confidence: {m.coverage_label}. {m.coverage_summary}"), small),
              Paragraph("Key takeaways", h2)] + bullets(m.takeaways)

    if m.alerts:
        story.append(Paragraph("Active alerts", h2))
        story += bullets(m.alerts)
    story.append(Paragraph("By factor", h2))
    rows = []
    for lbl, lvl, note in m.topics:
        rows.append([Paragraph(_t(lbl), ParagraphStyle("tl", parent=body, textColor=colors.HexColor(INK))),
                     Paragraph(f"<font color='{LEVEL_COLOURS[lvl]}'><b>{_t(LEVEL_WORD[lvl])}</b></font>", body),
                     Paragraph(_t(note), small)])
    t = Table(rows, colWidths=[58 * mm, 24 * mm, 88 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                           ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.HexColor(LINE))]))
    story.append(t)

    # Page 2 – factors and events (only when there is something to show)
    if m.key_factors or m.events:
        story.append(PageBreak())
        story.append(Paragraph("What drives the assessment", h2))
        story += bullets(m.key_factors) if m.key_factors else [Paragraph("No assessed factor is above Low.", body)]
        if m.events:
            story.append(Paragraph("Most relevant recent events", h2))
            story.append(Paragraph(_t("Ranked by influence on the assessment. Reliability notes describe how sure "
                                      "TravelSafe is about each report."), small))
            for e in m.events:
                block = [Spacer(1, 8), Paragraph(_t(e.title), ev_title), Paragraph(_t(e.meta), small)]
                if e.summary:
                    block.append(Paragraph(_t(e.summary), body))
                block.append(Paragraph(_t(e.reliability), small))
                if e.url:
                    block.append(Paragraph(f"<link href='{html.escape(e.url)}' color='{TEAL}'>Source article</link>",
                                           small))
                story.append(KeepTogether(block))

    # Context
    story.append(CondPageBreak(70 * mm))
    story.append(Paragraph("Practical precautions", h2))
    story += bullets(m.dos)
    if m.donts:
        story.append(Paragraph("Avoid", ParagraphStyle("sub", parent=body, fontName="Helvetica-Bold",
                                                       textColor=colors.HexColor(INK), spaceBefore=6,
                                                       keepWithNext=1)))
        story += bullets([_sentence(d.replace("Don't ", "")) for d in m.donts])
    story.append(Paragraph("Weather", h2))
    story += [Paragraph(_t(x), body) for x in m.weather_lines]
    story.append(Paragraph("Air quality", h2))
    story += [Paragraph(_t(x), body) for x in m.air_lines]
    if m.hazard_lines:
        story.append(Paragraph("Natural hazards", h2))
        story += [Paragraph(_t(x), body) for x in m.hazard_lines]
    story.append(Paragraph("Data sources and freshness", h2))
    story += bullets(m.sources)
    story.append(KeepTogether([Paragraph("How the assessment works", h2)] + bullets(m.method)))
    story.append(KeepTogether([Paragraph("Limitations", h2)] + bullets(m.limitations)
                              + [Spacer(1, 6), Paragraph(_t(m.disclaimer), small)]))

    doc.build(story, canvasmaker=lambda *a, **k: _NumberedCanvas(*a, city=m.city, **k))
    return buf.getvalue()


def build_pdf(ov: Any, wx: Any) -> bytes:
    return build_pdf_from_model(build_model(ov, wx))


# ---------------------------------------------------------------------------
# HTML (print-ready)
# ---------------------------------------------------------------------------


def build_html_from_model(m: ReportModel) -> str:
    e = html.escape

    def ul(items: List[str]) -> str:
        return "<ul>" + "".join(f"<li>{e(x)}</li>" for x in items) + "</ul>"

    topics = "".join(f"<tr><th scope='row'>{e(lbl)}</th><td class='lvl {lvl}'>{e(LEVEL_WORD[lvl])}</td>"
                     f"<td class='muted'>{e(note)}</td></tr>" for lbl, lvl, note in m.topics)
    events = "".join(
        f"<article class='ev'><h3>{e(ev.title)}</h3><p class='muted'>{e(ev.meta)}</p>"
        + (f"<p>{e(ev.summary)}</p>" if ev.summary else "")
        + f"<p class='muted'>{e(ev.reliability)}"
        + (f" <a href='{e(ev.url)}' rel='noopener noreferrer'>Source article</a>" if ev.url else "")
        + "</p></article>" for ev in m.events)
    sample = ("<p class='notice'>Sample data: this briefing uses synthetic demonstration headlines. It does not "
              "describe current conditions.</p>" if m.is_sample else "")
    second = ""
    if m.key_factors or m.events:
        second = ("<section class='page'><h2>What drives the assessment</h2>"
                  + (ul(m.key_factors) if m.key_factors else "<p>No assessed factor is above Low.</p>")
                  + ("<h2>Most relevant recent events</h2><p class='muted'>Ranked by influence on the assessment."
                     "</p>" + events if m.events else "") + "</section>")
    donts = [_sentence(d.replace("Don't ", "")) for d in m.donts]
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TravelSafe briefing: {e(m.city)}</title>
<style>
 @page {{ size: A4; margin: 20mm 20mm 22mm; }}
 body {{ font-family: "Segoe UI", Helvetica, Arial, sans-serif; color: {SOFT}; font-size: 15px; line-height: 1.55;
        max-width: 760px; margin: 40px auto; padding: 0 24px; }}
 h1 {{ font-family: Georgia, "Times New Roman", serif; color: {INK}; font-size: 40px; margin: 2px 0 6px; }}
 h2 {{ color: {INK}; font-size: 18px; margin: 32px 0 8px; break-after: avoid; }}
 h3 {{ color: {INK}; font-size: 15px; margin: 0 0 2px; }}
 .kicker {{ color: {TEAL}; font-weight: 600; font-size: 13px; margin: 0; }}
 .muted {{ color: {MUTED}; font-size: 13px; }}
 .notice {{ background: #F6ECD6; padding: 10px 14px; border-radius: 6px; }}
 .pair {{ display: grid; grid-template-columns: 1fr 1fr; gap: 28px; margin-top: 24px; }}
 .pair > div + div {{ border-left: 1px solid {LINE}; padding-left: 28px; }}
 .big {{ font-size: 21px; font-weight: 700; margin: 2px 0 6px; }}
 table {{ width: 100%; border-collapse: collapse; }} th, td {{ text-align: left; padding: 8px 8px 8px 0;
        border-bottom: 1px solid {LINE}; vertical-align: top; }} th {{ color: {INK}; font-weight: 500; }}
 .lvl {{ font-weight: 700; white-space: nowrap; }}
 {"".join(f".lvl.{k}, .c-{k} {{ color: {v}; }}" for k, v in LEVEL_COLOURS.items())}
 .ev {{ padding: 12px 0; border-bottom: 1px solid {LINE}; break-inside: avoid; }} .ev p {{ margin: 4px 0; }}
 a {{ color: {TEAL}; }} li {{ margin-bottom: 4px; }}
 .page {{ break-before: page; }}
 .toolbar {{ text-align: right; }} .toolbar button {{ font: inherit; padding: 6px 12px; cursor: pointer; }}
 @media print {{ .toolbar {{ display: none; }} body {{ margin: 0; max-width: none; font-size: 11pt; }} }}
 @media (max-width: 640px) {{ .pair {{ grid-template-columns: 1fr; }} .pair > div + div {{ border: 0; padding: 0; }} }}
</style></head><body>
<div class="toolbar"><button onclick="window.print()">Print or save as PDF</button></div>
<section>
<p class="kicker">TravelSafe travel briefing</p>
<h1>{e(m.city)}</h1>
<p>{e(m.place)}. Prepared for {e(m.persona.lower())} travellers.</p>
<p class="muted">Generated {e(m.generated)}. Covers {e(m.period)}. Data: {e(m.data_note)}.</p>
{sample}
<div class="pair">
 <div><div class="muted">Overall assessment</div><div class="big c-{m.general_level}">{e(m.general_label)}</div>
 <p>{e(m.general_summary)}</p></div>
 <div><div class="muted">For {e(m.persona.lower())} travellers</div><div class="big c-{m.personal_level}">{e(m.personal_label)}</div>
 <p>{e(m.personal_summary)}</p></div>
</div>
<p class="muted">Data confidence: {e(m.coverage_label)}. {e(m.coverage_summary)}</p>
<h2>Key takeaways</h2>{ul(m.takeaways)}
{('<h2>Active alerts</h2>' + ul(m.alerts)) if m.alerts else ''}
<h2>By factor</h2><table>{topics}</table>
</section>
{second}
<section>
<h2>Practical precautions</h2>{ul(m.dos)}
{('<h3>Avoid</h3>' + ul(donts)) if donts else ''}
<h2>Weather</h2>{"".join(f"<p>{e(x)}</p>" for x in m.weather_lines)}
<h2>Air quality</h2>{"".join(f"<p>{e(x)}</p>" for x in m.air_lines)}
{('<h2>Natural hazards</h2>' + "".join(f"<p>{e(x)}</p>" for x in m.hazard_lines)) if m.hazard_lines else ''}
<h2>Data sources and freshness</h2>{ul(m.sources)}
<h2>How the assessment works</h2>{ul(m.method)}
<h2>Limitations</h2>{ul(m.limitations)}
<p class="muted">{e(m.disclaimer)}</p>
</section>
</body></html>"""


def build_html(ov: Any, wx: Any) -> str:
    return build_html_from_model(build_model(ov, wx))


def report_filename(city: str, persona: str, ext: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    safe = "".join(ch if ch.isalnum() else "-" for ch in city.lower())
    return f"travelsafe-{safe}-{persona}-{stamp}.{ext}"
