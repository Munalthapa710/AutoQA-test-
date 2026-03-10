import type {
  Artifact,
  DiscoveredFlow,
  FailureReport,
  GeneratedTest,
  RunDetail,
  RunListItem,
  RunStep,
  TestConfig,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

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

export function artifactUrl(filePath: string) {
  return `${API_BASE}/files/artifacts/${filePath}`;
}

export function generatedTestFileUrl(filePath: string) {
  return `${API_BASE}/files/generated-tests/${filePath}`;
}

export const api = {
  listRuns: () => request<RunListItem[]>("/runs"),
  getRun: (id: string) => request<RunDetail>(`/runs/${id}`),
  getRunSteps: (id: string) => request<RunStep[]>(`/runs/${id}/steps`),
  getRunFlows: (id: string) => request<DiscoveredFlow[]>(`/runs/${id}/flows`),
  getRunFailures: (id: string) => request<FailureReport[]>(`/runs/${id}/failures`),
  getRunArtifacts: (id: string) => request<Artifact[]>(`/runs/${id}/artifacts`),
  listGeneratedTests: () => request<GeneratedTest[]>("/generated-tests"),
  getGeneratedTest: (id: string) => request<GeneratedTest>(`/generated-tests/${id}`),
  listConfigs: () => request<TestConfig[]>("/configs"),
  createConfig: (payload: Record<string, unknown>) =>
    request<TestConfig>("/configs", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  createRun: (configId: string) =>
    request<{ id: string }>("/runs", {
      method: "POST",
      body: JSON.stringify({ config_id: configId }),
    }),
};
