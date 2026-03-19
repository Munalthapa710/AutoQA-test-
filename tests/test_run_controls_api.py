import importlib
import os
import shutil
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
        self._temp_dir = Path.cwd() / ".runtime" / "test-temp" / self._testMethodName
        shutil.rmtree(self._temp_dir, ignore_errors=True)
        self._temp_dir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(shutil.rmtree, self._temp_dir, True)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._original_env)
        self._reset_modules()

    def test_pause_resume_stop_and_delete_run(self) -> None:
        client, db_module, models_module = self._load_app()
        config_id = self._create_config(client)
        run_id = client.post("/runs", json={"config_id": config_id}).json()["id"]

        self._set_run_status(db_module, models_module, run_id, "running")
        paused = client.post(f"/runs/{run_id}/pause")
        self.assertEqual(paused.status_code, 200)
        self.assertEqual(paused.json()["status"], "paused")

        resumed = client.post(f"/runs/{run_id}/resume")
        self.assertEqual(resumed.status_code, 200)
        self.assertEqual(resumed.json()["status"], "running")

        stopped = client.post(f"/runs/{run_id}/stop")
        self.assertEqual(stopped.status_code, 200)
        self.assertEqual(stopped.json()["status"], "stopped")

        deleted = client.delete(f"/runs/{run_id}")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(client.get(f"/runs/{run_id}").status_code, 404)

    def test_clear_history_keeps_active_runs(self) -> None:
        client, db_module, models_module = self._load_app()
        config_id = self._create_config(client)

        completed_run_id = client.post("/runs", json={"config_id": config_id}).json()["id"]
        stopped_run_id = client.post("/runs", json={"config_id": config_id}).json()["id"]
        running_run_id = client.post("/runs", json={"config_id": config_id}).json()["id"]

        self._set_run_status(db_module, models_module, completed_run_id, "completed")
        self._set_run_status(db_module, models_module, stopped_run_id, "stopped")
        self._set_run_status(db_module, models_module, running_run_id, "running")

        cleared = client.delete("/runs/history")
        self.assertEqual(cleared.status_code, 200)
        self.assertEqual(cleared.json()["deleted_runs"], 2)

        remaining_runs = client.get("/runs").json()
        self.assertEqual(len(remaining_runs), 1)
        self.assertEqual(remaining_runs[0]["id"], running_run_id)

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

    def _set_run_status(self, db_module, models_module, run_id: str, status: str) -> None:
        session = db_module.SessionLocal()
        try:
            run = session.get(models_module.TestRun, run_id)
            assert run is not None
            run.status = status
            session.commit()
        finally:
            session.close()

    def _configure_env(self) -> None:
        runtime_root = self._temp_dir / "runtime"
        database_path = runtime_root / "api-controls.db"
        os.environ.clear()
        os.environ.update(self._original_env)
        os.environ.update(
            {
                "DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
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
        return client, db_module, models_module

    def _reset_modules(self) -> None:
        for module_name in MODULES_TO_RESET:
            sys.modules.pop(module_name, None)


if __name__ == "__main__":
    unittest.main()
