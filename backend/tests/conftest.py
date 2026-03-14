import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def client(tmp_path_factory):
    db_dir = tmp_path_factory.mktemp("db")
    db_path = Path(db_dir) / "test_flowhub.db"

    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["FLOWHUB_API_KEY"] = "test-api-key"
    os.environ["SKILL_SEARCH_REMOTE_ENABLED"] = "false"
    os.environ["AI_ENABLED"] = "false"
    os.environ["PLANNER_AI_ENABLED"] = "false"

    from app.core.config import get_settings
    from app.core.database import get_engine, migrate_db, reset_database_state

    get_settings.cache_clear()
    reset_database_state()
    engine = get_engine()
    migrate_db()

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client

    engine.dispose()
    reset_database_state()
