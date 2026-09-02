from __future__ import annotations

import tomllib
import urllib.error
from email.message import Message
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from open_notebook.exceptions import ConfigurationError
from scripts import local_database, replit_build, replit_runtime

ROOT = Path(__file__).resolve().parents[1]


def secure_environment(**overrides: str) -> dict[str, str]:
    environment = {
        "REPLIT_DOMAINS": "open-notebook.replit.app,preview.example.test",
        "OPENROUTER_API_KEY": "openrouter-test-key",
        "OPEN_NOTEBOOK_ENCRYPTION_KEY": "e" * 32,
        "OPEN_NOTEBOOK_PASSWORD": "correct-horse-battery-staple",
        "SURREAL_PASSWORD": "database-password-strong",
    }
    environment.update(overrides)
    return environment


def test_replit_environment_is_cloud_only_and_loopback_internal():
    environment = replit_runtime.validated_environment(secure_environment())

    assert environment["OPEN_NOTEBOOK_MODEL_ROUTING_POLICY"] == "cloud-only"
    assert environment["OPEN_NOTEBOOK_REQUIRE_SECURITY"] == "true"
    assert environment["INTERNAL_API_URL"] == "http://127.0.0.1:5055"
    assert environment["SURREAL_URL"] == "ws://127.0.0.1:8000/rpc"
    assert environment["HOSTNAME"] == "0.0.0.0"
    assert environment["CORS_ORIGINS"] == (
        "https://open-notebook.replit.app,https://preview.example.test"
    )
    assert environment["SURREAL_PASS"] == environment["SURREAL_PASSWORD"]
    assert environment["TIKTOKEN_CACHE_DIR"].endswith(".runtime/tiktoken-cache")


def test_replit_environment_accepts_development_domain():
    environment = secure_environment(REPLIT_DOMAINS="")
    environment["REPLIT_DEV_DOMAIN"] = "workspace-id.replit.dev"

    validated = replit_runtime.validated_environment(environment)

    assert validated["CORS_ORIGINS"] == "https://workspace-id.replit.dev"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"OPENROUTER_API_KEY": ""}, "OPENROUTER_API_KEY"),
        ({"OPEN_NOTEBOOK_MODEL_ROUTING_POLICY": "hybrid"}, "cloud-only"),
        ({"OPEN_NOTEBOOK_REQUIRE_SECURITY": "false"}, "requires"),
        ({"CORS_ORIGINS": "*"}, "CORS_ORIGINS"),
        ({"PORT": "70000"}, "PORT"),
        ({"OPEN_NOTEBOOK_WORKER_MAX_TASKS": "0"}, "MAX_TASKS"),
    ],
)
def test_replit_environment_fails_closed(
    overrides: dict[str, str], message: str
):
    with pytest.raises(ConfigurationError, match=message):
        replit_runtime.validated_environment(secure_environment(**overrides))


def test_replit_environment_requires_an_explicit_origin():
    with pytest.raises(ConfigurationError, match="CORS_ORIGINS"):
        replit_runtime.validated_environment(
            secure_environment(REPLIT_DOMAINS="", REPLIT_DEV_DOMAIN="")
        )


def test_replit_service_graph_does_not_put_secrets_in_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    frontend = tmp_path / "frontend"
    venv_bin = tmp_path / ".venv" / "bin"
    database = tmp_path / ".runtime" / "surrealdb" / "bin" / "surreal"
    for executable in (venv_bin / "python", venv_bin / "surreal-commands-worker", database):
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_text("#!/bin/sh\n", encoding="utf-8")
        executable.chmod(0o755)
    (frontend / ".next" / "standalone").mkdir(parents=True)
    (frontend / ".next" / "standalone" / "server.js").write_text("", encoding="utf-8")
    (frontend / ".next" / "BUILD_ID").write_text("build-id", encoding="utf-8")
    (frontend / ".next" / "static").mkdir()
    next_cli = frontend / "node_modules" / "next" / "dist" / "bin" / "next"
    next_cli.parent.mkdir(parents=True)
    next_cli.write_text("#!/usr/bin/env node\n", encoding="utf-8")
    next_cli.chmod(0o755)

    monkeypatch.setattr(replit_runtime, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(replit_runtime, "FRONTEND_ROOT", frontend)
    monkeypatch.setattr(local_database, "BINARY_PATH", database)
    monkeypatch.setattr(replit_runtime.shutil, "which", lambda name: "/usr/bin/node")
    environment = replit_runtime.validated_environment(secure_environment())
    environment["SURREAL_DATA_PATH"] = str(tmp_path / "data" / "database.db")

    services = replit_runtime.service_definitions(environment)

    assert [service.name for service in services] == [
        "database",
        "api",
        "worker",
        "frontend",
    ]
    arguments = " ".join(part for service in services for part in service.command)
    assert environment["SURREAL_PASSWORD"] not in arguments
    assert environment["OPENROUTER_API_KEY"] not in arguments
    assert services[-1].ready_url == "http://127.0.0.1:8502/healthz"
    assert services[-1].command == ("/usr/bin/node", str(next_cli), "start")


def test_replit_service_graph_honors_uv_project_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    frontend = tmp_path / "frontend"
    environment_bin = tmp_path / ".pythonlibs" / "bin"
    database = tmp_path / ".runtime" / "surrealdb" / "bin" / "surreal"
    for executable in (
        environment_bin / "python",
        environment_bin / "surreal-commands-worker",
        database,
    ):
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_text("#!/bin/sh\n", encoding="utf-8")
        executable.chmod(0o755)
    (frontend / ".next" / "standalone").mkdir(parents=True)
    (frontend / ".next" / "standalone" / "server.js").write_text(
        "", encoding="utf-8"
    )
    (frontend / ".next" / "BUILD_ID").write_text("build-id", encoding="utf-8")
    (frontend / ".next" / "static").mkdir()
    next_cli = frontend / "node_modules" / "next" / "dist" / "bin" / "next"
    next_cli.parent.mkdir(parents=True)
    next_cli.write_text("#!/usr/bin/env node\n", encoding="utf-8")
    next_cli.chmod(0o755)

    monkeypatch.setattr(replit_runtime, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(replit_runtime, "FRONTEND_ROOT", frontend)
    monkeypatch.setattr(local_database, "BINARY_PATH", database)
    monkeypatch.setattr(replit_runtime.shutil, "which", lambda name: "/usr/bin/node")
    environment = replit_runtime.validated_environment(
        secure_environment(UV_PROJECT_ENVIRONMENT=".pythonlibs")
    )
    environment["SURREAL_DATA_PATH"] = str(tmp_path / "data" / "database.db")

    services = replit_runtime.service_definitions(environment)

    assert services[1].command[0] == str(environment_bin / "python")
    assert services[2].command[0] == str(
        environment_bin / "surreal-commands-worker"
    )


def test_replit_frontend_and_database_receive_only_required_secrets():
    environment = replit_runtime.validated_environment(secure_environment())

    frontend = replit_runtime.environment_for_service("frontend", environment)
    database = replit_runtime.environment_for_service("database", environment)
    api = replit_runtime.environment_for_service("api", environment)
    worker = replit_runtime.environment_for_service("worker", environment)

    assert "OPENROUTER_API_KEY" not in frontend
    assert "OPEN_NOTEBOOK_PASSWORD" not in frontend
    assert "OPENROUTER_API_KEY" not in database
    assert "SURREAL_PASSWORD" not in database
    assert database["SURREAL_PASS"] == environment["SURREAL_PASSWORD"]
    assert api["OPENROUTER_API_KEY"] == environment["OPENROUTER_API_KEY"]
    assert "SURREAL_PASS" not in api
    assert worker["OPENROUTER_API_KEY"] == environment["OPENROUTER_API_KEY"]
    assert "OPEN_NOTEBOOK_PASSWORD" not in worker
    assert "SURREAL_PASS" not in worker


def test_replit_readiness_requires_a_successful_response(
    monkeypatch: pytest.MonkeyPatch,
):
    response = MagicMock()
    response.__enter__.return_value.status = 204
    monkeypatch.setattr(replit_runtime.urllib.request, "urlopen", lambda *args, **kwargs: response)

    assert replit_runtime._url_is_ready("http://127.0.0.1:8502/healthz") is True


def test_replit_readiness_rejects_auth_and_server_errors(
    monkeypatch: pytest.MonkeyPatch,
):
    for status in (401, 503):
        error = urllib.error.HTTPError(
            "http://127.0.0.1:8502/healthz", status, "not ready", Message(), None
        )
        monkeypatch.setattr(
            replit_runtime.urllib.request,
            "urlopen",
            lambda *args, error=error, **kwargs: (_ for _ in ()).throw(error),
        )

        assert replit_runtime._url_is_ready("http://127.0.0.1:8502/healthz") is False


def test_replit_configuration_builds_and_runs_the_full_stack():
    configuration = tomllib.loads((ROOT / ".replit").read_text(encoding="utf-8"))

    assert configuration["modules"] == ["nodejs-22", "python-base-3.12"]
    assert configuration["run"]["args"][-1] == "scripts/replit_runtime.py"
    assert "uv sync --frozen --no-dev" in configuration["deployment"]["build"]
    assert "npm ci" in configuration["deployment"]["build"]
    assert "npm run build" in configuration["deployment"]["build"]
    assert configuration["deployment"]["run"][-1] == "scripts/replit_runtime.py"
    assert configuration["ports"] == [{"localPort": 8502, "externalPort": 80}]
    assert "ffmpeg" in (ROOT / "replit.nix").read_text(encoding="utf-8")


def test_replit_build_validation_requires_frontend_and_ffmpeg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(replit_build.shutil, "which", lambda name: "/nix/store/ffmpeg")
    with pytest.raises(RuntimeError, match="standalone"):
        replit_build.validate_build_artifacts(tmp_path)


def test_replit_build_validation_requires_source_tree_static_assets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(replit_build.shutil, "which", lambda name: "/nix/store/ffmpeg")
    standalone = tmp_path / "frontend" / ".next" / "standalone" / "server.js"
    standalone.parent.mkdir(parents=True)
    standalone.write_text("", encoding="utf-8")
    (tmp_path / "frontend" / ".next" / "BUILD_ID").write_text(
        "build-id", encoding="utf-8"
    )

    with pytest.raises(RuntimeError, match="production assets"):
        replit_build.validate_build_artifacts(tmp_path)
