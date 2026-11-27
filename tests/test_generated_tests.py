import unittest

from autoqa_shared.generated_tests import GeneratedTestExporter


class GeneratedTestExporterTests(unittest.TestCase):
    def test_login_export_uses_environment_variables(self) -> None:
        result = GeneratedTestExporter().build(
            "run",
            "https://example.com/login",
            "login",
            [{
                "type": "fill",
                "credential_env": "AUTOQA_TEST_PASSWORD",
                "value": "old-secret",
                "locator": {"strategy": "css", "selector": "input[type=password]"},
            }],
        )
        self.assertIn(".fill(process.env.AUTOQA_TEST_PASSWORD)", result.content)
        self.assertNotIn("old-secret", result.content)

    def test_escapes_names_and_urls_and_checks_loaded_body(self) -> None:
        result = GeneratedTestExporter().build("run", "https://example.com/a'b", "user's flow\nnext", [])
        self.assertIn("test('user\\'s flow\\nnext'", result.content)
        self.assertIn("page.goto('https://example.com/a\\'b')", result.content)
        self.assertIn("expect(page.locator('body')).toBeVisible()", result.content)
        self.assertNotIn("toHaveURL(/.*/)", result.content)
