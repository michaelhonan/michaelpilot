import pytest

from openpilot.cereal import log
from openpilot.selfdrive.ui.tests.diff.replay_script import AlertSize, AlertStatus, send_big_onroad_scene


class CapturingPubMaster:
  def __init__(self):
    self.messages = {}

  def send(self, service, message) -> None:
    self.messages.setdefault(service, []).append(message)


def test_big_alert_scene_preserves_engagement_and_mads_state():
  pm = CapturingPubMaster()
  send_big_onroad_scene(
    pm,
    control_mode="full",
    alert_size=AlertSize.mid,
    alert_text1="Smart/Adaptive Cruise Control: OFF",
    alert_text2="Manual Speed Control Required",
    alert_status=AlertStatus.userPrompt,
  )

  assert len(pm.messages["selfdriveState"]) == 1
  state = pm.messages["selfdriveState"][0].selfdriveState
  assert state.state == log.SelfdriveState.OpenpilotState.enabled
  assert state.enabled and state.active and state.engageable
  assert state.alertSize == AlertSize.mid
  assert state.alertText1 == "Smart/Adaptive Cruise Control: OFF"
  assert state.alertText2 == "Manual Speed Control Required"

  mads = pm.messages["selfdriveStateSP"][0].selfdriveStateSP.mads
  assert mads.available and mads.enabled and mads.active


def test_alert_setup_publishes_one_complete_selfdrive_state():
  pm = CapturingPubMaster()

  def base_send(**alert) -> None:
    send_big_onroad_scene(pm, control_mode="full", **alert)

  from openpilot.selfdrive.ui.tests.diff.replay_script import make_alert_setup
  make_alert_setup(pm, AlertSize.small, "Small Alert", "", AlertStatus.normal, base_send)()

  assert len(pm.messages["selfdriveState"]) == 1
  state = pm.messages["selfdriveState"][0].selfdriveState
  assert state.enabled and state.active
  assert state.alertSize == AlertSize.small


def test_big_speed_panel_scene_supports_unset_and_unavailable_cruise_values():
  unset_pm = CapturingPubMaster()
  send_big_onroad_scene(unset_pm, set_speed=255.0)
  assert unset_pm.messages["carState"][0].carState.vCruiseCluster == 255.0
  assert unset_pm.messages["controlsState"][0].controlsState.deprecated.vCruise == 255.0
  assert unset_pm.messages["carState"][0].carState.cruiseState.available

  unavailable_pm = CapturingPubMaster()
  send_big_onroad_scene(unavailable_pm, set_speed=-1.0, cruise_available=False)
  assert unavailable_pm.messages["carState"][0].carState.vCruiseCluster == -1.0
  assert unavailable_pm.messages["controlsState"][0].controlsState.deprecated.vCruise == -1.0
  assert not unavailable_pm.messages["carState"][0].carState.cruiseState.available


def test_lane_change_replay_scene_is_lateral_only_and_publishes_desire_probability():
  pm = CapturingPubMaster()
  send_big_onroad_scene(
    pm,
    control_mode="lateral",
    openpilot_longitudinal_control=False,
    lane_change_state=log.LaneChangeState.laneChangeStarting,
    lane_change_direction=log.LaneChangeDirection.right,
    lane_change_probability=0.6,
  )

  car_control = pm.messages["carControl"][0].carControl
  assert car_control.latActive
  assert not car_control.longActive
  assert not pm.messages["carParams"][0].carParams.openpilotLongitudinalControl

  model_message = pm.messages["modelV2"][0]
  assert model_message.valid
  model = model_message.modelV2
  assert model.meta.laneChangeState == log.LaneChangeState.laneChangeStarting
  assert model.meta.laneChangeDirection == log.LaneChangeDirection.right
  assert len(model.meta.desireState) == 7
  assert model.meta.desireState[log.Desire.laneChangeLeft] == 0.0
  assert model.meta.desireState[log.Desire.laneChangeRight] == pytest.approx(0.6)
