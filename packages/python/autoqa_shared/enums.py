try:
    from enum import StrEnum
except ImportError:
    from enum import Enum

    class StrEnum(str, Enum):
        pass


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class RunControlState(StrEnum):
    PAUSE_REQUESTED = "pause_requested"
    PAUSED = "paused"
    STOP_REQUESTED = "stop_requested"


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
