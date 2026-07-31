"""Lightweight metric fact extraction from page text (no domain hardcoding).

Captures:
- relative change: "기존대비 8% 증가", "납기준수율 +24%"
- absolute quantities: "371명", "1,931억원", "가동률 95%"
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from backend.domain.enums import MetricDirection, VerificationStatus


@dataclass
class ExtractedMetric:
    name: str
    change_value: float | None
    change_unit: str | None
    direction: MetricDirection | None
    definition: str | None
    measurement_method: str | None
    raw_span: str
    confidence: float
    result_value: float | None = None
    baseline_value: float | None = None


# "기존대비 8% 증가" / "기존 대비 +24% 향상"
_BASELINE_CHANGE_RE = re.compile(
    r"기존\s*대비\s*(?P<sign>[+\-±]?)\s*(?P<value>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>%|percent|퍼센트)\s*"
    r"(?P<dir>증가|감소|향상|개선|상승|하락)?",
    re.IGNORECASE,
)

# "생산량 +8%" / "클레임 -33%" — name immediately before signed %
_INLINE_CHANGE_RE = re.compile(
    r"(?P<name>[가-힣A-Za-z][가-힣A-Za-z/·]{1,24})"
    r"(?:\s+|)"
    r"(?P<sign>[+\-±])\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>%)\s*"
    r"(?P<dir>증가|감소|향상|개선|상승|하락)?",
    re.IGNORECASE,
)

# Absolute quantities: number + measure unit (linguistic units, not domain terms)
_MEASURE_UNITS = (
    "%|퍼센트|명|원|천원|만원|억원|조원|달러|건|개|회|대|톤|kg|t|ton|L|ml|mm|cm|m|km|GB|TB"
)
_ABS_VALUE_RE = re.compile(
    rf"(?<![0-9.,])(?P<value>\d{{1,3}}(?:,\d{{3}})*(?:\.\d+)?)\s*"
    rf"(?P<unit>{_MEASURE_UNITS})(?![가-힣A-Za-z%])",
    re.IGNORECASE,
)

# Numbered section titles: "1. 시간당생산량"
_NUMBERED_TITLE_RE = re.compile(
    r"(?:^|\n)\s*\d+[\.\)]\s*([가-힣A-Za-z][가-힣A-Za-z0-9/· ]{0,36})\s*(?=\n|$)",
)

_LABEL_LINE_RE = re.compile(
    r"(?:^|\n)\s*([가-힣A-Za-z][가-힣A-Za-z0-9/· ]{1,28})\s*(?=\n|$)",
)

_METHOD_RE = re.compile(
    r"(?:측정\s*방법|산정\s*방법|계산식)\s*[:：]?\s*([^\n]{2,120})",
    re.IGNORECASE,
)

_DIR_AFTER_PCT_RE = re.compile(r"^\s*(증가|감소|향상|개선|상승|하락)")

_NOISE_NAMES = {
    "효과",
    "기존대비",
    "기존",
    "대비",
    "contents",
    "정의",
    "측정방법",
    "산정방법",
    "계산식",
    "지표",
}

_NOISE_IN_NAME = ("정의", "측정방법", "산정방법", "효과", "기존대비", "기존 대비")

# Calendar / duration suffixes that are rarely KPI magnitudes by themselves
_WEAK_ABS_UNITS = {"년", "월", "일", "시", "분", "초"}


def extract_metrics_from_text(text: str) -> list[ExtractedMetric]:
    results: list[ExtractedMetric] = []
    seen: set[tuple[str, float | None, str]] = set()
    occupied: list[tuple[int, int]] = []

    for m in _BASELINE_CHANGE_RE.finditer(text):
        name = _name_before(text, m.start()) or "지표"
        if _append_change(results, seen, name=name, match=m, text=text, conf_base=0.88):
            occupied.append((m.start(), m.end()))

    for m in _INLINE_CHANGE_RE.finditer(text):
        name = m.group("name").strip(" :-–—|·")
        if not _ok_name(name):
            continue
        if _append_change(results, seen, name=name, match=m, text=text, conf_base=0.8):
            occupied.append((m.start(), m.end()))

    for m in _ABS_VALUE_RE.finditer(text):
        if _overlaps(m.start(), m.end(), occupied):
            continue
        if not _ok_absolute_match(text, m):
            continue
        name = _name_before(text, m.start())
        if not name or not _ok_name(name):
            continue
        value = _parse_number(m.group("value"))
        unit = m.group("unit").strip()
        if unit.lower().startswith("percent") or unit == "퍼센트":
            unit = "%"
        key = (_norm(name), value, "abs")
        if key in seen:
            continue
        seen.add(key)
        results.append(
            ExtractedMetric(
                name=_clean_name(name),
                change_value=None,
                change_unit=unit,
                direction=None,
                definition=None,
                measurement_method=None,
                raw_span=m.group(0).strip(),
                confidence=0.84,
                result_value=value,
            )
        )

    return results


def _append_change(
    results: list[ExtractedMetric],
    seen: set[tuple[str, float | None, str]],
    *,
    name: str,
    match: re.Match,
    text: str,
    conf_base: float,
) -> bool:
    name = _clean_name(name)
    if not _ok_name(name):
        return False
    value = float(match.group("value"))
    sign = match.group("sign") or ""
    unit = match.group("unit") or "%"
    if unit.lower().startswith("percent") or unit == "퍼센트":
        unit = "%"
    dir_word = (match.group("dir") or "").strip()
    direction = _direction(dir_word, sign)

    key = (_norm(name), value, "chg")
    if key in seen:
        return False
    seen.add(key)

    start = max(0, match.start() - 220)
    end = min(len(text), match.end() + 80)
    window = text[start:end]
    method_m = _METHOD_RE.search(window)
    method = method_m.group(1).strip() if method_m else None
    def_m = re.search(r"(?:^|\n)\s*정의\s*\n\s*([^\n]{2,80})", window)
    if not def_m:
        def_m = re.search(r"정의\s*[:：]?\s*([^\n]{2,80})", window)
    definition = def_m.group(1).strip() if def_m else None
    if definition and any(n in definition for n in _NOISE_IN_NAME):
        definition = definition.split()[0] if definition.split() else definition

    conf = conf_base
    if direction and unit == "%":
        conf = min(0.95, conf + 0.05)
    if method:
        conf = min(0.97, conf + 0.03)

    results.append(
        ExtractedMetric(
            name=name,
            change_value=value,
            change_unit=unit,
            direction=direction,
            definition=definition,
            measurement_method=method,
            raw_span=match.group(0).strip(),
            confidence=conf,
        )
    )
    return True


def _ok_absolute_match(text: str, match: re.Match) -> bool:
    unit = match.group("unit").strip()
    value = _parse_number(match.group("value"))
    line = _line_at(text, match.start())

    # Formula / expression lines — not standalone facts
    if "=" in line or line.count("*") >= 2 or line.count("(") >= 2:
        return False

    # Change phrases already handled elsewhere
    if unit == "%" and _DIR_AFTER_PCT_RE.match(text[match.end() : match.end() + 12]):
        return False
    if "기존" in line and "대비" in line:
        return False

    # Calendar-ish absolute values
    if unit in _WEAK_ABS_UNITS:
        if unit == "년" and 1900 <= value <= 2100:
            return False
        if unit == "월" and 1 <= value <= 12:
            return False
        if unit == "일" and value <= 366:
            return False
        if unit in {"시", "분", "초"} and value < 100:
            return False

    # Tiny bare percents without a nearby label are usually noise
    if unit == "%" and value == 100 and ("*" in line or "(" in line):
        return False

    return True


def _direction(dir_word: str, sign: str) -> MetricDirection | None:
    if dir_word in {"증가", "향상", "개선", "상승"} or sign == "+":
        return MetricDirection.INCREASE
    if dir_word in {"감소", "하락"} or sign == "-":
        return MetricDirection.DECREASE
    return None


def _name_before(text: str, pos: int) -> str | None:
    """Prefer nearest numbered title; else a short non-numeric label above."""
    window = text[max(0, pos - 280) : pos]

    numbered = _NUMBERED_TITLE_RE.findall(window)
    for title in reversed(numbered):
        name = _clean_name(title)
        if _ok_name(name) and not _ABS_VALUE_RE.fullmatch(name.strip()):
            return name

    labels = _LABEL_LINE_RE.findall(window)
    for title in reversed(labels):
        name = _clean_name(title)  # strips leading § from STRUCTURE echoes
        if not _ok_name(name):
            continue
        if name in {"효과", "측정방법", "정의"}:
            continue
        if "=" in name or "(" in name or "|" in name:
            continue
        if _ABS_VALUE_RE.search(name):
            continue
        return name
    return None


def _clean_name(name: str) -> str:
    name = re.sub(r"[\r\n\t]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip(" :-–—|·§")
    name = re.sub(r"^\d+[\.\)]\s*", "", name)
    # Only cut at whitespace-delimited noise tokens (not 구축효과 → 구축)
    parts = name.split()
    for noise in _NOISE_IN_NAME:
        if noise in parts:
            idx = parts.index(noise)
            if idx == 0:
                return ""
            name = " ".join(parts[:idx])
            break
    return name.strip()


def _ok_name(name: str) -> bool:
    if not name or len(name) < 2 or len(name) > 40:
        return False
    if "\n" in name:
        return False
    if _norm(name) in _NOISE_NAMES:
        return False
    if any(n in name for n in _NOISE_IN_NAME):
        return False
    if name.isdigit():
        return False
    if name.count(" ") > 4:
        return False
    if "=" in name:
        return False
    return True


def _parse_number(raw: str) -> float:
    return float(raw.replace(",", ""))


def _line_at(text: str, pos: int) -> str:
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    if end < 0:
        end = len(text)
    return text[start:end]


def _overlaps(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    for a, b in spans:
        if start < b and end > a:
            return True
    return False


def _norm(s: str) -> str:
    return "".join(s.lower().split())


def to_metric_row(
    metric: ExtractedMetric,
    *,
    source_id: str,
    page_number: int,
) -> dict:
    mid = f"MET-{uuid.uuid4().hex[:10].upper()}"
    status = VerificationStatus.VERIFIED.value
    if metric.confidence < 0.8:
        status = VerificationStatus.REQUIRES_VISUAL_CHECK.value
    elif metric.change_value is not None and not metric.measurement_method:
        status = VerificationStatus.REQUIRES_VISUAL_CHECK.value
    return {
        "metric_id": mid,
        "source_id": source_id,
        "page_number": page_number,
        "name": metric.name,
        "definition": metric.definition,
        "measurement_method": metric.measurement_method,
        "baseline_value": metric.baseline_value,
        "result_value": metric.result_value,
        "change_value": metric.change_value,
        "change_unit": metric.change_unit,
        "direction": metric.direction.value if metric.direction else None,
        "confidence": metric.confidence,
        "verification_status": status,
        "payload_json": None,
    }
