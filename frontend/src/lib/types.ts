// Mirrors the FastAPI response models (backend/app/main.py).

export type Column = { name: string; type: string };
export type Cell = string | number | boolean | null;
export type Row = Cell[];

export type ChartType = "bar" | "line" | "area" | "pie" | "scatter" | "kpi" | "table" | "empty";
export type ChartSpec = {
  type: ChartType;
  x: string | null;
  measures: string[];
  available_measures: string[];
  alternatives: ChartType[];
  horizontal: boolean;
  diverging: boolean;
  reason: string;
};

export type Attempt = {
  number: number;
  sql: string | null;
  outcome: "ok" | "no_sql" | "rejected_by_guard" | "database_error" | "timeout" | "suspicious_result" | "cannot_answer";
  detail: string | null;
  raw_sql: string | null;
};

export type Verification = {
  case_id: string;
  category: string;
  trap: string;
  expect: "match" | "refuse";
  matched: boolean;
  reason: string;
  golden_sql?: string;
  golden_columns?: string[];
  golden_rows?: Row[];
  ordered?: boolean;
};

export type AskResult = {
  status: "ok" | "failed" | "cannot_answer";
  question: string;
  sql: string | null;
  pretty_sql: string | null;
  tables: string[];
  columns: Column[];
  rows: Row[];
  row_count: number;
  truncated: boolean;
  elapsed_ms: number | null;
  effective_limit: number | null;
  limit_applied: boolean;
  warnings: string[];
  attempts: Attempt[];
  message: string | null;
  model: string | null;
  chart: ChartSpec | null;
  verification: Verification | null;
};

export type SqlResult = {
  sql: string;
  pretty_sql: string;
  tables: string[];
  warnings: string[];
  columns: Column[];
  rows: Row[];
  row_count: number;
  truncated: boolean;
  elapsed_ms: number;
  effective_limit: number;
  limit_applied: boolean;
  chart: ChartSpec;
};

// Server-sent pipeline events (backend/app/pipeline.py)
export type PipelineEvent =
  | { type: "start"; question: string; max_attempts: number }
  | { type: "attempt_start"; n: number }
  | { type: "sql"; n: number; sql: string }
  | { type: "guard"; n: number; ok: true; sql: string; pretty_sql: string; tables: string[]; effective_limit: number; limit_applied: boolean }
  | { type: "guard"; n: number; ok: false; code: string; message: string }
  | { type: "database_error"; n: number; code: string; message: string }
  | { type: "executed"; n: number; row_count: number; elapsed_ms: number }
  | { type: "checks"; n: number; issues: { code: string; message: string; repairable: boolean }[] }
  | { type: "repair"; n: number; reason: string }
  | { type: "no_sql"; n: number }
  | { type: "cannot_answer"; n: number; reason: string }
  | { type: "result"; data: AskResult }
  | { type: "error"; stage: string; code: string; message: string };

export type Meta = {
  provider: string;
  demo: boolean;
  reference_date: string;
  max_rows: number;
  statement_timeout_ms: number;
  max_attempts: number;
  examples: { id: string; question: string; category: string; expect: "match" | "refuse" }[];
};

export type SchemaColumn = { name: string; type: string; nullable: boolean; comment: string | null; sample_values: string[] };
export type SchemaTable = { name: string; comment: string | null; columns: SchemaColumn[]; constraints: string[] };
export type SchemaInfo = { tables: SchemaTable[] };

export type EvalCaseResult = {
  id: string; category: string; question: string; expect: string; passed: boolean; status: string;
  reason: string; attempts: number; generated_sql: string | null; golden_sql: string | null;
  elapsed_s: number; flags: string[]; trap: string;
};
export type EvalReport = {
  recording: "reference" | "naive";
  model: string;
  wall_ms: number;
  summary: { total: number; passed: number; accuracy: number; first_try_passes: number; recovered_by_repair: number;
             avg_attempts: number; total_seconds: number; database_integrity_ok: boolean };
  by_category: Record<string, { passed: number; total: number }>;
  results: EvalCaseResult[];
};

export type ProbeResult = { layer: string; statement: string; blocked: boolean; blocked_by: string; error: string; elapsed_ms: number };
export type ApiErrorDetail = { stage: string; code: string; message: string };
