"""
Risk rules from the assessment PDF.

    Condition  Low          Moderate   High       Severe     No Travel
    Wind       <25 mph      25–34      35–44      45–54      ≥55 mph
    Rain       <0.10 in/hr  0.10–0.25  0.25–0.50  0.50–1.00  >1.00
    Snow       <0.5 in/hr   0.5–1.0    1.0–2.0    2.0–3.0    >3.0

Load rules:
    ≥55 mph                      → No Travel for any load
    45–54 mph and >30,000 lb     → No Travel
    35–44 mph and >40,000 lb     → Severe

Boundary convention (documented in the README): a value that sits on a shared
boundary of two bands takes the higher band (0.25 in/hr of rain is High), except
where the PDF states the operator explicitly (rain >1.00 and snow >3.0 are
No Travel, so exactly 1.00 / 3.0 are Severe; wind ≥55 is No Travel).
"""

import math

import pytest

from routing.risk import (
    Level,
    WeatherSample,
    apply_load_rules,
    assess,
    classify_rain,
    classify_snow,
    classify_wind,
)

# --- Level enum -------------------------------------------------------------


def test_levels_are_ordered_low_to_no_travel():
    assert Level.LOW < Level.MODERATE < Level.HIGH < Level.SEVERE < Level.NO_TRAVEL
    assert [lvl.value for lvl in Level] == [0, 1, 2, 3, 4]


def test_level_labels_and_keys():
    assert Level.NO_TRAVEL.label == "No Travel"
    assert Level.NO_TRAVEL.key == "no_travel"
    assert Level.MODERATE.label == "Moderate"
    assert Level.MODERATE.key == "moderate"


# --- Wind -------------------------------------------------------------------


@pytest.mark.parametrize(
    "mph, expected",
    [
        (0, Level.LOW),
        (24.9, Level.LOW),
        (25, Level.MODERATE),
        (34.9, Level.MODERATE),
        (35, Level.HIGH),
        (44.9, Level.HIGH),
        (45, Level.SEVERE),
        (54.9, Level.SEVERE),
        (55, Level.NO_TRAVEL),
        (90, Level.NO_TRAVEL),
    ],
)
def test_classify_wind_boundaries(mph, expected):
    assert classify_wind(mph) is expected


# --- Rain -------------------------------------------------------------------


@pytest.mark.parametrize(
    "in_hr, expected",
    [
        (0, Level.LOW),
        (0.099, Level.LOW),
        (0.10, Level.MODERATE),
        (0.249, Level.MODERATE),
        (0.25, Level.HIGH),
        (0.499, Level.HIGH),
        (0.50, Level.SEVERE),
        (1.00, Level.SEVERE),
        (1.001, Level.NO_TRAVEL),
        (3.0, Level.NO_TRAVEL),
    ],
)
def test_classify_rain_boundaries(in_hr, expected):
    assert classify_rain(in_hr) is expected


# --- Snow -------------------------------------------------------------------


@pytest.mark.parametrize(
    "in_hr, expected",
    [
        (0, Level.LOW),
        (0.49, Level.LOW),
        (0.5, Level.MODERATE),
        (0.99, Level.MODERATE),
        (1.0, Level.HIGH),
        (1.99, Level.HIGH),
        (2.0, Level.SEVERE),
        (3.0, Level.SEVERE),
        (3.01, Level.NO_TRAVEL),
    ],
)
def test_classify_snow_boundaries(in_hr, expected):
    assert classify_snow(in_hr) is expected


# --- Load rules -------------------------------------------------------------


@pytest.mark.parametrize(
    "mph, load_lb, expected_level, rule_applied",
    [
        # ≥55 mph: No Travel regardless of load (already the table value).
        (56, 1_000, Level.NO_TRAVEL, False),
        # 45–54 mph: No Travel only when load exceeds 30,000 lb.
        (50, 30_000, Level.SEVERE, False),
        (50, 30_001, Level.NO_TRAVEL, True),
        (45, 30_001, Level.NO_TRAVEL, True),
        (54.9, 30_001, Level.NO_TRAVEL, True),
        # 35–44 mph: Severe only when load exceeds 40,000 lb.
        (40, 40_000, Level.HIGH, False),
        (40, 40_001, Level.SEVERE, True),
        (35, 40_001, Level.SEVERE, True),
        (44.9, 40_001, Level.SEVERE, True),
        (40, 50_000, Level.SEVERE, True),  # escalates to Severe, never beyond
        # Below 35 mph the load never matters.
        (30, 80_000, Level.MODERATE, False),
        (20, 80_000, Level.LOW, False),
    ],
)
def test_apply_load_rules(mph, load_lb, expected_level, rule_applied):
    level, rule = apply_load_rules(mph, load_lb)
    assert level is expected_level
    assert (rule is not None) == rule_applied


def test_load_rule_text_names_the_threshold():
    _, rule = apply_load_rules(50, 35_000)
    assert "30,000" in rule
    _, rule = apply_load_rules(40, 45_000)
    assert "40,000" in rule


# --- Checkpoint assessment --------------------------------------------------


def test_assess_takes_the_worst_component():
    result = assess(WeatherSample(wind_mph=10, rain_in_hr=0.6, snow_in_hr=0), load_lb=10_000)
    assert result.level is Level.SEVERE
    assert result.wind_level is Level.LOW
    assert result.rain_level is Level.SEVERE
    assert result.snow_level is Level.LOW
    assert result.load_rule is None


def test_assess_applies_load_rule_to_overall_level():
    result = assess(WeatherSample(wind_mph=50, rain_in_hr=0, snow_in_hr=0), load_lb=35_000)
    assert result.wind_level is Level.SEVERE  # table value, before load rule
    assert result.level is Level.NO_TRAVEL  # after load rule
    assert result.load_rule is not None


def test_assess_without_load_escalation():
    result = assess(WeatherSample(wind_mph=50, rain_in_hr=0, snow_in_hr=0), load_lb=20_000)
    assert result.level is Level.SEVERE
    assert result.load_rule is None


def test_assess_snow_and_wind_combined_keeps_the_worse():
    result = assess(WeatherSample(wind_mph=30, rain_in_hr=0, snow_in_hr=2.5), load_lb=10_000)
    assert result.level is Level.SEVERE
    assert result.snow_level is Level.SEVERE
    assert result.wind_level is Level.MODERATE


def test_reason_text_for_calm_conditions():
    result = assess(WeatherSample(wind_mph=8, rain_in_hr=0, snow_in_hr=0), load_lb=10_000)
    assert "Low" in result.reason


def test_reason_text_names_dominant_factor():
    result = assess(WeatherSample(wind_mph=10, rain_in_hr=0.6, snow_in_hr=0), load_lb=10_000)
    assert "Rain" in result.reason and "Severe" in result.reason


def test_reason_text_mentions_load_rule():
    result = assess(WeatherSample(wind_mph=50, rain_in_hr=0, snow_in_hr=0), load_lb=35_000)
    assert "30,000" in result.reason and "No Travel" in result.reason


@pytest.mark.parametrize(
    "sample, load_lb",
    [
        (WeatherSample(wind_mph=-1, rain_in_hr=0, snow_in_hr=0), 1000),
        (WeatherSample(wind_mph=0, rain_in_hr=-0.1, snow_in_hr=0), 1000),
        (WeatherSample(wind_mph=0, rain_in_hr=0, snow_in_hr=-0.1), 1000),
        (WeatherSample(wind_mph=math.nan, rain_in_hr=0, snow_in_hr=0), 1000),
        (WeatherSample(wind_mph=0, rain_in_hr=0, snow_in_hr=0), -5),
    ],
)
def test_assess_rejects_invalid_input(sample, load_lb):
    with pytest.raises(ValueError):
        assess(sample, load_lb)
