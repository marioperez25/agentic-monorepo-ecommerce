import os
from unittest import mock

import pytest
from agentic_ecommerce_shared.config import Settings
from pydantic import ValidationError


def test_required_fields_load_from_env() -> None:
    with mock.patch.dict(
        os.environ,
        {
            "DATABASE_URL": "postgresql+asyncpg://u:p@h/db",
            "JWT_SECRET_KEY": "test-secret",
        },
        clear=True,
    ):
        s = Settings(_env_file=None)
    assert s.database_url == "postgresql+asyncpg://u:p@h/db"
    assert s.jwt_secret_key.get_secret_value() == "test-secret"
    assert s.jwt_algorithm == "HS256"
    assert s.jwt_access_token_expire_minutes == 60


def test_jwt_secret_is_not_leaked_in_repr() -> None:
    with mock.patch.dict(
        os.environ,
        {
            "DATABASE_URL": "postgresql+asyncpg://u:p@h/db",
            "JWT_SECRET_KEY": "super-secret-value",
        },
        clear=True,
    ):
        s = Settings(_env_file=None)
    assert "super-secret-value" not in repr(s)


def test_missing_required_field_raises() -> None:
    with mock.patch.dict(os.environ, {"DATABASE_URL": "postgresql+asyncpg://u:p@h/db"}, clear=True):
        with pytest.raises(ValidationError):
            Settings(_env_file=None)
