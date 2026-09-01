import pytest

from open_notebook.exceptions import ConfigurationError
from open_notebook.utils.security_config import validate_production_security


def secure_environment() -> dict[str, str]:
    return {
        "OPEN_NOTEBOOK_REQUIRE_SECURITY": "true",
        "OPEN_NOTEBOOK_ENCRYPTION_KEY": "e" * 32,
        "OPEN_NOTEBOOK_PASSWORD": "correct-horse-battery-staple",
        "SURREAL_PASSWORD": "database-password-strong",
        "CORS_ORIGINS": "https://notebook.example.com",
    }


def test_security_validation_is_opt_in_for_local_development():
    validate_production_security({})


def test_secure_production_environment_passes():
    validate_production_security(secure_environment())


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        (
            "OPEN_NOTEBOOK_ENCRYPTION_KEY",
            "change-me-to-a-secret-string",
            "OPEN_NOTEBOOK_ENCRYPTION_KEY",
        ),
        ("OPEN_NOTEBOOK_PASSWORD", "secret", "OPEN_NOTEBOOK_PASSWORD"),
        ("SURREAL_PASSWORD", "root", "SURREAL_PASSWORD"),
        ("CORS_ORIGINS", "*", "CORS_ORIGINS"),
        ("CORS_ORIGINS", "", "CORS_ORIGINS"),
    ],
)
def test_insecure_production_setting_fails_without_leaking_value(
    key: str, value: str, expected: str
):
    environment = secure_environment()
    environment[key] = value

    with pytest.raises(ConfigurationError) as exc_info:
        validate_production_security(environment)

    assert expected in str(exc_info.value)
    if key != "CORS_ORIGINS":
        assert value not in str(exc_info.value)


def test_validation_reports_every_unsafe_setting_at_once():
    with pytest.raises(ConfigurationError) as exc_info:
        validate_production_security({"OPEN_NOTEBOOK_REQUIRE_SECURITY": "yes"})

    message = str(exc_info.value)
    assert "OPEN_NOTEBOOK_ENCRYPTION_KEY" in message
    assert "OPEN_NOTEBOOK_PASSWORD" in message
    assert "SURREAL_PASSWORD" in message
    assert "CORS_ORIGINS" in message
