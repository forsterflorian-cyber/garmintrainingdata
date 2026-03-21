"""
Pace-Analysis für Running.
Berechnet Critical Pace, Pace-Zonen und Training Impulse.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np

from observability import get_logger

LOGGER = get_logger(__name__)


@dataclass
class PaceMetrics:
    """Pace-basierte Trainings-Metriken für Running."""
    
    # Critical Pace (min/km)
    critical_pace: Optional[float] = None
    
    # Durchschnittliche Pace
    avg_pace: Optional[float] = None
    
    # Beste Pace
    best_pace: Optional[float] = None
    
    # Pace Variability (CV)
    pace_variability: Optional[float] = None
    
    # Training Impulse
    trimp: Optional[float] = None
    
    # Pace Zone Distribution
    zone_distribution: Optional[Dict[str, float]] = None
    
    # Running Effectiveness (Power/Pace, wenn Power verfügbar)
    running_effectiveness: Optional[float] = None
    
    # Pace pro Kilometer
    splits: Optional[List[Dict[str, float]]] = None


class PaceAnalyzer:
    """Analysiert Pace-Daten für Running."""
    
    # Pace Zones basierend auf Critical Pace
    # Verhältnis: aktuelle_pace / critical_pace
    ZONES = {
        "Z1: Recovery": (1.20, float('inf')),   # 120%+ von CP
        "Z2: Easy": (1.10, 1.20),               # 110-120% von CP
        "Z3: Moderate": (1.00, 1.10),           # 100-110% von CP
        "Z4: Threshold": (0.95, 1.00),          # 95-100% von CP
        "Z5: VO2max": (0.85, 0.95),             # 85-95% von CP
        "Z6: Anaerobic": (0.00, 0.85),          # < 85% von CP
    }
    
    def __init__(self, critical_pace: float):
        """
        Initialisiert PaceAnalyzer mit Critical Pace.
        
        Args:
            critical_pace: Critical Pace in min/km (z.B. 4.5 für 4:30/km)
        """
        if critical_pace <= 0:
            raise ValueError("Critical pace must be positive")
        self.critical_pace = critical_pace
    
    def pace_to_speed(self, pace_min_per_km: float) -> float:
        """
        Konvertiert Pace (min/km) zu Geschwindigkeit (km/h).
        
        Args:
            pace_min_per_km: Pace in Minuten pro Kilometer
            
        Returns:
            Geschwindigkeit in km/h
        """
        if pace_min_per_km <= 0:
            return 0.0
        return 60.0 / pace_min_per_km
    
    def speed_to_pace(self, speed_kmh: float) -> float:
        """
        Konvertiert Geschwindigkeit (km/h) zu Pace (min/km).
        
        Args:
            speed_kmh: Geschwindigkeit in km/h
            
        Returns:
            Pace in Minuten pro Kilometer
        """
        if speed_kmh <= 0:
            return float('inf')
        return 60.0 / speed_kmh
    
    def determine_pace_zone(self, current_pace: float) -> str:
        """
        Bestimmt Pace-Zone basierend auf Critical Pace.
        
        Args:
            current_pace: Aktuelle Pace in min/km
            
        Returns:
            Zone-String (z.B. "Z4: Threshold")
        """
        if current_pace <= 0 or self.critical_pace <= 0:
            return "Z1: Recovery"
        
        # Verhältnis: langsamere Pace = höherer Wert
        ratio = current_pace / self.critical_pace
        
        for zone_name, (min_ratio, max_ratio) in self.ZONES.items():
            if min_ratio <= ratio < max_ratio:
                return zone_name
        
        return "Z6: Anaerobic"
    
    def analyze_zone_distribution(self, pace_readings: List[float]) -> Dict[str, float]:
        """
        Analysiert die Verteilung der Pace über die Zonen.
        
        Args:
            pace_readings: Liste der Pace-Werte (min/km)
            
        Returns:
            Dict mit Zone-Name und Prozent-Anteil
        """
        if not pace_readings:
            return {zone: 0.0 for zone in self.ZONES}
        
        zone_counts = {zone: 0 for zone in self.ZONES}
        
        for pace in pace_readings:
            if pace > 0:  # Ungültige Paces ignorieren
                zone = self.determine_pace_zone(pace)
                zone_counts[zone] += 1
        
        total = len([p for p in pace_readings if p > 0])
        if total == 0:
            return {zone: 0.0 for zone in self.ZONES}
        
        return {zone: round((count / total) * 100, 1)
                for zone, count in zone_counts.items()}
    
    def calculate_trimp(self, duration_minutes: int, avg_hr: int,
                        max_hr: int, resting_hr: int = 60,
                        is_female: bool = False) -> float:
        """
        Berechnet Training Impulse (TRIMP).
        
        TRIMP = duration * hr_reserve * k * exp(k * hr_reserve)
        
        Args:
            duration_minutes: Dauer in Minuten
            avg_hr: Durchschnittliche Herzfrequenz
            max_hr: Maximale Herzfrequenz
            resting_hr: Ruheherzfrequenz
            is_female: Geschlecht (für differenten Faktor)
            
        Returns:
            Training Impulse Score
        """
        if max_hr <= resting_hr or avg_hr <= resting_hr:
            return 0.0
        
        # Herzfrequenz-Reserve
        hr_reserve = (avg_hr - resting_hr) / (max_hr - resting_hr)
        hr_reserve = max(0.0, min(1.0, hr_reserve))
        
        # Geschlechtsspezifischer Faktor
        if is_female:
            k = 1.67
        else:
            k = 1.92
        
        # TRIMP-Berechnung
        trimp = duration_minutes * hr_reserve * k * np.exp(k * hr_reserve)
        
        return round(trimp, 1)
    
    def calculate_pace_variability(self, pace_readings: List[float]) -> float:
        """
        Berechnet Pace-Variabilität (Coefficient of Variation).
        
        Args:
            pace_readings: Liste der Pace-Werte
            
        Returns:
            CV der Pace (0.0 = perfekt gleichmäßig)
        """
        if not pace_readings or len(pace_readings) < 2:
            return 0.0
        
        valid_paces = [p for p in pace_readings if p > 0]
        if len(valid_paces) < 2:
            return 0.0
        
        mean_pace = np.mean(valid_paces)
        std_pace = np.std(valid_paces)
        
        if mean_pace == 0:
            return 0.0
        
        return round(std_pace / mean_pace, 3)
    
    def calculate_splits(self, pace_readings: List[float],
                         distance_km: float) -> List[Dict[str, float]]:
        """
        Berechnet Splits pro Kilometer.
        
        Args:
            pace_readings: Liste der Pace-Werte (min/km)
            distance_km: Gesamtstrecke in km
            
        Returns:
            Liste von Splits mit km, pace, zone
        """
        if not pace_readings or distance_km <= 0:
            return []
        
        splits = []
        readings_per_km = len(pace_readings) / distance_km
        
        for km in range(1, int(distance_km) + 1):
            start_idx = int((km - 1) * readings_per_km)
            end_idx = int(km * readings_per_km)
            
            if start_idx >= len(pace_readings):
                break
            
            km_paces = pace_readings[start_idx:end_idx]
            valid_paces = [p for p in km_paces if p > 0]
            
            if valid_paces:
                avg_pace = float(np.mean(valid_paces))
                zone = self.determine_pace_zone(avg_pace)
                splits.append({
                    "km": km,
                    "pace": round(avg_pace, 2),
                    "zone": zone,
                })
        
        return splits
    
    def analyze_activity(self, pace_readings: List[float],
                         duration_minutes: int,
                         distance_km: float,
                         avg_hr: Optional[int] = None,
                         max_hr: Optional[int] = None,
                         resting_hr: int = 60,
                         is_female: bool = False) -> PaceMetrics:
        """
        Führt vollständige Pace-Analyse einer Aktivität durch.
        
        Args:
            pace_readings: Liste der Pace-Werte (min/km)
            duration_minutes: Dauer in Minuten
            distance_km: Strecke in km
            avg_hr: Durchschnittliche Herzfrequenz
            max_hr: Maximale Herzfrequenz
            resting_hr: Ruheherzfrequenz
            is_female: Geschlecht
            
        Returns:
            PaceMetrics mit allen berechneten Werten
        """
        if not pace_readings:
            return PaceMetrics(critical_pace=self.critical_pace)
        
        # Gültige Paces filtern
        valid_paces = [p for p in pace_readings if p > 0]
        
        if not valid_paces:
            return PaceMetrics(critical_pace=self.critical_pace)
        
        # Basis-Metriken
        avg_pace = float(np.mean(valid_paces))
        best_pace = float(np.min(valid_paces))
        pace_variability = self.calculate_pace_variability(valid_paces)
        
        # Zonen-Verteilung
        zone_distribution = self.analyze_zone_distribution(valid_paces)
        
        # TRIMP (wenn HR-Daten verfügbar)
        trimp = None
        if avg_hr and max_hr:
            trimp = self.calculate_trimp(
                duration_minutes=duration_minutes,
                avg_hr=avg_hr,
                max_hr=max_hr,
                resting_hr=resting_hr,
                is_female=is_female,
            )
        
        # Splits
        splits = self.calculate_splits(pace_readings, distance_km)
        
        return PaceMetrics(
            critical_pace=self.critical_pace,
            avg_pace=round(avg_pace, 2),
            best_pace=round(best_pace, 2),
            pace_variability=pace_variability,
            trimp=trimp,
            zone_distribution=zone_distribution,
            splits=splits,
        )


def estimate_critical_pace_from_activities(activities: List[Dict[str, Any]]) -> Optional[float]:
    """
    Schätzt Critical Pace basierend auf historischen Aktivitäten.
    
    Verwendet die schnellste Durchschnitts-Pace einer 10km+ Aktivität.
    
    Args:
        activities: Liste von Aktivitäten mit pace_readings
        
    Returns:
        Geschätzte Critical Pace in min/km oder None
    """
    best_pace = float('inf')
    
    for activity in activities:
        pace_readings = activity.get("pace_readings", [])
        distance_km = activity.get("distance_km", 0)
        
        # Nur Aktivitäten >= 10km für Pace-Schätzung
        if not pace_readings or distance_km < 10:
            continue
        
        valid_paces = [p for p in pace_readings if p > 0]
        if not valid_paces:
            continue
        
        avg_pace = float(np.mean(valid_paces))
        
        # Nur Pace-Werte die realistisch sind (3-8 min/km)
        if 3.0 <= avg_pace <= 8.0:
            best_pace = min(best_pace, avg_pace)
    
    if best_pace < float('inf'):
        # Critical Pace ≈ schnellste durchschnittliche Pace
        return round(best_pace, 2)
    
    return None


def calculate_pace_score(metrics: PaceMetrics) -> float:
    """
    Berechnet einen Pace-Score (0-100) basierend auf Metriken.
    
    Args:
        metrics: PaceMetrics einer Aktivität
        
    Returns:
        Score zwischen 0 und 100
    """
    score = 0.0
    
    # TRIMP gibt Punkte (bis 40)
    if metrics.trimp:
        score += min(metrics.trimp / 5, 40)
    
    # Pace-Variabilität (niedriger ist besser, bis 30)
    if metrics.pace_variability is not None:
        if metrics.pace_variability <= 0.05:
            score += 30
        elif metrics.pace_variability <= 0.10:
            score += 20
        elif metrics.pace_variability <= 0.15:
            score += 10
    
    # Zone-Verteilung (bis 30)
    if metrics.zone_distribution:
        # Bonus für ausgewogene Verteilung
        zone_values = list(metrics.zone_distribution.values())
        if any(v > 50 for v in zone_values):
            # Zu konzentriert auf eine Zone
            score += 10
        else:
            score += 30
    
    return round(min(score, 100), 1)