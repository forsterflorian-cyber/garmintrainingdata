"""
Einfache Metriken-Schätzung aus historischen Daten.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from observability import get_logger

LOGGER = get_logger(__name__)


def estimate_user_metrics(activities: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Schätzt User-Metriken aus historischen Aktivitäten.
    
    Args:
        activities: Liste von Aktivitäten
        
    Returns:
        Dict mit geschätzten Metriken
    """
    if not activities:
        return {}
    
    # Sammle alle verfügbaren Daten
    training_loads = []
    durations = []
    distances = []
    avg_hrs = []
    avg_speeds = []
    
    for activity in activities:
        # Training Load
        if activity.get("training_load"):
            try:
                load = float(activity["training_load"])
                if load > 0:
                    training_loads.append(load)
            except (ValueError, TypeError):
                pass
        
        # Duration
        if activity.get("duration_min"):
            try:
                duration = float(activity["duration_min"])
                if duration > 0:
                    durations.append(duration)
            except (ValueError, TypeError):
                pass
        
        # Distance
        if activity.get("distance_km"):
            try:
                distance = float(activity["distance_km"])
                if distance > 0:
                    distances.append(distance)
            except (ValueError, TypeError):
                pass
        
        # Avg HR
        if activity.get("avg_hr"):
            try:
                hr = int(activity["avg_hr"])
                if 50 < hr < 220:
                    avg_hrs.append(hr)
            except (ValueError, TypeError):
                pass
        
        # Avg Speed
        if activity.get("avg_speed_kmh"):
            try:
                speed = float(activity["avg_speed_kmh"])
                if speed > 0:
                    avg_speeds.append(speed)
            except (ValueError, TypeError):
                pass
    
    result = {}
    
    # Schätze FTP basierend auf Training Load
    if training_loads and durations:
        # Finde höchste Load pro Minute
        max_load_per_minute = 0
        for i, load in enumerate(training_loads):
            if i < len(durations):
                load_per_minute = load / durations[i]
                max_load_per_minute = max(max_load_per_minute, load_per_minute)
        
        if max_load_per_minute > 0:
            # Annahme: ~1 Load/Minute ≈ ~65 Watt
            estimated_ftp = max_load_per_minute * 65 * 0.9
            if 50 < estimated_ftp < 2000:
                result["ftp"] = round(estimated_ftp, 1)
    
    # Schätze Critical Pace basierend auf Speed
    if avg_speeds:
        max_speed = max(avg_speeds)
        if max_speed > 0:
            # Pace = 60 / Speed
            estimated_pace = 60.0 / max_speed
            if 2.0 < estimated_pace < 15.0:
                result["critical_pace"] = round(estimated_pace, 2)
    
    # Schätze LTHR basierend auf HR
    if avg_hrs:
        # Verwende höchste HR als Proxy für LTHR
        max_hr = max(avg_hrs)
        if max_hr > 100:
            # LTHR ≈ 85% von Max HR
            estimated_lthr = int(max_hr * 0.85)
            if 100 < estimated_lthr < 220:
                result["lthr"] = estimated_lthr
    
    return result