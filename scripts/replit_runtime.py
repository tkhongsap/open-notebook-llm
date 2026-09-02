#!/usr/bin/env python3
"""Run the complete Open Notebook stack in Replit's managed runtime.

Replit executes ``.replit`` build and run commands rather than the repository's
Dockerfile. This launcher preserves the single-service image contract: a
loopback-only SurrealDB, FastAPI API, and command worker sit behind the public
Next.js server. It intentionally permits only OpenRouter/cloud models.
"""

from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from open_notebook.exceptions import ConfigurationError
from open_notebook.utils.security_config import validate_production_security
from scripts import local_database

FRONTEND_ROOT = REPO_ROOT / "frontend"
DEFAULT_PORT = 8502
DEFAULT_STARTUP_TIMEOUT_SECONDS = 180


@dataclass(frozen=True)
class Service:
    name: str
    command: tuple[str, ...]
    cwd: Path
    ready_url: str | None = None
    ready_port: int | None = None


def _hostname(value: str) -> str:
    """Return a bare, valid hostname from a Replit domain variable."""

    candidate = value.strip()
    if not candidate:
        return ""
    parsed = urlsplit(candidate if "://" in candidate else f"https://{candidate}")
    return parsed.hostname or ""


def derive_cors_origins(environment: Mapping[str, str]) -> str:
    """Derive explicit same-origin CORS entries without ever using ``*``."""

    configured = (environment.get("CORS_ORIGINS") or "").strip()
    if configured:
        return configured

    hosts: list[str] = []
    for candidate in (environment.get("REPLIT_DOMAINS") or "").split(","):
        host = _hostname(candidate)
        if host and host not in hosts:
            hosts.append(host)
    development_host = _hostname(environment.get("REPLIT_DEV_DOMAIN") or "")
    if development_host and development_host not in hosts:
        hosts.append(development_host)
    if not hosts:
        raise ConfigurationError(
            "CORS_ORIGINS is required when Replit domain variables are unavailable"
        )
    return ",".join(f"https://{host}" for host in hosts)


def validated_environment(
    environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build the Replit environment and fail closed on unsafe configuration."""

    values = dict(os.environ if environment is None else environment)
    values.setdefault("PORT", str(DEFAULT_PORT))
    values.setdefault("SURREAL_USER", "open_notebook_admin")
    values.setdefault("SURREAL_NAMESPACE", "open_notebook")
    values.setdefault("SURREAL_DATABASE", "open_notebook")
    values.setdefault(
        "SURREAL_DATA_PATH", str(REPO_ROOT / "data" / "surrealdb" / "open-notebook.db")
    )
    values.setdefault("OPEN_NOTEBOOK_WORKER_MAX_TASKS", "1")
    values.setdefault("OPEN_NOTEBOOK_REQUIRE_SECURITY", "true")
    values.setdefault("OPEN_NOTEBOOK_MODEL_ROUTING_POLICY", "cloud-only")
    values.setdefault(
        "TIKTOKEN_CACHE_DIR", str(REPO_ROOT / ".runtime" / "tiktoken-cache")
    )

    # These internal endpoints are deliberately not operator-configurable in
    # this single-host profile. Only the Next.js port is public.
    values["API_HOST"] = "127.0.0.1"
    values["API_PORT"] = "5055"
    values["API_RELOAD"] = "false"
    values["INTERNAL_API_URL"] = "http://127.0.0.1:5055"
    values["SURREAL_URL"] = "ws://127.0.0.1:8000/rpc"
    values["HOSTNAME"] = "0.0.0.0"
    values["NODE_ENV"] = "production"
    values["CORS_ORIGINS"] = derive_cors_origins(values)

    if values["OPEN_NOTEBOOK_REQUIRE_SECURITY"].strip().lower() != "true":
        raise ConfigurationError(
            "The Replit profile requires OPEN_NOTEBOOK_REQUIRE_SECURITY=true"
        )
    if values["OPEN_NOTEBOOK_MODEL_ROUTING_POLICY"].strip().lower() != "cloud-only":
        raise ConfigurationError(
            "The Replit profile requires OPEN_NOTEBOOK_MODEL_ROUTING_POLICY=cloud-only"
        )
    if not (values.get("OPENROUTER_API_KEY") or "").strip():
        raise ConfigurationError("OPENROUTER_API_KEY is required for the Replit profile")

    try:
        port = int(values["PORT"])
        worker_tasks = int(values["OPEN_NOTEBOOK_WORKER_MAX_TASKS"])
    except ValueError as exc:
        raise ConfigurationError(
            "PORT and OPEN_NOTEBOOK_WORKER_MAX_TASKS must be integers"
        ) from exc
    if not 1 <= port <= 65535:
        raise ConfigurationError("PORT must be between 1 and 65535")
    if not 1 <= worker_tasks <= 32:
        raise ConfigurationError(
            "OPEN_NOTEBOOK_WORKER_MAX_TASKS must be between 1 and 32"
        )

    validate_production_security(values)
    # SurrealDB reads SURREAL_PASS, while the application uses
    # SURREAL_PASSWORD. Keeping the value in the environment avoids leaking it
    # through process arguments or startup logs.
    values["SURREAL_PASS"] = values["SURREAL_PASSWORD"]
    values["SURREAL_EXPERIMENTAL_GRAPHQL"] = "true"
    return values


def _require_executable(path: Path, description: str) -> str:
    if not path.is_file() or not os.access(path, os.X_OK):
        raise RuntimeError(f"Missing {description}: {path}")
    return str(path)


def _project_environment(environment: Mapping[str, str]) -> Path:
    """Return uv's configured project environment, relative to the repository."""

    configured = (environment.get("UV_PROJECT_ENVIRONMENT") or ".venv").strip()
    path = Path(configured).expanduser()
    return path if path.is_absolute() else REPO_ROOT / path


def service_definitions(environment: Mapping[str, str]) -> tuple[Service, ...]:
    """Return the four-process Replit service graph in startup order."""

    environment_bin = _project_environment(environment) / "bin"
    python = _require_executable(environment_bin / "python", "Python runtime")
    worker = _require_executable(
        environment_bin / "surreal-commands-worker",
        "command worker",
    )
    database = _require_executable(local_database.BINARY_PATH, "SurrealDB runtime")
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Missing Node.js runtime")
    next_cli = FRONTEND_ROOT / "node_modules" / "next" / "dist" / "bin" / "next"
    build_id = FRONTEND_ROOT / ".next" / "BUILD_ID"
    static_assets = FRONTEND_ROOT / ".next" / "static"
    if (
        not next_cli.is_file()
        or not os.access(next_cli, os.X_OK)
        or not build_id.is_file()
        or not static_assets.is_dir()
    ):
        raise RuntimeError("Missing production frontend build; run the Replit build command")

    database_path = Path(environment["SURREAL_DATA_PATH"])
    database_path.parent.mkdir(parents=True, exist_ok=True)
    port = int(environment["PORT"])
    return (
        Service(
            name="database",
            command=(
                database,
                "start",
                "--log",
                "info",
                "--bind",
                "127.0.0.1:8000",
                f"rocksdb:{database_path}",
            ),
            cwd=REPO_ROOT,
            ready_port=8000,
        ),
        Service(
            name="api",
            command=(python, "run_api.py"),
            cwd=REPO_ROOT,
            ready_url="http://127.0.0.1:5055/ready",
        ),
        Service(
            name="worker",
            command=(
                worker,
                "--import-modules",
                "commands",
                "--max-tasks",
                environment["OPEN_NOTEBOOK_WORKER_MAX_TASKS"],
            ),
            cwd=REPO_ROOT,
        ),
        Service(
            name="frontend",
            # Replit retains the source-tree build layout. ``next start`` serves
            # ``.next/static`` from that layout, while the standalone server
            # expects Docker's copied runtime layout and otherwise returns 404
            # for every browser chunk.
            command=(node, str(next_cli), "start"),
            cwd=FRONTEND_ROOT,
            ready_url=f"http://127.0.0.1:{port}/healthz",
        ),
    )


def _tcp_is_ready(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.settimeout(0.25)
        return connection.connect_ex(("127.0.0.1", port)) == 0


def _url_is_ready(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:  # noqa: S310
            return 200 <= response.status < 400
    except urllib.error.HTTPError:
        return False
    except (urllib.error.URLError, TimeoutError):
        return False


def _wait_until_ready(
    service: Service,
    process: subprocess.Popen[bytes],
    timeout_seconds: int,
) -> None:
    if service.ready_port is None and service.ready_url is None:
        time.sleep(1)
        if process.poll() is not None:
            raise RuntimeError(
                f"{service.name} exited during startup with code {process.returncode}"
            )
        return

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"{service.name} exited during startup with code {process.returncode}"
            )
        if service.ready_port is not None and _tcp_is_ready(service.ready_port):
            return
        if service.ready_url is not None and _url_is_ready(service.ready_url):
            return
        time.sleep(0.25)
    raise RuntimeError(f"{service.name} did not become ready within {timeout_seconds}s")


def _terminate(processes: list[subprocess.Popen[bytes]]) -> None:
    for process in reversed(processes):
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and any(p.poll() is None for p in processes):
        time.sleep(0.1)
    for process in reversed(processes):
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def environment_for_service(
    service_name: str, environment: Mapping[str, str]
) -> dict[str, str]:
    """Limit credentials to the processes that actually need them."""

    scoped = dict(environment)
    if service_name == "database":
        for key in (
            "OPENROUTER_API_KEY",
            "OPEN_NOTEBOOK_ENCRYPTION_KEY",
            "OPEN_NOTEBOOK_PASSWORD",
            "SURREAL_PASSWORD",
        ):
            scoped.pop(key, None)
    elif service_name == "frontend":
        for key in (
            "OPENROUTER_API_KEY",
            "OPEN_NOTEBOOK_ENCRYPTION_KEY",
            "OPEN_NOTEBOOK_PASSWORD",
            "SURREAL_PASSWORD",
            "SURREAL_PASS",
        ):
            scoped.pop(key, None)
    elif service_name == "worker":
        scoped.pop("OPEN_NOTEBOOK_PASSWORD", None)
        scoped.pop("SURREAL_PASS", None)
    else:
        # The application uses SURREAL_PASSWORD. SURREAL_PASS exists only for
        # the database binary and does not need to be duplicated here.
        scoped.pop("SURREAL_PASS", None)
    return scoped


def run_stack(environment: Mapping[str, str] | None = None) -> int:
    env = validated_environment(environment)
    local_database.install_binary()
    services = service_definitions(env)
    try:
        startup_timeout = int(
            env.get(
                "REPLIT_STARTUP_TIMEOUT_SECONDS",
                str(DEFAULT_STARTUP_TIMEOUT_SECONDS),
            )
        )
    except ValueError as exc:
        raise ConfigurationError(
            "REPLIT_STARTUP_TIMEOUT_SECONDS must be an integer"
        ) from exc
    if not 30 <= startup_timeout <= 600:
        raise ConfigurationError(
            "REPLIT_STARTUP_TIMEOUT_SECONDS must be between 30 and 600"
        )

    stopped = threading.Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stopped.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    processes: list[subprocess.Popen[bytes]] = []
    try:
        for service in services:
            print(f"[replit] starting {service.name}", flush=True)
            process = subprocess.Popen(  # noqa: S603
                service.command,
                cwd=service.cwd,
                env=environment_for_service(service.name, env),
                start_new_session=True,
            )
            processes.append(process)
            _wait_until_ready(service, process, startup_timeout)
            print(f"[replit] {service.name} ready", flush=True)

        print(
            f"[replit] Open Notebook ready on 0.0.0.0:{env['PORT']} "
            "(routing policy: cloud-only)",
            flush=True,
        )
        while not stopped.wait(0.5):
            for service, process in zip(services, processes, strict=True):
                if process.poll() is not None:
                    raise RuntimeError(
                        f"{service.name} exited unexpectedly with code {process.returncode}"
                    )
        return 0
    finally:
        _terminate(processes)


def main() -> int:
    try:
        return run_stack()
    except (ConfigurationError, RuntimeError) as exc:
        # Configuration errors name variables but validation deliberately never
        # includes their values.
        print(f"[replit] startup failed: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
