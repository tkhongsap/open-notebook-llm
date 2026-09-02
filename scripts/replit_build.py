#!/usr/bin/env python3
"""Verify and pre-cache artifacts required by the Replit runtime."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import local_database


def validate_build_artifacts(root: Path = REPO_ROOT) -> None:
    if not (3, 11) <= sys.version_info[:2] < (3, 13):
        raise RuntimeError("Open Notebook requires Python 3.11 or 3.12")
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required for podcast generation")
    standalone_server = root / "frontend" / ".next" / "standalone" / "server.js"
    if not standalone_server.is_file():
        raise RuntimeError("Next.js standalone build is missing")
    build_id = root / "frontend" / ".next" / "BUILD_ID"
    static_assets = root / "frontend" / ".next" / "static"
    if not build_id.is_file() or not static_assets.is_dir():
        raise RuntimeError("Next.js source-tree production assets are missing")


def main() -> int:
    os.environ.setdefault(
        "TIKTOKEN_CACHE_DIR", str(REPO_ROOT / ".runtime" / "tiktoken-cache")
    )
    import tiktoken

    local_database.install_binary()
    tiktoken.get_encoding("o200k_base")
    validate_build_artifacts()
    print("Replit runtime artifacts verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
