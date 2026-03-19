"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { formatDistanceToNow } from "date-fns";
import { ExternalLink, FileCode2, Image as ImageIcon, Link2, Pause, Play, ScrollText, Square, Trash2, TriangleAlert } from "lucide-react";

import { api, artifactUrl, generatedTestFileUrl } from "../lib/api";
import type { Artifact, DiscoveredFlow, FailureReport, GeneratedTest, RunDetail as RunDetailType, RunStep } from "../lib/types";
import { Panel } from "./panel";
import { StatusBadge } from "./status-badge";

export function RunDetail({ runId }: { runId: string }) {
  const router = useRouter();
  const [run, setRun] = useState<RunDetailType | null>(null);
  const [steps, setSteps] = useState<RunStep[]>([]);
  const [flows, setFlows] = useState<DiscoveredFlow[]>([]);
  const [failures, setFailures] = useState<FailureReport[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [tests, setTests] = useState<GeneratedTest[]>([]);
  const [isMutating, setIsMutating] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [confirmAction, setConfirmAction] = useState<"stop" | "delete" | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function load() {
      try {
        const [runData, stepData, flowData, failureData, artifactData, generatedTests] = await Promise.all([
          api.getRun(runId),
          api.getRunSteps(runId),
          api.getRunFlows(runId),
          api.getRunFailures(runId),
          api.getRunArtifacts(runId),
          api.listGeneratedTests(),
        ]);
        if (!active) {
          return;
        }
        setRun(runData);
        setSteps(stepData);
        setFlows(flowData);
        setFailures(failureData);
        setArtifacts(artifactData);
        setTests(generatedTests.filter((entry) => entry.run_id === runId));
      } catch (loadError) {
        if (active) {
          setError(loadError instanceof Error ? loadError.message : "Failed to load run details.");
        }
      }
    }

    void load();
    const interval = window.setInterval(() => {
      if (run?.status === "completed" || run?.status === "failed" || run?.status === "stopped") {
        return;
      }
      void load();
    }, 3_000);

    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, [runId, run?.status]);

  const screenshots = useMemo(() => artifacts.filter((artifact) => artifact.type === "screenshot"), [artifacts]);
  const secondaryArtifacts = useMemo(
    () => artifacts.filter((artifact) => artifact.type !== "screenshot"),
    [artifacts],
  );
  const stepById = useMemo(() => new Map(steps.map((step) => [step.id, step])), [steps]);
  const reportArtifactsByFailureId = useMemo(() => {
    const grouped = new Map<string, Artifact[]>();
    for (const artifact of artifacts) {
      if (artifact.type !== "report") {
        continue;
      }
      const metadata = getRecord(artifact.artifact_metadata);
      const failureId = metadata ? getString(metadata.failure_id) : null;
      if (!failureId) {
        continue;
      }
      grouped.set(failureId, [...(grouped.get(failureId) ?? []), artifact]);
    }
    return grouped;
  }, [artifacts]);
  const screenshotsByStepId = useMemo(() => {
    const grouped = new Map<string, Artifact[]>();
    for (const artifact of screenshots) {
      if (!artifact.step_id) {
        continue;
      }
      grouped.set(artifact.step_id, [...(grouped.get(artifact.step_id) ?? []), artifact]);
    }
    return grouped;
  }, [screenshots]);
  const summary = useMemo(() => {
    const runSummary = getRecord(run?.summary);
    return {
      discoveredForms: getNumber(runSummary?.discovered_form_count) ?? 0,
      attemptedVariants: getNumber(runSummary?.attempted_form_variant_count) ?? 0,
      submittedForms: getNumber(runSummary?.submitted_form_count) ?? 0,
      discoveredPages: getNumber(runSummary?.discovered_url_count) ?? 0,
      visitedPages: getNumber(runSummary?.visited_url_count) ?? 0,
      bugReports: getNumber(runSummary?.bug_report_count) ?? failures.length,
    };
  }, [failures.length, run?.summary]);

  async function handleRunAction(action: "pause" | "resume" | "stop" | "delete") {
    if (!run) {
      return;
    }
    setIsMutating(true);
    setError(null);
    setFeedback(runActionMessage(action, "pending"));
    try {
      if (action === "pause") {
        const nextRun = await api.pauseRun(run.id);
        setRun({ ...run, ...nextRun });
      } else if (action === "resume") {
        const nextRun = await api.resumeRun(run.id);
        setRun({ ...run, ...nextRun });
      } else if (action === "stop") {
        const nextRun = await api.stopRun(run.id);
        setRun({ ...run, ...nextRun });
      } else {
        await api.deleteRun(run.id);
        router.push("/");
        return;
      }
      setFeedback(runActionMessage(action, "done"));
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "Failed to update run.");
      setFeedback(null);
    } finally {
      setIsMutating(false);
    }
  }

  if (error) {
    return (
      <main className="mx-auto max-w-7xl">
        <Panel>
          <p className="text-sm text-rose-700">{error}</p>
        </Panel>
      </main>
    );
  }

  if (!run) {
    return (
      <main className="mx-auto max-w-7xl">
        <Panel>
          <p className="text-sm text-slate/70">Loading run details...</p>
        </Panel>
      </main>
    );
  }

  return (
    <main className="mx-auto flex w-full max-w-7xl flex-col gap-6">
      <section className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <Panel>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="font-mono text-xs uppercase tracking-[0.34em] text-slate/60">Run detail</p>
              <h1 className="overflow-anywhere mt-2 font-display text-3xl font-semibold text-ink">{run.config.name}</h1>
              <p className="overflow-anywhere mt-2 text-sm text-slate/75">{run.config.target_url}</p>
            </div>
            <StatusBadge value={run.status} />
          </div>

          <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            <KeyStat title="Steps" value={String(steps.length)} />
            <KeyStat title="Pages" value={String(summary.visitedPages)} />
            <KeyStat title="Flows" value={String(flows.length)} />
            <KeyStat title="Form submits" value={String(summary.submittedForms)} />
            <KeyStat title="Variants" value={String(summary.attemptedVariants)} />
            <KeyStat title="Findings" value={String(summary.bugReports)} />
            <KeyStat title="Specs" value={String(tests.length)} />
          </div>

          <div className="mt-6 grid gap-3 text-sm text-slate/75 sm:grid-cols-2 xl:grid-cols-3">
            <InfoPill label="Created" value={formatDistanceToNow(new Date(run.created_at), { addSuffix: true })} />
            <InfoPill label="Safe mode" value={run.safe_mode ? "enabled" : "disabled"} />
            <InfoPill label="Max steps" value={String(run.max_steps)} />
            <InfoPill label="Headless" value={String((run.run_settings.headless as boolean | undefined) ?? true)} />
            <InfoPill label="Forms discovered" value={String(summary.discoveredForms)} />
            <InfoPill label="Forms submitted" value={String(summary.submittedForms)} />
            <InfoPill label="Variants tested" value={String(summary.attemptedVariants)} />
            <InfoPill label="Pages discovered" value={String(summary.discoveredPages)} />
            <InfoPill label="Pages visited" value={String(summary.visitedPages)} />
          </div>

          {run.error_message ? <p className="mt-4 rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{run.error_message}</p> : null}
          {feedback ? (
            <p aria-live="polite" className="mt-4 rounded-2xl bg-cyan-50 px-4 py-3 text-sm text-cyan-900">
              {feedback}
            </p>
          ) : null}
          {runDetailStatusMessage(run) ? <p className="mt-4 rounded-2xl bg-white/80 px-4 py-3 text-sm text-slate/80">{runDetailStatusMessage(run)}</p> : null}

          <div className="mt-6 flex flex-wrap gap-3">
            <a href={run.config.target_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 rounded-full bg-ink px-5 py-3 text-sm font-semibold text-white">
              Open target
              <ExternalLink className="h-4 w-4" />
            </a>
            {run.status === "running" ? (
              <ActionButton disabled={isMutating} onClick={() => void handleRunAction("pause")}>
                <Pause className="h-4 w-4" />
                {isMutating ? "Pausing..." : "Pause run"}
              </ActionButton>
            ) : null}
            {run.status === "paused" ? (
              <ActionButton disabled={isMutating} onClick={() => void handleRunAction("resume")}>
                <Play className="h-4 w-4" />
                {isMutating ? "Resuming..." : "Resume run"}
              </ActionButton>
            ) : null}
            {["queued", "running", "paused"].includes(run.status) ? (
              <ActionButton disabled={isMutating} onClick={() => setConfirmAction("stop")}>
                <Square className="h-4 w-4" />
                {isMutating ? "Stopping..." : "Stop run"}
              </ActionButton>
            ) : null}
            {!["queued", "running", "paused"].includes(run.status) ? (
              <ActionButton disabled={isMutating} onClick={() => setConfirmAction("delete")}>
                <Trash2 className="h-4 w-4" />
                {isMutating ? "Deleting..." : "Delete run"}
              </ActionButton>
            ) : null}
            <Link href="/" className="inline-flex items-center gap-2 rounded-full border border-slate/10 bg-white px-5 py-3 text-sm font-semibold text-slate">
              Back to dashboard
              <Link2 className="h-4 w-4" />
            </Link>
          </div>
        </Panel>

        <Panel>
          <div className="flex items-center gap-3">
            <ScrollText className="h-5 w-5 text-slate" />
            <div>
              <p className="font-mono text-xs uppercase tracking-[0.34em] text-slate/60">Live step log</p>
              <h2 className="mt-1 font-display text-2xl font-semibold text-ink">Execution trace</h2>
            </div>
          </div>
          <div className="mt-6 max-h-[520px] space-y-4 overflow-y-auto pr-2">
            {steps.length === 0 ? (
              <p className="text-sm text-slate/70">No steps recorded yet.</p>
            ) : (
              steps.map((step) => (
                <article key={step.id} className="overflow-hidden rounded-[24px] border border-slate/10 bg-sand/50 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <p className="font-mono text-xs uppercase tracking-[0.22em] text-slate/60">
                        Step {step.step_index} - {step.node_name}
                      </p>
                      <h3 className="overflow-anywhere mt-1 font-display text-xl font-semibold text-ink">{step.action}</h3>
                    </div>
                    <div className="flex gap-2">
                      <StatusBadge value={step.status} />
                      <StatusBadge value={step.risk_level} />
                    </div>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-slate/80">{step.rationale}</p>
                  <div className="mt-4 grid gap-2 text-sm text-slate/75 sm:grid-cols-2">
                    <span className="overflow-anywhere">Element: {step.element_label ?? "n/a"}</span>
                    <span>Confidence: {(step.confidence * 100).toFixed(0)}%</span>
                    <span className="overflow-anywhere">Page: {step.page_title ?? "Untitled"}</span>
                    <span className="overflow-anywhere">URL: {step.url ?? "n/a"}</span>
                  </div>
                  {"error" in step.details ? (
                    <p className="mt-4 rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{String(step.details.error)}</p>
                  ) : null}
                </article>
              ))
            )}
          </div>
        </Panel>
      </section>

      <section className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
        <Panel className="relative overflow-hidden">
          <div className="absolute -right-10 top-0 h-28 w-28 rounded-full bg-ember/10 blur-3xl" />
          <div className="relative">
            <p className="font-mono text-xs uppercase tracking-[0.34em] text-slate/60">Coverage map</p>
            <h2 className="mt-2 font-display text-2xl font-semibold text-ink">What this run actually covered</h2>
            <div className="mt-5 grid gap-3 md:grid-cols-3">
              <CoverageTile
                title="Page discovery"
                value={`${summary.visitedPages}/${summary.discoveredPages || summary.visitedPages}`}
                description="Visited pages out of the same-domain pages the explorer discovered."
              />
              <CoverageTile
                title="Form coverage"
                value={`${summary.submittedForms}/${summary.discoveredForms || summary.submittedForms}`}
                description="Forms successfully submitted out of the forms surfaced during exploration."
              />
              <CoverageTile
                title="Variant checks"
                value={String(summary.attemptedVariants)}
                description="Invalid and valid submission paths attempted across discovered forms."
              />
            </div>
          </div>
        </Panel>

        <Panel className="relative overflow-hidden bg-white/90">
          <div className="absolute bottom-0 right-0 h-32 w-32 rounded-full bg-cyan-300/15 blur-3xl" />
          <div className="relative">
            <p className="font-mono text-xs uppercase tracking-[0.34em] text-slate/60">How to read this</p>
            <h2 className="mt-2 font-display text-2xl font-semibold text-ink">Tester handoff</h2>
            <div className="mt-5 space-y-3">
              <GuidanceRow
                title="Coverage first"
                description="Use the coverage map to see whether the run actually reached the pages and forms you expected."
              />
              <GuidanceRow
                title="Findings second"
                description="Each issue card below includes a readable bug title, actual result, expected result, and reproduction path."
              />
              <GuidanceRow
                title="Evidence last"
                description="Attach the linked screenshots, trace, and markdown/json reports directly to ClickUp or your bug tracker."
              />
            </div>
          </div>
        </Panel>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <Panel>
          <div className="flex items-center gap-3">
            <FileCode2 className="h-5 w-5 text-slate" />
            <div>
              <p className="font-mono text-xs uppercase tracking-[0.34em] text-slate/60">Discovered flows</p>
              <h2 className="mt-1 font-display text-2xl font-semibold text-ink">Reusable coverage ({flows.length})</h2>
            </div>
          </div>
          <div className="mt-6 max-h-[520px] space-y-4 overflow-y-auto pr-2">
            {flows.length === 0 ? (
              <p className="text-sm text-slate/70">No flows have been captured yet.</p>
            ) : (
              flows.map((flow) => {
                const linkedTest = tests.find((test) => test.flow_id === flow.id);
                return (
                  <article key={flow.id} className="overflow-hidden rounded-[24px] border border-slate/10 bg-sand/50 p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <p className="font-mono text-xs uppercase tracking-[0.22em] text-slate/60">{flow.flow_type}</p>
                        <h3 className="overflow-anywhere mt-1 font-display text-xl font-semibold text-ink">{flow.name}</h3>
                      </div>
                      <StatusBadge value={flow.success ? "completed" : "failed"} />
                    </div>
                    <p className="mt-3 text-sm leading-6 text-slate/80">{flow.description}</p>
                    <p className="mt-3 text-sm text-slate/70">Actions captured: {flow.path.length}</p>
                    {linkedTest ? (
                      <div className="mt-4 flex flex-wrap gap-3">
                        <Link href={`/tests/${linkedTest.id}`} className="inline-flex items-center gap-2 rounded-full bg-ink px-4 py-2 text-sm font-semibold text-white">
                          View generated spec
                        </Link>
                        <a href={generatedTestFileUrl(linkedTest.file_path)} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 rounded-full border border-slate/10 bg-white px-4 py-2 text-sm font-semibold text-slate">
                          Download file
                        </a>
                      </div>
                    ) : null}
                  </article>
                );
              })
            )}
          </div>
        </Panel>

        <Panel>
          <div className="flex items-center gap-3">
            <TriangleAlert className="h-5 w-5 text-slate" />
            <div>
              <p className="font-mono text-xs uppercase tracking-[0.34em] text-slate/60">Detected issues</p>
              <h2 className="mt-1 font-display text-2xl font-semibold text-ink">Failures and findings ({failures.length})</h2>
            </div>
          </div>
          <div className="mt-6 max-h-[520px] space-y-4 overflow-y-auto pr-2">
            {failures.length === 0 ? (
              <p className="text-sm text-slate/70">No failures recorded yet.</p>
            ) : (
              failures.map((failure) => {
                const bugReport = getBugReport(failure.evidence);
                const linkedStep = failure.step_id ? stepById.get(failure.step_id) ?? null : null;
                const reportArtifacts = reportArtifactsByFailureId.get(failure.id) ?? [];
                const failureScreenshots = failure.step_id ? screenshotsByStepId.get(failure.step_id) ?? [] : [];
                const primaryScreenshot = failureScreenshots[0] ?? null;
                const displayTitle = bugReport?.title ?? failure.title;
                const moduleLabel = formatModuleLabel(bugReport?.pageUrl ?? linkedStep?.url ?? run.config.target_url);

                return (
                  <article key={failure.id} className="overflow-hidden rounded-[24px] border border-rose-200 bg-rose-50/70 p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <p className="font-mono text-xs uppercase tracking-[0.22em] text-rose-700/70">{failure.failure_type}</p>
                        <h3 className="overflow-anywhere mt-1 font-display text-xl font-semibold text-rose-950">{displayTitle}</h3>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {bugReport?.assessment ? <StatusBadge value={bugReport.assessment} /> : null}
                        <StatusBadge value={failure.severity} />
                      </div>
                    </div>

                    {bugReport?.summary ? (
                      <p className="mt-3 rounded-2xl bg-white/80 px-4 py-3 text-sm leading-6 text-rose-950">{bugReport.summary}</p>
                    ) : (
                      <p className="mt-3 text-sm leading-6 text-rose-900/80">{failure.description}</p>
                    )}

                    <div className="mt-4 rounded-[22px] border border-rose-200/70 bg-white/80 px-4 py-4">
                      <p className="font-mono text-xs uppercase tracking-[0.22em] text-rose-700/70">Bug report</p>
                      <p className="overflow-anywhere mt-2 font-display text-lg font-semibold text-rose-950">{displayTitle}</p>
                      <p className="mt-2 text-sm leading-6 text-rose-950/85">
                        Copy these details into your bug tracker. The wording is already simplified for QA handoff.
                      </p>
                    </div>

                    <div className="mt-4 grid gap-3 sm:grid-cols-2">
                      <IssueField label="Bug title" value={displayTitle} />
                      <IssueField label="Module" value={moduleLabel} />
                      <IssueField label="Environment" value="Web Application" />
                      <IssueField label="Page" value={bugReport?.pageUrl ?? linkedStep?.url ?? "n/a"} />
                      <IssueField
                        label="Step"
                        value={linkedStep ? `${linkedStep.step_index} - ${linkedStep.action}` : "n/a"}
                      />
                      <IssueField label="Element" value={linkedStep?.element_label ?? "n/a"} />
                      <IssueField label="Assessment" value={bugReport?.assessment ?? "Needs review"} />
                    </div>

                    {bugReport?.bugDescription ? <IssueBlock title="Bug description" value={bugReport.bugDescription} /> : null}

                    {primaryScreenshot ? (
                      <details className="mt-4 overflow-hidden rounded-[22px] border border-rose-200/70 bg-white/80">
                        <summary className="cursor-pointer px-4 py-3 text-sm font-semibold text-rose-950">
                          Toggle failure screenshot
                        </summary>
                        <a
                          href={artifactUrl(primaryScreenshot.file_path)}
                          target="_blank"
                          rel="noreferrer"
                          className="block border-t border-rose-100"
                        >
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={artifactUrl(primaryScreenshot.file_path)}
                            alt={primaryScreenshot.file_path}
                            className="h-64 w-full object-cover object-top"
                          />
                          <div className="overflow-anywhere border-t border-rose-100 px-4 py-3 text-sm text-rose-950/80">
                            {primaryScreenshot.file_path}
                          </div>
                        </a>
                      </details>
                    ) : null}

                    {bugReport?.reproductionSteps.length ? <IssueSteps title="Steps to Reproduce" items={bugReport.reproductionSteps} /> : null}
                    {bugReport?.actualResult ? <IssueBlock title="Actual Result" value={bugReport.actualResult} /> : null}
                    {bugReport?.expectedResult ? <IssueBlock title="Expected Result" value={bugReport.expectedResult} /> : null}
                    <PageDiffBlock pageDiff={getPageDiff(failure.evidence)} />
                    {bugReport?.reason ? <IssueBlock title="Why this matters" value={bugReport.reason} /> : null}

                    {reportArtifacts.length ? (
                      <div className="mt-4 flex flex-wrap gap-3">
                        {reportArtifacts.map((artifact) => (
                          <a
                            key={artifact.id}
                            href={artifactUrl(artifact.file_path)}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex items-center gap-2 rounded-full border border-rose-200 bg-white px-4 py-2 text-sm font-semibold text-rose-950"
                          >
                            {artifactLabel(artifact)}
                            <ExternalLink className="h-4 w-4" />
                          </a>
                        ))}
                      </div>
                    ) : null}

                    <details className="mt-4 rounded-2xl bg-white/70 px-4 py-3">
                      <summary className="cursor-pointer text-sm font-semibold text-rose-950">Raw evidence</summary>
                      <pre className="mt-3 max-w-full overflow-x-auto font-mono text-xs leading-6 text-rose-900/80">
                        {JSON.stringify(stripBugReport(failure.evidence), null, 2)}
                      </pre>
                    </details>
                  </article>
                );
              })
            )}
          </div>
        </Panel>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <Panel>
          <div className="flex items-center gap-3">
            <ImageIcon className="h-5 w-5 text-slate" />
            <div>
              <p className="font-mono text-xs uppercase tracking-[0.34em] text-slate/60">Artifacts</p>
              <h2 className="mt-1 font-display text-2xl font-semibold text-ink">Screenshots, traces, and reports ({artifacts.length})</h2>
            </div>
          </div>
          <div className="mt-6 max-h-[520px] overflow-y-auto pr-2">
            <div className="grid gap-4 md:grid-cols-2">
            {screenshots.length === 0 ? (
              <p className="text-sm text-slate/70">No screenshots captured yet.</p>
            ) : (
              screenshots.map((artifact) => (
                <a key={artifact.id} href={artifactUrl(artifact.file_path)} target="_blank" rel="noreferrer" className="overflow-hidden rounded-[24px] border border-slate/10 bg-sand/50 transition hover:border-slate/20">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={artifactUrl(artifact.file_path)} alt={artifact.file_path} className="h-52 w-full object-cover" />
                  <div className="overflow-anywhere p-4 text-sm text-slate/75">{artifact.file_path}</div>
                </a>
              ))
            )}
            </div>
          </div>
          {secondaryArtifacts.length > 0 ? (
            <div className="mt-6 flex max-h-40 flex-wrap gap-3 overflow-y-auto pr-2">
              {secondaryArtifacts.map((artifact) => (
                <a key={artifact.id} href={artifactUrl(artifact.file_path)} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 rounded-full border border-slate/10 bg-white px-4 py-2 text-sm font-semibold text-slate">
                  {artifactLabel(artifact)}
                  <ExternalLink className="h-4 w-4" />
                </a>
              ))}
            </div>
          ) : null}
        </Panel>

        <Panel>
          <div className="flex items-center gap-3">
            <FileCode2 className="h-5 w-5 text-slate" />
            <div>
              <p className="font-mono text-xs uppercase tracking-[0.34em] text-slate/60">Generated tests</p>
              <h2 className="mt-1 font-display text-2xl font-semibold text-ink">Readable Playwright output ({tests.length})</h2>
            </div>
          </div>
          <div className="mt-6 max-h-[520px] space-y-4 overflow-y-auto pr-2">
            {tests.length === 0 ? (
              <p className="text-sm text-slate/70">The worker has not exported any specs for this run yet.</p>
            ) : (
              tests.map((test) => (
                <article key={test.id} className="overflow-hidden rounded-[24px] border border-slate/10 bg-sand/50 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <h3 className="font-display text-xl font-semibold text-ink">{test.name}</h3>
                      <p className="overflow-anywhere mt-1 text-sm text-slate/70">{test.file_path}</p>
                    </div>
                    <Link href={`/tests/${test.id}`} className="inline-flex items-center gap-2 rounded-full bg-ink px-4 py-2 text-sm font-semibold text-white">
                      View code
                    </Link>
                  </div>
                  <pre className="mt-4 overflow-x-auto rounded-2xl bg-ink px-4 py-3 font-mono text-xs leading-6 text-sand">
                    {test.content.split("\n").slice(0, 10).join("\n")}
                  </pre>
                </article>
              ))
            )}
          </div>
        </Panel>
      </section>
      {confirmAction ? (
        <ConfirmDialog
          title={confirmAction === "stop" ? "Stop this run?" : "Delete this run?"}
          description={
            confirmAction === "stop"
              ? "The worker will stop this run at the next safe checkpoint."
              : "This run and its recorded history will be removed from the dashboard."
          }
          confirmLabel={confirmAction === "stop" ? "Stop run" : "Delete run"}
          busy={isMutating}
          onCancel={() => setConfirmAction(null)}
          onConfirm={async () => {
            const nextAction = confirmAction;
            setConfirmAction(null);
            await handleRunAction(nextAction);
          }}
        />
      ) : null}
    </main>
  );
}

function ActionButton({
  children,
  disabled,
  onClick,
}: {
  children: React.ReactNode;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className="inline-flex items-center gap-2 rounded-full border border-slate/10 bg-white px-5 py-3 text-sm font-semibold text-slate transition hover:border-slate/20 disabled:cursor-not-allowed disabled:opacity-50"
    >
      {children}
    </button>
  );
}

function ConfirmDialog({
  title,
  description,
  confirmLabel,
  busy,
  onCancel,
  onConfirm,
}: {
  title: string;
  description: string;
  confirmLabel: string;
  busy?: boolean;
  onCancel: () => void;
  onConfirm: () => void | Promise<void>;
}) {
  return (
    <div aria-modal="true" role="dialog" className="fixed inset-0 z-50 flex items-center justify-center bg-ink/45 px-4">
      <div className="w-full max-w-md rounded-[28px] border border-slate/10 bg-white p-6 shadow-2xl">
        <p className="font-mono text-xs uppercase tracking-[0.26em] text-slate/55">Confirm action</p>
        <h3 className="mt-3 font-display text-2xl font-semibold text-ink">{title}</h3>
        <p className="mt-3 text-sm leading-6 text-slate/75">{description}</p>
        <div className="mt-6 flex flex-wrap gap-3">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="inline-flex items-center gap-2 rounded-full border border-slate/10 bg-sand/60 px-4 py-2 text-sm font-semibold text-slate transition hover:border-slate/20 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => void onConfirm()}
            disabled={busy}
            className="inline-flex items-center gap-2 rounded-full bg-ink px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? "Working..." : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

function runActionMessage(action: "pause" | "resume" | "stop" | "delete", phase: "pending" | "done"): string {
  const messages = {
    pause: { pending: "Pause requested. The run will wait at the next safe checkpoint.", done: "Run paused." },
    resume: { pending: "Resuming run...", done: "Run resumed." },
    stop: { pending: "Stop requested. The run will stop at the next safe checkpoint.", done: "Run stopped." },
    delete: { pending: "Deleting run...", done: "Run deleted." },
  };
  return messages[action][phase];
}

function runDetailStatusMessage(run: RunDetailType): string | null {
  if (run.status === "paused") {
    return "Paused by user. Resume to continue from the current checkpoint.";
  }
  if (run.status === "running") {
    return "Run is actively exploring the app.";
  }
  if (run.status === "queued") {
    return "Run is waiting for the worker to pick it up.";
  }
  if (run.status === "stopped") {
    return run.error_message ? null : "Stopped by user.";
  }
  const statusNote = typeof run.summary.status_note === "string" ? run.summary.status_note : null;
  return statusNote;
}

function KeyStat({ title, value }: { title: string; value: string }) {
  return (
    <div className="min-w-0 rounded-[22px] border border-slate/10 bg-sand/50 px-4 py-4">
      <p className="overflow-anywhere font-mono text-[10px] uppercase tracking-[0.18em] text-slate/60">{title}</p>
      <p className="mt-2 overflow-anywhere font-display text-3xl font-semibold leading-none text-ink">{value}</p>
    </div>
  );
}

function InfoPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[22px] border border-slate/10 bg-sand/50 px-4 py-3">
      <p className="font-mono text-xs uppercase tracking-[0.22em] text-slate/60">{label}</p>
      <p className="overflow-anywhere mt-1 text-sm font-medium text-slate/80">{value}</p>
    </div>
  );
}

function IssueField({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[20px] border border-rose-200/70 bg-white/70 px-4 py-3">
      <p className="font-mono text-xs uppercase tracking-[0.22em] text-rose-700/70">{label}</p>
      <p className="overflow-anywhere mt-1 text-sm font-medium text-rose-950/90">{value}</p>
    </div>
  );
}

function IssueBlock({ title, value }: { title: string; value: string }) {
  return (
    <div className="mt-4 rounded-[22px] border border-rose-200/70 bg-white/75 px-4 py-4">
      <p className="font-mono text-xs uppercase tracking-[0.22em] text-rose-700/70">{title}</p>
      <p className="mt-2 text-sm leading-6 text-rose-950/90">{value}</p>
    </div>
  );
}

function IssueSteps({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="mt-4 rounded-[22px] border border-rose-200/70 bg-white/75 px-4 py-4">
      <p className="font-mono text-xs uppercase tracking-[0.22em] text-rose-700/70">{title}</p>
      <ol className="mt-3 space-y-2 text-sm leading-6 text-rose-950/90">
        {items.map((item, index) => (
          <li key={`${title}-${index}`}>{index + 1}. {formatReproductionStep(item)}</li>
        ))}
      </ol>
    </div>
  );
}

function PageDiffBlock({ pageDiff }: { pageDiff: PageDiff | null }) {
  if (!pageDiff) {
    return null;
  }

  const hasChanges =
    pageDiff.urlChanged ||
    pageDiff.titleChanged ||
    pageDiff.afterValidationMessages.length > 0 ||
    pageDiff.afterAlerts.length > 0 ||
    pageDiff.buttonStateChanges.length > 0 ||
    pageDiff.newVisibleText.length > 0 ||
    pageDiff.removedVisibleText.length > 0;

  if (!hasChanges) {
    return null;
  }

  return (
    <div className="mt-4 rounded-[22px] border border-rose-200/70 bg-white/75 px-4 py-4">
      <p className="font-mono text-xs uppercase tracking-[0.22em] text-rose-700/70">What changed on the page</p>
      <div className="mt-3 space-y-3 text-sm leading-6 text-rose-950/90">
        {pageDiff.urlChanged ? (
          <IssueChangeRow label="URL changed" value={`${pageDiff.beforeUrl ?? "n/a"} -> ${pageDiff.afterUrl ?? "n/a"}`} />
        ) : null}
        {pageDiff.titleChanged ? (
          <IssueChangeRow label="Title changed" value={`${pageDiff.beforeTitle ?? "n/a"} -> ${pageDiff.afterTitle ?? "n/a"}`} />
        ) : null}
        {pageDiff.afterValidationMessages.length > 0 ? (
          <IssueList title="Validation shown" items={pageDiff.afterValidationMessages} />
        ) : null}
        {pageDiff.afterAlerts.length > 0 ? <IssueList title="Messages shown" items={pageDiff.afterAlerts} /> : null}
        {pageDiff.buttonStateChanges.length > 0 ? (
          <IssueList
            title="Button state changes"
            items={pageDiff.buttonStateChanges.map(
              (change) =>
                `${change.label}: ${formatButtonState(change.beforeDisabled)} -> ${formatButtonState(change.afterDisabled)}`,
            )}
          />
        ) : null}
        {pageDiff.newVisibleText.length > 0 ? <IssueList title="New text shown" items={pageDiff.newVisibleText} /> : null}
      </div>
    </div>
  );
}

function IssueChangeRow({ label, value }: { label: string; value: string }) {
  return (
    <p>
      <span className="font-semibold text-rose-950">{label}:</span> {value}
    </p>
  );
}

function IssueList({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <p className="font-semibold text-rose-950">{title}</p>
      <ul className="mt-1 space-y-1">
        {items.map((item, index) => (
          <li key={`${title}-${index}`} className="overflow-anywhere">- {item}</li>
        ))}
      </ul>
    </div>
  );
}

function CoverageTile({ title, value, description }: { title: string; value: string; description: string }) {
  return (
    <div className="rounded-[24px] border border-slate/10 bg-sand/50 px-4 py-4">
      <p className="font-mono text-xs uppercase tracking-[0.22em] text-slate/60">{title}</p>
      <p className="mt-2 font-display text-3xl font-semibold text-ink">{value}</p>
      <p className="mt-2 text-sm leading-6 text-slate/75">{description}</p>
    </div>
  );
}

function GuidanceRow({ title, description }: { title: string; description: string }) {
  return (
    <div className="rounded-[22px] border border-slate/10 bg-sand/40 px-4 py-4">
      <p className="font-display text-lg font-semibold text-ink">{title}</p>
      <p className="mt-1 text-sm leading-6 text-slate/75">{description}</p>
    </div>
  );
}

type BugReport = {
  title: string | null;
  summary: string | null;
  bugDescription: string | null;
  actualResult: string | null;
  expectedResult: string | null;
  assessment: string | null;
  pageUrl: string | null;
  reason: string | null;
  reproductionSteps: string[];
};

type PageDiff = {
  urlChanged: boolean;
  titleChanged: boolean;
  beforeUrl: string | null;
  afterUrl: string | null;
  beforeTitle: string | null;
  afterTitle: string | null;
  newVisibleText: string[];
  removedVisibleText: string[];
  beforeValidationMessages: string[];
  afterValidationMessages: string[];
  beforeAlerts: string[];
  afterAlerts: string[];
  buttonStateChanges: Array<{
    label: string;
    beforeDisabled: boolean | null;
    afterDisabled: boolean | null;
  }>;
};

function getBugReport(evidence: Record<string, unknown>): BugReport | null {
  const report = getRecord(evidence.bug_report);
  if (!report) {
    return null;
  }
  return {
    title: getString(report.title),
    summary: getString(report.summary),
    bugDescription: getString(report.bug_description),
    actualResult: getString(report.actual_result),
    expectedResult: getString(report.expected_result),
    assessment: getString(report.assessment),
    pageUrl: getString(report.page_url),
    reason: getString(report.reason),
    reproductionSteps: getStringArray(report.reproduction_steps),
  };
}

function getPageDiff(evidence: Record<string, unknown>): PageDiff | null {
  const diff = getRecord(evidence.page_diff);
  if (!diff) {
    return null;
  }

  const buttonStateChanges = Array.isArray(diff.button_state_changes)
    ? diff.button_state_changes
        .map((entry) => getRecord(entry))
        .filter((entry): entry is Record<string, unknown> => entry !== null)
        .map((entry) => ({
          label: getString(entry.label) ?? "Unnamed button",
          beforeDisabled: typeof entry.before_disabled === "boolean" ? entry.before_disabled : null,
          afterDisabled: typeof entry.after_disabled === "boolean" ? entry.after_disabled : null,
        }))
    : [];

  return {
    urlChanged: Boolean(diff.url_changed),
    titleChanged: Boolean(diff.title_changed),
    beforeUrl: getString(diff.before_url),
    afterUrl: getString(diff.after_url),
    beforeTitle: getString(diff.before_title),
    afterTitle: getString(diff.after_title),
    newVisibleText: getStringArray(diff.new_visible_text),
    removedVisibleText: getStringArray(diff.removed_visible_text),
    beforeValidationMessages: getStringArray(diff.before_validation_messages),
    afterValidationMessages: getStringArray(diff.after_validation_messages),
    beforeAlerts: getStringArray(diff.before_alerts),
    afterAlerts: getStringArray(diff.after_alerts),
    buttonStateChanges,
  };
}

function stripBugReport(evidence: Record<string, unknown>) {
  const { bug_report: _bugReport, ...rest } = evidence;
  return rest;
}

function artifactLabel(artifact: Artifact) {
  const metadata = getRecord(artifact.artifact_metadata);
  const format = metadata ? getString(metadata.format) : null;
  return format ? `${artifact.type} - ${format}` : artifact.type;
}

function getRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function getString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function getNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function getStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
}

function formatModuleLabel(url: string | null | undefined): string {
  if (!url) {
    return "Current Flow";
  }

  try {
    const parsed = new URL(url);
    const segments = parsed.pathname
      .split("/")
      .filter(Boolean)
      .filter((segment) => segment.toLowerCase() !== "admin")
      .map((segment) =>
        segment
          .replace(/[-_]+/g, " ")
          .replace(/\b\w/g, (char) => char.toUpperCase()),
      );

    if (segments.length === 0) {
      return "Dashboard";
    }

    return segments.join(" -> ");
  } catch {
    return "Current Flow";
  }
}

function formatReproductionStep(step: string): string {
  const trimmed = step.trim();

  const openTargetMatch = trimmed.match(/^Open the target application at (.+)\.$/i);
  if (openTargetMatch) {
    return "Open the application.";
  }

  const signInMatch = trimmed.match(/^Sign in through (.+) with a valid test account\.$/i);
  if (signInMatch) {
    return "Sign in with a valid test account.";
  }

  const openUrlMatch = trimmed.match(/^(Open|Navigate to) (https?:\/\/[^\s]+)\.?$/i);
  if (openUrlMatch) {
    return `Go to ${formatModuleLabel(openUrlMatch[2])}.`;
  }

  const observeMatch = trimmed.match(/^Observe the issue titled '(.+)'\.$/i);
  if (observeMatch) {
    return `Check the result: ${observeMatch[1]}.`;
  }

  return trimmed
    .replace(/^Submit /i, "Click ")
    .replace(/^Open /i, "Go to ")
    .replace(/\.$/, "") + ".";
}

function formatButtonState(value: boolean | null): string {
  if (value === true) {
    return "disabled";
  }
  if (value === false) {
    return "enabled";
  }
  return "unknown";
}
