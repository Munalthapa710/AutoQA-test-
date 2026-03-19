from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TestConfigCreate(BaseModel):
    name: str
    target_url: str
    login_url: str | None = None
    username: str | None = None
    password: str | None = None
    username_selector: str | None = None
    password_selector: str | None = None
    submit_selector: str | None = None
    headless: bool = True
    safe_mode: bool = True
    max_steps: int = Field(default=1000, ge=1, le=1000)
    allowed_domains: list[str] = Field(default_factory=list)
    notes: str | None = None


class TestConfigRead(BaseSchema):
    id: str
    name: str
    target_url: str
    login_url: str | None
    username: str | None
    password: str | None
    username_selector: str | None
    password_selector: str | None
    submit_selector: str | None
    headless: bool
    safe_mode: bool
    max_steps: int
    allowed_domains: list[str]
    notes: str | None
    created_at: datetime
    updated_at: datetime


class RunCreate(BaseModel):
    config_id: str


class RunDeleteRead(BaseModel):
    deleted_runs: int


class TestRunRead(BaseSchema):
    id: str
    config_id: str
    status: str
    max_steps: int
    safe_mode: bool
    started_at: datetime | None
    ended_at: datetime | None
    run_settings: dict[str, Any]
    summary: dict[str, Any]
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class RunListItemRead(TestRunRead):
    config_name: str
    target_url: str


class RunStepRead(BaseSchema):
    id: str
    run_id: str
    step_index: int
    node_name: str
    action: str
    rationale: str
    page_title: str | None
    url: str | None
    element_label: str | None
    locator: dict[str, Any]
    risk_level: str
    status: str
    confidence: float
    details: dict[str, Any]
    started_at: datetime
    finished_at: datetime | None


class DiscoveredFlowRead(BaseSchema):
    id: str
    run_id: str
    name: str
    flow_type: str
    success: bool
    description: str
    path: list[dict[str, Any]]
    flow_metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class FailureReportRead(BaseSchema):
    id: str
    run_id: str
    step_id: str | None
    failure_type: str
    severity: str
    title: str
    description: str
    evidence: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ArtifactRead(BaseSchema):
    id: str
    run_id: str
    step_id: str | None
    type: str
    file_path: str
    mime_type: str
    artifact_metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class GeneratedTestRead(BaseSchema):
    id: str
    run_id: str
    flow_id: str | None
    name: str
    file_path: str
    content: str
    language: str
    created_at: datetime
    updated_at: datetime


class RunDetailRead(TestRunRead):
    config: TestConfigRead


class HealthRead(BaseModel):
    status: str
    database: str
    redis: str
