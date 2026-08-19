#!/usr/bin/env python3
"""Import gate for C3/C3X onroad UI modules.

Run from a built openpilot checkout. BIG is established before the first UI
import so this exercises the same import boundary as the real UI process.
"""

import importlib
import os


CHANGED_MODULES = (
  "openpilot.selfdrive.ui.sunnypilot.onroad.modern_view",
  "openpilot.selfdrive.ui.sunnypilot.onroad.modern_road",
  "openpilot.selfdrive.ui.onroad.exp_button",
  "openpilot.selfdrive.ui.sunnypilot.onroad.speed_renderer",
  "openpilot.selfdrive.ui.sunnypilot.onroad.speed_limit",
  "openpilot.selfdrive.ui.sunnypilot.onroad.road_name",
  "openpilot.selfdrive.ui.sunnypilot.onroad.smart_cruise_control",
  "openpilot.selfdrive.ui.sunnypilot.onroad.turn_signal",
  "openpilot.selfdrive.ui.sunnypilot.onroad.circular_alerts",
  "openpilot.selfdrive.ui.sunnypilot.onroad.driver_state",
  "openpilot.selfdrive.ui.sunnypilot.onroad.alert_renderer",
  "openpilot.selfdrive.ui.sunnypilot.onroad.hud_renderer",
  "openpilot.selfdrive.ui.onroad.model_renderer",
  "openpilot.selfdrive.ui.onroad.augmented_road_view",
  "openpilot.selfdrive.ui.sunnypilot.ui_state",
  "openpilot.selfdrive.ui.sunnypilot.layouts.settings.visuals",
)


def main() -> None:
  os.environ.setdefault("BIG", "1")
  for module in CHANGED_MODULES:
    importlib.import_module(module)
  importlib.import_module("openpilot.selfdrive.ui.ui")


if __name__ == "__main__":
  main()
