# Copyright (c) 2026. NHTSA Vehicle Safety API client.
# Free, no-auth government APIs for vehicle safety data.

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

# ── API base URLs ─────────────────────────────────────────────────────────────

VPIC_BASE = "https://vpic.nhtsa.dot.gov/api/vehicles"
NHTSA_BASE = "https://api.nhtsa.gov"

_TIMEOUT = 15  # seconds


class NHTSAService:
    """Live NHTSA API client — all endpoints are free and require no API key."""

    # ── VIN Decode ────────────────────────────────────────────────────────────

    def decode_vin(self, vin: str) -> dict[str, Any]:
        """Decode a VIN and return vehicle specifications."""
        url = f"{VPIC_BASE}/DecodeVinValues/{vin}?format=json"
        data = self._get(url)

        results = data.get("Results", [])
        if not results:
            return {"error": "No results returned for this VIN."}

        raw = results[0]

        # Extract the useful fields (vPIC returns ~140 fields, most empty)
        decoded = {
            "vin": vin.upper(),
            "make": raw.get("Make", ""),
            "model": raw.get("Model", ""),
            "year": raw.get("ModelYear", ""),
            "trim": raw.get("Trim", ""),
            "body_class": raw.get("BodyClass", ""),
            "vehicle_type": raw.get("VehicleType", ""),
            "doors": raw.get("Doors", ""),
            "drive_type": raw.get("DriveType", ""),
            "fuel_type_primary": raw.get("FuelTypePrimary", ""),
            "engine_cylinders": raw.get("EngineCylinders", ""),
            "displacement_l": raw.get("DisplacementL", ""),
            "engine_hp": raw.get("EngineHP", ""),
            "transmission": raw.get("TransmissionStyle", ""),
            "plant_city": raw.get("PlantCity", ""),
            "plant_country": raw.get("PlantCountry", ""),
            "manufacturer": raw.get("Manufacturer", ""),
            "gvwr": raw.get("GVWR", ""),
            "electrification": raw.get("ElectrificationLevel", ""),
            "abs": raw.get("ABS", ""),
            "tpms": raw.get("TPMS", ""),
            "esc": raw.get("ESC", ""),
            "forward_collision_warning": raw.get("ForwardCollisionWarning", ""),
            "lane_departure_warning": raw.get("LaneDepartureWarning", ""),
            "adaptive_cruise_control": raw.get("AdaptiveCruiseControl", ""),
            "blind_spot_warning": raw.get("BlindSpotMon", ""),
            "error_code": raw.get("ErrorCode", ""),
            "error_text": raw.get("ErrorText", ""),
        }

        # Strip empty/None values for cleaner output
        return {k: v for k, v in decoded.items() if v}

    # ── Recalls ───────────────────────────────────────────────────────────────

    def get_recalls(
        self, make: str, model: str, year: int
    ) -> list[dict[str, Any]]:
        """Get safety recalls for a specific make/model/year."""
        url = (
            f"{NHTSA_BASE}/recalls/recallsByVehicle"
            f"?make={requests.utils.quote(make)}"
            f"&model={requests.utils.quote(model)}"
            f"&modelYear={year}"
        )
        data = self._get(url)

        recalls = []
        for r in data.get("results", []):
            recalls.append({
                "nhtsa_campaign_number": r.get("NHTSACampaignNumber", ""),
                "component": r.get("Component", ""),
                "summary": r.get("Summary", ""),
                "consequence": r.get("Consequence", ""),
                "remedy": r.get("Remedy", ""),
                "report_date": r.get("ReportReceivedDate", ""),
                "manufacturer": r.get("Manufacturer", ""),
            })
        return recalls

    # ── Complaints ────────────────────────────────────────────────────────────

    def get_complaints(
        self, make: str, model: str, year: int
    ) -> list[dict[str, Any]]:
        """Get consumer complaints for a specific make/model/year."""
        url = (
            f"{NHTSA_BASE}/complaints/complaintsByVehicle"
            f"?make={requests.utils.quote(make)}"
            f"&model={requests.utils.quote(model)}"
            f"&modelYear={year}"
        )
        data = self._get(url)

        complaints = []
        for c in data.get("results", []):
            complaints.append({
                "odi_number": c.get("odiNumber", ""),
                "component": c.get("components", ""),
                "summary": c.get("summary", ""),
                "crash": c.get("crash", False),
                "fire": c.get("fire", False),
                "injuries": c.get("injuries", 0),
                "deaths": c.get("deaths", 0),
                "date_filed": c.get("dateOfIncident", ""),
            })
        return complaints

    # ── Safety Ratings ────────────────────────────────────────────────────────

    def get_safety_ratings(
        self, make: str, model: str, year: int
    ) -> dict[str, Any] | None:
        """Get NCAP crash test safety ratings for a make/model/year.

        Returns None if no rating data exists (not all vehicles are tested).
        """
        # Step 1: get vehicle ID from the ratings API
        url = (
            f"{NHTSA_BASE}/SafetyRatings/modelyear/{year}"
            f"/make/{requests.utils.quote(make)}"
            f"/model/{requests.utils.quote(model)}"
            f"?format=json"
        )
        data = self._get(url)

        results = data.get("Results", [])
        if not results:
            return None

        # Step 2: fetch detailed ratings for the first matching vehicle ID
        vehicle_id = results[0].get("VehicleId")
        if not vehicle_id:
            return None

        detail_url = f"{NHTSA_BASE}/SafetyRatings/VehicleId/{vehicle_id}?format=json"
        detail_data = self._get(detail_url)

        detail_results = detail_data.get("Results", [])
        if not detail_results:
            return None

        r = detail_results[0]
        return {
            "vehicle_description": r.get("VehicleDescription", ""),
            "overall_rating": r.get("OverallRating", "Not Rated"),
            "overall_front_crash": r.get("OverallFrontCrashRating", "Not Rated"),
            "front_crash_driver": r.get("FrontCrashDriversideRating", "Not Rated"),
            "front_crash_passenger": r.get("FrontCrashPassengersideRating", "Not Rated"),
            "overall_side_crash": r.get("OverallSideCrashRating", "Not Rated"),
            "side_crash_driver": r.get("SideCrashDriversideRating", "Not Rated"),
            "side_crash_passenger": r.get("SideCrashPassengersideRating", "Not Rated"),
            "rollover_rating": r.get("RolloverRating", "Not Rated"),
            "rollover_possibility_pct": r.get("RolloverPossibility", ""),
            "complaints_count": r.get("ComplaintsCount", 0),
            "recalls_count": r.get("RecallsCount", 0),
            "investigation_count": r.get("InvestigationCount", 0),
        }

    # ── Model Lookup ──────────────────────────────────────────────────────────

    def get_models_for_make(
        self, make: str, year: int | None = None
    ) -> list[dict[str, Any]]:
        """List models available for a make, optionally filtered by year."""
        if year:
            url = (
                f"{VPIC_BASE}/GetModelsForMakeYear"
                f"/make/{requests.utils.quote(make)}"
                f"/modelyear/{year}?format=json"
            )
        else:
            url = f"{VPIC_BASE}/GetModelsForMake/{requests.utils.quote(make)}?format=json"

        data = self._get(url)

        models = []
        for m in data.get("Results", []):
            models.append({
                "make_name": m.get("Make_Name", ""),
                "model_name": m.get("Model_Name", ""),
                "make_id": m.get("Make_ID", ""),
                "model_id": m.get("Model_ID", ""),
            })
        return models

    # ── HTTP helper ───────────────────────────────────────────────────────────

    def _get(self, url: str) -> dict[str, Any]:
        """Make a GET request with timeout and error handling."""
        try:
            resp = requests.get(url, timeout=_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            logger.error("NHTSA API timeout: %s", url)
            raise RuntimeError("NHTSA API request timed out. Please try again.")
        except requests.exceptions.HTTPError as e:
            logger.error("NHTSA API HTTP error: %s — %s", url, e)
            raise RuntimeError(f"NHTSA API returned an error: {e.response.status_code}")
        except requests.exceptions.RequestException as e:
            logger.error("NHTSA API request failed: %s — %s", url, e)
            raise RuntimeError("Unable to reach NHTSA API. Check your network connection.")
