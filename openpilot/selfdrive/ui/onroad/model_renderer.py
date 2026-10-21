import colorsys
import numpy as np
import pyray as rl
from openpilot.cereal import messaging
from opendbc.car.structs import car
from dataclasses import dataclass, field
from openpilot.common.filter_simple import FirstOrderFilter
from openpilot.common.params import Params
from openpilot.selfdrive.locationd.calibrationd import HEIGHT_INIT
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import FontWeight, gui_app
from openpilot.system.ui.lib.shader_polygon import draw_polygon, Gradient
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.widgets import Widget

from openpilot.selfdrive.ui.sunnypilot.onroad.model_renderer import ChevronMetrics, ModelRendererSP
from openpilot.selfdrive.ui.sunnypilot.onroad.modern_view import (
  DEFAULT_MODERN_CONTRAST, LANE_LINE_WHITE, ModernContrast, NEUTRAL_GEOMETRY,
)
from openpilot.selfdrive.ui.sunnypilot.onroad.modern_road import (
  CLASSIC_LANE_LINE_HALF_WIDTH, MODERN_LANE_LINE_HALF_WIDTH, MODERN_PATH_EDGE_HALF_WIDTH, LeadSpeedLabel, LeadTrend,
  advance_transition, lane_line_style, lead_speed_label, path_style, road_edge_alpha, slice_ribbon,
)

CLIP_MARGIN = 500
MIN_DRAW_DISTANCE = 10.0
MAX_DRAW_DISTANCE = 100.0

STOCK_PATH_GRADIENT = Gradient(
  start=(0.0, 1.0),
  end=(0.0, 0.0),
  colors=[rl.Color(13, 248, 122, 102), rl.Color(114, 255, 92, 89), rl.Color(114, 255, 92, 0)],
  stops=[0.0, 0.5, 1.0],
)
ENGAGE_SWEEP_SECONDS = 0.6
DISENGAGE_SWEEP_SECONDS = 0.35

# Modern lead marker: a bracket across the path at the lead's rear bumper and a pill with the lead's speed.
LEAD_BRACKET_HALF_WIDTH = 0.9  # m either side of the lead centre
LEAD_SPEED_FILTER_RC = 0.5  # s
LEAD_PILL_HEIGHT = 74
LEAD_PILL_GAP = 42
LEAD_PILL_PADDING_X = 26
LEAD_ARROW_SIZE = 28
LEAD_SPEED_FONT_SIZE = 35
LEAD_UNIT_FONT_SIZE = 23
LEAD_PILL_BG = rl.Color(0, 0, 0, 168)
LEAD_UNIT_COLOR = rl.Color(0xAA, 0xB2, 0xBD, 0xFF)
LEAD_TREND_COLORS = {
  LeadTrend.closing: rl.Color(0xF5, 0xA1, 0x5F, 0xFF),
  LeadTrend.matching: rl.Color(0xE6, 0xE9, 0xEE, 0xFF),
  LeadTrend.pulling_away: rl.Color(0x5F, 0xD4, 0xC4, 0xFF),
}


@dataclass
class ModelPoints:
  raw_points: np.ndarray = field(default_factory=lambda: np.empty((0, 3), dtype=np.float32))
  projected_points: np.ndarray = field(default_factory=lambda: np.empty((0, 2), dtype=np.float32))


@dataclass
class LeadVehicle:
  glow: list[tuple[float, float]] = field(default_factory=list)
  chevron: list[tuple[float, float]] = field(default_factory=list)
  fill_alpha: int = 0


class ModelRenderer(Widget, ChevronMetrics, ModelRendererSP):
  def __init__(self):
    Widget.__init__(self)
    ChevronMetrics.__init__(self)
    ModelRendererSP.__init__(self)
    self._longitudinal_control = False
    self._lane_line_probs = np.zeros(4, dtype=np.float32)
    self._road_edge_stds = np.zeros(2, dtype=np.float32)
    self._lead_vehicles = [LeadVehicle(), LeadVehicle()]
    self._path_offset_z = HEIGHT_INIT[0]
    self._counter = -1
    self._camera_offset = ui_state.params.get("CameraOffset", return_default=True) if ui_state.active_bundle else 0.0
    # Initialize ModelPoints objects
    self._path = ModelPoints()
    self._lane_lines = [ModelPoints() for _ in range(4)]
    self._road_edges = [ModelPoints() for _ in range(2)]
    self._acceleration_x = np.empty((0,), dtype=np.float32)
    self._path_edges = [ModelPoints(), ModelPoints()]
    self._lead_bracket: tuple[rl.Vector2, rl.Vector2] | None = None
    self._lead_label: LeadSpeedLabel | None = None
    self._lead_speed_filter = FirstOrderFilter(0.0, LEAD_SPEED_FILTER_RC, 1 / gui_app.target_fps)
    self._lead_speed_initialized = False
    self._font_bold = gui_app.font(FontWeight.BOLD)
    self._font_medium = gui_app.font(FontWeight.MEDIUM)
    self._engagement_progress = 0.0
    self._engagement_target = 0.0
    self._engagement_sweep_active = False
    self._engaged_prev: bool | None = None
    self._modern_enabled_prev: bool | None = None
    self._modern_contrast = DEFAULT_MODERN_CONTRAST

    # Transform matrix (3x3 for car space to screen space)
    self._car_space_transform = np.zeros((3, 3), dtype=np.float32)
    self._transform_dirty = True
    self._clip_region = None

    self._path_gradient = Gradient(
      start=(0.0, 1.0),  # Bottom of path
      end=(0.0, 0.0),  # Top of path
      colors=[],
      stops=[],
    )

    # Get longitudinal control setting from car parameters
    if car_params := Params().get("CarParams"):
      cp = messaging.log_from_bytes(car_params, car.CarParams)
      self._longitudinal_control = cp.openpilotLongitudinalControl

  def set_transform(self, transform: np.ndarray):
    self._car_space_transform = transform.astype(np.float32)
    self._transform_dirty = True

  def set_modern_contrast(self, contrast: ModernContrast) -> None:
    self._modern_contrast = contrast

  def _render(self, rect: rl.Rectangle):
    sm = ui_state.sm

    # Check if data is up-to-date
    if (sm.recv_frame["extrinsicsCalibration"] < ui_state.started_frame or
        sm.recv_frame["modelV2"] < ui_state.started_frame):
      return

    # Set up clipping region
    self._clip_region = rl.Rectangle(
      rect.x - CLIP_MARGIN, rect.y - CLIP_MARGIN, rect.width + 2 * CLIP_MARGIN, rect.height + 2 * CLIP_MARGIN
    )

    # Update state
    extrinsics_calibration = sm['extrinsicsCalibration']
    self._path_offset_z = extrinsics_calibration.height[0] if extrinsics_calibration.height else HEIGHT_INIT[0]

    if self._counter % 60 == 0:
      self._camera_offset = ui_state.params.get("CameraOffset", return_default=True) if ui_state.active_bundle else 0.0
    self._counter += 1

    if sm.updated['carParams']:
      self._longitudinal_control = sm['carParams'].openpilotLongitudinalControl

    model = sm['modelV2']
    radar_state = sm['radarState'] if sm.valid['radarState'] else None
    lead_one = radar_state.leadOne if radar_state else None
    modern = ui_state.modern_driving_view
    # The modern lead marker is informational, so it shows even when the car's own cruise does the following.
    render_lead_indicator = self._longitudinal_control and radar_state is not None and not modern
    if modern:
      self._update_lead_label(lead_one)

    # Update model data when needed
    model_updated = sm.updated['modelV2']
    if model_updated or sm.updated['radarState'] or self._transform_dirty:
      if model_updated:
        self._update_raw_points(model)

      path_x_array = self._path.raw_points[:, 0]
      if path_x_array.size == 0:
        return

      self._update_model(lead_one, path_x_array)
      if render_lead_indicator:
        self._update_leads(radar_state, path_x_array)
      if modern:
        self._update_lead_bracket(lead_one, path_x_array)
      self._transform_dirty = False

    # Draw elements
    self._update_modern_animations()
    self._draw_lane_lines()
    self._draw_path()
    if modern:
      self._draw_lead_marker()

    if render_lead_indicator and radar_state:
      self._draw_lead_indicator()
      self.chevron_metrics.draw_lead_status(sm, radar_state, self._rect, self._lead_vehicles)

  def _update_raw_points(self, model):
    """Update raw 3D points from model data"""
    self._path.raw_points = np.array([model.position.x, np.array(model.position.y) + self._camera_offset, model.position.z], dtype=np.float32).T

    for i, lane_line in enumerate(model.laneLines):
      self._lane_lines[i].raw_points = np.array([lane_line.x, np.array(lane_line.y) + self._camera_offset, lane_line.z], dtype=np.float32).T

    for i, road_edge in enumerate(model.roadEdges):
      self._road_edges[i].raw_points = np.array([road_edge.x, np.array(road_edge.y) + self._camera_offset, road_edge.z], dtype=np.float32).T

    self._lane_line_probs = np.array(model.laneLineProbs, dtype=np.float32)
    self._road_edge_stds = np.array(model.roadEdgeStds, dtype=np.float32)
    self._acceleration_x = np.array(model.acceleration.x, dtype=np.float32)

  def _update_leads(self, radar_state, path_x_array):
    """Update positions of lead vehicles"""
    self._lead_vehicles = [LeadVehicle(), LeadVehicle()]
    leads = [radar_state.leadOne, radar_state.leadTwo]

    for i, lead_data in enumerate(leads):
      if lead_data and lead_data.present:
        d_rel, y_rel, v_rel = lead_data.dRel, lead_data.yRel, lead_data.vRel
        idx = self._get_path_length_idx(path_x_array, d_rel)

        # Get z-coordinate from path at the lead vehicle position
        z = self._path.raw_points[idx, 2] if idx < len(self._path.raw_points) else 0.0
        point = self._map_to_screen(d_rel, -y_rel + self._camera_offset, z + self._path_offset_z)
        if point:
          self._lead_vehicles[i] = self._update_lead_vehicle(d_rel, v_rel, point, self._rect)

  def _update_model(self, lead, path_x_array):
    """Update model visualization data based on model message"""
    max_distance = np.clip(path_x_array[-1], MIN_DRAW_DISTANCE, MAX_DRAW_DISTANCE)
    max_idx = self._get_path_length_idx(self._lane_lines[0].raw_points[:, 0], max_distance)

    # Update lane lines using raw points
    lane_line_half_width = MODERN_LANE_LINE_HALF_WIDTH if ui_state.modern_driving_view else CLASSIC_LANE_LINE_HALF_WIDTH
    for i, lane_line in enumerate(self._lane_lines):
      lane_line.projected_points = self._map_line_to_polygon(
        lane_line.raw_points, lane_line_half_width * self._lane_line_probs[i], 0.0, max_idx, max_distance
      )

    # Update road edges using raw points
    for road_edge in self._road_edges:
      road_edge.projected_points = self._map_line_to_polygon(road_edge.raw_points, 0.025, 0.0, max_idx, max_distance)

    # Update path using raw points
    if ui_state.modern_driving_view:
      # The path stops at the lead marker's bracket.
      if lead and self._lead_label is not None:
        max_distance = np.clip(lead.dRel, 0.0, max_distance)
    elif lead and lead.present:
      lead_d = lead.dRel * 2.0
      max_distance = np.clip(lead_d - min(lead_d * 0.35, 10.0), 0.0, max_distance)

    max_idx = self._get_path_length_idx(path_x_array, max_distance)
    path_half_width = self._get_path_half_width()
    self._path.projected_points = self._map_line_to_polygon(
      self._path.raw_points, path_half_width, self._path_offset_z, max_idx, max_distance, allow_invert=False
    )

    if ui_state.modern_driving_view:
      for edge, side in zip(self._path_edges, (-1.0, 1.0), strict=True):
        edge_points = self._path.raw_points + np.array([0.0, side * path_half_width, 0.0], dtype=np.float32)
        edge.projected_points = self._map_line_to_polygon(
          edge_points, MODERN_PATH_EDGE_HALF_WIDTH, self._path_offset_z, max_idx, max_distance, allow_invert=False
        )

    self._update_path_gradient()

  def _update_modern_animations(self) -> None:
    modern = ui_state.modern_driving_view
    engaged = ui_state.engaged
    if not modern:
      self._engagement_progress = 1.0 if engaged else 0.0
      self._engagement_target = self._engagement_progress
      self._engagement_sweep_active = False
      self._engaged_prev = engaged
      self._modern_enabled_prev = False
      return

    if self._modern_enabled_prev is None or modern != self._modern_enabled_prev:
      self._engagement_progress = 1.0 if engaged else 0.0
      self._engagement_target = self._engagement_progress
      self._engagement_sweep_active = False
      self._engaged_prev = engaged
      self._modern_enabled_prev = modern
    elif modern and engaged != self._engaged_prev:
      self._engagement_target = 1.0 if engaged else 0.0
      self._engagement_sweep_active = True
      self._engaged_prev = engaged

    dt = 1.0 / max(gui_app.target_fps, 1)
    if self._engagement_sweep_active:
      duration = ENGAGE_SWEEP_SECONDS if self._engagement_target > self._engagement_progress else DISENGAGE_SWEEP_SECONDS
      self._engagement_progress, self._engagement_sweep_active = advance_transition(
        self._engagement_progress, self._engagement_target, duration, dt,
      )

  def _update_lead_label(self, lead) -> None:
    label = None
    if lead is not None:
      if not self._lead_speed_initialized or not lead.present:
        self._lead_speed_filter.x = lead.vLeadK
        self._lead_speed_initialized = lead.present
      v_lead = self._lead_speed_filter.update(lead.vLeadK)
      label = lead_speed_label(lead.present, lead.radar, lead.modelProb, v_lead, lead.vRel, ui_state.is_metric)
    else:
      self._lead_speed_initialized = False
    self._lead_label = label

  def _update_lead_bracket(self, lead, path_x_array) -> None:
    self._lead_bracket = None
    if lead is None or not lead.present:
      return
    idx = self._get_path_length_idx(path_x_array, lead.dRel)
    z = (self._path.raw_points[idx, 2] if idx < len(self._path.raw_points) else 0.0) + self._path_offset_z
    y = -lead.yRel + self._camera_offset
    left = self._map_to_screen(lead.dRel, y - LEAD_BRACKET_HALF_WIDTH, z)
    right = self._map_to_screen(lead.dRel, y + LEAD_BRACKET_HALF_WIDTH, z)
    if left and right:
      if left[0] > right[0]:
        left, right = right, left
      self._lead_bracket = (rl.Vector2(*left), rl.Vector2(*right))

  def _draw_lead_marker(self) -> None:
    label = self._lead_label
    if label is None or self._lead_bracket is None:
      return

    color = LEAD_TREND_COLORS[label.trend]
    left, right = self._lead_bracket
    width = right.x - left.x
    tick = max(8.0, width * 0.08)
    thickness = float(np.clip(width * 0.03, 3.0, 6.0))
    bracket = (rl.Vector2(left.x, left.y - tick), left, right, rl.Vector2(right.x, right.y - tick))
    for start, end in zip(bracket, bracket[1:], strict=False):
      rl.draw_line_ex(start, end, thickness, color)

    speed_size = measure_text_cached(self._font_bold, label.speed, LEAD_SPEED_FONT_SIZE)
    unit_size = measure_text_cached(self._font_medium, label.unit, LEAD_UNIT_FONT_SIZE)
    pill_width = 2 * LEAD_PILL_PADDING_X + LEAD_ARROW_SIZE + 14 + speed_size.x + 10 + unit_size.x
    center_y = right.y - tick / 2
    pill_x = min(right.x + LEAD_PILL_GAP, self._rect.x + self._rect.width - pill_width - 20)
    pill = rl.Rectangle(pill_x, center_y - LEAD_PILL_HEIGHT / 2, pill_width, LEAD_PILL_HEIGHT)
    if pill.x > right.x:
      rl.draw_line_ex(rl.Vector2(right.x, center_y), rl.Vector2(pill.x, center_y), 3.0, rl.Color(color.r, color.g, color.b, 150))
    rl.draw_rectangle_rounded(pill, 1.0, 16, LEAD_PILL_BG)

    arrow_x = pill.x + LEAD_PILL_PADDING_X
    half = LEAD_ARROW_SIZE / 2
    if label.trend == LeadTrend.closing:
      rl.draw_triangle(rl.Vector2(arrow_x, center_y - half * 0.8), rl.Vector2(arrow_x + half, center_y + half * 0.8),
                       rl.Vector2(arrow_x + LEAD_ARROW_SIZE, center_y - half * 0.8), color)
    elif label.trend == LeadTrend.pulling_away:
      rl.draw_triangle(rl.Vector2(arrow_x + half, center_y - half * 0.8), rl.Vector2(arrow_x, center_y + half * 0.8),
                       rl.Vector2(arrow_x + LEAD_ARROW_SIZE, center_y + half * 0.8), color)
    else:
      rl.draw_rectangle_rec(rl.Rectangle(arrow_x, center_y - 4, LEAD_ARROW_SIZE, 8), color)

    text_x = arrow_x + LEAD_ARROW_SIZE + 14
    speed_y = center_y - speed_size.y / 2
    rl.draw_text_ex(self._font_bold, label.speed, rl.Vector2(text_x, speed_y), LEAD_SPEED_FONT_SIZE, 0, rl.WHITE)
    unit_y = speed_y + speed_size.y * 0.8 - unit_size.y * 0.8
    rl.draw_text_ex(self._font_medium, label.unit, rl.Vector2(text_x + speed_size.x + 10, unit_y),
                    LEAD_UNIT_FONT_SIZE, 0, LEAD_UNIT_COLOR)

  def _update_path_gradient(self):
    if not self._longitudinal_control:
      return

    max_len = min(len(self._path.projected_points) // 2, len(self._acceleration_x))

    segment_colors = []
    gradient_stops = []

    i = 0
    while i < max_len:
      # Some points (screen space) are out of frame (rect space)
      track_y = self._path.projected_points[i][1]
      if track_y < self._rect.y or track_y > (self._rect.y + self._rect.height):
        i += 1
        continue

      # Calculate color based on acceleration (0 is bottom, 1 is top)
      lin_grad_point = 1 - (track_y - self._rect.y) / self._rect.height

      # speed up: 120, slow down: 0
      path_hue = np.clip(60 + self._acceleration_x[i] * 35, 0, 120)

      saturation = min(abs(self._acceleration_x[i] * 1.5), 1)
      lightness = np.interp(saturation, [0.0, 1.0], [0.95, 0.62])
      alpha = np.interp(lin_grad_point, [0.75 / 2.0, 0.75], [0.4, 0.0])

      # Use HSL to RGB conversion
      color = self._hsla_to_color(path_hue / 360.0, saturation, lightness, alpha)

      gradient_stops.append(lin_grad_point)
      segment_colors.append(color)

      # Skip a point, unless next is last
      i += 1 + (1 if (i + 2) < max_len else 0)

    # Store the gradient in the path object
    self._path_gradient = Gradient(
      start=(0.0, 1.0),  # Bottom of path
      end=(0.0, 0.0),  # Top of path
      colors=segment_colors,
      stops=gradient_stops,
    )

  def _update_lead_vehicle(self, d_rel, v_rel, point, rect):
    speed_buff, lead_buff = 10.0, 40.0

    # Calculate fill alpha
    fill_alpha = 0
    if d_rel < lead_buff:
      fill_alpha = 255 * (1.0 - (d_rel / lead_buff))
      if v_rel < 0:
        fill_alpha += 255 * (-1 * (v_rel / speed_buff))
      fill_alpha = min(fill_alpha, 255)

    # Calculate size and position
    sz = np.clip((25 * 30) / (d_rel / 3 + 30), 15.0, 30.0) * 2.35
    x = np.clip(point[0], 0.0, rect.width - sz / 2)
    y = min(point[1], rect.height - sz * 0.6)

    g_xo = sz / 5
    g_yo = sz / 10

    glow = [(x + (sz * 1.35) + g_xo, y + sz + g_yo), (x, y - g_yo), (x - (sz * 1.35) - g_xo, y + sz + g_yo)]
    chevron = [(x + (sz * 1.25), y + sz), (x, y), (x - (sz * 1.25), y + sz)]

    return LeadVehicle(glow=glow, chevron=chevron, fill_alpha=int(fill_alpha))

  def _draw_lane_lines(self):
    """Draw lane lines and road edges"""
    modern = ui_state.modern_driving_view
    style = lane_line_style(modern, ui_state.status.value, ui_state.rainbow_path and self._lateral_active,
                            self._longitudinal_control)
    lane_line_base = self._modern_contrast.control_blue if style == "blue" else LANE_LINE_WHITE

    for i, lane_line in enumerate(self._lane_lines):
      if lane_line.projected_points.size == 0:
        continue

      alpha = np.clip(self._lane_line_probs[i], 0.0, 0.7)
      color = rl.Color(lane_line_base.r, lane_line_base.g, lane_line_base.b, int(alpha * 255))
      draw_polygon(self._rect, lane_line.projected_points, color)

    for i, road_edge in enumerate(self._road_edges):
      if road_edge.projected_points.size == 0:
        continue

      alpha = road_edge_alpha(self._road_edge_stds[i], modern)
      base = NEUTRAL_GEOMETRY if modern else rl.Color(255, 0, 0, 255)
      color = rl.Color(base.r, base.g, base.b, int(alpha * 255))
      draw_polygon(self._rect, road_edge.projected_points, color)

  def _draw_path(self):
    if not self._path.projected_points.size:
      return

    style = path_style(ui_state.modern_driving_view, ui_state.status.value,
                       ui_state.rainbow_path and self._lateral_active, self._longitudinal_control)

    if style == "rainbow":
      self.rainbow_path.draw_rainbow_path(self._rect, self._path)
    elif style == "experimental":
      # Draw with acceleration coloring
      if len(self._path_gradient.colors) > 1:
        draw_polygon(self._rect, self._path.projected_points, gradient=self._path_gradient)
      else:
        draw_polygon(self._rect, self._path.projected_points, rl.Color(255, 255, 255, 30))
    elif style == "classic":
      draw_polygon(self._rect, self._path.projected_points, gradient=STOCK_PATH_GRADIENT)
    else:
      if style == "blue":
        base = self._modern_contrast.lateral_only_blue if ui_state.status.value == "lat_only" else self._modern_contrast.control_blue
        fill_alphas, edge = (118, 68, 20), self._modern_contrast.lateral_only_blue
      else:
        base, fill_alphas, edge = NEUTRAL_GEOMETRY, (36, 22, 6), NEUTRAL_GEOMETRY
      gradient = Gradient(
        start=(0.0, 1.0),  # Bottom of path
        end=(0.0, 0.0),  # Top of path
        colors=[rl.Color(base.r, base.g, base.b, a) for a in fill_alphas],
        stops=[0.0, 0.45, 1.0],
      )
      draw_polygon(self._rect, self._path.projected_points, gradient=gradient)

      edge_alphas = (240, 150, 76) if style == "blue" else (150, 90, 40)
      edge_gradient = Gradient(
        start=(0.0, 1.0),
        end=(0.0, 0.0),
        colors=[rl.Color(edge.r, edge.g, edge.b, a) for a in edge_alphas],
        stops=[0.0, 0.5, 1.0],
      )
      for path_edge in self._path_edges:
        if path_edge.projected_points.size:
          draw_polygon(self._rect, path_edge.projected_points, gradient=edge_gradient)

    self._draw_engagement_sweep()

  def _draw_engagement_sweep(self) -> None:
    if not ui_state.modern_driving_view or not self._engagement_sweep_active:
      return

    band_half_width = 0.1
    start = max(0.0, self._engagement_progress - band_half_width)
    end = min(1.0, self._engagement_progress + band_half_width)
    polygon = slice_ribbon(self._path.projected_points, start, end)
    if not polygon.size:
      return

    base = self._modern_contrast.control_blue
    draw_polygon(self._rect, polygon, rl.Color(base.r, base.g, base.b, 180))

  def _draw_lead_indicator(self):
    # Draw lead vehicles if available
    for lead in self._lead_vehicles:
      if not lead.glow or not lead.chevron:
        continue

      rl.draw_triangle_fan(lead.glow, len(lead.glow), rl.Color(218, 202, 37, 255))
      rl.draw_triangle_fan(lead.chevron, len(lead.chevron), rl.Color(201, 34, 49, lead.fill_alpha))

  @staticmethod
  def _get_path_length_idx(pos_x_array: np.ndarray, path_distance: float) -> int:
    """Get the index corresponding to the given path distance"""
    if len(pos_x_array) == 0:
      return 0
    indices = np.where(pos_x_array <= path_distance)[0]
    return indices[-1] if indices.size > 0 else 0

  def _map_to_screen(self, in_x, in_y, in_z):
    """Project a point in car space to screen space"""
    input_pt = np.array([in_x, in_y, in_z])
    pt = self._car_space_transform @ input_pt

    if abs(pt[2]) < 1e-6:
      return None

    x, y = pt[0] / pt[2], pt[1] / pt[2]

    clip = self._clip_region
    if not (clip.x <= x <= clip.x + clip.width and clip.y <= y <= clip.y + clip.height):
      return None

    return (x, y)

  def _map_line_to_polygon(self, line: np.ndarray, y_off: float, z_off: float, max_idx: int, max_distance: float, allow_invert: bool = True) -> np.ndarray:
    """Convert 3D line to 2D polygon for rendering."""
    if line.shape[0] == 0:
      return np.empty((0, 2), dtype=np.float32)

    # Slice points and filter non-negative x-coordinates
    points = line[:max_idx + 1]

    # Interpolate around max_idx so path end is smooth (max_distance is always >= p0.x)
    if 0 < max_idx < line.shape[0] - 1:
      p0 = line[max_idx]
      p1 = line[max_idx + 1]
      x0, x1 = p0[0], p1[0]
      interp_y = np.interp(max_distance, [x0, x1], [p0[1], p1[1]])
      interp_z = np.interp(max_distance, [x0, x1], [p0[2], p1[2]])
      interp_point = np.array([max_distance, interp_y, interp_z], dtype=points.dtype)
      points = np.concatenate((points, interp_point[None, :]), axis=0)

    points = points[points[:, 0] >= 0]
    if points.shape[0] == 0:
      return np.empty((0, 2), dtype=np.float32)

    N = points.shape[0]
    # Generate left and right 3D points in one array using broadcasting
    offsets = np.array([[0, -y_off, z_off], [0, y_off, z_off]], dtype=np.float32)
    points_3d = points[None, :, :] + offsets[:, None, :]  # Shape: 2xNx3
    points_3d = points_3d.reshape(2 * N, 3)  # Shape: (2*N)x3

    # Transform all points to projected space in one operation
    proj = self._car_space_transform @ points_3d.T  # Shape: 3x(2*N)
    proj = proj.reshape(3, 2, N)
    left_proj = proj[:, 0, :]
    right_proj = proj[:, 1, :]

    # Filter points where z is sufficiently large
    valid_proj = (np.abs(left_proj[2]) >= 1e-6) & (np.abs(right_proj[2]) >= 1e-6)
    if not np.any(valid_proj):
      return np.empty((0, 2), dtype=np.float32)

    # Compute screen coordinates
    left_screen = left_proj[:2, valid_proj] / left_proj[2, valid_proj][None, :]
    right_screen = right_proj[:2, valid_proj] / right_proj[2, valid_proj][None, :]

    # Define clip region bounds
    clip = self._clip_region
    x_min, x_max = clip.x, clip.x + clip.width
    y_min, y_max = clip.y, clip.y + clip.height

    # Filter points within clip region
    left_in_clip = (
      (left_screen[0] >= x_min) & (left_screen[0] <= x_max) &
      (left_screen[1] >= y_min) & (left_screen[1] <= y_max)
    )
    right_in_clip = (
      (right_screen[0] >= x_min) & (right_screen[0] <= x_max) &
      (right_screen[1] >= y_min) & (right_screen[1] <= y_max)
    )
    both_in_clip = left_in_clip & right_in_clip

    if not np.any(both_in_clip):
      return np.empty((0, 2), dtype=np.float32)

    # Select valid and clipped points
    left_screen = left_screen[:, both_in_clip]
    right_screen = right_screen[:, both_in_clip]

    # Handle Y-coordinate inversion on hills
    if not allow_invert and left_screen.shape[1] > 1:
      y = left_screen[1, :]  # y-coordinates
      keep = y == np.minimum.accumulate(y)
      if not np.any(keep):
        return np.empty((0, 2), dtype=np.float32)
      left_screen = left_screen[:, keep]
      right_screen = right_screen[:, keep]

    return np.vstack((left_screen.T, right_screen[:, ::-1].T)).astype(np.float32)

  @staticmethod
  def _hsla_to_color(h, s, l, a):
    rgb = colorsys.hls_to_rgb(h, l, s)
    return rl.Color(
      int(rgb[0] * 255),
      int(rgb[1] * 255),
      int(rgb[2] * 255),
      int(a * 255)
    )
