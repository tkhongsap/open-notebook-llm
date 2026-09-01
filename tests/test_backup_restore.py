import io
import json
import tarfile
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.backup_restore import (
    ARCHIVE_ROOT,
    DatabaseConfig,
    _database_args,
    _prepare_import_script,
    _safe_extract,
    _surreal_environment,
    create_backup,
    normalize_cli_endpoint,
    restore_backup,
)


@pytest.fixture
def database_config() -> DatabaseConfig:
    return DatabaseConfig(
        endpoint="ws://127.0.0.1:8000/rpc",
        username="root",
        password="private-database-password",
        namespace="open_notebook",
        database="open_notebook",
    )


def test_normalize_cli_endpoint_handles_websocket_rpc_urls():
    assert normalize_cli_endpoint("ws://127.0.0.1:8000/rpc") == "http://127.0.0.1:8000"
    assert (
        normalize_cli_endpoint("wss://db.example.com/rpc") == "https://db.example.com"
    )
    assert normalize_cli_endpoint("http://db.example.com") == "http://db.example.com"


def test_database_password_is_only_passed_in_environment(
    database_config: DatabaseConfig,
):
    args = _database_args(Path("/usr/bin/surreal"), "export", database_config)
    environment = _surreal_environment(database_config)

    assert database_config.password not in args
    assert environment["SURREAL_PASS"] == database_config.password


def test_prepare_import_script_removes_only_duplicate_relation_endpoint_fields(
    tmp_path: Path,
):
    source = tmp_path / "database.surql"
    destination = tmp_path / "database.import.surql"
    source.write_text(
        "DEFINE TABLE artifact TYPE RELATION IN note OUT notebook SCHEMALESS;\n"
        "DEFINE FIELD in ON artifact TYPE record<note>;\n"
        "DEFINE FIELD out ON artifact TYPE record<notebook>;\n"
        "DEFINE TABLE ordinary SCHEMAFULL;\n"
        "DEFINE FIELD in ON ordinary TYPE string;\n",
        encoding="utf-8",
    )

    _prepare_import_script(source, destination)

    assert destination.read_text(encoding="utf-8") == (
        "DEFINE TABLE artifact TYPE RELATION IN note OUT notebook SCHEMALESS;\n"
        "DEFINE TABLE ordinary SCHEMAFULL;\n"
        "DEFINE FIELD in ON ordinary TYPE string;\n"
    )


def test_prepare_import_script_removes_redundant_typed_array_item_field(
    tmp_path: Path,
):
    source = tmp_path / "database.surql"
    destination = tmp_path / "database.import.surql"
    source.write_text(
        "DEFINE TABLE note SCHEMAFULL;\n"
        "DEFINE FIELD embedding ON note TYPE option<array<float>>;\n"
        "DEFINE FIELD embedding[*] ON note TYPE float;\n"
        "DEFINE FIELD metadata ON note TYPE array;\n"
        "DEFINE FIELD metadata[*] ON note TYPE object;\n"
        "DEFINE FIELD metadata[*].name ON note TYPE string;\n",
        encoding="utf-8",
    )

    _prepare_import_script(source, destination)

    assert destination.read_text(encoding="utf-8") == (
        "DEFINE TABLE note SCHEMAFULL;\n"
        "DEFINE FIELD embedding ON note TYPE option<array<float>>;\n"
        "DEFINE FIELD metadata ON note TYPE array;\n"
        "DEFINE FIELD metadata[*] ON note TYPE object;\n"
        "DEFINE FIELD metadata[*].name ON note TYPE string;\n"
    )


def test_backup_and_restore_round_trip_data_and_manifest(
    tmp_path: Path, database_config: DatabaseConfig
):
    data_dir = tmp_path / "source-data"
    data_dir.mkdir()
    (data_dir / "uploads").mkdir()
    (data_dir / "uploads" / "brief.md").write_text("Harborlight", encoding="utf-8")
    output = tmp_path / "backup.tar.gz"

    def fake_export(_binary: Path, _config: DatabaseConfig, destination: Path):
        destination.write_text("DEFINE TABLE notebook;\n", encoding="utf-8")

    imported: list[str] = []

    def fake_import(_binary: Path, _config: DatabaseConfig, source: Path):
        imported.append(source.read_text(encoding="utf-8"))

    with patch("scripts.backup_restore._run_export", side_effect=fake_export):
        create_backup(
            output,
            data_dir=data_dir,
            binary=Path("/usr/bin/surreal"),
            config=database_config,
        )

    assert output.stat().st_mode & 0o777 == 0o600
    with tarfile.open(output, "r:gz") as archive:
        manifest_file = archive.extractfile(f"{ARCHIVE_ROOT}/manifest.json")
        assert manifest_file is not None
        manifest = json.load(manifest_file)
    assert manifest["format_version"] == 1
    assert "database.surql" in manifest["checksums"]
    assert "data/uploads/brief.md" in manifest["checksums"]

    restored_data = tmp_path / "restored" / "data"
    with patch("scripts.backup_restore._run_import", side_effect=fake_import):
        preserved = restore_backup(
            output,
            data_dir=restored_data,
            binary=Path("/usr/bin/surreal"),
            config=database_config,
            confirmed=True,
            overwrite_data=False,
        )

    assert preserved is None
    assert imported == ["DEFINE TABLE notebook;\n"]
    assert (restored_data / "uploads" / "brief.md").read_text() == "Harborlight"


def test_restore_requires_confirmation(tmp_path: Path, database_config: DatabaseConfig):
    with pytest.raises(ValueError, match="confirm-restore"):
        restore_backup(
            tmp_path / "missing.tar.gz",
            data_dir=tmp_path / "safe" / "data",
            binary=Path("/usr/bin/surreal"),
            config=database_config,
            confirmed=False,
            overwrite_data=False,
        )


def test_restore_preserves_existing_data_when_overwrite_is_explicit(
    tmp_path: Path, database_config: DatabaseConfig
):
    source_data = tmp_path / "source" / "data"
    source_data.mkdir(parents=True)
    (source_data / "new.txt").write_text("new", encoding="utf-8")
    archive = tmp_path / "backup.tar.gz"
    target = tmp_path / "target" / "data"
    target.mkdir(parents=True)
    (target / "old.txt").write_text("old", encoding="utf-8")

    with patch(
        "scripts.backup_restore._run_export",
        side_effect=lambda _b, _c, destination: destination.write_text(
            "RETURN 1;\n", encoding="utf-8"
        ),
    ):
        create_backup(
            archive,
            data_dir=source_data,
            binary=Path("/usr/bin/surreal"),
            config=database_config,
        )

    with patch("scripts.backup_restore._run_import"):
        preserved = restore_backup(
            archive,
            data_dir=target,
            binary=Path("/usr/bin/surreal"),
            config=database_config,
            confirmed=True,
            overwrite_data=True,
        )

    assert preserved is not None
    assert (preserved / "old.txt").read_text() == "old"
    assert (target / "new.txt").read_text() == "new"


def test_safe_extract_rejects_path_traversal(tmp_path: Path):
    malicious = tmp_path / "malicious.tar.gz"
    with tarfile.open(malicious, "w:gz") as archive:
        payload = b"escape"
        member = tarfile.TarInfo(f"{ARCHIVE_ROOT}/../../escape.txt")
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))

    with tarfile.open(malicious, "r:gz") as archive:
        with pytest.raises(ValueError, match="Unsafe backup archive member"):
            _safe_extract(archive, tmp_path / "extract")
