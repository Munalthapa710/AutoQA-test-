import logging
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .settings import get_settings


logger = logging.getLogger("autoqa.db")


class Base(DeclarativeBase):
    pass


def _is_sqlite_url(url: str) -> bool:
    return url.startswith("sqlite:")


def _sqlite_engine_kwargs() -> dict:
    return {"connect_args": {"check_same_thread": False}}


def _default_fallback_database_url() -> str:
    settings = get_settings()
    fallback_path = Path(settings.runtime_root) / "autoqa-dev.db"
    return f"sqlite:///{fallback_path.as_posix()}"


def _engine_kwargs(url: str) -> dict:
    kwargs = {"pool_pre_ping": True}
    if _is_sqlite_url(url):
        kwargs.update(_sqlite_engine_kwargs())
    return kwargs


def _probe_database(engine) -> None:
    with engine.connect() as connection:
        connection.execute(text("select 1"))


def _ensure_sqlite_schema(engine) -> None:
    from . import models as _models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _apply_sqlite_compat_migrations(engine)


def _apply_sqlite_compat_migrations(engine) -> None:
    with engine.connect() as connection:
        inspector = inspect(connection)
        has_test_configs = "test_configs" in inspector.get_table_names()
        if has_test_configs:
            config_columns = {column["name"] for column in inspector.get_columns("test_configs")}
        else:
            config_columns = set()
        has_test_runs = "test_runs" in inspector.get_table_names()
        if not has_test_runs:
            run_columns = set()
        else:
            run_columns = {column["name"] for column in inspector.get_columns("test_runs")}

    with engine.begin() as connection:
        if has_test_configs and "include_paths" not in config_columns:
            connection.execute(text("ALTER TABLE test_configs ADD COLUMN include_paths JSON"))
            connection.execute(text("UPDATE test_configs SET include_paths = '[]' WHERE include_paths IS NULL"))
        if has_test_configs and "exclude_paths" not in config_columns:
            connection.execute(text("ALTER TABLE test_configs ADD COLUMN exclude_paths JSON"))
            connection.execute(text("UPDATE test_configs SET exclude_paths = '[]' WHERE exclude_paths IS NULL"))
        if has_test_configs and "crud_mode" not in config_columns:
            connection.execute(text("ALTER TABLE test_configs ADD COLUMN crud_mode BOOLEAN"))
            connection.execute(text("UPDATE test_configs SET crud_mode = 0 WHERE crud_mode IS NULL"))
        if has_test_configs and "crud_actions" not in config_columns:
            connection.execute(text("ALTER TABLE test_configs ADD COLUMN crud_actions JSON"))
            connection.execute(
                text(
                    "UPDATE test_configs "
                    "SET crud_actions = '[\"create\", \"read\", \"update\"]' "
                    "WHERE crud_actions IS NULL"
                )
            )
        if has_test_configs and "allow_destructive_actions" not in config_columns:
            connection.execute(text("ALTER TABLE test_configs ADD COLUMN allow_destructive_actions BOOLEAN"))
            connection.execute(
                text(
                    "UPDATE test_configs "
                    "SET allow_destructive_actions = 0 "
                    "WHERE allow_destructive_actions IS NULL"
                )
            )
        if has_test_runs and "control_state" not in run_columns:
            connection.execute(text("ALTER TABLE test_runs ADD COLUMN control_state VARCHAR(32)"))
            connection.execute(
                text(
                    "UPDATE test_runs "
                    "SET status = 'running', control_state = 'paused' "
                    "WHERE status = 'paused'"
                )
            )
        connection.execute(
            text(
                "UPDATE test_runs "
                "SET control_state = NULL "
                "WHERE status IN ('completed', 'failed', 'stopped')"
            )
        )


def _build_engine():
    settings = get_settings()
    primary_engine = create_engine(settings.database_url, **_engine_kwargs(settings.database_url))

    if _is_sqlite_url(settings.database_url):
        _ensure_sqlite_schema(primary_engine)
        return primary_engine

    try:
        _probe_database(primary_engine)
        return primary_engine
    except Exception as exc:
        fallback_url = settings.database_fallback_url or _default_fallback_database_url()
        logger.warning(
            "Primary database unavailable, falling back to local SQLite",
            extra={"database_url": settings.database_url, "fallback_url": fallback_url, "error": str(exc)},
        )
        fallback_engine = create_engine(fallback_url, **_engine_kwargs(fallback_url))
        _ensure_sqlite_schema(fallback_engine)
        return fallback_engine


settings = get_settings()
engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
