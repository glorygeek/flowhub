from collections.abc import Generator
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        kwargs: dict = {"future": True}
        if settings.database_url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_engine(settings.database_url, **kwargs)
    return _engine


def get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=get_engine(),
            expire_on_commit=False,
        )
    return _session_factory


def reset_database_state() -> None:
    global _engine
    global _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


def get_db() -> Generator[Session, None, None]:
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=get_engine())


def migrate_db() -> None:
    engine = get_engine()
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    config = _build_alembic_config()
    if not table_names:
        command.upgrade(config, "head")
        return

    if "alembic_version" not in table_names:
        init_db()
        _ensure_legacy_skill_sync_columns(engine)
        command.stamp(config, "head")
        return

    command.upgrade(config, "head")


def _build_alembic_config() -> Config:
    settings = get_settings()
    backend_root = Path(__file__).resolve().parents[2]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    config.set_main_option("script_location", str((backend_root / "migrations").resolve()))
    return config


def _ensure_legacy_skill_sync_columns(engine) -> None:
    inspector = inspect(engine)
    if "skills" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("skills")}
    statements = {
        "display_name": "ALTER TABLE skills ADD COLUMN display_name VARCHAR(120) NOT NULL DEFAULT ''",
        "source": "ALTER TABLE skills ADD COLUMN source VARCHAR(32) NOT NULL DEFAULT 'manual'",
        "source_slug": "ALTER TABLE skills ADD COLUMN source_slug VARCHAR(160)",
        "source_url": "ALTER TABLE skills ADD COLUMN source_url VARCHAR(500)",
        "owner_handle": "ALTER TABLE skills ADD COLUMN owner_handle VARCHAR(120)",
        "stats": "ALTER TABLE skills ADD COLUMN stats JSON NOT NULL DEFAULT '{}'",
        "metadata": "ALTER TABLE skills ADD COLUMN metadata JSON NOT NULL DEFAULT '{}'",
        "source_payload": "ALTER TABLE skills ADD COLUMN source_payload JSON NOT NULL DEFAULT '{}'",
        "last_synced_at": "ALTER TABLE skills ADD COLUMN last_synced_at DATETIME",
    }

    with engine.begin() as connection:
        for column_name, statement in statements.items():
            if column_name not in existing_columns:
                connection.execute(text(statement))

        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_skills_source ON skills (source)"))
        connection.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS ix_skills_source_slug ON skills (source_slug)")
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_skills_owner_handle ON skills (owner_handle)")
        )
