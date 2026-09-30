"""Test setup: a dedicated Postgres database (ipsakti_test), migrated and seeded once per session."""
import os

import pytest
from sqlalchemy import create_engine, text

BASE = os.environ.get("TEST_DATABASE_ADMIN_URL", "postgresql+psycopg://ipsakti:ipsakti@localhost:5433/ipsakti")
TEST_DB = "ipsakti_test"
os.environ["DATABASE_URL"] = BASE.rsplit("/", 1)[0] + f"/{TEST_DB}"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["EMBEDDING_PROVIDER"] = "hashing"
os.environ["RATE_LIMIT_CHAT"] = "1000"


def _ensure_db() -> None:
    eng = create_engine(BASE, isolation_level="AUTOCOMMIT")
    with eng.connect() as c:
        if not c.execute(text("SELECT 1 FROM pg_database WHERE datname = :d"), {"d": TEST_DB}).first():
            c.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
    eng.dispose()


@pytest.fixture(scope="session", autouse=True)
def seeded_db():
    _ensure_db()
    from alembic import command
    from alembic.config import Config

    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "backend", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "backend", "alembic"))
    command.upgrade(cfg, "head")
    from app.seed.run import main as seed

    assert seed(["--reset"]) == 0
    yield


@pytest.fixture(scope="session")
def client(seeded_db):
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def login(client, email="researcher@ipsakti.demo", password="Demo@12345") -> dict:
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}


@pytest.fixture(scope="session")
def researcher(client):
    return login(client)


@pytest.fixture(scope="session")
def admin(client):
    return login(client, "admin@ipsakti.demo")


@pytest.fixture(scope="session")
def reviewer(client):
    return login(client, "reviewer@ipsakti.demo")


@pytest.fixture()
def db(seeded_db):
    from app.db import SessionLocal

    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


@pytest.fixture()
def workspace_id(db):
    from app.models.orm import Workspace

    return db.query(Workspace).filter(Workspace.name == "Demo Research Workspace").one().id
