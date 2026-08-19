"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from dataclasses import dataclass
import math

import pyray as rl
from openpilot.selfdrive.ui.onroad.alert_renderer import AlertRenderer, AlertSize, ALERT_FONT_MEDIUM, ALERT_FONT_BIG, \
  ALERT_FONT_SMALL, ALERT_MARGIN, ALERT_HEIGHTS, ALERT_PADDING, Alert
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.selfdrive.ui.sunnypilot.onroad.modern_view import build_modern_layout
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.lib.wrap_text import wrap_text

ALERT_LINE_SPACING = 15
MODERN_ALERT_PADDING = 40
MODERN_COMPACT_ALERT_PADDING = 24
MODERN_FONT_STEP = 2
MODERN_SMALL_MIN_FONT = 48
MODERN_MID_MIN_TITLE_FONT = 56
MODERN_MID_MIN_BODY_FONT = 44
MODERN_COMPACT_MID_MIN_TITLE_FONT = 48
MODERN_COMPACT_MID_MIN_BODY_FONT = 38


@dataclass(frozen=True)
class ModernAlertLayout:
  surface: rl.Rectangle
  title_lines: tuple[str, ...]
  body_lines: tuple[str, ...]
  title_size: int
  body_size: int
  title_line_height: float
  body_line_height: float


class AlertRendererSP(AlertRenderer):
  def __init__(self):
    super().__init__()
    self._modern_fit_cache: dict[tuple, tuple | None] = {}

  def _render(self, rect: rl.Rectangle) -> None:
    if not ui_state.modern_driving_view:
      super()._render(rect)
      return

    alert = self.get_alert(ui_state.sm)
    ui_state.onroad_brightness_handle_alerts(ui_state, alert)
    if not alert:
      return

    if alert.size == AlertSize.full:
      self._draw_full_alert(rect, alert)
      return

    layout = self._layout_modern_alert(rect, alert)
    if layout is None:
      # Never clip safety text. Unexpected oversized noncritical alerts use the
      # established full-screen presentation for this occurrence.
      promoted = Alert(text1=alert.text1, text2=alert.text2, size=AlertSize.full, status=alert.status)
      self._draw_full_alert(rect, promoted)
      return

    self._draw_background(layout.surface, alert)
    self._draw_modern_text(layout)

  def _draw_full_alert(self, rect: rl.Rectangle, alert: Alert) -> None:
    self._draw_background(rect, alert)
    text_rect = rl.Rectangle(rect.x + ALERT_PADDING, rect.y + ALERT_PADDING,
                             rect.width - 2 * ALERT_PADDING, rect.height - 2 * ALERT_PADDING)
    self._draw_text(text_rect, alert)

  def _layout_modern_alert(self, rect: rl.Rectangle, alert: Alert) -> ModernAlertLayout | None:
    safe = build_modern_layout(rect, ui_state.developer_ui).alert_safe
    fit = self._fit_modern_alert(alert, int(safe.width), int(safe.height))
    if fit is None:
      return None

    title_lines, body_lines, title_size, body_size, title_height, body_height, surface_height = fit
    surface = rl.Rectangle(safe.x, safe.y + safe.height - surface_height, safe.width, surface_height)
    return ModernAlertLayout(surface, title_lines, body_lines, title_size, body_size, title_height, body_height)

  def _fit_modern_alert(self, alert: Alert, width: int, max_height: int) -> tuple | None:
    key = (alert.text1, alert.text2, alert.size, width, max_height)
    if key in self._modern_fit_cache:
      return self._modern_fit_cache[key]

    if alert.size == AlertSize.small:
      start_title, start_body = ALERT_FONT_MEDIUM, 0
      fit_specs = (
        (MODERN_ALERT_PADDING, MODERN_SMALL_MIN_FONT, 0),
        (MODERN_COMPACT_ALERT_PADDING, MODERN_SMALL_MIN_FONT, 0),
      )
    else:
      start_title, start_body = ALERT_FONT_BIG, ALERT_FONT_SMALL
      fit_specs = (
        (MODERN_ALERT_PADDING, MODERN_MID_MIN_TITLE_FONT, MODERN_MID_MIN_BODY_FONT),
        (MODERN_COMPACT_ALERT_PADDING, MODERN_COMPACT_MID_MIN_TITLE_FONT, MODERN_COMPACT_MID_MIN_BODY_FONT),
      )

    fit = None
    for padding, min_title, min_body in fit_specs:
      wrap_width = width - 2 * padding
      if wrap_width <= 0 or max_height <= 2 * padding:
        continue
      max_steps = max((start_title - min_title) // MODERN_FONT_STEP,
                      (start_body - min_body) // MODERN_FONT_STEP)
      for step in range(max_steps + 1):
        title_size = max(min_title, start_title - step * MODERN_FONT_STEP)
        body_size = max(min_body, start_body - step * MODERN_FONT_STEP)
        title_lines = tuple(wrap_text(self.font_bold, alert.text1, title_size, wrap_width))
        body_lines = tuple(wrap_text(self.font_regular, alert.text2, body_size, wrap_width)) if alert.text2 and body_size else ()
        title_height = measure_text_cached(self.font_bold, "A", title_size).y
        body_height = measure_text_cached(self.font_regular, "A", body_size).y if body_lines else 0.0
        text_height = len(title_lines) * title_height
        if body_lines:
          text_height += ALERT_LINE_SPACING + len(body_lines) * body_height
        surface_height = math.ceil(text_height + 2 * padding)
        if surface_height <= max_height:
          fit = (title_lines, body_lines, title_size, body_size, title_height, body_height, surface_height)
          break
      if fit is not None:
        break

    if len(self._modern_fit_cache) >= 32:
      self._modern_fit_cache.clear()
    self._modern_fit_cache[key] = fit
    return fit

  def _draw_modern_text(self, layout: ModernAlertLayout) -> None:
    text_height = len(layout.title_lines) * layout.title_line_height
    if layout.body_lines:
      text_height += ALERT_LINE_SPACING + len(layout.body_lines) * layout.body_line_height
    curr_y = layout.surface.y + (layout.surface.height - text_height) / 2

    for line in layout.title_lines:
      self._draw_line_centered(line, rl.Rectangle(layout.surface.x, curr_y, layout.surface.width,
                                                   layout.title_line_height),
                               self.font_bold, layout.title_size)
      curr_y += layout.title_line_height

    if layout.body_lines:
      curr_y += ALERT_LINE_SPACING
      for line in layout.body_lines:
        self._draw_line_centered(line, rl.Rectangle(layout.surface.x, curr_y, layout.surface.width,
                                                     layout.body_line_height),
                                 self.font_regular, layout.body_size)
        curr_y += layout.body_line_height

  def _draw_text(self, rect: rl.Rectangle, alert: Alert) -> None:
    if alert.size == AlertSize.small:
      self._draw_multiline_centered(alert.text1, rect, self.font_bold, ALERT_FONT_MEDIUM)

    elif alert.size == AlertSize.mid:
      wrap_width = int(rect.width)
      lines1 = wrap_text(self.font_bold, alert.text1, ALERT_FONT_BIG, wrap_width)
      lines2 = wrap_text(self.font_regular, alert.text2, ALERT_FONT_SMALL, wrap_width) if alert.text2 else []

      total_text_height = len(lines1) * measure_text_cached(self.font_bold, "A", ALERT_FONT_BIG).y
      if lines2:
        total_text_height += ALERT_LINE_SPACING + len(lines2) * measure_text_cached(self.font_regular, "A", ALERT_FONT_SMALL).y

      curr_y = rect.y + (rect.height - total_text_height) / 2

      for line in lines1:
        line_height = measure_text_cached(self.font_bold, alert.text1, ALERT_FONT_BIG).y
        self._draw_line_centered(line, rl.Rectangle(rect.x, curr_y, rect.width, line_height), self.font_bold, ALERT_FONT_BIG)
        curr_y += line_height

      if lines2:
        curr_y += ALERT_LINE_SPACING
        for line in lines2:
          line_height = measure_text_cached(self.font_regular, alert.text2, ALERT_FONT_SMALL).y
          self._draw_line_centered(line, rl.Rectangle(rect.x, curr_y, rect.width, line_height), self.font_regular, ALERT_FONT_SMALL)
          curr_y += line_height

    else:
      super()._draw_text(rect, alert)

  def _draw_multiline_centered(self, text, rect, font, font_size, color=rl.WHITE) -> None:
    lines = wrap_text(font, text, font_size, rect.width)
    line_height = measure_text_cached(font, text, font_size).y
    total_height = len(lines) * line_height
    curr_y = rect.y + (rect.height - total_height) / 2
    for line in lines:
      self._draw_line_centered(line, rl.Rectangle(rect.x, curr_y, rect.width, line_height), font, font_size, color)
      curr_y += line_height

  def _draw_line_centered(self, text, rect, font, font_size, color=rl.WHITE) -> None:
    text_size = measure_text_cached(font, text, font_size)
    x = rect.x + (rect.width - text_size.x) / 2
    y = rect.y
    rl.draw_text_ex(font, text, rl.Vector2(x, y), font_size, 0, color)

  def _get_alert_rect(self, rect: rl.Rectangle, size: int) -> rl.Rectangle:
    if size == AlertSize.full:
      return rect

    if ui_state.modern_driving_view:
      safe = build_modern_layout(rect, ui_state.developer_ui).alert_safe
      alert = self.get_alert(ui_state.sm)
      if alert:
        layout = self._layout_modern_alert(rect, alert)
        return rect if layout is None else layout.surface
      h = min(float(ALERT_HEIGHTS.get(size, 271)), safe.height)
      return rl.Rectangle(safe.x, safe.y + safe.height - h, safe.width, h)

    dev_ui_info = ui_state.developer_ui
    v_adjustment = 40 if dev_ui_info in {2, 3} and size != AlertSize.full else 0
    h_adjustment = 230 if dev_ui_info in {1, 3} and size != AlertSize.full else 0

    w = int(rect.width - ALERT_MARGIN * 2 - h_adjustment)
    h = self._calculate_dynamic_height(size, w)
    return rl.Rectangle(rect.x + ALERT_MARGIN, rect.y + rect.height - h + ALERT_MARGIN - v_adjustment, w,
                        h - ALERT_MARGIN * 2)

  def _calculate_dynamic_height(self, size: int, width: int) -> int:
    alert = self.get_alert(ui_state.sm)
    if not alert:
      return ALERT_HEIGHTS.get(size, 271)

    height = 2 * ALERT_PADDING
    wrap_width = width - 2 * ALERT_PADDING

    if size == AlertSize.small:
      lines = wrap_text(self.font_bold, alert.text1, ALERT_FONT_MEDIUM, wrap_width)
      line_height = measure_text_cached(self.font_bold, alert.text1, ALERT_FONT_MEDIUM).y
      height += int(len(lines) * line_height)
    elif size == AlertSize.mid:
      lines1 = wrap_text(self.font_bold, alert.text1, ALERT_FONT_BIG, wrap_width)
      line_height1 = measure_text_cached(self.font_bold, alert.text1, ALERT_FONT_BIG).y
      height += int(len(lines1) * line_height1)

      if alert.text2:
        lines2 = wrap_text(self.font_regular, alert.text2, ALERT_FONT_SMALL, wrap_width)
        line_height2 = measure_text_cached(self.font_regular, alert.text2, ALERT_FONT_SMALL).y
        height += int(ALERT_LINE_SPACING + len(lines2) * line_height2)
    else:
      height = ALERT_HEIGHTS.get(size, 271)

    return int(height)
