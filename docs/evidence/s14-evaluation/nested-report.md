# Data Optimizer engineering handoff

Schema: s12.1
Bundle: fcbcc1d958c20d4cf27a4b1efccacfae7119755ca1b5820564c1a1c531a88845
Original report: 70dc27d387111500547bb970cc5a5d222ab9edf70c40ba64edb584240b2f429e

## Decision and requirements

Outcome: insufficient\_evidence
Selected candidate: Unknown
Reason: Supply raw dataset/workload, complete costs and evidence for required constraints.
Evidence: local\_assessment
Search stopped: space\_exhausted

The JSON bundle contains the executable requirements, tested candidate configurations, workload, raw trials, integrity checks, environment and price snapshots. Nested fingerprints identify the original evidence; see export redactions.

Next questions:

- Provide a dataset and constrained workload for measurement.

## Profile coverage

Rows: 64; profiled: 64; fraction: 1.0; sampling: full\_scan; input physical bytes: 3638.

## Tested candidates and costs

All amounts below are copied from the stored calculations. Unknown is not zero.

## Price provenance

- synthetic\_storage\_demo: synthetic prices; synthetic-offline-example / synthetic-local / USD; effective 2026-11-02T00:00:00+00:00; retrieved 2026-11-02T00:00:00+00:00. Rates, units, minimums and discounts are in bundle.json. Synthetic means invented, never a provider quote.

## Prerequisites and deliberate migration

Use Python 3.12, this project's locked package and matching PyArrow/DuckDB versions.
Full assessment reproduction additionally requires Linux Docker/cgroup v2 and the recorded
immutable benchmark image (build locally with `make benchmark-image` in the matching checkout).
Use a private local source copy and a new empty workspace. Preserve the original source,
its fingerprint, all retained copies and a backup of the prior reader configuration.
Required reader support: No selected tested configuration. Never switch a transactional database on this evidence.
Check target reader support for decimals, null/missing fields, timestamps and codecs.
Budget peak space using the cost section; Unknown requires a separate estimate before migration.
Local output needs room for baseline plus all tested alternatives during assessment reproduction.

After extracting all files together, reproduce the full assessment:

```sh
data-optimizer reproduce ./bundle.json --source '/path/to/local source' \
  --root /tmp/new-assessment --output /tmp/new-reproduction.json
```

Paths above are placeholders: supply your private source and new destinations as quoted arguments.
The command checks the input digest and engine versions before running, compares the outcome and
selected configuration, and records disagreement explicitly. Timing variation is expected.
For metadata-only/startup guidance no raw-data reproduction or migration is authorized by evidence.
For keep_current retain the current reader; for insufficient_evidence answer the missing questions.

Only for a tested change, create and validate a local candidate copy:

```sh
sh ./migrate.sh '/path/to/local source' /tmp/new-migration /tmp/new-migration-result.json
```

The script uses fixed package commands and positional arguments, never dataset/AI shell content.
Read the resulting manifest: it records the exact configuration, schema/reader, output files,
physical bytes and full semantic integrity evidence. Every canonical-content/multiplicity and
workload-result check must pass. The source remains unchanged. No reader is switched automatically.

## Canary and rollback

1. Save the prior reader configuration and original SHA-256; keep source and backup accessible.
2. Run the bundle's complete constrained workload against the new manifest parts. Local conversion
   already checks these results against the source, including declared tolerances and duplicates.
3. Before any real switch, replay representative queries in the actual target reader/environment;
   compare counts, null/missing semantics, decimals, timestamps and results. Measure that reader's
   latency/concurrency against your requirements; local worker timings cannot substitute for this.
4. A human may then direct a limited canary to the copy, retaining the previous reader configuration
   and source. Stop on any result/schema mismatch, missing part, integrity failure, unacceptable
   latency, higher cost, retention violation or unsupported reader behavior.
5. On a trigger, stop directing new canary reads to the copy. Restore the saved prior reader
   configuration pointing at the retained original; verify the original SHA-256 and rerun the same
   workload on it. Confirm normal reads and record the failed candidate/evidence IDs for review.
   Keep both copies for investigation and meet existing retention rules. These instructions perform
   no automatic deletion, production mutation, external transfer or source cleanup.


## Coverage and limitations

- Measurements cover only the supplied input on the recorded local worker. Profile sampling does not establish full-dataset performance; metadata-only/startup guidance has no measured migration recommendation or historical savings.
- Typed load plus in-memory queries; OS cache uncontrolled. Native scans, cloud latency, concurrency, throughput and production tail latency remain unvalidated.
- Costs are forecasts, not invoices or realized savings. Synthetic prices are invented; user-supplied prices are unverified. Missing amounts remain Unknown. Fixed capacity must actually change to yield cash savings.
- Supported tariffs are flat linear rates with recorded minimums. Tier/free allowances, tax, FX, calendar proration, nonlinear growth and mixed-region allocation are unsupported.
- Search is bounded and may stop early; best tested feasible does not imply global optimality. Rerun timings and timing-based costs or decisions can differ; inspect any disagreement.
- Best tested feasible option within bounded coverage; no global optimality claim.
- Local typed load and in-memory queries; no native scans, cloud, concurrency or tail SLA proof.
- Costs are forecasts from explicit assumptions and price snapshots; synthetic rates stay synthetic.
- Retention/copies are declared cost assumptions, not a deployed durability guarantee.
- Observed maxima and ranges describe these repeats, not population confidence intervals.

## Privacy and evidence references

- Business descriptions, AI summaries, source notes/references, price narrative and paths are omitted. Schema/workload parameters remain necessary and may be sensitive.
- Nested evidence fingerprints reference the original records before narrative redaction. The bundle fingerprint covers the exported content; it is not a signature.
