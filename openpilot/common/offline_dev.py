"""
Offline Dev Mode gating.

A development-only capability (branch `dev-offline`) that disables driver monitoring
*enforcement* and takes the device fully offline for testing on private property.

It is gated on BOTH:
  1. the build being on the `dev-offline` branch, AND
  2. the `OfflineDevMode` param being set.

On any other branch (e.g. the road build) the capability is inert by construction, so there
is no runtime toggle that can leave a DM-disabled / offline state on a public-road build.

This is intentionally NOT a covert mechanism: driver state is still logged truthfully, the
param is logged, and a persistent on-screen banner is shown while it is active.

Software updates on the `dev-offline` branch are source-managed. This is independent of the
OfflineDevMode param: an internet connectivity check must never prevent this branch starting.
"""
from typing import Protocol

from openpilot.common.params import Params
from openpilot.common.version import get_build_metadata

OFFLINE_DEV_BRANCH = "dev-offline"


class BoolParamsLike(Protocol):
  def get_bool(self, key: str) -> bool: ...


class UpdateParamsLike(BoolParamsLike, Protocol):
  def get(self, key: str) -> object | None: ...


def on_offline_dev_branch() -> bool:
  try:
    return get_build_metadata().channel == OFFLINE_DEV_BRANCH
  except Exception:
    return False


def offline_dev_active(params: BoolParamsLike | None = None) -> bool:
  if not on_offline_dev_branch():
    return False
  return (params or Params()).get_bool("OfflineDevMode")


def update_connectivity_allows_startup(params: UpdateParamsLike | None = None) -> bool:
  params = params or Params()
  return (on_offline_dev_branch()
          or params.get("Offroad_ConnectivityNeeded") is None
          or params.get_bool("DisableUpdates")
          or params.get_bool("SnoozeUpdate"))
