"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { formatDistanceToNow } from "date-fns";
import { ArrowRight, ChevronDown, History, Pause, Play, Search, Square, Trash2 } from "lucide-react";

import { api } from "../lib/api";
import type { GeneratedTest, RunListItem } from "../lib/types";
import {
  canDeleteRun,
  canPauseRun,
  canResumeRun,
  canStopRun,
  displayRunStatus,
  isActiveRun,
  runStatusMessage as describeRunStatus,
} from "../lib/run-status";
import { Panel } from "./panel";
import { StatusBadge } from "./status-badge";

type ConfigFormState = {
  name: string;
  target_url: string;
  login_url: string;
  username: string;
  password: string;
  username_selector: string;
  password_selector: string;
  submit_selector: string;
  max_steps: number;
  max_duration_seconds: string;
  safe_mode: boolean;
  headless: boolean;
  allowed_domains: string;
  include_paths: string;
  exclude_paths: string;
  crud_mode: boolean;
  crud_create: boolean;
  crud_read: boolean;
  crud_update: boolean;
  crud_delete: boolean;
  allow_destructive_actions: boolean;
  notes: string;
};

const DEFAULT_FORM: ConfigFormState = {
  name: "",
  target_url: "",
  login_url: "",
  username: "",
  password: "",
  username_selector: "",
  password_selector: "",
  submit_selector: "",
  max_steps: 1000,
  max_duration_seconds: "",
  safe_mode: true,
  headless: true,
  allowed_domains: "",
  include_paths: "",
  exclude_paths: "",
  crud_mode: false,
  crud_create: true,
  crud_read: true,
  crud_update: true,
  crud_delete: false,
  allow_destructive_actions: false,
  notes: "",
};

export function Dashboard() {
  const router = useRouter();
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [tests, setTests] = useState<GeneratedTest[]>([]);
  const [activeTab, setActiveTab] = useState<"launch" | "activity">("launch");
  const [historySearch, setHistorySearch] = useState("");
  const [historyFilter, setHistoryFilter] = useState("all");
  const [isLoadingHistory, setIsLoadingHistory] = useState(true);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [form, setForm] = useState<ConfigFormState>(DEFAULT_FORM);
  const [isLaunching, setIsLaunching] = useState(false);
  const [busyRunId, setBusyRunId] = useState<string | null>(null);
  const [isClearingHistory, setIsClearingHistory] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [confirmAction, setConfirmAction] = useState<
    | { type: "stop"; run: RunListItem }
    | { type: "delete"; run: RunListItem }
    | { type: "clear-history" }
    | null
  >(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    function restoreTab() {
      setActiveTab(window.location.hash === "#history" ? "activity" : "launch");
    }
    restoreTab();
    window.addEventListener("hashchange", restoreTab);
    return () => window.removeEventListener("hashchange", restoreTab);
  }, []);

  async function loadDashboard() {
    const [runData, testData] = await Promise.all([api.listRuns(), api.listGeneratedTests()]);
    setRuns(runData);
    setTests(testData.slice(0, 6));
  }

  useEffect(() => {
    let active = true;

    async function load() {
      try {
        const [runData, testData] = await Promise.all([api.listRuns(), api.listGeneratedTests()]);
        if (!active) {
          return;
        }
        setRuns(runData);
        setTests(testData.slice(0, 6));
        setHistoryError(null);
      } catch (loadError) {
        if (active) {
          setHistoryError(loadError instanceof Error ? loadError.message : "Failed to load run history.");
        }
      } finally {
        if (active) setIsLoadingHistory(false);
      }
    }

    void load();
    const interval = window.setInterval(() => void load(), 5_000);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, []);

  const totals = useMemo(() => {
    return {
      totalRuns: runs.length,
      activeRuns: runs.filter((run) => isActiveRun(run)).length,
      failedRuns: runs.filter((run) => run.status === "failed").length,
    };
  }, [runs]);

  const search = historySearch.trim().toLowerCase();
  const visibleRuns = runs.filter((run) =>
    (historyFilter === "all" || (historyFilter === "active" ? isActiveRun(run) : run.status === historyFilter)) &&
    (!search || [run.config_name, run.target_url].some((value) => value.toLowerCase().includes(search))),
  );

  function showTab(tab: "launch" | "activity") {
    setError(null);
    setFeedback(null);
    setActiveTab(tab);
    window.history.replaceState(window.history.state, "", tab === "activity" ? "#history" : window.location.pathname + window.location.search);
  }

  async function launchRun(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsLaunching(true);
    setError(null);
    setFeedback(null);

    try {
      let target: URL;
      try {
        target = new URL(form.target_url.trim());
      } catch {
        throw new Error("Enter a valid target URL, such as https://staging.example.com.");
      }
      if (!["http:", "https:"].includes(target.protocol) || target.username || target.password) {
        throw new Error("Enter an HTTP or HTTPS target URL without embedded credentials.");
      }
      const created = await api.createConfig({
        ...form,
        name: form.name.trim() || target.host,
        target_url: target.href,
        max_duration_seconds: form.max_duration_seconds ? Number(form.max_duration_seconds) : null,
        login_url: form.login_url || null,
        username: form.username || null,
        password: form.password || null,
        username_selector: form.username_selector || null,
        password_selector: form.password_selector || null,
        submit_selector: form.submit_selector || null,
        allowed_domains: form.allowed_domains
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        include_paths: form.include_paths
          .split(/[\n,]+/)
          .map((item) => item.trim())
          .filter(Boolean),
        exclude_paths: form.exclude_paths
          .split(/[\n,]+/)
          .map((item) => item.trim())
          .filter(Boolean),
        crud_mode: form.crud_mode,
        crud_actions: [
          form.crud_create ? "create" : null,
          form.crud_read ? "read" : null,
          form.crud_update ? "update" : null,
          form.crud_delete ? "delete" : null,
        ].filter((item): item is string => item !== null),
        allow_destructive_actions: form.allow_destructive_actions,
      });

      const run = await api.createRun(created.id);
      router.push(`/runs/${run.id}`);
    } catch (launchError) {
      setError(launchError instanceof Error ? launchError.message : "Failed to launch run.");
    } finally {
      setIsLaunching(false);
    }
  }

  async function handleRunAction(run: RunListItem, action: "pause" | "resume" | "stop" | "delete") {
    setBusyRunId(run.id);
    setError(null);
    setFeedback(actionMessage(action, "pending"));
    try {
      let updatedRun: Pick<RunListItem, "status" | "control_state"> | null = null;
      if (action === "pause") {
        updatedRun = await api.pauseRun(run.id);
      } else if (action === "resume") {
        updatedRun = await api.resumeRun(run.id);
      } else if (action === "stop") {
        updatedRun = await api.stopRun(run.id);
      } else {
        await api.deleteRun(run.id);
      }
      await loadDashboard();
      setFeedback(actionMessage(action, "done", updatedRun));
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "Failed to update run.");
      setFeedback(null);
    } finally {
      setBusyRunId(null);
    }
  }

  async function handleClearHistory() {
    setIsClearingHistory(true);
    setError(null);
    setFeedback("Clearing recent session history...");
    try {
      const result = await api.clearRunHistory();
      await loadDashboard();
      setFeedback(result.deleted_runs > 0 ? `Deleted ${result.deleted_runs} inactive run${result.deleted_runs === 1 ? "" : "s"}.` : "There was no inactive history to clear.");
    } catch (clearError) {
      setError(clearError instanceof Error ? clearError.message : "Failed to clear history.");
      setFeedback(null);
    } finally {
      setIsClearingHistory(false);
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-7xl flex-col gap-6">
      <section className="flex flex-wrap items-end justify-between gap-5">
        <div>
          <h1 className="font-display text-4xl font-semibold tracking-tight text-ink">Exploration runs</h1>
          <p className="mt-2 text-sm text-slate/75">Start a browser test, check its progress, and review what it found.</p>
        </div>
        <div className="flex flex-wrap gap-x-5 gap-y-2 text-sm text-slate/75">
          <span><strong className="text-ink">{totals.totalRuns}</strong> total</span>
          <span><strong className="text-ink">{totals.activeRuns}</strong> active</span>
          <span><strong className="text-rose-800">{totals.failedRuns}</strong> failed</span>
        </div>
      </section>
      <nav aria-label="Run workspace" className="flex flex-wrap gap-2 border-b border-slate/15 pb-3">
        <TabButton label="New run" active={activeTab === "launch"} onClick={() => showTab("launch")} />
        <TabButton label="Run history" active={activeTab === "activity"} onClick={() => showTab("activity")} />
      </nav>

      {activeTab === "launch" ? (
        <section className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]">
          <Panel>
            <h2 className="font-display text-2xl font-semibold text-ink">Start a run</h2>
            <p className="mt-2 text-sm leading-6 text-slate/75">Enter the page where AutoQA should begin exploring.</p>
            <form className="mt-5 grid gap-4" onSubmit={launchRun} onInvalidCapture={(event) => {
              const settings = (event.target as HTMLElement).closest("details");
              if (settings) settings.open = true;
            }}>
              <Field label="Target URL">
                <input type="url" required maxLength={2048} value={form.target_url} onChange={(event) => setForm({ ...form, target_url: event.target.value })} placeholder="https://staging.example.com" className={inputClass} />
              </Field>
              <Field label="Run name (optional)">
                <input maxLength={255} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="Defaults to the target hostname" className={inputClass} />
              </Field>

              <FormSection
                title="Sign-in details"
                description="Add a login page or test account for pages that require sign-in."
              >
                <div className="grid gap-4 md:grid-cols-2">
                  <Field label="Login URL">
                    <input type="url" maxLength={2048} value={form.login_url} onChange={(event) => setForm({ ...form, login_url: event.target.value })} className={inputClass} />
                  </Field>
                  <Field label="Submit selector">
                    <input value={form.submit_selector} onChange={(event) => setForm({ ...form, submit_selector: event.target.value })} placeholder="button[type='submit']" className={inputClass} />
                  </Field>
                  <Field label="Username">
                    <input value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })} className={inputClass} />
                  </Field>
                  <Field label="Password">
                    <input type="password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} className={inputClass} />
                  </Field>
                  <Field label="Username selector">
                    <input value={form.username_selector} onChange={(event) => setForm({ ...form, username_selector: event.target.value })} placeholder="input[name='email']" className={inputClass} />
                  </Field>
                  <Field label="Password selector">
                    <input value={form.password_selector} onChange={(event) => setForm({ ...form, password_selector: event.target.value })} placeholder="input[type='password']" className={inputClass} />
                  </Field>
                </div>
              </FormSection>

              <FormSection
                title="Pages and actions"
                description="Limit where AutoQA can go and choose which record operations to test."
              >
                <div className="mb-4">
                  <Field label="Additional allowed domains">
                    <input value={form.allowed_domains} onChange={(event) => setForm({ ...form, allowed_domains: event.target.value })} placeholder="admin.example.com, accounts.example.com" className={inputClass} />
                  </Field>
                </div>
                <div className="grid gap-4 lg:grid-cols-2">
                  <Field label="Included paths">
                    <textarea
                      value={form.include_paths}
                      onChange={(event) => setForm({ ...form, include_paths: event.target.value })}
                      rows={4}
                      placeholder={"/customer-credit-note/*\n/sales-invoice/*"}
                      className={`${inputClass} min-h-28`}
                    />
                  </Field>
                  <Field label="Excluded paths">
                    <textarea
                      value={form.exclude_paths}
                      onChange={(event) => setForm({ ...form, exclude_paths: event.target.value })}
                      rows={4}
                      placeholder={"/reports/*\n/settings/audit-log"}
                      className={`${inputClass} min-h-28`}
                    />
                  </Field>
                </div>
                <div className="mt-4">
                  <Toggle label="Test record operations (CRUD)" checked={form.crud_mode} onChange={(checked) => setForm({ ...form, crud_mode: checked })} />
                </div>
                {form.crud_mode ? (
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <Toggle label="Create checks" checked={form.crud_create} onChange={(checked) => setForm({ ...form, crud_create: checked })} />
                  <Toggle label="Read checks" checked={form.crud_read} onChange={(checked) => setForm({ ...form, crud_read: checked })} />
                  <Toggle label="Update checks" checked={form.crud_update} onChange={(checked) => setForm({ ...form, crud_update: checked })} />
                  <Toggle label="Delete checks" checked={form.crud_delete} onChange={(checked) => setForm({ ...form, crud_delete: checked })} />
                  <Toggle
                    label="Allow destructive actions"
                    checked={form.allow_destructive_actions}
                    onChange={(checked) => setForm({ ...form, allow_destructive_actions: checked })}
                  />
                  </div>
                ) : null}
              </FormSection>

              <FormSection
                title="Run limits and browser"
                description="Set a step budget or time limit, change safe mode, or show the browser."
              >
                <div className="grid items-stretch gap-3 sm:grid-cols-2">
                  <NumberSetting
                    label="Max steps"
                    value={form.max_steps}
                    min={1}
                    max={1000}
                    onChange={(value) => setForm({ ...form, max_steps: value })}
                  />
                  <Toggle label="Safe mode" checked={form.safe_mode} onChange={(checked) => setForm({ ...form, safe_mode: checked })} />
                  <Toggle label="Headless browser" checked={form.headless} onChange={(checked) => setForm({ ...form, headless: checked })} />
                  <label className="block text-sm font-medium text-slate">
                    Time limit in seconds (optional)
                    <input
                      type="number"
                      min={10}
                      max={86400}
                      value={form.max_duration_seconds}
                      onChange={(event) => setForm({ ...form, max_duration_seconds: event.target.value })}
                      className={inputClass}
                    />
                  </label>
                </div>
                <div className="mt-4">
                  <Field label="Notes (optional)">
                    <textarea value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} rows={2} className={inputClass} />
                  </Field>
                </div>
              </FormSection>

              {error ? <p role="alert" className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-800">{error}</p> : null}
              {feedback ? (
                <p aria-live="polite" className="rounded-2xl bg-cyan-50 px-4 py-3 text-sm text-cyan-900">
                  {feedback}
                </p>
              ) : null}

              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate/10 pt-4">
                <p className="text-sm text-slate/75">
                  {form.safe_mode ? "Safe mode on" : "Safe mode off"} · {form.max_steps} step limit
                </p>
                <button type="submit" disabled={isLaunching} className="inline-flex items-center gap-2 rounded-xl bg-ink px-5 py-3 text-sm font-semibold text-white hover:bg-slate disabled:cursor-not-allowed disabled:opacity-60">
                  <Play className="h-4 w-4" aria-hidden="true" />
                  {isLaunching ? "Starting run…" : "Start run"}
                </button>
              </div>
            </form>
          </Panel>
          <Panel>
            <div className="flex items-center gap-2">
              <History className="h-5 w-5 text-slate/70" aria-hidden="true" />
              <h2 className="font-display text-xl font-semibold text-ink">Recent runs</h2>
            </div>
            {isLoadingHistory ? <p className="mt-4 text-sm text-slate/75" role="status">Loading runs…</p> :
              historyError ? <p className="mt-4 text-sm text-rose-800" role="status">{historyError}</p> :
              runs.length ? (
                <ul className="mt-3 divide-y divide-slate/10">
                  {runs.slice(0, 4).map((run) => (
                    <li key={run.id}>
                      <Link href={`/runs/${run.id}`} className="flex items-center justify-between gap-3 py-3">
                        <span className="min-w-0"><span className="block break-words text-sm font-semibold">{run.config_name}</span><span className="mt-1 block text-xs text-slate/75">{formatDistanceToNow(new Date(run.created_at), { addSuffix: true })}</span></span>
                        <StatusBadge value={displayRunStatus(run)} />
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : <p className="mt-4 text-sm leading-6 text-slate/75">Your first run will appear here with its status and results.</p>}
            <button type="button" onClick={() => showTab("activity")} className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-slate hover:underline">
              View run history <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </button>
          </Panel>
        </section>
      ) : null}

      {activeTab === "activity" ? (
        <section className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]">
        <Panel>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="font-display text-2xl font-semibold text-ink">Run history</h2>
            <button
              type="button"
              onClick={() => setConfirmAction({ type: "clear-history" })}
              disabled={isClearingHistory || runs.every((run) => isActiveRun(run))}
              className="inline-flex items-center gap-2 rounded-full border border-slate/10 bg-white px-4 py-2 text-sm font-semibold text-slate transition hover:border-slate/20 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Trash2 className="h-4 w-4" />
              {isClearingHistory ? "Clearing..." : "Clear history"}
            </button>
          </div>
          <div className="mt-5 grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto]">
            <label className="relative block">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate/60" aria-hidden="true" />
              <input type="search" aria-label="Search runs" className={`${inputClass} pl-9`} value={historySearch} onChange={(event) => setHistorySearch(event.target.value)} placeholder="Search by run name or URL" />
            </label>
            <select aria-label="Filter runs by status" className={inputClass} value={historyFilter} onChange={(event) => setHistoryFilter(event.target.value)}>
              <option value="all">All statuses</option>
              <option value="active">Active</option>
              <option value="completed">Completed</option>
              <option value="failed">Failed</option>
              <option value="stopped">Stopped</option>
            </select>
          </div>
          {error || historyError ? <p role="alert" className="mt-4 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-800">{error ?? historyError}</p> : null}
          {feedback ? <p role="status" className="mt-4 rounded-xl bg-mist px-4 py-3 text-sm text-slate">{feedback}</p> : null}
          <div className="mt-5 space-y-3">
            {isLoadingHistory ? (
              <p role="status" className="text-sm text-slate/75">Loading runs…</p>
            ) : visibleRuns.length === 0 ? (
              <EmptyState title={runs.length ? "No matching runs" : "No runs yet"} description={runs.length ? "Try a different search or status." : "Start a run to see its progress and results here."} />
            ) : (
              visibleRuns.map((run) => {
                const status = displayRunStatus(run);
                const statusMessage = describeRunStatus(run);
                return (
                <article key={run.id} className="overflow-hidden rounded-[24px] border border-slate/10 bg-sand/50 p-4 transition hover:border-slate/20 hover:bg-white">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <Link href={`/runs/${run.id}`} className="min-w-0 flex-1">
                      <p className="font-display text-lg font-semibold text-ink">{run.config_name}</p>
                      <p className="overflow-anywhere mt-1 text-sm text-slate/70">{run.target_url}</p>
                    </Link>
                    <StatusBadge value={status} />
                  </div>
                  <div className="mt-4 grid gap-3 text-sm text-slate/75 sm:grid-cols-3">
                    <span>Created {formatDistanceToNow(new Date(run.created_at), { addSuffix: true })}</span>
                    <span>Max steps {run.max_steps}</span>
                    <span>Failures {String((run.summary.failure_count as number | undefined) ?? 0)}</span>
                  </div>
                  {statusMessage ? (
                    <p className="mt-4 rounded-2xl bg-white/80 px-4 py-3 text-sm text-slate/80">{statusMessage}</p>
                  ) : null}
                  <div className="mt-4 flex flex-wrap gap-2">
                    <Link href={`/runs/${run.id}`} className="inline-flex items-center gap-2 rounded-full bg-ink px-4 py-2 text-sm font-semibold text-white">
                      View results
                    </Link>
                    {canPauseRun(run) ? (
                      <RunActionButton
                        icon={<Pause className="h-4 w-4" />}
                        label={busyRunId === run.id ? "Pausing..." : "Pause"}
                        disabled={busyRunId === run.id}
                        onClick={() => void handleRunAction(run, "pause")}
                      />
                    ) : null}
                    {canResumeRun(run) ? (
                      <RunActionButton
                        icon={<Play className="h-4 w-4" />}
                        label={busyRunId === run.id ? "Resuming..." : "Resume"}
                        disabled={busyRunId === run.id}
                        onClick={() => void handleRunAction(run, "resume")}
                      />
                    ) : null}
                    {canStopRun(run) ? (
                      <RunActionButton
                        icon={<Square className="h-4 w-4" />}
                        label={busyRunId === run.id ? "Stopping..." : "Stop"}
                        disabled={busyRunId === run.id}
                        onClick={() => setConfirmAction({ type: "stop", run })}
                      />
                    ) : null}
                    {canDeleteRun(run) ? (
                      <RunActionButton
                        icon={<Trash2 className="h-4 w-4" />}
                        label={busyRunId === run.id ? "Deleting..." : "Delete"}
                        disabled={busyRunId === run.id}
                        onClick={() => setConfirmAction({ type: "delete", run })}
                      />
                    ) : null}
                  </div>
                </article>
              )})
            )}
          </div>
        </Panel>

        <Panel>
          <div>
            <h2 className="font-display text-xl font-semibold text-ink">Recent Playwright exports</h2>
          </div>
          <div className="mt-6 space-y-4">
            {tests.length === 0 ? (
              <EmptyState title="No specs exported yet" description="Successful flows will appear here as readable Playwright files." />
            ) : (
              tests.map((test) => (
                <Link key={test.id} href={`/tests/${test.id}`} className="block overflow-hidden rounded-[24px] border border-slate/10 bg-sand/50 p-4 transition hover:-translate-y-0.5 hover:border-slate/20 hover:bg-white">
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <p className="font-display text-lg font-semibold text-ink">{test.name}</p>
                      <p className="overflow-anywhere mt-1 text-sm text-slate/70">{test.file_path}</p>
                    </div>
                    <ArrowRight className="h-4 w-4 shrink-0 text-slate/70" aria-hidden="true" />
                  </div>
                </Link>
              ))
            )}
          </div>
        </Panel>
        </section>
      ) : null}
      {confirmAction ? (
        <ConfirmDialog
          title={confirmTitle(confirmAction)}
          description={confirmDescription(confirmAction)}
          confirmLabel={confirmButtonLabel(confirmAction)}
          busy={isClearingHistory || (confirmAction.type !== "clear-history" && busyRunId === confirmAction.run.id)}
          onCancel={() => setConfirmAction(null)}
          onConfirm={async () => {
            const pending = confirmAction;
            setConfirmAction(null);
            if (pending.type === "clear-history") {
              await handleClearHistory();
              return;
            }
            await handleRunAction(pending.run, pending.type);
          }}
        />
      ) : null}
    </main>
  );
}

function TabButton({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`rounded-lg px-4 py-2.5 text-sm font-semibold transition ${
        active
          ? "bg-ink text-white"
          : "text-slate hover:bg-slate/10"
      }`}
    >
      {label}
    </button>
  );
}

function FormSection({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <details className="group rounded-xl border border-slate/15">
      <summary className="flex cursor-pointer list-none items-start justify-between gap-3 rounded-xl px-4 py-3.5 hover:bg-sand/60 [&::-webkit-details-marker]:hidden">
        <span>
          <span className="block text-sm font-semibold text-ink">{title}</span>
          <span className="mt-1 block text-sm leading-5 text-slate/75">{description}</span>
        </span>
        <ChevronDown className="mt-0.5 h-4 w-4 shrink-0 text-slate/75 transition-transform group-open:rotate-180" aria-hidden="true" />
      </summary>
      <div className="border-t border-slate/10 p-4">{children}</div>
    </details>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block min-w-0">
      <span className="mb-2 block text-sm font-medium text-slate/80">{label}</span>
      {children}
    </label>
  );
}

function NumberSetting({
  label,
  value,
  min,
  max,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="flex min-h-[88px] w-full items-center justify-between gap-4 rounded-xl border border-slate/10 bg-sand/50 px-4 py-3 transition focus-within:border-ember focus-within:bg-white">
      <span className="min-w-0">
        <span className="block text-sm font-semibold text-ink">{label}</span>
        <span className="mt-1 block text-xs uppercase tracking-[0.18em] text-slate/55">
          {min}-{max}
        </span>
      </span>
      <input
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="h-11 w-24 shrink-0 rounded-lg border border-slate/10 bg-white px-3 text-right text-sm font-semibold text-ink outline-none transition focus:border-ember"
      />
    </label>
  );
}

function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      aria-pressed={checked}
      className={`flex min-h-[88px] w-full items-center justify-between rounded-xl border px-4 py-3 text-left transition focus:outline-none focus:ring-2 focus:ring-ember/30 ${
        checked
          ? "border-ink/15 bg-white shadow-sm"
          : "border-slate/10 bg-sand/60 hover:border-slate/20 hover:bg-white/80"
      }`}
    >
      <span className="min-w-0 pr-3">
        <span className="block text-sm font-semibold text-ink">{label}</span>
        <span className="mt-1 block text-xs uppercase tracking-[0.18em] text-slate/55">{checked ? "Enabled" : "Disabled"}</span>
      </span>
      <span
        className={`relative inline-flex h-7 w-12 shrink-0 items-center rounded-full p-1 transition ${
          checked ? "bg-ink" : "bg-slate/20"
        }`}
      >
        <span
          className={`h-5 w-5 rounded-full bg-white shadow-sm transition-transform ${
            checked ? "translate-x-5" : "translate-x-0"
          }`}
        />
      </span>
    </button>
  );
}

function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="rounded-[24px] border border-dashed border-slate/15 bg-sand/35 px-5 py-8 text-center">
      <p className="font-display text-xl font-semibold text-ink">{title}</p>
      <p className="mt-2 text-sm text-slate/75">{description}</p>
    </div>
  );
}

function RunActionButton({
  icon,
  label,
  disabled,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className="inline-flex items-center gap-2 rounded-full border border-slate/10 bg-white px-4 py-2 text-sm font-semibold text-slate transition hover:border-slate/20 disabled:cursor-not-allowed disabled:opacity-50"
    >
      {icon}
      {label}
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

function actionMessage(
  action: "pause" | "resume" | "stop" | "delete",
  phase: "pending" | "done",
  run?: Pick<RunListItem, "status" | "control_state"> | null,
): string {
  if (phase === "pending") {
    const messages = {
      pause: "Pausing run...",
      resume: "Resuming run...",
      stop: "Stopping run...",
      delete: "Deleting run...",
    };
    return messages[action];
  }
  if (action === "pause") {
    return run?.control_state === "pause_requested" ? "Pause requested." : "Run paused.";
  }
  if (action === "resume") {
    return "Run resumed.";
  }
  if (action === "stop") {
    return run?.status === "stopped" ? "Run stopped." : "Stop requested.";
  }
  return "Run deleted.";
}

function confirmTitle(
  action:
    | { type: "stop"; run: RunListItem }
    | { type: "delete"; run: RunListItem }
    | { type: "clear-history" },
): string {
  if (action.type === "stop") {
    return "Stop this run?";
  }
  if (action.type === "delete") {
    return "Delete this run?";
  }
  return "Clear inactive history?";
}

function confirmDescription(
  action:
    | { type: "stop"; run: RunListItem }
    | { type: "delete"; run: RunListItem }
    | { type: "clear-history" },
): string {
  if (action.type === "stop") {
    return `The run "${action.run.config_name}" will stop at the next safe checkpoint.`;
  }
  if (action.type === "delete") {
    return `The run "${action.run.config_name}" and its recorded history will be removed from the dashboard.`;
  }
  return "All completed, failed, and stopped runs will be removed from recent session history.";
}

function confirmButtonLabel(
  action:
    | { type: "stop"; run: RunListItem }
    | { type: "delete"; run: RunListItem }
    | { type: "clear-history" },
): string {
  if (action.type === "stop") {
    return "Stop run";
  }
  if (action.type === "delete") {
    return "Delete run";
  }
  return "Clear history";
}

const inputClass =
  "w-full rounded-xl border border-slate/10 bg-sand/50 px-4 py-3 text-sm text-ink outline-none transition placeholder:text-slate/45 focus:border-ember focus:bg-white focus:ring-2 focus:ring-ember/15";
