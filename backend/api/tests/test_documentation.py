"""
Documentation contract: README.md and .env.example must agree with the code.

These run with the backend suite so that changing an error code, a risk threshold, a request field
or an environment variable fails the build until the documentation follows.
"""

import json
import re
import subprocess
from datetime import timedelta
from pathlib import Path

import pytest
from django.utils import timezone

from api import planner, serializers
from providers import errors
from routing import risk

REPO = Path(__file__).resolve().parents[3]


def read(relative: str) -> str:
    path = REPO / relative
    assert path.is_file(), f"{relative} is missing"
    return path.read_text(encoding="utf-8")


def section(markdown: str, heading: str) -> str:
    """Body of the first level-2 section whose heading contains `heading`."""
    match = re.search(rf"^## [^\n]*{re.escape(heading)}[^\n]*\n(.*?)(?=^## |\Z)", markdown, re.M | re.S)
    assert match, f"no '## {heading}' section"
    return match.group(1)


def fenced_blocks(markdown: str) -> list[str]:
    return re.findall(r"```[a-z]*\n(.*?)```", markdown, re.S)


def numbers(cell: str) -> list[float]:
    return [float(n) for n in re.findall(r"\d+(?:\.\d+)?", cell)]


def all_subclasses(cls: type) -> set[type]:
    found = set()
    for sub in cls.__subclasses__():
        found.add(sub)
        found |= all_subclasses(sub)
    return found


# --- README: API contract -------------------------------------------------------------------------


def test_readme_lists_every_api_error_code_with_its_http_status():
    raised = all_subclasses(errors.ProviderError) | all_subclasses(planner.PlanningError) | {planner.PlanningError}
    expected = {cls.code: cls.http_status for cls in raised}
    expected["validation_error"] = 400

    documented = {}
    for status, cell in re.findall(r"^\|\s*(\d{3})\s*\|(.+?)\|\s*$", section(read("README.md"), "API"), re.M):
        for code in re.findall(r"`([a-z_]+)`", cell):
            documented[code] = int(status)

    assert documented == expected


def test_readme_request_example_matches_the_serializer():
    api = section(read("README.md"), "API")
    example = json.loads(re.search(r"Request body:\s*```json\n(.*?)```", api, re.S).group(1))

    assert set(example) == set(serializers.PlanRequestSerializer().fields)
    assert example["sample_interval_miles"] in serializers.SAMPLE_INTERVALS_MILES

    live = {**example, "departure_time": (timezone.now() + timedelta(days=1)).isoformat(timespec="seconds")}
    serializer = serializers.PlanRequestSerializer(data=live)
    assert serializer.is_valid(), serializer.errors

    intervals = ", ".join(str(i) for i in serializers.SAMPLE_INTERVALS_MILES[:-1])
    assert f"{intervals} or {serializers.SAMPLE_INTERVALS_MILES[-1]}" in api
    assert f"{serializers.MAX_DEPARTURE_DAYS_AHEAD} days ahead" in api
    assert f"{serializers.MAX_DEPARTURE_HOURS_PAST} hour ago" in api
    assert f"{serializers.MAX_LOAD_LB:,} lb" in api


# --- README: risk rules -----------------------------------------------------------------------------


def threshold_row(label: str) -> list[str]:
    readme = read("README.md")
    match = re.search(rf"^\| {re.escape(label)} \|(.+)\|\s*$", readme, re.M)
    assert match, f"no threshold row for {label}"
    return [cell.strip() for cell in match.group(1).split("|")]


def test_readme_wind_thresholds_match_the_risk_rules():
    low, *bands = threshold_row("Wind (mph)")
    starts = [band for band, _ in risk.WIND_BANDS_MPH]

    assert low.startswith("<") and numbers(low) == [starts[0]]
    assert [numbers(cell)[0] for cell in bands] == starts
    assert bands[-1].startswith("≥"), "55 mph itself is No Travel"


@pytest.mark.parametrize(
    ("label", "band_table", "no_travel_above"),
    [
        ("Rain (in/hr)", risk.RAIN_BANDS_IN_HR, risk.RAIN_NO_TRAVEL_ABOVE_IN_HR),
        ("Snow (in/hr)", risk.SNOW_BANDS_IN_HR, risk.SNOW_NO_TRAVEL_ABOVE_IN_HR),
    ],
)
def test_readme_precipitation_thresholds_match_the_risk_rules(label, band_table, no_travel_above):
    low, *bands, no_travel = threshold_row(label)
    starts = [band for band, _ in band_table]

    assert low.startswith("<") and numbers(low) == [starts[0]]
    assert [numbers(cell)[0] for cell in bands] == starts
    assert numbers(bands[-1])[-1] == no_travel_above, "the Severe band ends at the No Travel limit"
    assert no_travel.startswith(">") and numbers(no_travel) == [no_travel_above], "only values above it are No Travel"


def test_readme_states_the_load_rules_as_coded():
    readme = read("README.md")
    for low, high, load_lb, level in risk.LOAD_RULES:
        assert f"wind of {low:g}–{high - 1:g} mph with a load over {load_lb:,} lb is {level.label}" in readme
    assert f"Wind of {risk.WIND_BANDS_MPH[-1][0]:g} mph or more is No Travel for any load" in readme


# --- README: architecture, assumptions, layout ---------------------------------------------------


def test_readme_has_an_architecture_diagram_naming_every_tier_and_provider():
    diagram = "\n".join(fenced_blocks(section(read("README.md"), "Architecture")))
    for name in (
        "Browser",
        "MapLibre",
        "nginx",
        "gunicorn",
        "Django",
        "api/",
        "routing/",
        "providers/",
        "TomTom",
        "Open-Meteo",
        "OpenFreeMap",
    ):
        assert name in diagram, f"architecture diagram does not show {name}"


def test_readme_states_every_assumption_from_the_plan():
    plan_ids = re.findall(r"^\| (A\d+) \|", read("docs/PLAN.md"), re.M)
    readme_ids = re.findall(r"^\| (A\d+) \|", section(read("README.md"), "Assumptions"), re.M)

    assert plan_ids, "the plan's assumptions table was not found"
    assert readme_ids == plan_ids


def test_readme_layout_names_every_tracked_top_level_directory():
    try:
        tracked = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git is not available")
    top_level = {path.split("/", 1)[0] for path in tracked.split() if "/" in path}
    layout = "\n".join(fenced_blocks(section(read("README.md"), "Repository layout")))

    for directory in sorted(top_level):
        assert re.search(rf"^{directory}/", layout, re.M), f"{directory}/ is missing from the layout"


def test_readme_has_a_limitations_section():
    assert section(read("README.md"), "Limitations").strip()


# --- Environment variables -------------------------------------------------------------------------


def settings_env_vars() -> set[str]:
    found = set()
    for path in (REPO / "backend" / "config" / "settings").glob("*.py"):
        found |= set(re.findall(r'os\.environ\.get\("([A-Z_]+)"', path.read_text(encoding="utf-8")))
    return found


def test_env_example_lists_every_variable_the_settings_read():
    example = read(".env.example")
    for var in sorted(settings_env_vars()):
        assert re.search(rf"^#?\s*{var}=", example, re.M), f"{var} is not in .env.example"


def test_every_env_example_variable_is_used_somewhere():
    consumers = settings_env_vars()
    for relative in ("docker-compose.yml", "deploy/deploy.sh", "deploy/backend.Dockerfile"):
        consumers |= set(re.findall(r"\b([A-Z][A-Z_]+)\b", read(relative)))
    for var in re.findall(r"^#?\s*([A-Z_]+)=", read(".env.example"), re.M):
        assert var in consumers, f"{var} in .env.example is read by nothing"


def test_readme_deployment_names_every_variable_the_deploy_script_requires():
    required = re.search(r"for key in ([A-Z_ ]+); do", read("deploy/deploy.sh")).group(1).split()
    deployment = section(read("README.md"), "Deployment")
    for var in required:
        assert var in deployment, f"{var} is required by deploy.sh but not mentioned under Deployment"
