"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { formatDistanceToNow } from "date-fns";
import { ExternalLink, FileCode2, Image as ImageIcon, Link2, ScrollText, TriangleAlert } from "lucide-react";

import { api, artifactUrl, generatedTestFileUrl } from "../lib/api";
import type { Artifact, DiscoveredFlow, FailureReport, GeneratedTest, RunDetail as RunDetailType, RunStep } from "../lib/types";
import { Panel } from "./panel";
import { StatusBadge } from "./status-badge";

export function RunDetail({ runId }: { runId: string }) {
  const [run, setRun] = useState<RunDetailType | null>(null);
  const [steps, setSteps] = useState<RunStep[]>([]);
  const [flows, setFlows] = useState<DiscoveredFlow[]>([]);
  const [failures, setFailures] = useState<FailureReport[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [tests, setTests] = useState<GeneratedTest[]>([]);
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
      if (run?.status === "completed" || run?.status === "failed") {
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
              <h1 className="mt-2 font-display text-3xl font-semibold text-ink">{run.config.name}</h1>
              <p className="mt-2 text-sm text-slate/75">{run.config.target_url}</p>
            </div>
            <StatusBadge value={run.status} />
          </div>

          <div className="mt-6 grid gap-3 sm:grid-cols-6">
            <KeyStat title="Steps" value={String(steps.length)} />
            <KeyStat title="Pages" value={String(summary.visitedPages)} />
            <KeyStat title="Flows" value={String(flows.length)} />
            <KeyStat title="Form submits" value={String(summary.submittedForms)} />
            <KeyStat title="Variants" value={String(summary.attemptedVariants)} />
            <KeyStat title="Findings" value={String(summary.bugReports)} />
            <KeyStat title="Specs" value={String(tests.length)} />
          </div>

          <div className="mt-6 grid gap-3 text-sm text-slate/75 sm:grid-cols-3">
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

          <div className="mt-6 flex flex-wrap gap-3">
            <a href={run.config.target_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 rounded-full bg-ink px-5 py-3 text-sm font-semibold text-white">
              Open target
              <ExternalLink className="h-4 w-4" />
            </a>
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
                <article key={step.id} className="rounded-[24px] border border-slate/10 bg-sand/50 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="font-mono text-xs uppercase tracking-[0.22em] text-slate/60">
                        Step {step.step_index} · {step.node_name}
                      </p>
                      <h3 className="mt-1 font-display text-xl font-semibold text-ink">{step.action}</h3>
                    </div>
                    <div className="flex gap-2">
                      <StatusBadge value={step.status} />
                      <StatusBadge value={step.risk_level} />
                    </div>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-slate/80">{step.rationale}</p>
                  <div className="mt-4 grid gap-2 text-sm text-slate/75 sm:grid-cols-2">
                    <span>Element: {step.element_label ?? "n/a"}</span>
                    <span>Confidence: {(step.confidence * 100).toFixed(0)}%</span>
                    <span>Page: {step.page_title ?? "Untitled"}</span>
                    <span className="truncate">URL: {step.url ?? "n/a"}</span>
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
              <h2 className="mt-1 font-display text-2xl font-semibold text-ink">Reusable coverage</h2>
            </div>
          </div>
          <div className="mt-6 space-y-4">
            {flows.length === 0 ? (
              <p className="text-sm text-slate/70">No flows have been captured yet.</p>
            ) : (
              flows.map((flow) => {
                const linkedTest = tests.find((test) => test.flow_id === flow.id);
                return (
                  <article key={flow.id} className="rounded-[24px] border border-slate/10 bg-sand/50 p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="font-mono text-xs uppercase tracking-[0.22em] text-slate/60">{flow.flow_type}</p>
                        <h3 className="mt-1 font-display text-xl font-semibold text-ink">{flow.name}</h3>
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
              <h2 className="mt-1 font-display text-2xl font-semibold text-ink">Failures and findings</h2>
            </div>
          </div>
          <div className="mt-6 space-y-4">
            {failures.length === 0 ? (
              <p className="text-sm text-slate/70">No failures recorded yet.</p>
            ) : (
              failures.map((failure) => {
                const bugReport = getBugReport(failure.evidence);
                const linkedStep = failure.step_id ? stepById.get(failure.step_id) ?? null : null;
                const reportArtifacts = reportArtifactsByFailureId.get(failure.id) ?? [];
                const displayTitle = bugReport?.title ?? failure.title;

                return (
                  <article key={failure.id} className="rounded-[24px] border border-rose-200 bg-rose-50/70 p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="font-mono text-xs uppercase tracking-[0.22em] text-rose-700/70">{failure.failure_type}</p>
                        <h3 className="mt-1 font-display text-xl font-semibold text-rose-950">{displayTitle}</h3>
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
                      <p className="font-mono text-xs uppercase tracking-[0.22em] text-rose-700/70">ClickUp handoff</p>
                      <p className="mt-2 font-display text-lg font-semibold text-rose-950">{displayTitle}</p>
                      <p className="mt-2 text-sm leading-6 text-rose-950/85">
                        Use this title and the fields below when filing the issue manually for developers.
                      </p>
                    </div>

                    <div className="mt-4 grid gap-3 sm:grid-cols-2">
                      <IssueField label="Bug title" value={displayTitle} />
                      <IssueField label="Page" value={bugReport?.pageUrl ?? linkedStep?.url ?? "n/a"} />
                      <IssueField
                        label="Step"
                        value={linkedStep ? `${linkedStep.step_index} · ${linkedStep.action}` : "n/a"}
                      />
                      <IssueField label="Element" value={linkedStep?.element_label ?? "n/a"} />
                      <IssueField label="Assessment" value={bugReport?.assessment ?? "Needs review"} />
                    </div>

                    {bugReport?.bugDescription ? <IssueBlock title="Bug description" value={bugReport.bugDescription} /> : null}
                    {bugReport?.actualResult ? <IssueBlock title="Actual result" value={bugReport.actualResult} /> : null}
                    {bugReport?.expectedResult ? <IssueBlock title="Expected result" value={bugReport.expectedResult} /> : null}
                    {bugReport?.reason ? <IssueBlock title="Why this matters" value={bugReport.reason} /> : null}

                    {bugReport?.reproductionSteps.length ? (
                      <div className="mt-4">
                        <p className="font-mono text-xs uppercase tracking-[0.22em] text-rose-700/70">Reproduction path</p>
                        <ol className="mt-3 space-y-2 text-sm leading-6 text-rose-950/85">
                          {bugReport.reproductionSteps.map((item, index) => (
                            <li key={`${failure.id}-${index}`}>{index + 1}. {item}</li>
                          ))}
                        </ol>
                      </div>
                    ) : null}

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
                      <pre className="mt-3 overflow-x-auto font-mono text-xs leading-6 text-rose-900/80">
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
              <h2 className="mt-1 font-display text-2xl font-semibold text-ink">Screenshots, traces, and reports</h2>
            </div>
          </div>
          <div className="mt-6 grid gap-4 md:grid-cols-2">
            {screenshots.length === 0 ? (
              <p className="text-sm text-slate/70">No screenshots captured yet.</p>
            ) : (
              screenshots.map((artifact) => (
                <a key={artifact.id} href={artifactUrl(artifact.file_path)} target="_blank" rel="noreferrer" className="overflow-hidden rounded-[24px] border border-slate/10 bg-sand/50 transition hover:border-slate/20">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={artifactUrl(artifact.file_path)} alt={artifact.file_path} className="h-52 w-full object-cover" />
                  <div className="p-4 text-sm text-slate/75">{artifact.file_path}</div>
                </a>
              ))
            )}
          </div>
          {secondaryArtifacts.length > 0 ? (
            <div className="mt-6 flex flex-wrap gap-3">
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
              <h2 className="mt-1 font-display text-2xl font-semibold text-ink">Readable Playwright output</h2>
            </div>
          </div>
          <div className="mt-6 space-y-4">
            {tests.length === 0 ? (
              <p className="text-sm text-slate/70">The worker has not exported any specs for this run yet.</p>
            ) : (
              tests.map((test) => (
                <article key={test.id} className="rounded-[24px] border border-slate/10 bg-sand/50 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <h3 className="font-display text-xl font-semibold text-ink">{test.name}</h3>
                      <p className="mt-1 text-sm text-slate/70">{test.file_path}</p>
                    </div>
                    <Link href={`/tests/${test.id}`} className="inline-flex items-center gap-2 rounded-full bg-ink px-4 py-2 text-sm font-semibold text-white">
                      View code
                    </Link>
                  </div>
                  <pre className="mt-4 rounded-2xl bg-ink px-4 py-3 font-mono text-xs leading-6 text-sand">
                    {test.content.split("\n").slice(0, 10).join("\n")}
                  </pre>
                </article>
              ))
            )}
          </div>
        </Panel>
      </section>
    </main>
  );
}

function KeyStat({ title, value }: { title: string; value: string }) {
  return (
    <div className="rounded-[22px] border border-slate/10 bg-sand/50 px-4 py-3">
      <p className="font-mono text-xs uppercase tracking-[0.22em] text-slate/60">{title}</p>
      <p className="mt-2 font-display text-3xl font-semibold text-ink">{value}</p>
    </div>
  );
}

function InfoPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[22px] border border-slate/10 bg-sand/50 px-4 py-3">
      <p className="font-mono text-xs uppercase tracking-[0.22em] text-slate/60">{label}</p>
      <p className="mt-1 text-sm font-medium text-slate/80">{value}</p>
    </div>
  );
}

function IssueField({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[20px] border border-rose-200/70 bg-white/70 px-4 py-3">
      <p className="font-mono text-xs uppercase tracking-[0.22em] text-rose-700/70">{label}</p>
      <p className="mt-1 text-sm font-medium text-rose-950/90">{value}</p>
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

function stripBugReport(evidence: Record<string, unknown>) {
  const { bug_report: _bugReport, ...rest } = evidence;
  return rest;
}

function artifactLabel(artifact: Artifact) {
  const metadata = getRecord(artifact.artifact_metadata);
  const format = metadata ? getString(metadata.format) : null;
  return format ? `${artifact.type} · ${format}` : artifact.type;
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
