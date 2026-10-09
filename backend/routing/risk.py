"""
Weather risk classification for a single checkpoint, exactly as specified in
the assessment PDF.

Thresholds:

    Condition  Low          Moderate   High       Severe     No Travel
    Wind       <25 mph      25–34      35–44      45–54      ≥55 mph
    Rain       <0.10 in/hr  0.10–0.25  0.25–0.50  0.50–1.00  >1.00
    Snow       <0.5 in/hr   0.5–1.0    1.0–2.0    2.0–3.0    >3.0

Load rules (wind combined with load weight):

    ≥55 mph                    → No Travel for any load
    45–54 mph and >30,000 lb   → No Travel
    35–44 mph and >40,000 lb   → Severe

Boundary convention: a value on a shared band boundary takes the higher band
(0.25 in/hr of rain is High). Where the PDF gives an explicit operator it is
followed literally: wind ≥55 is No Travel; rain >1.00 and snow >3.0 are
No Travel, so exactly 1.00 in/hr of rain and 3.0 in/hr of snow are Severe.

The checkpoint's overall level is the worst of the three conditions after the
load rules have been applied to wind.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import IntEnum


class Level(IntEnum):
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self) -> str:
        return _LABELS[self]

    @property
    def key(self) -> str:
        return _KEYS[self]


_LABELS = {
    Level.LOW: "Low",
    Level.MODERATE: "Moderate",
    Level.HIGH: "High",
    Level.SEVERE: "Severe",
    Level.NO_TRAVEL: "No Travel",
}
_KEYS = {
    Level.LOW: "low",
    Level.MODERATE: "moderate",
    Level.HIGH: "high",
    Level.SEVERE: "severe",
    Level.NO_TRAVEL: "no_travel",
}

# Lower bounds (inclusive) of each band above Low, in ascending order.
WIND_BANDS_MPH: tuple[tuple[float, Level], ...] = (
    (25, Level.MODERATE),
    (35, Level.HIGH),
    (45, Level.SEVERE),
    (55, Level.NO_TRAVEL),
)
RAIN_BANDS_IN_HR: tuple[tuple[float, Level], ...] = (
    (0.10, Level.MODERATE),
    (0.25, Level.HIGH),
    (0.50, Level.SEVERE),
)
RAIN_NO_TRAVEL_ABOVE_IN_HR = 1.00  # strictly greater than
SNOW_BANDS_IN_HR: tuple[tuple[float, Level], ...] = (
    (0.5, Level.MODERATE),
    (1.0, Level.HIGH),
    (2.0, Level.SEVERE),
)
SNOW_NO_TRAVEL_ABOVE_IN_HR = 3.0  # strictly greater than

# (wind lower bound inclusive, wind upper bound exclusive, load threshold lb, resulting level)
LOAD_RULES: tuple[tuple[float, float, int, Level], ...] = (
    (45, 55, 30_000, Level.NO_TRAVEL),
    (35, 45, 40_000, Level.SEVERE),
)


@dataclass(frozen=True)
class WeatherSample:
    """Forecast values at one checkpoint, in the PDF's units."""

    wind_mph: float
    rain_in_hr: float
    snow_in_hr: float
    gust_mph: float | None = None  # informational only; not part of the rules


@dataclass(frozen=True)
class RiskAssessment:
    level: Level  # overall, after load rules
    wind_level: Level  # table value for wind alone, before load rules
    rain_level: Level
    snow_level: Level
    load_rule: str | None  # description of the load rule that escalated wind, if any
    reason: str  # human-readable explanation shown in the UI


def _require_finite_non_negative(value: float, name: str) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"{name} must be a number, got {value!r}")
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite non-negative number, got {value!r}")


def _band(value: float, bands: tuple[tuple[float, Level], ...]) -> Level:
    level = Level.LOW
    for lower_bound, band_level in bands:
        if value >= lower_bound:
            level = band_level
    return level


def classify_wind(mph: float) -> Level:
    _require_finite_non_negative(mph, "wind_mph")
    return _band(mph, WIND_BANDS_MPH)


def classify_rain(in_hr: float) -> Level:
    _require_finite_non_negative(in_hr, "rain_in_hr")
    if in_hr > RAIN_NO_TRAVEL_ABOVE_IN_HR:
        return Level.NO_TRAVEL
    return _band(in_hr, RAIN_BANDS_IN_HR)


def classify_snow(in_hr: float) -> Level:
    _require_finite_non_negative(in_hr, "snow_in_hr")
    if in_hr > SNOW_NO_TRAVEL_ABOVE_IN_HR:
        return Level.NO_TRAVEL
    return _band(in_hr, SNOW_BANDS_IN_HR)


def apply_load_rules(wind_mph: float, load_lb: float) -> tuple[Level, str | None]:
    """
    Wind level after the load rules. Returns the level and, when a load rule
    changed it, a short description of that rule.
    """
    _require_finite_non_negative(load_lb, "load_lb")
    level = classify_wind(wind_mph)
    for wind_lo, wind_hi, load_threshold, target in LOAD_RULES:
        if wind_lo <= wind_mph < wind_hi and load_lb > load_threshold:
            rule = (
                f"load {load_lb:,.0f} lb exceeds {load_threshold:,} lb "
                f"in {wind_lo:.0f}-{wind_hi - 1:.0f} mph wind: {target.label}"
            )
            return max(level, target), rule
    return level, None


def assess(sample: WeatherSample, load_lb: float) -> RiskAssessment:
    """Classify one checkpoint. Raises ValueError on negative or non-finite input."""
    wind_level = classify_wind(sample.wind_mph)
    rain_level = classify_rain(sample.rain_in_hr)
    snow_level = classify_snow(sample.snow_in_hr)
    wind_after_load, load_rule = apply_load_rules(sample.wind_mph, load_lb)
    level = max(wind_after_load, rain_level, snow_level)
    reason = _reason(sample, level, wind_level, rain_level, snow_level, wind_after_load, load_rule)
    return RiskAssessment(
        level=level,
        wind_level=wind_level,
        rain_level=rain_level,
        snow_level=snow_level,
        load_rule=load_rule,
        reason=reason,
    )


def _reason(
    sample: WeatherSample,
    level: Level,
    wind_level: Level,
    rain_level: Level,
    snow_level: Level,
    wind_after_load: Level,
    load_rule: str | None,
) -> str:
    wind = f"Wind {sample.wind_mph:.0f} mph"
    rain = f"rain {sample.rain_in_hr:.2f} in/hr"
    snow = f"snow {sample.snow_in_hr:.1f} in/hr"
    if level is Level.LOW:
        return f"{wind}, {rain}, {snow}: Low"

    # Name only the conditions that drive the overall level.
    parts: list[str] = []
    if wind_after_load == level:
        text = f"{wind}: {wind_level.label}"
        if load_rule:
            text += f"; {load_rule}"
        parts.append(text)
    if rain_level == level:
        parts.append(f"{rain.capitalize()}: {rain_level.label}")
    if snow_level == level:
        parts.append(f"{snow.capitalize()}: {snow_level.label}")
    return " | ".join(parts)
