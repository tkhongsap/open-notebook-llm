#!/usr/bin/env python3
"""Manage a safe, detached Open Notebook development stack on localhost."""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

try:
    from scripts import local_database
except ModuleNotFoundError:  # Direct execution: `python scripts/local_stack.py`
    import local_database  # type: ignore[no-redef]

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = REPO_ROOT / "frontend"
RUNTIME_ROOT = REPO_ROOT / ".runtime" / "open-notebook"
PID_ROOT = RUNTIME_ROOT / "run"
LOG_ROOT = RUNTIME_ROOT / "logs"


@dataclass(frozen=True)
class Service:
    name: str
    command: tuple[str, ...]
    marker: str
    cwd: Path
    port: int | None = None
    ready_url: str | None = None

    @property
    def pid_path(self) -> Path:
        return PID_ROOT / f"{self.name}.pid"

    @property
    def log_path(self) -> Path:
        return LOG_ROOT / f"{self.name}.log"


def _find_executable(name: str) -> str:
    executable = shutil.which(name)
    if not executable:
        raise RuntimeError(f"Required executable is missing: {name}")
    return executable


def find_node() -> str:
    configured = os.environ.get("NODE", "").strip()
    locked_nodes = sorted(
        (REPO_ROOT / ".venv/lib").glob(
            "python*/site-packages/nodejs_wheel/bin/node"
        )
    )
    candidates = [Path(configured) if configured else None, *locked_nodes]
    for candidate in candidates:
        if candidate and candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return _find_executable("node")


def ensure_frontend_native_modules(frontend_root: Path = FRONTEND_ROOT) -> None:
    """Provide Lightning CSS's documented fallback path for hardened macOS.

    npm installs the platform binary as an optional sibling package. Next's
    Turbopack worker may be unable to resolve that sibling from a generated
    chunk, at which point Lightning CSS deliberately falls back to a binary
    inside its own package. Linking the already locked optional dependency to
    that fallback keeps the install reproducible and does not modify Git files.
    """
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        return
    node_modules = frontend_root / "node_modules"
    source = (
        node_modules
        / "lightningcss-darwin-arm64"
        / "lightningcss.darwin-arm64.node"
    )
    destination = node_modules / "lightningcss" / "lightningcss.darwin-arm64.node"
    if destination.exists():
        return
    if not source.is_file():
        raise RuntimeError(
            "Missing lightningcss-darwin-arm64. Reinstall frontend dependencies "
            "from package-lock.json."
        )
    destination.symlink_to(source)


def runtime_environment() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("SURREAL_URL", "ws://127.0.0.1:8000/rpc")
    env.setdefault("SURREAL_USER", "root")
    env.setdefault("SURREAL_PASSWORD", "root")
    env.setdefault("SURREAL_NAMESPACE", "open_notebook")
    env.setdefault("SURREAL_DATABASE", "open_notebook")
    env.setdefault("OPEN_NOTEBOOK_WORKER_MAX_TASKS", "1")
    env["API_RELOAD"] = "false"
    # Next/Turbopack spawns helper Node processes through PATH. Keep those on
    # the same unsigned locked Node runtime as the parent so macOS does not
    # reject npm's unsigned native extensions for a Team-ID mismatch.
    node_bin = str(Path(find_node()).parent)
    env["PATH"] = os.pathsep.join(
        part for part in (node_bin, env.get("PATH", "")) if part
    )
    return env


def service_definitions() -> tuple[Service, ...]:
    uv = _find_executable("uv")
    env_file = str(REPO_ROOT / ".env")
    next_cli = FRONTEND_ROOT / "node_modules/next/dist/bin/next"
    if not next_cli.is_file():
        raise RuntimeError(
            "Frontend dependencies are missing. Run `cd frontend && npm ci` first."
        )
    return (
        Service(
            name="api",
            command=(uv, "run", "--env-file", env_file, "run_api.py"),
            marker="run_api.py",
            cwd=REPO_ROOT,
            port=5055,
            ready_url="http://127.0.0.1:5055/health",
        ),
        Service(
            name="worker",
            command=(
                uv,
                "run",
                "--env-file",
                env_file,
                "surreal-commands-worker",
                "--import-modules",
                "commands",
                "--max-tasks",
                runtime_environment()["OPEN_NOTEBOOK_WORKER_MAX_TASKS"],
            ),
            marker="surreal-commands-worker",
            cwd=REPO_ROOT,
        ),
        Service(
            name="frontend",
            command=(
                find_node(),
                str(next_cli),
                "dev",
                "--hostname",
                "127.0.0.1",
            ),
            marker="next/dist/bin/next dev",
            cwd=FRONTEND_ROOT,
            port=3000,
            ready_url="http://127.0.0.1:3000/notebooks",
        ),
    )


def read_pid(service: Service) -> int | None:
    try:
        return int(service.pid_path.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        return None


def pid_matches_service(service: Service, pid: int) -> bool:
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        capture_output=True,
        check=False,
        text=True,
        timeout=2,
    )
    return result.returncode == 0 and service.marker in result.stdout


def service_is_running(service: Service) -> bool:
    pid = read_pid(service)
    return bool(pid and pid_matches_service(service, pid))


def tcp_is_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.settimeout(0.25)
        return connection.connect_ex(("127.0.0.1", port)) == 0


def url_is_ready(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=1) as response:  # noqa: S310
            return response.status < 500
    except urllib.error.HTTPError as exc:
        return exc.code < 500
    except (urllib.error.URLError, TimeoutError):
        return False


def start_service(service: Service, env: dict[str, str]) -> None:
    if service_is_running(service):
        print(f"{service.name}: already running")
        return
    if service.port and tcp_is_open(service.port):
        raise RuntimeError(
            f"{service.name}: port {service.port} belongs to an unmanaged process"
        )

    PID_ROOT.mkdir(parents=True, exist_ok=True)
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    with service.log_path.open("ab") as log_handle:
        process = subprocess.Popen(  # noqa: S603
            service.command,
            cwd=service.cwd,
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    service.pid_path.write_text(f"{process.pid}\n", encoding="utf-8")

    attempts = 240 if service.ready_url else 8
    for _ in range(attempts):
        if process.poll() is not None:
            service.pid_path.unlink(missing_ok=True)
            raise RuntimeError(
                f"{service.name}: exited during startup; inspect {service.log_path}"
            )
        ready = url_is_ready(service.ready_url) if service.ready_url else True
        if ready:
            print(f"{service.name}: ready")
            return
        time.sleep(0.25)

    stop_service(service)
    raise RuntimeError(f"{service.name}: startup timeout; inspect {service.log_path}")


def stop_service(service: Service) -> None:
    pid = read_pid(service)
    if not pid or not pid_matches_service(service, pid):
        service.pid_path.unlink(missing_ok=True)
        print(f"{service.name}: stopped")
        return

    os.killpg(pid, signal.SIGTERM)
    for _ in range(40):
        if not pid_matches_service(service, pid):
            service.pid_path.unlink(missing_ok=True)
            print(f"{service.name}: stopped")
            return
        time.sleep(0.25)
    if pid_matches_service(service, pid):
        os.killpg(pid, signal.SIGKILL)
    service.pid_path.unlink(missing_ok=True)
    print(f"{service.name}: force-stopped")


def start_stack() -> None:
    if not (REPO_ROOT / ".env").is_file():
        raise RuntimeError("Missing .env; copy .env.example and set an encryption key")
    ensure_frontend_native_modules()
    local_database.start_database()
    env = runtime_environment()
    started: list[Service] = []
    try:
        for service in service_definitions():
            start_service(service, env)
            started.append(service)
    except Exception:
        for service in reversed(started):
            stop_service(service)
        raise
    print("Open Notebook ready at http://127.0.0.1:3000")


def stop_stack() -> None:
    for service in reversed(service_definitions()):
        stop_service(service)
    local_database.stop_database()


def status_stack() -> bool:
    statuses = [("database", local_database.status_database())]
    for service in service_definitions():
        running = service_is_running(service)
        if service.port:
            running = running and tcp_is_open(service.port)
        statuses.append((service.name, running))
        print(f"{service.name}: {'running' if running else 'stopped'}")
    return all(running for _, running in statuses)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("start", "stop", "status"))
    args = parser.parse_args()
    try:
        if args.command == "start":
            start_stack()
        elif args.command == "stop":
            stop_stack()
        elif not status_stack():
            return 1
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
