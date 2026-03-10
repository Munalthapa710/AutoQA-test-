import json
import re
from pathlib import Path

from .settings import get_settings


def slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return normalized or "artifact"


class ArtifactStorage:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.root = self.settings.artifacts_root
        self.generated_tests_root = self.settings.generated_tests_root

    def ensure_run_dir(self, category: str, run_id: str) -> Path:
        path = self.root / category / run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_bytes(self, category: str, run_id: str, filename: str, content: bytes) -> str:
        target_dir = self.ensure_run_dir(category, run_id)
        file_path = target_dir / filename
        file_path.write_bytes(content)
        return str(file_path.relative_to(self.root))

    def write_text(self, category: str, run_id: str, filename: str, content: str) -> str:
        target_dir = self.ensure_run_dir(category, run_id)
        file_path = target_dir / filename
        file_path.write_text(content, encoding="utf-8")
        return str(file_path.relative_to(self.root))

    def write_json(self, category: str, run_id: str, filename: str, content: dict) -> str:
        return self.write_text(category, run_id, filename, json.dumps(content, indent=2))

    def reserve_screenshot_path(self, run_id: str, step_index: int, label: str) -> tuple[str, Path]:
        filename = f"{step_index:03d}-{slugify(label)}.png"
        target_dir = self.ensure_run_dir("screenshots", run_id)
        file_path = target_dir / filename
        return str(file_path.relative_to(self.root)), file_path

    def reserve_trace_path(self, run_id: str, label: str = "trace") -> tuple[str, Path]:
        filename = f"{slugify(label)}.zip"
        target_dir = self.ensure_run_dir("traces", run_id)
        file_path = target_dir / filename
        return str(file_path.relative_to(self.root)), file_path

    def write_generated_test(self, filename: str, content: str) -> str:
        target_dir = self.generated_tests_root
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / filename
        file_path.write_text(content, encoding="utf-8")
        return str(file_path.relative_to(self.generated_tests_root))
