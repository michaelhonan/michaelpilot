"""Pure geometry and animation helpers for the modern big-UI road view."""

from dataclasses import dataclass
from enum import StrEnum

import numpy as np


CLASSIC_LANE_LINE_HALF_WIDTH = 0.025
MODERN_LANE_LINE_HALF_WIDTH = 0.040
MODERN_ROAD_EDGE_MAX_ALPHA = 0.35
LANE_CHANGE_COMPLETE_SECONDS = 0.4
LANE_CHANGE_START_MIN_SECONDS = 0.5
LANE_CHANGE_MODEL_FRAME_TOLERANCE_SECONDS = 0.05
LANE_CHANGE_TIMEOUT_SECONDS = 10.0
LANE_CHANGE_COMPLETE_PROBABILITY = 0.02


def smoothstep(progress: float) -> float:
  progress = max(0.0, min(progress, 1.0))
  return progress * progress * (3.0 - 2.0 * progress)


class LaneChangeIntent(StrEnum):
  off = "off"
  requested = "requested"
  active = "active"
  finishing = "finishing"


class LaneChangeVisualPhase(StrEnum):
  idle = "idle"
  active = "active"
  completing = "completing"


@dataclass(frozen=True)
class LaneChangeVisualInput:
  intent: LaneChangeIntent
  lateral_active: bool
  desire_probability: float | None
  enabled: bool = True


@dataclass(frozen=True)
class LaneChangeVisualOutput:
  phase: LaneChangeVisualPhase
  lock_sweep_position: float | None


class LaneChangeAnimator:
  """Frame-rate-independent completion confirmation for a model lane-change sequence."""

  def __init__(self) -> None:
    self.phase = LaneChangeVisualPhase.idle
    self.previous_intent = LaneChangeIntent.off
    self.active_elapsed = 0.0
    self.completion_progress = 0.0
    self.completion_latched = False

  def reset(self, intent: LaneChangeIntent = LaneChangeIntent.off) -> None:
    self.phase = LaneChangeVisualPhase.idle
    self.previous_intent = intent
    self.active_elapsed = 0.0
    self.completion_progress = 0.0
    self.completion_latched = False

  @staticmethod
  def _is_completion(input_state: LaneChangeVisualInput, active_elapsed: float) -> bool:
    probability = input_state.desire_probability
    return bool(input_state.lateral_active and probability is not None and
                active_elapsed + LANE_CHANGE_MODEL_FRAME_TOLERANCE_SECONDS + 1e-9 >= LANE_CHANGE_START_MIN_SECONDS and
                active_elapsed <= LANE_CHANGE_TIMEOUT_SECONDS + LANE_CHANGE_MODEL_FRAME_TOLERANCE_SECONDS + 1e-9 and
                probability < LANE_CHANGE_COMPLETE_PROBABILITY)

  def _start_active(self) -> None:
    self.phase = LaneChangeVisualPhase.active
    self.active_elapsed = 0.0
    self.completion_progress = 0.0
    self.completion_latched = False

  def _start_completion(self) -> None:
    self.phase = LaneChangeVisualPhase.completing
    self.completion_progress = 0.0
    self.completion_latched = True

  def update(self, input_state: LaneChangeVisualInput, dt: float) -> LaneChangeVisualOutput:
    if not input_state.enabled:
      self.reset(input_state.intent)
      return self.output()

    dt = max(0.0, dt)
    intent_changed = input_state.intent != self.previous_intent

    if not input_state.lateral_active:
      self.reset(input_state.intent)
    elif intent_changed:
      previous_intent = self.previous_intent
      if input_state.intent == LaneChangeIntent.finishing:
        if self.phase == LaneChangeVisualPhase.active and not self.completion_latched:
          self._start_completion()
      elif previous_intent == LaneChangeIntent.active and input_state.intent in (LaneChangeIntent.off, LaneChangeIntent.requested):
        if self._is_completion(input_state, self.active_elapsed):
          self._start_completion()
        else:
          self.reset(input_state.intent)
      elif input_state.intent == LaneChangeIntent.active:
        self._start_active()
      elif input_state.intent == LaneChangeIntent.off and previous_intent == LaneChangeIntent.finishing:
        if self.phase != LaneChangeVisualPhase.completing:
          self.phase = LaneChangeVisualPhase.idle

    if self.phase == LaneChangeVisualPhase.active:
      self.active_elapsed += dt
    elif self.phase == LaneChangeVisualPhase.completing:
      self.completion_progress, active = advance_transition(
        self.completion_progress, 1.0, LANE_CHANGE_COMPLETE_SECONDS, dt,
      )
      if not active:
        self.phase = LaneChangeVisualPhase.idle

    self.previous_intent = input_state.intent
    return self.output()

  def output(self) -> LaneChangeVisualOutput:
    return LaneChangeVisualOutput(
      phase=self.phase,
      lock_sweep_position=(1.0 - smoothstep(self.completion_progress)
                           if self.phase == LaneChangeVisualPhase.completing else None),
    )


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
