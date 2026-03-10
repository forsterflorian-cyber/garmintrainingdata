from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Mapping, Tuple


@dataclass(frozen=True)
class WindowConfig:
    baseline_days: int = 21
    acute_load_days: int = 7
    chronic_load_days: int = 28
    min_baseline_samples: int = 7
    min_ratio_history_days: int = 7
    default_activity_limit: int = 400
    dashboard_history_limit: int = 365
    default_dashboard_range: int = 28
    range_filters: Tuple[int, ...] = (7, 14, 28, 84, 365)


@dataclass(frozen=True)
class ReadinessConfig:
    min_score: int = 1
    max_score: int = 99
    score_center: int = 50
    score_scale: int = 15
    std_floor: float = 0.5
    z_clip: float = 2.5
    higher_is_better: Mapping[str, bool] = field(
        default_factory=lambda: {
            "hrv": True,
            "resting_hr": False,
            "respiration": False,
            "sleep_h": True,
        }
        )


@dataclass(frozen=True)
class DecisionConfig:
    quality_min: float = 0.5
    moderate_min: float = -0.3
    easy_min: float = -0.8
    high_risk_ratio_min: float = 1.5
    high_risk_readiness_max: int = 30
    weights: Mapping[str, float] = field(
        default_factory=lambda: {
            "hrv": 0.35,
            "resting_hr": 0.25,
            "sleep_h": 0.20,
            "respiration": 0.10,
            "load": 0.10,
        }
    )


@dataclass(frozen=True)
class RatioConfig:
    under_target_max: float = 0.8
    target_max: float = 1.3
    elevated_max: float = 1.5


@dataclass(frozen=True)
class StressConfig:
    moderate_aero_te: float = 2.0
    moderate_anaerobic_te: float = 0.7
    moderate_load: float = 60.0
    high_aero_te: float = 4.0
    high_anaerobic_te: float = 2.0
    high_load: float = 120.0


@dataclass(frozen=True)
class MorningAlertConfig:
    respiration_high: float = 15.5
    hrv_low: float = 33.0
    resting_hr_high: float = 58.0


@dataclass(frozen=True)
class ModeScoreConfig:
    recovery_max: int
    moderate_max: int
    solid_max: int
    quality_max: int


@dataclass(frozen=True)
class FlagThresholdConfig:
    quality_min: int
    strength_heavy_min: int
    max_test_min: int


@dataclass(frozen=True)
class TrainingConfig:
    windows: WindowConfig = field(default_factory=WindowConfig)
    readiness: ReadinessConfig = field(default_factory=ReadinessConfig)
    decision: DecisionConfig = field(default_factory=DecisionConfig)
    ratio: RatioConfig = field(default_factory=RatioConfig)
    stress: StressConfig = field(default_factory=StressConfig)
    alerts: MorningAlertConfig = field(default_factory=MorningAlertConfig)
    recommendation_bands: Dict[str, ModeScoreConfig] = field(
        default_factory=lambda: {
            "run": ModeScoreConfig(35, 50, 65, 80),
            "bike": ModeScoreConfig(35, 50, 65, 80),
            "strength": ModeScoreConfig(35, 50, 65, 80),
            "hybrid": ModeScoreConfig(35, 50, 65, 80),
        }
    )
    unit_bands: Dict[str, Tuple[int, int, int]] = field(
        default_factory=lambda: {
            "run": (40, 65, 80),
            "bike": (40, 65, 80),
            "strength": (40, 60, 80),
            "hybrid": (40, 60, 80),
        }
    )
    flag_thresholds: Dict[str, FlagThresholdConfig] = field(
        default_factory=lambda: {
            "run": FlagThresholdConfig(65, 55, 80),
            "bike": FlagThresholdConfig(65, 55, 82),
            "strength": FlagThresholdConfig(70, 55, 85),
            "hybrid": FlagThresholdConfig(60, 60, 82),
        }
    )
    metric_labels: Mapping[str, str] = field(
        default_factory=lambda: {
            "hrv": "HRV",
            "resting_hr": "Resting HR",
            "respiration": "Respiration",
            "sleep_h": "Sleep",
        }
    )

    def recommendation_band(self, mode: str) -> ModeScoreConfig:
        return self.recommendation_bands.get(mode, self.recommendation_bands["hybrid"])

    def unit_band(self, mode: str) -> Tuple[int, int, int]:
        return self.unit_bands.get(mode, self.unit_bands["hybrid"])

    def flags_for_mode(self, mode: str) -> FlagThresholdConfig:
        return self.flag_thresholds.get(mode, self.flag_thresholds["hybrid"])


TRAINING_CONFIG = TrainingConfig()
