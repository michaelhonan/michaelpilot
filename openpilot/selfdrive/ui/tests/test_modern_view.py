import numpy as np
import pyray as rl

from openpilot.selfdrive.ui.layouts import SIDEBAR_WIDTH
from openpilot.selfdrive.ui.sunnypilot.onroad.modern_road import (
  CLASSIC_LANE_LINE_HALF_WIDTH, MODERN_LANE_LINE_HALF_WIDTH, MODERN_ROAD_EDGE_MAX_ALPHA, LeadTrend,
  advance_transition, control_blue_active, instrument_blue_active, lane_line_style,
  lateral_blue_active, lead_speed_label, path_style, road_edge_alpha, slice_ribbon,
)
from openpilot.selfdrive.ui.sunnypilot.onroad.modern_view import (
  BLOCKED_RED, BOTTOM_DEV_UI_RESERVE, BRIGHT_CONTROL_BLUE, CONTROL_BLUE, DEFAULT_MODERN_CONTRAST,
  LANE_LINE_WHITE, MODERN_FRAME_THICKNESS, NEUTRAL_GEOMETRY, RIGHT_DEV_UI_RESERVE, STRIP_HEIGHT,
  AdaptiveContrast, SegmentTone, build_modern_layout, format_speed_panel_values, strip_status,
)
from openpilot.selfdrive.ui.tests.profile_onroad import resolve_profile_view


SCREEN_RECT = rl.Rectangle(0, 0, 2160, 1080)
SIDEBAR_RECT = rl.Rectangle(SIDEBAR_WIDTH, 0, SCREEN_RECT.width - SIDEBAR_WIDTH, SCREEN_RECT.height)
VIEW_RECTS = (SCREEN_RECT, SIDEBAR_RECT)


def rect_right(rect: rl.Rectangle) -> float:
  return rect.x + rect.width


def rect_bottom(rect: rl.Rectangle) -> float:
  return rect.y + rect.height


def rect_center_x(rect: rl.Rectangle) -> float:
  return rect.x + rect.width / 2


def rect_tuple(rect: rl.Rectangle) -> tuple[float, float, float, float]:
  return rect.x, rect.y, rect.width, rect.height


def rectangles_overlap(first: rl.Rectangle, second: rl.Rectangle) -> bool:
  return (first.x < rect_right(second) and rect_right(first) > second.x and
          first.y < rect_bottom(second) and rect_bottom(first) > second.y)


def test_channel_access_palette_uses_color_structs_not_predefined_tuples():
  assert isinstance(rl.WHITE, tuple)
  colors = (CONTROL_BLUE, BRIGHT_CONTROL_BLUE, BLOCKED_RED, NEUTRAL_GEOMETRY,
            LANE_LINE_WHITE, DEFAULT_MODERN_CONTRAST.control_blue,
            DEFAULT_MODERN_CONTRAST.lateral_only_blue)
  assert all(all(hasattr(color, channel) for channel in ("r", "g", "b", "a")) for color in colors)


def rect_contains(outer: rl.Rectangle, inner: rl.Rectangle) -> bool:
  return (inner.x >= outer.x and inner.y >= outer.y and
          rect_right(inner) <= rect_right(outer) and rect_bottom(inner) <= rect_bottom(outer))


def test_camera_sits_in_a_status_frame_above_the_dash_strip():
  layout = build_modern_layout(SCREEN_RECT)

  assert MODERN_FRAME_THICKNESS == 12
  assert rect_tuple(layout.camera_frame) == (15, 15, 2130, 840)
  assert rect_tuple(layout.camera) == (27, 27, 2106, 816)
  assert rect_tuple(layout.strip) == (15, 875, 2130, STRIP_HEIGHT)
  assert rect_bottom(layout.strip) == SCREEN_RECT.height - 15
  assert not rectangles_overlap(layout.camera_frame, layout.strip)


def test_strip_zones_are_ordered_inside_the_strip_without_overlap():
  for view_rect in VIEW_RECTS:
    for developer_ui in range(4):
      layout = build_modern_layout(view_rect, developer_ui)
      zones = (layout.status_zone, layout.centre_zone, layout.speed_zone)
      assert all(rect_contains(layout.strip, zone) for zone in zones)
      assert rect_right(layout.status_zone) < layout.centre_zone.x
      assert rect_right(layout.centre_zone) < layout.speed_zone.x
      assert layout.centre_zone.width > 0


def test_sidebar_narrows_the_camera_and_strip_but_keeps_both_heights():
  full = build_modern_layout(SCREEN_RECT)
  sidebar = build_modern_layout(SIDEBAR_RECT)

  assert sidebar.camera.x == full.camera.x + SIDEBAR_WIDTH
  assert sidebar.camera.width == full.camera.width - SIDEBAR_WIDTH
  assert sidebar.camera.height == full.camera.height
  assert sidebar.strip.width == full.strip.width - SIDEBAR_WIDTH
  assert rect_right(sidebar.speed_zone) == rect_right(full.speed_zone)


def test_alert_zone_is_inside_the_camera_below_the_mirror_and_clear_of_the_strip():
  for view_rect in VIEW_RECTS:
    for developer_ui in range(4):
      layout = build_modern_layout(view_rect, developer_ui)
      safe = layout.alert_safe
      assert rect_contains(layout.camera, safe)
      assert safe.y >= layout.camera.y + layout.camera.height * 0.3
      assert not rectangles_overlap(safe, layout.strip)
      assert safe.x == layout.camera.x + 40


def test_developer_ui_reserves_space_in_the_alert_zone_only():
  base = build_modern_layout(SCREEN_RECT, 0)
  bottom = build_modern_layout(SCREEN_RECT, 1)
  right = build_modern_layout(SCREEN_RECT, 2)
  both = build_modern_layout(SCREEN_RECT, 3)

  assert rect_bottom(base.alert_safe) - rect_bottom(bottom.alert_safe) == BOTTOM_DEV_UI_RESERVE
  assert rect_bottom(right.alert_safe) - rect_bottom(both.alert_safe) == BOTTOM_DEV_UI_RESERVE
  assert base.alert_safe.width - right.alert_safe.width == RIGHT_DEV_UI_RESERVE
  for layout in (bottom, right, both):
    assert rect_tuple(layout.camera) == rect_tuple(base.camera)
    assert rect_tuple(layout.strip) == rect_tuple(base.strip)


def status_tuple(status) -> tuple[SegmentTone, str, SegmentTone]:
  return status.steer_tone, status.steer_label, status.cruise_tone


def test_strip_status_separates_steering_from_cruise():
  # Lat-only car with stock ACC: steering only, then steering with the car's cruise engaged.
  assert status_tuple(strip_status(True, "lat_only", False)) == (SegmentTone.active, "STEERING", SegmentTone.off)
  assert status_tuple(strip_status(True, "engaged", True)) == (SegmentTone.active, "STEERING", SegmentTone.active)
  # MADS paused (e.g. brake pressed) while cruise stays on.
  assert status_tuple(strip_status(False, "override", True)) == (SegmentTone.paused, "PAUSED", SegmentTone.active)
  assert status_tuple(strip_status(False, "disengaged", False)) == (SegmentTone.off, "STEERING", SegmentTone.off)
  assert status_tuple(strip_status(False, "long_only", True)) == (SegmentTone.off, "STEERING", SegmentTone.active)


def test_speed_panel_values_cover_active_unset_unavailable_and_units():
  assert format_speed_panel_values(True, 62.4, 49.6, False) == ("62", "50", "mph")
  assert format_speed_panel_values(False, 255.0, 80.2, True) == ("–", "80", "km/h")
  assert format_speed_panel_values(False, -1.0, 0.0, False) == ("–", "0", "mph")


def test_lead_speed_label_shows_absolute_speed_and_trend():
  closing = lead_speed_label(True, True, 0.9, 71 / 3.6, -2.0, True)
  assert closing is not None
  assert (closing.speed, closing.unit, closing.trend) == ("71", "km/h", LeadTrend.closing)

  matching = lead_speed_label(True, True, 0.9, 22.2, -0.5, False)
  assert matching is not None
  assert (matching.speed, matching.unit, matching.trend) == ("50", "mph", LeadTrend.matching)

  pulling_away = lead_speed_label(True, True, 0.9, 25.0, 1.5, True)
  assert pulling_away is not None
  assert pulling_away.trend == LeadTrend.pulling_away

  stopped = lead_speed_label(True, True, 0.9, -0.3, -5.0, True)
  assert stopped is not None
  assert stopped.speed == "0"


def test_lead_speed_label_hides_absent_and_unconfident_vision_leads():
  assert lead_speed_label(False, True, 0.9, 20.0, 0.0, True) is None
  assert lead_speed_label(True, False, 0.3, 20.0, 0.0, True) is None
  assert lead_speed_label(True, False, 0.6, 20.0, 0.0, True) is not None
  # A radar-matched lead is trusted regardless of the vision probability.
  assert lead_speed_label(True, True, 0.1, 20.0, 0.0, True) is not None


def test_adaptive_contrast_is_smoothed_and_has_midpoint_fallback():
  unavailable = AdaptiveContrast(60).update(-1)
  contrast = AdaptiveContrast(60)
  dark = None
  for _ in range(120):
    dark = contrast.update(0)
  assert dark is not None
  first_bright = contrast.update(100)
  assert first_bright.control_blue.r - dark.control_blue.r < 3
  bright = first_bright
  for _ in range(120):
    bright = contrast.update(100)

  assert dark.text_shadow_alpha < unavailable.text_shadow_alpha < bright.text_shadow_alpha
  assert dark.control_blue.r < unavailable.control_blue.r < bright.control_blue.r
  for contrast_state in (dark, unavailable, bright):
    standard = contrast_state.control_blue
    lateral_only = contrast_state.lateral_only_blue
    assert lateral_only.b > lateral_only.g > lateral_only.r
    assert lateral_only.r + lateral_only.g + lateral_only.b > standard.r + standard.g + standard.b
  fallback = contrast.update(-1)
  assert (fallback.control_blue.r, fallback.control_blue.g, fallback.control_blue.b) == (
    unavailable.control_blue.r, unavailable.control_blue.g, unavailable.control_blue.b,
  )
  assert (fallback.lateral_only_blue.r, fallback.lateral_only_blue.g, fallback.lateral_only_blue.b) == (
    unavailable.lateral_only_blue.r, unavailable.lateral_only_blue.g, unavailable.lateral_only_blue.b,
  )
  assert fallback.text_shadow_alpha == unavailable.text_shadow_alpha
  assert not hasattr(fallback, "scrim_top_alpha")
  assert not hasattr(fallback, "scrim_bottom_alpha")


def test_path_style_covers_control_states_master_fallback_and_special_modes():
  assert path_style(True, "engaged", False, False) == "blue"
  assert path_style(True, "lat_only", False, False) == "blue"
  assert path_style(True, "override", False, False) == "blue"
  for status in ("long_only", "disengaged"):
    assert path_style(True, status, False, False) == "neutral"
  for status in ("engaged", "lat_only", "long_only", "override", "disengaged"):
    assert path_style(False, status, False, False) == "classic"
    assert path_style(True, status, False, True) == "experimental"
    assert path_style(True, status, True, True) == "rainbow"


def test_lane_lines_follow_standard_blue_path_and_stay_neutral_in_special_modes():
  for status in ("engaged", "lat_only", "override"):
    assert lane_line_style(True, status, False, False) == "blue"
  for status in ("long_only", "disengaged"):
    assert lane_line_style(True, status, False, False) == "neutral"
  for status in ("engaged", "lat_only", "override", "long_only", "disengaged"):
    assert lane_line_style(True, status, True, False) == "neutral"
    assert lane_line_style(True, status, False, True) == "neutral"
    assert lane_line_style(False, status, False, False) == "classic"


def test_modern_lane_width_and_road_edge_alpha_policy_preserve_classic_values():
  assert CLASSIC_LANE_LINE_HALF_WIDTH == 0.025
  assert MODERN_LANE_LINE_HALF_WIDTH == 0.040
  assert MODERN_ROAD_EDGE_MAX_ALPHA == 0.35
  assert road_edge_alpha(0.0, True) == 0.35
  assert road_edge_alpha(0.5, True) == 0.175
  assert road_edge_alpha(1.0, True) == 0.0
  assert road_edge_alpha(-1.0, True) == 0.35
  assert road_edge_alpha(0.0, False) == 1.0
  assert road_edge_alpha(0.5, False) == 0.5


def test_modern_active_blue_policy_covers_steering_and_longitudinal_overrides():
  for status in ("engaged", "lat_only", "long_only", "override"):
    assert instrument_blue_active(status)
  assert instrument_blue_active("disengaged", longitudinal_override=True)
  assert not instrument_blue_active("disengaged")

  assert control_blue_active("engaged")
  assert control_blue_active("long_only")
  assert control_blue_active("override")
  assert control_blue_active("disengaged", longitudinal_override=True)
  assert not control_blue_active("lat_only")
  assert not control_blue_active("disengaged")

  assert lateral_blue_active("engaged")
  assert lateral_blue_active("lat_only")
  assert lateral_blue_active("override")
  assert not lateral_blue_active("long_only")
  assert not lateral_blue_active("disengaged")


def test_engagement_transition_reverses_from_current_progress():
  progress = 0.0
  active = True
  for _ in range(18):
    progress, active = advance_transition(progress, 1.0, 0.6, 1 / 60)
  midpoint = progress
  reversed_progress, active = advance_transition(progress, 0.0, 0.35, 1 / 60)

  assert active
  assert 0.0 < reversed_progress < midpoint < 1.0


def test_sweep_ribbon_slice_preserves_polygon_order():
  left = np.column_stack((np.zeros(10), np.arange(10)))
  right = np.column_stack((np.ones(10), np.arange(10)))[::-1]
  ribbon = np.vstack((left, right)).astype(np.float32)
  sliced = slice_ribbon(ribbon, 0.25, 0.75)

  count = len(sliced) // 2
  assert count >= 2
  assert np.all(sliced[:count, 0] == 0)
  assert np.all(sliced[count:, 0] == 1)


def test_profile_view_selection_is_explicit_and_device_safe():
  assert resolve_profile_view(True, None) == "modern"
  assert resolve_profile_view(True, "classic") == "classic"
  assert resolve_profile_view(False, None) == "classic"
  try:
    resolve_profile_view(False, "modern")
  except ValueError:
    pass
  else:
    raise AssertionError("mici must reject the modern driving view")
