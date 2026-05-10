# Copyright (c) 2026. Car Search Agent — Microsoft Agent Framework.

import os

from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from pydantic import Field
from typing_extensions import Annotated

from car_data import CarSearchService

# Load environment variables from .env file.
# override=False so Foundry-injected env vars take precedence at runtime.
load_dotenv(override=False)

# Initialise the car search data service
car_service = CarSearchService()

# ── Tools ────────────────────────────────────────────────────────────────────


@tool(approval_mode="never_require")
def search_cars(
    zip_code: Annotated[str, Field(description="The 5-digit US zip code to search near")],
    max_price: Annotated[int | None, Field(description="Maximum price in USD")] = None,
    min_price: Annotated[int | None, Field(description="Minimum price in USD")] = None,
    make: Annotated[str | None, Field(description="Car make / manufacturer (e.g. Toyota, Honda, BMW)")] = None,
    model: Annotated[str | None, Field(description="Car model (e.g. Camry, Civic, X3)")] = None,
    year_min: Annotated[int | None, Field(description="Minimum model year")] = None,
    year_max: Annotated[int | None, Field(description="Maximum model year")] = None,
    max_mileage: Annotated[int | None, Field(description="Maximum mileage in miles")] = None,
    condition: Annotated[str | None, Field(description="'new' or 'used'")] = None,
    body_type: Annotated[str | None, Field(description="Body type: sedan, suv, truck, coupe, hatchback, wagon, van, convertible")] = None,
    fuel_type: Annotated[str | None, Field(description="Fuel type: gas, diesel, electric, hybrid, plug-in hybrid")] = None,
    color: Annotated[str | None, Field(description="Exterior color")] = None,
    radius_miles: Annotated[int | None, Field(description="Search radius in miles from zip code (default 25)")] = 25,
) -> str:
    """Search for available cars based on the user's preferences.

    Returns a list of matching car listings with details like price, mileage,
    year, make, model, and dealer information. Always ask the user for at
    least a zip code before calling this tool.
    """
    results = car_service.search(
        zip_code=zip_code,
        max_price=max_price,
        min_price=min_price,
        make=make,
        model=model,
        year_min=year_min,
        year_max=year_max,
        max_mileage=max_mileage,
        condition=condition,
        body_type=body_type,
        fuel_type=fuel_type,
        color=color,
        radius_miles=radius_miles,
    )
    if not results:
        return "No cars found matching your criteria. Try broadening your search — increase the radius, raise the budget, or remove some filters."
    # Format results for the model
    lines = [f"Found {len(results)} car(s):\n"]
    for i, car in enumerate(results, 1):
        lines.append(
            f"{i}. {car['year']} {car['make']} {car['model']} — "
            f"${car['price']:,} | {car['mileage']:,} mi | {car['condition']} | "
            f"{car['color']} {car['body_type']} | {car['fuel_type']} | "
            f"Dealer: {car['dealer_name']} ({car['dealer_city']}, {car['dealer_state']}) | "
            f"{car['distance_miles']} mi away"
        )
    return "\n".join(lines)


@tool(approval_mode="never_require")
def get_car_details(
    listing_id: Annotated[str, Field(description="The listing ID of the car to get details for")],
) -> str:
    """Get detailed information about a specific car listing, including
    full feature list, vehicle history, and dealer contact information.
    """
    car = car_service.get_details(listing_id)
    if not car:
        return "Listing not found. It may have been sold or removed."
    lines = [
        f"## {car['year']} {car['make']} {car['model']} {car.get('trim', '')}",
        f"**Price:** ${car['price']:,}",
        f"**Condition:** {car['condition']}",
        f"**Mileage:** {car['mileage']:,} miles",
        f"**Exterior Color:** {car['color']}",
        f"**Body Type:** {car['body_type']}",
        f"**Fuel Type:** {car['fuel_type']}",
        f"**Transmission:** {car.get('transmission', 'N/A')}",
        f"**Drivetrain:** {car.get('drivetrain', 'N/A')}",
        f"**Engine:** {car.get('engine', 'N/A')}",
        f"**VIN:** {car.get('vin', 'N/A')}",
        "",
        f"**Features:** {', '.join(car.get('features', []))}",
        "",
        f"**Dealer:** {car['dealer_name']}",
        f"**Location:** {car['dealer_city']}, {car['dealer_state']} {car['dealer_zip']}",
        f"**Phone:** {car.get('dealer_phone', 'N/A')}",
    ]
    return "\n".join(lines)


# ── Agent setup ──────────────────────────────────────────────────────────────

SYSTEM_INSTRUCTIONS = """\
You are **CarFinder**, a friendly and knowledgeable car-shopping assistant.

Your job is to help users find available cars that match their preferences.
You have access to a car listings database via tools.

## How to behave
- Always greet the user warmly and ask clarifying questions when needed.
- At minimum, ask for a **zip code** before searching.
- Suggest relevant filters (budget, make/model, body type, etc.) to narrow results.
- Present results in a clean, easy-to-read format with key highlights.
- When showing multiple results, offer to give more details on any listing.
- If no results are found, suggest broadening the search criteria.
- Be conversational but concise — users are busy car shoppers!
- When comparing cars, create helpful comparison summaries.
- Proactively mention important considerations (e.g., fuel economy for long commutes,
  AWD for snowy areas, cargo space for families).

## Formatting
- Use bullet points and bold text for readability.
- Show prices prominently.
- Mention distance from the user's location.
"""


def main():
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=DefaultAzureCredential(),
    )

    agent = Agent(
        client=client,
        instructions=SYSTEM_INSTRUCTIONS,
        tools=[search_cars, get_car_details],
        # History managed by hosting infrastructure
        default_options={"store": False},
    )

    server = ResponsesHostServer(agent)
    server.run()


if __name__ == "__main__":
    main()
