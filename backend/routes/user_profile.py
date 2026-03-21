"""
User Profile API Routes.
CRUD Endpunkte für User-Profile und personalisierte Metriken.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, Optional

from flask import Blueprint, jsonify, request

from auth_supabase import require_user
from backend.validators import InputValidator
from observability import ErrorCategory, ServiceError, get_logger, log_event, log_exception

LOGGER = get_logger(__name__)


def create_user_profile_blueprint(supabase_client: Any) -> Blueprint:
    """Erstellt Blueprint für User-Profile Routes."""
    
    bp = Blueprint("user_profile", __name__, url_prefix="/api/user-profile")
    
    @bp.get("/")
    @require_user
    def get_user_profile():
        """Lädt das User-Profil."""
        try:
            response = (
                supabase_client.table("user_profiles")
                .select("*")
                .eq("user_id", request.user_id)
                .limit(1)
                .execute()
            )
            
            if not response.data:
                return jsonify({"profile": None})
            
            profile = response.data[0]
            
            # Sensible Daten nicht zurückgeben
            profile.pop("user_id", None)
            
            return jsonify({"profile": profile})
            
        except Exception as exc:
            log_exception(
                LOGGER,
                category=ErrorCategory.DB,
                event="user_profile.fetch_failed",
                message="Failed to fetch user profile.",
                exc=exc,
                user_id=request.user_id,
            )
            raise ServiceError(
                "Failed to load user profile.",
                status_code=500,
                category=ErrorCategory.DB,
                event="user_profile.fetch_failed",
            ) from exc
    
    @bp.post("/")
    @require_user
    def create_or_update_user_profile():
        """Erstellt oder aktualisiert das User-Profil."""
        data = request.get_json(silent=True) or {}
        
        # Validierung
        try:
            validated_data = _validate_profile_data(data)
        except ValueError as exc:
            raise ServiceError(
                str(exc),
                status_code=400,
                category=ErrorCategory.VALIDATION,
                event="user_profile.validation_failed",
            ) from exc
        
        try:
            # Prüfe ob Profil existiert
            existing = (
                supabase_client.table("user_profiles")
                .select("user_id")
                .eq("user_id", request.user_id)
                .limit(1)
                .execute()
            )
            
            if existing.data:
                # Update
                response = (
                    supabase_client.table("user_profiles")
                    .update(validated_data)
                    .eq("user_id", request.user_id)
                    .execute()
                )
                log_event(
                    LOGGER,
                    logging.INFO,
                    category=ErrorCategory.DB,
                    event="user_profile.updated",
                    message="User profile updated.",
                    user_id=request.user_id,
                )
            else:
                # Insert
                validated_data["user_id"] = request.user_id
                response = (
                    supabase_client.table("user_profiles")
                    .insert(validated_data)
                    .execute()
                )
                log_event(
                    LOGGER,
                    logging.INFO,
                    category=ErrorCategory.DB,
                    event="user_profile.created",
                    message="User profile created.",
                    user_id=request.user_id,
                )
            
            profile = response.data[0] if response.data else {}
            profile.pop("user_id", None)
            
            return jsonify({"profile": profile, "status": "success"})
            
        except Exception as exc:
            log_exception(
                LOGGER,
                category=ErrorCategory.DB,
                event="user_profile.upsert_failed",
                message="Failed to save user profile.",
                exc=exc,
                user_id=request.user_id,
            )
            raise ServiceError(
                "Failed to save user profile.",
                status_code=500,
                category=ErrorCategory.DB,
                event="user_profile.upsert_failed",
            ) from exc
    
    @bp.delete("/")
    @require_user
    def delete_user_profile():
        """Löscht das User-Profil."""
        try:
            (
                supabase_client.table("user_profiles")
                .delete()
                .eq("user_id", request.user_id)
                .execute()
            )
            
            log_event(
                LOGGER,
                logging.INFO,
                category=ErrorCategory.DB,
                event="user_profile.deleted",
                message="User profile deleted.",
                user_id=request.user_id,
            )
            
            return jsonify({"status": "deleted"})
            
        except Exception as exc:
            log_exception(
                LOGGER,
                category=ErrorCategory.DB,
                event="user_profile.delete_failed",
                message="Failed to delete user profile.",
                exc=exc,
                user_id=request.user_id,
            )
            raise ServiceError(
                "Failed to delete user profile.",
                status_code=500,
                category=ErrorCategory.DB,
                event="user_profile.delete_failed",
            ) from exc
    
    @bp.post("/estimate-metrics")
    @require_user
    def estimate_metrics():
        """Schätzt Metriken basierend auf historischen Daten."""
        try:
            # Lade Training-Days
            response = (
                supabase_client.table("training_days")
                .select("data")
                .eq("user_id", request.user_id)
                .order("date", desc=True)
                .limit(180)
                .execute()
            )
            
            activities = []
            for row in response.data or []:
                data = row.get("data", {})
                for activity in data.get("activities", []):
                    if isinstance(activity, dict):
                        activities.append(activity)
            
            if not activities:
                return jsonify({
                    "estimated": {},
                    "message": "No activities found for estimation."
                })
            
            # Einfache Schätzlogik
            from backend.services.estimation_service import estimate_user_metrics
            
            estimated = estimate_user_metrics(activities)
            
            return jsonify({
                "estimated": estimated,
                "activities_analyzed": len(activities),
            })
            
        except Exception as exc:
            log_exception(
                LOGGER,
                category=ErrorCategory.API,
                event="user_profile.estimate_failed",
                message="Failed to estimate metrics.",
                exc=exc,
                user_id=request.user_id,
            )
            raise ServiceError(
                "Failed to estimate metrics.",
                status_code=500,
                category=ErrorCategory.API,
                event="user_profile.estimate_failed",
            ) from exc
    
    return bp


def _validate_profile_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validiert User-Profil Daten."""
    
    validated = {}
    
    # Basis-Daten
    if "age" in data:
        age = data["age"]
        if age is not None:
            if not isinstance(age, int) or age < 1 or age > 120:
                raise ValueError("Age must be between 1 and 120")
            validated["age"] = age
    
    if "weight_kg" in data:
        weight = data["weight_kg"]
        if weight is not None:
            if not isinstance(weight, (int, float)) or weight < 20 or weight > 500:
                raise ValueError("Weight must be between 20 and 500 kg")
            validated["weight_kg"] = float(weight)
    
    if "height_cm" in data:
        height = data["height_cm"]
        if height is not None:
            if not isinstance(height, (int, float)) or height < 50 or height > 300:
                raise ValueError("Height must be between 50 and 300 cm")
            validated["height_cm"] = float(height)
    
    if "gender" in data:
        gender = data["gender"]
        if gender is not None:
            if gender not in ("male", "female", "other"):
                raise ValueError("Gender must be male, female, or other")
            validated["gender"] = gender
    
    # Heart Rate
    if "max_hr" in data:
        max_hr = data["max_hr"]
        if max_hr is not None:
            if not isinstance(max_hr, int) or max_hr < 100 or max_hr > 250:
                raise ValueError("Max HR must be between 100 and 250")
            validated["max_hr"] = max_hr
    
    if "resting_hr" in data:
        resting_hr = data["resting_hr"]
        if resting_hr is not None:
            if not isinstance(resting_hr, int) or resting_hr < 30 or resting_hr > 120:
                raise ValueError("Resting HR must be between 30 and 120")
            validated["resting_hr"] = resting_hr
    
    if "lthr" in data:
        lthr = data["lthr"]
        if lthr is not None:
            if not isinstance(lthr, int) or lthr < 100 or lthr > 250:
                raise ValueError("LTHR must be between 100 and 250")
            validated["lthr"] = lthr
    
    # Power
    if "ftp" in data:
        ftp = data["ftp"]
        if ftp is not None:
            if not isinstance(ftp, (int, float)) or ftp < 50 or ftp > 2000:
                raise ValueError("FTP must be between 50 and 2000 watt")
            validated["ftp"] = float(ftp)
    
    if "critical_power" in data:
        cp = data["critical_power"]
        if cp is not None:
            if not isinstance(cp, (int, float)) or cp < 50 or cp > 2000:
                raise ValueError("Critical Power must be between 50 and 2000 watt")
            validated["critical_power"] = float(cp)
    
    # Pace
    if "critical_pace" in data:
        pace = data["critical_pace"]
        if pace is not None:
            if not isinstance(pace, (int, float)) or pace < 2.0 or pace > 20.0:
                raise ValueError("Critical Pace must be between 2.0 and 20.0 min/km")
            validated["critical_pace"] = float(pace)
    
    if "vdot" in data:
        vdot = data["vdot"]
        if vdot is not None:
            if not isinstance(vdot, (int, float)) or vdot < 20 or vdot > 100:
                raise ValueError("VDOT must be between 20 and 100")
            validated["vdot"] = float(vdot)
    
    # Training Preferences
    if "sport_focus" in data:
        sport_focus = data["sport_focus"]
        if sport_focus is not None:
            if sport_focus not in ("run", "bike", "strength", "hybrid"):
                raise ValueError("Sport focus must be run, bike, strength, or hybrid")
            validated["sport_focus"] = sport_focus
    
    if "weekly_volume_target" in data:
        volume = data["weekly_volume_target"]
        if volume is not None:
            if not isinstance(volume, int) or volume < 0 or volume > 10000:
                raise ValueError("Weekly volume target must be between 0 and 10000 minutes")
            validated["weekly_volume_target"] = volume
    
    if "intensity_preference" in data:
        intensity = data["intensity_preference"]
        if intensity is not None:
            if intensity not in ("low", "moderate", "high"):
                raise ValueError("Intensity preference must be low, moderate, or high")
            validated["intensity_preference"] = intensity
    
    # Goals
    if "race_date" in data:
        race_date = data["race_date"]
        if race_date is not None:
            try:
                if isinstance(race_date, str):
                    date.fromisoformat(race_date)
                validated["race_date"] = race_date
            except ValueError:
                raise ValueError("Race date must be in YYYY-MM-DD format")
    
    if "race_distance" in data:
        validated["race_distance"] = data.get("race_distance")
    
    if "race_goal_time" in data:
        validated["race_goal_time"] = data.get("race_goal_time")
    
    return validated