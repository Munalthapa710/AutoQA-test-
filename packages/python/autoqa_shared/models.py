import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def uuid_str() -> str:
    return str(uuid.uuid4())


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class TestConfig(Base, TimestampMixin):
    __tablename__ = "test_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    target_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    login_url: Mapped[str | None] = mapped_column(String(2048))
    username: Mapped[str | None] = mapped_column(String(255))
    password: Mapped[str | None] = mapped_column(String(255))
    username_selector: Mapped[str | None] = mapped_column(String(255))
    password_selector: Mapped[str | None] = mapped_column(String(255))
    submit_selector: Mapped[str | None] = mapped_column(String(255))
    headless: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    safe_mode: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_steps: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    allowed_domains: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    runs: Mapped[list["TestRun"]] = relationship(back_populates="config")


class TestRun(Base, TimestampMixin):
    __tablename__ = "test_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    config_id: Mapped[str] = mapped_column(ForeignKey("test_configs.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    control_state: Mapped[str | None] = mapped_column(String(32))
    max_steps: Mapped[int] = mapped_column(Integer, nullable=False)
    safe_mode: Mapped[bool] = mapped_column(Boolean, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    run_settings: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)

    config: Mapped["TestConfig"] = relationship(back_populates="runs")
    steps: Mapped[list["RunStep"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    flows: Mapped[list["DiscoveredFlow"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    failures: Mapped[list["FailureReport"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    generated_tests: Mapped[list["GeneratedTest"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    artifacts: Mapped[list["Artifact"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class RunStep(Base):
    __tablename__ = "run_steps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    run_id: Mapped[str] = mapped_column(ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    node_name: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    page_title: Mapped[str | None] = mapped_column(String(512))
    url: Mapped[str | None] = mapped_column(String(2048))
    element_label: Mapped[str | None] = mapped_column(String(512))
    locator: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    run: Mapped["TestRun"] = relationship(back_populates="steps")
    artifacts: Mapped[list["Artifact"]] = relationship(back_populates="step")


class DiscoveredFlow(Base, TimestampMixin):
    __tablename__ = "discovered_flows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    run_id: Mapped[str] = mapped_column(ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    flow_type: Mapped[str] = mapped_column(String(64), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    flow_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    run: Mapped["TestRun"] = relationship(back_populates="flows")


class FailureReport(Base, TimestampMixin):
    __tablename__ = "failure_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    run_id: Mapped[str] = mapped_column(ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False)
    step_id: Mapped[str | None] = mapped_column(ForeignKey("run_steps.id", ondelete="SET NULL"))
    failure_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), default="medium", nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    run: Mapped["TestRun"] = relationship(back_populates="failures")


class GeneratedTest(Base, TimestampMixin):
    __tablename__ = "generated_tests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    run_id: Mapped[str] = mapped_column(ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False)
    flow_id: Mapped[str | None] = mapped_column(ForeignKey("discovered_flows.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(32), default="typescript", nullable=False)

    run: Mapped["TestRun"] = relationship(back_populates="generated_tests")
    flow: Mapped["DiscoveredFlow"] = relationship(foreign_keys=[flow_id])


class Artifact(Base, TimestampMixin):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    run_id: Mapped[str] = mapped_column(ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False)
    step_id: Mapped[str | None] = mapped_column(ForeignKey("run_steps.id", ondelete="SET NULL"))
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    run: Mapped["TestRun"] = relationship(back_populates="artifacts")
    step: Mapped["RunStep"] = relationship(back_populates="artifacts")
