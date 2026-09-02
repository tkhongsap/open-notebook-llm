from pathlib import Path

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_has_database_aware_healthcheck_and_embedded_db_opt_in():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "SURREAL_EMBEDDED=false" in dockerfile
    assert "SURREAL_EMBEDDED=true" in dockerfile
    assert "http://127.0.0.1:8502/healthz" in dockerfile
    assert "HEALTHCHECK" in dockerfile


def test_supervisor_keeps_embedded_database_disabled_by_default():
    config = (ROOT / "supervisord.surrealdb.conf").read_text(encoding="utf-8")

    assert "autostart=%(ENV_SURREAL_EMBEDDED)s" in config
    assert "SURREAL_PASS=${SURREAL_PASSWORD:-root}" in config
    assert "SURREAL_DATA_PATH:-/mydata" in config
    assert "--pass" not in config


def test_production_compose_requires_security_and_persistent_volumes():
    compose_path = ROOT / "deploy/docker/docker-compose.production.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    app = compose["services"]["open_notebook"]
    database = compose["services"]["surrealdb"]

    assert app["environment"]["OPEN_NOTEBOOK_REQUIRE_SECURITY"] == "true"
    assert app["environment"]["INTERNAL_API_URL"] == "http://127.0.0.1:5055"
    assert app["volumes"] == ["notebook_data:/app/data"]
    assert database["volumes"] == ["surreal_data:/mydata"]
    assert database["environment"]["SURREAL_PASS"] == (
        "${SURREAL_PASSWORD:?Set SURREAL_PASSWORD}"
    )
    assert "--pass" not in database["command"]
    assert "healthcheck" in app
    assert "healthcheck" in database
    assert compose["networks"]["backend"]["internal"] is True


def test_local_compose_does_not_publish_database_or_api_broadly():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))

    assert compose["services"]["surrealdb"]["ports"] == ["127.0.0.1:8000:8000"]
    assert "127.0.0.1:5055:5055" in compose["services"]["open_notebook"]["ports"]


def test_ghcr_workflows_publish_to_the_current_repository_namespace():
    for relative_path in (
        ".github/workflows/build-dev.yml",
        ".github/workflows/build-and-release.yml",
    ):
        workflow = yaml.safe_load((ROOT / relative_path).read_text(encoding="utf-8"))

        assert workflow["permissions"]["packages"] == "write"
        assert workflow["env"]["GHCR_IMAGE"] == "ghcr.io/${{ github.repository }}"
