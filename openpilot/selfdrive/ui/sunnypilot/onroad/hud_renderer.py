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
from openpilot.selfdrive.ui.sunnypilot.onroad.modern_road import instrument_blue_active
from openpilot.selfdrive.ui.sunnypilot.onroad.modern_view import (
  DEFAULT_MODERN_CONTRAST, MODERN_SURFACES, MODERN_TYPOGRAPHY, ModernContrast, build_modern_layout,
  format_speed_panel_values,
)
from openpilot.selfdrive.ui.ui_state import ui_state, UIStatus
from openpilot.selfdrive.ui.onroad.hud_renderer import HudRenderer, UI_CONFIG, FONT_SIZES, COLORS, CRUISE_DISABLED_CHAR
from openpilot.system.ui.lib.application import gui_app, FontWeight
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.lib.text_measure import measure_text_cached

SLA_ACTIVE_COLOR = rl.Color(0x91, 0x9b, 0x95, 0xff)


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
    self._font_audiowide = gui_app.font(FontWeight.AUDIOWIDE)

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

  def _draw_speed_panel_modern(self, rect: rl.Rectangle) -> None:
    long_override = ui_state.sm['carControl'].cruiseControl.override
    control_active = instrument_blue_active(ui_state.status.value, long_override)
    border = self._modern_contrast.control_blue if control_active else COLORS.BORDER_TRANSLUCENT

    rl.draw_rectangle_rounded(rect, MODERN_SURFACES.panel_roundness, 10,
                              rl.Color(0, 0, 0, MODERN_SURFACES.panel_alpha))
    rl.draw_rectangle_rounded_lines_ex(rect, MODERN_SURFACES.panel_roundness, 10,
                                       MODERN_SURFACES.panel_border_width, border)

    label_color = self._modern_contrast.control_blue if control_active else COLORS.GREY
    set_label_color = label_color if self.is_cruise_set else rl.Color(label_color.r, label_color.g, label_color.b, 90)
    set_value_color = COLORS.WHITE if self.is_cruise_set else rl.Color(255, 255, 255, 90)
    value_shadow = rl.Color(0, 0, 0, self._modern_contrast.text_shadow_alpha)

    set_center_x = rect.x + rect.width * 0.25
    speed_center_x = rect.x + rect.width * 0.75
    label_y = rect.y + 24
    value_y = rect.y + 70

    self._draw_modern_text_centered(tr("SET"), set_center_x, label_y,
                                    self._font_audiowide, MODERN_TYPOGRAPHY.panel_label, set_label_color)
    self._draw_modern_text_centered(tr("SPEED"), speed_center_x, label_y,
                                    self._font_audiowide, MODERN_TYPOGRAPHY.panel_label, label_color)

    set_speed_text, speed_text, unit_text = format_speed_panel_values(
      self.is_cruise_set, self.set_speed, self.speed_renderer.speed, ui_state.is_metric,
    )
    self._draw_modern_text_centered(set_speed_text, set_center_x + 3, value_y + 3,
                                    self._font_audiowide, MODERN_TYPOGRAPHY.panel_value, value_shadow)
    self._draw_modern_text_centered(set_speed_text, set_center_x, value_y,
                                    self._font_audiowide, MODERN_TYPOGRAPHY.panel_value, set_value_color)
    self._draw_modern_text_centered(speed_text, speed_center_x + 3, value_y + 3,
                                    self._font_audiowide, MODERN_TYPOGRAPHY.panel_value, value_shadow)
    self._draw_modern_text_centered(speed_text, speed_center_x, value_y,
                                    self._font_audiowide, MODERN_TYPOGRAPHY.panel_value, COLORS.WHITE)

    unit_text = tr(unit_text)
    self._draw_modern_text_centered(unit_text, speed_center_x, rect.y + rect.height - 45,
                                    self._font_medium, MODERN_TYPOGRAPHY.panel_unit,
                                    COLORS.WHITE_TRANSLUCENT)

  @staticmethod
  def _draw_modern_text_centered(text: str, center_x: float, y: float, font: rl.Font,
                                 font_size: int, color: rl.Color) -> None:
    text_size = measure_text_cached(font, text, font_size)
    rl.draw_text_ex(font, text, rl.Vector2(center_x - text_size.x / 2, y), font_size, 0, color)

  def _render_modern(self, rect: rl.Rectangle) -> None:
    layout = build_modern_layout(rect, ui_state.developer_ui)

    self._draw_speed_panel_modern(layout.speed_panel)

    self._exp_button.modern_style = True
    self._exp_button.modern_color = self._modern_contrast.control_blue
    self._exp_button.render(layout.experimental_control)

    if ui_state.torque_bar:
      self._torque_bar.render(rl.Rectangle(rect.x, rect.y, rect.width, rect.height - get_bottom_dev_ui_offset()))

    self.developer_ui.render(rect)
    self.road_name_renderer.render_modern(layout.road_name)
    self.smart_cruise_control_renderer.render_modern(layout.smart_cruise, self._modern_contrast.control_blue)
    self.turn_signal_controller.render_modern(layout.left_signal, layout.right_signal)
    self.circular_alerts_renderer.render_modern(layout.circular_alert)
    self.rocket_fuel.render_modern(layout.acceleration_bar, ui_state.sm)

  def _render(self, rect: rl.Rectangle) -> None:
    if ui_state.modern_driving_view:
      self._render_modern(rect)
      return

    self._exp_button.modern_style = False
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
