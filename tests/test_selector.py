import importlib
import sys
import types
from pathlib import Path


def _load_selector_module():
    scanner_stub = types.ModuleType("iphoto.scanner")
    scanner_stub.rank_moments = lambda moments, sort_by="size": moments
    scanner_stub.rank_videos = lambda videos, sort_by="size": videos
    sys.modules.setdefault("iphoto.scanner", scanner_stub)
    return importlib.import_module("iphoto.selector")


def test_get_free_disk_space_for_nonexistent_nested_path(tmp_path):
    selector = _load_selector_module()
    nested = tmp_path / "missing" / "deep"
    free_gb = selector.get_free_disk_space(nested)
    assert free_gb is not None
    assert free_gb > 0


def test_choose_archive_destination_from_list(monkeypatch):
    selector = _load_selector_module()
    choices = iter(["2"])

    monkeypatch.setattr(selector, "suggest_archive_destinations", lambda _: [Path("/A"), Path("/B")])
    monkeypatch.setattr(selector.Prompt, "ask", lambda *args, **kwargs: next(choices))
    monkeypatch.setattr(selector.Confirm, "ask", lambda *args, **kwargs: True)

    selected = selector.choose_archive_destination(Path("/initial"))
    assert selected == Path("/B")


def test_choose_archive_destination_custom_path(monkeypatch):
    selector = _load_selector_module()
    choices = iter(["custom", "~/ArchiveVideos"])

    monkeypatch.setattr(selector, "suggest_archive_destinations", lambda _: [Path("/A")])
    monkeypatch.setattr(selector.Prompt, "ask", lambda *args, **kwargs: next(choices))
    monkeypatch.setattr(selector.Confirm, "ask", lambda *args, **kwargs: True)

    selected = selector.choose_archive_destination(Path("/initial"))
    assert selected == Path("~/ArchiveVideos").expanduser()
