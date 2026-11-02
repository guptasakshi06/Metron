import { useEffect, useRef, useState } from "react";
import type { InputAssessmentRequest, AssistIntakeResult } from "./contracts.generated";
import { Api, assistanceStatus, errorText, pretty } from "./api";

export default function Intake({ api, projectId, context, request, onConfirm }: {
  api: Api; projectId: string; context: string; request: InputAssessmentRequest | null;
  onConfirm: (request: InputAssessmentRequest, id: string, before: string) => void;
}) {
  const active = useRef(true);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  const [description, setDescription] = useState(context);
  const [proposal, setProposal] = useState<AssistIntakeResult | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [approved, setApproved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  async function action(fn: () => Promise<void>) {
    setBusy(true); setMessage("");
    try { await fn(); } catch (e) { setMessage(errorText(e)); }
    finally { setBusy(false); }
  }
  function show(result: AssistIntakeResult) {
    setProposal(result); setApproved(false);
    setValues(Object.fromEntries(result.fields.map(f => [f.field, String(f.value)])));
  }
  return <div className="notice" aria-label="Requirement assistance">
    <h3>Clarify requirements (optional)</h3>
    <p>Works without an AI key. Review explicit retention in days and freshness in seconds.
      Other requirements stay in the workload editor. Proposals are assumptions until confirmed.</p>
    <label>Assistance description
      <textarea maxLength={4000} value={description} disabled={busy}
        onChange={e => { setDescription(e.target.value); setProposal(null); setApproved(false); }} />
    </label>
    <button type="button" disabled={busy || !request || !description.trim()}
      onClick={() => void action(async () => {
        show(await api.call<AssistIntakeResult>(`/v1/projects/${projectId}/intake`, { description, request }));
      })}>Review requirement proposals</button>
    {proposal && <>
      <p>{proposal.assumption} {assistanceStatus(proposal.status)}</p>
      {proposal.source === "deterministic" && proposal.status !== "not_requested" &&
        <p>AI assistance was unavailable. The deterministic review remains usable.</p>}
      {proposal.fields.map(f => <label key={f.field}>
        Proposed {f.field === "retention_days" ? "retention days" : "freshness seconds"}
        <input type="number" min={f.field === "retention_days" ? 1 : 0} max={36500}
          value={values[f.field] ?? ""} disabled={busy}
          onChange={e => setValues(v => ({ ...v, [f.field]: e.target.value }))} />
        <span>From: “{f.source_quote}”. Clear the value to keep it unknown.</span>
      </label>)}
      {Object.entries(proposal.questions).map(([key, text]) => <p key={key}>{text}</p>)}
      <details><summary>Review summary that optional AI receives</summary>
        <pre>{pretty(proposal.summary)}</pre>
      </details>
      <p>Only this reviewed description and allowed fields/questions are sent.
        Remove sensitive details. Files, raw records and query text are excluded.</p>
      <label className="check"><input type="checkbox" checked={approved} disabled={busy}
        onChange={e => setApproved(e.target.checked)} />
        I approve sending this summary to the configured AI provider.</label>
      <button type="button" disabled={busy || !approved} onClick={() => void action(async () => {
        show(await api.call<AssistIntakeResult>(`/v1/projects/${projectId}/intake/${proposal.id}/refine`,
          { approved_summary_fingerprint: proposal.summary_fingerprint }));
      })}>Refine reviewed summary with AI</button>
      <button type="button" disabled={busy || !request} onClick={() => void action(async () => {
        if (!request) return;
        const next = { ...request, policy: { ...request.policy } };
        for (const f of proposal.fields) {
          const raw = values[f.field] ?? "";
          next.policy[f.field] = raw === "" ? null : Number(raw);
        }
        const confirmation = await api.call<{ id: string; version: number }>(
          `/v1/projects/${projectId}/intake/${proposal.id}/confirm`, { request: next });
        if (active.current) onConfirm(next, confirmation.id, pretty(request));
        setMessage(`Requirements version ${confirmation.version} confirmed. Original description is preserved.`);
      })}>Confirm and apply reviewed requirements</button>
    </>}
    {busy && <p role="status">Reviewing requirements…</p>}
    {message && <p role="status">{message}</p>}
  </div>;
}
