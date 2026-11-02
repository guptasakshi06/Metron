import { test, expect } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
const example = JSON.parse(readFileSync(join(import.meta.dirname, "../../examples/s08-assessment-request.json"), "utf8"));
const components = ["storage", "query_compute", "transform_compute", "read_requests", "write_requests", "retrieval", "network", "backups", "replicas", "maintenance", "service"];

test("real observation history reconciles growth, lower usage, missing bills, negative outcomes, revert and reassessment", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", e => errors.push(e.message));
  page.on("console", e => { if (e.type() === "error" && !e.location().url.endsWith("/favicon.ico")) errors.push(e.text()); });
  await page.goto("/");
  await page.getByLabel("Project name", { exact: true }).fill("S13 synthetic adoption history");
  await page.getByRole("button", { name: "Create project", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Project created" })).toBeVisible();
  await page.getByLabel("Dataset file", { exact: true }).setInputFiles(join(process.env.S10_FIXTURE_DIR!, "events.ndjson"));
  await page.getByLabel("I reviewed the retention").check();
  await page.getByRole("button", { name: "Upload and validate", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Upload validated" })).toBeVisible();
  const request = structuredClone(example);
  request.conversion.max_candidates = 4; request.benchmark.repeats = 1; request.search.max_trials = 4;
  await page.getByLabel("Assessment request JSON", { exact: true }).fill(JSON.stringify(request));
  const created = page.waitForResponse(r => r.url().endsWith("/v1/assessments") && r.request().method() === "POST");
  await page.getByRole("button", { name: "Run assessment", exact: true }).click();
  const state = await (await created).json();
  await expect(page.locator("#result-title")).toHaveText("A tested change is worth considering", { timeout: 90000 });
  const original = await (await page.request.get(`/api/v1/assessments/${state.id}/result`)).text();
  const report = JSON.parse(original);
  const region = page.getByRole("region", { name: "Adoption & savings history" });
  await region.getByText("Adoption plan & deployment status", { exact: true }).click();
  const plan = { expected_version: 0, state: "proposed", reference_logical_bytes: 287,
    source: "Synthetic browser adoption", note: "No actual production deployment",
    deployed_at: null as string | null, reverted_at: null as string | null, actual_migration_cost: null as string | null };
  for (const status of ["proposed", "planned", "deployed"]) {
    plan.state = status;
    if (status === "deployed") { plan.deployed_at = "2026-08-01T00:00:00Z"; plan.actual_migration_cost = "5"; }
    await region.getByLabel("Adoption plan JSON").fill(JSON.stringify(plan));
    await region.getByRole("button", { name: "Save adoption version" }).click();
    await expect(region.getByTestId("adoption-state")).toHaveText(status);
    plan.expected_version++;
  }
  const historyResponse = await (await page.request.get(`/api/v1/assessments/${state.id}/migration-plan`)).json();
  const historyUrl = `/api/v1/migration-plans/${historyResponse.plan.id}/history`;
  const q = report.request.conversion.workload.queries;
  const base = { expected_version: 0, period_start: "2026-09-01T00:00:00Z", period_end: "2026-10-01T00:00:00Z",
    currency: "USD", retained_bytes: 276, logical_volume_bytes: 574, workload_replays: "200",
    query_mix: Object.fromEntries(q.map((x: {id: string}) => [x.id, (1 / q.length).toFixed(12)])),
    access_quantities: Object.fromEntries(components.map(c => [c, "0"])),
    itemized_costs: Object.fromEntries(components.map(c => [c, "1000"])),
    coverage: "Synthetic complete bill", source: "Invented browser fixture", note: "Not a real bill", excluded: false };
  await region.getByRole("button", { name: "New manual observation" }).click();
  await region.getByRole("textbox", {name: "Observation JSON", exact: true}).fill(JSON.stringify(base));
  await region.getByRole("button", { name: "Save observation revision" }).click();
  await expect(region.getByRole("status").filter({hasText: "Observation revision saved"})).toBeVisible();
  let history = await (await page.request.get(historyUrl)).json();
  let entry = history.observations[0];
  expect(Number(entry.calculation.modeled_savings)).toBeLessThan(0);
  expect(entry.calculation.drift_signals).toContain("logical_volume_changed_at_least_20_percent");
  const row = region.getByTestId("observation-row");
  for (const [cell, field] of [[1, "actual_cost"], [2, "original_projected_cost"], [3, "modeled_adjusted_baseline"], [4, "modeled_savings"]] as const) {
    await expect(row.locator("td").nth(cell)).toHaveText(`${entry.calculation[field]} USD`);
  }
  await expect(region.getByTestId("cumulative-benefit")).toHaveText(`${history.cumulative_modeled_benefit} USD`);
  // Revisions preserve original input. Lower usage with equal adjusted bill yields zero.
  await region.getByRole("button", { name: "Revise observation 1" }).click();
  const lowered = { ...entry.payload, observation_id: entry.id, expected_version: 1,
    logical_volume_bytes: 143, workload_replays: "50", itemized_costs: Object.fromEntries(components.map(c => [c, "0"])) };
  await region.getByRole("textbox", {name: "Observation JSON", exact: true}).fill(JSON.stringify(lowered));
  await region.getByRole("button", { name: "Save observation revision" }).click();
  await expect(region.getByRole("button", {name: "Revise observation 2"})).toBeVisible();
  history = await (await page.request.get(historyUrl)).json(); entry = history.observations[0];
  lowered.expected_version = 2; lowered.itemized_costs.storage = entry.calculation.modeled_adjusted_baseline;
  await region.getByRole("button", { name: "Revise observation 2" }).click();
  await region.getByRole("textbox", {name: "Observation JSON", exact: true}).fill(JSON.stringify(lowered));
  await region.getByRole("button", { name: "Save observation revision" }).click();
  await expect(region.getByRole("button", {name: "Revise observation 3"})).toBeVisible();
  history = await (await page.request.get(historyUrl)).json();
  expect(Number(history.observations[0].calculation.modeled_savings)).toBe(0);
  // Missing bills and currency mismatch keep savings unknown.
  for (const [version, costs, currency] of [[3, {storage: "10"}, "USD"], [4, base.itemized_costs, "EUR"]] as const) {
    await region.getByRole("button", { name: `Revise observation ${version}` }).click();
    await region.getByRole("textbox", {name: "Observation JSON", exact: true}).fill(JSON.stringify({...lowered, expected_version: version, itemized_costs: costs, currency}));
    await region.getByRole("button", { name: "Save observation revision" }).click();
    await expect(region.getByRole("button", {name: `Revise observation ${version + 1}`})).toBeVisible();
    await expect(row.locator("td").nth(4)).toHaveText("Unknown");
    await expect(region.getByTestId("cumulative-benefit")).toHaveText("Unknown");
  }
  plan.state = "reverted"; plan.reverted_at = "2026-10-01T00:00:00Z";
  await region.getByLabel("Adoption plan JSON").fill(JSON.stringify(plan));
  await region.getByRole("button", { name: "Save adoption version" }).click();
  await expect(region.getByTestId("adoption-state")).toHaveText("reverted");
  await page.reload();
  await expect(region.getByTestId("adoption-state")).toHaveText("reverted");
  history = await (await page.request.get(historyUrl)).json();
  expect(history.observation_revisions.length).toBe(5);
  writeFileSync("../docs/evidence/s13-browser-history.json", JSON.stringify(history, null, 2));
  await region.screenshot({path: "../docs/evidence/s13-history-desktop.png"});
  await page.setViewportSize({width: 390, height: 844});
  await region.screenshot({path: "../docs/evidence/s13-history-narrow.png"});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.setViewportSize({width: 1440, height: 1000});
  await region.getByLabel("Reason for reassessment").fill("Workload and price review");
  await region.getByRole("button", {name: "Prepare reassessment", exact: true}).click();
  await expect(page.getByRole("status").filter({hasText: "Reassessment prepared"})).toBeVisible();
  const changed = JSON.parse(await page.getByLabel("Assessment request JSON", {exact: true}).inputValue());
  changed.policy.minimum_net_savings = "12";
  await page.getByLabel("Assessment request JSON", {exact: true}).fill(JSON.stringify(changed));
  // Explicitly select original dataset after refresh in the existing dataset control.
  await page.getByLabel("Ready dataset", {exact: true}).selectOption(state.dataset_id);
  const reassessed = page.waitForResponse(r => r.url().endsWith("/v1/assessments") && r.request().method() === "POST");
  await page.getByRole("button", {name: "Run assessment", exact: true}).click();
  const next = await (await reassessed).json();
  expect(next.id).not.toBe(state.id);
  await expect(page.getByText("Assessment version comparison", {exact: true})).toBeVisible({timeout: 90000});
  expect(await (await page.request.get(`/api/v1/assessments/${state.id}/result`)).text()).toBe(original);
  const comparison = await (await page.request.get(`/api/v1/assessments/${next.id}/comparison`)).json();
  expect(comparison.previous.id).toBe(state.id);
  expect(comparison.current.decision.policy.minimum_net_savings).toBe("12");
  writeFileSync("../docs/evidence/s13-browser-comparison.json", JSON.stringify(comparison, null, 2));
  await page.getByLabel("Local demo identity").selectOption("bob");
  await expect(page.getByRole("heading", {name: "Adoption & savings history"})).toHaveCount(0);
  expect(errors).toEqual([]);
});
