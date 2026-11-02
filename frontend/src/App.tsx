import { useEffect, useMemo, useRef, useState } from "react";
import type {
  Config,
  Dataset,
  InputAssessmentRequest,
  ProfileRef,
  Project,
  ResultAssessmentReport,
  Status,
} from "./api";
import type { LocalProfileReport } from "./contracts.generated";
import { Api, errorText, pretty, terminal } from "./api";
import demo from "./demo-request.json";
import Results from "./Results";
import Handoff from "./Handoff";
import Intake from "./Intake";
import { requirementsKey } from "./api";
import Explanation from "./Explanation";

function stored(key: string) {
  try {
    return sessionStorage.getItem(key) ?? "";
  } catch {
    return "";
  }
}
function save(key: string, value: string) {
  try {
    sessionStorage.setItem(key, value);
  } catch {
    /* Storage is optional. */
  }
}
const baseRequest: InputAssessmentRequest = {
  policy: { scenario: "user_scenario" },
  conversion: {
    tenant_id: "00000000-0000-0000-0000-000000000000",
    assessment_id: "00000000-0000-0000-0000-000000000000",
    source: { format: "ndjson" },
    workload: {
      queries: [{ id: "scan", kind: "full_scan" }],
      concurrency: 1,
      concurrency_scope: "single_process",
    },
  },
};

export default function App() {
  const [config, setConfig] = useState<Config | null>(null);
  const [error, setError] = useState("");
  const [identity, setIdentity] = useState(
    () => stored("do:v1:identity") || "alice",
  );
  const [token, setToken] = useState("");
  const [credential, setCredential] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/v1/dashboard/config", { signal: controller.signal })
      .then(async (r) => {
        if (!r.ok)
          throw new Error(
            "API is not reachable. Start make dev and check local services.",
          );
        setConfig((await r.json()) as Config);
        setError("");
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(errorText(e));
      });
    return () => controller.abort();
  }, [retry]);
  return (
    <div className="app-shell">
      <a className="skip-link" href="#workspace">
        Skip to workspace
      </a>
      <header className="topbar">
        <a href="#workspace" className="brand">
          <span className="brand-mark">DO</span>Data Optimizer
        </a>
        <span className="environment-tag">Local assessment workspace</span>
      </header>
      <div className="session-bar">
        {config?.auth_mode === "local" ? (
          <label>
            Local demo identity{" "}
            <select
              aria-label="Local demo identity"
              value={identity}
              onChange={(e) => {
                setIdentity(e.target.value);
                save("do:v1:identity", e.target.value);
              }}
            >
              <option value="alice">Alice</option>
              <option value="bob">Bob</option>
            </select>
          </label>
        ) : config?.auth_mode === "jwt" ? (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setToken(credential);
              setCredential("");
            }}
          >
            <label>
              Verified session token{" "}
              <input
                type="password"
                autoComplete="off"
                value={credential}
                onChange={(e) => setCredential(e.target.value)}
              />
            </label>
            <button>Use session</button>
            <button
              type="button"
              onClick={() => {
                setToken("");
                setCredential("");
              }}
            >
              Sign out
            </button>
          </form>
        ) : (
          <span>Connecting to API…</span>
        )}
        <span>Compare copies. Preserve your source.</span>
      </div>
      {error && (
        <div className="error" role="alert">
          {error}
          <button onClick={() => setRetry((n) => n + 1)}>
            Retry connection
          </button>
        </div>
      )}
      {config && (config.auth_mode === "local" || token) ? (
        <Dashboard
          key={config.auth_mode === "local" ? identity : token}
          identity={identity}
          token={token}
          config={config}
        />
      ) : (
        <main id="workspace">
          <h1>Evidence before change.</h1>
          <p>
            {config?.auth_mode === "jwt"
              ? "Enter a verified identity token to open your projects. Tokens are kept in memory only."
              : "Waiting for the assessment API."}
          </p>
        </main>
      )}
      <footer>
        DATA OPTIMIZER / Evidence from your sample. Costs from explicit
        assumptions.
      </footer>
    </div>
  );
}

function Dashboard({
  identity,
  token,
  config,
}: {
  identity: string;
  token: string;
  config: Config;
}) {
  const scope = token ? "verified-session" : identity;
  const api = useMemo(() => new Api(identity, token), [identity, token]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState(() =>
    token ? "" : stored(`do:v1:${scope}:project`),
  );
  const [name, setName] = useState("");
  const [context, setContext] = useState("");
  const [mode, setMode] = useState<"raw" | "metadata" | "startup">("raw");
  const [format, setFormat] = useState<"csv" | "ndjson" | "parquet">("ndjson");
  const [file, setFile] = useState<File | null>(null);
  const [retention, setRetention] = useState(config.default_retention_days);
  const [consent, setConsent] = useState(false);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [datasetId, setDatasetId] = useState("");
  const [profiles, setProfiles] = useState<ProfileRef[]>([]);
  const [profileId, setProfileId] = useState("");
  const [metadata, setMetadata] = useState<LocalProfileReport | null>(null);
  const [reviewed, setReviewed] = useState(false);
  const [requestText, setRequestText] = useState(
    () => (!token && stored(`do:v1:${scope}:draft`)) || pretty(baseRequest),
  );
  const [acceptedIntake, setAcceptedIntake] = useState<{ id: string; key: string } | null>(() => {
    if (token) return null;
    try {
      const saved = JSON.parse(stored(`do:v1:${scope}:intake`));
      return saved?.projectId === projectId && typeof saved?.id === "string" && typeof saved?.key === "string"
        ? { id: saved.id, key: saved.key } : null;
    } catch { return null; }
  });
  const latestDraft = useRef(requestText);
  latestDraft.current = requestText;
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [uploadPercent, setUploadPercent] = useState<number | null>(null);
  const [assessments, setAssessments] = useState<Status[]>([]);
  const [assessmentId, setAssessmentId] = useState(() =>
    token ? "" : stored(`do:v1:${scope}:assessment`),
  );
  const [status, setStatus] = useState<Status | null>(null);
  const [report, setReport] = useState<ResultAssessmentReport | null>(null);
  const [pollError, setPollError] = useState("");
  const [pollRetry, setPollRetry] = useState(0);
  const [issues, setIssues] = useState<{ path: string; code: string }[]>([]);
  const submission = useRef<{ payload: string; key: string } | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const [loaded, setLoaded] = useState(false);
  const [reload, setReload] = useState(0);
  let request: InputAssessmentRequest | null = null;
  let parseError = "";
  try {
    request = JSON.parse(requestText) as InputAssessmentRequest;
    if (
      !request ||
      typeof request !== "object" ||
      !request.policy ||
      typeof request.policy !== "object" ||
      (request.conversion != null &&
        (typeof request.conversion !== "object" ||
          !request.conversion.source ||
          typeof request.conversion.source !== "object"))
    )
      throw new Error("Include a policy object.");
  } catch (e) {
    request = null;
    parseError = errorText(e);
  }

  useEffect(() => () => api.abortAll(), [api]);
  useEffect(() => {
    if (!token) save(`do:v1:${scope}:draft`, requestText);
  }, [requestText, scope, token]);
  useEffect(() => {
    let active = true;
    api
      .call<{ items: Project[] }>("/v1/projects")
      .then((r) => {
        if (active) {
          setProjects(r.items);
          setLoaded(true);
        }
      })
      .catch((e) => {
        if (active) {
          setError(errorText(e));
          setLoaded(true);
        }
      });
    return () => {
      active = false;
    };
  }, [api, reload]);
  useEffect(() => {
    if (!projectId) return;
    let active = true;
    Promise.all([
      api.call<{ items: Dataset[] }>(`/v1/projects/${projectId}/datasets`),
      api.call<{ items: ProfileRef[] }>(`/v1/projects/${projectId}/profiles`),
      api.call<{ items: Status[] }>(`/v1/assessments?project_id=${projectId}`),
    ])
      .then(([d, p, a]) => {
        if (active) {
          setDatasets(d.items);
          setProfiles(p.items);
          setAssessments(a.items);
        }
      })
      .catch((e) => {
        if (active) setError(errorText(e));
      });
    return () => {
      active = false;
    };
  }, [api, projectId, reload]);
  useEffect(() => {
    if (!assessmentId) return;
    let active = true;
    let timer: number | undefined;
    async function poll() {
      try {
        const s = await api.call<Status>(`/v1/assessments/${assessmentId}`);
        if (!active) return;
        setStatus(s);
        setPollError("");
        if (terminal(s.status)) {
          try {
            const r = await api.call<ResultAssessmentReport>(
              `/v1/assessments/${assessmentId}/result`,
            );
            if (active) {
              setReport(r);
              timer = window.setTimeout(() => void poll(), 10000);
            }
          } catch (e) {
            if (active && !["cancelled", "failed"].includes(s.status)) {
              setPollError(errorText(e));
              timer = window.setTimeout(() => void poll(), 3000);
            }
          }
        } else timer = window.setTimeout(() => void poll(), 1500);
      } catch (e) {
        if (active) {
          setStatus(null);
          setReport(null);
          setPollError(errorText(e));
          timer = window.setTimeout(() => void poll(), 5000);
        }
      }
    }
    void poll();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [api, assessmentId, pollRetry]);

  async function action(label: string, fn: () => Promise<void>) {
    setBusy(label);
    setError("");
    setNotice("");
    setIssues([]);
    try {
      await fn();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy("");
      setUploadPercent(null);
    }
  }
  function selectAssessment(id: string) {
    setAssessmentId(id);
    setStatus(null);
    setReport(null);
    setPollError("");
    if (!token) save(`do:v1:${scope}:assessment`, id);
  }
  function selectProject(id: string) {
    setProjectId(id);
    setAcceptedIntake(null);
    if (!token) save(`do:v1:${scope}:intake`, "");
    setDatasetId("");
    setProfileId("");
    setDatasets([]);
    setProfiles([]);
    setAssessments([]);
    setMetadata(null);
    setReviewed(false);
    selectAssessment("");
    setError("");
    if (!token) save(`do:v1:${scope}:project`, id);
  }
  function editRequest(v: InputAssessmentRequest) {
    setRequestText(pretty(v));
    setIssues([]);
  }
  async function createProject() {
    const p = await api.call<Project>("/v1/projects", {
      name,
      business_context: context || null,
    });
    setProjects((prev) => [p, ...prev]);
    selectProject(p.project_id);
    setNotice("Project created. Add a dataset or reviewed metadata.");
  }
  async function upload() {
    if (!file) throw new Error("Choose a file.");
    if (file.size > config.max_raw_upload_bytes)
      throw new Error("File exceeds the configured raw upload limit.");
    const session = await api.call<{
      upload_url: string;
      upload_session_id: string;
    }>(`/v1/projects/${projectId}/datasets`, {
      format,
      filename: file.name,
      expected_bytes: file.size,
      retention_days: retention,
    });
    setUploadPercent(0);
    await api.upload(session.upload_url, file, setUploadPercent);
    setBusy("Validating file structure…");
    const d = await api.call<Dataset>(
      `/v1/uploads/${session.upload_session_id}/finalize`,
      {},
    );
    setDatasets((prev) => [d, ...prev]);
    setDatasetId(d.dataset_id);
    setNotice("Upload validated. Confirm schema and workload before running.");
    if (request?.conversion)
      editRequest({
        ...request,
        conversion: {
          ...request.conversion,
          source: {
            ...request.conversion.source,
            format: d.detected_format ?? format,
          },
        },
      });
  }
  async function readMetadata(f: File | undefined) {
    if (!f) return;
    setMetadata(null);
    setReviewed(false);
    if (f.size > 2_097_152) throw new Error("Metadata report exceeds 2 MiB.");
    const r = JSON.parse(await f.text()) as LocalProfileReport;
    if (
      !r.profile_fingerprint ||
      r.evidence !== "local_profile" ||
      r.raw_data_inspected_by_server
    )
      throw new Error(
        "Choose a local metadata-only profile report. Server profiles cannot be imported.",
      );
    setMetadata(r);
  }
  async function run() {
    if (!request || parseError)
      throw new Error("Correct the request JSON first.");
    if (acceptedIntake && acceptedIntake.key !== requirementsKey(request))
      throw new Error("Requirements changed after confirmation. Review and confirm them again.");
    const validation = await api.call<{
      valid: boolean;
      issues: { path: string; code: string }[];
      request: InputAssessmentRequest;
    }>("/v1/dashboard/validate", request);
    setIssues(validation.issues);
    if (!validation.valid)
      throw new Error(
        "Correct the fields listed below. Inputs have been preserved.",
      );
    const payload = {
      project_id: projectId,
      intake_confirmation_id: acceptedIntake?.id ?? null,
      dataset_id: mode === "raw" ? datasetId : null,
      profile_id: mode === "metadata" ? profileId : null,
      request: validation.request,
    };
    const json = pretty(payload);
    // Retain the same key on transport errors, including refresh, so retries cannot duplicate work.
    let pending = submission.current;
    if (!pending && !token) {
      try {
        pending = JSON.parse(
          stored(`do:v1:${scope}:submission`),
        ) as typeof pending;
      } catch {
        /* No pending retry. */
      }
    }
    if (!pending || pending.payload !== json)
      pending = { payload: json, key: crypto.randomUUID() };
    submission.current = pending;
    if (!token) save(`do:v1:${scope}:submission`, pretty(pending));
    const s = await api.call<Status>("/v1/assessments", payload, "POST", {
      "Idempotency-Key": pending.key,
    });
    selectAssessment(s.id);
    setStatus(s);
    setAssessments((prev) => [s, ...prev.filter((a) => a.id !== s.id)]);
    submission.current = null;
    if (!token) save(`do:v1:${scope}:submission`, "");
    setNotice("Assessment submitted. Progress is read from the worker.");
  }
  const chosen = datasets.find((d) => d.dataset_id === datasetId);
  return (
    <main id="workspace">
      <div className="intro">
        <div>
          <div className="section-label">Evidence before recommendations</div>
          <h1>
            A better fit for
            <br />
            <em>your data.</em>
          </h1>
          <p>
            Test lossless representations against your workload.
            <br />
            See what changes, what it costs, and what remains unknown.
          </p>
        </div>
        <div className="intro-note">
          <span>YOUR WORKSPACE</span>
          <strong>
            {loaded ? `${projects.length} projects` : "Loading projects…"}
          </strong>
          <p>
            Private assessment copies
            <br />
            No automatic migration
          </p>
        </div>
      </div>
      <nav className="flow-nav" aria-label="Assessment workflow">
        <a href="#project">01 Project</a>
        <a href="#input">02 Evidence</a>
        <a href="#requirements">03 Workload</a>
        <a href="#assessment">04 Results</a>
      </nav>
      {error && (
        <div className="error" role="alert">
          {error}{" "}
          <button onClick={() => setReload((n) => n + 1)}>
            Reload workspace
          </button>
        </div>
      )}
      {notice && (
        <p className="success" role="status">
          {notice}
        </p>
      )}
      <section id="project" className="panel">
        <div className="section-label">01 / Context</div>
        <h2>Start with your project</h2>
        <div className="two-column">
          <div>
            <label>
              Existing project
              <select aria-label="Existing project"
                value={projectId}
                onChange={(e) => selectProject(e.target.value)}
                disabled={!!busy}
              >
                <option value="">Choose a project</option>
                {projects.map((p) => (
                  <option key={p.project_id} value={p.project_id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            {projects.find((p) => p.project_id === projectId)
              ?.business_context && (
              <p>
                {
                  projects.find((p) => p.project_id === projectId)
                    ?.business_context
                }
              </p>
            )}
            {loaded && projects.length === 0 && (
              <p>No projects yet. Create your first assessment workspace.</p>
            )}
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void action("Creating project…", createProject);
            }}
          >
            <label>
              Project name
              <input
                required
                maxLength={200}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label>
              Business context <span>(optional)</span>
              <textarea
                maxLength={4000}
                value={context}
                onChange={(e) => setContext(e.target.value)}
                placeholder="What does your product do? Which analytical data is growing?"
              />
            </label>
            <button disabled={!!busy || !name.trim()}>Create project</button>
          </form>
        </div>
      </section>
      {projectId && <Intake key={projectId} api={api} projectId={projectId}
        context={projects.find(p => p.project_id === projectId)?.business_context ?? ""}
        request={request} onConfirm={(next, id, before) => {
          try {
            if (pretty(JSON.parse(latestDraft.current)) !== before) {
              setError("The draft changed during confirmation. Review and confirm the current requirements again.");
              return;
            }
          } catch { return; }
          const accepted = { id, key: requirementsKey(next) };
          editRequest(next); setAcceptedIntake(accepted);
          if (!token) save(`do:v1:${scope}:intake`, pretty({ ...accepted, projectId }));
        }} />}
      <fieldset disabled={!projectId || !!busy} className="panel" id="input">
        <legend>02 / Dataset evidence</legend>
        <h2>Choose what you share</h2>
        <div className="mode-buttons" role="group" aria-label="Evidence mode">
          {(["raw", "metadata", "startup"] as const).map((m) => (
            <button
              type="button"
              key={m}
              aria-pressed={mode === m}
              onClick={() => {
                setMode(m);
                setConsent(false);
              }}
            >
              {m === "raw"
                ? "Upload data"
                : m === "metadata"
                  ? "Metadata only"
                  : "No dataset yet"}
            </button>
          ))}
        </div>
        {mode === "raw" && (
          <>
            <div className="notice">
              Only your assessment copy is stored, for {retention} days. Source
              files stay untouched. Delete a copy below to revoke access;
              cleanup removes retained artifacts. Raw limit:{" "}
              {(config.max_raw_upload_bytes / 1048576).toFixed(0)} MiB; decoded
              limit: {(config.max_decompressed_bytes / 1048576).toFixed(0)} MiB.
              Limits are provisional.
            </div>
            <div className="two-column">
              <label>
                File format
                <select aria-label="File format"
                  value={format}
                  onChange={(e) => setFormat(e.target.value as typeof format)}
                >
                  <option value="csv">CSV</option>
                  <option value="ndjson">NDJSON</option>
                  <option value="parquet">Parquet</option>
                </select>
              </label>
              <label>
                Retention in days
                <input
                  type="number"
                  min={1}
                  max={30}
                  value={retention}
                  onChange={(e) => setRetention(Number(e.target.value))}
                />
              </label>
            </div>
            <label>
              Dataset file
              <input
                ref={fileInput}
                type="file"
                accept=".csv,.ndjson,.jsonl,.parquet,.gz"
                onChange={(e) => {
                  setFile(e.target.files?.[0] ?? null);
                  setConsent(false);
                }}
              />
            </label>
            {file && file.size > config.max_raw_upload_bytes && (
              <p className="error" role="alert">
                File exceeds the raw upload limit.
              </p>
            )}
            <label className="check">
              <input
                type="checkbox"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
              />
              I reviewed the retention choice and want to transfer this
              assessment copy.
            </label>
            <button
              type="button"
              disabled={
                !file ||
                !consent ||
                retention < 1 ||
                retention > 30 ||
                file.size > config.max_raw_upload_bytes
              }
              onClick={() => void action("Uploading…", upload)}
            >
              Upload and validate
            </button>
            <label>
              Ready dataset
              <select aria-label="Ready dataset"
                value={datasetId}
                onChange={(e) => {
                  setDatasetId(e.target.value);
                  const d = datasets.find(
                    (d) => d.dataset_id === e.target.value,
                  );
                  if (request?.conversion && d?.detected_format)
                    editRequest({
                      ...request,
                      conversion: {
                        ...request.conversion,
                        source: {
                          ...request.conversion.source,
                          format: d.detected_format,
                        },
                      },
                    });
                }}
              >
                <option value="">Choose a validated copy</option>
                {datasets
                  .filter((d) => d.state === "ready")
                  .map((d) => (
                    <option key={d.dataset_id} value={d.dataset_id}>
                      {d.detected_format} · {d.original_bytes ?? "unknown"}{" "}
                      bytes · {d.dataset_id.slice(0, 8)}
                    </option>
                  ))}
              </select>
            </label>
            {chosen && (
              <div>
                <p>
                  Copy expires: {new Date(chosen.expires_at).toLocaleString()}
                </p>
                <button
                  type="button"
                  className="secondary"
                  onClick={() =>
                    void action("Deleting copy…", async () => {
                      await api.call(
                        `/v1/datasets/${datasetId}`,
                        undefined,
                        "DELETE",
                      );
                      setDatasets((prev) =>
                        prev.filter((d) => d.dataset_id !== datasetId),
                      );
                      setDatasetId("");
                      selectAssessment("");
                      setNotice(
                        "Assessment copy deletion requested. External source is untouched.",
                      );
                      setReload((n) => n + 1);
                    })
                  }
                >
                  Delete assessment copy
                </button>
              </div>
            )}
          </>
        )}
        {mode === "metadata" && (
          <>
            <p>
              Run the local profiler and review its JSON report. Field
              statistics and names can still be sensitive. Only reviewed
              metadata transfers; metadata alone cannot establish measured
              savings.
            </p>
            <details>
              <summary>Local profiler instructions</summary>
              <pre>
                data-optimizer profile LOCAL_FILE --format csv --output
                profile.json{`\n`}data-optimizer profile-review profile.json
              </pre>
            </details>
            <label>
              Local profile report
              <input
                type="file"
                accept=".json"
                onChange={(e) =>
                  void action("Reading metadata…", () =>
                    readMetadata(e.target.files?.[0]),
                  )
                }
              />
            </label>
            {metadata && (
              <>
                <details open>
                  <summary>Review metadata before transfer</summary>
                  <pre>{pretty(metadata)}</pre>
                </details>
                <label className="check">
                  <input
                    type="checkbox"
                    checked={reviewed}
                    onChange={(e) => setReviewed(e.target.checked)}
                  />
                  I reviewed these statistics and approve importing this
                  metadata.
                </label>
                <button
                  type="button"
                  disabled={!reviewed}
                  onClick={() =>
                    void action("Importing reviewed metadata…", async () => {
                      const p = await api.call<ProfileRef>(
                        `/v1/projects/${projectId}/profiles`,
                        {
                          report: metadata,
                          reviewed_fingerprint: metadata.profile_fingerprint,
                        },
                      );
                      setProfileId(p.profile_id);
                      setProfiles((prev) => [
                        p,
                        ...prev.filter((x) => x.profile_id !== p.profile_id),
                      ]);
                      setNotice(
                        "Reviewed metadata imported. Raw data was not uploaded.",
                      );
                    })
                  }
                >
                  Import reviewed metadata
                </button>
              </>
            )}
            <label>
              Imported profile
              <select aria-label="Imported profile"
                value={profileId}
                onChange={(e) => setProfileId(e.target.value)}
              >
                <option value="">Choose a metadata profile</option>
                {profiles.map((p) => (
                  <option key={p.profile_id} value={p.profile_id}>
                    Version {p.profile_version} · {p.profile_id.slice(0, 8)}
                  </option>
                ))}
              </select>
            </label>
          </>
        )}
        {mode === "startup" && (
          <p>
            Get useful next questions from your requirements. Without a dataset,
            results are scenario guidance and historical savings remain unknown.
          </p>
        )}
      </fieldset>
      {busy && (
        <div className="working" role="status">
          {busy}
          {uploadPercent !== null && (
            <>
              <progress
                aria-label="File transfer progress"
                max={100}
                value={uploadPercent}
              />
              <span>
                {uploadPercent}% transferred; server validation follows.
              </span>
            </>
          )}
        </div>
      )}
      <fieldset
        className="panel"
        id="requirements"
        disabled={!projectId || !!busy}
      >
        <legend>03 / Requirements & assumptions</legend>
        <h2>Define the test</h2>
        <p>
          Blank fields mean unknown. CSV columns stay text unless you provide
          explicit overrides; IDs and precision are preserved. Choose only
          operations supported by your dataset.
        </p>
        <div className="two-column">
          <label>
            Workload template
            <select
              value=""
              onChange={(e) => {
                if (!request?.conversion) return;
                const queries =
                  e.target.value === "projection"
                    ? [
                        {
                          id: "ids",
                          kind: "projection" as const,
                          columns: ["id"],
                        },
                      ]
                    : e.target.value === "group"
                      ? [
                          {
                            id: "groups",
                            kind: "grouped_aggregate" as const,
                            group_by: ["category"],
                            aggregates: [{ op: "count" as const, alias: "n" }],
                          },
                        ]
                      : e.target.value === "unknown"
                        ? []
                        : [{ id: "scan", kind: "full_scan" as const }];
                editRequest({
                  ...request,
                  conversion: {
                    ...request.conversion,
                    workload: { ...request.conversion.workload, queries },
                  },
                });
              }}
            >
              <option value="">Choose a template to edit</option>
              <option value="scan">Full scan</option>
              <option value="projection">Projection of id</option>
              <option value="group">Counts by category</option>
              <option value="unknown">Workload unknown</option>
            </select>
          </label>
          <label>
            Required retention days <span>(unknown if blank)</span>
            <input
              type="number"
              min={1}
              max={36500}
              value={request?.policy.retention_days ?? ""}
              onChange={(e) => {
                if (request)
                  editRequest({
                    ...request,
                    policy: {
                      ...request.policy,
                      retention_days: e.target.value
                        ? Number(e.target.value)
                        : null,
                    },
                  });
              }}
            />
          </label>
          <label>
            Required freshness seconds <span>(unknown if blank)</span>
            <input
              type="number"
              min={0}
              value={request?.policy.freshness_seconds ?? ""}
              onChange={(e) => {
                if (request)
                  editRequest({
                    ...request,
                    policy: {
                      ...request.policy,
                      freshness_seconds: e.target.value
                        ? Number(e.target.value)
                        : null,
                    },
                  });
              }}
            />
          </label>
          <label>
            Workload replays per month <span>(unknown if blank)</span>
            <input
              type="number"
              min={0}
              value={request?.replays_per_month ?? ""}
              onChange={(e) => {
                if (request)
                  editRequest({
                    ...request,
                    replays_per_month: e.target.value || null,
                  });
              }}
            />
          </label>
        </div>
        <div className="mode-buttons">
          <button
            type="button"
            onClick={() => {
              if (request)
                editRequest({
                  ...request,
                  cost_template: null,
                  policy: { ...request.policy, scenario: "user_scenario" },
                });
            }}
          >
            Leave prices unknown
          </button>
          <button
            type="button"
            onClick={() => {
              if (request)
                editRequest({
                  ...request,
                  cost_template:
                    demo.cost_template as InputAssessmentRequest["cost_template"],
                  policy: { ...request.policy, scenario: demo.policy.scenario },
                  replays_per_month: demo.replays_per_month,
                });
            }}
          >
            Use synthetic cost example
          </button>
        </div>
        <p className="notice">
          {request?.cost_template
            ? "Cost assumptions are active. The synthetic example uses invented amplified storage prices and explicitly zero non-storage usage. Edit all quantities, rates, copies and migration assumptions in JSON for your scenario. This is not a provider quote or observed saving."
            : "Pricing and migration costs are unknown. You can measure bytes and workload timings, but a cost recommendation needs explicit assumptions."}
        </p>
        <details open>
          <summary>Schema, workload & cost editor (JSON)</summary>
          <p>
            Set conversion.source.schema_overrides for typed columns,
            csv_null_tokens for explicit nulls, workload queries and
            target_latency_seconds for performance requirements. The server
            validates the full contract before submission. No arbitrary SQL.
          </p>
          <label>
            Assessment request JSON
            <textarea
              aria-label="Assessment request JSON"
              className="json-editor"
              spellCheck={false}
              value={requestText}
              onChange={(e) => {
                setRequestText(e.target.value);
                setIssues([]);
              }}
              aria-invalid={!!parseError || issues.length > 0}
              aria-describedby="request-errors"
            />
          </label>
          <div id="request-errors">
            {parseError && <p className="error">Invalid JSON: {parseError}</p>}
            {issues.length > 0 && (
              <ul className="error">
                {issues.map((x, i) => (
                  <li key={i}>
                    {x.path || "request"}: {x.code}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <button
            type="button"
            onClick={() =>
              void action("Checking requirements…", async () => {
                if (!request) throw new Error("Correct JSON first.");
                const v = await api.call<{
                  valid: boolean;
                  issues: typeof issues;
                }>("/v1/dashboard/validate", request);
                setIssues(v.issues);
                setNotice(
                  v.valid
                    ? "Request contract is valid. Dataset compatibility is checked by the worker."
                    : "Correct the fields listed in the editor.",
                );
              })
            }
          >
            Validate requirements
          </button>
        </details>
        <button
          type="button"
          className="primary"
          disabled={
            !!parseError ||
            !request ||
            (mode === "raw" && !datasetId) ||
            (mode === "metadata" && !profileId)
          }
          onClick={() => void action("Submitting assessment…", run)}
        >
          Run assessment
        </button>
      </fieldset>
      <section id="assessment" className="panel">
        <div className="section-label">04 / Assessment</div>
        <h2>Follow the evidence</h2>
        <label>
          Assessment history
          <select aria-label="Assessment history"
            value={assessmentId}
            onChange={(e) => selectAssessment(e.target.value)}
          >
            <option value="">Choose an assessment</option>
            {assessmentId &&
              !assessments.some((a) => a.id === assessmentId) && (
                <option value={assessmentId}>
                  {assessmentId.slice(0, 8)} · recovered from this session
                </option>
              )}
            {assessments.map((a) => (
              <option key={a.id} value={a.id}>
                {a.id.slice(0, 8)} ·{" "}
                {a.id === status?.id ? status.status : a.status}
              </option>
            ))}
          </select>
        </label>
        {!assessmentId && (
          <p>
            No assessment selected. Run a new assessment or open one from your
            project history.
          </p>
        )}
        {pollError && (
          <p className="error" role="alert">
            {pollError} Access may have expired or services may be unavailable.{" "}
            <button onClick={() => setPollRetry((n) => n + 1)}>
              Retry status
            </button>
          </p>
        )}
        {assessmentId && !status && !pollError && (
          <p role="status">Loading assessment…</p>
        )}
        {status && (
          <>
            <div className="status-heading" role="status">
              <strong>{status.status.replaceAll("_", " ")}</strong>
              <span>
                {status.progress.stage ?? "Awaiting worker"} · attempt{" "}
                {status.attempts}
              </span>
            </div>
            <p>
              {status.progress.completed_configurations ?? 0} configurations
              completed · {status.progress.completed_trials ?? 0} trial records.
              Counts reflect completed work; no estimated percentage.
            </p>
            {!terminal(status.status) && (
              <>
                <p>
                  Queued work needs the local dispatcher and worker. You can
                  refresh this page safely.
                </p>
                <button
                  disabled={status.cancel_requested || !!busy}
                  onClick={() =>
                    void action("Requesting cancellation…", async () => {
                      const s = await api.call<Status>(
                        `/v1/assessments/${status.id}/cancel`,
                        {},
                      );
                      setStatus(s);
                      setPollRetry((n) => n + 1);
                    })
                  }
                >
                  {status.cancel_requested
                    ? "Cancellation requested…"
                    : "Cancel assessment"}
                </button>
              </>
            )}
            {status.stop_reason && (
              <p>
                Stop reason: {status.stop_reason}.{" "}
                {status.status === "failed"
                  ? "Review schema and workload compatibility, then create a corrected assessment."
                  : "Partial coverage remains explicit in the evidence."}
              </p>
            )}
            <details>
              <summary>Assessment provenance</summary>
              <pre>{pretty(status)}</pre>
            </details>
          </>
        )}
        {report && <>
          <Explanation key={assessmentId + report.report_fingerprint} api={api}
            assessmentId={assessmentId} fingerprint={report.report_fingerprint} />
          <Results report={report} />
          <Handoff key={assessmentId} api={api} assessmentId={assessmentId} />
        </>}
      </section>
    </main>
  );
}
