import { useEffect, useState } from "react";
import { Api, assistanceStatus, errorText, pretty } from "./api";

type ExplanationResult = {
  source: "provider" | "deterministic"; status: string;
  report_fingerprint: string; summary_fingerprint: string; summary: unknown;
  cards: Array<{ candidate_id: string | null; evidence_id: string; reason: string; text: string }>;
};
export default function Explanation({ api, assessmentId, fingerprint }: {
  api: Api; assessmentId: string; fingerprint: string;
}) {
  const [result, setResult] = useState<ExplanationResult | null>(null);
  const [approved, setApproved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    api.call<ExplanationResult>(`/v1/assessments/${assessmentId}/explanation`)
      .then(r => { if (active && r.report_fingerprint === fingerprint) setResult(r); })
      .catch(e => { if (active) setError(errorText(e)); });
    return () => { active = false; };
  }, [api, assessmentId, fingerprint, retry]);
  return <div className="notice" aria-label="Grounded explanation">
    <h3>Understand the evidence</h3>
    <p>Statements link to the immutable report. Calculated values appear in the comparison below.</p>
    {error && <p role="alert">{error} <button type="button" onClick={() => {
      setError(""); setRetry(n => n + 1);
    }}>Retry explanation</button></p>}
    {result && <>
      <p>{assistanceStatus(result.status)}
        {result.source === "deterministic" && result.status !== "not_requested" &&
          " AI is unavailable; checked evidence guidance is shown."}</p>
      {result.cards.map((card, i) => <p key={i}>{card.text}<br />
        {card.candidate_id && <>Candidate: <code>{card.candidate_id}</code><br /></>}
        Evidence: <code>{card.evidence_id}</code></p>)}
      <details><summary>Review explanation summary for optional AI</summary>
        <pre>{pretty(result.summary)}</pre>
      </details>
      <label className="check"><input type="checkbox" checked={approved} disabled={busy}
        onChange={e => setApproved(e.target.checked)} />
        I approve sending these evidence references to the configured AI provider.</label>
      <button type="button" disabled={!approved || busy} onClick={async () => {
        setBusy(true); setError("");
        try {
          const r = await api.call<ExplanationResult>(`/v1/assessments/${assessmentId}/explanation`,
            { approved_summary_fingerprint: result.summary_fingerprint });
          if (r.report_fingerprint === fingerprint) setResult(r);
          setApproved(false);
        } catch (e) { setError(errorText(e)); }
        finally { setBusy(false); }
      }}>{busy ? "Preparing explanation…" : "Prioritize evidence with AI"}</button>
    </>}
  </div>;
}
