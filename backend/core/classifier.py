"""
Event classifier
================

Rule-based, explainable classifier that turns a news item into an event
category, subtype, severity (-3..+3) and a separate classification
confidence (0..1).

Why it was rewritten
--------------------
The previous classifier:

* matched keywords as raw substrings ("rain" matched "train"/"Bahrain",
  "march" matched the month, "drug" matched "drugstore");
* divided keyword confidence by 3 and discarded anything below 0.3, so most
  single-keyword headlines (e.g. "Robbery at jewelry store", "Cyclone alert
  issued") became *neutral* while "Two arrested ..." became crime;
* derived severity from a second, inconsistent keyword list;
* depended on a TF-IDF model trained on templates of its own keywords, which
  added no information and silently failed to train on current
  scikit-learn (``multi_class`` was removed).

Design
------
1. Text is lower-cased and normalised; all patterns use word boundaries.
2. Each rule has a category, subtype, base severity and evidence weight.
3. Matches preceded by a negator ("no", "denies", "rumours of", "fake") are
   ignored; matches inside awareness/drill/campaign headlines are ignored.
4. Severity is the most severe matched rule, then adjusted by casualty
   language (fatalities/injuries escalate; "minor", "no injuries" cap it).
5. Historical references and crimes resolved by arrest are flagged; the
   scoring layer down-weights them.
6. Confidence reflects strength and agreement of evidence and is reduced
   for ambiguity between categories or mixed negated signals.

The classifier never infers personal or protected characteristics.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Tuple

from .models import ClassifiedEvent, NewsItem

# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize(text: Optional[str]) -> str:
    if not text:
        return ""
    text = text.lower().replace("’", "'").replace("'", "")
    return " " + _NON_ALNUM.sub(" ", text).strip() + " "


NEGATORS = {
    "no", "not", "never", "deny", "denies", "denied", "denial", "rumour", "rumours",
    "rumor", "rumors", "hoax", "fake", "false", "unfounded", "without", "nor", "dismiss",
    "dismisses", "dismissed", "debunk", "debunks", "debunked",
}
_NEGATION_WINDOW = 4


def _is_negated(text: str, start: int) -> bool:
    before = text[:start].split()[-_NEGATION_WINDOW:]
    if any(tok in NEGATORS for tok in before):
        return True
    # "ruled out", "rules out" just before the term
    joined = " ".join(before)
    return "ruled out" in joined or "rules out" in joined


def _rx(pattern: str) -> re.Pattern:
    return re.compile(r"(?<![a-z0-9])(?:" + pattern + r")(?![a-z0-9])")


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Rule:
    category: str
    subtype: str
    severity: int
    weight: float
    pattern: re.Pattern
    exclude: Optional[re.Pattern] = None


def _rule(category, subtype, severity, weight, pattern, exclude=None) -> Rule:
    return Rule(category, subtype, severity, weight, _rx(pattern), _rx(exclude) if exclude else None)


RULES: List[Rule] = [
    # ---- Crime ----------------------------------------------------------
    _rule("crime", "terrorism", -3, 0.9,
          r"terror(ist)? (attack|strike)s?|bomb (blast|attack)s?|suicide bomb(ing|er)?s?|"
          r"mass shooting|massacre|serial killer|ied blast"),
    _rule("crime", "homicide", -2, 0.85,
          r"murder(ed|s|er)?|homicides?|stabbed to death|shot dead|hacked to death|"
          r"beaten to death|lynch(ed|ing)"),
    _rule("crime", "kidnapping", -2, 0.85, r"kidnap(ped|ping|s)?|abduct(ed|ion|s)?"),
    _rule("crime", "sexual violence & harassment", -2, 0.8,
          r"rape[ds]?|sexual(ly)? assault(ed)?|molest(ed|ation)?|harass(ed|ment)?|"
          r"eve teasing|stalk(ed|ing)"),
    _rule("crime", "robbery & snatching", -2, 0.8,
          r"armed robbery|robber(y|ies)|robbed|dacoity|mugg(ed|ing)|"
          r"(chain|bag|phone|mobile) snatch(ing|ers?|ed)?|snatch(ing|ers?|ed)|loot(ed|ing)"),
    _rule("crime", "assault", -2, 0.78,
          r"assault(ed|s)?|stabb(ed|ing)|stab wounds?|shoot ?out|shooting|shot at|"
          r"gang (war|violence)|brawl|thrashed|acid attack",
          exclude=r"film|movie|shooting schedule|photo ?shoot|ad shoot|shooting star|shooting range"),
    _rule("crime", "theft & burglary", -1, 0.75,
          r"theft|thieves|thief|stole|stolen|steal(ing|s)?|pickpocket(s|ing|ed|ers?)?|"
          r"burglar(y|ies|s)?|break in|house ?break(ing)?|vehicle lifting|shoplift(ing)?"),
    _rule("crime", "fraud & scams", -1, 0.7,
          r"fraud(s|sters?)?|scam(s|mers?|med)?|cheat(ed|ing)|cyber ?crimes?|phishing|"
          r"extortion|duped|swindl(ed|ing)"),
    _rule("crime", "drugs", -1, 0.7,
          r"drug (racket|peddl\w*|haul|bust|cartel|traffick\w*|syndicate)|narcotics?|"
          r"smuggl(ing|ed|ers?)|ganja|cocaine|heroin|mdma"),
    _rule("crime", "vandalism", -1, 0.65, r"vandal(ism|ised|ized|s)?"),
    # ---- Protest / civil disruption ------------------------------------
    _rule("protest", "unrest", -2, 0.85,
          r"riots?|rioting|mob violence|violent (clash(es)?|protests?|unrest)|clash(es|ed)|"
          r"stone pelting|arson|curfew|section 144|prohibitory orders|communal tension|"
          r"lathi ?charge|tear ?gas"),
    _rule("protest", "demonstration & strike", -1, 0.72,
          r"protests?|protesters|protestors|protested|demonstrations?|rally|rallies|"
          r"strikes?|bandh|hartal|shut ?down|blockades?|road blockade|agitation|dharna|"
          r"sit in|chakka jam|march(es)? (towards|to|against)|protest march",
          exclude=r"air ?strikes?|lightning strikes?|strike rate|hunger strike over|shutdown of (app|server|website)"),
    # ---- Accidents & service disruption --------------------------------
    _rule("accident", "structural / mass-casualty", -2, 0.88,
          r"(building|bridge|wall|roof|flyover|structure) collapse[ds]?|derail(ed|ment|s)?|"
          r"plane crash|air crash|stampede|capsiz(ed|es|e)"),
    _rule("accident", "road & transport accident", -1, 0.78,
          r"accidents?|crash(ed|es)?|collision|collided|pile ?up|overturn(s|ed)?|hit and run|"
          r"mishap|run over|(hits?|rams?|rammed|crashes into) (a |the |into )?(divider|pole|tree|"
          r"wall|truck|lorry|bus|car|pedestrians?|barricade)",
          exclude=r"stock market crash|market crash|crash course|app crash(es|ed)?|server crash"),
    _rule("accident", "fire & explosion", -1, 0.78,
          r"fire (broke|breaks|break) out|fire at|blaze|gutted|caught fire|catches fire|"
          r"fire breaks|major fire|explosion|cylinder blast|gas leak|boiler blast",
          exclude=r"ceasefire|fire ?works|fired from|opened fire"),
    _rule("accident", "service disruption", -1, 0.62,
          r"(train|metro|local train|flight|bus|rail|ferry) (services? )?(disrupted|suspended|cancelled|"
          r"canceled|delayed|halted|hit)|flights? (delayed|diverted|cancelled|canceled)|"
          r"(power|electricity) (outage|cut|failure|supply disrupted)|outages?|blackout|"
          r"water supply (disrupted|cut|hit|affected)|pipeline burst|traffic (jam|congestion|"
          r"diversions?|snarl|chaos)|road closures?|roads? closed|technical fault"),
    # ---- Disasters & public health --------------------------------------
    _rule("disaster", "earthquake", -2, 0.9, r"earthquakes?|quake"),
    _rule("disaster", "minor seismic", -1, 0.8, r"tremors?|aftershocks?|mild quake|minor quake"),
    _rule("disaster", "storm system", -2, 0.88,
          r"cyclone|hurricane|typhoon|tornado|super cyclone|tropical storm"),
    _rule("disaster", "flood & landslide", -2, 0.85,
          r"floods?|flooding|flooded|flash floods?|inundat(ed|ion)|landslides?|"
          r"mudslides?|cloudburst|avalanche",
          exclude=r"flood of (tourists|visitors|devotees|calls|messages|applications|wishes)"),
    _rule("disaster", "fire & eruption", -2, 0.85,
          r"wildfires?|forest fires?|bushfires?|volcan(o|ic) eruptions?|volcano erupts"),
    _rule("disaster", "tsunami", -3, 0.95, r"tsunami"),
    _rule("disaster", "public health", -1, 0.65,
          r"epidemic|pandemic|outbreak|food poisoning|dengue|cholera|malaria cases|"
          r"heat stroke cases|virus cases"),
    # ---- Weather --------------------------------------------------------
    _rule("weather", "severe weather", -2, 0.85,
          r"red alert|orange alert|extreme heat|heat ?waves?|cold ?waves?|hailstorms?|"
          r"blizzards?|torrential( rain)?|very heavy rain(fall)?|dense fog|zero visibility|"
          r"severe (storm|thunderstorm|weather)|dust ?storm"),
    _rule("weather", "rain & storms", -1, 0.7,
          r"heavy rain(fall|s)?|rain(fall|s)?|showers|downpour|thunderstorms?|storms?|"
          r"waterlogg(ing|ed)|gusty winds?|strong winds?|yellow alert|weather (advisory|"
          r"warning|alert)",
          exclude=r"brain ?storm(ing)?|rain ?check|storm(ed|s) (to|into|out)|"
                  r"taking .* by storm|social media storm|political storm"),
    _rule("weather", "hazardous air quality", -2, 0.8,
          r"(air quality|aqi)( index)?( \w+){0,4} (severe|hazardous|very poor)|"
          r"(severe|hazardous|very poor) (air quality|aqi)|toxic smog"),
    _rule("weather", "fog & air quality", -1, 0.7,
          r"fog|smog|air quality|aqi|air pollution|haze"),
    # ---- Positive / civic (context only) --------------------------------
    _rule("positive", "civic & tourism", 1, 0.7,
          r"festivals?|celebrat(ion|ions|es|ed)|carnival|inaugurat(ed|es|ion)|"
          r"opens? for (public|visitors)|new (metro|terminal|flyover|road|line|airport)|"
          r"tourism|tourists flock|heritage walk|marathon|cleanliness drive|clean ?up drive|"
          r"cleaning drive|beautification|recognition|awards?|record (ridership|visitors|tourists)"),
    _rule("positive", "safety improvement", 2, 0.85,
          r"crime (rate|cases)? ?(drops?|dips?|falls?|declines?|down)|decline in (crime|"
          r"accidents)|safest city|patrol(s|ling)? (increased|stepped up)|"
          r"(increase|step up|stepped up) (police )?patrol(s|ling)?|cctv cameras? installed|"
          r"safety measures"),
]

# Context patterns -----------------------------------------------------------

FATAL = _rx(r"killed|dead|died|dies|death toll|deaths?|fatal(ly|ities)?|bodies|"
            r"lost (their |his |her )?lives?|charred|succumbed")
MASS = _rx(r"([3-9]|[1-9][0-9]+|three|four|five|six|seven|eight|nine|ten|dozens?|scores of|"
           r"hundreds|several|multiple|many) (people |persons |passengers |pilgrims |workers )?"
           r"(killed|dead|died|deaths|feared dead|bodies)|mass casualt\w*|death toll")
INJURY = _rx(r"injur(ed|ies|y)|hurt|wounded|hospitali[sz]ed|critical condition")
DEESCALATE_CRIME = _rx(r"petty|minor scuffle|no one (was )?(injured|hurt)")
DEESCALATE = _rx(r"minor|small|petty|no (one|body) (was )?(injured|hurt|killed)|"
                 r"no (injuries|casualties|damage|deaths?|loss of life)|without (injur\w+|casualt\w+)|"
                 r"averted|narrow escape|brought under control|under control|false alarm")
MILD_WEATHER = _rx(r"light|mild|pleasant|moderate|drizzle|brief")
HEAVY_WEATHER = _rx(r"heavy|very heavy|torrential|severe|extreme|intense")
FORECAST = _rx(r"expected|likely|forecast|predicted|predicts|warns of|may (see|witness)")
PEACEFUL = _rx(r"peaceful(ly)?")
RESOLVED = _rx(r"arrest(ed|s)?|held|nabbed|nabs|nab|bust(ed|s)?|caught|apprehended|detained|"
               r"in custody|held for|cracked|solved")
ONGOING = _rx(r"manhunt|absconding|at large|on the run|search on|yet to be (traced|arrested)")
POLICE_ACTION = _rx(r"police (arrest|nab|bust|raid)\w*|raid(s|ed)?|crackdown")
AWARENESS = _rx(r"awareness|mock drill|drills?|campaign|workshop|seminar|training session|"
                r"preparedness|safety audit|exhibition|film|movie|web series|novel|"
                r"documentary|book launch")
HISTORICAL = _rx(r"anniversary|years? ago|decades? ago|verdict|sentenced|convicted|acquitted|"
                 r"life imprisonment|death sentence|trial (begins|opens)|cold case|remember(s|ing)|"
                 r"memorial|recalls?|commemorat\w+")
_YEAR_CONTEXT = re.compile(r"(?<![a-z0-9])(in|of|since|during) ((19|20)\d{2})(?![a-z0-9])|"
                           r"(?<![a-z0-9])((19|20)\d{2}) (blasts?|attacks?|riots?|murders?|case|"
                           r"floods?|earthquake|accident|bombings?)(?![a-z0-9])")

RISK_CATEGORIES = ("crime", "protest", "accident", "disaster", "weather")


@dataclass
class _Hit:
    rule: Rule
    term: str
    in_title: bool
    negated: bool


@dataclass
class Classification:
    event_type: str
    subtype: str
    severity: int
    confidence: float
    matched_terms: List[str] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)
    is_historical: bool = False
    is_resolved: bool = False


def _collect_hits(title_n: str, desc_n: str) -> List[_Hit]:
    hits: List[_Hit] = []
    for rule in RULES:
        for text, in_title in ((title_n, True), (desc_n, False)):
            if not text.strip():
                continue
            for m in rule.pattern.finditer(text):
                if rule.exclude is not None:
                    window = text[max(0, m.start() - 30): m.end() + 30]
                    if rule.exclude.search(window):
                        continue
                hits.append(_Hit(rule, m.group(0).strip(), in_title, _is_negated(text, m.start())))
    return hits


def _category_score(hits: Iterable[_Hit]) -> Tuple[float, List[_Hit]]:
    active = [h for h in hits if not h.negated]
    if not active:
        return 0.0, []
    by_term = {}
    for h in active:
        prev = by_term.get(h.term)
        if prev is None or (h.in_title and not prev.in_title):
            by_term[h.term] = h
    weights = sorted((h.rule.weight for h in by_term.values()), reverse=True)
    score = weights[0] + 0.15 * sum(weights[1:])
    if any(h.in_title for h in by_term.values()):
        score += 0.1
    return score, list(by_term.values())


def _is_historical(text: str, reference_year: int) -> bool:
    if HISTORICAL.search(text):
        return True
    for m in _YEAR_CONTEXT.finditer(text):
        year = m.group(2) or m.group(4)
        if year and int(year) < reference_year:
            return True
    return False


def classify_text(title: str, description: Optional[str] = None,
                  reference_year: Optional[int] = None) -> Classification:
    """Classify a headline (+ optional description). Pure function."""
    reference_year = reference_year or datetime.now(timezone.utc).year
    title_n, desc_n = normalize(title), normalize(description)
    full = title_n + " " + desc_n
    flags: List[str] = []

    hits = _collect_hits(title_n, desc_n)

    # Awareness / drill / campaign headlines are not incidents.
    if AWARENESS.search(title_n):
        risk_hits = [h for h in hits if h.rule.category in RISK_CATEGORIES]
        if risk_hits:
            flags.append("awareness or preparedness context; not treated as an incident")
        hits = [h for h in hits if h.rule.category not in RISK_CATEGORIES]

    negated_terms = sorted({h.term for h in hits if h.negated})
    if negated_terms:
        flags.append("negated terms ignored: " + ", ".join(negated_terms))

    scores = {}
    for cat in RISK_CATEGORIES + ("positive",):
        scores[cat] = _category_score([h for h in hits if h.rule.category == cat])

    risk_ranked = sorted(
        ((scores[c][0], c) for c in RISK_CATEGORIES if scores[c][0] > 0), reverse=True
    )
    pos_score = scores["positive"][0]

    if not risk_ranked and pos_score == 0:
        return Classification("neutral", "general", 0, 0.5, [], flags)

    if not risk_ranked or pos_score > risk_ranked[0][0] + 0.1:
        active = scores["positive"][1]
        top = max(active, key=lambda h: (h.rule.severity, h.rule.weight))
        conf = min(0.9, top.rule.weight + 0.05 * (len(active) - 1))
        return Classification("positive", top.rule.subtype, top.rule.severity, round(conf, 2),
                              sorted({h.term for h in active}), flags)

    best_score, category = risk_ranked[0]
    active = scores[category][1]
    top = min(active, key=lambda h: (h.rule.severity, -h.rule.weight))
    severity = top.rule.severity
    subtype = top.rule.subtype

    # ---- Severity adjustments from casualty language -------------------
    def _active(pattern: re.Pattern) -> bool:
        return any(not _is_negated(full, m.start()) for m in pattern.finditer(full))

    fatal = _active(FATAL)
    mass = _active(MASS)
    injured = _active(INJURY)

    if fatal and category in ("accident", "disaster", "protest", "weather", "crime"):
        severity = min(severity, -2)
        flags.append("fatalities reported")
    if mass and fatal:
        severity = -3
        flags.append("multiple fatalities reported")
    elif injured and category in ("accident", "protest", "disaster"):
        severity = min(severity, -2)
        flags.append("injuries reported")
    deescalate = DEESCALATE_CRIME if category == "crime" else DEESCALATE
    limited_injury = re.search(r"minor injur|slight injur|minor burns", full) is not None
    if not fatal and (not injured or limited_injury) and deescalate.search(full):
        if severity < -1:
            flags.append("de-escalated: report describes limited impact")
        severity = max(severity, -1)
    if (category == "weather" and severity == -1 and not fatal
            and MILD_WEATHER.search(full) and not HEAVY_WEATHER.search(full)):
        severity = 0
        flags.append("mild weather conditions; no adverse impact assumed")
    if category == "protest" and PEACEFUL.search(full) and severity == -2 and not fatal:
        severity = -1
    if category in ("weather", "disaster") and FORECAST.search(full):
        flags.append("forecast or warning, not a confirmed impact")

    # ---- Resolution / historical --------------------------------------
    is_resolved = False
    if category == "crime" and RESOLVED.search(full) and not ONGOING.search(full):
        is_resolved = True
        flags.append("report describes arrest or police action")
    is_historical = _is_historical(full, reference_year)
    if is_historical:
        flags.append("historical reference (past incident, verdict or anniversary)")

    # ---- Confidence ----------------------------------------------------
    conf = top.rule.weight
    conf += min(0.1, 0.05 * (len(active) - 1))
    if any(h.in_title for h in active):
        conf += 0.05
    if len(risk_ranked) > 1 and risk_ranked[1][0] >= 0.8 * best_score:
        conf -= 0.1
        flags.append(f"ambiguous: also matches {risk_ranked[1][1]}")
    if any(h.negated and h.rule.category == category for h in hits):
        conf -= 0.15
    if not any(h.in_title for h in active):
        conf -= 0.1  # evidence only in the description
    conf = max(0.05, min(0.95, conf))

    terms = sorted({h.term for h in active})
    return Classification(category, subtype, max(-3, min(3, severity)), round(conf, 2),
                          terms, flags, is_historical, is_resolved)


def event_id(item: NewsItem) -> str:
    basis = (item.url or "") + "|" + item.title.strip().lower() + "|" + item.city.lower()
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def classify_news_item(item: NewsItem, reference_year: Optional[int] = None) -> ClassifiedEvent:
    c = classify_text(item.title, item.description, reference_year)
    return ClassifiedEvent(
        id=event_id(item),
        news_item=item,
        event_type=c.event_type,
        subtype=c.subtype,
        severity=c.severity,
        confidence=c.confidence,
        matched_terms=c.matched_terms,
        flags=c.flags,
        is_historical=c.is_historical,
        is_resolved=c.is_resolved,
        sources=[item.source],
        urls=[item.url] if item.url else [],
    )


def classify_news_list(items: List[NewsItem], reference_year: Optional[int] = None) -> List[ClassifiedEvent]:
    return [classify_news_item(i, reference_year) for i in items]
