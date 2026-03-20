import importlib
import os
import shutil
import sqlite3
import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


MODULES_TO_RESET = [
    "app",
    "app.main",
    "app.dependencies",
    "app.api",
    "app.api.routes",
    "app.api.routes.configs",
    "app.api.routes.generated_tests",
    "app.api.routes.health",
    "app.api.routes.runs",
    "autoqa_shared",
    "autoqa_shared.db",
    "autoqa_shared.models",
    "autoqa_shared.queue",
    "autoqa_shared.settings",
]


class RunControlsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_env = os.environ.copy()
        self._engines_to_dispose = []
        self._clients_to_close = []
        self._temp_dir = Path.cwd() / ".runtime" / "test-temp" / self._testMethodName
        shutil.rmtree(self._temp_dir, ignore_errors=True)
        self._temp_dir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(shutil.rmtree, self._temp_dir, True)

    def tearDown(self) -> None:
        for client in self._clients_to_close:
            client.close()
        for engine in self._engines_to_dispose:
            engine.dispose()
        os.environ.clear()
        os.environ.update(self._original_env)
        self._reset_modules()

    def test_pause_resume_stop_and_delete_run(self) -> None:
        client, db_module, models_module = self._load_app()
        config_id = self._create_config(client)
        run_id = client.post("/runs", json={"config_id": config_id}).json()["id"]

        self._set_run_state(db_module, models_module, run_id, status="running")
        paused = client.post(f"/runs/{run_id}/pause")
        self.assertEqual(paused.status_code, 200)
        self.assertEqual(paused.json()["status"], "running")
        self.assertEqual(paused.json()["control_state"], "pause_requested")

        self._set_run_state(db_module, models_module, run_id, status="running", control_state="paused")
        resumed = client.post(f"/runs/{run_id}/resume")
        self.assertEqual(resumed.status_code, 200)
        self.assertEqual(resumed.json()["status"], "running")
        self.assertIsNone(resumed.json()["control_state"])

        stopped = client.post(f"/runs/{run_id}/stop")
        self.assertEqual(stopped.status_code, 200)
        self.assertEqual(stopped.json()["status"], "running")
        self.assertEqual(stopped.json()["control_state"], "stop_requested")

        self._set_run_state(
            db_module,
            models_module,
            run_id,
            status="stopped",
            error_message="Run stopped by user.",
        )
        deleted = client.delete(f"/runs/{run_id}")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(client.get(f"/runs/{run_id}").status_code, 404)

    def test_stop_queued_run_marks_it_stopped_immediately(self) -> None:
        client, _, _ = self._load_app()
        config_id = self._create_config(client)
        run_id = client.post("/runs", json={"config_id": config_id}).json()["id"]

        stopped = client.post(f"/runs/{run_id}/stop")
        self.assertEqual(stopped.status_code, 200)
        self.assertEqual(stopped.json()["status"], "stopped")
        self.assertIsNone(stopped.json()["control_state"])

    def test_clear_history_keeps_controlled_active_runs(self) -> None:
        client, db_module, models_module = self._load_app()
        config_id = self._create_config(client)

        completed_run_id = client.post("/runs", json={"config_id": config_id}).json()["id"]
        stopped_run_id = client.post("/runs", json={"config_id": config_id}).json()["id"]
        paused_run_id = client.post("/runs", json={"config_id": config_id}).json()["id"]
        stopping_run_id = client.post("/runs", json={"config_id": config_id}).json()["id"]

        self._set_run_state(db_module, models_module, completed_run_id, status="completed")
        self._set_run_state(db_module, models_module, stopped_run_id, status="stopped")
        self._set_run_state(db_module, models_module, paused_run_id, status="running", control_state="paused")
        self._set_run_state(db_module, models_module, stopping_run_id, status="running", control_state="stop_requested")

        cleared = client.delete("/runs/history")
        self.assertEqual(cleared.status_code, 200)
        self.assertEqual(cleared.json()["deleted_runs"], 2)

        remaining_runs = client.get("/runs").json()
        self.assertEqual({run["id"] for run in remaining_runs}, {paused_run_id, stopping_run_id})

    def test_sqlite_compat_migration_adds_control_state_column(self) -> None:
        runtime_root = self._temp_dir / "runtime-compat"
        database_path = runtime_root / "compat.db"
        runtime_root.mkdir(parents=True, exist_ok=True)

        connection = sqlite3.connect(database_path)
        try:
            connection.executescript(
                """
                CREATE TABLE test_runs (
                    id TEXT PRIMARY KEY,
                    config_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    max_steps INTEGER NOT NULL,
                    safe_mode INTEGER NOT NULL,
                    started_at TEXT,
                    ended_at TEXT,
                    run_settings TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                INSERT INTO test_runs (
                    id, config_id, status, max_steps, safe_mode, started_at, ended_at,
                    run_settings, summary, error_message, created_at, updated_at
                ) VALUES (
                    'legacy-run', 'legacy-config', 'paused', 5, 1, NULL, NULL,
                    '{}', '{}', NULL, '2026-03-19T00:00:00Z', '2026-03-19T00:00:00Z'
                );
                """
            )
            connection.commit()
        finally:
            connection.close()

        self._configure_env(
            database_url=f"sqlite:///{database_path.as_posix()}",
            runtime_root=runtime_root,
        )
        self._reset_modules()
        db_module = importlib.import_module("autoqa_shared.db")
        models_module = importlib.import_module("autoqa_shared.models")
        self._engines_to_dispose.append(db_module.engine)

        session = db_module.SessionLocal()
        try:
            run = session.get(models_module.TestRun, "legacy-run")
            self.assertIsNotNone(run)
            assert run is not None
            self.assertEqual(run.status, "running")
            self.assertEqual(run.control_state, "paused")
        finally:
            session.close()

    def _create_config(self, client: TestClient) -> str:
        response = client.post(
            "/configs",
            json={
                "name": "API control test",
                "target_url": "https://example.com",
                "headless": True,
                "safe_mode": True,
                "max_steps": 5,
                "allowed_domains": [],
            },
        )
        self.assertEqual(response.status_code, 201)
        return response.json()["id"]

    def _set_run_state(
        self,
        db_module,
        models_module,
        run_id: str,
        *,
        status: str,
        control_state: str | None = None,
        error_message: str | None = None,
    ) -> None:
        session = db_module.SessionLocal()
        try:
            run = session.get(models_module.TestRun, run_id)
            assert run is not None
            run.status = status
            run.control_state = control_state
            run.error_message = error_message
            session.commit()
        finally:
            session.close()

    def _configure_env(
        self,
        *,
        database_url: str | None = None,
        runtime_root: Path | None = None,
    ) -> None:
        runtime_root = runtime_root or (self._temp_dir / "runtime")
        database_path = runtime_root / "api-controls.db"
        os.environ.clear()
        os.environ.update(self._original_env)
        os.environ.update(
            {
                "DATABASE_URL": database_url or f"sqlite:///{database_path.as_posix()}",
                "REDIS_URL": "redis://127.0.0.1:63999/0",
                "RUNTIME_ROOT": str(runtime_root),
                "ARTIFACTS_ROOT": str(self._temp_dir / "artifacts"),
                "GENERATED_TESTS_ROOT": str(self._temp_dir / "generated-tests"),
            }
        )

    def _load_app(self):
        self._configure_env()
        self._reset_modules()
        app_module = importlib.import_module("app.main")
        db_module = importlib.import_module("autoqa_shared.db")
        models_module = importlib.import_module("autoqa_shared.models")
        client = TestClient(app_module.app)
        self._clients_to_close.append(client)
        self._engines_to_dispose.append(db_module.engine)
        return client, db_module, models_module

    def _reset_modules(self) -> None:
        for module_name in MODULES_TO_RESET:
            sys.modules.pop(module_name, None)


if __name__ == "__main__":
    unittest.main()
