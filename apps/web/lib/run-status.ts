import type { Run } from "./types";

type RunLike = Pick<Run, "status" | "control_state" | "error_message" | "summary">;

export type DisplayRunStatus =
  | "queued"
  | "running"
  | "pausing"
  | "paused"
  | "stopping"
  | "completed"
  | "failed"
  | "stopped";

export function displayRunStatus(run: Pick<Run, "status" | "control_state">): DisplayRunStatus {
  if (run.status === "completed" || run.status === "failed" || run.status === "stopped") {
    return run.status;
  }
  if (run.control_state === "stop_requested") {
    return "stopping";
  }
  if (run.control_state === "pause_requested") {
    return "pausing";
  }
  if (run.control_state === "paused" || run.status === "paused") {
    return "paused";
  }
  if (run.status === "running" || run.status === "queued") {
    return run.status;
  }
  return "running";
}

export function canPauseRun(run: Pick<Run, "status" | "control_state">): boolean {
  return run.status === "running" && run.control_state == null;
}

export function canResumeRun(run: Pick<Run, "status" | "control_state">): boolean {
  return run.status === "running" && ["pause_requested", "paused"].includes(run.control_state ?? "");
}

export function canStopRun(run: Pick<Run, "status" | "control_state">): boolean {
  if (run.status === "stopped" || run.status === "completed" || run.status === "failed") {
    return false;
  }
  return run.control_state !== "stop_requested";
}

export function canDeleteRun(run: Pick<Run, "status">): boolean {
  return ["completed", "failed", "stopped"].includes(run.status);
}

export function isActiveRun(run: Pick<Run, "status">): boolean {
  return !canDeleteRun(run);
}

export function runStatusMessage(run: RunLike): string | null {
  if (run.control_state === "pause_requested") {
    return "Pause requested. The run will pause at the next safe checkpoint.";
  }
  if (run.control_state === "paused" || run.status === "paused") {
    return "Paused by user. Resume to continue from the current checkpoint.";
  }
  if (run.control_state === "stop_requested") {
    return "Stop requested. The worker is finishing the current safe checkpoint.";
  }
  if (run.status === "running") {
    return "Run is actively exploring the app.";
  }
  if (run.status === "queued") {
    return "Run is waiting for the worker to pick it up.";
  }
  if (run.status === "stopped") {
    return run.error_message || "Stopped by user.";
  }
  const statusNote = typeof run.summary.status_note === "string" ? run.summary.status_note : null;
  return statusNote;
}
