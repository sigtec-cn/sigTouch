from sigtouch.platformsupport import permissions as P
from sigtouch.platformsupport.permissions import PermissionKind


def test_non_darwin_always_granted_and_noop(monkeypatch):
    monkeypatch.setattr(P.sys, "platform", "linux")
    for kind in PermissionKind:
        assert P.check(kind) is True
        P.request(kind)        # no-op,不抛
        P.open_settings(kind)  # no-op,不抛
    assert P.all_granted() is True


def test_snapshot_covers_all_kinds(monkeypatch):
    monkeypatch.setattr(P.sys, "platform", "linux")
    snap = P.snapshot()
    assert set(snap) == set(PermissionKind)
    assert all(snap.values())


def test_check_fails_open_on_darwin_errors(monkeypatch):
    monkeypatch.setattr(P.sys, "platform", "darwin")

    def boom(*a, **k):
        raise RuntimeError("api unavailable")

    monkeypatch.setattr(P, "_camera_status_darwin", boom)
    monkeypatch.setattr(P, "_accessibility_trusted_darwin", boom)
    monkeypatch.setattr(P, "_input_monitoring_status_darwin", boom)
    for kind in PermissionKind:
        assert P.check(kind) is True  # fail-open


def test_request_swallows_darwin_errors(monkeypatch):
    monkeypatch.setattr(P.sys, "platform", "darwin")

    def boom(*a, **k):
        raise RuntimeError("api unavailable")

    monkeypatch.setattr(P, "_camera_request_darwin", boom)
    monkeypatch.setattr(P, "_accessibility_trusted_darwin", boom)
    monkeypatch.setattr(P, "_input_monitoring_request_darwin", boom)
    for kind in PermissionKind:
        P.request(kind)  # 不抛


def test_settings_urls_cover_all_kinds():
    assert set(P._SETTINGS_URLS) == set(PermissionKind)
    for url in P._SETTINGS_URLS.values():
        assert url.startswith("x-apple.systempreferences:")


def test_real_host_check_returns_bool():
    # 真实宿主(macOS 走真实 API,其余平台恒 True)——接口契约冒烟
    for kind in PermissionKind:
        assert isinstance(P.check(kind), bool)
