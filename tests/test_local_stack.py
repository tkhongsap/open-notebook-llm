from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts import local_stack


def _service(tmp_path: Path, *, port: int | None = None) -> local_stack.Service:
    return local_stack.Service(
        name="fixture",
        command=("fixture", "serve"),
        marker="fixture serve",
        cwd=tmp_path,
        port=port,
    )


def test_runtime_environment_is_loopback_and_serial(monkeypatch):
    for key in (
        "SURREAL_URL",
        "OPEN_NOTEBOOK_WORKER_MAX_TASKS",
        "API_RELOAD",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(local_stack, "find_node", lambda: "/locked/node/bin/node")

    env = local_stack.runtime_environment()

    assert env["SURREAL_URL"] == "ws://127.0.0.1:8000/rpc"
    assert env["OPEN_NOTEBOOK_WORKER_MAX_TASKS"] == "1"
    assert env["API_RELOAD"] == "false"
    assert env["PATH"].split(":", 1)[0] == "/locked/node/bin"


def test_pid_match_requires_service_marker(tmp_path, monkeypatch):
    service = _service(tmp_path)
    completed = Mock(returncode=0, stdout="fixture serve --safe\n")
    monkeypatch.setattr(local_stack.subprocess, "run", lambda *args, **kwargs: completed)

    assert local_stack.pid_matches_service(service, 1234) is True


def test_start_service_refuses_unmanaged_port(tmp_path, monkeypatch):
    service = _service(tmp_path, port=4321)
    monkeypatch.setattr(local_stack, "service_is_running", lambda value: False)
    monkeypatch.setattr(local_stack, "tcp_is_open", lambda port: True)

    with pytest.raises(RuntimeError, match="unmanaged process"):
        local_stack.start_service(service, {})


def test_frontend_native_fallback_links_locked_optional_package(tmp_path, monkeypatch):
    monkeypatch.setattr(local_stack.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(local_stack.platform, "machine", lambda: "arm64")
    source = (
        tmp_path
        / "node_modules/lightningcss-darwin-arm64/lightningcss.darwin-arm64.node"
    )
    source.parent.mkdir(parents=True)
    source.write_bytes(b"native-module")
    (tmp_path / "node_modules/lightningcss").mkdir(parents=True)

    local_stack.ensure_frontend_native_modules(tmp_path)

    destination = tmp_path / "node_modules/lightningcss/lightningcss.darwin-arm64.node"
    assert destination.is_symlink()
    assert destination.read_bytes() == b"native-module"
