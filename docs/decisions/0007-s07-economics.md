# Decision 0007: explicit offline snapshots and reconciled Decimal forecasts

Date: 2026-11-02 (Asia/Kolkata)

- Keep the existing stack/lockfile. Add immutable `s07.1` executable pricing/economics
  contracts separately from S01 descriptive contracts, as in S04–S06. Embed complete
  snapshots/requests and content hashes in reports; DB/tenant persistence remains S09.
- Ship only invented, visibly synthetic offline prices. No provider SDK, credential,
  price scraping or current provider-rate claim is needed for local completion.
- Require explicit quantities/rates for all recurring and one-time components. Emit
  unknown line items and known subtotals; missing inputs cannot become free charges.
  Use Decimal precision 80, half-even line rounding to six currency decimals, reconciled
  totals and twelve-place ratios. Retain signed savings and meaningful payback reasons.
- Separate used bytes from provisioned/fixed billing. Prevent shrinking shared fixed
  commitments and require a feasible capacity-change source before modeling a reduction
  in provisioned commitments. Preserve equal logical content, retention and copy counts.
- Count metadata objects and all declared copies; apply per-object storage minimums and
  amortized lifetime minimums. Reject manual storage quantities with minimum tariffs.
  This limited linear model is not a general cloud billing engine.
- Keep migration conversion, incremental overlap, traffic, labor and rollback in separate
  once-only buckets. Actual incurred costs never alter forecast fields. Peak space assumes
  all retained baseline/candidate copies coexist plus explicitly supplied scratch.
- Use named full-input scenarios with coverage-aware ranges, explicit projected growth
  inventories and horizon-average usage. No confidence scores or implicit extrapolation.
- Adapt saved S06 evidence only with explicit replay/billing assumptions; preserve data-only
  byte scope and local typed load/in-memory query scope. Failed/incomplete repeats remain
  unknown. No native-scan/cloud benefit or recommendation follows from this cost calculation.

Method, CLI and unsupported tariffs: [pricing method](../pricing-method.md).
