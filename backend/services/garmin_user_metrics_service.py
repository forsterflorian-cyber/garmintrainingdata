"""
Garmin User Metrics Service.
Fetches user-specific metrics from Garmin (LTHR, FTP, Training Readiness, etc.)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from observability import ErrorCategory, get_logger, log_event, log_exception

LOGGER = get_logger(__name__)


def fetch_garmin_lthr(client: Any) -> Optional[Dict[str, Any]]:
    """
    Fetches Lactate Threshold Heart Rate from Garmin.
    
    Args:
        client: Authenticated Garmin client
        
    Returns:
        Dict with lthr value and metadata, or None if not available
    """
    try:
        result = client.get_lactate_threshold(latest=True)
        
        if not result:
            log_event(
                LOGGER,
                logging.INFO,
                category=ErrorCategory.API,
                event="garmin.lthr_not_available",
                message="LTHR data not available from Garmin.",
            )
            return None
        
        speed_hr = result.get("speed_and_heart_rate", {})
        heart_rate = speed_hr.get("heartRate")
        
        if heart_rate is None:
            log_event(
                LOGGER,
                logging.INFO,
                category=ErrorCategory.API,
                event="garmin.lthr_no_hr",
                message="LTHR response missing heart rate value.",
            )
            return None
        
        lthr_value = int(heart_rate)
        
        # Validate reasonable LTHR range
        if not (100 <= lthr_value <= 220):
            log_event(
                LOGGER,
                logging.WARNING,
                category=ErrorCategory.API,
                event="garmin.lthr_invalid_range",
                message=f"LTHR value {lthr_value} outside reasonable range.",
                lthr=lthr_value,
            )
            return None
        
        calendar_date = speed_hr.get("calendarDate")
        
        log_event(
            LOGGER,
            logging.INFO,
            category=ErrorCategory.API,
            event="garmin.lthr_fetched",
            message=f"Successfully fetched LTHR: {lthr_value} bpm",
            lthr=lthr_value,
            date=calendar_date,
        )
        
        return {
            "lthr": lthr_value,
            "date": calendar_date,
            "speed": speed_hr.get("speed"),
        }
        
    except Exception as exc:
        log_exception(
            LOGGER,
            category=ErrorCategory.API,
            event="garmin.lthr_fetch_failed",
            message="Failed to fetch LTHR from Garmin.",
            exc=exc,
            level=logging.WARNING,
        )
        return None


def fetch_garmin_ftp(client: Any) -> Optional[Dict[str, Any]]:
    """
    Fetches Functional Threshold Power (FTP) from Garmin.
    
    Args:
        client: Authenticated Garmin client
        
    Returns:
        Dict with ftp value and metadata, or None if not available
    """
    try:
        result = client.get_cycling_ftp()
        
        if not result:
            log_event(
                LOGGER,
                logging.INFO,
                category=ErrorCategory.API,
                event="garmin.ftp_not_available",
                message="FTP data not available from Garmin.",
            )
            return None
        
        # Handle both list and dict responses
        if isinstance(result, list):
            if not result:
                return None
            result = result[0]
        
        ftp_value = result.get("functionalThresholdPower")
        
        if ftp_value is None:
            log_event(
                LOGGER,
                logging.INFO,
                category=ErrorCategory.API,
                event="garmin.ftp_no_value",
                message="FTP response missing power value.",
            )
            return None
        
        ftp_value = float(ftp_value)
        
        # Validate reasonable FTP range
        if not (50 <= ftp_value <= 600):
            log_event(
                LOGGER,
                logging.WARNING,
                category=ErrorCategory.API,
                event="garmin.ftp_invalid_range",
                message=f"FTP value {ftp_value} outside reasonable range.",
                ftp=ftp_value,
            )
            return None
        
        calendar_date = result.get("calendarDate")
        
        log_event(
            LOGGER,
            logging.INFO,
            category=ErrorCategory.API,
            event="garmin.ftp_fetched",
            message=f"Successfully fetched FTP: {ftp_value}W",
            ftp=ftp_value,
            date=calendar_date,
        )
        
        return {
            "ftp": ftp_value,
            "date": calendar_date,
        }
        
    except Exception as exc:
        log_exception(
            LOGGER,
            category=ErrorCategory.API,
            event="garmin.ftp_fetch_failed",
            message="Failed to fetch FTP from Garmin.",
            exc=exc,
            level=logging.WARNING,
        )
        return None


def fetch_garmin_training_readiness(client: Any, cdate: str) -> Optional[Dict[str, Any]]:
    """
    Fetches Training Readiness score from Garmin.
    
    Args:
        client: Authenticated Garmin client
        cdate: Date in YYYY-MM-DD format
        
    Returns:
        Dict with training readiness data, or None if not available
    """
    try:
        result = client.get_morning_training_readiness(cdate)
        
        if not result:
            return None
        
        score = result.get("score")
        
        if score is None:
            return None
        
        log_event(
            LOGGER,
            logging.INFO,
            category=ErrorCategory.API,
            event="garmin.training_readiness_fetched",
            message=f"Training readiness: {score}",
            score=score,
            date=cdate,
        )
        
        return {
            "score": int(score),
            "date": cdate,
            "raw": result,
        }
        
    except Exception as exc:
        log_exception(
            LOGGER,
            category=ErrorCategory.API,
            event="garmin.training_readiness_fetch_failed",
            message="Failed to fetch training readiness from Garmin.",
            exc=exc,
            level=logging.WARNING,
        )
        return None


def fetch_garmin_training_status(client: Any, cdate: str) -> Optional[Dict[str, Any]]:
    """
    Fetches Training Status from Garmin.
    
    Args:
        client: Authenticated Garmin client
        cdate: Date in YYYY-MM-DD format
        
    Returns:
        Dict with training status data, or None if not available
    """
    try:
        result = client.get_training_status(cdate)
        
        if not result:
            return None
        
        # Training status is typically a string like "PRODUCTIVE", "MAINTAINING", etc.
        status_key = result.get("userTrainingStatusKey")
        
        if not status_key:
            return None
        
        log_event(
            LOGGER,
            logging.INFO,
            category=ErrorCategory.API,
            event="garmin.training_status_fetched",
            message=f"Training status: {status_key}",
            status=status_key,
            date=cdate,
        )
        
        return {
            "status": status_key,
            "date": cdate,
            "raw": result,
        }
        
    except Exception as exc:
        log_exception(
            LOGGER,
            category=ErrorCategory.API,
            event="garmin.training_status_fetch_failed",
            message="Failed to fetch training status from Garmin.",
            exc=exc,
            level=logging.WARNING,
        )
        return None


def sync_garmin_user_metrics(
    client: Any,
    supabase_client: Any,
    user_id: str,
) -> Dict[str, Any]:
    """
    Syncs user-specific metrics from Garmin to the database.
    
    Args:
        client: Authenticated Garmin client
        supabase_client: Supabase client
        user_id: User ID
        
    Returns:
        Dict with sync results
    """
    from datetime import date
    
    results = {
        "lthr_synced": False,
        "ftp_synced": False,
        "training_readiness_synced": False,
        "training_status_synced": False,
        "lthr": None,
        "ftp": None,
        "training_readiness": None,
        "training_status": None,
    }
    
    now_iso = datetime.now(timezone.utc).isoformat()
    today = date.today().isoformat()
    
    # Fetch current profile to check existing values
    try:
        profile_response = (
            supabase_client.table("user_profiles")
            .select("lthr, lthr_source, ftp, ftp_source")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        existing_profile = profile_response.data[0] if profile_response.data else {}
    except Exception:
        existing_profile = {}
    
    # Fetch LTHR from Garmin
    lthr_data = fetch_garmin_lthr(client)
    if lthr_data and lthr_data.get("lthr"):
        lthr_value = lthr_data["lthr"]
        # Only update if not manually set or if Garmin value is newer
        existing_source = existing_profile.get("lthr_source")
        if existing_source != "manual":
            results["lthr"] = lthr_value
            results["lthr_synced"] = True
    
    # Fetch FTP from Garmin
    ftp_data = fetch_garmin_ftp(client)
    if ftp_data and ftp_data.get("ftp"):
        ftp_value = ftp_data["ftp"]
        # Only update if not manually set
        existing_source = existing_profile.get("ftp_source")
        if existing_source != "manual":
            results["ftp"] = ftp_value
            results["ftp_synced"] = True
    
    # Fetch Training Readiness
    readiness_data = fetch_garmin_training_readiness(client, today)
    if readiness_data and readiness_data.get("score") is not None:
        results["training_readiness"] = readiness_data["score"]
        results["training_readiness_synced"] = True
    
    # Fetch Training Status
    status_data = fetch_garmin_training_status(client, today)
    if status_data and status_data.get("status"):
        results["training_status"] = status_data["status"]
        results["training_status_synced"] = True
    
    # Update database
    update_fields = {}
    
    if results["lthr_synced"]:
        update_fields["lthr"] = results["lthr"]
        update_fields["lthr_source"] = "garmin"
        update_fields["lthr_synced_at"] = now_iso
    
    if results["ftp_synced"]:
        update_fields["ftp"] = results["ftp"]
        update_fields["ftp_source"] = "garmin"
        update_fields["ftp_synced_at"] = now_iso
    
    if results["training_readiness_synced"]:
        update_fields["garmin_training_readiness"] = results["training_readiness"]
    
    if results["training_status_synced"]:
        update_fields["garmin_training_status"] = results["training_status"]
    
    if update_fields:
        update_fields["garmin_metrics_synced_at"] = now_iso
        
        try:
            # Check if profile exists
            existing = (
                supabase_client.table("user_profiles")
                .select("user_id")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            
            if existing.data:
                # Update existing profile
                supabase_client.table("user_profiles").update(update_fields).eq("user_id", user_id).execute()
            else:
                # Insert new profile
                update_fields["user_id"] = user_id
                supabase_client.table("user_profiles").insert(update_fields).execute()
            
            log_event(
                LOGGER,
                logging.INFO,
                category=ErrorCategory.DB,
                event="garmin.metrics_synced",
                message="Garmin user metrics synced to database.",
                user_id=user_id,
                lthr=results.get("lthr"),
                ftp=results.get("ftp"),
                training_readiness=results.get("training_readiness"),
                training_status=results.get("training_status"),
            )
            
        except Exception as exc:
            log_exception(
                LOGGER,
                category=ErrorCategory.DB,
                event="garmin.metrics_sync_failed",
                message="Failed to sync Garmin metrics to database.",
                exc=exc,
                user_id=user_id,
            )
    
    return results