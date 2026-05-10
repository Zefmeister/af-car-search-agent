# Copyright (c) 2026. Mock vehicle safety data service.
# Returns realistic fake data matching the NHTSAService interface.
# Activated by MOCK_MODE=true in environment.

from __future__ import annotations

from typing import Any


class MockService:
    """Drop-in replacement for NHTSAService using static mock data.

    Useful for demos, local development, and testing without network access.
    """

    # ── VIN Decode ────────────────────────────────────────────────────────────

    _MOCK_VINS: dict[str, dict[str, Any]] = {
        "1HGBH41JXMN109186": {
            "vin": "1HGBH41JXMN109186",
            "make": "HONDA",
            "model": "Civic",
            "year": "2021",
            "trim": "EX",
            "body_class": "Sedan/Saloon",
            "vehicle_type": "PASSENGER CAR",
            "doors": "4",
            "drive_type": "FWD",
            "fuel_type_primary": "Gasoline",
            "engine_cylinders": "4",
            "displacement_l": "2.0",
            "engine_hp": "158",
            "transmission": "CVT",
            "plant_city": "Greensburg",
            "plant_country": "UNITED STATES (USA)",
            "manufacturer": "HONDA MOTOR CO., LTD",
            "abs": "Standard",
            "tpms": "Direct",
            "esc": "Standard",
            "forward_collision_warning": "Standard",
            "lane_departure_warning": "Standard",
            "blind_spot_warning": "Standard",
        },
        "5YJSA1E26MF000001": {
            "vin": "5YJSA1E26MF000001",
            "make": "TESLA",
            "model": "Model S",
            "year": "2021",
            "trim": "Long Range",
            "body_class": "Hatchback/Liftback",
            "vehicle_type": "PASSENGER CAR",
            "doors": "4",
            "drive_type": "AWD",
            "fuel_type_primary": "Electric",
            "engine_cylinders": "",
            "displacement_l": "",
            "engine_hp": "670",
            "transmission": "1-Speed Direct Drive",
            "plant_city": "Fremont",
            "plant_country": "UNITED STATES (USA)",
            "manufacturer": "TESLA, INC.",
            "electrification": "BEV (Battery Electric Vehicle)",
            "abs": "Standard",
            "tpms": "Direct",
            "esc": "Standard",
            "forward_collision_warning": "Standard",
            "lane_departure_warning": "Standard",
            "adaptive_cruise_control": "Standard",
            "blind_spot_warning": "Standard",
        },
        "1FTFW1E57MFA00001": {
            "vin": "1FTFW1E57MFA00001",
            "make": "FORD",
            "model": "F-150",
            "year": "2021",
            "trim": "XLT",
            "body_class": "Pickup",
            "vehicle_type": "TRUCK",
            "doors": "4",
            "drive_type": "4WD",
            "fuel_type_primary": "Gasoline",
            "engine_cylinders": "6",
            "displacement_l": "3.5",
            "engine_hp": "400",
            "transmission": "Automatic",
            "plant_city": "Dearborn",
            "plant_country": "UNITED STATES (USA)",
            "manufacturer": "FORD MOTOR COMPANY, LLC",
            "abs": "Standard",
            "tpms": "Direct",
            "esc": "Standard",
        },
    }

    def decode_vin(self, vin: str) -> dict[str, Any]:
        upper = vin.upper().replace(" ", "")
        if upper in self._MOCK_VINS:
            return self._MOCK_VINS[upper]
        # Generate a plausible generic decode for unknown VINs
        return {
            "vin": upper,
            "make": "TOYOTA",
            "model": "Camry",
            "year": "2023",
            "trim": "SE",
            "body_class": "Sedan/Saloon",
            "vehicle_type": "PASSENGER CAR",
            "doors": "4",
            "drive_type": "FWD",
            "fuel_type_primary": "Gasoline",
            "engine_cylinders": "4",
            "displacement_l": "2.5",
            "engine_hp": "203",
            "transmission": "Automatic",
            "plant_city": "Georgetown",
            "plant_country": "UNITED STATES (USA)",
            "manufacturer": "TOYOTA MOTOR MANUFACTURING, KENTUCKY, INC.",
            "abs": "Standard",
            "esc": "Standard",
            "error_text": "(Mock) VIN not in mock database — returned default Toyota Camry.",
        }

    # ── Recalls ───────────────────────────────────────────────────────────────

    _MOCK_RECALLS: dict[str, list[dict[str, Any]]] = {
        "honda_civic_2021": [
            {
                "nhtsa_campaign_number": "21V786000",
                "component": "ENGINE AND ENGINE COOLING",
                "summary": "Honda is recalling certain 2021 Civic vehicles. The engine "
                           "control module software may cause unexpected engine stalling.",
                "consequence": "An engine stall while driving increases the risk of a crash.",
                "remedy": "Dealers will update the engine control module software, free of charge.",
                "report_date": "10/15/2021",
                "manufacturer": "Honda (American Honda Motor Co.)",
            },
        ],
        "ford_f-150_2021": [
            {
                "nhtsa_campaign_number": "21V917000",
                "component": "ELECTRICAL SYSTEM",
                "summary": "Ford is recalling certain 2021 F-150 vehicles. The windshield "
                           "wiper motor may fail.",
                "consequence": "Loss of windshield wiper function during rain reduces visibility "
                               "and increases the risk of a crash.",
                "remedy": "Dealers will replace the wiper motor, free of charge.",
                "report_date": "12/01/2021",
                "manufacturer": "Ford Motor Company",
            },
            {
                "nhtsa_campaign_number": "22V043000",
                "component": "FUEL SYSTEM, GASOLINE",
                "summary": "Ford is recalling certain 2021 F-150 vehicles equipped with "
                           "3.5L EcoBoost engines. A fuel injector may crack.",
                "consequence": "A cracked fuel injector can cause fuel odor, a fuel leak, and "
                               "possibly a fire.",
                "remedy": "Dealers will inspect and replace the fuel injectors if necessary, "
                          "free of charge.",
                "report_date": "01/20/2022",
                "manufacturer": "Ford Motor Company",
            },
        ],
        "tesla_model s_2021": [],
        "toyota_camry_2023": [
            {
                "nhtsa_campaign_number": "23V456000",
                "component": "AIR BAGS",
                "summary": "Toyota is recalling certain 2023 Camry vehicles. The front "
                           "passenger airbag may not deploy correctly.",
                "consequence": "In a crash, the airbag may not adequately protect the occupant.",
                "remedy": "Dealers will replace the airbag module, free of charge.",
                "report_date": "06/15/2023",
                "manufacturer": "Toyota Motor Engineering & Manufacturing",
            },
        ],
    }

    def get_recalls(
        self, make: str, model: str, year: int
    ) -> list[dict[str, Any]]:
        key = f"{make.lower()}_{model.lower()}_{year}"
        return self._MOCK_RECALLS.get(key, [])

    # ── Complaints ────────────────────────────────────────────────────────────

    _MOCK_COMPLAINTS: dict[str, list[dict[str, Any]]] = {
        "honda_civic_2021": [
            {
                "odi_number": "11400001",
                "component": "ENGINE",
                "summary": "While driving at highway speed, the engine suddenly lost power "
                           "without warning. Restarting the vehicle resolved the issue temporarily.",
                "crash": False,
                "fire": False,
                "injuries": 0,
                "deaths": 0,
                "date_filed": "03/10/2022",
            },
            {
                "odi_number": "11400002",
                "component": "ELECTRICAL SYSTEM",
                "summary": "The infotainment system intermittently freezes and the backup "
                           "camera goes black. Requires a full system reboot.",
                "crash": False,
                "fire": False,
                "injuries": 0,
                "deaths": 0,
                "date_filed": "05/22/2022",
            },
        ],
        "ford_f-150_2021": [
            {
                "odi_number": "11400010",
                "component": "ELECTRICAL SYSTEM",
                "summary": "The dashboard display went completely blank while driving. "
                           "Speedometer, fuel gauge, and warning indicators were all lost.",
                "crash": False,
                "fire": False,
                "injuries": 0,
                "deaths": 0,
                "date_filed": "02/14/2022",
            },
            {
                "odi_number": "11400011",
                "component": "POWER TRAIN",
                "summary": "Transmission jerks harshly when shifting between 2nd and 3rd gear. "
                           "Dealer says software update should fix it but problem persists.",
                "crash": False,
                "fire": False,
                "injuries": 0,
                "deaths": 0,
                "date_filed": "04/03/2022",
            },
            {
                "odi_number": "11400012",
                "component": "FUEL SYSTEM",
                "summary": "Noticed strong fuel smell coming from the engine compartment. "
                           "Dealer found a cracked fuel injector and replaced under recall.",
                "crash": False,
                "fire": False,
                "injuries": 0,
                "deaths": 0,
                "date_filed": "06/18/2022",
            },
        ],
        "tesla_model s_2021": [
            {
                "odi_number": "11400020",
                "component": "ELECTRICAL SYSTEM",
                "summary": "Touchscreen became unresponsive while driving. Unable to access "
                           "climate controls, turn signals via screen, or navigation.",
                "crash": False,
                "fire": False,
                "injuries": 0,
                "deaths": 0,
                "date_filed": "01/08/2022",
            },
        ],
        "toyota_camry_2023": [],
    }

    def get_complaints(
        self, make: str, model: str, year: int
    ) -> list[dict[str, Any]]:
        key = f"{make.lower()}_{model.lower()}_{year}"
        return self._MOCK_COMPLAINTS.get(key, [])

    # ── Safety Ratings ────────────────────────────────────────────────────────

    _MOCK_RATINGS: dict[str, dict[str, Any]] = {
        "honda_civic_2021": {
            "vehicle_description": "2021 Honda Civic 4 DR FWD",
            "overall_rating": "5",
            "overall_front_crash": "4",
            "front_crash_driver": "4",
            "front_crash_passenger": "5",
            "overall_side_crash": "5",
            "side_crash_driver": "5",
            "side_crash_passenger": "5",
            "rollover_rating": "4",
            "rollover_possibility_pct": "13.9%",
            "complaints_count": 2,
            "recalls_count": 1,
            "investigation_count": 0,
        },
        "ford_f-150_2021": {
            "vehicle_description": "2021 Ford F-150 SuperCrew 4WD",
            "overall_rating": "5",
            "overall_front_crash": "4",
            "front_crash_driver": "4",
            "front_crash_passenger": "4",
            "overall_side_crash": "5",
            "side_crash_driver": "5",
            "side_crash_passenger": "5",
            "rollover_rating": "3",
            "rollover_possibility_pct": "21.2%",
            "complaints_count": 3,
            "recalls_count": 2,
            "investigation_count": 1,
        },
        "tesla_model s_2021": {
            "vehicle_description": "2021 Tesla Model S AWD",
            "overall_rating": "5",
            "overall_front_crash": "5",
            "front_crash_driver": "5",
            "front_crash_passenger": "5",
            "overall_side_crash": "5",
            "side_crash_driver": "5",
            "side_crash_passenger": "5",
            "rollover_rating": "5",
            "rollover_possibility_pct": "7.9%",
            "complaints_count": 1,
            "recalls_count": 0,
            "investigation_count": 0,
        },
        "toyota_camry_2023": {
            "vehicle_description": "2023 Toyota Camry 4 DR FWD",
            "overall_rating": "5",
            "overall_front_crash": "5",
            "front_crash_driver": "5",
            "front_crash_passenger": "4",
            "overall_side_crash": "5",
            "side_crash_driver": "5",
            "side_crash_passenger": "5",
            "rollover_rating": "4",
            "rollover_possibility_pct": "14.2%",
            "complaints_count": 0,
            "recalls_count": 1,
            "investigation_count": 0,
        },
    }

    def get_safety_ratings(
        self, make: str, model: str, year: int
    ) -> dict[str, Any] | None:
        key = f"{make.lower()}_{model.lower()}_{year}"
        return self._MOCK_RATINGS.get(key)

    # ── Model Lookup ──────────────────────────────────────────────────────────

    _MOCK_MODELS: dict[str, list[dict[str, Any]]] = {
        "honda": [
            {"make_name": "HONDA", "model_name": "Accord", "make_id": 474, "model_id": 1861},
            {"make_name": "HONDA", "model_name": "Civic", "make_id": 474, "model_id": 1863},
            {"make_name": "HONDA", "model_name": "CR-V", "make_id": 474, "model_id": 1866},
            {"make_name": "HONDA", "model_name": "HR-V", "make_id": 474, "model_id": 14390},
            {"make_name": "HONDA", "model_name": "Odyssey", "make_id": 474, "model_id": 1879},
            {"make_name": "HONDA", "model_name": "Passport", "make_id": 474, "model_id": 1880},
            {"make_name": "HONDA", "model_name": "Pilot", "make_id": 474, "model_id": 1881},
            {"make_name": "HONDA", "model_name": "Ridgeline", "make_id": 474, "model_id": 2696},
        ],
        "toyota": [
            {"make_name": "TOYOTA", "model_name": "4Runner", "make_id": 448, "model_id": 1724},
            {"make_name": "TOYOTA", "model_name": "Camry", "make_id": 448, "model_id": 1735},
            {"make_name": "TOYOTA", "model_name": "Corolla", "make_id": 448, "model_id": 1744},
            {"make_name": "TOYOTA", "model_name": "Highlander", "make_id": 448, "model_id": 1760},
            {"make_name": "TOYOTA", "model_name": "RAV4", "make_id": 448, "model_id": 1791},
            {"make_name": "TOYOTA", "model_name": "Tacoma", "make_id": 448, "model_id": 1808},
            {"make_name": "TOYOTA", "model_name": "Tundra", "make_id": 448, "model_id": 1816},
        ],
        "ford": [
            {"make_name": "FORD", "model_name": "Bronco", "make_id": 460, "model_id": 14581},
            {"make_name": "FORD", "model_name": "Escape", "make_id": 460, "model_id": 1945},
            {"make_name": "FORD", "model_name": "Explorer", "make_id": 460, "model_id": 1948},
            {"make_name": "FORD", "model_name": "F-150", "make_id": 460, "model_id": 1952},
            {"make_name": "FORD", "model_name": "Maverick", "make_id": 460, "model_id": 27091},
            {"make_name": "FORD", "model_name": "Mustang", "make_id": 460, "model_id": 1967},
            {"make_name": "FORD", "model_name": "Ranger", "make_id": 460, "model_id": 1980},
        ],
        "tesla": [
            {"make_name": "TESLA", "model_name": "Model 3", "make_id": 10199, "model_id": 16724},
            {"make_name": "TESLA", "model_name": "Model S", "make_id": 10199, "model_id": 14491},
            {"make_name": "TESLA", "model_name": "Model X", "make_id": 10199, "model_id": 16047},
            {"make_name": "TESLA", "model_name": "Model Y", "make_id": 10199, "model_id": 25332},
            {"make_name": "TESLA", "model_name": "Cybertruck", "make_id": 10199, "model_id": 30050},
        ],
        "chevrolet": [
            {"make_name": "CHEVROLET", "model_name": "Bolt EV", "make_id": 467, "model_id": 22095},
            {"make_name": "CHEVROLET", "model_name": "Colorado", "make_id": 467, "model_id": 2602},
            {"make_name": "CHEVROLET", "model_name": "Equinox", "make_id": 467, "model_id": 2612},
            {"make_name": "CHEVROLET", "model_name": "Silverado 1500", "make_id": 467, "model_id": 2649},
            {"make_name": "CHEVROLET", "model_name": "Tahoe", "make_id": 467, "model_id": 2652},
            {"make_name": "CHEVROLET", "model_name": "Traverse", "make_id": 467, "model_id": 2658},
        ],
        "bmw": [
            {"make_name": "BMW", "model_name": "3 Series", "make_id": 452, "model_id": 1685},
            {"make_name": "BMW", "model_name": "5 Series", "make_id": 452, "model_id": 1687},
            {"make_name": "BMW", "model_name": "X3", "make_id": 452, "model_id": 1714},
            {"make_name": "BMW", "model_name": "X5", "make_id": 452, "model_id": 1717},
            {"make_name": "BMW", "model_name": "iX", "make_id": 452, "model_id": 27570},
        ],
    }

    def get_models_for_make(
        self, make: str, year: int | None = None
    ) -> list[dict[str, Any]]:
        return self._MOCK_MODELS.get(make.lower(), [])
