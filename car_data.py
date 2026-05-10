# Copyright (c) 2026. Car listing data service.
# Provides a clean interface for car search — currently backed by mock data.
# To switch to a real API (e.g., Marketcheck, CarAPI), implement a new class
# with the same search() / get_details() interface and swap it in main.py.

from __future__ import annotations

import math
import random
import uuid
from typing import Any

# ── Zip code → approximate coordinates (subset for demo) ─────────────────────
# In production, use a geocoding API or a full zip-code database.
_ZIP_COORDS: dict[str, tuple[float, float]] = {
    "10001": (40.7484, -73.9967),   # New York, NY
    "10002": (40.7157, -73.9863),
    "10003": (40.7317, -73.9893),
    "10016": (40.7459, -73.9778),
    "07030": (40.7440, -74.0324),   # Hoboken, NJ
    "07302": (40.7178, -74.0431),   # Jersey City, NJ
    "11201": (40.6936, -73.9897),   # Brooklyn, NY
    "11101": (40.7429, -73.9234),   # Long Island City, NY
    "90001": (33.9425, -118.2551),  # Los Angeles, CA
    "90012": (34.0669, -118.2400),
    "90210": (34.0901, -118.4065),  # Beverly Hills, CA
    "90401": (34.0195, -118.4912),  # Santa Monica, CA
    "91101": (34.1478, -118.1445),  # Pasadena, CA
    "91301": (34.1597, -118.7606),  # Calabasas, CA
    "60601": (41.8819, -87.6278),   # Chicago, IL
    "60602": (41.8832, -87.6285),
    "60614": (41.9215, -87.6513),
    "60657": (41.9400, -87.6531),
    "77001": (29.7604, -95.3698),   # Houston, TX
    "77002": (29.7572, -95.3583),
    "77030": (29.7067, -95.3964),
    "75201": (32.7872, -96.7985),   # Dallas, TX
    "75202": (32.7811, -96.7978),
    "33101": (25.7617, -80.1918),   # Miami, FL
    "33109": (25.7598, -80.1349),   # Miami Beach, FL
    "33131": (25.7627, -80.1892),
    "85001": (33.4484, -112.0740),  # Phoenix, AZ
    "85281": (33.4152, -111.8315),  # Tempe, AZ
    "98101": (47.6062, -122.3321),  # Seattle, WA
    "98102": (47.6383, -122.3227),
    "30301": (33.7490, -84.3880),   # Atlanta, GA
    "30303": (33.7537, -84.3925),
    "02101": (42.3601, -71.0589),   # Boston, MA
    "02102": (42.3388, -71.0480),
    "94102": (37.7749, -122.4194),  # San Francisco, CA
    "94103": (37.7726, -122.4099),
    "19101": (39.9526, -75.1652),   # Philadelphia, PA
    "19102": (39.9489, -75.1654),
    "80201": (39.7392, -104.9903),  # Denver, CO
    "80202": (39.7536, -104.9962),
    "48201": (42.3314, -83.0458),   # Detroit, MI
    "48202": (42.3669, -83.0749),
}

# ── Mock car inventory ────────────────────────────────────────────────────────

_MAKES_MODELS: dict[str, list[dict[str, Any]]] = {
    "Toyota": [
        {"model": "Camry", "body_type": "sedan", "fuel_type": "gas", "engine": "2.5L 4-Cylinder"},
        {"model": "RAV4", "body_type": "suv", "fuel_type": "gas", "engine": "2.5L 4-Cylinder"},
        {"model": "RAV4 Hybrid", "body_type": "suv", "fuel_type": "hybrid", "engine": "2.5L 4-Cylinder Hybrid"},
        {"model": "Tacoma", "body_type": "truck", "fuel_type": "gas", "engine": "3.5L V6"},
        {"model": "Corolla", "body_type": "sedan", "fuel_type": "gas", "engine": "2.0L 4-Cylinder"},
        {"model": "Highlander", "body_type": "suv", "fuel_type": "gas", "engine": "3.5L V6"},
    ],
    "Honda": [
        {"model": "Civic", "body_type": "sedan", "fuel_type": "gas", "engine": "2.0L 4-Cylinder"},
        {"model": "CR-V", "body_type": "suv", "fuel_type": "gas", "engine": "1.5L Turbo 4-Cylinder"},
        {"model": "CR-V Hybrid", "body_type": "suv", "fuel_type": "hybrid", "engine": "2.0L 4-Cylinder Hybrid"},
        {"model": "Accord", "body_type": "sedan", "fuel_type": "gas", "engine": "1.5L Turbo 4-Cylinder"},
        {"model": "Pilot", "body_type": "suv", "fuel_type": "gas", "engine": "3.5L V6"},
    ],
    "Ford": [
        {"model": "F-150", "body_type": "truck", "fuel_type": "gas", "engine": "3.5L EcoBoost V6"},
        {"model": "Mustang", "body_type": "coupe", "fuel_type": "gas", "engine": "5.0L V8"},
        {"model": "Escape", "body_type": "suv", "fuel_type": "gas", "engine": "1.5L EcoBoost"},
        {"model": "Bronco", "body_type": "suv", "fuel_type": "gas", "engine": "2.7L EcoBoost V6"},
        {"model": "Maverick", "body_type": "truck", "fuel_type": "hybrid", "engine": "2.5L Hybrid"},
    ],
    "Tesla": [
        {"model": "Model 3", "body_type": "sedan", "fuel_type": "electric", "engine": "Electric Motor"},
        {"model": "Model Y", "body_type": "suv", "fuel_type": "electric", "engine": "Dual Motor AWD"},
        {"model": "Model S", "body_type": "sedan", "fuel_type": "electric", "engine": "Dual Motor AWD"},
    ],
    "BMW": [
        {"model": "3 Series", "body_type": "sedan", "fuel_type": "gas", "engine": "2.0L Turbo 4-Cylinder"},
        {"model": "X3", "body_type": "suv", "fuel_type": "gas", "engine": "2.0L Turbo 4-Cylinder"},
        {"model": "X5", "body_type": "suv", "fuel_type": "gas", "engine": "3.0L Turbo Inline-6"},
        {"model": "iX", "body_type": "suv", "fuel_type": "electric", "engine": "Dual Motor AWD"},
    ],
    "Chevrolet": [
        {"model": "Silverado 1500", "body_type": "truck", "fuel_type": "gas", "engine": "5.3L V8"},
        {"model": "Equinox", "body_type": "suv", "fuel_type": "gas", "engine": "1.5L Turbo"},
        {"model": "Bolt EV", "body_type": "hatchback", "fuel_type": "electric", "engine": "Electric Motor"},
        {"model": "Tahoe", "body_type": "suv", "fuel_type": "gas", "engine": "5.3L V8"},
    ],
    "Hyundai": [
        {"model": "Tucson", "body_type": "suv", "fuel_type": "gas", "engine": "2.5L 4-Cylinder"},
        {"model": "Elantra", "body_type": "sedan", "fuel_type": "gas", "engine": "2.0L 4-Cylinder"},
        {"model": "Ioniq 5", "body_type": "suv", "fuel_type": "electric", "engine": "Dual Motor AWD"},
        {"model": "Palisade", "body_type": "suv", "fuel_type": "gas", "engine": "3.8L V6"},
    ],
    "Mercedes-Benz": [
        {"model": "C-Class", "body_type": "sedan", "fuel_type": "gas", "engine": "2.0L Turbo 4-Cylinder"},
        {"model": "GLC", "body_type": "suv", "fuel_type": "gas", "engine": "2.0L Turbo 4-Cylinder"},
        {"model": "EQS", "body_type": "sedan", "fuel_type": "electric", "engine": "Dual Motor AWD"},
    ],
    "Subaru": [
        {"model": "Outback", "body_type": "wagon", "fuel_type": "gas", "engine": "2.5L Boxer 4-Cylinder"},
        {"model": "Forester", "body_type": "suv", "fuel_type": "gas", "engine": "2.5L Boxer 4-Cylinder"},
        {"model": "Crosstrek", "body_type": "suv", "fuel_type": "gas", "engine": "2.0L Boxer 4-Cylinder"},
    ],
    "Jeep": [
        {"model": "Wrangler", "body_type": "suv", "fuel_type": "gas", "engine": "3.6L V6"},
        {"model": "Grand Cherokee", "body_type": "suv", "fuel_type": "gas", "engine": "3.6L V6"},
        {"model": "Grand Cherokee 4xe", "body_type": "suv", "fuel_type": "plug-in hybrid", "engine": "2.0L Turbo PHEV"},
    ],
}

_COLORS = ["White", "Black", "Silver", "Gray", "Red", "Blue", "Green", "Brown", "Orange", "Yellow"]
_TRIMS = ["Base", "SE", "LE", "XLE", "Sport", "Limited", "Premium", "Platinum", "Touring"]
_TRANSMISSIONS = ["Automatic", "CVT", "Manual", "Dual-Clutch"]
_DRIVETRAINS = ["FWD", "RWD", "AWD", "4WD"]
_FEATURES_POOL = [
    "Apple CarPlay", "Android Auto", "Bluetooth", "Backup Camera",
    "Blind Spot Monitor", "Lane Departure Warning", "Adaptive Cruise Control",
    "Heated Seats", "Leather Seats", "Sunroof/Moonroof", "Navigation System",
    "Keyless Entry", "Push Button Start", "Remote Start", "LED Headlights",
    "Alloy Wheels", "Tow Package", "Third Row Seating", "Wireless Charging",
    "360-Degree Camera", "Parking Sensors", "Power Liftgate",
    "Premium Sound System", "Ventilated Seats", "Head-Up Display",
]

_DEALER_NAMES = [
    "AutoNation", "Hendrick Automotive", "Penske Motor Group",
    "Larry H. Miller", "Sonic Automotive", "Lithia Motors",
    "Group 1 Automotive", "Asbury Automotive", "Metro Auto Gallery",
    "CarMax", "Carvana", "Suburban Motors", "Heritage Auto",
    "Pioneer Auto Group", "Prestige Motor Works",
]


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return distance in miles between two lat/lon points."""
    R = 3958.8  # Earth radius in miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def _generate_listings(count: int = 500, seed: int = 42) -> list[dict[str, Any]]:
    """Generate a reproducible set of mock car listings spread across zip codes."""
    rng = random.Random(seed)
    listings: list[dict[str, Any]] = []
    zips = list(_ZIP_COORDS.keys())

    for _ in range(count):
        make = rng.choice(list(_MAKES_MODELS.keys()))
        model_info = rng.choice(_MAKES_MODELS[make])
        year = rng.randint(2018, 2026)
        condition = "new" if year >= 2025 and rng.random() < 0.3 else "used"
        base_price = {
            "sedan": 22000, "suv": 30000, "truck": 34000, "coupe": 28000,
            "hatchback": 24000, "wagon": 27000, "van": 32000, "convertible": 35000,
        }.get(model_info["body_type"], 25000)

        # Adjust price by make tier
        make_multiplier = {
            "BMW": 1.6, "Mercedes-Benz": 1.7, "Tesla": 1.4,
            "Jeep": 1.1, "Subaru": 1.0, "Hyundai": 0.85,
        }.get(make, 1.0)

        price = int(base_price * make_multiplier * (0.6 + 0.08 * (year - 2018)) * rng.uniform(0.85, 1.25))
        if condition == "new":
            price = int(price * 1.15)

        mileage = 0 if condition == "new" else rng.randint(5000, 120000)
        dealer_zip = rng.choice(zips)
        dlat, dlon = _ZIP_COORDS[dealer_zip]

        listing = {
            "listing_id": str(uuid.UUID(int=rng.getrandbits(128))),
            "make": make,
            "model": model_info["model"],
            "year": year,
            "price": price,
            "mileage": mileage,
            "condition": condition,
            "color": rng.choice(_COLORS),
            "body_type": model_info["body_type"],
            "fuel_type": model_info["fuel_type"],
            "trim": rng.choice(_TRIMS),
            "transmission": rng.choice(_TRANSMISSIONS),
            "drivetrain": rng.choice(_DRIVETRAINS),
            "engine": model_info["engine"],
            "vin": "".join(rng.choices("ABCDEFGHJKLMNPRSTUVWXYZ0123456789", k=17)),
            "features": rng.sample(_FEATURES_POOL, k=rng.randint(5, 12)),
            "dealer_name": rng.choice(_DEALER_NAMES),
            "dealer_zip": dealer_zip,
            "dealer_city": _zip_to_city(dealer_zip),
            "dealer_state": _zip_to_state(dealer_zip),
            "dealer_phone": f"({rng.randint(200,999)}) {rng.randint(200,999)}-{rng.randint(1000,9999)}",
            "dealer_lat": dlat,
            "dealer_lon": dlon,
        }
        listings.append(listing)
    return listings


def _zip_to_city(z: str) -> str:
    _map = {
        "10001": "New York", "10002": "New York", "10003": "New York", "10016": "New York",
        "07030": "Hoboken", "07302": "Jersey City", "11201": "Brooklyn", "11101": "Long Island City",
        "90001": "Los Angeles", "90012": "Los Angeles", "90210": "Beverly Hills",
        "90401": "Santa Monica", "91101": "Pasadena", "91301": "Calabasas",
        "60601": "Chicago", "60602": "Chicago", "60614": "Chicago", "60657": "Chicago",
        "77001": "Houston", "77002": "Houston", "77030": "Houston",
        "75201": "Dallas", "75202": "Dallas",
        "33101": "Miami", "33109": "Miami Beach", "33131": "Miami",
        "85001": "Phoenix", "85281": "Tempe",
        "98101": "Seattle", "98102": "Seattle",
        "30301": "Atlanta", "30303": "Atlanta",
        "02101": "Boston", "02102": "Boston",
        "94102": "San Francisco", "94103": "San Francisco",
        "19101": "Philadelphia", "19102": "Philadelphia",
        "80201": "Denver", "80202": "Denver",
        "48201": "Detroit", "48202": "Detroit",
    }
    return _map.get(z, "Unknown")


def _zip_to_state(z: str) -> str:
    prefix = z[:3]
    _map = {
        "100": "NY", "070": "NJ", "073": "NJ", "112": "NY", "111": "NY",
        "900": "CA", "902": "CA", "904": "CA", "911": "CA", "913": "CA",
        "606": "IL", "770": "TX", "752": "TX",
        "331": "FL", "850": "AZ", "852": "AZ",
        "981": "WA", "303": "GA", "021": "MA",
        "941": "CA", "191": "PA", "802": "CO", "482": "MI",
    }
    return _map.get(prefix, "XX")


class CarSearchService:
    """Car listing search service backed by mock data.

    To swap in a real API, implement a class with the same search() and
    get_details() signatures and replace this in main.py.
    """

    def __init__(self) -> None:
        self._listings = _generate_listings()
        self._by_id = {c["listing_id"]: c for c in self._listings}

    def search(
        self,
        zip_code: str,
        max_price: int | None = None,
        min_price: int | None = None,
        make: str | None = None,
        model: str | None = None,
        year_min: int | None = None,
        year_max: int | None = None,
        max_mileage: int | None = None,
        condition: str | None = None,
        body_type: str | None = None,
        fuel_type: str | None = None,
        color: str | None = None,
        radius_miles: int | None = 25,
    ) -> list[dict[str, Any]]:
        """Return listings matching filters, sorted by distance from zip_code."""
        origin = _ZIP_COORDS.get(zip_code)
        if not origin:
            # If zip not in our dataset, pick closest known zip
            origin = (39.8283, -98.5795)  # geographic center of US as fallback

        radius = radius_miles or 25
        results: list[dict[str, Any]] = []

        for car in self._listings:
            dist = _haversine(origin[0], origin[1], car["dealer_lat"], car["dealer_lon"])
            if dist > radius:
                continue
            if max_price is not None and car["price"] > max_price:
                continue
            if min_price is not None and car["price"] < min_price:
                continue
            if make and car["make"].lower() != make.lower():
                continue
            if model and model.lower() not in car["model"].lower():
                continue
            if year_min is not None and car["year"] < year_min:
                continue
            if year_max is not None and car["year"] > year_max:
                continue
            if max_mileage is not None and car["mileage"] > max_mileage:
                continue
            if condition and car["condition"].lower() != condition.lower():
                continue
            if body_type and car["body_type"].lower() != body_type.lower():
                continue
            if fuel_type and car["fuel_type"].lower() != fuel_type.lower():
                continue
            if color and car["color"].lower() != color.lower():
                continue

            result = {**car, "distance_miles": round(dist, 1)}
            results.append(result)

        # Sort by distance, limit to 15 results
        results.sort(key=lambda x: x["distance_miles"])
        return results[:15]

    def get_details(self, listing_id: str) -> dict[str, Any] | None:
        """Return full details for a single listing, or None if not found."""
        return self._by_id.get(listing_id)
