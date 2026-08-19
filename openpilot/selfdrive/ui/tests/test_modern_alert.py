import textwrap

import pyray as rl

from openpilot.selfdrive.ui.onroad.alert_renderer import Alert, AlertSize, AlertStatus
from openpilot.selfdrive.ui.sunnypilot.onroad import alert_renderer as alert_renderer_module
from openpilot.selfdrive.ui.sunnypilot.onroad.alert_renderer import (
  MODERN_COMPACT_MID_MIN_BODY_FONT, MODERN_COMPACT_MID_MIN_TITLE_FONT,
  MODERN_MID_MIN_BODY_FONT, MODERN_MID_MIN_TITLE_FONT, AlertRendererSP,
)
from openpilot.selfdrive.ui.sunnypilot.onroad.modern_view import build_modern_layout


def make_renderer(monkeypatch):
  renderer = AlertRendererSP.__new__(AlertRendererSP)
  renderer.font_bold = object()
  renderer.font_regular = object()
  renderer._modern_fit_cache = {}

  def fake_wrap(_font, text, font_size, width):
    chars_per_line = max(1, int(width / (font_size * 0.55)))
    return textwrap.wrap(text, chars_per_line) or [""]

  monkeypatch.setattr(alert_renderer_module, "wrap_text", fake_wrap)
  monkeypatch.setattr(alert_renderer_module, "measure_text_cached",
                      lambda _font, _text, font_size: rl.Vector2(font_size * 0.55, font_size * 1.1))
  return renderer


def test_long_known_medium_alert_fits_inside_protected_height(monkeypatch):
  renderer = make_renderer(monkeypatch)
  alert = Alert(
    text1="Smart/Adaptive Cruise Control: OFF",
    text2="Manual Speed Control Required",
    size=AlertSize.mid,
    status=AlertStatus.userPrompt,
  )

  fit = renderer._fit_modern_alert(alert, 720, 420)
  assert fit is not None
  _, _, title_size, body_size, _, _, surface_height = fit
  assert title_size >= MODERN_MID_MIN_TITLE_FONT
  assert body_size >= MODERN_MID_MIN_BODY_FONT
  assert surface_height <= 420


def test_known_medium_alert_fits_sidebar_and_right_developer_ui_gap(monkeypatch):
  renderer = make_renderer(monkeypatch)
  alert = Alert(
    text1="Smart/Adaptive Cruise Control: OFF",
    text2="Manual Speed Control Required",
    size=AlertSize.mid,
    status=AlertStatus.userPrompt,
  )
  layout = build_modern_layout(rl.Rectangle(420, 30, 1680, 1020), developer_ui=2)

  assert layout.alert_safe.width == 502
  fit = renderer._fit_modern_alert(alert, int(layout.alert_safe.width), int(layout.alert_safe.height))
  assert fit is not None
  _, _, title_size, body_size, _, _, surface_height = fit
  assert title_size >= MODERN_COMPACT_MID_MIN_TITLE_FONT
  assert body_size >= MODERN_COMPACT_MID_MIN_BODY_FONT
  assert surface_height <= layout.alert_safe.height


def test_oversized_medium_alert_requests_full_screen_fallback(monkeypatch):
  renderer = make_renderer(monkeypatch)
  alert = Alert(
    text1=" ".join(["Unexpected"] * 200),
    text2=" ".join(["safety information"] * 200),
    size=AlertSize.mid,
    status=AlertStatus.userPrompt,
  )

  assert renderer._fit_modern_alert(alert, 720, 420) is None
