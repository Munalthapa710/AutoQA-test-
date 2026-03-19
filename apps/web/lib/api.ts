import type {
  Artifact,
  DiscoveredFlow,
  FailureReport,
  GeneratedTest,
  Run,
  RunDetail,
  RunListItem,
  RunStep,
  TestConfig,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const LOCAL_STORE_KEY = "autoqa.local-store.v1";

type LocalStore = {
  configs: TestConfig[];
  runs: Run[];
  runSteps: RunStep[];
  flows: DiscoveredFlow[];
  failures: FailureReport[];
  artifacts: Artifact[];
  generatedTests: GeneratedTest[];
};

const EMPTY_STORE: LocalStore = {
  configs: [],
  runs: [],
  runSteps: [],
  flows: [],
  failures: [],
  artifacts: [],
  generatedTests: [],
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with status ${response.status}`);
  }

  return response.json() as Promise<T>;
}

function canUseLocalStore() {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

function isBackendUnavailable(error: unknown) {
  if (!(error instanceof Error)) {
    return false;
  }

  const message = error.message.toLowerCase();
  return (
    error.name === "TypeError" ||
    message.includes("failed to fetch") ||
    message.includes("networkerror") ||
    message.includes("load failed")
  );
}

function readLocalStore(): LocalStore {
  if (!canUseLocalStore()) {
    return EMPTY_STORE;
  }

  try {
    const raw = window.localStorage.getItem(LOCAL_STORE_KEY);
    if (!raw) {
      return EMPTY_STORE;
    }

    const parsed = JSON.parse(raw) as Partial<LocalStore>;
    return {
      configs: parsed.configs ?? [],
      runs: parsed.runs ?? [],
      runSteps: parsed.runSteps ?? [],
      flows: parsed.flows ?? [],
      failures: parsed.failures ?? [],
      artifacts: parsed.artifacts ?? [],
      generatedTests: parsed.generatedTests ?? [],
    };
  } catch {
    return EMPTY_STORE;
  }
}

function writeLocalStore(store: LocalStore) {
  if (!canUseLocalStore()) {
    return;
  }

  window.localStorage.setItem(LOCAL_STORE_KEY, JSON.stringify(store));
}

function createId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `local-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function nowIso() {
  return new Date().toISOString();
}

async function withFallback<T>(remote: () => Promise<T>, local: () => T): Promise<T> {
  try {
    return await remote();
  } catch (error) {
    if (!canUseLocalStore() || !isBackendUnavailable(error)) {
      throw error;
    }
    return local();
  }
}

function getLocalRunDetail(id: string): RunDetail {
  const store = readLocalStore();
  const run = store.runs.find((entry) => entry.id === id);
  if (!run) {
    throw new Error("Run not found.");
  }

  const config = store.configs.find((entry) => entry.id === run.config_id);
  if (!config) {
    throw new Error("Config not found for run.");
  }

  return { ...run, config };
}

export function artifactUrl(filePath: string) {
  return `${API_BASE}/files/artifacts/${toAssetPath(filePath)}`;
}

export function generatedTestFileUrl(filePath: string) {
  return `${API_BASE}/files/generated-tests/${toAssetPath(filePath)}`;
}

function toAssetPath(filePath: string) {
  return filePath
    .split(/[\\/]+/)
    .filter(Boolean)
    .map((segment) => encodeURIComponent(segment))
    .join("/");
}

export const api = {
  listRuns: () =>
    withFallback(
      () => request<RunListItem[]>("/runs"),
      () => {
        const store = readLocalStore();
        return store.runs
          .map((run) => {
            const config = store.configs.find((entry) => entry.id === run.config_id);
            if (!config) {
              return null;
            }

            return {
              ...run,
              config_name: config.name,
              target_url: config.target_url,
            };
          })
          .filter((entry): entry is RunListItem => entry !== null)
          .sort((left, right) => right.created_at.localeCompare(left.created_at));
      },
    ),
  getRun: (id: string) =>
    withFallback(() => request<RunDetail>(`/runs/${id}`), () => getLocalRunDetail(id)),
  getRunSteps: (id: string) =>
    withFallback(
      () => request<RunStep[]>(`/runs/${id}/steps`),
      () => readLocalStore().runSteps.filter((entry) => entry.run_id === id),
    ),
  getRunFlows: (id: string) =>
    withFallback(
      () => request<DiscoveredFlow[]>(`/runs/${id}/flows`),
      () => readLocalStore().flows.filter((entry) => entry.run_id === id),
    ),
  getRunFailures: (id: string) =>
    withFallback(
      () => request<FailureReport[]>(`/runs/${id}/failures`),
      () => readLocalStore().failures.filter((entry) => entry.run_id === id),
    ),
  getRunArtifacts: (id: string) =>
    withFallback(
      () => request<Artifact[]>(`/runs/${id}/artifacts`),
      () => readLocalStore().artifacts.filter((entry) => entry.run_id === id),
    ),
  listGeneratedTests: () =>
    withFallback(() => request<GeneratedTest[]>("/generated-tests"), () => readLocalStore().generatedTests),
  getGeneratedTest: (id: string) =>
    withFallback(
      () => request<GeneratedTest>(`/generated-tests/${id}`),
      () => {
        const test = readLocalStore().generatedTests.find((entry) => entry.id === id);
        if (!test) {
          throw new Error("Generated test not found.");
        }
        return test;
      },
    ),
  listConfigs: () =>
    withFallback(() => request<TestConfig[]>("/configs"), () => readLocalStore().configs),
  createConfig: (payload: Record<string, unknown>) =>
    withFallback(
      () =>
        request<TestConfig>("/configs", {
          method: "POST",
          body: JSON.stringify(payload),
        }),
      () => {
        const store = readLocalStore();
        const timestamp = nowIso();
        const config: TestConfig = {
          id: createId(),
          name: String(payload.name ?? "Untitled run"),
          target_url: String(payload.target_url ?? ""),
          login_url: (payload.login_url as string | null | undefined) ?? null,
          username: (payload.username as string | null | undefined) ?? null,
          password: (payload.password as string | null | undefined) ?? null,
          username_selector: (payload.username_selector as string | null | undefined) ?? null,
          password_selector: (payload.password_selector as string | null | undefined) ?? null,
          submit_selector: (payload.submit_selector as string | null | undefined) ?? null,
          headless: Boolean(payload.headless),
          safe_mode: payload.safe_mode !== false,
          max_steps: Number(payload.max_steps ?? 20),
          allowed_domains: Array.isArray(payload.allowed_domains)
            ? payload.allowed_domains.filter((item): item is string => typeof item === "string")
            : [],
          notes: (payload.notes as string | null | undefined) ?? null,
          created_at: timestamp,
          updated_at: timestamp,
        };

        writeLocalStore({
          ...store,
          configs: [config, ...store.configs],
        });
        return config;
      },
    ),
  createRun: (configId: string) =>
    withFallback(
      () =>
        request<{ id: string }>("/runs", {
          method: "POST",
          body: JSON.stringify({ config_id: configId }),
        }),
      () => {
        const store = readLocalStore();
        const config = store.configs.find((entry) => entry.id === configId);
        if (!config) {
          throw new Error("Config not found.");
        }

        const timestamp = nowIso();
        const run: Run = {
          id: createId(),
          config_id: configId,
          status: "queued",
          max_steps: config.max_steps,
          safe_mode: config.safe_mode,
          started_at: null,
          ended_at: null,
          run_settings: {
            headless: config.headless,
          },
          summary: {},
          error_message: "Backend unavailable. This run is stored locally until the API is available.",
          created_at: timestamp,
          updated_at: timestamp,
        };

        writeLocalStore({
          ...store,
          runs: [run, ...store.runs],
        });
        return { id: run.id };
      },
    ),
};
