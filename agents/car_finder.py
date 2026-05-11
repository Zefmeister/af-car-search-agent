# Copyright (c) 2026. Car Finder agent — searches mock inventory.

from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient
from pydantic import Field
from typing_extensions import Annotated

from car_data import CarSearchService

_car_svc = CarSearchService()

# ── Tools ────────────────────────────────────────────────────────────────────


@tool(approval_mode="never_require")
def search_cars(
    zip_code: Annotated[str, Field(description="5-digit US zip code for location-based search")],
    make: Annotated[str | None, Field(description="Vehicle make (e.g. Honda, Toyota)")] = None,
    model: Annotated[str | None, Field(description="Vehicle model (e.g. Civic, RAV4)")] = None,
    max_price: Annotated[int | None, Field(description="Maximum price in USD")] = None,
    min_price: Annotated[int | None, Field(description="Minimum price in USD")] = None,
    year_min: Annotated[int | None, Field(description="Earliest model year")] = None,
    year_max: Annotated[int | None, Field(description="Latest model year")] = None,
    max_mileage: Annotated[int | None, Field(description="Maximum mileage")] = None,
    body_type: Annotated[str | None, Field(description="Body type: sedan, suv, truck, coupe, hatchback, wagon")] = None,
    fuel_type: Annotated[str | None, Field(description="Fuel type: gas, electric, hybrid, plug-in hybrid")] = None,
    condition: Annotated[str | None, Field(description="Condition: new or used")] = None,
    radius_miles: Annotated[int | None, Field(description="Search radius in miles (default 25)")] = None,
) -> str:
    """Search car inventory by location, make, model, price, mileage, body type, and more.

    Returns up to 15 matching listings sorted by distance from the given zip code.
    If user doesn't specify a zip code, use 10001 (New York) as default.
    """
    results = _car_svc.search(
        zip_code=zip_code,
        make=make,
        model=model,
        max_price=max_price,
        min_price=min_price,
        year_min=year_min,
        year_max=year_max,
        max_mileage=max_mileage,
        body_type=body_type,
        fuel_type=fuel_type,
        condition=condition,
        radius_miles=radius_miles,
    )

    if not results:
        return "No cars found matching your criteria. Try broadening your search (larger radius, higher price, or fewer filters)."

    lines = [f"## Found {len(results)} matching vehicles\n"]
    for i, car in enumerate(results, 1):
        price_str = f"${car['price']:,}"
        miles_str = f"{car['mileage']:,} mi" if car["mileage"] > 0 else "New"
        lines.append(
            f"**{i}. {car['year']} {car['make']} {car['model']}** — {price_str}\n"
            f"   {car['trim']} | {car['color']} | {miles_str} | {car['fuel_type']}\n"
            f"   Location: {car['dealer_name']}, {car['dealer_city']}, {car['dealer_state']} "
            f"({car['distance_miles']} mi away)\n"
            f"   ID: `{car['listing_id'][:8]}`\n"
        )
    return "\n".join(lines)


@tool(approval_mode="never_require")
def get_listing_details(
    listing_id: Annotated[str, Field(description="The listing ID (full UUID or first 8 characters)")],
) -> str:
    """Get full details for a specific car listing including features, VIN, and dealer contact."""
    # Support partial IDs (first 8 chars)
    match = _car_svc.get_details(listing_id)
    if not match:
        # Try partial match
        for lid, car in _car_svc._by_id.items():
            if lid.startswith(listing_id):
                match = car
                break

    if not match:
        return f"Listing '{listing_id}' not found. Use search_cars to find available vehicles."

    lines = [
        f"## {match['year']} {match['make']} {match['model']} — ${match['price']:,}\n",
        f"**Trim:** {match['trim']}",
        f"**Condition:** {match['condition'].title()}",
        f"**Color:** {match['color']}",
        f"**Mileage:** {match['mileage']:,} miles" if match['mileage'] > 0 else "**Mileage:** 0 (New)",
        f"**Body Type:** {match['body_type'].title()}",
        f"**Fuel Type:** {match['fuel_type'].title()}",
        f"**Engine:** {match['engine']}",
        f"**Transmission:** {match['transmission']}",
        f"**Drivetrain:** {match['drivetrain']}",
        f"**VIN:** `{match['vin']}`",
        "",
        "**Features:**",
        ", ".join(match["features"]),
        "",
        "**Dealer:**",
        f"- {match['dealer_name']}",
        f"- {match['dealer_city']}, {match['dealer_state']} {match['dealer_zip']}",
        f"- {match['dealer_phone']}",
    ]
    return "\n".join(lines)


# ── Agent factory ────────────────────────────────────────────────────────────

CAR_FINDER_INSTRUCTIONS = """\
You are **CarFinder**, a car inventory search specialist.

Your job is to help users find cars from our listing database based on their \
preferences — make, model, price range, location, mileage, body type, etc.

## How to behave
- Ask clarifying questions if the user's criteria are vague (e.g., no location given → \
ask for zip code or use 10001 as default).
- Present results in a clean, scannable format.
- Highlight best-value picks and call out notable features.
- If no results match, suggest broadening filters.
- When you've helped the user find a car they're interested in, suggest they \
can check its safety record or get a price estimate by handing off.

## Limitations
- Inventory is a demo dataset (500 listings across major US cities).
- Prices are illustrative, not real market prices.
"""


def create_car_finder_agent(client: FoundryChatClient) -> Agent:
    """Create the Car Finder specialist agent."""
    return Agent(
        client=client,
        name="car_finder",
        description="Searches car inventory by make, model, price, location, mileage, and more.",
        instructions=CAR_FINDER_INSTRUCTIONS,
        tools=[search_cars, get_listing_details],
        default_options={"store": False},
        require_per_service_call_history_persistence=True,
    )
