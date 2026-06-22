import openpilot.common.offline_dev as od


class FakeParams:
  def __init__(self, val: bool):
    self.val = val

  def get_bool(self, key: str) -> bool:
    assert key == "OfflineDevMode"
    return self.val


class TestOfflineDevGating:
  def test_branch_detection(self, monkeypatch):
    class BM:
      channel = od.OFFLINE_DEV_BRANCH
    monkeypatch.setattr(od, "get_build_metadata", lambda: BM())
    assert od.on_offline_dev_branch() is True

    class BM2:
      channel = "personal"
    monkeypatch.setattr(od, "get_build_metadata", lambda: BM2())
    assert od.on_offline_dev_branch() is False

  def test_branch_detection_failsafe(self, monkeypatch):
    # any failure resolving the branch must be treated as "not on dev-offline"
    def boom():
      raise RuntimeError("no metadata")
    monkeypatch.setattr(od, "get_build_metadata", boom)
    assert od.on_offline_dev_branch() is False

  def test_requires_both_branch_and_param(self, monkeypatch):
    # off the dev-offline branch: never active, even with the param set
    monkeypatch.setattr(od, "on_offline_dev_branch", lambda: False)
    assert od.offline_dev_active(FakeParams(True)) is False
    assert od.offline_dev_active(FakeParams(False)) is False

    # on the dev-offline branch: follows the param
    monkeypatch.setattr(od, "on_offline_dev_branch", lambda: True)
    assert od.offline_dev_active(FakeParams(False)) is False
    assert od.offline_dev_active(FakeParams(True)) is True
