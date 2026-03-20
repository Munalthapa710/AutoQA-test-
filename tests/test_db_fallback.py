import importlib
import os
import shutil
import sys
import unittest
from pathlib import Path


MODULES_TO_RESET = [
    "autoqa_shared",
    "autoqa_shared.db",
    "autoqa_shared.models",
    "autoqa_shared.settings",
]


class DatabaseFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_env = os.environ.copy()
        self._engines_to_dispose = []
        self._temp_dir = Path.cwd() / ".runtime" / "test-temp" / self._testMethodName
        shutil.rmtree(self._temp_dir, ignore_errors=True)
        self._temp_dir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(shutil.rmtree, self._temp_dir, True)

    def tearDown(self) -> None:
        for engine in self._engines_to_dispose:
            engine.dispose()
        os.environ.clear()
        os.environ.update(self._original_env)
        self._reset_modules()

    def test_uses_sqlite_directly_when_configured(self) -> None:
        runtime_root = self._temp_dir / "runtime-direct"
        database_path = runtime_root / "explicit.db"

        self._configure_env(
            DATABASE_URL=f"sqlite:///{database_path.as_posix()}",
            RUNTIME_ROOT=str(runtime_root),
            ARTIFACTS_ROOT=str(self._temp_dir / "artifacts"),
            GENERATED_TESTS_ROOT=str(self._temp_dir / "generated-tests"),
        )

        db_module, models_module = self._load_modules()
        session = db_module.SessionLocal()
        try:
            config = models_module.TestConfig(
                name="Direct SQLite",
                target_url="https://example.com",
                headless=True,
                safe_mode=True,
                max_steps=5,
                allowed_domains=[],
            )
            session.add(config)
            session.commit()
        finally:
            session.close()

        self.assertEqual(str(db_module.engine.url), f"sqlite:///{database_path.as_posix()}")
        self.assertTrue(database_path.exists())

    def test_falls_back_to_sqlite_when_primary_database_is_unreachable(self) -> None:
        runtime_root = self._temp_dir / "runtime-fallback"
        fallback_path = runtime_root / "fallback.db"

        self._configure_env(
            DATABASE_URL="postgresql+psycopg://postgres:postgres@127.0.0.1:65432/autoqa?connect_timeout=1",
            DATABASE_FALLBACK_URL=f"sqlite:///{fallback_path.as_posix()}",
            RUNTIME_ROOT=str(runtime_root),
            ARTIFACTS_ROOT=str(self._temp_dir / "artifacts"),
            GENERATED_TESTS_ROOT=str(self._temp_dir / "generated-tests"),
        )

        db_module, models_module = self._load_modules()
        session = db_module.SessionLocal()
        try:
            config = models_module.TestConfig(
                name="Fallback SQLite",
                target_url="https://example.com",
                headless=True,
                safe_mode=True,
                max_steps=5,
                allowed_domains=[],
            )
            session.add(config)
            session.commit()
        finally:
            session.close()

        self.assertEqual(str(db_module.engine.url), f"sqlite:///{fallback_path.as_posix()}")
        self.assertTrue(fallback_path.exists())

    def _configure_env(self, **overrides: str) -> None:
        os.environ.clear()
        os.environ.update(self._original_env)
        os.environ.update(overrides)

    def _load_modules(self):
        self._reset_modules()
        settings_module = importlib.import_module("autoqa_shared.settings")
        db_module = importlib.import_module("autoqa_shared.db")
        models_module = importlib.import_module("autoqa_shared.models")
        settings_module.get_settings.cache_clear()
        self._engines_to_dispose.append(db_module.engine)
        return db_module, models_module

    def _reset_modules(self) -> None:
        for module_name in MODULES_TO_RESET:
            sys.modules.pop(module_name, None)


if __name__ == "__main__":
    unittest.main()
