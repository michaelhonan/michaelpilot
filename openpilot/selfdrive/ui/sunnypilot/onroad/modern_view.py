"""Shared geometry and visual tokens for the big-UI modern driving view.

This module deliberately has no dependency on UI state or a renderer.  It is
safe for the HUD, alerts, road visualisation, and layout tests to import without
creating an onroad import cycle.
"""

from __future__ import annotations

from dataclasses import dataclass

import pyray as rl

from openpilot.common.filter_simple import FirstOrderFilter


CONTROL_BLUE = rl.Color(0x3E, 0x6A, 0xE1, 0xFF)
BRIGHT_CONTROL_BLUE = rl.Color(0x6F, 0x91, 0xFF, 0xFF)
BLOCKED_RED = rl.Color(0xC9, 0x22, 0x31, 0xFF)
NEUTRAL_GEOMETRY = rl.Color(0xF2, 0xF2, 0xF2, 0xFF)
LANE_LINE_WHITE = rl.Color(0xFF, 0xFF, 0xFF, 0xFF)

MODERN_FRAME_THICKNESS = 15
RIGHT_MARGIN = 48
BOTTOM_MARGIN = 42
SPEED_PANEL_WIDTH = 590
SPEED_PANEL_HEIGHT = 220
ROAD_NAME_HEIGHT = 64
UTILITY_SIZE = 192
RIGHT_DEV_UI_RESERVE = 244
BOTTOM_DEV_UI_RESERVE = 60
ELEMENT_GAP = 28


@dataclass(frozen=True)
class ModernContrast:
  control_blue: rl.Color
  lateral_only_blue: rl.Color
  text_shadow_alpha: int


@dataclass(frozen=True)
class ModernTypography:
  panel_label: int = 32
  panel_value: int = 86
  panel_unit: int = 28
  road_name: int = 40
  utility: int = 40


@dataclass(frozen=True)
class ModernSurfaces:
  panel_alpha: int = 170
  utility_alpha: int = 118
  panel_roundness: float = 0.18
  panel_border_width: int = 4


@dataclass(frozen=True)
class ModernLayout:
  speed_panel: rl.Rectangle
  road_name: rl.Rectangle
  experimental_control: rl.Rectangle
  acceleration_bar: rl.Rectangle
  smart_cruise: rl.Rectangle
  circular_alert: rl.Rectangle
  alert_safe: rl.Rectangle
  left_signal: rl.Rectangle
  right_signal: rl.Rectangle


MODERN_TYPOGRAPHY = ModernTypography()
MODERN_SURFACES = ModernSurfaces()


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
  """Calculate the complete modern HUD layout from the current content bounds.

  Developer UI values intentionally remain numeric here so this shared module
  does not need to import the UI-state-facing DeveloperUiState enum.
  """
  has_bottom_dev_ui = developer_ui in (1, 3)
  has_right_dev_ui = developer_ui in (2, 3)
  bottom_reserve = BOTTOM_DEV_UI_RESERVE if has_bottom_dev_ui else 0
  right_reserve = RIGHT_DEV_UI_RESERVE if has_right_dev_ui else 0

  right = rect.x + rect.width - RIGHT_MARGIN - right_reserve
  bottom = rect.y + rect.height - BOTTOM_MARGIN - bottom_reserve
  speed_panel = rl.Rectangle(right - SPEED_PANEL_WIDTH, bottom - SPEED_PANEL_HEIGHT,
                             SPEED_PANEL_WIDTH, SPEED_PANEL_HEIGHT)

  utility_bottom = bottom
  exp_rect = rl.Rectangle(rect.x + RIGHT_MARGIN, utility_bottom - UTILITY_SIZE, UTILITY_SIZE, UTILITY_SIZE)
  acceleration_bar = rl.Rectangle(rect.x + 8, exp_rect.y, 28, exp_rect.height)
  road_left = exp_rect.x + exp_rect.width + ELEMENT_GAP
  road_right = speed_panel.x - ELEMENT_GAP
  road_name = rl.Rectangle(road_left, bottom - ROAD_NAME_HEIGHT,
                           max(1.0, road_right - road_left), ROAD_NAME_HEIGHT)
  circular_x = min(exp_rect.x + exp_rect.width + 26, speed_panel.x - 16 - 220)
  circular_alert = rl.Rectangle(circular_x, utility_bottom - 220, 220, 220)
  smart_cruise = rl.Rectangle(rect.x + RIGHT_MARGIN, circular_alert.y - 16 - 64 - 16 - 92, 360, 92)

  alert_left = exp_rect.x + exp_rect.width + ELEMENT_GAP
  alert_right = speed_panel.x - ELEMENT_GAP
  alert_available_width = max(1.0, alert_right - alert_left)
  alert_width = min(900.0, alert_available_width)
  alert_x = alert_left + (alert_available_width - alert_width) / 2
  alert_bottom = bottom
  alert_top = max(rect.y + rect.height * 0.3, alert_bottom - 420)
  alert_safe = rl.Rectangle(alert_x, alert_top, alert_width, alert_bottom - alert_top)

  signal_size = 150
  signal_y = rect.y + rect.height * 0.45 - signal_size / 2
  left_signal = rl.Rectangle(rect.x + 34, signal_y, signal_size, signal_size)
  right_signal = rl.Rectangle(rect.x + rect.width - signal_size - 34 - right_reserve,
                              signal_y, signal_size, signal_size)

  return ModernLayout(
    speed_panel=speed_panel,
    road_name=road_name,
    experimental_control=exp_rect,
    acceleration_bar=acceleration_bar,
    smart_cruise=smart_cruise,
    circular_alert=circular_alert,
    alert_safe=alert_safe,
    left_signal=left_signal,
    right_signal=right_signal,
  )
