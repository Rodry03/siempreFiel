"""
Fixtures compartidas para los smoke tests.

Se ejecuta a nivel de módulo (no dentro de un fixture) porque `app.main` hace
llamadas con efectos secundarios en el momento del import (auth_check contra
la API de Langfuse), y pytest importa los módulos de test antes de que
cualquier fixture llegue a correr. Si no interceptamos esto aquí, `import
app.main` intentaría una petición de red real y fallaría en CI sin
credenciales.
"""
import os
from unittest.mock import MagicMock

os.environ.setdefault("SECRET_KEY", "test-only-secret")

import langfuse  # noqa: E402

_fake_langfuse_client = MagicMock()
_fake_langfuse_client.auth_check.return_value = True
langfuse.get_client = lambda *args, **kwargs: _fake_langfuse_client

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.database import Base, get_db  # noqa: E402
import app.database as database  # noqa: E402

_test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)

# El middleware que resuelve el usuario autenticado (CurrentUserMiddleware) no
# pasa por la dependencia `get_db`: abre su propia sesión con
# `app.database.SessionLocal`. Lo sustituimos también para que, si algún test
# futuro simula una sesión de usuario, siga sin tocar Neon.
database.engine = _test_engine
database.SessionLocal = TestingSessionLocal

Base.metadata.create_all(bind=_test_engine)


def _override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client
