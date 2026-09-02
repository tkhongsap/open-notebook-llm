#!/usr/bin/env python3
"""Install and manage the pinned native SurrealDB runtime.

Docker remains the production/deployment contract. This helper exists for macOS
developer machines where Docker is unavailable and for the Replit deployment
launcher, whose managed runtime does not execute this repository's Dockerfile.
The downloaded archive is verified before extraction and every listener is
bound to loopback.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import tarfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

SURREAL_VERSION = "v2.6.5"


@dataclass(frozen=True)
class Asset:
    filename: str
    sha256: str

    @property
    def url(self) -> str:
        return (
            "https://github.com/surrealdb/surrealdb/releases/download/"
            f"{SURREAL_VERSION}/{self.filename}"
        )


SUPPORTED_ASSETS = {
    ("Darwin", "arm64"): Asset(
        filename="surreal-v2.6.5.darwin-arm64.tgz",
        sha256="71d031be990d59ed57e41e147fda7463660a2b449ae91868c83eb0888d07fade",
    ),
    ("Linux", "x86_64"): Asset(
        filename="surreal-v2.6.5.linux-amd64.tgz",
        sha256="929d73f46c4fb59f237810e6fe6da54c1756064f3ed8d7d1f6a970e8fdf38fb0",
    ),
}

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = REPO_ROOT / ".runtime" / "surrealdb"
BINARY_PATH = RUNTIME_ROOT / "bin" / "surreal"
DOWNLOAD_ROOT = RUNTIME_ROOT / "downloads"
RUN_ROOT = RUNTIME_ROOT / "run"
LOG_PATH = RUNTIME_ROOT / "logs" / "surrealdb.log"
PID_PATH = RUN_ROOT / "surrealdb.pid"
DATA_PATH = RUNTIME_ROOT / "data" / "open-notebook.db"
HOST = "127.0.0.1"
PORT = 8000


def select_asset(system: str | None = None, machine: str | None = None) -> Asset:
    """Return the verified release asset for this developer platform."""
    key = (system or platform.system(), machine or platform.machine())
    try:
        return SUPPORTED_ASSETS[key]
    except KeyError as exc:
        raise RuntimeError(
            f"Native SurrealDB bootstrap is not supported on {key[0]} {key[1]}. "
            "Install the pinned SurrealDB v2 binary manually or use Docker Compose."
        ) from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def install_binary() -> Path:
    """Install the pinned SurrealDB binary after verifying its archive."""
    if BINARY_PATH.is_file():
        return BINARY_PATH

    asset = select_asset()
    DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    BINARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    archive_path = DOWNLOAD_ROOT / asset.filename
    partial_path = archive_path.with_suffix(archive_path.suffix + ".part")

    if not archive_path.is_file() or sha256_file(archive_path) != asset.sha256:
        request = urllib.request.Request(
            asset.url,
            headers={"User-Agent": "open-notebook-local-bootstrap"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            with partial_path.open("wb") as destination:
                shutil.copyfileobj(response, destination)
        if sha256_file(partial_path) != asset.sha256:
            partial_path.unlink(missing_ok=True)
            raise RuntimeError("Downloaded SurrealDB archive failed SHA-256 verification")
        partial_path.replace(archive_path)

    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        if len(members) != 1 or members[0].name != "surreal" or not members[0].isfile():
            raise RuntimeError("Unexpected SurrealDB archive contents")
        extracted = archive.extractfile(members[0])
        if extracted is None:
            raise RuntimeError("SurrealDB binary was missing from its archive")
        with BINARY_PATH.open("wb") as destination:
            shutil.copyfileobj(extracted, destination)
    BINARY_PATH.chmod(0o755)
    print(f"Installed SurrealDB {SURREAL_VERSION} at {BINARY_PATH}")
    return BINARY_PATH


def tcp_is_open(host: str = HOST, port: int = PORT) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.settimeout(0.25)
        return connection.connect_ex((host, port)) == 0


def read_pid() -> int | None:
    try:
        return int(PID_PATH.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        return None


def pid_matches_database(pid: int) -> bool:
    """Only recognize the exact managed command, preventing PID-reuse kills."""
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        capture_output=True,
        check=False,
        text=True,
        timeout=2,
    )
    command = result.stdout.strip()
    return (
        result.returncode == 0
        and str(BINARY_PATH) in command
        and " start " in f" {command} "
    )


def is_running() -> bool:
    pid = read_pid()
    return bool(pid and pid_matches_database(pid))


def start_database() -> None:
    if is_running():
        print(f"SurrealDB is already running on http://{HOST}:{PORT}")
        return
    if tcp_is_open():
        raise RuntimeError(
            f"Port {PORT} is already in use by an unmanaged process; refusing to start"
        )

    binary = install_binary()
    for path in (RUN_ROOT, LOG_PATH.parent, DATA_PATH.parent):
        path.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["SURREAL_EXPERIMENTAL_GRAPHQL"] = "true"
    username = env.get("SURREAL_USER", "root")
    password = env.get("SURREAL_PASSWORD", "root")
    command = [
        str(binary),
        "start",
        "--log",
        "info",
        "--user",
        username,
        "--pass",
        password,
        "--bind",
        f"{HOST}:{PORT}",
        f"rocksdb:{DATA_PATH}",
    ]

    with LOG_PATH.open("ab") as log_handle:
        process = subprocess.Popen(  # noqa: S603
            command,
            cwd=REPO_ROOT,
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    PID_PATH.write_text(f"{process.pid}\n", encoding="utf-8")

    for _ in range(120):
        if process.poll() is not None:
            PID_PATH.unlink(missing_ok=True)
            raise RuntimeError(f"SurrealDB exited during startup; inspect {LOG_PATH}")
        if tcp_is_open():
            print(f"SurrealDB ready on http://{HOST}:{PORT}")
            return
        time.sleep(0.25)

    stop_database()
    raise RuntimeError(f"SurrealDB did not become ready; inspect {LOG_PATH}")


def stop_database() -> None:
    pid = read_pid()
    if not pid or not pid_matches_database(pid):
        PID_PATH.unlink(missing_ok=True)
        print("SurrealDB is not running")
        return

    os.killpg(pid, signal.SIGTERM)
    for _ in range(40):
        if not pid_matches_database(pid):
            PID_PATH.unlink(missing_ok=True)
            print("SurrealDB stopped")
            return
        time.sleep(0.25)

    if pid_matches_database(pid):
        os.killpg(pid, signal.SIGKILL)
    PID_PATH.unlink(missing_ok=True)
    print("SurrealDB force-stopped after the shutdown timeout")


def status_database() -> bool:
    running = is_running() and tcp_is_open()
    print(
        f"SurrealDB: {'running' if running else 'stopped'} "
        f"(http://{HOST}:{PORT})"
    )
    return running


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("install", "start", "stop", "status"))
    args = parser.parse_args()
    try:
        if args.command == "install":
            install_binary()
        elif args.command == "start":
            start_database()
        elif args.command == "stop":
            stop_database()
        elif not status_database():
            return 1
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
