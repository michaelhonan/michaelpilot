"""Pure geometry and animation helpers for the modern big-UI road view."""

from dataclasses import dataclass
from enum import StrEnum

import numpy as np


CLASSIC_LANE_LINE_HALF_WIDTH = 0.025
MODERN_LANE_LINE_HALF_WIDTH = 0.040
MODERN_ROAD_EDGE_MAX_ALPHA = 0.35
MODERN_PATH_EDGE_HALF_WIDTH = 0.05
LEAD_MIN_MODEL_PROB = 0.5
LEAD_TREND_DEADBAND = 1.0  # m/s, roughly 3.6 km/h either side of matching speed
MS_TO_KPH = 3.6
MS_TO_MPH = 2.236936


class LeadTrend(StrEnum):
  closing = "closing"
  matching = "matching"
  pulling_away = "pulling_away"


@dataclass(frozen=True)
class LeadSpeedLabel:
  speed: str
  unit: str
  trend: LeadTrend


def lead_speed_label(present: bool, radar: bool, model_prob: float, v_lead: float, v_rel: float,
                     is_metric: bool) -> LeadSpeedLabel | None:
  """Describe the lead vehicle's absolute speed, or None when the lead is not trustworthy enough to show."""
  if not present or (not radar and model_prob < LEAD_MIN_MODEL_PROB):
    return None

  speed = max(0.0, v_lead) * (MS_TO_KPH if is_metric else MS_TO_MPH)
  if v_rel < -LEAD_TREND_DEADBAND:
    trend = LeadTrend.closing
  elif v_rel > LEAD_TREND_DEADBAND:
    trend = LeadTrend.pulling_away
  else:
    trend = LeadTrend.matching
  return LeadSpeedLabel(str(round(speed)), "km/h" if is_metric else "mph", trend)


def control_blue_active(status: str, longitudinal_override: bool = False) -> bool:
  return longitudinal_override or status in ("engaged", "long_only", "override")


def instrument_blue_active(status: str, longitudinal_override: bool = False) -> bool:
  return longitudinal_override or status != "disengaged"


def lateral_blue_active(status: str) -> bool:
  return status in ("engaged", "lat_only", "override")


def path_style(modern: bool, status: str, rainbow: bool, experimental: bool) -> str:
  if rainbow:
    return "rainbow"
  if experimental:
    return "experimental"
  if not modern:
    return "classic"
  return "blue" if lateral_blue_active(status) else "neutral"


def lane_line_style(modern: bool, status: str, rainbow: bool, experimental: bool) -> str:
  if not modern:
    return "classic"
  return "blue" if path_style(modern, status, rainbow, experimental) == "blue" else "neutral"


def road_edge_alpha(standard_deviation: float, modern: bool) -> float:
  confidence = float(np.clip(1.0 - standard_deviation, 0.0, 1.0))
  return confidence * MODERN_ROAD_EDGE_MAX_ALPHA if modern else confidence


def advance_transition(progress: float, target: float, duration: float, dt: float) -> tuple[float, bool]:
  if progress == target:
    return progress, False
  if duration <= 0.0:
    return target, False
  step = max(0.0, dt) / duration
  if abs(target - progress) <= step + 1e-9:
    return target, False
  if target > progress:
    progress = min(target, progress + step)
  else:
    progress = max(target, progress - step)
  return progress, progress != target


def slice_ribbon(polygon: np.ndarray, start: float, end: float) -> np.ndarray:
  count = len(polygon) // 2
  if count < 2:
    return np.empty((0, 2), dtype=np.float32)
  lo = max(0, min(count - 2, int(start * (count - 1))))
  hi = max(lo + 2, min(count, int(np.ceil(end * (count - 1))) + 1))
  left = polygon[lo:hi]
  right = polygon[2 * count - hi:2 * count - lo]
  return np.vstack((left, right)).astype(np.float32)
