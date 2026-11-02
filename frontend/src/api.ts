import type {
  InputAssessmentRequest,
  ResultAssessmentReport,
} from "./contracts.generated";
export type { InputAssessmentRequest, ResultAssessmentReport };
export type Config = {
  auth_mode: "local" | "jwt";
  max_raw_upload_bytes: number;
  max_decompressed_bytes: number;
  default_retention_days: number;
};
export type Project = {
  project_id: string;
  name: string;
  business_context: string | null;
};
export type Dataset = {
  dataset_id: string;
  state: string;
  detected_format: "csv" | "ndjson" | "parquet" | null;
  original_bytes: number | null;
  expires_at: string;
};
export type ProfileRef = { profile_id: string; profile_version: number };
export type Status = {
  id: string;
  project_id: string;
  dataset_id: string | null;
  profile_id: string | null;
  status: string;
  progress: {
    stage?: string;
    completed_configurations?: number;
    completed_trials?: number;
    eligible_configurations?: number;
  };
  attempts: number;
  stop_reason: string | null;
  cancel_requested: boolean;
  request_fingerprint: string;
  input_fingerprint: string;
  expires_at: string;
};
export const terminal = (status: string) =>
  ["completed", "needs_input", "cancelled", "failed"].includes(status);
export function message(body: unknown, status: number): string {
  const obj = body as { detail?: unknown; message?: string };
  return `${status}: ${typeof obj?.detail === "string" ? obj.detail : (obj?.message ?? "Request failed. Check the inputs and retry.")}`;
}
export class Api {
  headers: Record<string, string>;
  pending = new Set<AbortController>();
  uploads = new Set<XMLHttpRequest>();
  constructor(identity: string, token: string) {
    this.headers = token
      ? { Authorization: `Bearer ${token}` }
      : { "X-Local-Identity": identity };
  }
  abortAll() {
    this.pending.forEach((c) => c.abort());
    this.uploads.forEach((x) => x.abort());
  }
  async call<T>(
    path: string,
    body?: unknown,
    method = body === undefined ? "GET" : "POST",
    extra = {},
  ): Promise<T> {
    const controller = new AbortController();
    this.pending.add(controller);
    const timer = window.setTimeout(() => controller.abort(), 90_000);
    try {
      const response = await fetch(`/api${path}`, {
        method,
        headers: {
          Accept: "application/json",
          ...this.headers,
          ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
          ...extra,
        },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
      });
      const result: unknown = await response.json();
      if (!response.ok) throw new Error(message(result, response.status));
      return result as T;
    } finally {
      clearTimeout(timer);
      this.pending.delete(controller);
    }
  }
  async download(path: string, filename: string): Promise<void> {
    const controller = new AbortController();
    this.pending.add(controller);
    const timer = window.setTimeout(() => controller.abort(), 90_000);
    try {
      const response = await fetch(`/api${path}`, {
        headers: this.headers, signal: controller.signal,
      });
      if (!response.ok) throw new Error(message(await response.json(), response.status));
      const blob = await response.blob();
      if (controller.signal.aborted) throw new Error("Download interrupted.");
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } finally {
      clearTimeout(timer);
      this.pending.delete(controller);
    }
  }
  upload(
    path: string,
    file: File,
    progress: (n: number) => void,
  ): Promise<void> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      this.uploads.add(xhr);
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable)
          progress(Math.round((e.loaded / e.total) * 100));
      };
      xhr.open("PUT", `/api${path}`);
      xhr.timeout = 300_000;
      Object.entries(this.headers).forEach(([k, v]) =>
        xhr.setRequestHeader(k, v),
      );
      xhr.setRequestHeader("Content-Type", "application/octet-stream");
      xhr.onload = () => {
        this.uploads.delete(xhr);
        if (xhr.status >= 200 && xhr.status < 300) resolve();
        else {
          let body: unknown = {};
          try {
            body = JSON.parse(xhr.responseText);
          } catch {
            /* Proxy may return text. */
          }
          reject(new Error(message(body, xhr.status)));
        }
      };
      xhr.onerror =
        xhr.ontimeout =
        xhr.onabort =
          () => {
            this.uploads.delete(xhr);
            reject(new Error("Transfer interrupted. Retry the upload."));
          };
      xhr.send(file);
    });
  }
}
export const pretty = (v: unknown) => JSON.stringify(v, null, 2);
export const errorText = (e: unknown) =>
  e instanceof Error ? e.message : "Request failed. Retry.";

export const requirementsKey = (request: InputAssessmentRequest) =>
  pretty({ policy: request.policy, workload: request.conversion?.workload ?? null });

export function assistanceStatus(status: string): string {
  return ({
    not_requested: "Local guidance is ready.", completed: "AI selection was checked against the evidence.",
    disabled: "Optional AI is disabled.", missing_key: "No AI provider key is configured.",
    timeout: "The AI provider timed out.", provider_unavailable: "The AI provider is unavailable.",
    invalid_output: "The AI response could not be verified.",
    incomplete_or_refused: "The AI provider did not return a complete answer.",
    budget_exhausted: "The AI usage budget has been reached.",
    input_budget_exhausted: "This summary exceeds the configured AI input limit.",
  } as Record<string, string>)[status] ?? "Local guidance remains available.";
}
