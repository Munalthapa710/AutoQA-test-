import unittest

from autoqa_shared.generated_tests import GeneratedTestExporter


class GeneratedTestExporterTests(unittest.TestCase):
    def test_escapes_names_and_urls_and_checks_loaded_body(self) -> None:
        result = GeneratedTestExporter().build("run", "https://example.com/a'b", "user's flow\nnext", [])
        self.assertIn("test('user\\'s flow\\nnext'", result.content)
        self.assertIn("page.goto('https://example.com/a\\'b')", result.content)
        self.assertIn("expect(page.locator('body')).toBeVisible()", result.content)
        self.assertNotIn("toHaveURL(/.*/)", result.content)
