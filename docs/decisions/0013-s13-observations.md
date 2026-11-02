# Decision 0013: append-only manual adoption and comparable-usage models

Date: 2026-11-02 (Asia/Kolkata)

Keep the selected S12 assessment/report/configuration fixed in a tenant-owned migration plan.
Append optimistic-versioned proposed/planned/deployed/reverted records and manual observation
revisions, each with actor/time/source/coverage. Database triggers forbid updates/deletes;
parent assessment row locks serialize plan/revision/period admission. Reject overlapping active
periods; preserve excluded/revised originals. Retention/deletion gates remain inherited from
the owned assessment. This is a record of user assertions, not a production deployment agent.

Reuse original S07 itemized tariffs and footprint/copy assumptions for an explicitly modeled
30-day-month comparable-usage baseline. Linear volume and same-mix replay scaling are unvalidated
assumptions, so publish them with line items and conservative unknowns. Keep fixed commitments
constant. Do not use an unadjusted pre-change bill as the counterfactual. Separate actual bill
cost, original projection, modeled savings, and recorded-period cumulative benefit after a
single user-supplied actual migration cost. Currency mismatch, missing inputs and incompatible
mix/schema/topology suppress attribution; negative outcomes remain visible. No provider verified
or causal savings claim, FX, billing-minimum topology model or unsupported tariff extension.

Deliberate reassessment extends the existing submission contract with an owned same-project
parent and reason, stored transactionally as an immutable link. Existing idempotency digests
stay stable when those fields are absent. Use the real asynchronous pipeline and compare saved
versions; do not update old evidence or launch automatically on advisory drift. No scheduler,
notifications, new dependency, stack change, external service or paid/public deployment.

The technical dashboard retains its existing reviewable JSON editing approach and adds bounded
manual-file review, revision/history controls and separate exact API amounts. See
[runbook](../runbooks/observations.md) and [verification](../evidence/s13-verification.md).
