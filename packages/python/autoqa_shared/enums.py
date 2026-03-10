from enum import StrEnum


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class StepStatus(StrEnum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class RiskLevel(StrEnum):
    SAFE = "safe"
    RISKY = "risky"
    DESTRUCTIVE = "destructive"


class FailureType(StrEnum):
    ASSERTION = "assertion"
    CONSOLE = "console"
    NETWORK = "network"
    ACCESSIBILITY = "accessibility"
    UNCERTAINTY = "uncertainty"
    EXPLORATION = "exploration"


class ArtifactType(StrEnum):
    SCREENSHOT = "screenshot"
    TRACE = "trace"
    REPORT = "report"
