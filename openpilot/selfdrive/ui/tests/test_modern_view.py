from itertools import pairwise

import numpy as np
import pyray as rl

from openpilot.selfdrive.ui.layouts import SIDEBAR_WIDTH
from openpilot.selfdrive.ui.sunnypilot.onroad.modern_road import (
  CLASSIC_LANE_LINE_HALF_WIDTH, MODERN_LANE_LINE_HALF_WIDTH, MODERN_ROAD_EDGE_MAX_ALPHA,
  LaneChangeAnimator, LaneChangeIntent, LaneChangeVisualInput, LaneChangeVisualPhase,
  advance_transition, control_blue_active, instrument_blue_active, lane_line_style,
  lateral_blue_active, path_style, road_edge_alpha, slice_ribbon,
)
from openpilot.selfdrive.ui.sunnypilot.onroad.modern_view import (
  BLOCKED_RED, BOTTOM_DEV_UI_RESERVE, BRIGHT_CONTROL_BLUE, CONTROL_BLUE, DEFAULT_MODERN_CONTRAST,
  ELEMENT_GAP, LANE_LINE_WHITE, MODERN_FRAME_THICKNESS, NEUTRAL_GEOMETRY, RIGHT_DEV_UI_RESERVE, ROAD_NAME_HEIGHT,
  SPEED_PANEL_HEIGHT, SPEED_PANEL_WIDTH, AdaptiveContrast, build_modern_layout,
  format_speed_panel_values,
)
from openpilot.selfdrive.ui.tests.profile_onroad import resolve_profile_view


SCREEN_RECT = rl.Rectangle(0, 0, 2160, 1080)
CONTENT_RECT = rl.Rectangle(
  SCREEN_RECT.x + MODERN_FRAME_THICKNESS,
  SCREEN_RECT.y + MODERN_FRAME_THICKNESS,
  SCREEN_RECT.width - 2 * MODERN_FRAME_THICKNESS,
  SCREEN_RECT.height - 2 * MODERN_FRAME_THICKNESS,
)
SIDEBAR_CONTENT_RECT = rl.Rectangle(
  SIDEBAR_WIDTH + MODERN_FRAME_THICKNESS,
  MODERN_FRAME_THICKNESS,
  SCREEN_RECT.width - SIDEBAR_WIDTH - 2 * MODERN_FRAME_THICKNESS,
  SCREEN_RECT.height - 2 * MODERN_FRAME_THICKNESS,
)


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


def test_modern_frame_is_half_classic_thickness_and_content_uses_new_inset():
  assert MODERN_FRAME_THICKNESS == 15
  assert rect_tuple(CONTENT_RECT) == (15, 15, 2130, 1050)
  assert rect_tuple(SIDEBAR_CONTENT_RECT) == (315, 15, 1830, 1050)


def test_speed_panel_is_fixed_bottom_right_and_replaces_old_regions():
  layout = build_modern_layout(CONTENT_RECT)

  assert rect_tuple(layout.speed_panel) == (
    CONTENT_RECT.x + CONTENT_RECT.width - 48 - SPEED_PANEL_WIDTH,
    CONTENT_RECT.y + CONTENT_RECT.height - 42 - SPEED_PANEL_HEIGHT,
    SPEED_PANEL_WIDTH,
    SPEED_PANEL_HEIGHT,
  )
  assert not hasattr(layout, "current_speed")
  assert not hasattr(layout, "set_speed")
  assert not hasattr(layout, "speed_limit")
  assert not hasattr(layout, "speed_zone")


def test_speed_panel_values_cover_active_unset_unavailable_and_units():
  assert format_speed_panel_values(True, 62.4, 49.6, False) == ("62", "50", "mph")
  assert format_speed_panel_values(False, 255.0, 80.2, True) == ("–", "80", "km/h")
  assert format_speed_panel_values(False, -1.0, 0.0, False) == ("–", "0", "mph")


def test_road_name_fills_the_gap_between_bottom_controls_with_consistent_padding():
  for content_rect in (CONTENT_RECT, SIDEBAR_CONTENT_RECT):
    for developer_ui in range(4):
      layout = build_modern_layout(content_rect, developer_ui)
      assert layout.road_name.x == rect_right(layout.experimental_control) + ELEMENT_GAP
      assert rect_right(layout.road_name) == layout.speed_panel.x - ELEMENT_GAP
      assert layout.road_name.height == ROAD_NAME_HEIGHT
      assert not rectangles_overlap(layout.road_name, layout.experimental_control)
      assert not rectangles_overlap(layout.road_name, layout.speed_panel)


def test_developer_ui_reserves_bottom_and_right_space():
  base = build_modern_layout(CONTENT_RECT, 0)
  bottom = build_modern_layout(CONTENT_RECT, 1)
  right = build_modern_layout(CONTENT_RECT, 2)
  both = build_modern_layout(CONTENT_RECT, 3)

  assert rect_bottom(base.speed_panel) - rect_bottom(bottom.speed_panel) == BOTTOM_DEV_UI_RESERVE
  assert rect_bottom(right.speed_panel) - rect_bottom(both.speed_panel) == BOTTOM_DEV_UI_RESERVE
  assert rect_right(base.speed_panel) - rect_right(right.speed_panel) == RIGHT_DEV_UI_RESERVE
  assert rect_right(bottom.speed_panel) - rect_right(both.speed_panel) == RIGHT_DEV_UI_RESERVE
  assert rect_bottom(base.road_name) - rect_bottom(bottom.road_name) == BOTTOM_DEV_UI_RESERVE
  assert base.road_name.width - right.road_name.width == RIGHT_DEV_UI_RESERVE


def test_sidebar_width_recomputes_regions_without_alert_speed_overlap():
  sidebar_rect = SIDEBAR_CONTENT_RECT
  for developer_ui in range(4):
    layout = build_modern_layout(sidebar_rect, developer_ui)
    assert rect_right(layout.alert_safe) <= layout.speed_panel.x
    assert layout.alert_safe.x >= rect_right(layout.experimental_control)
    assert rect_bottom(layout.alert_safe) == rect_bottom(layout.experimental_control)
    assert rect_right(layout.speed_panel) <= rect_right(sidebar_rect)


def test_required_regions_stay_below_mirror_occlusion_zone():
  lhd_layout = build_modern_layout(CONTENT_RECT)
  rhd_layout = build_modern_layout(CONTENT_RECT)
  occlusion_bottom = CONTENT_RECT.y + CONTENT_RECT.height * 0.3

  assert rect_tuple(lhd_layout.experimental_control) == rect_tuple(rhd_layout.experimental_control)
  required = [lhd_layout.speed_panel, lhd_layout.road_name, lhd_layout.experimental_control,
              lhd_layout.smart_cruise, lhd_layout.alert_safe,
              lhd_layout.left_signal, lhd_layout.right_signal]
  assert all(region.y >= occlusion_bottom for region in required)
  assert rect_bottom(lhd_layout.alert_safe) == rect_bottom(lhd_layout.experimental_control)


def test_wheel_uses_former_driver_monitoring_position_and_obsolete_regions_are_removed():
  layout = build_modern_layout(CONTENT_RECT)

  assert rect_tuple(layout.experimental_control) == (
    CONTENT_RECT.x + 48,
    CONTENT_RECT.y + CONTENT_RECT.height - 42 - 192,
    192,
    192,
  )
  assert not hasattr(layout, "driver_monitoring")
  assert not hasattr(layout, "scrim")


def test_alert_is_centered_in_bottom_gap_between_wheel_and_speed_cluster():
  content_rects = (CONTENT_RECT, SIDEBAR_CONTENT_RECT)
  for content_rect in content_rects:
    for developer_ui in range(4):
      layout = build_modern_layout(content_rect, developer_ui)
      gap_left = rect_right(layout.experimental_control) + 28
      gap_right = layout.speed_panel.x - 28
      available_width = max(1.0, gap_right - gap_left)

      assert layout.alert_safe.width == min(900.0, available_width)
      assert rect_center_x(layout.alert_safe) == gap_left + available_width / 2
      assert rect_bottom(layout.alert_safe) == rect_bottom(layout.experimental_control)
      assert not rectangles_overlap(layout.alert_safe, layout.experimental_control)
      assert not rectangles_overlap(layout.alert_safe, layout.speed_panel)
      assert rectangles_overlap(layout.alert_safe, layout.road_name)


def test_bottom_left_utility_regions_never_collide():
  content_rects = (CONTENT_RECT, SIDEBAR_CONTENT_RECT)
  for content_rect in content_rects:
    for developer_ui in range(4):
      layout = build_modern_layout(content_rect, developer_ui)
      utility_regions = (layout.experimental_control, layout.smart_cruise, layout.circular_alert)
      for index, first in enumerate(utility_regions):
        assert all(not rectangles_overlap(first, second) for second in utility_regions[index + 1:])
      assert rect_bottom(layout.smart_cruise) + 96 == layout.circular_alert.y
      assert all(not rectangles_overlap(region, layout.speed_panel) for region in utility_regions)


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


def test_lane_change_request_has_no_visual_output():
  animator = LaneChangeAnimator()
  output = animator.update(LaneChangeVisualInput(LaneChangeIntent.requested, True, 0.0), 1 / 60)
  assert output.phase == LaneChangeVisualPhase.idle
  assert output.lock_sweep_position is None


def test_lane_change_completion_uses_reverse_lock_sweep_once():
  animator = LaneChangeAnimator()
  active = LaneChangeVisualInput(LaneChangeIntent.active, True, 0.5)
  completed = LaneChangeVisualInput(LaneChangeIntent.off, True, 0.01)
  for _ in range(30):
    animator.update(active, 1 / 60)

  output = animator.update(completed, 1 / 60)
  assert output.phase == LaneChangeVisualPhase.completing
  assert output.lock_sweep_position is not None
  assert 0.0 < output.lock_sweep_position < 1.0

  lock_positions = [output.lock_sweep_position]
  for _ in range(23):
    output = animator.update(completed, 1 / 60)
    if output.lock_sweep_position is not None:
      lock_positions.append(output.lock_sweep_position)
  assert all(first > second for first, second in pairwise(lock_positions))
  assert output.phase == LaneChangeVisualPhase.idle
  assert output.lock_sweep_position is None
  assert animator.update(completed, 1 / 60).lock_sweep_position is None


def test_lane_change_cancel_and_control_loss_have_no_visual_output():
  animator = LaneChangeAnimator()
  animator.update(LaneChangeVisualInput(LaneChangeIntent.requested, True, 0.0), 1 / 60)
  output = animator.update(LaneChangeVisualInput(LaneChangeIntent.off, True, None), 1 / 60)
  assert output.phase == LaneChangeVisualPhase.idle
  assert output.lock_sweep_position is None

  animator = LaneChangeAnimator()
  active = LaneChangeVisualInput(LaneChangeIntent.active, True, 0.6)
  interrupted = LaneChangeVisualInput(LaneChangeIntent.off, False, 0.6)
  for _ in range(35):
    animator.update(active, 1 / 60)
  output = animator.update(interrupted, 1 / 60)
  assert output.phase == LaneChangeVisualPhase.idle
  assert output.lock_sweep_position is None


def test_lane_change_control_loss_overrides_finishing_and_completion():
  animator = LaneChangeAnimator()
  active = LaneChangeVisualInput(LaneChangeIntent.active, True, 0.5)
  for _ in range(30):
    animator.update(active, 1 / 60)

  finishing_without_control = LaneChangeVisualInput(LaneChangeIntent.finishing, False, 0.01)
  output = animator.update(finishing_without_control, 1 / 60)
  assert output.phase == LaneChangeVisualPhase.idle
  assert output.lock_sweep_position is None

  animator = LaneChangeAnimator()
  for _ in range(30):
    animator.update(active, 1 / 60)
  completed = LaneChangeVisualInput(LaneChangeIntent.off, True, 0.01)
  assert animator.update(completed, 1 / 60).phase == LaneChangeVisualPhase.completing

  completion_interrupted = LaneChangeVisualInput(LaneChangeIntent.off, False, 0.01)
  output = animator.update(completion_interrupted, 1 / 60)
  assert output.phase == LaneChangeVisualPhase.idle
  assert output.lock_sweep_position is None


def test_lane_change_short_active_state_does_not_false_complete():
  animator = LaneChangeAnimator()
  active = LaneChangeVisualInput(LaneChangeIntent.active, True, 0.5)
  for _ in range(26):
    animator.update(active, 1 / 60)

  output = animator.update(
    LaneChangeVisualInput(LaneChangeIntent.off, True, 0.01),
    1 / 60,
  )
  assert output.phase == LaneChangeVisualPhase.idle
  assert output.lock_sweep_position is None

  animator = LaneChangeAnimator()
  for _ in range(27):
    animator.update(active, 1 / 60)
  output = animator.update(
    LaneChangeVisualInput(LaneChangeIntent.off, True, 0.01),
    1 / 60,
  )
  assert output.phase == LaneChangeVisualPhase.completing


def test_lane_change_missing_desire_data_fails_conservatively_without_confirmation():
  animator = LaneChangeAnimator()
  active = LaneChangeVisualInput(LaneChangeIntent.active, True, 0.5)
  for _ in range(35):
    animator.update(active, 1 / 60)
  output = animator.update(
    LaneChangeVisualInput(LaneChangeIntent.off, True, None),
    1 / 60,
  )
  assert output.phase == LaneChangeVisualPhase.idle
  assert output.lock_sweep_position is None


def test_lane_change_legacy_finishing_starts_completion_confirmation():
  animator = LaneChangeAnimator()
  active = LaneChangeVisualInput(LaneChangeIntent.active, True, 0.5)
  finishing = LaneChangeVisualInput(LaneChangeIntent.finishing, True, 0.0)

  output = animator.update(finishing, 1 / 60)
  assert output.phase == LaneChangeVisualPhase.idle
  assert output.lock_sweep_position is None

  animator = LaneChangeAnimator()
  animator.update(active, 1 / 60)
  output = animator.update(finishing, 1 / 60)
  assert output.phase == LaneChangeVisualPhase.completing
  assert output.lock_sweep_position is not None


def test_lane_change_completion_duration_is_frame_rate_independent_and_disable_resets():
  for fps in (30, 60):
    animator = LaneChangeAnimator()
    animator.update(LaneChangeVisualInput(LaneChangeIntent.active, True, 0.5), 1 / fps)
    output = animator.update(LaneChangeVisualInput(LaneChangeIntent.finishing, True, 0.0), 1 / fps)
    assert output.phase == LaneChangeVisualPhase.completing
    for _ in range(round(0.4 * fps) - 1):
      output = animator.update(LaneChangeVisualInput(LaneChangeIntent.off, True, 0.0), 1 / fps)
    assert output.phase == LaneChangeVisualPhase.idle

  output = animator.update(
    LaneChangeVisualInput(LaneChangeIntent.active, True, 0.5, enabled=False),
    1 / 60,
  )
  assert output.phase == LaneChangeVisualPhase.idle
  assert output.lock_sweep_position is None


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
