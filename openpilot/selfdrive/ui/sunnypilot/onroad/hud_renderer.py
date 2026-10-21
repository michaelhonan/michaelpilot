"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import pyray as rl

from openpilot.common.constants import CV
from openpilot.selfdrive.ui.mici.onroad.torque_bar import TorqueBar
from openpilot.selfdrive.ui.sunnypilot.onroad.developer_ui import DeveloperUiRenderer, DeveloperUiState, get_bottom_dev_ui_offset
from openpilot.selfdrive.ui.sunnypilot.onroad.road_name import RoadNameRenderer
from openpilot.selfdrive.ui.sunnypilot.onroad.rocket_fuel import RocketFuel
from openpilot.selfdrive.ui.sunnypilot.onroad.speed_limit import SpeedLimitRenderer
from openpilot.selfdrive.ui.sunnypilot.onroad.smart_cruise_control import SmartCruiseControlRenderer
from openpilot.selfdrive.ui.sunnypilot.onroad.turn_signal import TurnSignalController
from openpilot.selfdrive.ui.sunnypilot.onroad.circular_alerts import CircularAlertsRenderer
from openpilot.selfdrive.ui.sunnypilot.onroad.speed_renderer import SpeedRenderer
from openpilot.selfdrive.ui.sunnypilot.onroad.modern_view import (
  DEFAULT_MODERN_CONTRAST, ModernContrast, ModernLayout, SegmentTone, build_modern_layout,
  format_speed_panel_values, strip_status,
)
from openpilot.selfdrive.ui.ui_state import ui_state, UIStatus
from openpilot.selfdrive.ui.onroad.hud_renderer import HudRenderer, UI_CONFIG, FONT_SIZES, COLORS, CRUISE_DISABLED_CHAR
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.lib.text_measure import measure_text_cached

SLA_ACTIVE_COLOR = rl.Color(0x91, 0x9b, 0x95, 0xff)

# Dash strip. Font sizes are nominal: draw_text_ex scales them up by FONT_SCALE on the big UI.
STRIP_BG = rl.Color(0x0B, 0x0D, 0x10, 0xFF)
STRIP_RADIUS = 48
STRIP_PILL_BG = rl.Color(0x15, 0x19, 0x1E, 0xFF)
STRIP_MUTED = rl.Color(0x5F, 0x68, 0x73, 0xFF)
STRIP_SECONDARY = rl.Color(0x8A, 0x93, 0xA0, 0xFF)
STRIP_DIVIDER = rl.Color(255, 255, 255, 31)
STRIP_ROAD_NAME = rl.Color(0xE6, 0xE9, 0xEE, 0xFF)
STRIP_PAUSED = rl.Color(0x8A, 0x91, 0x8D, 0xFF)
SIGNAL_IDLE = rl.Color(255, 255, 255, 36)
SIGNAL_LIT = rl.Color(0x3D, 0xDC, 0x84, 0xFF)
SIGNAL_BLIND_SPOT = rl.Color(0xF0, 0x56, 0x4A, 0xFF)
SIGNAL_MIN_LIT = 0.45

STATUS_PILL_HEIGHT = 116
STATUS_PILL_PADDING = 8
STATUS_SEGMENT_PADDING_X = 34
STATUS_DOT_SIZE = 16
STATUS_DOT_GAP = 14
STATUS_FONT_SIZE = 26
STATUS_LETTER_SPACING = 2
ROAD_NAME_FONT_SIZE = 37
SIGNAL_SIZE = 64
SIGNAL_GAP = 36
SPEED_FONT_SIZE = 121
SPEED_UNIT_FONT_SIZE = 24
SET_LABEL_FONT_SIZE = 21
SET_VALUE_FONT_SIZE = 58
SET_COLUMN_WIDTH = 120
SPEED_GROUP_GAP = 28
SIGN_SIZE = 136
MUTCD_SIGN_WIDTH = 112


class HudRendererSP(HudRenderer):
  def __init__(self):
    super().__init__()
    self.developer_ui = DeveloperUiRenderer()
    self.road_name_renderer = RoadNameRenderer()
    self.rocket_fuel = RocketFuel()
    self.speed_limit_renderer = SpeedLimitRenderer()
    self.smart_cruise_control_renderer = SmartCruiseControlRenderer()
    self.turn_signal_controller = TurnSignalController()
    self.circular_alerts_renderer = CircularAlertsRenderer()
    self.speed_renderer = SpeedRenderer()
    self._torque_bar = TorqueBar(scale=3.0, always=True)
    self._modern_contrast = DEFAULT_MODERN_CONTRAST

    self.pcm_cruise_speed: bool = True
    self.show_icbm_status: bool = False
    self.icbm_active_counter: int = 0
    self.speed_cluster: float = 0.0
    self.speed_conv: float = CV.MS_TO_KPH if ui_state.is_metric else CV.MS_TO_MPH

  def set_modern_contrast(self, contrast: ModernContrast) -> None:
    self._modern_contrast = contrast

  def _update_state(self) -> None:
    if ui_state.sm.recv_frame["carState"] < ui_state.started_frame:
      return

    if ui_state.CP_SP is not None:
      self.pcm_cruise_speed = ui_state.CP_SP.pcmCruiseSpeed
    self.speed_conv = CV.MS_TO_KPH if ui_state.is_metric else CV.MS_TO_MPH
    self.speed_cluster = ui_state.sm['carState'].cruiseState.speedCluster * self.speed_conv

    super()._update_state()
    self.road_name_renderer.update()
    self.speed_limit_renderer.update()
    self.smart_cruise_control_renderer.update()
    self.turn_signal_controller.update()
    self.circular_alerts_renderer.update()
    self.speed_renderer.update()

  def _get_icbm_status(self):
    if not self.pcm_cruise_speed and ui_state.sm['carControl'].enabled:
      if round(self.set_speed) != round(self.speed_cluster):
        self.icbm_active_counter = 3 * gui_app.target_fps  # 3 seconds usually
      elif self.icbm_active_counter > 0:
        self.icbm_active_counter -= 1
    else:
      self.icbm_active_counter = 0

    self.show_icbm_status = self.icbm_active_counter > 0

  def _draw_set_speed(self, rect: rl.Rectangle) -> None:
    long_plan_sp = ui_state.sm['longitudinalPlanSP']
    long_override = ui_state.sm['carControl'].cruiseControl.override
    self._get_icbm_status()

    set_speed_width = UI_CONFIG.set_speed_width_metric if ui_state.is_metric else UI_CONFIG.set_speed_width_imperial
    x = rect.x + 60 + (UI_CONFIG.set_speed_width_imperial - set_speed_width) // 2
    y = rect.y + 45

    set_speed_rect = rl.Rectangle(x, y, set_speed_width, UI_CONFIG.set_speed_height)
    rl.draw_rectangle_rounded(set_speed_rect, 0.35, 10, COLORS.BLACK_TRANSLUCENT)
    rl.draw_rectangle_rounded_lines_ex(set_speed_rect, 0.35, 10, 6, COLORS.BORDER_TRANSLUCENT)

    max_color = COLORS.GREY
    set_speed_color = COLORS.DARK_GREY
    if self.is_cruise_set:
      set_speed_color = COLORS.WHITE
      if long_plan_sp.speedLimit.assist.active:
        set_speed_color = SLA_ACTIVE_COLOR if long_override else rl.Color(0, 0xff, 0, 0xff)
        max_color = SLA_ACTIVE_COLOR if long_override else rl.Color(0x80, 0xd8, 0xa6, 0xff)
      else:
        if ui_state.status == UIStatus.ENGAGED:
          max_color = COLORS.ENGAGED
        elif ui_state.status == UIStatus.DISENGAGED:
          max_color = COLORS.DISENGAGED
        elif ui_state.status == UIStatus.OVERRIDE:
          max_color = COLORS.OVERRIDE

    max_str_size = 60 if self.show_icbm_status else 40
    max_str_y = 15 if self.show_icbm_status else 27

    max_text = str(round(self.speed_cluster)) if self.show_icbm_status else tr("MAX")
    max_text_width = measure_text_cached(self._font_semi_bold, max_text, max_str_size).x
    rl.draw_text_ex(
      self._font_semi_bold,
      max_text,
      rl.Vector2(x + (set_speed_width - max_text_width) / 2, y + max_str_y),
      max_str_size,
      0,
      max_color,
    )

    set_speed_text = CRUISE_DISABLED_CHAR if not self.is_cruise_set else str(round(self.set_speed))
    speed_text_width = measure_text_cached(self._font_bold, set_speed_text, FONT_SIZES.set_speed).x
    rl.draw_text_ex(
      self._font_bold,
      set_speed_text,
      rl.Vector2(x + (set_speed_width - speed_text_width) / 2, y + 77),
      FONT_SIZES.set_speed,
      0,
      set_speed_color,
    )

  def _draw_current_speed(self, rect: rl.Rectangle) -> None:
    self.speed_renderer.render(rect)

  def _render_modern(self, rect: rl.Rectangle) -> None:
    layout = build_modern_layout(rect, ui_state.developer_ui)
    camera = layout.camera

    if ui_state.torque_bar:
      self._torque_bar.render(rl.Rectangle(camera.x, camera.y, camera.width, camera.height - get_bottom_dev_ui_offset()))

    self.developer_ui.render(camera)
    self._draw_strip(layout)

  def _draw_strip(self, layout: ModernLayout) -> None:
    strip = layout.strip
    rl.draw_rectangle_rounded(strip, STRIP_RADIUS * 2 / min(strip.width, strip.height), 10, STRIP_BG)
    self._draw_strip_status(layout.status_zone)
    self._draw_strip_road(layout.centre_zone)
    self._draw_strip_speed(layout.speed_zone)

  def _draw_strip_status(self, zone: rl.Rectangle) -> None:
    sm = ui_state.sm
    status = strip_status(sm['carControl'].latActive, ui_state.status.value, sm['carState'].cruiseState.enabled)
    segments = ((tr(status.steer_label), status.steer_tone), (tr("CRUISE"), status.cruise_tone))

    font = self._font_bold
    widths = [2 * STATUS_SEGMENT_PADDING_X + STATUS_DOT_SIZE + STATUS_DOT_GAP +
              measure_text_cached(font, text, STATUS_FONT_SIZE, STATUS_LETTER_SPACING).x for text, _ in segments]
    pill = rl.Rectangle(zone.x, zone.y + (zone.height - STATUS_PILL_HEIGHT) / 2,
                        sum(widths) + STATUS_PILL_PADDING * (len(segments) + 1), STATUS_PILL_HEIGHT)
    rl.draw_rectangle_rounded(pill, 1.0, 16, STRIP_PILL_BG)

    segment_height = STATUS_PILL_HEIGHT - 2 * STATUS_PILL_PADDING
    x = pill.x + STATUS_PILL_PADDING
    center_y = pill.y + pill.height / 2
    for (text, tone), width in zip(segments, widths, strict=True):
      if tone == SegmentTone.active:
        background, foreground = self._modern_contrast.control_blue, COLORS.WHITE
      elif tone == SegmentTone.paused:
        background, foreground = STRIP_PAUSED, COLORS.WHITE
      else:
        background, foreground = None, STRIP_MUTED
      if background is not None:
        rl.draw_rectangle_rounded(rl.Rectangle(x, pill.y + STATUS_PILL_PADDING, width, segment_height), 1.0, 16, background)

      dot_x = x + STATUS_SEGMENT_PADDING_X
      rl.draw_circle_v(rl.Vector2(dot_x + STATUS_DOT_SIZE / 2, center_y), STATUS_DOT_SIZE / 2, foreground)
      text_size = measure_text_cached(font, text, STATUS_FONT_SIZE, STATUS_LETTER_SPACING)
      rl.draw_text_ex(font, text, rl.Vector2(dot_x + STATUS_DOT_SIZE + STATUS_DOT_GAP, center_y - text_size.y / 2),
                      STATUS_FONT_SIZE, STATUS_LETTER_SPACING, foreground)
      x += width + STATUS_PILL_PADDING

  def _draw_strip_road(self, zone: rl.Rectangle) -> None:
    center = rl.Vector2(zone.x + zone.width / 2, zone.y + zone.height / 2)
    show_signals = ui_state.turn_signals or ui_state.blindspot
    signal_space = SIGNAL_SIZE + SIGNAL_GAP if show_signals else 0

    road_name = self.road_name_renderer.road_name if ui_state.road_name_toggle else ""
    text_width = 0.0
    if road_name:
      max_width = zone.width - 2 * signal_space
      text = self._truncate(self._font_semi_bold, road_name, ROAD_NAME_FONT_SIZE, max_width)
      if text:
        size = measure_text_cached(self._font_semi_bold, text, ROAD_NAME_FONT_SIZE)
        text_width = size.x
        rl.draw_text_ex(self._font_semi_bold, text, rl.Vector2(center.x - size.x / 2, center.y - size.y / 2),
                        ROAD_NAME_FONT_SIZE, 0, STRIP_ROAD_NAME)

    if not show_signals:
      return
    offset = (text_width / 2 + SIGNAL_GAP) if text_width else SIGNAL_GAP / 2
    (left_type, left_alpha), (right_type, right_alpha) = self.turn_signal_controller.strip_states()
    self._draw_signal_arrow(center.x - offset - SIGNAL_SIZE, center.y, False, self._signal_color(left_type, left_alpha))
    self._draw_signal_arrow(center.x + offset, center.y, True, self._signal_color(right_type, right_alpha))

  @staticmethod
  def _signal_color(signal_type: str | None, alpha: int) -> rl.Color:
    if signal_type == 'blind_spot':
      return SIGNAL_BLIND_SPOT
    if signal_type == 'signal':
      # Blink between full and part green rather than back to idle, so an indicator that's on always reads as on.
      lit = max(SIGNAL_MIN_LIT, min(alpha / 255, 1.0))
      return rl.Color(
        round(SIGNAL_IDLE.r + (SIGNAL_LIT.r - SIGNAL_IDLE.r) * lit),
        round(SIGNAL_IDLE.g + (SIGNAL_LIT.g - SIGNAL_IDLE.g) * lit),
        round(SIGNAL_IDLE.b + (SIGNAL_LIT.b - SIGNAL_IDLE.b) * lit),
        round(SIGNAL_IDLE.a + (SIGNAL_LIT.a - SIGNAL_IDLE.a) * lit),
      )
    return SIGNAL_IDLE

  @staticmethod
  def _draw_signal_arrow(x: float, center_y: float, pointing_right: bool, color: rl.Color) -> None:
    # Arrow drawn on a 24-unit grid: a head from x=2..10 and a shaft from x=10..20, mirrored for the right side.
    scale = SIGNAL_SIZE / 24
    top = center_y - SIGNAL_SIZE / 2

    def point(u: float, v: float) -> rl.Vector2:
      return rl.Vector2(x + (24 - u if pointing_right else u) * scale, top + v * scale)

    tip, head_top, head_bottom = point(2, 12), point(10, 4), point(10, 20)
    # raylib only fills triangles wound counter-clockwise on screen.
    if pointing_right:
      rl.draw_triangle(tip, head_top, head_bottom, color)
    else:
      rl.draw_triangle(tip, head_bottom, head_top, color)
    shaft_left = x + (4 if pointing_right else 10) * scale
    rl.draw_rectangle_rec(rl.Rectangle(shaft_left, top + 9 * scale, 10 * scale, 6 * scale), color)

  def _draw_strip_speed(self, zone: rl.Rectangle) -> None:
    center_y = zone.y + zone.height / 2
    set_text, speed_text, unit_text = format_speed_panel_values(
      self.is_cruise_set, self.set_speed, self.speed_renderer.speed, ui_state.is_metric,
    )
    unit_text = tr(unit_text)

    # Laid out right to left so the current speed always hugs the strip's right edge.
    right = zone.x + zone.width
    if not ui_state.hide_v_ego_ui:
      speed_size = measure_text_cached(self._font_bold, speed_text, SPEED_FONT_SIZE)
      unit_size = measure_text_cached(self._font_medium, unit_text, SPEED_UNIT_FONT_SIZE)
      unit_x = right - unit_size.x
      speed_x = unit_x - 12 - speed_size.x
      speed_y = center_y - speed_size.y / 2
      # Sit the unit on the speed's baseline (roughly 80% of the line height for Inter).
      unit_y = speed_y + speed_size.y * 0.8 - unit_size.y * 0.8
      rl.draw_text_ex(self._font_bold, speed_text, rl.Vector2(speed_x, speed_y), SPEED_FONT_SIZE, 0, COLORS.WHITE)
      rl.draw_text_ex(self._font_medium, unit_text, rl.Vector2(unit_x, unit_y), SPEED_UNIT_FONT_SIZE, 0, STRIP_SECONDARY)

      divider_x = speed_x - SPEED_GROUP_GAP
      rl.draw_rectangle_rec(rl.Rectangle(divider_x - 2, center_y - 60, 2, 120), STRIP_DIVIDER)
      right = divider_x - 2 - SPEED_GROUP_GAP

    if self.is_cruise_available:
      set_x = right - SET_COLUMN_WIDTH
      label_color = self._modern_contrast.lateral_only_blue if self.is_cruise_set else STRIP_MUTED
      value_color = COLORS.WHITE if self.is_cruise_set else STRIP_MUTED
      label_size = measure_text_cached(self._font_bold, tr("SET"), SET_LABEL_FONT_SIZE, 3)
      value_size = measure_text_cached(self._font_bold, set_text, SET_VALUE_FONT_SIZE)
      column_top = center_y - (label_size.y + value_size.y) / 2
      rl.draw_text_ex(self._font_bold, tr("SET"), rl.Vector2(set_x + (SET_COLUMN_WIDTH - label_size.x) / 2, column_top),
                      SET_LABEL_FONT_SIZE, 3, label_color)
      rl.draw_text_ex(self._font_bold, set_text,
                      rl.Vector2(set_x + (SET_COLUMN_WIDTH - value_size.x) / 2, column_top + label_size.y),
                      SET_VALUE_FONT_SIZE, 0, value_color)
      right = set_x - SPEED_GROUP_GAP

    sign_width = SIGN_SIZE if ui_state.is_metric else MUTCD_SIGN_WIDTH
    self.speed_limit_renderer.render_strip(rl.Rectangle(right - sign_width, center_y - SIGN_SIZE / 2, sign_width, SIGN_SIZE))

  @staticmethod
  def _truncate(font: rl.Font, text: str, font_size: int, max_width: float) -> str:
    if max_width <= 0:
      return ""
    if measure_text_cached(font, text, font_size).x <= max_width:
      return text
    while text and measure_text_cached(font, text + "...", font_size).x > max_width:
      text = text[:-1]
    return text + "..." if text else ""

  def _render(self, rect: rl.Rectangle) -> None:
    if ui_state.modern_driving_view:
      self._render_modern(rect)
      return

    super()._render(rect)

    if ui_state.torque_bar:
      torque_rect = rect
      if ui_state.developer_ui in (DeveloperUiState.BOTTOM, DeveloperUiState.BOTH):
        torque_rect = rl.Rectangle(rect.x, rect.y, rect.width, rect.height - get_bottom_dev_ui_offset())
      self._torque_bar.render(torque_rect)

    self.developer_ui.render(rect)
    self.road_name_renderer.render(rect)
    self.speed_limit_renderer.render(rect)
    self.smart_cruise_control_renderer.render(rect)
    self.turn_signal_controller.render(rect)
    self.circular_alerts_renderer.render(rect)
    self.rocket_fuel.render(rect, ui_state.sm)
