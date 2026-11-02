# S07 pricing and cost method

`s07.1` computes itemized **forecasts** from explicit usage, retained copies and an embedded
immutable price snapshot. It does not choose a candidate or fetch a provider catalog.
No key, database, object storage or network access is required. S08 owns ranking; S09 owns
authenticated persistence. The original S01 `domain.contracts.PriceSnapshot` remains a
descriptive compatibility contract; executable economics uses `pricing.models.PriceSnapshot`.

## Run

After the existing locked setup, from the repository root:

```bash
export PATH="$PWD/.tools/uv-bin:$PATH"
uv run --locked --project backend data-optimizer cost \
  --request examples/s07-cost-request.json --output /tmp/s07-cost.json
```

Choose a new output filename on every run. Publication uses an atomic hard link and never
overwrites an input, previous report or existing file. Exit 0 means all cost/space inputs
are supplied, **not** that migration is recommended; exit 1 saves a report with missing
inputs; exit 2 means invalid inputs, unsupported tariff/unit/commitment changes or an
unavailable output path. A report embeds its complete normalized request, snapshots,
sources, assumptions, formulas, line items and request/report SHA-256 fingerprints.
Fingerprints detect changed content; they do not authenticate supplied measurements or bills.

## Prices, units and provenance

`examples/s07-synthetic-prices.json` contains entirely invented USD rates in the
`synthetic-local` region. The example request embeds that same snapshot. Its effective and
retrieval dates are fixture metadata, not evidence of a provider retrieval. Nothing is
relabeled as a live quote. There is no real provider adapter in S07.

Snapshots are frozen typed objects containing provider, region, currency, UTC effective and
retrieval dates, source references, assumptions and a tuple of unique rate IDs. Their ID
is the hash of all normalized fields. Altering a rate, discount, date or region creates a
different ID. Rates inherit the snapshot currency and region. A comparison uses one snapshot
for both configurations. Ranges require one currency; there is no exchange-rate conversion.
User supplied catalogs stay labeled `user_supplied`, never provider verified.

Supported units are `GB_month`, `GiB_month`, `compute_hour`, `request`, `GB`, `GiB`, `hour`
and `month`. GB is exactly 1,000,000,000 bytes; GiB is exactly 1,073,741,824 bytes.
Each rate has an amount **per_quantity** units, a discount fraction from zero through one,
and a mandatory discount explanation. For example, $0.001 per 1,000 requests at 10,000,000
requests costs $10. Unknown rates are null/missing, including for explicitly zero usage.

Use decimal strings in JSON. Finite nonnegative amounts support at most 30 decimal digits
and 12 fractional places. Calculations use a private Decimal context with precision 80.
Each line is rounded to six currency decimals using half even; totals sum those rounded
lines. Percentages and payback round to twelve places. No intermediate binary float
arithmetic is used in authoritative economics. Extremely small costs can round to zero;
raw quantities/rates and formulas remain available.

## Required components and billing boundaries

Every recurring total has eleven components:

| Component | Quantity |
| --- | --- |
| storage | Per-object primary data and metadata bytes, including primary copies |
| query_compute | Explicit monthly compute hours |
| transform_compute | Explicit monthly ongoing transformation hours |
| read_requests / write_requests | Monthly request counts, billed independently |
| retrieval / network | Monthly transferred GB or GiB, billed independently |
| backups / replicas | Declared full retained copies, separately priced |
| maintenance | Monthly labor hours or service months |
| service | Monthly recurring service/optimization fees |

Missing components produce unknown line items. Declare zero usage with provenance when a
charge does not apply. There are no assumed free components. Each line carries quantity,
unit, rate/basis/discount, snapshot ID, sources, formula, amount and missing input paths.
`known_subtotal` sums available amounts; `total` is null if any component is unknown.

The footprint lists each data object and each metadata object separately. An empty tuple
means explicitly no objects; null means unknown. Physical bytes sum their actual sizes
times primary + backup + replica copies. Baseline and candidate must identify equivalent
logical content, equal retention and equal required copy counts. Zero-byte baselines
have no percentage saving. Compression can increase bytes and produce negative savings.
Directory/filesystem allocation overhead is outside this object-byte boundary unless
explicitly represented as metadata; backups are full copies, not modeled incremental backups.

For usage storage, minimum object size applies to **each** object and copy, including
metadata. Minimum duration is amortized for a steady population replaced after the stated
retention lifetime:

```text
monthly_billable_storage_units =
  sum(max(object_bytes, minimum_object_bytes)) * copies / bytes_per_unit
  * max(retention_days, minimum_duration_days) / retention_days

line_cost = quantity / per_quantity * rate_amount * (1 - discount_fraction)
```

Retention is also the modeled object lifetime in this limited tariff. A one-time cohort,
changing lifetimes, partial calendar months or actual early-deletion invoices need a
different usage model. Minimum-duration overhead changes billed bytes, never physical bytes.
Explicit temporary byte-month estimates and provisioned capacities support tariffs with
zero object/duration minimums; combining a manual storage quantity with a minimum tariff
is rejected, rather than silently ignoring the minimum.

`basis=provisioned` requires an explicit billed-capacity quantity. Its amount is independent
of used bytes. Changing provisioned quantities/rates requires
`achievable_capacity_change` evidence describing the feasible capacity action. This is a
labeled forecast assumption, not verification that the provider resized anything.
`basis=shared_fixed` requires a shared commitment key and identical rate/quantity on both
sides; it cannot disappear or shrink. Fixed/provisioned charges cannot silently switch to
usage pricing. Do not duplicate one shared commitment across components.

## Migration, savings and unknowns

Migration has exactly five distinct forecast components: `conversion`, `temporary_storage`,
`transfer`, `labor` and `rollback`. Omitted components are unknown; duplicate component
IDs are rejected. Conversion includes verification if that is inside its measured/estimated
boundary. Temporary storage is the **incremental overlap** byte-month charge, excluding
storage already counted in the recurring baseline/candidate models. Transfer covers migration
traffic, separate from recurring network usage. Labor excludes separately charged rollback
preparation. Callers must define these nonoverlapping assumptions; the calculator cannot
inspect a customer invoice for duplicate scope.

Migration peak space conservatively sums retained baseline bytes + retained candidate bytes
+ explicitly supplied extra scratch bytes. Peak space is independent of temporary storage
price and becomes null if any byte input is unknown. It is not a measurement of live disk
peak usage. `actual_incurred` and its user supplied source remain separate fields and never
get added to or substituted into forecast savings.

```text
monthly_savings = baseline_monthly_total - candidate_monthly_total
monthly_savings_percent = 100 * monthly_savings / baseline_monthly_total
horizon_recurring_savings = monthly_savings * horizon_months
horizon_net_savings = horizon_recurring_savings - migration_forecast_total
payback_months = migration_forecast_total / monthly_savings
```

Payback is available only for positive savings, complete forecast costs and explicitly steady
monthly usage. A free migration can have zero payback with positive savings. Zero/negative
savings never get a fabricated payback. Missing migration inputs leave known recurring
savings available but net savings/payback null. Missing operating inputs leave recurring
savings null. Missing physical/peak inputs are listed independently, even when provisioned
costs are calculable. Negative net savings and space changes are preserved.

## Scenarios and saved benchmark evidence

A request accepts up to twelve named scenarios with explicit assumptions, complete baseline,
candidate, migration and snapshot inputs. Duplicate the example's scenario and change the
quantities, projected object inventories or rates to explore workload, growth or price ranges.
Projected inventories must carry `assumption` provenance; keep the source logical dataset
fingerprint as the comparison anchor. Both alternatives in each scenario represent the same
logical population/retention/copies. Monthly quantities represent horizon-average usage;
there is no implicit growth curve, automatic sample scaling or time-varying cash-flow model.
Set `steady_monthly_usage=false` for nonsteady average scenarios to suppress simple payback.
Ranges report min/max and known/total scenario coverage. They are not confidence intervals;
missing scenarios never silently become zero-valued bounds. Every scenario remains inspectable.

Optionally bind the saved S06 fixture evidence:

```bash
# Use a non-baseline manifests[].key from this JSON as CANDIDATE_KEY.
uv run --locked --project backend data-optimizer cost \
  --request examples/s07-cost-request.json \
  --benchmark docs/evidence/s06-benchmark-fresh.json \
  --candidate CANDIDATE_KEY --replays-per-month 10000 \
  --output /tmp/s07-sample-cost.json
```

The adapter verifies fingerprints and matching input/request/workload/content lineage.
It binds actual data-part sizes, sample content identity and explicit report/manifest
references. Metadata sizes, copies, retention and all other usage/prices remain supplied
assumptions; the example's zero metadata and invented fees remain **synthetic**.
For usage query compute, it models median measured **load + entire workload** seconds times
supplied replays/month divided by 3600. This assumes rates bill active engine time; startup,
warmups and orchestration are excluded. It cannot estimate a provider compute invoice.
S05 whole-conversion-worker CPU hours, including verification, feed the one-time conversion
forecast under a separate explicit process-CPU billing assumption. Both are projections
from local sample measurements, never cloud performance results.

All selected repeats must pass with the expected query fingerprints. Missing/failed/stopped
trials leave query compute null, even with a zero replay assumption. Unknown monthly usage
also leaves it null. An explicit zero is distinct. Provisioned/fixed query charges retain
their supplied quantities. No scanned-byte charge is derived: S06 does not measure physical
scan I/O. The adapter applies the same measured sample to every supplied scenario, replacing
data inventories; use explicit unbound scenarios for larger-dataset projections.

## Verification and limits

```bash
make check
make test
make build
uv run --locked --project backend python scripts/verify-s07.py --output-dir /tmp/s07-evidence
```

The last command runs the extracted wheel outside the source tree, verifies synthetic,
saved-measurement and unknown-usage CLI cases, report fingerprints/reconciliation and source
preservation. It does not rerun Docker. See [S07 evidence](evidence/s07-verification.md).

Unsupported tariffs: tiers, free allowances, taxes, FX, contract allocation, reservations,
incremental backups, mixed-region copies, calendar/day proration, nonlinear growth schedules
and minimum tariffs for manually specified storage quantities. Those require explicit external
calculation or future extensions; supplying a flat assumption does not make them verified.
No live prices, actual customer bills, production changes, recommendation ranking or UI are
part of this sprint.
