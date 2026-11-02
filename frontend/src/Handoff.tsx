import { useState } from "react";
import { Api, errorText } from "./api";

type Grant = {
  expires_at: string;
  bundle_fingerprint: string;
  links: Record<"zip" | "json" | "markdown" | "html", string>;
};

export default function Handoff({ api, assessmentId }: { api: Api; assessmentId: string }) {
  const [grant, setGrant] = useState<Grant | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function prepare() {
    setBusy(true);
    setError("");
    setGrant(null);
    try {
      setGrant(await api.call<Grant>(`/v1/assessments/${assessmentId}/handoff`, {}));
    } catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  }
  async function download(kind: keyof Grant["links"]) {
    if (!grant) return;
    setBusy(true);
    setError("");
    try { await api.download(grant.links[kind], {
      zip: "handoff.zip", json: "bundle.json", markdown: "report.md", html: "report.html",
    }[kind]); }
    catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  }
  return <section aria-labelledby="handoff-title">
    <h3 id="handoff-title">Engineering handoff</h3>
    <p>Export the measured evidence, costs, reproduction commands and rollback instructions.
      Schema and workload parameters may be sensitive; review before sharing.
      Migration creates a local copy and requires a separate deliberate reader switch.</p>
    <button onClick={() => void prepare()} disabled={busy}>
      {busy ? "Preparing download…" : "Prepare expiring report links"}
    </button>
    {grant && <>
      <p>Links expire at {new Date(grant.expires_at).toLocaleString()} and require your session.
        Prepare new links if they expire.</p>
      <div className="actions">
        {(["zip", "json", "markdown", "html"] as const).map(kind =>
          <button key={kind} disabled={busy} onClick={() => void download(kind)}>
            Download {kind === "zip" ? "complete bundle (ZIP)" : kind.toUpperCase()}
          </button>)}
      </div>
      <p>Bundle fingerprint: <code>{grant.bundle_fingerprint}</code></p>
    </>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
