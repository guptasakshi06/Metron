import type { ResultAssessmentReport } from "./api";
import { pretty } from "./api";
const value = (n: string | number | null | undefined, suffix = "") =>
  n == null ? "Unknown" : `${n}${suffix}`;
const labels = {
  change: "A tested change is worth considering",
  keep_current: "Keep your current representation",
  insufficient_evidence: "More evidence is needed",
};
export default function Results({
  report,
}: {
  report: ResultAssessmentReport;
}) {
  const d = report.decision;
  const prices = report.request.cost_template?.scenarios ?? [];
  return (
    <section className="results" aria-labelledby="result-title">
      <div className="section-label">04 / Decision & evidence</div>
      <div className={`decision ${d.outcome}`}>
        <span className="badge">{d.outcome.replaceAll("_", " ")}</span>
        <h2 id="result-title">{labels[d.outcome]}</h2>
        <p>{d.reason}</p>
      </div>
      <div className="evidence-strip">
        <span>
          Measurement:{" "}
          {report.evidence === "scenario_guidance"
            ? "Scenario guidance only"
            : "Uploaded sample · local worker"}
        </span>
        <span>Costs: modeled projections</span>
        <span>Production observations: unavailable</span>
      </div>
      {prices.map((s) => (
        <div className="notice" key={s.name}>
          <strong>
            {s.prices.source === "synthetic"
              ? "Synthetic pricing · invented rates"
              : "User-supplied pricing · unverified provider rates"}
          </strong>
          <p>{s.assumption}</p>
          <p>
            {s.prices.provider} / {s.prices.region} / {s.prices.currency} ·
            effective {s.prices.effective_at} · snapshot {"see itemized costs"}
          </p>
        </div>
      ))}
      {d.next_questions.length > 0 && (
        <div className="notice">
          <h3>Next steps</h3>
          <ul>
            {d.next_questions.map((q) => (
              <li key={q}>{q}</li>
            ))}
          </ul>
          <p>
            Edit the requirements below and run a new assessment. Existing
            evidence stays immutable.
          </p>
        </div>
      )}
      {report.profile && (
        <p>
          Profile: {report.profile.evidence} ·{" "}
          {report.profile.raw_data_inspected_by_server
            ? "raw data inspected by server"
            : "locally supplied metadata; raw data not inspected by server"}
          . Coverage and sampling details are in the evidence below.
        </p>
      )}
      {d.candidates.length > 0 && (
        <div
          className="table-wrap"
          tabIndex={0}
          role="region"
          aria-label="Candidate comparison, scroll horizontally"
        >
          <table>
            <caption>
              Best tested feasible options ·{" "}
              {report.request.cost_template?.horizon_months ?? "unknown"} month
              horizon
            </caption>
            <thead>
              <tr>
                <th>Representation</th>
                <th>Feasibility</th>
                <th>Physical data bytes</th>
                <th>Observed workload seconds</th>
                <th>Horizon total + migration</th>
              </tr>
            </thead>
            <tbody>
              {d.candidates.map((c) => {
                const manifest = report.benchmark?.manifests.find(
                  (m) => m.key === c.candidate_id,
                );
                return (
                  <tr
                    key={c.candidate_id}
                    className={
                      c.candidate_id === d.selected_candidate_id
                        ? "selected"
                        : ""
                    }
                  >
                    <th scope="row">
                      {c.configuration.baseline ? "Baseline · " : ""}
                      {c.configuration.format} / {c.configuration.codec}
                      {c.candidate_id === d.selected_candidate_id && (
                        <span className="badge">Selected</span>
                      )}
                      <small>{c.candidate_id.slice(0, 12)}</small>
                    </th>
                    <td>{c.feasibility}</td>
                    <td>{value(manifest?.physical_bytes)}</td>
                    <td>
                      {value(c.workload_seconds)}
                      <small>
                        Range{" "}
                        {c.observed_range_seconds?.join(" – ") ?? "Unknown"};
                        local load + queries
                      </small>
                    </td>
                    <td>
                      {value(c.horizon_total)} {c.costs?.currency}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {d.candidates.map((c) => (
        <details key={c.candidate_id}>
          <summary>
            {c.configuration.baseline
              ? "Baseline"
              : c.configuration.format + " / " + c.configuration.codec}{" "}
            · feasibility & costs · {c.candidate_id.slice(0, 8)}
          </summary>
          <ul>
            {c.coverage.map((x, i) => (
              <li key={i}>
                <strong>
                  {x.requirement}: {x.status}
                </strong>{" "}
                — {x.reason}
              </li>
            ))}
          </ul>
          <p>Evidence IDs: {c.evidence_ids.join(", ") || "None"}</p>
          {c.costs && (
            <>
              <dl className="metrics">
                <div>
                  <dt>Monthly recurring total</dt>
                  <dd>
                    {value(
                      c.configuration.baseline
                        ? c.costs.baseline.total
                        : c.costs.candidate.total,
                    )}{" "}
                    {c.costs.currency}
                  </dd>
                </div>
                <div>
                  <dt>One-time migration forecast</dt>
                  <dd>
                    {c.configuration.baseline
                      ? "0 (baseline stays in place)"
                      : value(c.costs.migration_forecast.total)}{" "}
                    {c.costs.currency}
                  </dd>
                </div>
                <div>
                  <dt>Horizon net savings</dt>
                  <dd>
                    {c.configuration.baseline
                      ? "Not applicable to baseline"
                      : value(c.costs.horizon_net_savings)}{" "}
                    {c.costs.currency}
                  </dd>
                </div>
                <div>
                  <dt>Payback months</dt>
                  <dd>
                    {c.configuration.baseline
                      ? "Not applicable to baseline"
                      : value(c.costs.payback_months)}
                  </dd>
                </div>
                <div>
                  <dt>Migration peak bytes</dt>
                  <dd>
                    {c.configuration.baseline
                      ? "Not applicable to baseline"
                      : value(c.costs.space.migration_peak_bytes)}
                  </dd>
                </div>
              </dl>
              <p>
                {c.configuration.baseline
                  ? "Baseline has no migration. The monthly operating breakdown below uses the same comparison boundary."
                  : c.costs.payback_reason}
              </p>
              <div
                className="table-wrap"
                tabIndex={0}
                role="region"
                aria-label="Itemized costs"
              >
                <table>
                  <caption>
                    Modeled cost line items · exact API amounts (
                    {c.costs.currency})
                  </caption>
                  <thead>
                    <tr>
                      <th>Scope</th>
                      <th>Component</th>
                      <th>Quantity / unit</th>
                      <th>Amount</th>
                      <th>Missing inputs</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(c.configuration.baseline
                      ? (["baseline"] as const)
                      : ([
                          "baseline",
                          "candidate",
                          "migration_forecast",
                        ] as const)
                    ).flatMap((scope) =>
                      c.costs![scope].items.map((item, i) => (
                        <tr key={scope + i}>
                          <td>{scope}</td>
                          <th scope="row">{item.component}</th>
                          <td>
                            {value(item.quantity)} {item.unit}
                          </td>
                          <td>{value(item.amount)}</td>
                          <td>{item.missing_inputs.join("; ") || "None"}</td>
                        </tr>
                      )),
                    )}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </details>
      ))}
      {report.candidates?.candidates
        .filter((c) => c.status !== "eligible")
        .map((c, i) => (
          <p key={i}>
            Excluded {c.configuration.format}/{c.configuration.codec}:{" "}
            {c.reasons?.join("; ")}
          </p>
        ))}
      <h3>Coverage & limitations</h3>
      <ul>
        {d.limitations.map((l) => (
          <li key={l}>{l}</li>
        ))}
      </ul>
      <p>
        Performance scope: {d.performance_scope}. OS cache is uncontrolled;
        production concurrency and tail latency are unvalidated.
      </p>
      {report.search && (
        <p>
          Search stopped: {report.search.stop_reason}.{" "}
          {report.search.history?.length ?? 0} configurations tested. Best
          tested feasible does not imply global optimality.
        </p>
      )}
      <details>
        <summary>Raw evidence & reproducibility metadata</summary>
        <p>
          Report fingerprint: <code>{report.report_fingerprint}</code>
        </p>
        <h3>Environment</h3>
        <pre>
          {pretty(report.benchmark?.environment ?? { status: "No benchmark" })}
        </pre>
        <h3>Complete API evidence</h3>
        <pre>{pretty(report)}</pre>
      </details>
    </section>
  );
}
