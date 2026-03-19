"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { formatDistanceToNow } from "date-fns";
import { ArrowRight, Beaker, History, Pause, Play, Sparkles, Square, Trash2 } from "lucide-react";

import { api } from "../lib/api";
import type { GeneratedTest, RunListItem } from "../lib/types";
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
  safe_mode: boolean;
  headless: boolean;
  allowed_domains: string;
  notes: string;
};

const DEFAULT_FORM: ConfigFormState = {
  name: "Full form coverage",
  target_url: "http://localhost:3001",
  login_url: "",
  username: "",
  password: "",
  username_selector: "",
  password_selector: "",
  submit_selector: "",
  max_steps: 1000,
  safe_mode: true,
  headless: true,
  allowed_domains: "",
  notes: "",
};

export function Dashboard() {
  const router = useRouter();
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [tests, setTests] = useState<GeneratedTest[]>([]);
  const [form, setForm] = useState<ConfigFormState>(DEFAULT_FORM);
  const [isLaunching, setIsLaunching] = useState(false);
  const [busyRunId, setBusyRunId] = useState<string | null>(null);
  const [isClearingHistory, setIsClearingHistory] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      } catch (loadError) {
        if (active) {
          setError(loadError instanceof Error ? loadError.message : "Failed to load dashboard data.");
        }
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
      activeRuns: runs.filter((run) => run.status === "running" || run.status === "queued").length,
      failedRuns: runs.filter((run) => run.status === "failed").length,
      generatedTests: tests.length,
    };
  }, [runs, tests]);

  async function launchRun(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsLaunching(true);
    setError(null);

    try {
      const created = await api.createConfig({
        ...form,
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
    try {
      if (action === "pause") {
        await api.pauseRun(run.id);
      } else if (action === "resume") {
        await api.resumeRun(run.id);
      } else if (action === "stop") {
        await api.stopRun(run.id);
      } else {
        await api.deleteRun(run.id);
      }
      await loadDashboard();
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "Failed to update run.");
    } finally {
      setBusyRunId(null);
    }
  }

  async function handleClearHistory() {
    setIsClearingHistory(true);
    setError(null);
    try {
      await api.clearRunHistory();
      await loadDashboard();
    } catch (clearError) {
      setError(clearError instanceof Error ? clearError.message : "Failed to clear history.");
    } finally {
      setIsClearingHistory(false);
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-7xl flex-col gap-6">
      <section className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <Panel className="relative overflow-hidden">
          <div className="absolute right-0 top-0 h-32 w-32 rounded-full bg-ember/15 blur-3xl" />
          <div className="absolute bottom-0 left-8 h-28 w-28 rounded-full bg-cyan-300/20 blur-3xl" />
          <div className="relative">
            <p className="font-mono text-xs uppercase tracking-[0.34em] text-slate/60">Agentic Web QA</p>
            <h1 className="mt-3 max-w-2xl font-display text-4xl font-semibold tracking-tight text-ink sm:text-5xl">
              Systematically discover pages, exercise forms, and turn failures into readable bug reports.
            </h1>
            <p className="mt-4 max-w-2xl text-sm leading-6 text-slate/80 sm:text-base">
              This dashboard is built for QA. It walks same-domain navigation, opens visible create and edit flows, tests invalid and valid form submissions, records every step, and keeps screenshots, traces, and downloadable bug reports in one place.
            </p>
            <div className="mt-8 grid gap-3 sm:grid-cols-4">
              <Metric title="Runs" value={String(totals.totalRuns)} icon={<History className="h-4 w-4" />} />
              <Metric title="Active" value={String(totals.activeRuns)} icon={<Play className="h-4 w-4" />} />
              <Metric title="Failures" value={String(totals.failedRuns)} icon={<Beaker className="h-4 w-4" />} />
              <Metric title="Specs" value={String(totals.generatedTests)} icon={<Sparkles className="h-4 w-4" />} />
            </div>
          </div>
        </Panel>

        <Panel>
          <div className="flex items-center justify-between">
            <div>
              <p className="font-mono text-xs uppercase tracking-[0.34em] text-slate/60">Launch Run</p>
              <h2 className="mt-2 font-display text-2xl font-semibold text-ink">Run configuration</h2>
            </div>
            <StatusBadge value={form.safe_mode ? "safe" : "risky"} />
          </div>

          <form className="mt-6 grid gap-4" onSubmit={launchRun}>
            <FormSection
              eyebrow="Scope"
              title="Target and navigation"
              description="Point the run at the app entry page and keep the domain list tight so the explorer stays on the product under test."
            >
              <div className="grid gap-4 md:grid-cols-2">
                <Field label="Name">
                  <input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} className={inputClass} />
                </Field>
                <Field label="Target URL">
                  <input value={form.target_url} onChange={(event) => setForm({ ...form, target_url: event.target.value })} className={inputClass} />
                </Field>
                <Field label="Allowed domains">
                  <input value={form.allowed_domains} onChange={(event) => setForm({ ...form, allowed_domains: event.target.value })} placeholder="example.com, admin.example.com" className={inputClass} />
                </Field>
                <Field label="Notes">
                  <textarea value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} rows={3} className={`${inputClass} min-h-24`} />
                </Field>
              </div>
            </FormSection>

            <FormSection
              eyebrow="Auth"
              title="Login details"
              description="Use these fields when the run must sign in before it can reach the real menu structure and form surfaces."
            >
              <div className="grid gap-4 md:grid-cols-2">
                <Field label="Login URL">
                  <input value={form.login_url} onChange={(event) => setForm({ ...form, login_url: event.target.value })} className={inputClass} />
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
              eyebrow="Depth"
              title="Execution settings"
              description="Increase the step budget for large menu trees. Safe mode avoids destructive actions while still allowing create/edit form coverage."
            >
              <div className="grid gap-4 lg:grid-cols-[0.8fr_1.2fr]">
                <Field label="Max steps">
                  <input type="number" min={1} max={1000} value={form.max_steps} onChange={(event) => setForm({ ...form, max_steps: Number(event.target.value) })} className={inputClass} />
                </Field>
                <div className="grid gap-3 sm:grid-cols-2">
                  <Toggle label="Safe mode" checked={form.safe_mode} onChange={(checked) => setForm({ ...form, safe_mode: checked })} />
                  <Toggle label="Headless browser" checked={form.headless} onChange={(checked) => setForm({ ...form, headless: checked })} />
                </div>
              </div>
            </FormSection>

            {error ? <p className="rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p> : null}

            <div className="rounded-[22px] border border-slate/10 bg-sand/50 px-4 py-4 text-sm leading-6 text-slate/80">
              AutoQA will:
              <br />
              discover same-domain pages,
              <br />
              fill visible form fields,
              <br />
              submit invalid and valid form variants when possible,
              <br />
              and generate bug evidence you can hand to developers or paste into ClickUp.
            </div>

            <button
              type="submit"
              disabled={isLaunching}
              className="inline-flex items-center gap-2 rounded-full bg-ink px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isLaunching ? "Launching..." : "Create config and start run"}
              <ArrowRight className="h-4 w-4" />
            </button>
          </form>
        </Panel>
      </section>

      <section className="grid gap-4 lg:grid-cols-3">
        <GuideCard
          title="Discover pages"
          description="The agent keeps a queue of same-domain links and revisits newly discovered pages so forms hidden behind nav items are easier to reach."
        />
        <GuideCard
          title="Exercise forms"
          description="For each visible form, the run now tries validation-focused scenarios first and then a happy-path submit when the form stays available."
        />
        <GuideCard
          title="Create bug handoff"
          description="Failures are stored with a tester-friendly title, bug description, reproduction steps, actual result, expected result, and downloadable evidence."
        />
      </section>

      <section className="grid gap-4 lg:grid-cols-4">
        <WorkflowStep
          step="1"
          title="Start at the main app"
          description="Use the first page a tester would open after login so menu branches can fan out from there."
        />
        <WorkflowStep
          step="2"
          title="Let AutoQA walk menus"
          description="The explorer clicks through safe navigation, create, and edit actions, then backtracks to continue into other branches."
        />
        <WorkflowStep
          step="3"
          title="Review bug cards"
          description="Each issue card is written to be reused as a bug title plus actual result, expected result, and reproduction steps."
        />
        <WorkflowStep
          step="4"
          title="File in ClickUp"
          description="Attach the screenshot, trace, and markdown/json report to give developers direct evidence."
        />
      </section>

      <section className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <Panel>
          <div className="flex items-center justify-between">
            <div>
              <p className="font-mono text-xs uppercase tracking-[0.34em] text-slate/60">Run history</p>
              <h2 className="mt-2 font-display text-2xl font-semibold text-ink">Recent sessions</h2>
            </div>
            <button
              type="button"
              onClick={handleClearHistory}
              disabled={isClearingHistory || runs.every((run) => ["queued", "running", "paused"].includes(run.status))}
              className="inline-flex items-center gap-2 rounded-full border border-slate/10 bg-white px-4 py-2 text-sm font-semibold text-slate transition hover:border-slate/20 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Trash2 className="h-4 w-4" />
              {isClearingHistory ? "Clearing..." : "Clear history"}
            </button>
          </div>
          <div className="mt-6 space-y-4">
            {runs.length === 0 ? (
              <EmptyState title="No runs yet" description="Launch the first exploration run to start building coverage and generated tests." />
            ) : (
              runs.map((run) => (
                <article key={run.id} className="overflow-hidden rounded-[24px] border border-slate/10 bg-sand/50 p-4 transition hover:border-slate/20 hover:bg-white">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <Link href={`/runs/${run.id}`} className="min-w-0 flex-1">
                      <p className="font-display text-lg font-semibold text-ink">{run.config_name}</p>
                      <p className="overflow-anywhere mt-1 text-sm text-slate/70">{run.target_url}</p>
                    </Link>
                    <StatusBadge value={run.status} />
                  </div>
                  <div className="mt-4 grid gap-3 text-sm text-slate/75 sm:grid-cols-3">
                    <span>Created {formatDistanceToNow(new Date(run.created_at), { addSuffix: true })}</span>
                    <span>Max steps {run.max_steps}</span>
                    <span>Failures {String((run.summary.failure_count as number | undefined) ?? 0)}</span>
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <Link href={`/runs/${run.id}`} className="inline-flex items-center gap-2 rounded-full bg-ink px-4 py-2 text-sm font-semibold text-white">
                      Open
                    </Link>
                    {run.status === "running" ? (
                      <RunActionButton
                        icon={<Pause className="h-4 w-4" />}
                        label="Pause"
                        disabled={busyRunId === run.id}
                        onClick={() => void handleRunAction(run, "pause")}
                      />
                    ) : null}
                    {run.status === "paused" ? (
                      <RunActionButton
                        icon={<Play className="h-4 w-4" />}
                        label="Resume"
                        disabled={busyRunId === run.id}
                        onClick={() => void handleRunAction(run, "resume")}
                      />
                    ) : null}
                    {["queued", "running", "paused"].includes(run.status) ? (
                      <RunActionButton
                        icon={<Square className="h-4 w-4" />}
                        label="Stop"
                        disabled={busyRunId === run.id}
                        onClick={() => void handleRunAction(run, "stop")}
                      />
                    ) : null}
                    {!["queued", "running", "paused"].includes(run.status) ? (
                      <RunActionButton
                        icon={<Trash2 className="h-4 w-4" />}
                        label="Delete"
                        disabled={busyRunId === run.id}
                        onClick={() => void handleRunAction(run, "delete")}
                      />
                    ) : null}
                  </div>
                </article>
              ))
            )}
          </div>
        </Panel>

        <Panel>
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.34em] text-slate/60">Generated tests</p>
            <h2 className="mt-2 font-display text-2xl font-semibold text-ink">Recent exported specs</h2>
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
                    <StatusBadge value="completed" />
                  </div>
                  <pre className="mt-4 overflow-x-auto rounded-2xl bg-ink px-4 py-3 font-mono text-xs leading-6 text-sand">
                    {test.content.split("\n").slice(0, 8).join("\n")}
                  </pre>
                </Link>
              ))
            )}
          </div>
        </Panel>
      </section>
    </main>
  );
}

function Metric({ title, value, icon }: { title: string; value: string; icon: React.ReactNode }) {
  return (
    <div className="rounded-[22px] border border-slate/10 bg-white/75 px-4 py-3">
      <div className="flex items-center justify-between text-slate/70">
        <span className="font-mono text-xs uppercase tracking-[0.26em]">{title}</span>
        {icon}
      </div>
      <p className="mt-2 font-display text-3xl font-semibold text-ink">{value}</p>
    </div>
  );
}

function GuideCard({ title, description }: { title: string; description: string }) {
  return (
    <Panel className="relative overflow-hidden bg-white/80">
      <div className="absolute right-0 top-0 h-24 w-24 rounded-full bg-ember/10 blur-3xl" />
      <div className="relative">
        <p className="font-mono text-xs uppercase tracking-[0.26em] text-slate/55">How It Works</p>
        <h3 className="mt-3 font-display text-2xl font-semibold text-ink">{title}</h3>
        <p className="mt-3 text-sm leading-6 text-slate/80">{description}</p>
      </div>
    </Panel>
  );
}

function FormSection({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-[24px] border border-slate/10 bg-sand/40 px-4 py-5">
      <p className="font-mono text-xs uppercase tracking-[0.22em] text-slate/55">{eyebrow}</p>
      <h3 className="mt-2 font-display text-xl font-semibold text-ink">{title}</h3>
      <p className="mt-2 text-sm leading-6 text-slate/75">{description}</p>
      <div className="mt-4">{children}</div>
    </div>
  );
}

function WorkflowStep({ step, title, description }: { step: string; title: string; description: string }) {
  return (
    <Panel className="relative overflow-hidden bg-white/85">
      <div className="absolute right-0 top-0 h-20 w-20 rounded-full bg-cyan-300/15 blur-3xl" />
      <div className="relative">
        <p className="font-mono text-xs uppercase tracking-[0.22em] text-slate/55">Step {step}</p>
        <h3 className="mt-2 font-display text-2xl font-semibold text-ink">{title}</h3>
        <p className="mt-3 text-sm leading-6 text-slate/75">{description}</p>
      </div>
    </Panel>
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
      className={`flex min-h-[76px] items-center justify-between rounded-[22px] border px-4 py-3 text-left transition ${
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
        className={`relative inline-flex h-8 w-14 shrink-0 items-center rounded-full p-1 transition ${
          checked ? "bg-ink" : "bg-slate/20"
        }`}
      >
        <span
          className={`h-6 w-6 rounded-full bg-white shadow-sm transition-transform ${
            checked ? "translate-x-6" : "translate-x-0"
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

const inputClass =
  "w-full rounded-2xl border border-slate/10 bg-sand/60 px-4 py-3 text-sm text-ink outline-none transition placeholder:text-slate/45 focus:border-ember focus:bg-white";
