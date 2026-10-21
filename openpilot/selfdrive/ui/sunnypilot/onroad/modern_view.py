"""Shared geometry and visual tokens for the big-UI modern driving view (camera above a dash strip).

This module deliberately has no dependency on UI state or a renderer.  It is
safe for the HUD, alerts, road visualisation, and layout tests to import without
creating an onroad import cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import pyray as rl

from openpilot.common.filter_simple import FirstOrderFilter


CONTROL_BLUE = rl.Color(0x3E, 0x6A, 0xE1, 0xFF)
BRIGHT_CONTROL_BLUE = rl.Color(0x6F, 0x91, 0xFF, 0xFF)
BLOCKED_RED = rl.Color(0xC9, 0x22, 0x31, 0xFF)
NEUTRAL_GEOMETRY = rl.Color(0xF2, 0xF2, 0xF2, 0xFF)
LANE_LINE_WHITE = rl.Color(0xFF, 0xFF, 0xFF, 0xFF)

SCREEN_MARGIN = 15
MODERN_FRAME_THICKNESS = 12
STRIP_HEIGHT = 190
STRIP_GAP = 20
STRIP_PADDING_X = 40
STRIP_COLUMN_GAP = 32
STATUS_ZONE_WIDTH = 560
SPEED_ZONE_WIDTH = 720
ALERT_MARGIN = 40
ALERT_MAX_HEIGHT = 460
MIRROR_OCCLUSION_FRACTION = 0.3
RIGHT_DEV_UI_RESERVE = 244
BOTTOM_DEV_UI_RESERVE = 60


@dataclass(frozen=True)
class ModernContrast:
  control_blue: rl.Color
  lateral_only_blue: rl.Color
  text_shadow_alpha: int


class SegmentTone(StrEnum):
  off = "off"
  active = "active"
  paused = "paused"


@dataclass(frozen=True)
class StripStatus:
  steer_tone: SegmentTone
  steer_label: str
  cruise_tone: SegmentTone


@dataclass(frozen=True)
class ModernLayout:
  camera_frame: rl.Rectangle
  camera: rl.Rectangle
  strip: rl.Rectangle
  status_zone: rl.Rectangle
  centre_zone: rl.Rectangle
  speed_zone: rl.Rectangle
  alert_safe: rl.Rectangle


def strip_status(lateral_active: bool, status: str, cruise_enabled: bool) -> StripStatus:
  """Split control state into the strip's STEERING and CRUISE segments.

  Steering follows what openpilot is actually commanding; cruise follows the car's own cruise state, so a stock-ACC
  car still shows when its cruise is engaged.
  """
  if lateral_active:
    steer_tone, steer_label = SegmentTone.active, "STEERING"
  elif status == "override":
    steer_tone, steer_label = SegmentTone.paused, "PAUSED"
  else:
    steer_tone, steer_label = SegmentTone.off, "STEERING"
  return StripStatus(steer_tone, steer_label, SegmentTone.active if cruise_enabled else SegmentTone.off)


def format_speed_panel_values(is_cruise_set: bool, set_speed: float,
                              current_speed: float, is_metric: bool) -> tuple[str, str, str]:
  set_value = str(round(set_speed)) if is_cruise_set else "–"
  speed_value = str(round(current_speed))
  unit = "km/h" if is_metric else "mph"
  return set_value, speed_value, unit


class AdaptiveContrast:
  """Smooth camera light input into stable HUD contrast over roughly two seconds."""

  def __init__(self, target_fps: int):
    dt = 1.0 / max(target_fps, 1)
    self._light = FirstOrderFilter(0.5, 2.0, dt)

  def update(self, light_sensor: float) -> ModernContrast:
    # UIState exposes camera light on a 0-100 scale and -1 when unavailable.
    if light_sensor < 0:
      self._light.x = 0.5
      light = 0.5
    else:
      target = max(0.0, min(light_sensor / 100.0, 1.0))
      light = max(0.0, min(float(self._light.update(target)), 1.0))
    control_blue = blend_color(CONTROL_BLUE, BRIGHT_CONTROL_BLUE, light)
    return ModernContrast(
      control_blue=control_blue,
      lateral_only_blue=blend_color(control_blue, LANE_LINE_WHITE, 0.32),
      text_shadow_alpha=round(100 + 90 * light),
    )


def blend_color(begin: rl.Color, end: rl.Color, amount: float, alpha: int | None = None) -> rl.Color:
  amount = max(0.0, min(amount, 1.0))
  inv_amount = 1.0 - amount
  return rl.Color(
    round(inv_amount * begin.r + amount * end.r),
    round(inv_amount * begin.g + amount * end.g),
    round(inv_amount * begin.b + amount * end.b),
    round(inv_amount * begin.a + amount * end.a) if alpha is None else alpha,
  )


_DEFAULT_CONTROL_BLUE = blend_color(CONTROL_BLUE, BRIGHT_CONTROL_BLUE, 0.5)
DEFAULT_MODERN_CONTRAST = ModernContrast(
  control_blue=_DEFAULT_CONTROL_BLUE,
  lateral_only_blue=blend_color(_DEFAULT_CONTROL_BLUE, LANE_LINE_WHITE, 0.32),
  text_shadow_alpha=145,
)


def build_modern_layout(rect: rl.Rectangle, developer_ui: int | None = 0) -> ModernLayout:
  """Split the onroad view into the framed camera area and the dash strip below it.

  Developer UI values intentionally remain numeric here so this shared module
  does not need to import the UI-state-facing DeveloperUiState enum.
  """
  has_bottom_dev_ui = developer_ui in (1, 3)
  has_right_dev_ui = developer_ui in (2, 3)
  bottom_reserve = BOTTOM_DEV_UI_RESERVE if has_bottom_dev_ui else 0
  right_reserve = RIGHT_DEV_UI_RESERVE if has_right_dev_ui else 0

  frame_height = rect.height - 2 * SCREEN_MARGIN - STRIP_GAP - STRIP_HEIGHT
  camera_frame = rl.Rectangle(rect.x + SCREEN_MARGIN, rect.y + SCREEN_MARGIN,
                              rect.width - 2 * SCREEN_MARGIN, frame_height)
  camera = rl.Rectangle(camera_frame.x + MODERN_FRAME_THICKNESS, camera_frame.y + MODERN_FRAME_THICKNESS,
                        camera_frame.width - 2 * MODERN_FRAME_THICKNESS,
                        camera_frame.height - 2 * MODERN_FRAME_THICKNESS)
  strip = rl.Rectangle(camera_frame.x, camera_frame.y + camera_frame.height + STRIP_GAP,
                       camera_frame.width, STRIP_HEIGHT)

  inner_left = strip.x + STRIP_PADDING_X
  inner_right = strip.x + strip.width - STRIP_PADDING_X
  status_zone = rl.Rectangle(inner_left, strip.y, STATUS_ZONE_WIDTH, strip.height)
  speed_zone = rl.Rectangle(inner_right - SPEED_ZONE_WIDTH, strip.y, SPEED_ZONE_WIDTH, strip.height)
  centre_left = status_zone.x + status_zone.width + STRIP_COLUMN_GAP
  centre_zone = rl.Rectangle(centre_left, strip.y, max(0.0, speed_zone.x - STRIP_COLUMN_GAP - centre_left), strip.height)

  alert_left = camera.x + ALERT_MARGIN
  alert_right = camera.x + camera.width - ALERT_MARGIN - right_reserve
  alert_width = max(1.0, alert_right - alert_left)
  alert_x = alert_left
  alert_bottom = camera.y + camera.height - ALERT_MARGIN - bottom_reserve
  alert_top = max(camera.y + camera.height * MIRROR_OCCLUSION_FRACTION, alert_bottom - ALERT_MAX_HEIGHT)
  alert_safe = rl.Rectangle(alert_x, alert_top, alert_width, alert_bottom - alert_top)

  return ModernLayout(
    camera_frame=camera_frame,
    camera=camera,
    strip=strip,
    status_zone=status_zone,
    centre_zone=centre_zone,
    speed_zone=speed_zone,
    alert_safe=alert_safe,
  )
