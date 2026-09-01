from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts import local_database


def test_select_asset_is_pinned_for_apple_silicon():
    asset = local_database.select_asset("Darwin", "arm64")

    assert asset.filename == "surreal-v2.6.5.darwin-arm64.tgz"
    assert asset.url.startswith("https://github.com/surrealdb/surrealdb/releases/")
    assert len(asset.sha256) == 64


def test_select_asset_rejects_unverified_platform():
    with pytest.raises(RuntimeError, match="not supported"):
        local_database.select_asset("Plan9", "mips")


def test_sha256_file(tmp_path: Path):
    fixture = tmp_path / "fixture.bin"
    fixture.write_bytes(b"open-notebook")

    assert local_database.sha256_file(fixture) == (
        "47a2077a8563acbe943e2b18bf6d7cf28464bf140fb7e01ca0ad43bc16fb2a5c"
    )


def test_pid_match_requires_managed_binary_and_start(monkeypatch):
    completed = Mock(
        returncode=0,
        stdout=f"{local_database.BINARY_PATH} start --bind 127.0.0.1:8000\n",
    )
    monkeypatch.setattr(local_database.subprocess, "run", lambda *args, **kwargs: completed)

    assert local_database.pid_matches_database(1234) is True


def test_start_refuses_an_unmanaged_listener(monkeypatch):
    monkeypatch.setattr(local_database, "is_running", lambda: False)
    monkeypatch.setattr(local_database, "tcp_is_open", lambda: True)

    with pytest.raises(RuntimeError, match="unmanaged process"):
        local_database.start_database()
