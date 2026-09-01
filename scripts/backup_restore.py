#!/usr/bin/env python3
"""Create and restore portable Open Notebook backups.

The archive contains a SurrealQL export, the durable ``data`` directory, a
manifest, and SHA-256 checksums. Database passwords are passed to the SurrealDB
CLI through ``SURREAL_PASS`` and never placed in process arguments or logs.

Restore intentionally imports into the configured database without deleting it.
Use an empty database name for disaster recovery, validate it, and then switch
the deployment. Existing data directories are preserved beside the restored
directory when ``--overwrite-data`` is explicitly selected.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from dotenv import dotenv_values

ARCHIVE_ROOT = "open-notebook-backup"
MANIFEST_VERSION = 1
RELATION_TABLE_RE = re.compile(
    r"^\s*DEFINE\s+TABLE\s+(?P<table>[^\s;]+)\s+TYPE\s+RELATION\b",
    re.IGNORECASE,
)
RELATION_ENDPOINT_FIELD_RE = re.compile(
    r"^\s*DEFINE\s+FIELD\s+(?P<field>in|out)\s+ON\s+(?P<table>[^\s;]+)\b",
    re.IGNORECASE,
)
TYPED_ARRAY_FIELD_RE = re.compile(
    r"^\s*DEFINE\s+FIELD\s+(?P<field>[^\s;]+)\s+ON\s+"
    r"(?P<table>[^\s;]+)\s+TYPE\s+.*\barray\s*<",
    re.IGNORECASE,
)
ARRAY_ITEM_FIELD_RE = re.compile(
    r"^\s*DEFINE\s+FIELD\s+(?P<field>[^\s;]+)\[\*\]\s+ON\s+"
    r"(?P<table>[^\s;]+)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DatabaseConfig:
    endpoint: str
    username: str
    password: str
    namespace: str
    database: str


def normalize_cli_endpoint(endpoint: str) -> str:
    """Convert an SDK websocket URL into a SurrealDB CLI HTTP endpoint."""

    parsed = urlsplit(endpoint)
    scheme = {"ws": "http", "wss": "https"}.get(parsed.scheme, parsed.scheme)
    path = parsed.path.rstrip("/")
    if path.endswith("/rpc"):
        path = path[: -len("/rpc")]
    return urlunsplit((scheme, parsed.netloc, path, "", ""))


def find_surreal_binary(candidate: str | None = None) -> Path:
    if candidate:
        path = Path(candidate).expanduser().resolve()
        if path.is_file() and os.access(path, os.X_OK):
            return path
        raise FileNotFoundError(f"SurrealDB CLI is not executable: {path}")

    repository_binary = (
        Path(__file__).resolve().parents[1] / ".runtime/surrealdb/bin/surreal"
    )
    if repository_binary.is_file() and os.access(repository_binary, os.X_OK):
        return repository_binary

    discovered = shutil.which("surreal")
    if discovered:
        return Path(discovered).resolve()
    raise FileNotFoundError(
        "SurrealDB CLI not found. Start the native stack once or pass --surreal-bin."
    )


def load_database_config(env_file: Path | None = None) -> DatabaseConfig:
    values: dict[str, str] = {}
    if env_file:
        values.update(
            {
                key: str(value)
                for key, value in dotenv_values(env_file).items()
                if value is not None
            }
        )
    values.update({key: value for key, value in os.environ.items() if value})

    return DatabaseConfig(
        endpoint=values.get("SURREAL_URL", "ws://127.0.0.1:8000/rpc"),
        username=values.get("SURREAL_USER", "root"),
        password=values.get("SURREAL_PASSWORD", "root"),
        namespace=values.get("SURREAL_NAMESPACE", "open_notebook"),
        database=values.get("SURREAL_DATABASE", "open_notebook"),
    )


def _surreal_environment(config: DatabaseConfig) -> dict[str, str]:
    environment = os.environ.copy()
    environment["SURREAL_PASS"] = config.password
    return environment


def _database_args(binary: Path, action: str, config: DatabaseConfig) -> list[str]:
    return [
        str(binary),
        action,
        "--endpoint",
        normalize_cli_endpoint(config.endpoint),
        "--username",
        config.username,
        "--namespace",
        config.namespace,
        "--database",
        config.database,
    ]


def _run_export(binary: Path, config: DatabaseConfig, destination: Path) -> None:
    subprocess.run(
        [*_database_args(binary, "export", config), str(destination)],
        check=True,
        env=_surreal_environment(config),
    )


def _run_import(binary: Path, config: DatabaseConfig, source: Path) -> None:
    subprocess.run(
        [*_database_args(binary, "import", config), str(source)],
        check=True,
        env=_surreal_environment(config),
    )


def _prepare_import_script(source: Path, destination: Path) -> None:
    """Remove relation endpoint fields duplicated by SurrealDB 2.x exports.

    ``TYPE RELATION IN ... OUT ...`` creates the ``in`` and ``out`` fields
    implicitly. SurrealDB 2.6 exports those fields again as explicit
    ``DEFINE FIELD`` statements, which makes importing the export into a fresh
    database fail. Preserve the checksummed raw export and normalize only the
    temporary script passed to the importer.
    """

    lines = source.read_text(encoding="utf-8").splitlines(keepends=True)
    relation_tables = {
        match.group("table")
        for line in lines
        if (match := RELATION_TABLE_RE.match(line)) is not None
    }
    typed_array_fields = {
        (match.group("table"), match.group("field"))
        for line in lines
        if (match := TYPED_ARRAY_FIELD_RE.match(line)) is not None
        and "[" not in match.group("field")
    }

    normalized: list[str] = []
    for line in lines:
        field_match = RELATION_ENDPOINT_FIELD_RE.match(line)
        if field_match and field_match.group("table") in relation_tables:
            continue
        array_item_match = ARRAY_ITEM_FIELD_RE.match(line)
        if (
            array_item_match
            and (array_item_match.group("table"), array_item_match.group("field"))
            in typed_array_fields
        ):
            continue
        normalized.append(line)
    destination.write_text("".join(normalized), encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _checksums(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): _sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    }


def create_backup(
    output: Path,
    *,
    data_dir: Path,
    binary: Path,
    config: DatabaseConfig,
) -> Path:
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    data_dir = data_dir.expanduser().resolve()

    with tempfile.TemporaryDirectory(prefix="open-notebook-backup-") as temp_name:
        staging = Path(temp_name) / ARCHIVE_ROOT
        staging.mkdir()

        _run_export(binary, config, staging / "database.surql")
        staged_data = staging / "data"
        if data_dir.exists():
            shutil.copytree(data_dir, staged_data, symlinks=False)
        else:
            staged_data.mkdir()

        manifest = {
            "format_version": MANIFEST_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "namespace": config.namespace,
            "database": config.database,
            "checksums": _checksums(staging),
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        temporary_archive = Path(temp_name) / "backup.tar.gz"
        with tarfile.open(temporary_archive, "w:gz") as archive:
            archive.add(staging, arcname=ARCHIVE_ROOT, recursive=True)
        os.replace(temporary_archive, output)
        output.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return output


def _safe_extract(archive: tarfile.TarFile, destination: Path) -> None:
    destination = destination.resolve()
    for member in archive.getmembers():
        member_path = PurePosixPath(member.name)
        if (
            member_path.is_absolute()
            or ".." in member_path.parts
            or not member_path.parts
            or member_path.parts[0] != ARCHIVE_ROOT
            or member.issym()
            or member.islnk()
            or member.isdev()
        ):
            raise ValueError(f"Unsafe backup archive member: {member.name}")
        resolved = (destination / Path(*member_path.parts)).resolve()
        if not resolved.is_relative_to(destination):
            raise ValueError(f"Unsafe backup archive member: {member.name}")
    archive.extractall(destination, filter="data")


def _validate_staging(staging: Path) -> dict[str, Any]:
    manifest_path = staging / "manifest.json"
    database_path = staging / "database.surql"
    data_path = staging / "data"
    if (
        not manifest_path.is_file()
        or not database_path.is_file()
        or not data_path.is_dir()
    ):
        raise ValueError(
            "Backup archive is missing its manifest, database export, or data directory"
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format_version") != MANIFEST_VERSION:
        raise ValueError("Unsupported backup format version")
    expected = manifest.get("checksums")
    if not isinstance(expected, dict) or expected != _checksums(staging):
        raise ValueError("Backup checksum validation failed")
    return manifest


def _validate_restore_target(data_dir: Path) -> Path:
    resolved = data_dir.expanduser().resolve()
    forbidden = {Path("/").resolve(), Path.home().resolve(), Path.cwd().resolve()}
    if resolved in forbidden or len(resolved.parts) < 3:
        raise ValueError(f"Refusing unsafe restore target: {resolved}")
    return resolved


def restore_backup(
    archive_path: Path,
    *,
    data_dir: Path,
    binary: Path,
    config: DatabaseConfig,
    confirmed: bool,
    overwrite_data: bool,
) -> Path | None:
    if not confirmed:
        raise ValueError("Restore requires --confirm-restore")

    archive_path = archive_path.expanduser().resolve()
    if not archive_path.is_file():
        raise FileNotFoundError(f"Backup archive not found: {archive_path}")
    data_dir = _validate_restore_target(data_dir)

    with tempfile.TemporaryDirectory(prefix="open-notebook-restore-") as temp_name:
        extraction_root = Path(temp_name)
        with tarfile.open(archive_path, "r:gz") as archive:
            _safe_extract(archive, extraction_root)
        staging = extraction_root / ARCHIVE_ROOT
        _validate_staging(staging)

        if data_dir.exists() and any(data_dir.iterdir()) and not overwrite_data:
            raise FileExistsError(
                f"Restore target is not empty: {data_dir}. Pass --overwrite-data to preserve and replace it."
            )

        import_script = extraction_root / "database.import.surql"
        _prepare_import_script(staging / "database.surql", import_script)
        _run_import(binary, config, import_script)

        preserved: Path | None = None
        if data_dir.exists() and any(data_dir.iterdir()):
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            preserved = data_dir.with_name(f"{data_dir.name}.before-restore-{stamp}")
            if preserved.exists():
                raise FileExistsError(f"Preservation path already exists: {preserved}")
            shutil.move(str(data_dir), str(preserved))
        elif data_dir.exists():
            data_dir.rmdir()

        data_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(staging / "data", data_dir, symlinks=False)
        return preserved


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, help="Optional dotenv file")
    parser.add_argument("--surreal-bin", help="Path to the SurrealDB CLI")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(os.environ.get("OPEN_NOTEBOOK_DATA_DIR", "data")),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup = subparsers.add_parser("backup", help="Create a backup archive")
    backup.add_argument("output", type=Path)

    restore = subparsers.add_parser("restore", help="Restore a backup archive")
    restore.add_argument("archive", type=Path)
    restore.add_argument("--confirm-restore", action="store_true")
    restore.add_argument("--overwrite-data", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    config = load_database_config(args.env_file)
    binary = find_surreal_binary(args.surreal_bin)

    if args.command == "backup":
        output = create_backup(
            args.output,
            data_dir=args.data_dir,
            binary=binary,
            config=config,
        )
        print(f"Backup created: {output}")
        return 0

    preserved = restore_backup(
        args.archive,
        data_dir=args.data_dir,
        binary=binary,
        config=config,
        confirmed=args.confirm_restore,
        overwrite_data=args.overwrite_data,
    )
    print(f"Backup restored to database '{config.database}' and {args.data_dir}")
    if preserved:
        print(f"Previous data preserved at: {preserved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
