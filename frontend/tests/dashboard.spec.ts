import { test, expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
const fixtures = process.env.S10_FIXTURE_DIR!;
const example = JSON.parse(
  readFileSync(
    join(import.meta.dirname, "../../examples/s08-assessment-request.json"),
    "utf8",
  ),
);
async function project(page: Page, name: string) {
  await page.goto("/");
  await page.getByLabel("Project name", { exact: true }).fill(name);
  await page
    .getByLabel("Business context")
    .fill("Synthetic browser verification; analytical event copies.");
  await page
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "Project created" }),
  ).toBeVisible();
}
async function upload(page: Page, name: string, format = "ndjson") {
  await page.getByLabel("File format", { exact: true }).selectOption(format);
  await page
    .getByLabel("Dataset file", { exact: true })
    .setInputFiles(join(fixtures, name));
  await page.getByLabel("I reviewed the retention").check();
  await page
    .getByRole("button", { name: "Upload and validate", exact: true })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "Upload validated" }),
  ).toBeVisible();
  await expect(page.getByLabel("Ready dataset")).not.toHaveValue("");
}
async function request(page: Page, format = "ndjson", repeats = 1) {
  const r = structuredClone(example);
  r.conversion.source = {
    format,
    ...(format === "ndjson"
      ? { schema_overrides: { timestamp: "timestamp" } }
      : {}),
  };
  r.conversion.workload = {
    queries: [{ id: "scan", kind: "full_scan" }],
    concurrency: 1,
    concurrency_scope: "single_process",
  };
  r.conversion.max_candidates = 4;
  r.benchmark.repeats = repeats;
  r.search.max_trials = 4;
  await page
    .getByLabel("Assessment request JSON", { exact: true })
    .fill(JSON.stringify(r, null, 2));
}
async function run(page: Page) {
  const created = page.waitForResponse(
    (r) =>
      r.url().endsWith("/v1/assessments") && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Run assessment", exact: true })
    .click();
  const response = await created;
  expect(response.status()).toBe(202);
  return (await response.json()).id as string;
}
async function completed(
  page: Page,
  outcome: "change" | "keep_current",
  id: string,
) {
  await expect(page.locator("#result-title")).toHaveText(
    outcome === "change"
      ? "A tested change is worth considering"
      : "Keep your current representation",
    { timeout: 90_000 },
  );
  const response = await page.request.get(`/api/v1/assessments/${id}/result`);
  expect(response.ok()).toBeTruthy();
  const report = await response.json();
  expect(report.decision.outcome).toBe(outcome);
  for (const candidate of report.decision.candidates) {
    const row = page
      .getByRole("row")
      .filter({ hasText: candidate.candidate_id.slice(0, 12) });
    const manifest = report.benchmark.manifests.find(
      (m: { key: string }) => m.key === candidate.candidate_id,
    );
    await expect(row.getByRole("cell").nth(1)).toHaveText(
      String(manifest.physical_bytes),
    );
    await expect(row.getByRole("cell").nth(3)).toContainText(
      String(candidate.horizon_total),
    );
  }
  await expect(
    page.getByText("Assessment snapshot · observations in adoption history", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Synthetic pricing · invented rates", { exact: true }),
  ).toBeVisible();
  const candidate = report.decision.candidates.find(
    (c: { configuration: { baseline: boolean } }) => !c.configuration.baseline,
  );
  await page
    .getByText(
      `${candidate.configuration.format} / ${candidate.configuration.codec} · feasibility & costs · ${candidate.candidate_id.slice(0, 8)}`,
      { exact: true },
    )
    .click();
  const detail = page
    .locator("details")
    .filter({
      has: page.getByText(
        `${candidate.configuration.format} / ${candidate.configuration.codec} · feasibility & costs · ${candidate.candidate_id.slice(0, 8)}`,
        { exact: true },
      ),
    });
  const dd = detail.locator("dd");
  await expect(dd.nth(0)).toHaveText(
    `${candidate.costs.candidate.total} ${candidate.costs.currency}`,
  );
  await expect(dd.nth(1)).toHaveText(
    `${candidate.costs.migration_forecast.total} ${candidate.costs.currency}`,
  );
  await expect(dd.nth(2)).toHaveText(
    `${candidate.costs.horizon_net_savings} ${candidate.costs.currency}`,
  );
  const lines = detail.getByRole("table").getByRole("row");
  const apiLines = [
    ...candidate.costs.baseline.items,
    ...candidate.costs.candidate.items,
    ...candidate.costs.migration_forecast.items,
  ];
  for (let i = 0; i < apiLines.length; i++)
    await expect(
      lines
        .nth(i + 1)
        .getByRole("cell")
        .nth(2),
    ).toHaveText(apiLines[i].amount ?? "Unknown");
  await page
    .getByText("Raw evidence & reproducibility metadata", { exact: true })
    .click();
  await expect(
    page.getByText(`Report fingerprint: ${report.report_fingerprint}`, {
      exact: true,
    }),
  ).toBeVisible();
  return report;
}

test("NDJSON measured change, refresh, exact API totals, keyboard and responsive layout", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await project(page, "S10 measured event assessment");
  await upload(page, "events.ndjson");
  await request(page);
  const id = await run(page);
  await page.reload();
  await expect(page.getByLabel("Assessment history")).toHaveValue(id);
  const report = await completed(page, "change", id);
  await page.screenshot({
    path: `../docs/evidence/${process.env.BROWSER_EVIDENCE_PREFIX ?? "s10"}-dashboard-desktop.png`,
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator("#result-title")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: `../docs/evidence/${process.env.BROWSER_EVIDENCE_PREFIX ?? "s10"}-dashboard-narrow.png`,
    fullPage: true,
  });
  await page.reload();
  await expect(page.locator("#result-title")).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("link", { name: "Skip to workspace" }),
  ).toBeFocused();
  expect(errors).toEqual([]);
  expect(
    report.benchmark.trials.every(
      (t: { status: string }) => t.status === "passed",
    ),
  ).toBeTruthy();
});

test("already compressed input keeps current, session ownership switches clear prior results", async ({
  page,
}) => {
  await project(page, "S10 compressed baseline");
  await upload(page, "events.ndjson.gz");
  await request(page);
  const id = await run(page);
  await completed(page, "keep_current", id);
  await page.getByLabel("Local demo identity").selectOption("bob");
  await expect(
    page.getByText("No projects yet. Create your first assessment workspace."),
  ).toBeVisible();
  await expect(page.locator("#result-title")).toHaveCount(0);
  const denied = await page.request.get(`/api/v1/assessments/${id}/result`, {
    headers: { "X-Local-Identity": "bob" },
  });
  expect(denied.status()).toBe(404);
  await page.getByLabel("Local demo identity").selectOption("alice");
  await expect(page.locator("#result-title")).toHaveText(
    "Keep your current representation",
  );
});

for (const format of ["csv", "parquet"])
  test(`${format} upload and real worker assessment`, async ({ page }) => {
    await project(page, `S10 ${format} analytical data`);
    await upload(page, `events.${format}`, format);
    await request(page, format);
    const id = await run(page);
    await expect(page.locator("#result-title")).toBeVisible({
      timeout: 90_000,
    });
    const r = await (
      await page.request.get(`/api/v1/assessments/${id}/result`)
    ).json();
    expect(r.benchmark.trials.length).toBeGreaterThanOrEqual(4);
    expect(
      r.benchmark.trials.every(
        (t: { status: string }) => t.status === "passed",
      ),
    ).toBeTruthy();
  });

test("missing data and unknown costs give actionable insufficient evidence", async ({
  page,
}) => {
  await project(page, "S10 startup without a dataset");
  await page
    .getByRole("button", { name: "No dataset yet", exact: true })
    .click();
  const id = await run(page);
  await expect(page.locator("#result-title")).toHaveText(
    "More evidence is needed",
  );
  await expect(page.getByRole("heading", { name: "Next steps" })).toBeVisible();
  const r = await (await page.request.get(`/api/v1/assessments/${id}`)).json();
  expect(r.status).toBe("needs_input");
  await expect(
    page.getByText("Scenario guidance only", { exact: false }),
  ).toBeVisible();
  await page.reload();
  await expect(page.locator("#result-title")).toHaveText(
    "More evidence is needed",
  );
});

test("reviewed metadata import preserves provenance and never invents sample benchmarks", async ({
  page,
}) => {
  await project(page, "S10 private local profile");
  await page
    .getByRole("button", { name: "Metadata only", exact: true })
    .click();
  await page
    .getByLabel("Local profile report", { exact: true })
    .setInputFiles(join(fixtures, "profile.json"));
  await expect(
    page.getByRole("button", { name: "Import reviewed metadata", exact: true }),
  ).toBeDisabled();
  await page.getByLabel("I reviewed these statistics").check();
  await page
    .getByRole("button", { name: "Import reviewed metadata", exact: true })
    .click();
  await expect(page.getByLabel("Imported profile")).not.toHaveValue("");
  const id = await run(page);
  await expect(page.locator("#result-title")).toHaveText(
    "More evidence is needed",
  );
  await expect(
    page.getByText(
      /locally supplied metadata; raw data not inspected by server/,
    ),
  ).toBeVisible();
  const r = await (
    await page.request.get(`/api/v1/assessments/${id}/result`)
  ).json();
  expect(r.profile.raw_data_inspected_by_server).toBe(false);
  expect(r.benchmark).toBeNull();
});

test("malformed upload and invalid workload are actionable and preserve entered fields", async ({
  page,
}) => {
  await project(page, "S10 validation recovery");
  await page
    .getByLabel("Dataset file", { exact: true })
    .setInputFiles({
      name: "bad.ndjson",
      mimeType: "application/json",
      buffer: Buffer.from("{broken\n"),
    });
  await page.getByLabel("I reviewed the retention").check();
  await page
    .getByRole("button", { name: "Upload and validate", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("422");
  await expect(page.getByLabel("Project name", { exact: true })).toHaveValue(
    "S10 validation recovery",
  );
  await expect(page.getByLabel("Ready dataset")).toHaveValue("");
  await upload(page, "events.ndjson");
  await request(page);
  const text = await page
    .getByLabel("Assessment request JSON", { exact: true })
    .inputValue();
  const invalid = JSON.parse(text);
  invalid.conversion.workload.queries = [
    { id: "bad", kind: "projection", columns: [] },
  ];
  await page
    .getByLabel("Assessment request JSON", { exact: true })
    .fill(JSON.stringify(invalid));
  await page
    .getByRole("button", { name: "Validate requirements", exact: true })
    .click();
  await expect(page.locator("#request-errors")).toContainText(
    "conversion.workload.queries.0",
  );
  await expect(
    page.getByLabel("Assessment request JSON", { exact: true }),
  ).toHaveValue(JSON.stringify(invalid));
  await page.getByLabel("Assessment request JSON", { exact: true }).fill("{");
  await expect(
    page.getByRole("button", { name: "Run assessment", exact: true }),
  ).toBeDisabled();
  await expect(page.locator("#request-errors")).toContainText("Invalid JSON");
});

test("active assessment cancellation survives refresh and preserves stopped status", async ({
  page,
}) => {
  await project(page, "S10 active cancellation");
  await upload(page, "events.ndjson");
  await request(page, "ndjson", 5);
  const id = await run(page);
  await expect
    .poll(
      async () =>
        (await (await page.request.get(`/api/v1/assessments/${id}`)).json())
          .status,
      { timeout: 40_000 },
    )
    .toBe("benchmarking");
  await page
    .getByRole("button", { name: "Cancel assessment", exact: true })
    .click();
  await page.reload();
  await expect(page.locator(".status-heading strong")).toHaveText("cancelled", {
    timeout: 40_000,
  });
  await expect(page.getByText(/Stop reason: user_cancelled/)).toBeVisible();
});
