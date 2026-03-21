"""
Power-Analysis für Cycling und Running.
Berechnet FTP-basierte Metriken, Power-Zonen und Training Stress Score.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np

from observability import get_logger

LOGGER = get_logger(__name__)


@dataclass
class PowerMetrics:
    """Power-basierte Trainings-Metriken."""
    
    # Functional Threshold Power
    ftp: Optional[float] = None  # Watt
    
    # Intensity Factor (NP / FTP)
    intensity_factor: Optional[float] = None
    
    # Training Stress Score
    tss: Optional[float] = None
    
    # Variability Index (NP / AP)
    variability_index: Optional[float] = None
    
    # Power-to-Weight Ratio
    power_to_weight: Optional[float] = None  # W/kg
    
    # Peak Power
    peak_power: Optional[float] = None
    
    # Average Power
    avg_power: Optional[float] = None
    
    # Normalized Power
    normalized_power: Optional[float] = None
    
    # Power Zone Distribution
    zone_distribution: Optional[Dict[str, float]] = None


class PowerAnalyzer:
    """Analysiert Power-Daten für Cycling/Running."""
    
    # Power Zones basierend auf FTP
    ZONES = {
        "Z1: Recovery": (0, 0.55),
        "Z2: Endurance": (0.55, 0.75),
        "Z3: Tempo": (0.75, 0.90),
        "Z4: Threshold": (0.90, 1.05),
        "Z5: VO2max": (1.05, 1.20),
        "Z6: Anaerobic": (1.20, 1.50),
        "Z7: Sprint": (1.50, float('inf')),
    }
    
    def __init__(self, ftp: float):
        """
        Initialisiert PowerAnalyzer mit FTP.
        
        Args:
            ftp: Functional Threshold Power in Watt
        """
        if ftp <= 0:
            raise ValueError("FTP must be positive")
        self.ftp = ftp
    
    def calculate_normalized_power(self, power_readings: List[float]) -> float:
        """
        Berechnet Normalized Power (NP).
        
        NP ist der 30-Sekunden Rolling Average hoch 4, dann Durchschnitt, dann Wurzel 4.
        Das gewichtet höhere Leistung stärker.
        
        Args:
            power_readings: Liste der Power-Werte (1 pro Sekunde)
            
        Returns:
            Normalized Power in Watt
        """
        if not power_readings:
            return 0.0
        
        if len(power_readings) < 30:
            # Zu wenige Daten für Rolling Average
            return float(np.mean(power_readings))
        
        # 30-Sekunden Rolling Average
        rolling_avg = []
        for i in range(len(power_readings) - 29):
            window = power_readings[i:i + 30]
            window_mean = np.mean(window)
            rolling_avg.append(window_mean ** 4)
        
        # Durchschnitt der 4. Potenzen, dann Wurzel 4
        return float(np.mean(rolling_avg) ** 0.25)
    
    def calculate_intensity_factor(self, normalized_power: float) -> float:
        """
        Berechnet Intensity Factor (IF).
        
        IF = NP / FTP
        
        Args:
            normalized_power: Normalized Power in Watt
            
        Returns:
            Intensity Factor (0.0 - 2.0+)
        """
        if self.ftp <= 0:
            return 0.0
        return normalized_power / self.ftp
    
    def calculate_tss(self, duration_seconds: int, normalized_power: float,
                      intensity_factor: float) -> float:
        """
        Berechnet Training Stress Score (TSS).
        
        TSS = (duration_sec * NP * IF) / (FTP * 3600) * 100
        
        Args:
            duration_seconds: Dauer in Sekunden
            normalized_power: Normalized Power in Watt
            intensity_factor: Intensity Factor
            
        Returns:
            Training Stress Score
        """
        if self.ftp <= 0 or duration_seconds <= 0:
            return 0.0
        
        tss = (duration_seconds * normalized_power * intensity_factor) / (self.ftp * 3600) * 100
        return round(tss, 1)
    
    def calculate_variability_index(self, normalized_power: float,
                                     avg_power: float) -> float:
        """
        Berechnet Variability Index (VI).
        
        VI = NP / AP
        
        Ein VI von 1.0 bedeutet gleichmäßige Leistung.
        Höheres VI bedeutet mehr Schwankungen.
        
        Args:
            normalized_power: Normalized Power
            avg_power: Average Power
            
        Returns:
            Variability Index
        """
        if avg_power <= 0:
            return 1.0
        return normalized_power / avg_power
    
    def determine_power_zone(self, power: float) -> str:
        """
        Bestimmt Power-Zone basierend auf FTP.
        
        Args:
            power: Power in Watt
            
        Returns:
            Zone-String (z.B. "Z4: Threshold")
        """
        if power <= 0 or self.ftp <= 0:
            return "Z1: Recovery"
        
        ratio = power / self.ftp
        
        for zone_name, (min_ratio, max_ratio) in self.ZONES.items():
            if min_ratio <= ratio < max_ratio:
                return zone_name
        
        return "Z7: Sprint"
    
    def analyze_zone_distribution(self, power_readings: List[float]) -> Dict[str, float]:
        """
        Analysiert die Verteilung der Power über die Zonen.
        
        Args:
            power_readings: Liste der Power-Werte
            
        Returns:
            Dict mit Zone-Name und Prozent-Anteil
        """
        if not power_readings:
            return {zone: 0.0 for zone in self.ZONES}
        
        zone_counts = {zone: 0 for zone in self.ZONES}
        
        for power in power_readings:
            zone = self.determine_power_zone(power)
            zone_counts[zone] += 1
        
        total = len(power_readings)
        return {zone: round((count / total) * 100, 1)
                for zone, count in zone_counts.items()}
    
    def analyze_activity(self, power_readings: List[float],
                         duration_seconds: int,
                         weight_kg: Optional[float] = None) -> PowerMetrics:
        """
        Führt vollständige Power-Analyse einer Aktivität durch.
        
        Args:
            power_readings: Liste der Power-Werte
            duration_seconds: Dauer in Sekunden
            weight_kg: Körpergewicht in kg (optional)
            
        Returns:
            PowerMetrics mit allen berechneten Werten
        """
        if not power_readings:
            return PowerMetrics(ftp=self.ftp)
        
        # Basis-Metriken
        avg_power = float(np.mean(power_readings))
        peak_power = float(np.power(power_readings, 1))  # max()
        normalized_power = self.calculate_normalized_power(power_readings)
        
        # Abgeleitete Metriken
        intensity_factor = self.calculate_intensity_factor(normalized_power)
        tss = self.calculate_tss(duration_seconds, normalized_power, intensity_factor)
        variability_index = self.calculate_variability_index(normalized_power, avg_power)
        
        # Power-to-Weight (wenn Gewicht bekannt)
        power_to_weight = None
        if weight_kg and weight_kg > 0:
            power_to_weight = round(peak_power / weight_kg, 2)
        
        # Zonen-Verteilung
        zone_distribution = self.analyze_zone_distribution(power_readings)
        
        return PowerMetrics(
            ftp=self.ftp,
            intensity_factor=round(intensity_factor, 3),
            tss=tss,
            variability_index=round(variability_index, 3),
            power_to_weight=power_to_weight,
            peak_power=round(peak_power, 1),
            avg_power=round(avg_power, 1),
            normalized_power=round(normalized_power, 1),
            zone_distribution=zone_distribution,
        )


def estimate_ftp_from_activities(activities: List[Dict[str, Any]]) -> Optional[float]:
    """
    Schätzt FTP basierend auf historischen Aktivitäten.
    
    Verwendet die höchste 20-Minuten-Power oder avg_power als Fallback.
    
    Args:
        activities: Liste von Aktivitäten mit power_readings oder avg_power
        
    Returns:
        Geschätzter FTP oder None
    """
    best_20min_power = 0.0
    best_avg_power = 0.0
    
    for activity in activities:
        power_readings = activity.get("power_readings", [])
        avg_power = activity.get("avg_power")
        duration_min = activity.get("duration_min", 0)
        
        # Versuche power_readings zu verwenden
        if power_readings and duration_min >= 20:
            duration_seconds = duration_min * 60
            readings_per_second = len(power_readings) / duration_seconds
            window_size = int(20 * 60 * readings_per_second)
            
            if window_size <= len(power_readings):
                for i in range(len(power_readings) - window_size + 1):
                    window = power_readings[i:i + window_size]
                    avg_20min = float(np.mean(window))
                    best_20min_power = max(best_20min_power, avg_20min)
        
        # Fallback: Verwende avg_power für Aktivitäten >= 20 Minuten
        elif avg_power and duration_min >= 20:
            best_avg_power = max(best_avg_power, float(avg_power))
    
    # Bevorzuge power_readings, falls verfügbar
    if best_20min_power > 0:
        return round(best_20min_power * 0.95, 1)
    
    # Fallback: avg_power mit konservativerer Schätzung
    if best_avg_power > 0:
        return round(best_avg_power * 0.90, 1)
    
    return None


def calculate_power_score(metrics: PowerMetrics) -> float:
    """
    Berechnet einen Power-Score (0-100) basierend auf Metriken.
    
    Args:
        metrics: PowerMetrics einer Aktivität
        
    Returns:
        Score zwischen 0 und 100
    """
    score = 0.0
    
    # TSS gibt Punkte (bis 50)
    if metrics.tss:
        score += min(metrics.tss / 2, 50)
    
    # Intensity Factor gibt Punkte (bis 30)
    if metrics.intensity_factor:
        if metrics.intensity_factor >= 0.85:
            score += 30
        elif metrics.intensity_factor >= 0.75:
            score += 20
        elif metrics.intensity_factor >= 0.65:
            score += 10
    
    # Variability Index (niedriger ist besser, bis 20)
    if metrics.variability_index:
        if metrics.variability_index <= 1.05:
            score += 20
        elif metrics.variability_index <= 1.10:
            score += 15
        elif metrics.variability_index <= 1.15:
            score += 10
    
    return round(min(score, 100), 1)