from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from playwright.async_api import BrowserContext, Page, TimeoutError as PlaywrightTimeoutError, expect

from .artifact_storage import ArtifactStorage
from .enums import RiskLevel

SAFE_KEYWORDS = {
    "search",
    "filter",
    "apply",
    "view",
    "details",
    "open",
    "dashboard",
    "home",
    "refresh",
    "retry",
    "settings",
    "profile",
    "menu",
    "sort",
}
RISKY_KEYWORDS = {
    "save",
    "submit",
    "create",
    "add",
    "new",
    "edit",
    "update",
    "login",
    "sign in",
    "sign-in",
    "register",
    "invite",
}
DESTRUCTIVE_KEYWORDS = {
    "delete",
    "remove",
    "destroy",
    "purge",
    "reset",
    "payment",
    "charge",
    "purchase",
    "buy",
    "refund",
    "deactivate",
    "terminate",
}


def normalize_text(value: str | None) -> str:
    return " ".join((value or "").split()).strip()


def classify_risk(label: str, href: str | None = None) -> str:
    source = f"{normalize_text(label)} {href or ''}".lower()
    if any(keyword in source for keyword in DESTRUCTIVE_KEYWORDS):
        return RiskLevel.DESTRUCTIVE.value
    if any(keyword in source for keyword in RISKY_KEYWORDS):
        return RiskLevel.RISKY.value
    return RiskLevel.SAFE.value


def infer_category(label: str, href: str | None = None) -> str:
    source = f"{normalize_text(label)} {href or ''}".lower()
    if "login" in source or "sign in" in source:
        return "login"
    if any(keyword in source for keyword in {"create", "new", "add"}):
        return "create"
    if any(keyword in source for keyword in {"edit", "update"}):
        return "edit"
    if any(keyword in source for keyword in {"search", "filter", "apply", "sort"}):
        return "filter"
    if "settings" in source:
        return "settings"
    if "logout" in source or "sign out" in source:
        return "logout"
    if any(keyword in source for keyword in {"view", "details", "open"}):
        return "view"
    return "navigation"


def build_locator(element: dict[str, Any]) -> dict[str, Any]:
    role = normalize_text(element.get("role"))
    text = normalize_text(element.get("text"))
    aria_label = normalize_text(element.get("ariaLabel"))
    label = normalize_text(element.get("label"))
    placeholder = normalize_text(element.get("placeholder"))
    tag = normalize_text(element.get("tag"))
    test_id = normalize_text(element.get("testId"))
    element_id = normalize_text(element.get("id"))
    name_attr = normalize_text(element.get("name"))

    semantic_role = None
    if role in {"button", "link", "textbox", "checkbox", "combobox", "tab", "menuitem", "radio"}:
        semantic_role = role
    elif tag == "button":
        semantic_role = "button"
    elif tag == "a":
        semantic_role = "link"
    elif tag in {"textarea"}:
        semantic_role = "textbox"
    elif tag == "select":
        semantic_role = "combobox"
    elif tag == "input":
        input_type = normalize_text(element.get("inputType")).lower()
        if input_type in {"checkbox"}:
            semantic_role = "checkbox"
        elif input_type in {"radio"}:
            semantic_role = "radio"
        else:
            semantic_role = "textbox"

    if semantic_role and (text or aria_label or label):
        return {
            "strategy": "role",
            "role": semantic_role,
            "name": text or aria_label or label,
        }
    if label:
        return {"strategy": "label", "label": label}
    if placeholder:
        return {"strategy": "placeholder", "placeholder": placeholder}
    if text:
        return {"strategy": "text", "text": text}
    if test_id:
        return {"strategy": "css", "selector": f"[data-testid='{test_id}']"}
    if element_id:
        return {"strategy": "css", "selector": f"#{element_id}"}
    if name_attr:
        return {"strategy": "css", "selector": f"[name='{name_attr}']"}
    if tag:
        return {"strategy": "css", "selector": tag}
    return {"strategy": "css", "selector": "*"}


class PlaywrightTools:
    def __init__(self, page: Page, context: BrowserContext, storage: ArtifactStorage, run_id: str) -> None:
        self.page = page
        self.context = context
        self.storage = storage
        self.run_id = run_id
        self.console_errors: list[dict[str, Any]] = []
        self.network_failures: list[dict[str, Any]] = []
        self._network_failure_keys: set[str] = set()
        self._trace_active = False

        page.on("console", self._handle_console)
        page.on("pageerror", self._handle_page_error)
        page.on("requestfailed", self._handle_request_failed)
        page.on("response", self._handle_response)

    async def start_tracing(self) -> None:
        if not self._trace_active:
            await self.context.tracing.start(screenshots=True, snapshots=True, sources=True)
            self._trace_active = True

    async def open_page(self, url: str) -> dict[str, Any]:
        response = await self.page.goto(url, wait_until="domcontentloaded")
        try:
            await self.page.wait_for_load_state("networkidle", timeout=5_000)
        except PlaywrightTimeoutError:
            pass
        return {
            "status_code": response.status if response else None,
            "url": self.page.url,
            "title": await self.page.title(),
        }

    async def get_page_state(self) -> dict[str, Any]:
        snapshot = await self.page.evaluate(
            """
            () => {
              const visible = (element) => {
                const rect = element.getBoundingClientRect();
                const style = window.getComputedStyle(element);
                return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
              };
              const bodyText = Array.from(document.querySelectorAll('main, [role="main"], body'))
                .find((element) => visible(element))?.innerText ?? '';
              return {
                title: document.title,
                url: window.location.href,
                headings: Array.from(document.querySelectorAll('h1, h2, h3'))
                  .map((node) => node.textContent?.trim())
                  .filter(Boolean)
                  .slice(0, 8),
                forms: document.querySelectorAll('form').length,
                tables: document.querySelectorAll('table').length,
                modals: document.querySelectorAll('[role="dialog"], dialog').length,
                visibleText: bodyText.slice(0, 1200),
              };
            }
            """
        )
        return dict(snapshot)

    async def list_interactive_elements(self) -> list[dict[str, Any]]:
        elements = await self.page.evaluate(
            """
            () => {
              const visible = (element) => {
                const rect = element.getBoundingClientRect();
                const style = window.getComputedStyle(element);
                return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
              };

              const getLabel = (element) => {
                const elementId = element.getAttribute('id');
                if (elementId) {
                  const external = document.querySelector(`label[for="${elementId}"]`);
                  if (external?.textContent?.trim()) return external.textContent.trim();
                }
                if (element.closest('label')?.textContent?.trim()) {
                  return element.closest('label').textContent.trim();
                }
                return '';
              };

              const isRequired = (element) =>
                element.hasAttribute('required') || element.getAttribute('aria-required') === 'true';

              const isFillableField = (element) => {
                const tag = element.tagName.toLowerCase();
                const type = (element.getAttribute('type') || '').toLowerCase();
                if (tag === 'textarea' || tag === 'select') {
                  return true;
                }
                if (tag !== 'input') {
                  return false;
                }
                return !['hidden', 'button', 'submit', 'reset', 'file'].includes(type);
              };

              const isEmptyField = (element) => {
                const tag = element.tagName.toLowerCase();
                const type = (element.getAttribute('type') || '').toLowerCase();
                if (tag === 'select') {
                  return !(element.value || '').trim();
                }
                if (type === 'checkbox' || type === 'radio') {
                  return !element.checked;
                }
                return !(element.value || '').trim();
              };

              const getActionContainer = (element) => {
                const nativeForm = element.form || element.closest('form');
                if (nativeForm) {
                  return nativeForm;
                }

                const modalSurface = element.closest('[role="dialog"], dialog, [aria-modal="true"], [data-testid*="modal"], [data-testid*="drawer"], .modal, .drawer');
                if (modalSurface) {
                  return modalSurface;
                }

                let current = element.parentElement;
                let depth = 0;
                while (current && depth < 6) {
                  if (!visible(current)) {
                    current = current.parentElement;
                    depth += 1;
                    continue;
                  }

                  const controls = Array.from(current.querySelectorAll('input, select, textarea')).filter((control) => visible(control) && !control.disabled);
                  const submits = Array.from(current.querySelectorAll("button, input[type='submit'], button[type='submit']")).filter((control) => visible(control) && !control.disabled);
                  if (controls.length >= 2 && submits.length >= 1) {
                    return current;
                  }

                  current = current.parentElement;
                  depth += 1;
                }

                return null;
              };

              const isSubmitControl = (element) => {
                const tag = element.tagName.toLowerCase();
                const type = (element.getAttribute('type') || '').toLowerCase();
                if (tag === 'input') {
                  return type === 'submit';
                }
                if (tag === 'button') {
                  return type === 'submit' || (!type && !!element.form);
                }
                return false;
              };

              return Array.from(document.querySelectorAll('button, a[href], input, select, textarea, [role="button"], [role="link"], [role="tab"], [role="menuitem"]'))
                .filter((element) => visible(element))
                .slice(0, 320)
                .map((element, index) => {
                  const text = element.innerText || element.textContent || '';
                  const label = getLabel(element);
                  const container = getActionContainer(element);
                  const isNativeForm = !!container && container.tagName.toLowerCase() === 'form';
                  const selectOptions = element.tagName.toLowerCase() === 'select'
                    ? Array.from(element.options).map((option) => ({ label: option.label, value: option.value })).slice(0, 10)
                    : [];
                  const formFields = container
                    ? Array.from(container.querySelectorAll('input, select, textarea')).filter((control) => visible(control) && !control.disabled)
                    : [];
                  const fillableFields = formFields.filter((control) => isFillableField(control));
                  const formText = container ? (container.innerText || container.textContent || '').trim() : '';
                  const primaryFormText = formText.split('\\n').map((entry) => entry.trim()).find(Boolean) || '';
                  const formLabel = container
                    ? (
                        container.getAttribute('aria-label')
                        || container.getAttribute('name')
                        || container.getAttribute('id')
                        || primaryFormText
                        || (isNativeForm ? 'form' : 'panel form')
                      )
                    : '';
                  const formSignature = container
                    ? [
                        container.tagName.toLowerCase(),
                        container.getAttribute('id') || '',
                        container.getAttribute('name') || '',
                        isNativeForm ? (container.getAttribute('action') || '') : '',
                        isNativeForm ? (container.getAttribute('method') || 'get') : 'synthetic',
                        primaryFormText.slice(0, 80),
                        String(fillableFields.length),
                      ].join('|')
                    : '';

                  return {
                    index,
                    tag: element.tagName.toLowerCase(),
                    role: element.getAttribute('role') || element.tagName.toLowerCase(),
                    text: text.trim().slice(0, 120),
                    href: element.getAttribute('href') || '',
                    name: element.getAttribute('name') || '',
                    id: element.getAttribute('id') || '',
                    testId: element.getAttribute('data-testid') || '',
                    ariaLabel: element.getAttribute('aria-label') || '',
                    label: label.slice(0, 120),
                    placeholder: element.getAttribute('placeholder') || '',
                    inputType: element.getAttribute('type') || '',
                    disabled: !!element.disabled || element.getAttribute('aria-disabled') === 'true',
                    value: element.value || '',
                    checked: "checked" in element ? !!element.checked : false,
                    required: isRequired(element),
                    options: selectOptions,
                    isSubmitControl: isSubmitControl(element),
                    formSignature,
                    formLabel: formLabel.slice(0, 120),
                    formAction: isNativeForm ? (container?.getAttribute('action') || '') : '',
                    formMethod: isNativeForm ? (container?.getAttribute('method') || '') : '',
                    formFillableCount: fillableFields.length,
                    formEmptyFillableCount: fillableFields.filter((control) => isEmptyField(control)).length,
                    formRequiredCount: fillableFields.filter((control) => isRequired(control)).length,
                    formEmptyRequiredCount: fillableFields.filter((control) => isRequired(control) && isEmptyField(control)).length,
                    formFilledFillableCount: fillableFields.filter((control) => !isEmptyField(control)).length,
                  };
                });
            }
            """
        )

        enriched: list[dict[str, Any]] = []
        for element in elements:
            display_label = normalize_text(
                element.get("text")
                or element.get("ariaLabel")
                or element.get("label")
                or element.get("placeholder")
                or element.get("name")
                or element.get("id")
            )
            element["displayLabel"] = display_label or element.get("tag") or "element"
            element["risk"] = classify_risk(display_label, element.get("href"))
            element["category"] = infer_category(display_label, element.get("href"))
            element["locator"] = build_locator(element)
            element["signature"] = self.signature_for(element)
            enriched.append(element)
        return enriched

    async def click_element(self, element: dict[str, Any]) -> dict[str, Any]:
        locator = self._resolve_locator(element.get("locator", {}))
        await locator.first.click(timeout=6_000)
        try:
            await self.page.wait_for_load_state("networkidle", timeout=4_000)
        except PlaywrightTimeoutError:
            pass
        return {"url": self.page.url, "title": await self.page.title()}

    async def type_text(self, element: dict[str, Any], value: str) -> dict[str, Any]:
        locator = self._resolve_locator(element.get("locator", {}))
        await locator.first.fill(value, timeout=6_000)
        return {"value": value, "url": self.page.url, "title": await self.page.title()}

    async def select_option(self, element: dict[str, Any], option_label: str) -> dict[str, Any]:
        locator = self._resolve_locator(element.get("locator", {}))
        await locator.first.select_option(label=option_label, timeout=6_000)
        return {"value": option_label, "url": self.page.url, "title": await self.page.title()}

    async def press_key(self, key: str) -> dict[str, Any]:
        await self.page.keyboard.press(key)
        return {"key": key, "url": self.page.url, "title": await self.page.title()}

    async def assert_text(self, text: str) -> dict[str, Any]:
        await expect(self.page.get_by_text(text, exact=False).first).to_be_visible(timeout=4_000)
        return {"asserted_text": text, "url": self.page.url}

    async def assert_url(self, fragment: str) -> dict[str, Any]:
        current_url = self.page.url
        if fragment not in current_url:
            raise AssertionError(f"Expected URL to contain '{fragment}', got '{current_url}'")
        return {"asserted_url_fragment": fragment, "url": current_url}

    async def capture_screenshot(self, step_index: int, label: str) -> str:
        relative_path, absolute_path = self.storage.reserve_screenshot_path(self.run_id, step_index, label)
        await self.page.screenshot(path=str(absolute_path), full_page=True)
        return relative_path

    def get_console_errors(self) -> list[dict[str, Any]]:
        return list(self.console_errors)

    def get_network_failures(self) -> list[dict[str, Any]]:
        return list(self.network_failures)

    async def inspect_form_feedback(self) -> dict[str, Any]:
        feedback = await self.page.evaluate(
            """
            () => {
              const visible = (element) => {
                const rect = element.getBoundingClientRect();
                const style = window.getComputedStyle(element);
                return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
              };

              const getLabel = (element) => {
                const elementId = element.getAttribute('id');
                if (elementId) {
                  const external = document.querySelector(`label[for="${elementId}"]`);
                  if (external?.textContent?.trim()) return external.textContent.trim();
                }
                if (element.closest('label')?.textContent?.trim()) {
                  return element.closest('label').textContent.trim();
                }
                return element.getAttribute('aria-label') || element.getAttribute('placeholder') || element.getAttribute('name') || '';
              };

              const invalidFields = Array.from(document.querySelectorAll('input, select, textarea'))
                .filter((element) => visible(element) && !element.disabled && (element.matches(':invalid') || element.getAttribute('aria-invalid') === 'true'))
                .slice(0, 8)
                .map((element) => ({
                  label: getLabel(element).slice(0, 120),
                  type: element.getAttribute('type') || element.tagName.toLowerCase(),
                  message: (element.validationMessage || '').slice(0, 200),
                }));

              const errorSelectors = ['[role="alert"]', '[aria-live="assertive"]', '.error', '.errors', '.field-error', '.invalid-feedback', '.alert-danger'];
              const errorMessages = Array.from(document.querySelectorAll(errorSelectors.join(',')))
                .filter((element) => visible(element))
                .map((element) => (element.innerText || element.textContent || '').trim())
                .filter(Boolean)
                .slice(0, 8);

              const successSelectors = ['[role="status"]', '[aria-live="polite"]', '.alert-success', '.success', '.toast-success'];
              const successMessages = Array.from(document.querySelectorAll(successSelectors.join(',')))
                .filter((element) => visible(element))
                .map((element) => (element.innerText || element.textContent || '').trim())
                .filter(Boolean)
                .slice(0, 6);

              return {
                invalidFieldCount: invalidFields.length,
                invalidFields,
                errorMessages,
                successMessages,
              };
            }
            """
        )
        return dict(feedback)

    async def run_accessibility_scan(self) -> list[dict[str, Any]]:
        findings = await self.page.evaluate(
            """
            () => {
              const issues = [];

              Array.from(document.querySelectorAll('img')).forEach((element) => {
                if (!element.getAttribute('alt')) {
                  issues.push({ rule: 'image-alt', severity: 'medium', target: element.outerHTML.slice(0, 140), message: 'Image is missing alt text.' });
                }
              });

              Array.from(document.querySelectorAll('button, [role="button"], a[href]')).forEach((element) => {
                const name = element.getAttribute('aria-label') || element.textContent || '';
                if (!name.trim()) {
                  issues.push({ rule: 'interactive-name', severity: 'high', target: element.outerHTML.slice(0, 140), message: 'Interactive element has no accessible name.' });
                }
              });

              Array.from(document.querySelectorAll('input, select, textarea')).forEach((element) => {
                const id = element.getAttribute('id');
                const label = id ? document.querySelector(`label[for="${id}"]`) : element.closest('label');
                const named = element.getAttribute('aria-label') || element.getAttribute('placeholder') || label?.textContent || '';
                const type = element.getAttribute('type') || '';
                if (!named.trim() && type !== 'hidden') {
                  issues.push({ rule: 'form-label', severity: 'high', target: element.outerHTML.slice(0, 140), message: 'Form field is missing a label or aria-label.' });
                }
              });

              return issues.slice(0, 20);
            }
            """
        )
        return list(findings)

    async def save_trace(self, label: str = "trace") -> str | None:
        if not self._trace_active:
            return None
        relative_path, absolute_path = self.storage.reserve_trace_path(self.run_id, label)
        await self.context.tracing.stop(path=str(absolute_path))
        self._trace_active = False
        return relative_path

    def signature_for(self, element: dict[str, Any]) -> str:
        url = urlparse(self.page.url)
        path = url.path or "/"
        return f"{path}|{element.get('tag')}|{element.get('displayLabel')}|{element.get('href')}|{element.get('name')}"

    def _resolve_locator(self, locator: dict[str, Any]):
        strategy = locator.get("strategy")
        if strategy == "role":
            return self.page.get_by_role(locator["role"], name=locator.get("name"), exact=False)
        if strategy == "label":
            return self.page.get_by_label(locator["label"], exact=False)
        if strategy == "placeholder":
            return self.page.get_by_placeholder(locator["placeholder"], exact=False)
        if strategy == "text":
            return self.page.get_by_text(locator["text"], exact=False)
        if strategy == "css":
            return self.page.locator(locator.get("selector", "*"))
        return self.page.locator("*")

    def _handle_console(self, message) -> None:
        if message.type == "error":
            self.console_errors.append(
                {
                    "type": message.type,
                    "text": message.text,
                    "url": self.page.url,
                }
            )

    def _handle_page_error(self, error: Exception) -> None:
        self.console_errors.append({"type": "pageerror", "text": str(error), "url": self.page.url})

    def _handle_request_failed(self, request) -> None:
        failure = request.failure
        if isinstance(failure, str):
            error_text = failure
        elif failure is None:
            error_text = "unknown"
        else:
            error_text = getattr(failure, "error_text", str(failure))
        resource_type = getattr(request, "resource_type", None)
        if self._should_ignore_network_failure(
            url=request.url,
            method=request.method,
            error_text=error_text,
            status=None,
            resource_type=resource_type,
        ):
            return
        self._record_network_failure(
            {
                "url": request.url,
                "method": request.method,
                "error_text": error_text,
                "resource_type": resource_type,
            }
        )

    def _handle_response(self, response) -> None:
        if response.status >= 400:
            request = response.request
            resource_type = getattr(request, "resource_type", None)
            if self._should_ignore_network_failure(
                url=response.url,
                method=request.method,
                error_text=f"HTTP {response.status}",
                status=response.status,
                resource_type=resource_type,
            ):
                return
            self._record_network_failure(
                {
                    "url": response.url,
                    "method": request.method,
                    "status": response.status,
                    "error_text": f"HTTP {response.status}",
                    "resource_type": resource_type,
                }
            )

    def _record_network_failure(self, payload: dict[str, Any]) -> None:
        key = "|".join(
            [
                normalize_text(str(payload.get("url") or "")),
                normalize_text(str(payload.get("method") or "")),
                normalize_text(str(payload.get("status") or "")),
                normalize_text(str(payload.get("error_text") or "")),
            ]
        )
        if key in self._network_failure_keys:
            return
        self._network_failure_keys.add(key)
        self.network_failures.append(payload)

    def _should_ignore_network_failure(
        self,
        *,
        url: str,
        method: str,
        error_text: str,
        status: int | None,
        resource_type: str | None,
    ) -> bool:
        parsed = urlparse(url)
        normalized_error = normalize_text(error_text).lower()
        normalized_method = normalize_text(method).upper()
        request_path = parsed.path or "/"
        query = parsed.query or ""

        is_framework_request = request_path.startswith("/_next/") or "_rsc=" in query or "__flight__" in query
        is_aborted_navigation_noise = normalized_method == "GET" and "err_aborted" in normalized_error
        is_prefetch_noise = resource_type in {"image", "font"} and status == 404 and request_path.startswith("/_next/")

        if is_framework_request and (is_aborted_navigation_noise or is_prefetch_noise):
            return True
        if is_framework_request and status in {404, 409}:
            return True
        return False
