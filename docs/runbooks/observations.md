# Adoption, manual observations and reassessment (S13)

Run the existing locked local stack (`make infra-up`, `make migrate`, `make seed-local`,
`make storage-init`, `make dev`, dispatcher and worker). Migration
`0008_observations.sql` adds append-only adoption versions, observation revisions and
reassessment links. No provider connector, scheduled notification or production switch runs.

## Adoption and manual entry

Open a completed assessment, then **Adoption & savings history**. A tested `change`
with original cost evidence can create one adoption plan. The selected candidate ID,
configuration, assessment and report fingerprint are fixed. Keep-current and guidance
results can be reassessed, but cannot become a migration plan.

Expand **Adoption plan & deployment status**. Review the JSON, especially
`reference_logical_bytes`: the logical volume of the *original assessed dataset*, using a
consistent definition across periods. The UI proposes original decoded bytes; Parquet or
other sources may need a domain-specific logical-volume measure. Never substitute a larger
production volume for a sample's original reference. Scaling is a declared model, not a
measured production result. The initial reference cannot be edited; use a new assessment if
it was wrong. Provide a private source reference and note with every version.

`examples/s13-adoption.json` and `examples/s13-observation.json` are explicitly invented
manual-entry examples for the six-query tiny fixture, not live observations. Review all
values and dates before using them.

Save `proposed` with `expected_version: 0`; then save `planned` with version 1.
After a deliberate real reader change and validation, record `deployed`, the UTC
`deployed_at`, and the latest expected version. This records the user's assertion only.
Enter `actual_migration_cost` separately in the original price snapshot currency, or leave
null if unknown. Forecast migration cost is never substituted for actual spend. Later versions
can correct that cost with a source/note, retaining the old values. State transitions cannot
skip stages or reverse; the deployment date becomes immutable once supplied.

**New manual observation** prepares a JSON form. **Upload observation JSON** loads a file
(up to 128 KiB) for review; **Save observation revision** submits it. Manual JSON entry and
upload use the same typed validation. Decimal amounts should be quoted strings. Required:

- `period_start` and exclusive `period_end`: past UTC ISO timestamps, positive interval,
  at most 366 days, inside the deployment interval. A partial month is allowed.
- `logical_volume_bytes`: representative average logical volume for this period, using the
  original reference definition; `retained_bytes`: measured physical bytes including the same
  retained copies and metadata. Missing values remain null.
- `workload_replays`: total complete workload replays in this interval. `query_mix`: fractions
  by original query ID. The benchmark executes each query once per replay, so comparable mix
  is equal fractions. Fractions accept 12 decimal places, with 1e-10 sum tolerance and 1e-12
  per-query match tolerance. Changed/unknown mixes need fresh measurement.
- `access_quantities`: period totals in the original baseline charge units, shown under
  **Original baseline billing units**. Non-storage usage such as request counts, network GB,
  retrieval GB, transform compute-hours, maintenance hours and service months must be supplied,
  including confirmed zeros. Storage, copies and query compute use the model described below.
  Quantities for those derived components are ignored; they do not override original evidence.
- `itemized_costs`: all eleven recurring components from the original calculation boundary,
  each with a nonnegative amount or null. All eleven known amounts are needed for a total.
  Enter a confirmed zero explicitly. A partial bill yields a known subtotal and an unknown total.
- `currency`, private `source`, `coverage` (resources, copies, omissions, bill allocation), and
  `note`. These inputs are always **user supplied, not provider verified**.
- Optional original-format `schema_fingerprint` and `input_fingerprint` for drift checks.

The API rejects overlapping active observation periods. Revise an entry with its
`observation_id` and latest `expected_version`; every original payload, author, timestamp
and plan-version reference remains in the audit history. Set `excluded: true` in a revision
to remove an erroneous interval from aggregation without deleting its history. A transport
retry cannot silently double count an overlapping bill; reload history on a 409.

## Calculation and limits

Calculation version is `s13.linear_usage_v1`. It reuses the immutable original selected
scenario's baseline representation, required copies, retention, region, rates and assumptions.
All amounts use Decimal arithmetic under precision 80, with the existing six-place half-even
currency-line rounding. The period model uses an explicit 30-day month; this is not provider
calendar proration. Formula inputs and period baseline line amounts are in the history response.

```text
period_months = exact_period_seconds / (30 * 86400)
volume_ratio = observed_logical_bytes / original_reference_logical_bytes
modeled_baseline_objects = round_half_even(original_object_bytes * volume_ratio)
baseline_query_hours_per_month = original_query_hours_per_month
    * (observed_period_replays / period_months / original_monthly_replays) * volume_ratio
other_usage_per_month = observed_period_quantity / period_months
modeled_savings = modeled_adjusted_baseline_for_period - actual_itemized_cost_for_period
cumulative_benefit = sum(latest non-excluded recorded modeled_savings) - actual_migration_cost
```

Storage retains the original object topology, scaling object bytes linearly. Query CPU scales
linearly only for a matching query mix. Both are **unvalidated counterfactual assumptions**;
changed selectivity, data shape, compression, layout and resource contention can invalidate
them. Usage reduction alone is not attributed to optimization: the unchanged representation
under the reduced usage can produce zero modeled savings. Changed schema suppresses the
baseline; changed input is advisory because volume changes can still be modeled. Billing
minimums, out-of-range modeled quantities, missing rates/usage, and changed/unknown query mix
suppress the modeled total. Fixed/shared/provisioned commitments remain at their original
monthly quantity, independent of used bytes and replay counts.

The history displays separate actual costs (observation currency), original candidate cost
projection (original usage, prorated to this interval), modeled adjusted baseline and modeled
savings (original model currency). Currency mismatch suppresses savings; no FX conversion.
Negative savings and negative cumulative benefit are preserved. Excluded entries and periods
outside a reverted deployment do not produce savings. Cumulative benefit is unknown if any
active period's savings or actual migration cost is unknown. It covers only recorded intervals;
gaps are not estimated, and migration spend is deducted once. It is never a verified invoice
saving, complete lifetime total, causal claim or automatic payback measurement.

## Reconciliation and reverting

Match the provider bill's period, account, region, currency, storage classes, required copies,
resource IDs, taxes/discount exclusions and shared-capacity allocation to the assessment
boundary. Retain the bill privately and enter only a suitable reference. Check every line,
including explicit zero charges; do not equate physical byte reductions to capacity savings.
Record missing allocations in coverage and leave their amounts null. Compare the original
projection with actual cost for forecast error, then inspect the adjusted baseline and all
attribution assumptions before interpreting modeled savings. No bills were provider verified
in S13's synthetic test scenarios.

If the real change is reverted, follow the S12 source/reader validation and rollback runbook,
then append a `reverted` adoption version with the original deployment timestamp and a past
UTC `reverted_at`. Both dates are immutable thereafter. New observations must end at or before
that instant. Existing entries crossing it remain in history with unknown savings; split/revise
or exclude them to restore comparable period coverage. A new deployment needs a new
assessment/plan. This app never switches readers or deletes source data.

## Manual reassessment and drift

Enter a reason and choose **Prepare reassessment** on any saved result. The UI loads the
original executable request and input references. Review the dataset or reviewed metadata,
workload, requirements and prices; explicitly click **Run assessment**. The standard quota,
validation, confirmation, idempotency and worker pipeline creates a different immutable ID and
requirements snapshot. No assessment or plan is overwritten. Edited requirements require a
new confirmation if using optional intake. Ordinary pre-S13 submission digests remain stable.
Local demo drafts keep the parent/reason in scoped session storage; JWT drafts stay in memory.

The result compares version IDs, input and price fingerprints, decision and selected horizon
cost. Different usage/prices/currencies are independent evidence, not directly subtractable
savings. If prior evidence has expired or its input/project was deleted, owned comparison is
unavailable under the existing retention policy; no access bypass is introduced. Choose
assessment-copy retention up front to cover the intended observation period (default seven
days). This sprint does not silently prolong raw retention or offer long-term history after
assessment expiry; a separate metadata-retention design remains future work.

Supported advisory signals: >=20% logical-volume change, >=20% replay-rate change, >=20%
retained-byte divergence from the scaled candidate, changed query mix, missing retained-byte
measurement, supplied schema/input fingerprint changes, and original price snapshot >=90 days
old at period end. Thresholds are transparent heuristics, not calibrated staleness probabilities.
There is no scheduled job, external notification or automatic reassessment.

## APIs and verification

All endpoints require the same verified owner identity as assessments. Ownership, input/project
deletion and retention are rechecked for history and writes. Missing/foreign/expired resources
return 404; invalid entries/transitions 422; stale versions/overlaps 409; body cap 413.

| Method/path | Purpose |
| --- | --- |
| POST `/v1/assessments/{id}/migration-plan` | Append proposed/state/cost version with expected version |
| GET `/v1/assessments/{id}/migration-plan` | Plan, versions, revisions and calculated current history, or `plan: null` |
| POST `/v1/migration-plans/{id}/observations` | Append new observation or revision |
| GET `/v1/migration-plans/{id}/history` | Original references, audit input history, totals, assumptions and drift |
| POST `/v1/assessments` | Optional paired `reassessment_of` and `reassessment_reason`; same-project owned parent required |
| GET `/v1/assessments/{id}/comparison` | Parent/current independent evidence comparison |

Migration tables reject SQL UPDATE and DELETE through triggers. Existing assessment inputs and
evidence protections stay in force. Logical copy/project deletion revokes access; metadata/audit
rows remain in PostgreSQL under existing tombstone policy. No raw data, bill attachment or
external credentials are stored by manual entry. Private source/coverage notes are sensitive;
review before sharing API history or screenshots.

Run `make check`, `make test`, `make build`, the targeted integration file
`backend/tests/integration/test_observations_api.py`, and `make test-observations-browser`.
The latter uses isolated PostgreSQL/MinIO/Redis/worker/Chrome and real Docker assessments,
with invented manual adoption/bill entries. See [evidence](../evidence/s13-verification.md).
