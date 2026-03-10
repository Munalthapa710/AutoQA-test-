from dataclasses import dataclass
from typing import Any

from .artifact_storage import slugify


@dataclass
class ExportedTest:
    name: str
    file_path: str
    content: str


class GeneratedTestExporter:
    def build(self, run_name: str, base_url: str, flow_name: str, actions: list[dict[str, Any]]) -> ExportedTest:
        safe_flow_name = slugify(flow_name)
        file_name = f"{slugify(run_name)}-{safe_flow_name}.spec.ts"
        lines = [
            "import { expect, test } from '@playwright/test';",
            "",
            f"test('{flow_name}', async ({{ page }}) => {{",
            f"  await page.goto('{base_url}');",
        ]

        for action in actions:
            command = self._render_action(action)
            if command:
                lines.extend([f"  {line}" for line in command])

        lines.extend(
            [
                "  await expect(page).toHaveURL(/.*/);",
                "});",
                "",
            ]
        )
        return ExportedTest(name=flow_name, file_path=file_name, content="\n".join(lines))

    def _render_action(self, action: dict[str, Any]) -> list[str]:
        locator_expr = self._locator_expression(action.get("locator", {}))
        action_type = action.get("type")

        if action_type == "goto":
            return [f"await page.goto('{action['value']}');"]
        if action_type == "click" and locator_expr:
            return [f"await {locator_expr}.click();"]
        if action_type == "fill" and locator_expr:
            value = action.get("value", "")
            return [f"await {locator_expr}.fill('{self._escape(value)}');"]
        if action_type == "select" and locator_expr:
            value = action.get("value", "")
            return [f"await {locator_expr}.selectOption({{ label: '{self._escape(value)}' }});"]
        if action_type == "press":
            return [f"await page.keyboard.press('{self._escape(action.get('value', 'Enter'))}');"]
        if action_type == "assert_text":
            value = action.get("value", "")
            return [f"await expect(page.getByText('{self._escape(value)}', {{ exact: false }})).toBeVisible();"]
        if action_type == "assert_url":
            value = action.get("value", "")
            return [f"await expect(page).toHaveURL(/.*{self._escape_regex(value)}.*/);"]
        return []

    def _locator_expression(self, locator: dict[str, Any]) -> str | None:
        strategy = locator.get("strategy")
        if strategy == "role":
            role = locator.get("role")
            name = locator.get("name")
            if role and name:
                return f"page.getByRole('{role}', {{ name: '{self._escape(name)}', exact: false }})"
        if strategy == "label":
            label = locator.get("label")
            if label:
                return f"page.getByLabel('{self._escape(label)}', {{ exact: false }})"
        if strategy == "placeholder":
            value = locator.get("placeholder")
            if value:
                return f"page.getByPlaceholder('{self._escape(value)}', {{ exact: false }})"
        if strategy == "text":
            value = locator.get("text")
            if value:
                return f"page.getByText('{self._escape(value)}', {{ exact: false }})"
        if strategy == "css":
            selector = locator.get("selector")
            if selector:
                return f"page.locator('{self._escape(selector)}')"
        return None

    def _escape(self, value: str) -> str:
        return value.replace("\\", "\\\\").replace("'", "\\'")

    def _escape_regex(self, value: str) -> str:
        escaped = []
        for char in value:
            if char.isalnum():
                escaped.append(char)
            else:
                escaped.append(f"\\{char}")
        return "".join(escaped)
