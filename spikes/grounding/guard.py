"""
SPIKE 2 — grounding normalizer and the three-outcome guard.

Standard library only. Pure functions, no dependency on any other component, which
is why this risk can be closed before Phase 0 exists.

The design is AGENTS.md section 5:
  * context-gated extraction  — a number is financial only in a financial context
  * expanded accepted set     — build every legitimate representation of a payload
                                figure rather than parsing every spelling
  * three outcomes            — GROUNDED / UNVERIFIED / UNGROUNDED

SPIKE ONLY. Phase 13 re-implements this against the real payload schema; the corpus
carries forward to tests/data/grounding_corpus.jsonl.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class Outcome(str, Enum):
    GROUNDED = "GROUNDED"
    UNVERIFIED = "UNVERIFIED"      # guard limitation -> ACCEPT the response, flag it
    UNGROUNDED = "UNGROUNDED"      # confident parse, no payload match -> REJECT


# --------------------------------------------------------------------------
# configuration (Phase 13 moves these into app/config.py)
# --------------------------------------------------------------------------
MAGNITUDE_FLOOR = 1000.0          # a bare number this large is financial even
                                  # without a cue word
RELATIVE_TOLERANCE = 0.01         # 1%
ABSOLUTE_TOLERANCE = 1.0          # ±1 rupee
ABSOLUTE_TOLERANCE_MIN_MAGNITUDE = 100.0   # ...applied only to figures this large
SMALL_CUED_FLOOR = 100.0          # a cued number at least this large is a confident
                                  # financial claim even without a unit

CUE_WORDS = {
    "emi", "interest", "rate", "tenure", "principal", "amount", "loan", "repayment",
    "instalment", "installment", "months", "month", "years", "year", "yrs", "yr",
    "score", "lakh", "lakhs", "crore", "crores", "rs", "inr", "percent", "pa",
    "suitability", "total", "cost", "portfolio", "liquidate", "liquidated", "fee",
}

# Numbers appearing in these shapes are structural, never financial.
STRUCTURAL_PATTERNS = [
    re.compile(r"\b\d+(st|nd|rd|th)\b", re.I),                 # 1st, 2nd
    re.compile(r"\boption\s+\d+\b", re.I),                     # Option 2
    re.compile(r"\bsection\s+\d+\b", re.I),                    # Section 7
    re.compile(r"\bstep\s+\d+\b", re.I),                       # Step 3
    re.compile(r"\btop\s+\d+\b", re.I),                        # top 3
    re.compile(r"\b\d+\s+(alternatives?|options?|products?|lenders?|banks?|reasons?|choices?)\b", re.I),
    re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"),          # dates
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),                      # ISO dates
]

_MULTIPLIERS = {
    "lakh": 100_000.0, "lakhs": 100_000.0, "lac": 100_000.0, "lacs": 100_000.0,
    "l": 100_000.0,
    "crore": 10_000_000.0, "crores": 10_000_000.0, "cr": 10_000_000.0,
    "k": 1_000.0,
    "million": 1_000_000.0, "mn": 1_000_000.0,
}

# number, optionally preceded by a currency marker, optionally followed by a unit.
#
# The grouped-digits branch REQUIRES at least one comma group and is tried first;
# otherwise `\d{1,3}(?:,\d{2,3})*` matches only the first three digits of a plain
# number and "600000" is read as 600 followed by 000. That defect made grounded
# cases pass for entirely the wrong reason until the corpus caught it.
_NUMBER = re.compile(
    r"""
    (?:(?<![A-Za-z])(?P<currency>₹|rs\.?|inr)\s*)?
    (?P<number>\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)
    [\s-]*
    (?P<unit>%|percent|lakhs?|lacs?|crores?|cr\b|l\b|k\b|million|mn\b|months?|years?|yrs?|yr\b)?
    """,
    re.IGNORECASE | re.VERBOSE,
)


@dataclass
class Finding:
    text: str
    outcome: Outcome
    interpretations: list[float] = field(default_factory=list)
    note: str = ""


@dataclass
class GuardResult:
    outcome: Outcome
    findings: list[Finding] = field(default_factory=list)

    @property
    def rejected(self) -> bool:
        return self.outcome is Outcome.UNGROUNDED

    def offending(self) -> list[str]:
        return [f.text for f in self.findings if f.outcome is Outcome.UNGROUNDED]

    def unverified(self) -> list[str]:
        return [f.text for f in self.findings if f.outcome is Outcome.UNVERIFIED]


# --------------------------------------------------------------------------
# accepted set
# --------------------------------------------------------------------------
def build_accepted_set(payload: dict) -> set[float]:
    """
    Expand every payload figure into every legitimate representation of it.

    Expanding the accepted set is far more robust than trying to parse every
    possible spelling out of the response.
    """
    accepted: set[float] = set()

    def add(value: float) -> None:
        if value is None:
            return
        accepted.add(float(value))

    # NOTE: no lakh/crore/thousand *divisions* and no rounding expansion here.
    # The response side (_interpretations) already converts "6 lakh" and "6L" into
    # 600000, so the accepted set only needs base units. The original version added
    # v/1000 and round(v, -5) for every figure, which made sanctioned_limit
    # 15,000,000 accept a fabricated EMI of "Rs 15,000" and total_repayment 782,384
    # accept a fabricated loan of "Rs 8,00,000". Rounding by a writer is covered by
    # the 1% relative tolerance instead.

    for key, value in _walk(payload):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        add(value)
        k = key.lower()
        if "rate" in k or "percent" in k or k.endswith("_pct"):
            add(value / 100.0)               # 8%   -> 0.08
            add(value * 100.0)               # 0.08 -> 8
        if "tenure" in k or "month" in k:
            add(value / 12.0)                # 48 months -> 4 years
        if "year" in k:
            add(value * 12.0)
        if "score" in k or "suitability" in k:
            add(value * 100.0)               # 0.86 -> 86
    return accepted


def _walk(obj, prefix: str = ""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk(item, prefix)
    else:
        yield prefix, obj


def _matches(value: float, accepted: set[float]) -> bool:
    for a in accepted:
        tolerance = abs(a) * RELATIVE_TOLERANCE
        # The +/-1 rupee allowance is meaningful for rupee amounts and catastrophic
        # for small derived numbers: it made "5 years" match a 4-year tenure and
        # "9%" match an 8% rate.
        if abs(a) >= ABSOLUTE_TOLERANCE_MIN_MAGNITUDE:
            tolerance = max(tolerance, ABSOLUTE_TOLERANCE)
        if abs(value - a) <= tolerance:
            return True
    return False


# --------------------------------------------------------------------------
# extraction
# --------------------------------------------------------------------------
def _structural_spans(text: str) -> list[tuple[int, int]]:
    spans = []
    for pattern in STRUCTURAL_PATTERNS:
        spans.extend(m.span() for m in pattern.finditer(text))
    return spans


def _in_span(pos: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= pos < end for start, end in spans)


def _has_cue(text: str, start: int, end: int, window: int = 28) -> bool:
    left = text[max(0, start - window):start].lower()
    right = text[end:end + window].lower()
    words = set(re.findall(r"[a-z]+", left + " " + right))
    return bool(words & CUE_WORDS)


def _interpretations(raw_number: str, unit: str | None, currency: str | None) -> list[float]:
    """Every reading of this token. Matching any one of them grounds it."""
    base = float(raw_number.replace(",", ""))
    unit = (unit or "").lower().rstrip(".")
    out: list[float] = []

    if unit in ("%", "percent"):
        out += [base, base / 100.0]
    elif unit in _MULTIPLIERS:
        # A lakh/crore/k suffix is UNAMBIGUOUS: "8 lakh" is 800000, never 8.
        # Keeping the bare base as a fallback let a fabricated "8 lakh" match the
        # 8% interest rate in the payload.
        out += [base * _MULTIPLIERS[unit]]
    elif unit in ("month", "months"):
        out += [base, base / 12.0]
    elif unit in ("year", "years", "yr", "yrs"):
        out += [base * 12.0, base]           # 4 years -> 48 months, or 4
    else:
        out.append(base)
        if currency:
            out.append(base)
    return out


def verify_numeric_grounding(response_text: str, payload: dict) -> GuardResult:
    accepted = build_accepted_set(payload)
    spans = _structural_spans(response_text)
    findings: list[Finding] = []

    for m in _NUMBER.finditer(response_text):
        start, end = m.span()
        number_start = m.start("number")

        # inside a word (e.g. "P1", "HOME-A2") -> not a figure
        before = response_text[max(0, number_start - 1):number_start]
        if before.isalpha():
            continue
        if _in_span(number_start, spans):
            continue

        currency = m.group("currency")
        unit = m.group("unit")
        raw = m.group("number")
        try:
            base = float(raw.replace(",", ""))
        except ValueError:
            findings.append(Finding(m.group(0).strip(), Outcome.UNVERIFIED, [], "unparseable"))
            continue

        explicit = bool(currency) or bool(unit)
        cued = _has_cue(response_text, start, end)
        financial = explicit or cued or base >= MAGNITUDE_FLOOR
        if not financial:
            continue                                    # structural small integer

        readings = _interpretations(raw, unit, currency)
        if any(_matches(v, accepted) for v in readings):
            findings.append(Finding(m.group(0).strip(), Outcome.GROUNDED, readings))
            continue

        # No match. Is the parse confident enough to call it invented?
        # Confident enough to call it invented? An explicit unit or currency always
        # is. A cued number is, when it is either large or a decimal — decimals are
        # almost never structural. A bare small cued integer is NOT: that is exactly
        # where false positives live, so it degrades to UNVERIFIED instead.
        confident = (
            explicit
            or base >= MAGNITUDE_FLOOR
            or (cued and (base >= SMALL_CUED_FLOOR or "." in raw))
        )
        if confident:
            findings.append(Finding(m.group(0).strip(), Outcome.UNGROUNDED, readings, "no payload match"))
        else:
            findings.append(
                Finding(m.group(0).strip(), Outcome.UNVERIFIED, readings, "ambiguous, low confidence")
            )

    if any(f.outcome is Outcome.UNGROUNDED for f in findings):
        return GuardResult(Outcome.UNGROUNDED, findings)
    if any(f.outcome is Outcome.UNVERIFIED for f in findings):
        return GuardResult(Outcome.UNVERIFIED, findings)
    return GuardResult(Outcome.GROUNDED, findings)


# --------------------------------------------------------------------------
# entity grounding
# --------------------------------------------------------------------------
def verify_entity_grounding(
    response_text: str, payload_entities: list[str], known_entities: list[str]
) -> GuardResult:
    """
    A name from the catalogue vocabulary that is NOT in this payload is invented.

    Checking against a known vocabulary rather than guessing at capitalised phrases
    keeps this precise: unknown capitalised text is never asserted to be a product.
    """
    findings: list[Finding] = []
    allowed = {e.lower() for e in payload_entities}
    lowered = response_text.lower()
    for entity in known_entities:
        if entity.lower() in allowed:
            continue
        if re.search(rf"\b{re.escape(entity.lower())}\b", lowered):
            findings.append(Finding(entity, Outcome.UNGROUNDED, [], "entity not in payload"))
    outcome = Outcome.UNGROUNDED if findings else Outcome.GROUNDED
    return GuardResult(outcome, findings)
