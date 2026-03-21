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
    
    # Debug-Ausgabe
    LOGGER.info(f"Estimation: {len(training_loads)} loads, {len(durations)} durations, {len(avg_speeds)} speeds, {len(avg_hrs)} HRs")
    
    # Schätze FTP basierend auf Training Load
    if training_loads:
        # Verwende höchsten Training Load als Basis
        max_load = max(training_loads)
        if max_load > 0:
            # Annahme: ~1 Load ≈ ~0.8 Watt (konservativ)
            estimated_ftp = max_load * 0.8
            if 50 < estimated_ftp < 2000:
                result["ftp"] = round(estimated_ftp, 1)
                LOGGER.info(f"Estimated FTP: {result['ftp']}W from max load {max_load}")
    
    # Schätze Critical Pace basierend auf Speed
    if avg_speeds:
        max_speed = max(avg_speeds)
        if max_speed > 5:  # Mindestens 5 km/h
            # Pace = 60 / Speed
            estimated_pace = 60.0 / max_speed
            if 2.0 < estimated_pace < 15.0:
                result["critical_pace"] = round(estimated_pace, 2)
                LOGGER.info(f"Estimated Critical Pace: {result['critical_pace']} min/km from speed {max_speed} km/h")
    
    # LTHR NICHT aus Aktivitäts-Daten schätzen!
    # LTHR sollte IMMER aus User-Profil max_hr berechnet werden (85-90% von max_hr)
    # Dies ist eine kritische Metrik, die nicht aus Durchschnittswerten geschätzt werden sollte
    #
    # Grund: Die höchste durchschnittliche HR einer Aktivität ist NICHT die maximale HR des Users!
    # Beispiel: Eine Recovery-Run mit Avg HR 87 bpm ergibt LTHR = 78 bpm (falsch!)
    # Korrekt: LTHR = max_hr * 0.85 (aus User-Profil, z.B. 185 * 0.85 = 157 bpm)
    #
    # Siehe hr_analysis.py für korrekte LTHR-Berechnung basierend auf User-Profil
    
    return result
