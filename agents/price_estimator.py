# Copyright (c) 2026. Price Estimator agent — fair market value estimation.

from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient
from pydantic import Field
from typing_extensions import Annotated


@tool(approval_mode="never_require")
def estimate_price(
    make: Annotated[str, Field(description="Vehicle make (e.g. Honda, Toyota)")],
    model: Annotated[str, Field(description="Vehicle model (e.g. Civic, Camry)")],
    year: Annotated[int, Field(description="Model year")],
    mileage: Annotated[int, Field(description="Current odometer reading in miles")],
    condition: Annotated[str, Field(description="Condition: excellent, good, fair, poor")] = "good",
    trim: Annotated[str | None, Field(description="Trim level if known")] = None,
) -> str:
    """Estimate fair market value using depreciation model.

    Uses a simplified depreciation curve based on make, model, age, mileage,
    and condition. Returns a price range (low/mid/high) for private party
    and dealer pricing.
    """
    import datetime

    current_year = datetime.date.today().year
    age = current_year - year

    # Base MSRP estimates by segment (simplified)
    base_prices = {
        # Economy
        ("honda", "civic"): 25000, ("toyota", "corolla"): 23000,
        ("hyundai", "elantra"): 22000,
        # Mid-size
        ("honda", "accord"): 29000, ("toyota", "camry"): 28000,
        ("hyundai", "sonata"): 27000,
        # Compact SUV
        ("honda", "cr-v"): 31000, ("toyota", "rav4"): 30000,
        ("hyundai", "tucson"): 29000, ("subaru", "crosstrek"): 27000,
        ("ford", "escape"): 29000,
        # Mid-size SUV
        ("toyota", "highlander"): 40000, ("honda", "pilot"): 39000,
        ("ford", "explorer"): 37000, ("jeep", "grand cherokee"): 42000,
        ("hyundai", "palisade"): 37000,
        # Truck
        ("ford", "f-150"): 42000, ("chevrolet", "silverado 1500"): 40000,
        ("toyota", "tacoma"): 35000, ("ford", "maverick"): 28000,
        # Luxury
        ("bmw", "3 series"): 45000, ("bmw", "x3"): 48000, ("bmw", "x5"): 63000,
        ("mercedes-benz", "c-class"): 46000, ("mercedes-benz", "glc"): 50000,
        # Electric
        ("tesla", "model 3"): 40000, ("tesla", "model y"): 45000,
        ("tesla", "model s"): 80000,
        ("chevrolet", "bolt ev"): 28000, ("hyundai", "ioniq 5"): 42000,
        ("bmw", "ix"): 85000,
        # Sport
        ("ford", "mustang"): 35000, ("ford", "bronco"): 38000,
        ("subaru", "outback"): 30000, ("subaru", "forester"): 29000,
        ("jeep", "wrangler"): 35000,
    }

    # Look up base MSRP
    key = (make.lower(), model.lower())
    msrp = base_prices.get(key)
    if not msrp:
        # Estimate based on make tier
        make_tier = {
            "bmw": 50000, "mercedes-benz": 52000, "tesla": 50000,
            "toyota": 30000, "honda": 29000, "ford": 33000,
            "chevrolet": 32000, "hyundai": 27000, "subaru": 28000,
            "jeep": 36000,
        }
        msrp = make_tier.get(make.lower(), 30000)

    # Depreciation curve (annual % of remaining value lost)
    # Year 1: 20%, Year 2: 15%, Year 3-5: 12%, Year 6+: 8%
    value = msrp
    for yr in range(age):
        if yr == 0:
            value *= 0.80
        elif yr == 1:
            value *= 0.85
        elif yr <= 4:
            value *= 0.88
        else:
            value *= 0.92

    # Mileage adjustment: average 12k/year
    expected_miles = age * 12000
    mile_diff = mileage - expected_miles
    if mile_diff > 0:
        # High mileage penalty: -$0.05 per excess mile
        value -= mile_diff * 0.05
    elif mile_diff < 0:
        # Low mileage premium: +$0.03 per mile under
        value += abs(mile_diff) * 0.03

    # Condition multiplier
    condition_mult = {
        "excellent": 1.10,
        "good": 1.00,
        "fair": 0.88,
        "poor": 0.72,
    }.get(condition.lower(), 1.00)
    value *= condition_mult

    # Ensure minimum value
    value = max(value, 2000)

    # Price ranges
    private_party_mid = int(value)
    private_party_low = int(value * 0.90)
    private_party_high = int(value * 1.10)
    dealer_mid = int(value * 1.15)
    dealer_low = int(value * 1.05)
    dealer_high = int(value * 1.25)

    trim_note = f" ({trim})" if trim else ""
    lines = [
        f"## Price Estimate: {year} {make} {model}{trim_note}\n",
        f"**Mileage:** {mileage:,} miles",
        f"**Condition:** {condition.title()}",
        f"**Vehicle Age:** {age} years",
        "",
        "### Private Party Value",
        f"- Low: ${private_party_low:,}",
        f"- **Mid: ${private_party_mid:,}**",
        f"- High: ${private_party_high:,}",
        "",
        "### Dealer Retail Value",
        f"- Low: ${dealer_low:,}",
        f"- **Mid: ${dealer_mid:,}**",
        f"- High: ${dealer_high:,}",
        "",
        "---",
        f"*Based on {current_year} MSRP of ~${msrp:,} with standard depreciation curve.*",
        "*Actual prices vary by region, market conditions, and vehicle history.*",
    ]

    # Add context
    if mile_diff > 20000:
        lines.append(f"\n⚠️ High mileage ({mileage:,} vs expected {expected_miles:,}) — price adjusted down.")
    elif mile_diff < -20000:
        lines.append(f"\n[+] Low mileage ({mileage:,} vs expected {expected_miles:,}) -- price adjusted up.")

    return "\n".join(lines)


@tool(approval_mode="never_require")
def compare_prices(
    vehicles: Annotated[
        str,
        Field(description="Comma-separated list of vehicles to compare, format: 'year make model mileage' per entry, e.g. '2021 Honda Civic 35000, 2022 Toyota Corolla 20000'"),
    ],
) -> str:
    """Compare estimated prices for multiple vehicles side by side.

    Provide vehicles as comma-separated entries: 'year make model mileage'.
    """
    import datetime

    entries = [v.strip() for v in vehicles.split(",")]
    if len(entries) < 2:
        return "Please provide at least 2 vehicles to compare (comma-separated)."

    lines = ["## Price Comparison\n"]
    lines.append("| Vehicle | Est. Value (Private) | Est. Value (Dealer) |")
    lines.append("|---------|---------------------|---------------------|")

    for entry in entries[:5]:  # Max 5 comparisons
        parts = entry.split()
        if len(parts) < 4:
            lines.append(f"| {entry} | [X] Invalid format | -- |")
            continue

        try:
            year = int(parts[0])
            mileage = int(parts[-1])
            make = parts[1]
            model = " ".join(parts[2:-1])
        except ValueError:
            lines.append(f"| {entry} | [X] Parse error | -- |")
            continue

        # Quick inline calculation (same logic as estimate_price)
        current_year = datetime.date.today().year
        age = current_year - year
        base_prices = {
            ("honda", "civic"): 25000, ("toyota", "corolla"): 23000,
            ("honda", "cr-v"): 31000, ("toyota", "rav4"): 30000,
            ("ford", "f-150"): 42000, ("tesla", "model 3"): 40000,
            ("bmw", "3 series"): 45000,
        }
        msrp = base_prices.get((make.lower(), model.lower()), 30000)
        value = msrp
        for yr in range(age):
            if yr == 0:
                value *= 0.80
            elif yr == 1:
                value *= 0.85
            elif yr <= 4:
                value *= 0.88
            else:
                value *= 0.92
        expected_miles = age * 12000
        mile_diff = mileage - expected_miles
        if mile_diff > 0:
            value -= mile_diff * 0.05
        elif mile_diff < 0:
            value += abs(mile_diff) * 0.03
        value = max(value, 2000)

        private_val = f"${int(value):,}"
        dealer_val = f"${int(value * 1.15):,}"
        lines.append(f"| {year} {make} {model} ({mileage:,} mi) | {private_val} | {dealer_val} |")

    lines.append("\n*Estimates assume 'good' condition. Actual values vary.*")
    return "\n".join(lines)


# ── Agent factory ────────────────────────────────────────────────────────────

PRICE_ESTIMATOR_INSTRUCTIONS = """\
You are **PriceCheck**, a vehicle price estimation specialist.

Your job is to help users understand the fair market value of a vehicle \
based on its make, model, year, mileage, and condition.

## How to behave
- When given vehicle details, provide a clear price range (private party vs dealer).
- Explain factors that affect pricing (mileage, condition, age).
- For comparisons, present a side-by-side table.
- If the user has a specific listing price, tell them if it's above, below, or \
at market value.
- Be transparent that these are estimates based on a depreciation model, not live \
market data.

## Limitations
- Prices are estimates based on standard depreciation curves.
- Does not account for regional market variations, accident history, or \
specific trim packages in detail.
- For the most accurate valuation, recommend checking KBB or Edmunds.
"""


def create_price_estimator_agent(client: FoundryChatClient) -> Agent:
    """Create the Price Estimator specialist agent."""
    return Agent(
        client=client,
        name="price_estimator",
        description="Estimates fair market value using depreciation models — provides private party and dealer price ranges.",
        instructions=PRICE_ESTIMATOR_INSTRUCTIONS,
        tools=[estimate_price, compare_prices],
        default_options={"store": False},
        require_per_service_call_history_persistence=True,
    )
