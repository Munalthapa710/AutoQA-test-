from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

from langgraph.graph import END, StateGraph
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright
from sqlalchemy.orm import Session

from .artifact_storage import ArtifactStorage, slugify
from .enums import ArtifactType, FailureType, RiskLevel, RunStatus, StepStatus
from .generated_tests import GeneratedTestExporter
from .models import Artifact, DiscoveredFlow, FailureReport, GeneratedTest, RunStep, TestConfig, TestRun
from .playwright_tools import PlaywrightTools, classify_risk, infer_category, normalize_text
from .settings import get_settings


GraphState = dict[str, Any]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ExplorationEngine:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()
        self.storage = ArtifactStorage()
        self.exporter = GeneratedTestExporter()

    async def run(self, run_id: str) -> None:
        run = self.db.get(TestRun, run_id)
        if run is None:
            raise ValueError(f"Run {run_id} was not found")
        config = self.db.get(TestConfig, run.config_id)
        if config is None:
            raise ValueError(f"Config {run.config_id} was not found")

        run.status = RunStatus.RUNNING.value
        run.started_at = utcnow()
        self.db.commit()

        graph = self._build_graph()
        initial_state: GraphState = {
            "run": run,
            "config": config,
            "steps_taken": 0,
            "visited_signatures": set(),
            "visited_action_keys": set(),
            "action_attempt_counts": {},
            "successful_actions": [],
            "discovered_flow_keys": set(),
            "discovered_forms": set(),
            "attempted_form_variants": set(),
            "submitted_forms": set(),
            "discovered_urls": set(),
            "visited_urls": set(),
            "navigation_stack": [],
            "home_url": self._normalized_url(config.target_url).geturl(),
            "seen_console_count": 0,
            "seen_network_count": 0,
            "scanned_urls": set(),
            "uncertainty_streak": 0,
            "done": False,
            "page_state": {},
            "interactive_elements": [],
            "last_action": None,
            "last_step_id": None,
        }

        try:
            final_state = await graph.ainvoke(
                initial_state,
                config={"recursion_limit": max(50, run.max_steps * 8)},
            )
            await self._finalize_run(final_state, failed=False)
        except Exception as exc:
            await self._close_runtime(initial_state)
            await self._handle_fatal_error(run, str(exc))
            raise

    def _build_graph(self):
        workflow = StateGraph(dict)
        workflow.add_node("bootstrap", self._bootstrap)
        workflow.add_node("login", self._login)
        workflow.add_node("inspect", self._inspect_page)
        workflow.add_node("choose_action", self._choose_action)
        workflow.add_node("execute_action", self._execute_action)
        workflow.add_node("validate", self._validate_page)
        workflow.add_node("finalize", self._graph_finalize)

        workflow.set_entry_point("bootstrap")
        workflow.add_edge("bootstrap", "login")
        workflow.add_edge("login", "inspect")
        workflow.add_edge("inspect", "choose_action")
        workflow.add_conditional_edges(
            "choose_action",
            self._route_after_choose,
            {"execute_action": "execute_action", "finalize": "finalize"},
        )
        workflow.add_edge("execute_action", "validate")
        workflow.add_conditional_edges(
            "validate",
            self._route_after_validate,
            {"inspect": "inspect", "finalize": "finalize"},
        )
        workflow.add_edge("finalize", END)
        return workflow.compile()

    async def _bootstrap(self, state: GraphState) -> GraphState:
        config: TestConfig = state["config"]
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=config.headless)
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()
        tools = PlaywrightTools(page=page, context=context, storage=self.storage, run_id=state["run"].id)
        await tools.start_tracing()

        state.update(
            {
                "playwright": playwright,
                "browser": browser,
                "context": context,
                "page": page,
                "tools": tools,
                "allowed_domains": set(config.allowed_domains or []),
            }
        )
        state["allowed_domains"].add(urlparse(config.target_url).netloc)

        result = await tools.open_page(config.login_url or config.target_url)
        state["home_url"] = self._normalized_url(config.target_url).geturl()
        state["page_state"] = await tools.get_page_state()
        step = await self._append_step(
            run=state["run"],
            step_index=state["steps_taken"],
            node_name="bootstrap",
            action="open_page",
            rationale="Opened the configured entry point before exploration begins.",
            risk_level=RiskLevel.SAFE.value,
            status=StepStatus.PASSED.value,
            details=result,
            locator={},
            element_label=config.login_url or config.target_url,
        )
        state["last_step_id"] = step.id
        state["steps_taken"] += 1
        return state

    async def _login(self, state: GraphState) -> GraphState:
        config: TestConfig = state["config"]
        if not config.username or not config.password:
            return state

        page = state["page"]
        tools: PlaywrightTools = state["tools"]

        try:
            if config.username_selector:
                await page.locator(config.username_selector).first.fill(config.username)
            else:
                await self._fill_by_heuristic(page, config.username, ["email", "username", "user"])

            if config.password_selector:
                await page.locator(config.password_selector).first.fill(config.password)
            else:
                await self._fill_by_heuristic(page, config.password, ["password", "pass"])

            if config.submit_selector:
                await page.locator(config.submit_selector).first.click()
            else:
                submit = page.get_by_role("button", name="sign in", exact=False)
                if await submit.count() == 0:
                    submit = page.get_by_role("button", name="login", exact=False)
                if await submit.count() == 0:
                    submit = page.locator("button[type='submit'], input[type='submit']")
                await submit.first.click()

            try:
                await page.wait_for_load_state("networkidle", timeout=6_000)
            except PlaywrightTimeoutError:
                pass

            screenshot_path = await tools.capture_screenshot(state["steps_taken"], "login-result")
            step = await self._append_step(
                run=state["run"],
                step_index=state["steps_taken"],
                node_name="login",
                action="submit_login",
                rationale="Credentials were provided, so the agent performed the configured login flow.",
                risk_level=RiskLevel.RISKY.value,
                status=StepStatus.PASSED.value,
                details={"url": page.url, "title": await page.title()},
                locator={"strategy": "custom", "selector": config.submit_selector or "heuristic"},
                element_label="Login submission",
            )
            self._record_artifact(step.id, state["run"].id, ArtifactType.SCREENSHOT.value, screenshot_path, "image/png")
            self._record_flow(
                run=state["run"],
                flow_type="login",
                name="Login flow",
                description="Authenticated with configured credentials.",
                actions=[
                    {
                        "type": "fill",
                        "locator": {"strategy": "css", "selector": config.username_selector or "input[type='email'], input[name='username']"},
                        "value": config.username,
                    },
                    {
                        "type": "fill",
                        "locator": {"strategy": "css", "selector": config.password_selector or "input[type='password']"},
                        "value": config.password,
                    },
                    {
                        "type": "click",
                        "locator": {"strategy": "css", "selector": config.submit_selector or "button[type='submit']"},
                    },
                ],
                metadata={"url": page.url, "title": await page.title()},
            )
            state["home_url"] = self._normalized_url(page.url).geturl()
            state["last_step_id"] = step.id
            state["steps_taken"] += 1
        except (PlaywrightError, PlaywrightTimeoutError, AssertionError) as exc:
            step = await self._append_step(
                run=state["run"],
                step_index=state["steps_taken"],
                node_name="login",
                action="submit_login",
                rationale="Attempted to log in with configured credentials.",
                risk_level=RiskLevel.RISKY.value,
                status=StepStatus.FAILED.value,
                details={"error": str(exc), "url": page.url},
                locator={"strategy": "custom", "selector": config.submit_selector or "heuristic"},
                element_label="Login submission",
            )
            self._record_failure(
                run_id=state["run"].id,
                failure_type=FailureType.EXPLORATION.value,
                title="Login flow failed",
                description=str(exc),
                evidence={"url": page.url},
                step_id=step.id,
            )
            state["last_step_id"] = step.id
            state["steps_taken"] += 1
        return state

    async def _inspect_page(self, state: GraphState) -> GraphState:
        if state["steps_taken"] >= state["run"].max_steps:
            state["done"] = True
            return state

        tools: PlaywrightTools = state["tools"]
        state["page_state"] = await tools.get_page_state()
        state["interactive_elements"] = await tools.list_interactive_elements()
        current_url = self._normalized_url(state["page"].url)
        current_path = urlparse(state["page"].url).path or "/"
        state["visited_urls"].add(current_url)
        state["discovered_urls"].add(current_url)
        state["discovered_forms"].update(
            f"{current_path}|{signature}"
            for signature in {
                normalize_text(element.get("formSignature"))
                for element in state["interactive_elements"]
                if element.get("formSignature")
            }
            if signature
        )
        for element in state["interactive_elements"]:
            discovered_url = self._discover_url_candidate(
                current_url=current_url,
                href=element.get("href"),
                allowed_domains=state["allowed_domains"],
            )
            if discovered_url:
                state["discovered_urls"].add(discovered_url)
        return state

    async def _choose_action(self, state: GraphState) -> GraphState:
        action = self._pick_action(state)
        if action is None:
            state["uncertainty_streak"] += 1
            if state["uncertainty_streak"] >= 2:
                state["done"] = True
                self._record_failure(
                    run_id=state["run"].id,
                    failure_type=FailureType.UNCERTAINTY.value,
                    title="Exploration stopped due to uncertainty",
                    description="The agent could not identify a confident low-risk next action.",
                    evidence={"url": state["page"].url, "page_state": state["page_state"]},
                )
            state["next_action"] = None
            return state

        state["uncertainty_streak"] = 0
        state["next_action"] = action
        return state

    async def _execute_action(self, state: GraphState) -> GraphState:
        action = state["next_action"]
        if action is None:
            return state

        tools: PlaywrightTools = state["tools"]
        page = state["page"]
        pre_url = page.url
        pre_title = await page.title()
        status = StepStatus.PASSED.value
        details: dict[str, Any] = {"pre_url": pre_url, "pre_title": pre_title}
        step = None

        try:
            if action["type"] == "goto":
                result = await tools.open_page(action["value"])
            elif action["type"] == "backtrack":
                result = await tools.open_page(action["value"])
            elif action["type"] == "click":
                result = await tools.click_element(action["element"])
            elif action["type"] == "fill":
                result = await tools.type_text(action["element"], action["value"])
            elif action["type"] == "select":
                result = await tools.select_option(action["element"], action["value"])
            elif action["type"] == "press":
                result = await tools.press_key(action["value"])
            elif action["type"] == "assert_text":
                result = await tools.assert_text(action["value"])
            elif action["type"] == "assert_url":
                result = await tools.assert_url(action["value"])
            else:
                raise ValueError(f"Unsupported action type: {action['type']}")
            details.update({"result": result, "post_url": page.url, "post_title": await page.title()})
        except (PlaywrightError, PlaywrightTimeoutError, AssertionError, ValueError) as exc:
            status = StepStatus.FAILED.value
            details.update({"error": str(exc), "post_url": page.url, "post_title": await page.title()})

        details["form_signature"] = action.get("form_signature")
        details["submits_form"] = bool(action.get("submits_form"))
        details["form_scenario"] = action.get("form_scenario")
        details["form_variant_key"] = action.get("form_variant_key")
        details["form_label"] = action.get("form_label")

        step = await self._append_step(
            run=state["run"],
            step_index=state["steps_taken"],
            node_name="execute_action",
            action=action["type"],
            rationale=action["rationale"],
            risk_level=action["risk"],
            status=status,
            details=details,
            locator=action.get("element", {}).get("locator", {}),
            element_label=action.get("element", {}).get("displayLabel") if action.get("element") else action.get("value"),
            confidence=action.get("confidence", 0.0),
        )
        state["last_step_id"] = step.id

        if status == StepStatus.FAILED.value:
            self._record_failure(
                run_id=state["run"].id,
                failure_type=FailureType.EXPLORATION.value,
                title=f"Action failed: {action['type']}",
                description=str(details.get("error", "Action failed.")),
                evidence={"action": action, "url": page.url},
                step_id=step.id,
            )

        screenshot_path = await tools.capture_screenshot(state["steps_taken"], action["label"])
        self._record_artifact(step.id, state["run"].id, ArtifactType.SCREENSHOT.value, screenshot_path, "image/png")
        state["steps_taken"] += 1
        state["visited_signatures"].add(action["signature"])
        state["visited_action_keys"].add(action["action_key"])
        state["action_attempt_counts"][action["action_key"]] = state["action_attempt_counts"].get(action["action_key"], 0) + 1
        executed_action = dict(action)
        executed_action.update({"pre_url": pre_url, "post_url": page.url, "status": status})
        state["last_action"] = executed_action

        pre_url_normalized = self._normalized_url(pre_url).geturl()
        post_url_normalized = self._normalized_url(page.url).geturl()
        if status == StepStatus.PASSED.value and pre_url_normalized != post_url_normalized:
            if action["type"] == "backtrack":
                while state["navigation_stack"] and state["navigation_stack"][-1] != post_url_normalized:
                    state["navigation_stack"].pop()
                if state["navigation_stack"] and state["navigation_stack"][-1] == post_url_normalized:
                    state["navigation_stack"].pop()
            elif not state["navigation_stack"] or state["navigation_stack"][-1] != pre_url_normalized:
                state["navigation_stack"].append(pre_url_normalized)

        if status == StepStatus.PASSED.value:
            if action.get("submits_form") and action.get("form_variant_key"):
                state["attempted_form_variants"].add(action["form_variant_key"])
            if (
                action.get("submits_form")
                and action.get("form_signature")
                and action.get("form_scenario") == "happy_path"
            ):
                state["submitted_forms"].add(action["form_signature"])
            recorded = {
                "type": action["type"],
                "locator": action.get("element", {}).get("locator", {}),
                "value": action.get("value"),
                "label": action["label"],
                "category": action["category"],
                "url": page.url,
                "form_signature": action.get("form_signature"),
                "form_scenario": action.get("form_scenario"),
                "form_variant_key": action.get("form_variant_key"),
            }
            state["successful_actions"].append(recorded)
            self._maybe_record_flow(state, action)
        return state

    async def _validate_page(self, state: GraphState) -> GraphState:
        tools: PlaywrightTools = state["tools"]
        current_state = await tools.get_page_state()
        state["page_state"] = current_state
        state["interactive_elements"] = await tools.list_interactive_elements()

        if not current_state.get("title") and not current_state.get("visibleText"):
            self._record_failure(
                run_id=state["run"].id,
                failure_type=FailureType.ASSERTION.value,
                title="Page content missing after action",
                description="The page has neither a title nor visible body text after the last action.",
                evidence={"url": state["page"].url},
                step_id=state.get("last_step_id"),
            )

        console_errors = tools.get_console_errors()
        for entry in console_errors[state["seen_console_count"] :]:
            self._record_failure(
                run_id=state["run"].id,
                failure_type=FailureType.CONSOLE.value,
                title="Browser console error",
                description=entry["text"],
                evidence=entry,
                step_id=state.get("last_step_id"),
            )
        state["seen_console_count"] = len(console_errors)

        network_failures = tools.get_network_failures()
        for entry in network_failures[state["seen_network_count"] :]:
            self._record_failure(
                run_id=state["run"].id,
                failure_type=FailureType.NETWORK.value,
                title="Network request failure",
                description=entry.get("error_text", "Request failed"),
                evidence=entry,
                step_id=state.get("last_step_id"),
            )
        state["seen_network_count"] = len(network_failures)

        current_url = state["page"].url
        if current_url not in state["scanned_urls"]:
            findings = await tools.run_accessibility_scan()
            if findings:
                self._record_failure(
                    run_id=state["run"].id,
                    failure_type=FailureType.ACCESSIBILITY.value,
                    title="Accessibility issues detected",
                    description=f"Detected {len(findings)} accessibility findings on {current_url}.",
                    evidence={"findings": findings, "url": current_url},
                    step_id=state.get("last_step_id"),
                )
            state["scanned_urls"].add(current_url)

        if (state.get("last_action") or {}).get("submits_form"):
            feedback = await tools.inspect_form_feedback()
            last_action = state["last_action"]
            scenario = last_action.get("form_scenario")
            if scenario == "happy_path" and (feedback.get("invalidFieldCount") or feedback.get("errorMessages")):
                self._record_failure(
                    run_id=state["run"].id,
                    failure_type=FailureType.ASSERTION.value,
                    title="Valid form submission surfaced validation or error feedback",
                    description=self._describe_form_feedback(feedback),
                    evidence={"form_feedback": feedback, "action": last_action, "url": current_url},
                    step_id=state.get("last_step_id"),
                )
            if scenario in {"missing_required", "invalid_email"} and not (
                feedback.get("invalidFieldCount") or feedback.get("errorMessages")
            ):
                self._record_failure(
                    run_id=state["run"].id,
                    failure_type=FailureType.ASSERTION.value,
                    title="Form accepted invalid or incomplete input without visible validation",
                    description=self._missing_validation_description(scenario),
                    evidence={"form_feedback": feedback, "action": last_action, "url": current_url},
                    step_id=state.get("last_step_id"),
                )

        if state["steps_taken"] >= state["run"].max_steps:
            state["done"] = True
        return state

    async def _graph_finalize(self, state: GraphState) -> GraphState:
        tools: PlaywrightTools = state["tools"]
        trace_path = await tools.save_trace()
        if trace_path:
            self._record_artifact(None, state["run"].id, ArtifactType.TRACE.value, trace_path, "application/zip")
        return state

    def _route_after_choose(self, state: GraphState) -> str:
        return "execute_action" if state.get("next_action") and not state.get("done") else "finalize"

    def _route_after_validate(self, state: GraphState) -> str:
        return "finalize" if state.get("done") else "inspect"

    def _pick_action(self, state: GraphState) -> dict[str, Any] | None:
        elements: list[dict[str, Any]] = state["interactive_elements"]
        action_attempt_counts: dict[str, int] = state["action_attempt_counts"]
        last_action = state.get("last_action") or {}
        current_url = self._normalized_url(state["page"].url)
        current_path = current_url.path or "/"
        allowed_domains: set[str] = state["allowed_domains"]
        discovered_urls: set[str] = state["discovered_urls"]
        visited_urls: set[str] = state["visited_urls"]
        attempted_form_variants: set[str] = state["attempted_form_variants"]
        submitted_forms: set[str] = state["submitted_forms"]
        navigation_stack: list[str] = state["navigation_stack"]
        home_url = normalize_text(state.get("home_url"))
        safe_mode = state["run"].safe_mode
        candidates: list[dict[str, Any]] = []
        pending_submit_controls: list[dict[str, Any]] = []
        active_form_variants = self._active_form_variants(elements, current_path, attempted_form_variants)

        for element in elements:
            if element.get("disabled"):
                continue

            href = element.get("href") or ""
            if href.startswith("http") and urlparse(href).netloc not in allowed_domains:
                continue

            label = normalize_text(element.get("displayLabel"))
            tag = element.get("tag", "")
            risk = element.get("risk", classify_risk(label, href))
            if safe_mode and risk == RiskLevel.DESTRUCTIVE.value:
                continue

            raw_category = element.get("category", infer_category(label, href))
            form_signature = self._form_signature(current_path, element)
            active_form_variant = active_form_variants.get(form_signature) if form_signature else None
            form_scenario = active_form_variant["name"] if active_form_variant else None
            variant_target_signature = active_form_variant["target_signature"] if active_form_variant else None
            form_variant_key = active_form_variant["variant_key"] if active_form_variant else None
            scenario_scope = self._form_candidate_scope(form_signature, form_variant_key)
            category = "form" if form_signature and raw_category == "navigation" else raw_category
            if tag in {"input", "textarea"}:
                if form_signature and form_scenario is None:
                    continue
                input_type = (element.get("inputType") or "text").lower()
                if input_type in {"hidden", "button", "reset", "file"}:
                    continue

                if input_type == "submit":
                    if form_signature:
                        pending_submit_controls.append(
                            {
                                "element": element,
                                "label": label or "submit form",
                                "risk": risk,
                                "category": raw_category,
                                "form_signature": form_signature,
                                "form_scenario": form_scenario,
                                "form_variant_key": form_variant_key,
                                "form_label": normalize_text(element.get("formLabel")) or label or "form",
                            }
                        )
                    continue

                if input_type in {"checkbox", "radio"}:
                    action_key = self._action_key(
                        current_path,
                        "click",
                        label or input_type,
                        category,
                        scope=scenario_scope,
                    )
                    if not self._can_queue_action(
                        action_key=action_key,
                        action_type="click",
                        category=category,
                        action_attempt_counts=action_attempt_counts,
                        last_action=last_action,
                        current_url=current_url.geturl(),
                    ):
                        continue
                    candidates.append(
                        {
                            "type": "click",
                            "element": element,
                            "label": f"toggle {label or input_type}",
                            "signature": f"{element['signature']}|click",
                            "risk": RiskLevel.SAFE.value if category == "filter" else risk,
                            "confidence": 0.78 if form_signature else 0.62,
                            "category": category,
                            "priority": self._priority_for_toggle(category, inside_form=form_signature is not None),
                            "rationale": self._rationale_for_toggle(element, category, form_scenario),
                            "action_key": action_key,
                            "form_signature": form_signature,
                            "form_scenario": form_scenario,
                            "form_variant_key": form_variant_key,
                            "form_label": normalize_text(element.get("formLabel")) or label or "form",
                        }
                    )
                    continue

                value = self._value_for_field(
                    element,
                    scenario=form_scenario,
                    target_signature=variant_target_signature,
                )
                if value is None:
                    continue

                priority = self._priority_for_field(
                    category,
                    inside_form=form_signature is not None,
                    required=bool(element.get("required")),
                    input_type=input_type,
                )
                action_key = self._action_key(current_path, "fill", label, category, value, scope=scenario_scope)
                if not self._can_queue_action(
                    action_key=action_key,
                    action_type="fill",
                    category=category,
                    action_attempt_counts=action_attempt_counts,
                    last_action=last_action,
                    current_url=current_url.geturl(),
                ):
                    continue
                candidates.append(
                    {
                        "type": "fill",
                        "element": element,
                        "value": value,
                        "label": f"fill {label}",
                        "signature": f"{element['signature']}|fill|{value}",
                        "risk": RiskLevel.SAFE.value if category == "filter" else RiskLevel.RISKY.value,
                        "confidence": 0.86 if form_signature else (0.82 if category == "filter" else 0.68),
                        "category": category,
                        "priority": priority,
                        "rationale": self._rationale_for_field(element, category, form_scenario),
                        "action_key": action_key,
                        "form_signature": form_signature,
                        "form_scenario": form_scenario,
                        "form_variant_key": form_variant_key,
                        "form_label": normalize_text(element.get("formLabel")) or label or "form",
                    }
                )
            elif tag == "select" and element.get("options"):
                if form_signature and form_scenario is None:
                    continue
                option = self._value_for_select(
                    element,
                    scenario=form_scenario,
                    target_signature=variant_target_signature,
                )
                if option:
                    action_key = self._action_key(current_path, "select", label, category, option, scope=scenario_scope)
                    if not self._can_queue_action(
                        action_key=action_key,
                        action_type="select",
                        category=category,
                        action_attempt_counts=action_attempt_counts,
                        last_action=last_action,
                        current_url=current_url.geturl(),
                    ):
                        continue
                    candidates.append(
                        {
                            "type": "select",
                            "element": element,
                            "value": option,
                            "label": f"select {label}",
                            "signature": f"{element['signature']}|select|{option}",
                            "risk": RiskLevel.SAFE.value,
                            "confidence": 0.82 if form_signature else 0.7,
                            "category": category,
                            "priority": self._priority_for_select(category, inside_form=form_signature is not None),
                            "rationale": self._rationale_for_select(label, category, form_scenario),
                            "action_key": action_key,
                            "form_signature": form_signature,
                            "form_scenario": form_scenario,
                            "form_variant_key": form_variant_key,
                            "form_label": normalize_text(element.get("formLabel")) or label or "form",
                        }
                    )
            else:
                if element.get("isSubmitControl") and form_signature:
                    pending_submit_controls.append(
                        {
                            "element": element,
                            "label": label or "submit form",
                            "risk": risk,
                            "category": raw_category,
                            "form_signature": form_signature,
                            "form_scenario": form_scenario,
                            "form_variant_key": form_variant_key,
                            "form_label": normalize_text(element.get("formLabel")) or label or "form",
                        }
                    )
                    continue

                priority = self._priority_for_element(
                    label,
                    category,
                    current_path,
                    navigation_hint=bool(href) or element.get("role") in {"link", "tab", "menuitem"},
                )
                action_key = self._action_key(current_path, "click", label, category, scope=scenario_scope)
                if not self._can_queue_action(
                    action_key=action_key,
                    action_type="click",
                    category=category,
                    action_attempt_counts=action_attempt_counts,
                    last_action=last_action,
                    current_url=current_url.geturl(),
                ):
                    continue
                candidates.append(
                    {
                        "type": "click",
                        "element": element,
                        "label": f"click {label}",
                        "signature": f"{element['signature']}|click",
                        "risk": risk,
                        "confidence": 0.9 if risk == RiskLevel.SAFE.value else 0.64,
                        "category": category,
                        "priority": priority,
                        "rationale": self._rationale_for_click(label, category, risk),
                        "action_key": action_key,
                        "form_signature": form_signature,
                        "form_scenario": form_scenario,
                        "form_variant_key": form_variant_key,
                        "form_label": normalize_text(element.get("formLabel")) or label or "form",
                    }
                )

        for pending in pending_submit_controls:
            form_signature = pending["form_signature"]
            form_scenario = pending["form_scenario"]
            form_variant_key = pending.get("form_variant_key")
            if not form_signature or not form_scenario:
                continue
            if form_scenario == "happy_path" and form_signature in submitted_forms:
                continue
            if any(
                candidate.get("form_signature") == form_signature
                and candidate.get("form_variant_key") == form_variant_key
                and not candidate.get("submits_form")
                for candidate in candidates
            ):
                continue

            submit_category = "filter" if pending["category"] == "filter" else "form"
            submit_risk = (
                RiskLevel.SAFE.value
                if submit_category == "filter"
                else pending["risk"] if pending["risk"] != RiskLevel.SAFE.value else RiskLevel.RISKY.value
            )
            action_key = self._action_key(
                current_path,
                "submit",
                pending["label"],
                submit_category,
                scope=self._form_candidate_scope(form_signature, form_variant_key),
            )
            if not self._can_queue_action(
                action_key=action_key,
                action_type="submit",
                category=submit_category,
                action_attempt_counts=action_attempt_counts,
                last_action=last_action,
                current_url=current_url.geturl(),
            ):
                continue
            candidates.append(
                {
                    "type": "click",
                    "element": pending["element"],
                    "label": f"submit {pending['label']}",
                    "signature": f"{pending['element']['signature']}|submit",
                    "risk": submit_risk,
                    "confidence": 0.88,
                    "category": submit_category,
                    "priority": self._priority_for_submit(pending["category"], submit_risk),
                    "rationale": self._rationale_for_submit(
                        pending["label"],
                        pending["category"],
                        submit_risk,
                        form_scenario,
                    ),
                    "action_key": action_key,
                    "form_signature": form_signature,
                    "form_scenario": form_scenario,
                    "form_variant_key": form_variant_key,
                    "form_label": pending.get("form_label"),
                    "submits_form": True,
                }
            )

        for target_url in sorted(discovered_urls - visited_urls):
            if target_url == current_url:
                continue
            action_key = self._action_key(current_path, "goto", target_url.geturl(), "navigation", target_url.geturl())
            if not self._can_queue_action(
                action_key=action_key,
                action_type="goto",
                category="navigation",
                action_attempt_counts=action_attempt_counts,
                last_action=last_action,
                current_url=current_url.geturl(),
            ):
                continue
            candidates.append(
                {
                    "type": "goto",
                    "value": target_url.geturl(),
                    "label": f"open {target_url.path or '/'}",
                    "signature": f"goto|{target_url.geturl()}",
                    "risk": RiskLevel.SAFE.value,
                    "confidence": 0.94,
                    "category": "navigation",
                    "priority": 83,
                    "rationale": "Open a newly discovered page so the explorer can inspect additional forms and flows.",
                    "action_key": action_key,
                }
            )

        previous_url = navigation_stack[-1] if navigation_stack else ""
        if previous_url and previous_url != current_url.geturl():
            action_key = self._action_key(current_path, "backtrack", previous_url, "navigation", previous_url)
            if self._can_queue_action(
                action_key=action_key,
                action_type="backtrack",
                category="navigation",
                action_attempt_counts=action_attempt_counts,
                last_action=last_action,
                current_url=current_url.geturl(),
            ):
                candidates.append(
                    {
                        "type": "backtrack",
                        "value": previous_url,
                        "label": f"return to {urlparse(previous_url).path or '/'}",
                        "signature": f"backtrack|{previous_url}",
                        "risk": RiskLevel.SAFE.value,
                        "confidence": 0.89,
                        "category": "navigation",
                        "priority": 80,
                        "rationale": "Return to the previous page so the explorer can continue through the remaining menu and navigation branches.",
                        "action_key": action_key,
                    }
                )

        if home_url and home_url != current_url.geturl():
            action_key = self._action_key(current_path, "goto", home_url, "navigation", home_url, "home")
            if self._can_queue_action(
                action_key=action_key,
                action_type="goto",
                category="navigation",
                action_attempt_counts=action_attempt_counts,
                last_action=last_action,
                current_url=current_url.geturl(),
            ):
                candidates.append(
                    {
                        "type": "goto",
                        "value": home_url,
                        "label": "return to home page",
                        "signature": f"goto|home|{home_url}",
                        "risk": RiskLevel.SAFE.value,
                        "confidence": 0.86,
                        "category": "navigation",
                        "priority": 78,
                        "rationale": "Return to the main entry page so the explorer can continue into any top-level menu items that have not been exercised yet.",
                        "action_key": action_key,
                    }
                )

        if not candidates:
            return None

        candidates.sort(key=lambda item: (item["priority"], 1 if item["risk"] == RiskLevel.SAFE.value else 0), reverse=True)
        best = candidates[0]
        if best["confidence"] < 0.45:
            return None
        return best

    def _action_key(
        self,
        path: str,
        action_type: str,
        label: str,
        category: str,
        value: str | None = None,
        scope: str | None = None,
    ) -> str:
        normalized_label = normalize_text(label).lower()
        normalized_value = normalize_text(value).lower() if value else ""
        normalized_scope = normalize_text(scope).lower() if scope else ""
        return f"{path}|{normalized_scope}|{action_type}|{category}|{normalized_label}|{normalized_value}"

    def _normalized_url(self, url: str):
        parsed = urlparse(url)
        return parsed._replace(fragment="")

    def _discover_url_candidate(
        self,
        *,
        current_url,
        href: str | None,
        allowed_domains: set[str],
    ):
        normalized_href = normalize_text(href)
        if not normalized_href or normalized_href.startswith(("javascript:", "mailto:", "tel:", "#")):
            return None
        parsed = urlparse(urljoin(current_url.geturl(), normalized_href))
        if parsed.scheme not in {"http", "https"}:
            return None
        if parsed.netloc and parsed.netloc not in allowed_domains:
            return None
        return parsed._replace(fragment="")

    def _form_signature(self, path: str, element: dict[str, Any]) -> str | None:
        signature = normalize_text(element.get("formSignature"))
        if not signature:
            return None
        return f"{path}|{signature}"

    def _active_form_variants(
        self,
        elements: list[dict[str, Any]],
        path: str,
        attempted_form_variants: set[str],
    ) -> dict[str, dict[str, str] | None]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for element in elements:
            form_signature = self._form_signature(path, element)
            if form_signature:
                grouped.setdefault(form_signature, []).append(element)

        variants: dict[str, dict[str, str] | None] = {}
        for form_signature, grouped_elements in grouped.items():
            required_targets = [
                element
                for element in grouped_elements
                if bool(element.get("required")) and self._can_skip_for_missing_required(element)
            ]
            email_targets = [
                element
                for element in grouped_elements
                if (element.get("inputType") or "").lower() == "email"
            ]

            for target in required_targets:
                variant_key = f"{form_signature}|missing_required|{target['signature']}"
                if variant_key not in attempted_form_variants:
                    variants[form_signature] = {
                        "name": "missing_required",
                        "target_signature": target["signature"],
                        "variant_key": variant_key,
                    }
                    break
            if form_signature in variants:
                continue

            for target in email_targets:
                variant_key = f"{form_signature}|invalid_email|{target['signature']}"
                if variant_key not in attempted_form_variants:
                    variants[form_signature] = {
                        "name": "invalid_email",
                        "target_signature": target["signature"],
                        "variant_key": variant_key,
                    }
                    break
            if form_signature in variants:
                continue

            if f"{form_signature}|happy_path" not in attempted_form_variants:
                variants[form_signature] = {
                    "name": "happy_path",
                    "target_signature": "",
                    "variant_key": f"{form_signature}|happy_path",
                }
                continue

            variants[form_signature] = None

        return variants

    def _form_candidate_scope(self, form_signature: str | None, form_variant_key: str | None) -> str | None:
        if not form_signature:
            return None
        if not form_variant_key:
            return form_signature
        return form_variant_key

    def _can_skip_for_missing_required(self, element: dict[str, Any]) -> bool:
        tag = (element.get("tag") or "").lower()
        input_type = (element.get("inputType") or "").lower()
        if tag in {"textarea"}:
            return True
        if tag == "select":
            return not normalize_text(str(element.get("value") or ""))
        if tag == "input" and input_type in {"checkbox", "radio"}:
            return not bool(element.get("checked"))
        if tag == "input" and input_type not in {"checkbox", "radio", "hidden", "submit", "button", "reset", "file"}:
            return True
        return False

    def _can_queue_action(
        self,
        *,
        action_key: str,
        action_type: str,
        category: str,
        action_attempt_counts: dict[str, int],
        last_action: dict[str, Any],
        current_url: str,
    ) -> bool:
        if action_attempt_counts.get(action_key, 0) >= self._max_attempts_for_action(action_type, category):
            return False
        if last_action.get("action_key") != action_key:
            return True
        if normalize_text(last_action.get("status")) == StepStatus.FAILED.value:
            return False
        last_pre_url = normalize_text(last_action.get("pre_url"))
        last_post_url = normalize_text(last_action.get("post_url"))
        if last_pre_url == current_url and last_post_url == current_url:
            return False
        return True

    def _max_attempts_for_action(self, action_type: str, category: str) -> int:
        if action_type in {"fill", "select", "submit", "goto", "backtrack"}:
            return 1
        if category == "navigation":
            return 4
        if category in {"create", "edit", "settings", "view"}:
            return 2
        return 1

    def _priority_for_element(self, label: str, category: str, path: str, *, navigation_hint: bool = False) -> int:
        lower = label.lower()
        if category == "create":
            return 95
        if category == "edit":
            return 88
        if category == "filter":
            return 84
        if category == "navigation" and navigation_hint:
            return 82
        if category == "settings":
            return 74
        if category == "logout":
            return 30
        if any(keyword in lower for keyword in {"dashboard", "table", "list", "details", "view"}):
            return 72
        if path.endswith("/dashboard"):
            return 65
        return 58

    def _priority_for_field(self, category: str, *, inside_form: bool, required: bool, input_type: str) -> int:
        if category == "filter":
            return 92
        if inside_form and required:
            return 98
        if inside_form:
            return 94
        if input_type == "search":
            return 88
        return 75

    def _priority_for_select(self, category: str, *, inside_form: bool) -> int:
        if category == "filter":
            return 90
        if inside_form:
            return 93
        return 78

    def _priority_for_toggle(self, category: str, *, inside_form: bool) -> int:
        if category == "filter":
            return 89
        if inside_form:
            return 91
        return 68

    def _priority_for_submit(self, category: str, risk: str) -> int:
        if category in {"create", "edit", "login"}:
            return 97
        if category == "filter":
            return 92
        if risk == RiskLevel.SAFE.value:
            return 95
        return 94

    def _value_for_field(
        self,
        element: dict[str, Any],
        *,
        scenario: str | None = None,
        target_signature: str | None = None,
    ) -> str | None:
        label = normalize_text(
            element.get("label") or element.get("ariaLabel") or element.get("placeholder") or element.get("name")
        ).lower()
        input_type = (element.get("inputType") or "text").lower()
        if scenario == "missing_required" and target_signature == element.get("signature"):
            return "" if normalize_text(str(element.get("value") or "")) else None
        if scenario == "invalid_email" and target_signature == element.get("signature"):
            return "invalid-email"
        if "search" in label or "filter" in label or input_type == "search":
            return "test"
        if input_type == "password":
            return "AutoQA!234"
        if input_type == "email":
            return "qa@example.com"
        if input_type == "number":
            return "1"
        if input_type == "url":
            return "https://example.com"
        if input_type == "date":
            return "2026-03-10"
        if input_type == "datetime-local":
            return "2026-03-10T09:30"
        if input_type == "time":
            return "09:30"
        if input_type == "tel":
            return "+15555550123"
        if "name" in label:
            return "AutoQA Smoke"
        if "title" in label:
            return "AutoQA Title"
        if "description" in label or element.get("tag") == "textarea":
            return "Generated by AutoQA Agent"
        if input_type in {"text", ""}:
            return "AutoQA"
        return None

    def _value_for_select(
        self,
        element: dict[str, Any],
        *,
        scenario: str | None = None,
        target_signature: str | None = None,
    ) -> str | None:
        if scenario == "missing_required" and target_signature == element.get("signature"):
            return None
        for entry in element.get("options", []):
            label = normalize_text(entry.get("label"))
            if not label:
                continue
            placeholder_text = label.lower()
            if placeholder_text in {"select", "choose", "please select"}:
                continue
            if placeholder_text.startswith("select ") or placeholder_text.startswith("choose "):
                continue
            return label
        return None

    def _rationale_for_field(self, element: dict[str, Any], category: str, scenario: str | None) -> str:
        label = normalize_text(element.get("displayLabel")).lower()
        if scenario == "missing_required" and element.get("required"):
            return f"Leave '{label}' empty once to verify that the form blocks incomplete submissions with clear validation."
        if scenario == "invalid_email" and (element.get("inputType") or "").lower() == "email":
            return f"Enter an invalid email into '{label}' once to check client-side or server-side validation."
        if category == "filter":
            return f"Filling '{label}' should exercise search or filtering behavior without mutating data."
        if element.get("formSignature"):
            if element.get("required"):
                return f"Filling required field '{label}' moves the agent toward a full end-to-end form submission."
            return f"Filling '{label}' expands full-form coverage before the submit action is attempted."
        return f"Filling '{label}' is the least risky way to continue a visible form flow."

    def _rationale_for_select(self, label: str, category: str, scenario: str | None) -> str:
        if scenario == "missing_required":
            return f"Choose a visible option in '{label}' so the invalid-submission scenario only leaves the targeted required field empty."
        if scenario == "invalid_email":
            return f"Select a valid value for '{label}' while isolating the invalid email check."
        if category == "filter":
            return f"Selecting '{label}' should exercise a filter without mutating data."
        return "Selecting a visible option expands form coverage before attempting submission."

    def _rationale_for_toggle(self, element: dict[str, Any], category: str, scenario: str | None) -> str:
        label = normalize_text(element.get("displayLabel")).lower()
        if scenario == "missing_required":
            return f"Toggle '{label}' so the invalid-submission scenario covers the rest of the form before submit."
        if category == "filter":
            return f"Toggling '{label}' should exercise a non-destructive filter or preference control."
        return f"Toggling '{label}' completes another visible form control before submission."

    def _rationale_for_click(self, label: str, category: str, risk: str) -> str:
        if category == "create":
            return f"'{label}' is prioritized because create flows are core MVP coverage and the action is not classified as destructive."
        if category == "edit":
            return f"'{label}' should expose an edit form or detail surface, which is a high-value CRUD path."
        if category == "filter":
            return f"'{label}' is a deterministic low-risk action that should reveal search or filtering behavior."
        if category == "settings":
            return f"'{label}' is a common secondary flow and appears safe enough to explore."
        if risk == RiskLevel.SAFE.value:
            return f"'{label}' is the least risky visible action and keeps exploration moving."
        return f"'{label}' is the most valuable remaining action that is still allowed under the current safety mode."

    def _rationale_for_submit(self, label: str, category: str, risk: str, scenario: str | None) -> str:
        if scenario == "missing_required":
            return f"Submit '{label}' once with an intentionally missing required field to check whether validation blocks the form clearly."
        if scenario == "invalid_email":
            return f"Submit '{label}' once with an invalid email value to verify validation messaging and error handling."
        if category == "filter":
            return f"Submitting '{label}' validates that the visible filter form actually changes the results surface."
        if risk == RiskLevel.SAFE.value:
            return f"Submitting '{label}' checks the end-to-end form path after the visible inputs have been exercised."
        return f"Submitting '{label}' is the highest-value remaining step to verify the completed form flow."

    def _missing_validation_description(self, scenario: str) -> str:
        if scenario == "missing_required":
            return "The form submission did not show visible validation after the agent intentionally left a required field blank."
        if scenario == "invalid_email":
            return "The form submission did not show visible validation after the agent entered an invalid email format."
        return "The form submission did not show the expected validation feedback for an intentionally invalid scenario."

    def _describe_form_feedback(self, feedback: dict[str, Any]) -> str:
        error_messages = [normalize_text(message) for message in feedback.get("errorMessages", []) if normalize_text(message)]
        if error_messages:
            return f"Form submission displayed visible error feedback: {error_messages[0]}"

        invalid_fields = feedback.get("invalidFields", [])
        if invalid_fields:
            labels = [
                normalize_text(field.get("label") or field.get("type") or "field")
                for field in invalid_fields
                if isinstance(field, dict)
            ]
            preview = ", ".join(labels[:3])
            return f"Form submission left invalid fields on the page: {preview or 'validation state persisted'}."

        return "Form submission produced validation feedback that should be reviewed."

    def _maybe_record_flow(self, state: GraphState, action: dict[str, Any]) -> None:
        category = action["category"]
        if category not in {"login", "create", "edit", "filter", "form", "settings", "logout", "view"}:
            return

        page = state["page"]
        flow_key = f"{category}:{page.url}"
        if flow_key in state["discovered_flow_keys"]:
            return
        state["discovered_flow_keys"].add(flow_key)

        actions = state["successful_actions"][-4:]
        self._record_flow(
            run=state["run"],
            flow_type=category,
            name=f"{category.title()} flow",
            description=f"Successful {category} interaction ending at {page.url}.",
            actions=actions,
            metadata={"url": page.url, "title": state["page_state"].get("title")},
        )

    async def _fill_by_heuristic(self, page, value: str, labels: list[str]) -> None:
        for label in labels:
            locator = page.get_by_label(label, exact=False)
            if await locator.count() > 0:
                await locator.first.fill(value)
                return

            locator = page.get_by_placeholder(label, exact=False)
            if await locator.count() > 0:
                await locator.first.fill(value)
                return

        input_locator = page.locator("input")
        if await input_locator.count() > 0:
            await input_locator.first.fill(value)

    async def _append_step(
        self,
        *,
        run: TestRun,
        step_index: int,
        node_name: str,
        action: str,
        rationale: str,
        risk_level: str,
        status: str,
        details: dict[str, Any],
        locator: dict[str, Any],
        element_label: str | None,
        confidence: float = 1.0,
    ) -> RunStep:
        step = RunStep(
            run_id=run.id,
            step_index=step_index,
            node_name=node_name,
            action=action,
            rationale=rationale,
            page_title=details.get("post_title") or details.get("title") or details.get("pre_title"),
            url=details.get("post_url") or details.get("url") or details.get("pre_url"),
            element_label=element_label,
            locator=locator,
            risk_level=risk_level,
            status=status,
            confidence=confidence,
            details=details,
            finished_at=utcnow(),
        )
        self.db.add(step)
        self.db.commit()
        self.db.refresh(step)
        return step

    def _record_failure(
        self,
        *,
        run_id: str,
        failure_type: str,
        title: str,
        description: str,
        evidence: dict[str, Any],
        step_id: str | None = None,
        severity: str = "medium",
    ) -> FailureReport:
        run = self.db.get(TestRun, run_id)
        step = self.db.get(RunStep, step_id) if step_id else None
        enriched_evidence = self._build_failure_evidence(
            run=run,
            step=step,
            failure_type=failure_type,
            title=title,
            description=description,
            severity=severity,
            evidence=evidence,
        )
        friendly_title = str(enriched_evidence.get("bug_report", {}).get("title") or title)
        report = FailureReport(
            run_id=run_id,
            step_id=step_id,
            failure_type=failure_type,
            severity=severity,
            title=friendly_title,
            description=description,
            evidence=enriched_evidence,
        )
        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)
        report_path = self.storage.write_json("reports", run_id, f"{slugify(friendly_title)}-{report.id}.json", enriched_evidence)
        self._record_artifact(
            step_id,
            run_id,
            ArtifactType.REPORT.value,
            report_path,
            "application/json",
            {"failure_id": report.id, "format": "json"},
        )
        markdown_path = self.storage.write_text(
            "reports",
            run_id,
            f"{slugify(friendly_title)}-{report.id}.md",
            self._build_failure_markdown(report=report, run=run, step=step),
        )
        self._record_artifact(
            step_id,
            run_id,
            ArtifactType.REPORT.value,
            markdown_path,
            "text/markdown",
            {"failure_id": report.id, "format": "markdown"},
        )
        return report

    def _build_failure_evidence(
        self,
        *,
        run: TestRun | None,
        step: RunStep | None,
        failure_type: str,
        title: str,
        description: str,
        severity: str,
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        enriched = dict(evidence)
        url = enriched.get("url") or (step.url if step else run.config.target_url if run else None)
        step_context = self._step_context(step)
        bug_title = self._bug_title(
            failure_type=failure_type,
            title=title,
            description=description,
            evidence=enriched,
            step=step,
        )
        actual_result = self._actual_result(
            failure_type=failure_type,
            title=title,
            description=description,
            evidence=enriched,
            step=step,
        )
        expected_result = self._expected_result(
            failure_type=failure_type,
            title=title,
            evidence=enriched,
            step=step,
        )
        assessment = self._assess_failure(
            failure_type=failure_type,
            title=title,
            description=description,
            evidence=enriched,
        )
        enriched["bug_report"] = {
            "title": bug_title,
            "summary": self._bug_summary(bug_title, actual_result),
            "bug_description": description,
            "actual_result": actual_result,
            "expected_result": expected_result,
            "assessment": assessment["label"],
            "verdict": assessment["verdict"],
            "reason": assessment["reason"],
            "severity": severity,
            "page_url": url,
            "step": step_context,
            "reproduction_steps": self._reproduction_steps(run=run, step=step, url=url, title=title),
        }
        if url:
            enriched.setdefault("url", url)
        if step_context:
            enriched.setdefault("step_context", step_context)
        return enriched

    def _assess_failure(
        self,
        *,
        failure_type: str,
        title: str,
        description: str,
        evidence: dict[str, Any],
        ) -> dict[str, str]:
        text = f"{title} {description}".lower()
        action = evidence.get("action", {}) if isinstance(evidence.get("action"), dict) else {}
        scenario = action.get("form_scenario")
        if failure_type == FailureType.ACCESSIBILITY.value:
            return {
                "verdict": "confirmed-issue",
                "label": "Confirmed issue",
                "reason": "Accessibility findings are actionable product defects even when the flow remains usable.",
            }
        if failure_type == FailureType.CONSOLE.value:
            return {
                "verdict": "likely-bug",
                "label": "Likely bug",
                "reason": "Unhandled browser errors usually indicate broken client-side behavior.",
            }
        if failure_type == FailureType.NETWORK.value:
            status = evidence.get("status")
            if isinstance(status, int) and 400 <= status < 500:
                return {
                    "verdict": "needs-review",
                    "label": "Needs review",
                    "reason": "The request failed with a client-visible HTTP error. This may be expected validation or an application bug.",
                }
            return {
                "verdict": "likely-bug",
                "label": "Likely bug",
                "reason": "Failed network requests typically block the workflow being tested.",
            }
        if failure_type == FailureType.UNCERTAINTY.value:
            return {
                "verdict": "needs-review",
                "label": "Needs review",
                "reason": "The agent could not safely continue, which indicates incomplete coverage rather than a confirmed product defect.",
            }
        if scenario in {"missing_required", "invalid_email"} and "without visible validation" in text:
            return {
                "verdict": "confirmed-issue",
                "label": "Confirmed issue",
                "reason": "The form accepted intentionally invalid input without surfacing validation, which is a strong product defect signal.",
            }
        if scenario == "happy_path" and ("validation" in text or "error feedback" in text):
            return {
                "verdict": "likely-bug",
                "label": "Likely bug",
                "reason": "A valid-form scenario should not end in validation or generic error feedback.",
            }
        if "validation" in text or "required" in text or "invalid" in text:
            return {
                "verdict": "needs-review",
                "label": "Needs review",
                "reason": "The form showed validation or error feedback. Review whether the submitted data should have been accepted.",
            }
        if failure_type == FailureType.ASSERTION.value:
            return {
                "verdict": "likely-bug",
                "label": "Likely bug",
                "reason": "The UI state after the action did not match the expected baseline for a healthy page.",
            }
        return {
            "verdict": "needs-review",
            "label": "Needs review",
            "reason": "The run captured a problem, but the available evidence is not conclusive enough to label it a product bug automatically.",
        }

    def _step_context(self, step: RunStep | None) -> dict[str, Any] | None:
        if step is None:
            return None
        return {
            "step_id": step.id,
            "step_index": step.step_index,
            "action": step.action,
            "element_label": step.element_label,
            "url": step.url,
            "page_title": step.page_title,
            "risk_level": step.risk_level,
        }

    def _reproduction_steps(
        self,
        *,
        run: TestRun | None,
        step: RunStep | None,
        url: str | None,
        title: str,
    ) -> list[str]:
        steps: list[str] = []
        if run is not None:
            steps.append(f"Open the target application at {run.config.target_url}.")
            if run.config.login_url and run.config.username:
                steps.append(f"Sign in through {run.config.login_url} with a valid test account.")
        elif url:
            steps.append(f"Open {url}.")

        if url and run is not None and url != run.config.target_url:
            steps.append(f"Navigate to {url}.")

        if run is not None and step is not None:
            recent_steps = self._recent_steps(run_id=run.id, step_index=step.step_index)
            for recent_step in recent_steps:
                phrase = self._reproduction_phrase(recent_step)
                if phrase and (not steps or steps[-1] != phrase):
                    steps.append(phrase)
        elif step is not None:
            phrase = self._reproduction_phrase(step)
            if phrase:
                steps.append(phrase)

        steps.append(f"Observe the issue titled '{title}'.")
        return steps

    def _bug_title(
        self,
        *,
        failure_type: str,
        title: str,
        description: str,
        evidence: dict[str, Any],
        step: RunStep | None,
    ) -> str:
        action = evidence.get("action", {}) if isinstance(evidence.get("action"), dict) else {}
        scenario = action.get("form_scenario")
        form_label = normalize_text(action.get("form_label"))
        step_form_label = (
            normalize_text(step.details.get("form_label"))
            if step is not None and isinstance(step.details, dict)
            else ""
        )
        action_label = normalize_text(
            form_label
            or step_form_label
            or (step.element_label if step else None)
            or action.get("label")
            or title
        ) or "the form"
        page_url = normalize_text((step.url if step else None) or evidence.get("url"))

        if failure_type == FailureType.NETWORK.value:
            request_url = normalize_text(evidence.get("url"))
            status = evidence.get("status")
            if status:
                return f"Request to {request_url or page_url or 'the backend'} returned HTTP {status}"
            return f"Network request failed while testing {action_label}"
        if failure_type == FailureType.CONSOLE.value:
            return f"Console error appears after interacting with {action_label}"
        if failure_type == FailureType.ACCESSIBILITY.value:
            return f"Accessibility issue found on {page_url or 'the current page'}"
        if scenario == "happy_path":
            return f"Valid submission for {action_label} fails instead of completing successfully"
        if scenario in {"missing_required", "invalid_email"} and "without visible validation" in description.lower():
            return f"{action_label} accepts invalid input without validation"
        if step is not None and step.action in {"goto", "backtrack"}:
            return f"Navigation to {action_label} failed"
        if step is not None:
            return f"{step.action.title()} failed for {action_label}"
        return title

    def _bug_summary(self, bug_title: str, actual_result: str) -> str:
        return f"{bug_title}. {actual_result}"

    def _actual_result(
        self,
        *,
        failure_type: str,
        title: str,
        description: str,
        evidence: dict[str, Any],
        step: RunStep | None,
    ) -> str:
        action = evidence.get("action", {}) if isinstance(evidence.get("action"), dict) else {}
        scenario = action.get("form_scenario")
        if failure_type == FailureType.NETWORK.value:
            return normalize_text(description) or "The browser recorded a failed network request."
        if failure_type == FailureType.CONSOLE.value:
            return normalize_text(description) or "The browser console logged an error."
        if failure_type == FailureType.ACCESSIBILITY.value:
            return normalize_text(description) or "Accessibility findings were detected on the page."
        if scenario in {"missing_required", "invalid_email"} and "without visible validation" in description.lower():
            return "The form submission went through without showing the expected validation feedback."
        if scenario == "happy_path":
            return "The form surfaced validation or generic error feedback during a valid submission attempt."
        if failure_type == FailureType.ASSERTION.value:
            return normalize_text(description) or "The page did not reach the expected post-action state."
        return normalize_text(description) or f"{title}."

    def _expected_result(
        self,
        *,
        failure_type: str,
        title: str,
        evidence: dict[str, Any],
        step: RunStep | None,
    ) -> str:
        action = evidence.get("action", {}) if isinstance(evidence.get("action"), dict) else {}
        scenario = action.get("form_scenario")
        if failure_type == FailureType.NETWORK.value:
            return "The related request should complete successfully without transport or HTTP failure."
        if failure_type == FailureType.CONSOLE.value:
            return "The browser console should remain free of runtime errors during the tested flow."
        if failure_type == FailureType.ACCESSIBILITY.value:
            return "Interactive content should meet the basic accessibility checks collected by the agent."
        if scenario == "happy_path":
            return "A valid form submission should complete successfully and show a success state or next-step page."
        if scenario == "missing_required":
            return "The form should block submission and highlight the missing required field with clear validation."
        if scenario == "invalid_email":
            return "The form should block submission and show validation for the invalid email value."
        if failure_type == FailureType.ASSERTION.value:
            return "The page should remain usable and display the expected content after the action."
        if step is not None and step.action in {"goto", "backtrack"}:
            return "The target page should open successfully."
        return "The tested workflow should complete without errors."

    def _recent_steps(self, *, run_id: str, step_index: int, limit: int = 5) -> list[RunStep]:
        recent_steps = (
            self.db.query(RunStep)
            .filter(RunStep.run_id == run_id, RunStep.step_index <= step_index)
            .order_by(RunStep.step_index.desc())
            .limit(limit)
            .all()
        )
        return list(reversed(recent_steps))

    def _reproduction_phrase(self, step: RunStep) -> str | None:
        details = step.details if isinstance(step.details, dict) else {}
        label = normalize_text(step.element_label or details.get("form_label")) or "the visible control"
        if step.node_name == "bootstrap":
            return None
        if step.action == "submit_login":
            return "Submit the login form."
        if step.action in {"goto", "backtrack"}:
            return f"Open {step.url or label}."
        if step.action == "fill":
            return f"Fill {label}."
        if step.action == "select":
            return f"Choose a value in {label}."
        if step.action == "click":
            if details.get("submits_form"):
                return f"Submit {normalize_text(details.get('form_label')) or label}."
            return f"Click {label}."
        if step.action == "press":
            return f"Press {label}."
        return f"Perform {step.action} on {label}."

    def _build_failure_markdown(
        self,
        *,
        report: FailureReport,
        run: TestRun | None,
        step: RunStep | None,
    ) -> str:
        bug_report = report.evidence.get("bug_report", {}) if isinstance(report.evidence, dict) else {}
        raw_evidence = {
            key: value
            for key, value in (report.evidence.items() if isinstance(report.evidence, dict) else [])
            if key != "bug_report"
        }
        friendly_title = str(bug_report.get("title") or report.title)
        lines = [
            f"# {friendly_title}",
            "",
            f"- Assessment: {bug_report.get('assessment', 'Needs review')}",
            f"- Severity: {report.severity}",
            f"- Failure type: {report.failure_type}",
        ]
        if bug_report.get("page_url"):
            lines.append(f"- URL: {bug_report['page_url']}")
        if step is not None:
            lines.append(f"- Step: {step.step_index} ({step.action})")
            if step.element_label:
                lines.append(f"- Element: {step.element_label}")

        lines.extend(
            [
                "",
                "## What happened",
                str(bug_report.get("bug_description", report.description)),
                "",
                "## Actual result",
                str(bug_report.get("actual_result", report.description)),
                "",
                "## Expected result",
                str(bug_report.get("expected_result", "The tested workflow should complete without errors.")),
                "",
                "## Why this matters",
                str(bug_report.get("reason", "Review the raw evidence attached to this run.")),
            ]
        )

        reproduction_steps = bug_report.get("reproduction_steps", [])
        if isinstance(reproduction_steps, list) and reproduction_steps:
            lines.extend(["", "## Reproduction steps"])
            lines.extend(f"{index}. {item}" for index, item in enumerate(reproduction_steps, start=1))

        lines.extend(["", "## Raw evidence", "```json", json.dumps(raw_evidence, indent=2), "```"])
        if run is not None:
            lines.extend(["", f"_Run: {run.id}_"])
        return "\n".join(lines)

    def _record_artifact(
        self,
        step_id: str | None,
        run_id: str,
        artifact_type: str,
        file_path: str,
        mime_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> Artifact:
        artifact = Artifact(
            run_id=run_id,
            step_id=step_id,
            type=artifact_type,
            file_path=file_path,
            mime_type=mime_type,
            artifact_metadata=metadata or {},
        )
        self.db.add(artifact)
        self.db.commit()
        self.db.refresh(artifact)
        return artifact

    def _record_flow(
        self,
        *,
        run: TestRun,
        flow_type: str,
        name: str,
        description: str,
        actions: list[dict[str, Any]],
        metadata: dict[str, Any],
    ) -> DiscoveredFlow:
        flow = DiscoveredFlow(
            run_id=run.id,
            name=name,
            flow_type=flow_type,
            success=True,
            description=description,
            path=actions,
            flow_metadata=metadata,
        )
        self.db.add(flow)
        self.db.commit()
        self.db.refresh(flow)
        return flow

    async def _handle_fatal_error(self, run: TestRun, error_message: str) -> None:
        self._record_failure(
            run_id=run.id,
            failure_type=FailureType.EXPLORATION.value,
            title="Run failed unexpectedly",
            description=error_message,
            evidence={"error": error_message},
            severity="high",
        )
        run.status = RunStatus.FAILED.value
        run.error_message = error_message
        run.ended_at = utcnow()
        self.db.commit()

    async def _finalize_run(self, state: GraphState, failed: bool) -> None:
        run: TestRun = self.db.get(TestRun, state["run"].id)
        flows = self.db.query(DiscoveredFlow).filter(DiscoveredFlow.run_id == run.id).all()
        generated_count = 0

        if not flows and state["successful_actions"]:
            flows = [
                self._record_flow(
                    run=run,
                    flow_type="smoke",
                    name="Smoke flow",
                    description="Fallback flow assembled from the successful exploration history.",
                    actions=state["successful_actions"],
                    metadata={"url": state["page"].url, "title": state["page_state"].get("title")},
                )
            ]

        for flow in flows:
            exported = self.exporter.build(run_name=run.config.name, base_url=run.config.target_url, flow_name=flow.name, actions=flow.path)
            stored_path = self.storage.write_generated_test(exported.file_path, exported.content)
            generated = GeneratedTest(
                run_id=run.id,
                flow_id=flow.id,
                name=exported.name,
                file_path=stored_path,
                content=exported.content,
            )
            self.db.add(generated)
            self.db.commit()
            self.db.refresh(generated)
            generated_count += 1

        failure_count = self.db.query(FailureReport).filter(FailureReport.run_id == run.id).count()
        run.status = RunStatus.FAILED.value if failed and failure_count else RunStatus.COMPLETED.value
        summary = {
            "failure_count": failure_count,
            "generated_test_count": generated_count,
            "successful_step_count": len(state["successful_actions"]),
            "discovered_form_count": len(state.get("discovered_forms", set())),
            "attempted_form_variant_count": len(state.get("attempted_form_variants", set())),
            "submitted_form_count": len(state.get("submitted_forms", set())),
            "discovered_url_count": len(state.get("discovered_urls", set())),
            "visited_url_count": len(state.get("visited_urls", set())),
            "bug_report_count": failure_count,
        }
        if failure_count and run.status == RunStatus.COMPLETED.value:
            summary["status_note"] = "Completed with findings"
        run.summary = summary
        run.ended_at = utcnow()
        self.db.commit()

        await self._close_runtime(state)

    async def _close_runtime(self, state: GraphState) -> None:
        browser = state.get("browser")
        playwright = state.get("playwright")
        if browser is not None:
            await browser.close()
        if playwright is not None:
            await playwright.stop()
