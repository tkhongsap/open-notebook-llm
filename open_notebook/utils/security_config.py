"""Production deployment security validation.

Local development intentionally remains permissive. Hosted/container deployments
can set ``OPEN_NOTEBOOK_REQUIRE_SECURITY=true`` to turn unsafe defaults into a
startup error instead of a warning.
"""

from collections.abc import Mapping

from open_notebook.exceptions import ConfigurationError

_INSECURE_VALUES = {
    "change-me",
    "change-me-to-a-secret-string",
    "changeme",
    "password",
    "root",
    "secret",
}


def _is_true(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _is_insecure(value: str | None, *, minimum_length: int) -> bool:
    normalized = (value or "").strip()
    return len(normalized) < minimum_length or normalized.lower() in _INSECURE_VALUES


def validate_production_security(environment: Mapping[str, str]) -> None:
    """Reject unsafe production settings when strict deployment mode is enabled.

    Error messages identify the setting but never echo its value.
    """

    if not _is_true(environment.get("OPEN_NOTEBOOK_REQUIRE_SECURITY")):
        return

    problems: list[str] = []
    if _is_insecure(environment.get("OPEN_NOTEBOOK_ENCRYPTION_KEY"), minimum_length=32):
        problems.append(
            "OPEN_NOTEBOOK_ENCRYPTION_KEY must be a non-placeholder value of at least 32 characters"
        )
    if _is_insecure(environment.get("OPEN_NOTEBOOK_PASSWORD"), minimum_length=12):
        problems.append(
            "OPEN_NOTEBOOK_PASSWORD must be a non-placeholder value of at least 12 characters"
        )
    if _is_insecure(environment.get("SURREAL_PASSWORD"), minimum_length=16):
        problems.append(
            "SURREAL_PASSWORD must be a non-placeholder value of at least 16 characters"
        )

    cors_origins = [
        origin.strip()
        for origin in (environment.get("CORS_ORIGINS") or "").split(",")
        if origin.strip()
    ]
    if not cors_origins or "*" in cors_origins:
        problems.append(
            "CORS_ORIGINS must contain explicit frontend origin(s), not '*'"
        )

    if problems:
        raise ConfigurationError(
            "Production security validation failed: " + "; ".join(problems)
        )
