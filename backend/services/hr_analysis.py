"""
Heart-Rate-Analysis für alle Sportarten.
Berechnet HR-Zonen, Training Load und Recovery-Metriken.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np

from observability import get_logger

LOGGER = get_logger(__name__)


@dataclass
class HeartRateMetrics:
    """Heart-Rate-basierte Trainings-Metriken."""
    
    # Max & Resting Heart Rate
    max_hr: Optional[int] = None
    resting_hr: Optional[int] = None
    
    # Heart Rate Reserve
    hr_reserve: Optional[int] = None
    
    # Durchschnittliche HR
    avg_hr: Optional[int] = None
    
    # Maximale HR der Aktivität
    peak_hr: Optional[int] = None
    
    # Lactate Threshold Heart Rate
    lthr: Optional[int] = None
    
    # Heart Rate Recovery (1 min)
    hrr_1min: Optional[int] = None
    
    # Training Load (HR-basiert)
    hr_training_load: Optional[float] = None
    
    # HR Zone Distribution
    zone_distribution: Optional[Dict[str, float]] = None
    
    # Time in Zones (Minuten)
    time_in_zones: Optional[Dict[str, float]] = None
    
    # Efficiency Factor (Power/HR, wenn Power verfügbar)
    efficiency_factor: Optional[float] = None
    
    # Decoupling (Pace/HR Ratio über Zeit)
    decoupling: Optional[float] = None


class HeartRateAnalyzer:
    """Analysiert Heart-Rate-Daten für alle Sportarten."""
    
    # HR Zones basierend auf Heart Rate Reserve (Karvonen)
    ZONES_KARVONEN = {
        "Z1: Recovery": (0.50, 0.60),
        "Z2: Easy": (0.60, 0.70),
        "Z3: Moderate": (0.70, 0.80),
        "Z4: Threshold": (0.80, 0.90),
        "Z5: VO2max": (0.90, 1.00),
    }
    
    # HR Zones basierend auf LTHR
    ZONES_LTHR = {
        "Z1: Recovery": (0.00, 0.85),
        "Z2: Easy": (0.85, 0.92),
        "Z3: Moderate": (0.92, 0.97),
        "Z4: Threshold": (0.97, 1.02),
        "Z5: VO2max": (1.02, float('inf')),
    }
    
    def __init__(self, max_hr: int, resting_hr: int,
                 lthr: Optional[int] = None):
        """
        Initialisiert HeartRateAnalyzer.
        
        Args:
            max_hr: Maximale Herzfrequenz
            resting_hr: Ruheherzfrequenz
            lthr: Lactate Threshold Heart Rate (optional)
        """
        if max_hr <= resting_hr:
            raise ValueError("max_hr must be greater than resting_hr")
        
        self.max_hr = max_hr
        self.resting_hr = resting_hr
        self.hr_reserve = max_hr - resting_hr
        self.lthr = lthr or int(max_hr * 0.85)  # Schätzung
    
    def calculate_hr_zone_karvonen(self, current_hr: int) -> str:
        """
        Bestimmt HR-Zone mit Karvonen-Formel.
        
        Zone = (HR - Resting) / (Max - Resting)
        
        Args:
            current_hr: Aktuelle Herzfrequenz
            
        Returns:
            Zone-String
        """
        if current_hr <= self.resting_hr:
            return "Z1: Recovery"
        
        hr_percentage = (current_hr - self.resting_hr) / self.hr_reserve
        
        for zone_name, (min_pct, max_pct) in self.ZONES_KARVONEN.items():
            if min_pct <= hr_percentage < max_pct:
                return zone_name
        
        return "Z5: VO2max"
    
    def calculate_hr_zone_lthr(self, current_hr: int) -> str:
        """
        Bestimmt HR-Zone basierend auf LTHR.
        
        Args:
            current_hr: Aktuelle Herzfrequenz
            
        Returns:
            Zone-String
        """
        if current_hr <= 0 or self.lthr <= 0:
            return "Z1: Recovery"
        
        ratio = current_hr / self.lthr
        
        for zone_name, (min_ratio, max_ratio) in self.ZONES_LTHR.items():
            if min_ratio <= ratio < max_ratio:
                return zone_name
        
        return "Z5: VO2max"
    
    def analyze_zone_distribution(self, hr_readings: List[int],
                                   use_lthr: bool = False) -> Dict[str, float]:
        """
        Analysiert die Verteilung der HR über die Zonen.
        
        Args:
            hr_readings: Liste der HR-Werte
            use_lthr: LTHR-basierte Zonen verwenden
            
        Returns:
            Dict mit Zone-Name und Prozent-Anteil
        """
        if not hr_readings:
            zones = self.ZONES_LTHR if use_lthr else self.ZONES_KARVONEN
            return {zone: 0.0 for zone in zones}
        
        zones = self.ZONES_LTHR if use_lthr else self.ZONES_KARVONEN
        zone_counts = {zone: 0 for zone in zones}
        
        for hr in hr_readings:
            if hr > 0:
                if use_lthr:
                    zone = self.calculate_hr_zone_lthr(hr)
                else:
                    zone = self.calculate_hr_zone_karvonen(hr)
                zone_counts[zone] += 1
        
        total = len([hr for hr in hr_readings if hr > 0])
        if total == 0:
            return {zone: 0.0 for zone in zones}
        
        return {zone: round((count / total) * 100, 1)
                for zone, count in zone_counts.items()}
    
    def calculate_time_in_zones(self, hr_readings: List[int],
                                 readings_per_minute: float = 1.0,
                                 use_lthr: bool = False) -> Dict[str, float]:
        """
        Berechnet Zeit in Zonen (Minuten).
        
        Args:
            hr_readings: Liste der HR-Werte
            readings_per_minute: Anzahl Readings pro Minute
            use_lthr: LTHR-basierte Zonen
            
        Returns:
            Dict mit Zone-Name und Minuten
        """
        zone_distribution = self.analyze_zone_distribution(hr_readings, use_lthr)
        total_minutes = len(hr_readings) / readings_per_minute
        
        return {zone: round((pct / 100) * total_minutes, 1)
                for zone, pct in zone_distribution.items()}
    
    def calculate_hr_recovery(self, peak_hr: int, recovery_hr: int) -> int:
        """
        Berechnet Heart Rate Recovery (1 Minute).
        
        HRR = Peak HR - HR nach 1 Minute
        
        Args:
            peak_hr: Maximale HR während Aktivität
            recovery_hr: HR nach 1 Minute Erholung
            
        Returns:
            HRR in bpm
        """
        return max(0, peak_hr - recovery_hr)
    
    def calculate_training_load(self, duration_minutes: int, avg_hr: int,
                                 is_female: bool = False) -> float:
        """
        Berechnet HR-basierten Training Load (TRIMP).
        
        Args:
            duration_minutes: Dauer in Minuten
            avg_hr: Durchschnittliche Herzfrequenz
            is_female: Geschlecht
            
        Returns:
            Training Load Score
        """
        if avg_hr <= self.resting_hr:
            return 0.0
        
        # Herzfrequenz-Reserve
        hr_reserve = (avg_hr - self.resting_hr) / self.hr_reserve
        hr_reserve = max(0.0, min(1.0, hr_reserve))
        
        # Geschlechtsspezifischer Faktor
        k = 1.67 if is_female else 1.92
        
        # TRIMP
        trimp = duration_minutes * hr_reserve * k * np.exp(k * hr_reserve)
        
        return round(trimp, 1)
    
    def calculate_efficiency_factor(self, avg_power: float,
                                     avg_hr: float) -> float:
        """
        Berechnet Efficiency Factor (Power/HR).
        
        Args:
            avg_power: Durchschnittliche Leistung in Watt
            avg_hr: Durchschnittliche Herzfrequenz
            
        Returns:
            Efficiency Factor (Watt/bpm)
        """
        if avg_hr <= 0:
            return 0.0
        return round(avg_power / avg_hr, 2)
    
    def calculate_decoupling(self, first_half_paces: List[float],
                              first_half_hrs: List[int],
                              second_half_paces: List[float],
                              second_half_hrs: List[int]) -> float:
        """
        Berechnet Decoupling (Pace/HR Ratio Veränderung).
        
        Decoupling zeigt Fatigue an:
        - 0% = keine Veränderung
        - Positiv = Pace wird langsamer bei gleicher HR
        - Negativ = Pace wird schneller bei gleicher HR
        
        Args:
            first_half_paces: Pace-Werte erste Hälfte
            first_half_hrs: HR-Werte erste Hälfte
            second_half_paces: Pace-Werte zweite Hälfte
            second_half_hrs: HR-Werte zweite Hälfte
            
        Returns:
            Decoupling in Prozent
        """
        if not first_half_paces or not first_half_hrs:
            return 0.0
        if not second_half_paces or not second_half_hrs:
            return 0.0
        
        # Pace/HR Ratio für beide Hälften
        first_ratio = np.mean(first_half_paces) / np.mean(first_half_hrs)
        second_ratio = np.mean(second_half_paces) / np.mean(second_half_hrs)
        
        if first_ratio <= 0:
            return 0.0
        
        # Decoupling = Veränderung in %
        decoupling = ((second_ratio - first_ratio) / first_ratio) * 100
        
        return round(decoupling, 2)
    
    def analyze_activity(self, hr_readings: List[int],
                         duration_minutes: int,
                         peak_hr: Optional[int] = None,
                         recovery_hr: Optional[int] = None,
                         avg_power: Optional[float] = None,
                         pace_readings: Optional[List[float]] = None,
                         is_female: bool = False,
                         use_lthr: bool = False) -> HeartRateMetrics:
        """
        Führt vollständige HR-Analyse einer Aktivität durch.
        
        Args:
            hr_readings: Liste der HR-Werte
            duration_minutes: Dauer in Minuten
            peak_hr: Maximale HR (optional)
            recovery_hr: HR nach 1 Minute (optional)
            avg_power: Durchschnittliche Power (optional)
            pace_readings: Pace-Werte (optional)
            is_female: Geschlecht
            use_lthr: LTHR-basierte Zonen
            
        Returns:
            HeartRateMetrics mit allen berechneten Werten
        """
        if not hr_readings:
            return HeartRateMetrics(
                max_hr=self.max_hr,
                resting_hr=self.resting_hr,
                hr_reserve=self.hr_reserve,
                lthr=self.lthr,
            )
        
        # Gültige HRs filtern
        valid_hrs = [hr for hr in hr_readings if hr > 0]
        
        if not valid_hrs:
            return HeartRateMetrics(
                max_hr=self.max_hr,
                resting_hr=self.resting_hr,
                hr_reserve=self.hr_reserve,
                lthr=self.lthr,
            )
        
        # Basis-Metriken
        avg_hr = int(np.mean(valid_hrs))
        peak_hr = peak_hr or int(np.max(valid_hrs))
        
        # Zonen-Verteilung
        zone_distribution = self.analyze_zone_distribution(valid_hrs, use_lthr)
        
        # Time in Zones
        time_in_zones = self.calculate_time_in_zones(
            valid_hrs,
            readings_per_minute=len(valid_hrs) / duration_minutes,
            use_lthr=use_lthr,
        )
        
        # Training Load
        hr_training_load = self.calculate_training_load(
            duration_minutes=duration_minutes,
            avg_hr=avg_hr,
            is_female=is_female,
        )
        
        # Heart Rate Recovery
        hrr_1min = None
        if recovery_hr:
            hrr_1min = self.calculate_hr_recovery(peak_hr, recovery_hr)
        
        # Efficiency Factor (wenn Power verfügbar)
        efficiency_factor = None
        if avg_power:
            efficiency_factor = self.calculate_efficiency_factor(avg_power, avg_hr)
        
        # Decoupling (wenn Pace verfügbar)
        decoupling = None
        if pace_readings and len(pace_readings) >= 10:
            half = len(pace_readings) // 2
            first_half_paces = pace_readings[:half]
            second_half_paces = pace_readings[half:]
            
            # Annahme: gleiche Anzahl HRs wie Paces
            hr_per_pace = len(valid_hrs) / len(pace_readings)
            first_half_hrs = valid_hrs[:int(half * hr_per_pace)]
            second_half_hrs = valid_hrs[int(half * hr_per_pace):]
            
            if first_half_hrs and second_half_hrs:
                decoupling = self.calculate_decoupling(
                    first_half_paces, first_half_hrs,
                    second_half_paces, second_half_hrs,
                )
        
        return HeartRateMetrics(
            max_hr=self.max_hr,
            resting_hr=self.resting_hr,
            hr_reserve=self.hr_reserve,
            avg_hr=avg_hr,
            peak_hr=peak_hr,
            lthr=self.lthr,
            hrr_1min=hrr_1min,
            hr_training_load=hr_training_load,
            zone_distribution=zone_distribution,
            time_in_zones=time_in_zones,
            efficiency_factor=efficiency_factor,
            decoupling=decoupling,
        )


def estimate_lthr_from_activities(activities: List[Dict[str, Any]]) -> Optional[int]:
    """
    Schätzt LTHR basierend auf historischen Aktivitäten.
    
    Verwendet die durchschnittliche HR der Schwellenaktivitäten.
    
    Args:
        activities: Liste von Aktivitäten mit hr_readings
        
    Returns:
        Geschätztes LTHR oder None
    """
    threshold_hrs = []
    
    for activity in activities:
        hr_readings = activity.get("hr_readings", [])
        duration_min = activity.get("duration_min", 0)
        
        # Aktivitäten 20-60 Minuten für LTHR-Schätzung
        if not hr_readings or not (20 <= duration_min <= 60):
            continue
        
        valid_hrs = [hr for hr in hr_readings if hr > 0]
        if not valid_hrs:
            continue
        
        avg_hr = int(np.mean(valid_hrs))
        
        # Nur HRs im Bereich 150-190 für LTHR
        if 150 <= avg_hr <= 190:
            threshold_hrs.append(avg_hr)
    
    if threshold_hrs:
        # Durchschnitt der Schwellenwerte
        return int(np.mean(threshold_hrs))
    
    return None


def calculate_hr_score(metrics: HeartRateMetrics) -> float:
    """
    Berechnet einen HR-Score (0-100) basierend auf Metriken.
    
    Args:
        metrics: HeartRateMetrics einer Aktivität
        
    Returns:
            Score zwischen 0 und 100
    """
    score = 0.0
    
    # Training Load gibt Punkte (bis 40)
    if metrics.hr_training_load:
        score += min(metrics.hr_training_load / 5, 40)
    
    # Heart Rate Recovery (bis 30)
    if metrics.hrr_1min:
        if metrics.hrr_1min >= 30:
            score += 30
        elif metrics.hrr_1min >= 20:
            score += 20
        elif metrics.hrr_1min >= 10:
            score += 10
    
    # Decoupling (niedriger ist besser, bis 30)
    if metrics.decoupling is not None:
        if abs(metrics.decoupling) <= 5:
            score += 30
        elif abs(metrics.decoupling) <= 10:
            score += 20
        elif abs(metrics.decoupling) <= 15:
            score += 10
    
    return round(min(score, 100), 1)