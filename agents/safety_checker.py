# Copyright (c) 2026. Safety Checker agent — NHTSA vehicle safety data.
# Extracted from the original single-agent main.py.

import os

from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient
from pydantic import Field
from typing_extensions import Annotated

# ── Service initialisation (MOCK_MODE toggle) ────────────────────────────────

_mock_mode = os.environ.get("MOCK_MODE", "false").lower() in ("true", "1", "yes")

if _mock_mode:
    from mock_service import MockService
    _svc = MockService()
else:
    from nhtsa_service import NHTSAService
    _svc = NHTSAService()

# ── Tools ────────────────────────────────────────────────────────────────────


@tool(approval_mode="never_require")
def decode_vin(
    vin: Annotated[str, Field(description="The 17-character Vehicle Identification Number (VIN)")],
) -> str:
    """Decode a VIN to get full vehicle specifications — make, model, year,
    engine, body type, safety features, and manufacturing details."""
    try:
        result = _svc.decode_vin(vin)
    except RuntimeError as e:
        return f"Error decoding VIN: {e}"

    if "error" in result:
        return result["error"]

    lines = [f"## VIN Decode: {result.get('vin', vin)}"]
    year = result.get("year", "")
    make = result.get("make", "")
    model = result.get("model", "")
    trim = result.get("trim", "")
    lines.append(f"**Vehicle:** {year} {make} {model} {trim}".strip())
    if result.get("body_class"):
        lines.append(f"**Body:** {result['body_class']}")
    if result.get("vehicle_type"):
        lines.append(f"**Type:** {result['vehicle_type']}")
    if result.get("doors"):
        lines.append(f"**Doors:** {result['doors']}")
    if result.get("drive_type"):
        lines.append(f"**Drive:** {result['drive_type']}")

    # Powertrain
    engine_parts = []
    if result.get("displacement_l"):
        engine_parts.append(f"{result['displacement_l']}L")
    if result.get("engine_cylinders"):
        engine_parts.append(f"{result['engine_cylinders']}-cyl")
    if result.get("engine_hp"):
        engine_parts.append(f"{result['engine_hp']} hp")
    if engine_parts:
        lines.append(f"**Engine:** {' / '.join(engine_parts)}")
    if result.get("fuel_type_primary"):
        lines.append(f"**Fuel:** {result['fuel_type_primary']}")
    if result.get("electrification"):
        lines.append(f"**Electrification:** {result['electrification']}")
    if result.get("transmission"):
        lines.append(f"**Transmission:** {result['transmission']}")

    # Manufacturing
    plant_parts = []
    if result.get("plant_city"):
        plant_parts.append(result["plant_city"])
    if result.get("plant_country"):
        plant_parts.append(result["plant_country"])
    if plant_parts:
        lines.append(f"**Assembled in:** {', '.join(plant_parts)}")
    if result.get("manufacturer"):
        lines.append(f"**Manufacturer:** {result['manufacturer']}")

    # Safety features
    safety = []
    for feat, label in [
        ("abs", "ABS"), ("esc", "ESC"), ("tpms", "TPMS"),
        ("forward_collision_warning", "Forward Collision Warning"),
        ("lane_departure_warning", "Lane Departure Warning"),
        ("adaptive_cruise_control", "Adaptive Cruise Control"),
        ("blind_spot_warning", "Blind Spot Warning"),
    ]:
        val = result.get(feat)
        if val and val.lower() not in ("", "not applicable"):
            safety.append(f"{label}: {val}")
    if safety:
        lines.append("")
        lines.append("**Safety Features:**")
        for s in safety:
            lines.append(f"- {s}")

    if result.get("error_text"):
        lines.append(f"\n⚠️ {result['error_text']}")

    return "\n".join(lines)


@tool(approval_mode="never_require")
def get_recalls(
    make: Annotated[str, Field(description="Vehicle make (e.g. Honda, Toyota, Ford)")],
    model: Annotated[str, Field(description="Vehicle model (e.g. Civic, Camry, F-150)")],
    year: Annotated[int, Field(description="Model year (e.g. 2021)")],
) -> str:
    """Check for open safety recalls on a specific vehicle.
    Recall repairs are always free at authorized dealers."""
    try:
        recalls = _svc.get_recalls(make, model, year)
    except RuntimeError as e:
        return f"Error checking recalls: {e}"

    if not recalls:
        return f"No recalls found for {year} {make} {model}. [OK]"

    lines = [f"## Recalls for {year} {make} {model} — {len(recalls)} found\n"]
    for i, r in enumerate(recalls, 1):
        lines.append(f"### Recall {i}: {r.get('nhtsa_campaign_number', 'N/A')}")
        lines.append(f"**Component:** {r.get('component', 'N/A')}")
        lines.append(f"**Date:** {r.get('report_date', 'N/A')}")
        lines.append(f"**Summary:** {r.get('summary', 'N/A')}")
        lines.append(f"**Consequence:** {r.get('consequence', 'N/A')}")
        lines.append(f"**Remedy:** {r.get('remedy', 'N/A')}")
        lines.append("")
    return "\n".join(lines)


@tool(approval_mode="never_require")
def get_complaints(
    make: Annotated[str, Field(description="Vehicle make (e.g. Honda, Toyota, Ford)")],
    model: Annotated[str, Field(description="Vehicle model (e.g. Civic, Camry, F-150)")],
    year: Annotated[int, Field(description="Model year (e.g. 2021)")],
) -> str:
    """Look up consumer complaints filed with NHTSA for a vehicle."""
    try:
        complaints = _svc.get_complaints(make, model, year)
    except RuntimeError as e:
        return f"Error fetching complaints: {e}"

    if not complaints:
        return f"No complaints filed for {year} {make} {model}. [OK]"

    total = len(complaints)
    shown = complaints[:10]
    lines = [f"## Complaints for {year} {make} {model} — {total} total\n"]

    crashes = sum(1 for c in complaints if c.get("crash"))
    fires = sum(1 for c in complaints if c.get("fire"))
    injuries = sum(c.get("injuries", 0) for c in complaints)
    if crashes or fires or injuries:
        lines.append(f"⚠️ **Incidents:** {crashes} crashes, {fires} fires, {injuries} injuries reported\n")

    for i, c in enumerate(shown, 1):
        lines.append(f"**{i}. {c.get('component', 'N/A')}** (filed {c.get('date_filed', 'N/A')})")
        lines.append(f"   {c.get('summary', 'N/A')}")
        lines.append("")

    if total > 10:
        lines.append(f"_(Showing 10 of {total} complaints)_")

    return "\n".join(lines)


@tool(approval_mode="never_require")
def get_safety_ratings(
    make: Annotated[str, Field(description="Vehicle make (e.g. Honda, Toyota, Ford)")],
    model: Annotated[str, Field(description="Vehicle model (e.g. Civic, Camry, F-150)")],
    year: Annotated[int, Field(description="Model year (e.g. 2021)")],
) -> str:
    """Get NCAP crash test safety ratings from NHTSA (1-5 stars)."""
    try:
        rating = _svc.get_safety_ratings(make, model, year)
    except RuntimeError as e:
        return f"Error fetching safety ratings: {e}"

    if not rating:
        return (
            f"No NCAP crash test ratings available for {year} {make} {model}. "
            "This vehicle may not have been tested by NHTSA."
        )

    def stars(val: str) -> str:
        try:
            n = int(val)
            return "*" * n + f" ({n}/5)"
        except (ValueError, TypeError):
            return val or "Not Rated"

    lines = [
        f"## Safety Ratings: {rating.get('vehicle_description', f'{year} {make} {model}')}\n",
        f"**Overall:** {stars(rating.get('overall_rating', ''))}",
        "",
        "**Frontal Crash:**",
        f"- Overall: {stars(rating.get('overall_front_crash', ''))}",
        f"- Driver: {stars(rating.get('front_crash_driver', ''))}",
        f"- Passenger: {stars(rating.get('front_crash_passenger', ''))}",
        "",
        "**Side Crash:**",
        f"- Overall: {stars(rating.get('overall_side_crash', ''))}",
        f"- Driver: {stars(rating.get('side_crash_driver', ''))}",
        f"- Passenger: {stars(rating.get('side_crash_passenger', ''))}",
        "",
        f"**Rollover Resistance:** {stars(rating.get('rollover_rating', ''))}",
    ]
    if rating.get("rollover_possibility_pct"):
        lines.append(f"- Rollover risk: {rating['rollover_possibility_pct']}")

    lines.append("")
    lines.append(
        f"**NHTSA Records:** {rating.get('complaints_count', 0)} complaints, "
        f"{rating.get('recalls_count', 0)} recalls, "
        f"{rating.get('investigation_count', 0)} investigations"
    )
    return "\n".join(lines)


@tool(approval_mode="never_require")
def lookup_models(
    make: Annotated[str, Field(description="Vehicle make / manufacturer (e.g. Honda, Toyota, BMW)")],
    year: Annotated[int | None, Field(description="Optional model year to filter by")] = None,
) -> str:
    """Look up what models are available for a given make, optionally by year."""
    try:
        models = _svc.get_models_for_make(make, year)
    except RuntimeError as e:
        return f"Error looking up models: {e}"

    if not models:
        year_str = f" ({year})" if year else ""
        return f"No models found for {make}{year_str}. Check the manufacturer name."

    year_str = f" ({year})" if year else ""
    lines = [f"## Models for {make.upper()}{year_str} — {len(models)} found\n"]
    for m in models:
        lines.append(f"- {m.get('model_name', 'N/A')}")
    return "\n".join(lines)


# ── Agent factory ────────────────────────────────────────────────────────────

SAFETY_CHECKER_INSTRUCTIONS = """\
You are **SafeCheck**, a vehicle safety research specialist powered by \
official NHTSA (National Highway Traffic Safety Administration) data.

Your job is to help users research vehicle safety — recalls, complaints, \
crash test ratings, and VIN decoding.

## How to behave
- When given a VIN, decode it first, then proactively offer to check recalls, \
complaints, and safety ratings.
- Always highlight open recalls prominently — they represent free repairs.
- For complaints, note patterns (e.g., multiple reports about same component).
- If safety ratings are low, explain what that means in plain language.
- Help users compare safety profiles of different vehicles.

## Limitations
- NHTSA data covers U.S.-market vehicles only.
- Safety ratings are available for most but not all vehicles/years.
- Complaint data reflects consumer reports, not verified defects.
"""


def create_safety_checker_agent(client: FoundryChatClient) -> Agent:
    """Create the Safety Checker specialist agent."""
    return Agent(
        client=client,
        name="safety_checker",
        description="Checks vehicle safety — recalls, crash test ratings, consumer complaints, and VIN decoding using NHTSA data.",
        instructions=SAFETY_CHECKER_INSTRUCTIONS,
        tools=[decode_vin, get_recalls, get_complaints, get_safety_ratings, lookup_models],
        default_options={"store": False},
        require_per_service_call_history_persistence=True,
    )
