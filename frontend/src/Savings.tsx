import { useEffect, useState } from "react";
import { Api, errorText, pretty } from "./api";
import type { ResultAssessmentReport } from "./api";
import type { AdoptionPlanInput, ObservedObservationInput } from "./contracts.generated";

type Revision = { version: number; payload: AdoptionPlanInput; created_at: string; actor_principal_id: string };
type Entry = {
  id: string; version: number; plan_version: number; payload: ObservedObservationInput;
  calculation: {
    actual_currency: string; model_currency: string; actual_cost: string | null; actual_known_subtotal: string;
    original_projected_cost: string | null; modeled_adjusted_baseline: string | null;
    modeled_savings: string | null; missing_inputs: string[]; drift_signals: string[];
    assumptions: string[];
  };
};
type History = {
  plan: null | { id: string; assessment_id: string; report_fingerprint: string; candidate_id: string; configuration: unknown };
  versions?: Revision[]; observations?: Entry[]; observation_revisions?: unknown[];
  cumulative_modeled_benefit?: string | null; currency?: string; cumulative_scope?: string;
};
type Comparison = {
  previous: null | Version; current?: Version; reason?: string; limitation?: string;
};
type Version = {
  id: string; status: string; input_fingerprint: string; request_fingerprint: string;
  price_snapshot_ids: string[];
  decision: ResultAssessmentReport["decision"] | null;
};
const amount = (value: string | null | undefined, currency: string | undefined) =>
  value == null ? "Unknown" : `${value} ${currency ?? ""}`;
const recurring = ["storage", "query_compute", "transform_compute", "read_requests", "write_requests",
  "retrieval", "network", "backups", "replicas", "maintenance", "service"] as const;

export default function Savings({ api, assessmentId, report, onReassess }: {
  api: Api; assessmentId: string; report: ResultAssessmentReport;
  onReassess: (reason: string) => void;
}) {
  const [history, setHistory] = useState<History | null>(null);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [planText, setPlanText] = useState(() => pretty({
    expected_version: 0, state: "proposed", reference_logical_bytes: report.profile?.decoded_bytes ?? null,
    deployed_at: null, reverted_at: null, actual_migration_cost: null,
    source: "Manual adoption record", note: "Review target reader, validation and rollback before deployment.",
  }));
  const [observationText, setObservationText] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    Promise.all([
      api.call<History>(`/v1/assessments/${assessmentId}/migration-plan`),
      api.call<Comparison>(`/v1/assessments/${assessmentId}/comparison`),
    ]).then(([h, c]) => {
      if (!active) return;
      setHistory(h); setComparison(c); setError("");
      const last = h.versions?.at(-1);
      if (last) setPlanText(pretty({ ...last.payload, expected_version: last.version }));
    }).catch(e => { if (active) setError(errorText(e)); });
    return () => { active = false; };
  }, [api, assessmentId, revision]);
  async function perform(action: () => Promise<void>) {
    setBusy(true); setError(""); setNotice("");
    try { await action(); setRevision(n => n + 1); }
    catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  }
  function newObservation() {
    const cost = report.costs[report.decision.selected_candidate_id ?? ""];
    const scenario = cost?.request.scenarios.find(s => s.name === report.request.policy.scenario);
    const queries = report.request.conversion?.workload?.queries ?? [];
    setObservationText(pretty({
      expected_version: 0, period_start: null, period_end: null,
      currency: scenario?.prices.currency ?? "USD", retained_bytes: null,
      logical_volume_bytes: null, workload_replays: null,
      query_mix: Object.fromEntries(queries.map(q => [q.id, null])),
      access_quantities: Object.fromEntries((scenario?.baseline.recurring ?? [])
        .filter(c => c.quantity && c.basis === "usage" && c.component !== "query_compute")
        .map(c => [c.component, null])),
      itemized_costs: Object.fromEntries(recurring.map(c => [c, null])),
      source: "Manual bill or measurement reference", coverage: "Describe included resources, copies and gaps",
      note: "User supplied; not provider verified", excluded: false,
    }));
  }
  const currency = history?.currency;
  return <section aria-labelledby="savings-title" className="savings">
    <h3 id="savings-title">Adoption & savings history</h3>
    <p>Manual observations are user supplied, not provider verified. Adjusted savings use a modeled
      baseline under comparable observed usage. Lower usage alone does not establish optimization savings.</p>
    {report.decision.outcome === "change" ? <>
      <details>
        <summary>Adoption plan & deployment status</summary>
        <p>Start proposed, then planned, deployed and optionally reverted. Record UTC deployment/revert dates
          after the real reader change. Source and validation remain your responsibility.</p>
        <p>Reference logical bytes must describe the original assessment data, not compressed retained bytes.
          Actual migration cost is a separate user-supplied total in the original model currency;
          leave it null until known. Original evidence and dates stay immutable.</p>
        <label>Adoption plan JSON<textarea aria-label="Adoption plan JSON" className="json-editor" value={planText}
          onChange={e => setPlanText(e.target.value)} spellCheck={false} /></label>
        <button disabled={busy} onClick={() => void perform(async () => {
          await api.call(`/v1/assessments/${assessmentId}/migration-plan`, JSON.parse(planText));
          setNotice("Adoption version saved.");
        })}>Save adoption version</button>
      </details>
      {history?.plan && <>
        <p>Adoption state: <strong data-testid="adoption-state">{history.versions?.at(-1)?.payload.state}</strong>
          {" · "}Version {history.versions?.at(-1)?.version} · Currency {currency}</p>
        <p>Migration-adjusted benefit for recorded periods: <strong data-testid="cumulative-benefit">
          {amount(history.cumulative_modeled_benefit, currency)}</strong></p>
        <p>{history.cumulative_scope}</p>
        <div className="actions">
          <button disabled={busy} onClick={newObservation}>New manual observation</button>
          <label>Upload observation JSON<input type="file" accept=".json,application/json"
            onChange={e => {
              const file = e.target.files?.[0];
              if (file) void perform(async () => {
                if (file.size > 131072) throw new Error("Observation exceeds 128 KiB.");
                setObservationText(pretty(JSON.parse(await file.text())));
                setNotice("File loaded for review. Save to submit.");
              });
            }} /></label>
        </div>
        {observationText && <>
          <p>Use UTC ISO dates with an exclusive period end. Enter logical/retained volume in bytes;
            workload replays and access quantities are period totals in the original charge units.
            Query mix uses original query IDs and fractions totaling 1. Null means unknown;
            enter 0 only when the bill confirms no charge. All eleven costs are required for an actual total.</p>
          <details><summary>Original baseline billing units</summary><pre>{pretty(
            report.costs[report.decision.selected_candidate_id ?? ""]?.request.scenarios
              .find(s => s.name === report.request.policy.scenario)?.baseline.recurring
          )}</pre></details>
          <label>Observation JSON<textarea aria-label="Observation JSON" className="json-editor" value={observationText}
            onChange={e => setObservationText(e.target.value)} spellCheck={false} /></label>
          <button disabled={busy} onClick={() => void perform(async () => {
            await api.call(`/v1/migration-plans/${history.plan!.id}/observations`, JSON.parse(observationText));
            setObservationText(""); setNotice("Observation revision saved.");
          })}>Save observation revision</button>
        </>}
        <div className="table-wrap"><table>
          <caption>User-supplied observations and modeled attribution · exact API amounts</caption>
          <thead><tr><th>Period (UTC)</th><th>Actual cost</th><th>Original projection</th>
            <th>Modeled adjusted baseline</th><th>Modeled savings</th><th>History</th></tr></thead>
          <tbody>{history.observations?.map(entry => <tr key={entry.id} data-testid="observation-row">
            <td>{entry.payload.period_start} – {entry.payload.period_end}<br />
              {entry.payload.retained_bytes ?? "Unknown"} retained bytes<br />
              {entry.payload.logical_volume_bytes ?? "Unknown"} logical bytes
              {entry.payload.excluded && <strong> Excluded</strong>}</td>
            <td>{amount(entry.calculation.actual_cost, entry.calculation.actual_currency)}
              {entry.calculation.actual_cost == null && <p>Known subtotal: {amount(
                entry.calculation.actual_known_subtotal, entry.calculation.actual_currency)}</p>}</td>
            <td>{amount(entry.calculation.original_projected_cost, currency)}</td>
            <td>{amount(entry.calculation.modeled_adjusted_baseline, currency)}</td>
            <td>{amount(entry.calculation.modeled_savings, currency)}</td>
            <td><button disabled={busy} onClick={() => setObservationText(pretty({
              ...entry.payload, observation_id: entry.id, expected_version: entry.version,
            }))}>Revise observation {entry.version}</button></td>
          </tr>)}</tbody>
        </table></div>
        {history.observations?.map(entry => <details key={entry.id}>
          <summary>Attribution, drift & source · {entry.payload.period_start}</summary>
          <p>{entry.payload.source} · {entry.payload.coverage} · {entry.payload.note}</p>
          <p>Missing or incompatible inputs: {entry.calculation.missing_inputs.join(", ") || "None"}</p>
          <p>Drift signals: {entry.calculation.drift_signals.join(", ") || "None detected in supplied metadata"}</p>
          {entry.calculation.assumptions.map(a => <p key={a}>{a}</p>)}
        </details>)}
        <details><summary>Immutable input & edit audit history</summary>
          <pre>{pretty({ original: history.plan, adoption: history.versions,
            observations: history.observation_revisions })}</pre>
        </details>
      </>}
    </> : <p>An adoption plan requires a tested change with original cost evidence.</p>}
    <h4>Deliberate reassessment</h4>
    <p>Prepare the original request, then review data, workload and prices in the editor above.
      Run assessment creates a new immutable version. Existing evidence remains available.</p>
    <label>Reason for reassessment<input value={reason} maxLength={2000}
      onChange={e => setReason(e.target.value)} placeholder="Describe changed data, workload or prices" /></label>
    <button disabled={busy || !reason.trim()} onClick={() => onReassess(reason.trim())}>
      Prepare reassessment</button>
    {comparison?.previous && <details open><summary>Assessment version comparison</summary>
      <p>{comparison.reason} · {comparison.limitation}</p>
      {[comparison.previous, comparison.current!].map(v => {
        const selected = v.decision?.candidates.find(c => c.candidate_id === v.decision?.selected_candidate_id);
        return <div key={v.id}><p><code>{v.id}</code> · {v.status} · {v.decision?.outcome ?? "Pending"}</p>
          <p>Selected horizon cost: {amount(selected?.horizon_total, selected?.costs?.currency)}</p>
          <p>Input: <code>{v.input_fingerprint}</code></p>
          <p>Prices: {v.price_snapshot_ids.join(", ") || "Unknown"}</p></div>;
      })}
    </details>}
    <button disabled={busy} onClick={() => setRevision(n => n + 1)}>Reload savings history</button>
    {busy && <p role="status">Saving manual record…</p>}
    {notice && <p role="status">{notice}</p>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
