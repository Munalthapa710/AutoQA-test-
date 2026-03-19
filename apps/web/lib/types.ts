export type TestConfig = {
  id: string;
  name: string;
  target_url: string;
  login_url: string | null;
  username: string | null;
  password: string | null;
  username_selector: string | null;
  password_selector: string | null;
  submit_selector: string | null;
  headless: boolean;
  safe_mode: boolean;
  max_steps: number;
  allowed_domains: string[];
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type Run = {
  id: string;
  config_id: string;
  status: string;
  control_state: string | null;
  max_steps: number;
  safe_mode: boolean;
  started_at: string | null;
  ended_at: string | null;
  run_settings: Record<string, unknown>;
  summary: Record<string, unknown>;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

export type RunListItem = Run & {
  config_name: string;
  target_url: string;
};

export type RunDetail = Run & {
  config: TestConfig;
};

export type RunStep = {
  id: string;
  run_id: string;
  step_index: number;
  node_name: string;
  action: string;
  rationale: string;
  page_title: string | null;
  url: string | null;
  element_label: string | null;
  locator: Record<string, unknown>;
  risk_level: string;
  status: string;
  confidence: number;
  details: Record<string, unknown>;
  started_at: string;
  finished_at: string | null;
};

export type DiscoveredFlow = {
  id: string;
  run_id: string;
  name: string;
  flow_type: string;
  success: boolean;
  description: string;
  path: Array<Record<string, unknown>>;
  flow_metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type FailureReport = {
  id: string;
  run_id: string;
  step_id: string | null;
  failure_type: string;
  severity: string;
  title: string;
  description: string;
  evidence: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type Artifact = {
  id: string;
  run_id: string;
  step_id: string | null;
  type: string;
  file_path: string;
  mime_type: string;
  artifact_metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type GeneratedTest = {
  id: string;
  run_id: string;
  flow_id: string | null;
  name: string;
  file_path: string;
  content: string;
  language: string;
  created_at: string;
  updated_at: string;
};
