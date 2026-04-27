import importlib
import os
import shutil
import sys
import unittest
from pathlib import Path


MODULES_TO_RESET = [
    "autoqa_shared",
    "autoqa_shared.db",
    "autoqa_shared.explorer",
    "autoqa_shared.models",
    "autoqa_shared.settings",
]


class ExplorerSamplingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_env = os.environ.copy()
        self._engines_to_dispose = []
        self._temp_dir = Path.cwd() / ".runtime" / "test-temp" / self._testMethodName
        shutil.rmtree(self._temp_dir, ignore_errors=True)
        self._temp_dir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(shutil.rmtree, self._temp_dir, True)

        runtime_root = self._temp_dir / "runtime"
        database_path = runtime_root / "explorer-sampling.db"
        os.environ.clear()
        os.environ.update(self._original_env)
        os.environ.update(
            {
                "DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
                "RUNTIME_ROOT": str(runtime_root),
                "ARTIFACTS_ROOT": str(self._temp_dir / "artifacts"),
                "GENERATED_TESTS_ROOT": str(self._temp_dir / "generated-tests"),
            }
        )

        self._reset_modules()
        db_module = importlib.import_module("autoqa_shared.db")
        explorer_module = importlib.import_module("autoqa_shared.explorer")
        self._engines_to_dispose.append(db_module.engine)
        self.engine = explorer_module.ExplorationEngine(db=None)

    def tearDown(self) -> None:
        for engine in self._engines_to_dispose:
            engine.dispose()
        os.environ.clear()
        os.environ.update(self._original_env)
        self._reset_modules()

    def test_repeated_edit_actions_share_a_sampling_group(self) -> None:
        elements = [
            {
                "displayLabel": "Edit John",
                "tag": "button",
                "role": "button",
                "category": "edit",
                "disabled": False,
                "href": "",
                "formSignature": "",
            },
            {
                "displayLabel": "Edit Mary",
                "tag": "button",
                "role": "button",
                "category": "edit",
                "disabled": False,
                "href": "",
                "formSignature": "",
            },
        ]

        counts = self.engine._sample_group_counts("/users", elements)
        group = self.engine._sample_group_for_element("/users", elements[0], "edit")

        self.assertEqual(counts[group], 2)
        self.assertTrue(self.engine._should_skip_due_to_sampling(group, counts, {group: 1}))

    def test_repeated_submit_controls_share_a_sampling_group(self) -> None:
        pending = {
            "displayLabel": "Save Customer",
            "label": "save customer",
            "form_label": "Customer Form",
            "tag": "button",
            "role": "button",
            "category": "form",
            "disabled": False,
            "href": "",
            "isSubmitControl": True,
            "formSignature": "form|customer|post|2",
        }
        elements = [dict(pending), dict(pending)]

        counts = self.engine._sample_group_counts("/customers", elements)
        group = self.engine._sample_group_for_submit("/customers", pending)

        self.assertEqual(counts[group], 2)
        self.assertTrue(self.engine._should_skip_due_to_sampling(group, counts, {group: 1}))

    def test_scope_matching_honors_include_and_exclude_paths(self) -> None:
        from autoqa_shared.models import TestConfig

        scoped = TestConfig(
            name="Scoped CRUD",
            target_url="https://example.com/customer-credit-note",
            headless=True,
            safe_mode=True,
            max_steps=10,
            allowed_domains=[],
            include_paths=["/customer-credit-note/*"],
            exclude_paths=["/customer-credit-note/archive/*"],
            crud_mode=True,
            crud_actions=["create", "read", "update"],
            allow_destructive_actions=False,
        )

        self.assertTrue(self.engine._is_path_in_scope("/customer-credit-note/new", scoped))
        self.assertFalse(self.engine._is_path_in_scope("/customer-credit-note/archive/42", scoped))
        self.assertFalse(self.engine._is_path_in_scope("/sales-invoice/new", scoped))

    def test_crud_mode_requires_explicit_delete_opt_in(self) -> None:
        from autoqa_shared.models import TestConfig
        from autoqa_shared.enums import RiskLevel

        config = TestConfig(
            name="CRUD no delete",
            target_url="https://example.com/customers",
            headless=True,
            safe_mode=True,
            max_steps=10,
            allowed_domains=[],
            crud_mode=True,
            crud_actions=["create", "read", "update"],
            allow_destructive_actions=False,
        )
        delete_enabled = TestConfig(
            name="CRUD delete",
            target_url="https://example.com/customers",
            headless=True,
            safe_mode=False,
            max_steps=10,
            allowed_domains=[],
            crud_mode=True,
            crud_actions=["create", "read", "update", "delete"],
            allow_destructive_actions=True,
        )

        self.assertFalse(self.engine._is_category_enabled("edit", risk=RiskLevel.DESTRUCTIVE.value, config=config))
        self.assertTrue(self.engine._is_category_enabled("edit", risk=RiskLevel.DESTRUCTIVE.value, config=delete_enabled))

    def test_crud_module_paths_normalize_wildcards(self) -> None:
        from autoqa_shared.models import TestConfig

        config = TestConfig(
            name="CRUD paths",
            target_url="https://example.com/dashboard",
            headless=True,
            safe_mode=False,
            max_steps=10,
            allowed_domains=[],
            include_paths=["/vendor*", "/customer/*", "/vendor/new*"],
            crud_mode=True,
            crud_actions=["create", "read", "update", "delete"],
            allow_destructive_actions=True,
        )

        self.assertEqual(self.engine._crud_module_paths(config), ["/vendor", "/customer", "/vendor/new"])
        self.assertTrue(self.engine._use_deterministic_crud(config))

    def _reset_modules(self) -> None:
        for module_name in MODULES_TO_RESET:
            sys.modules.pop(module_name, None)


if __name__ == "__main__":
    unittest.main()
