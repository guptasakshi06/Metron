import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
const example = JSON.parse(readFileSync(join(import.meta.dirname, "../../examples/s08-assessment-request.json"), "utf8"));
test("real measured bundle downloads reconcile, retain confirmation and recover on refresh", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", e => errors.push(e.message));
  await page.goto("/");
  await page.getByLabel("Project name", { exact: true }).fill("S12 exported assessment");
  await page.getByLabel("Business context").fill("PRIVATE_DESCRIPTION_SECRET retention 7 days");
  await page.getByRole("button", { name: "Create project", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Project created" })).toBeVisible();
  await page.getByLabel("Dataset file", { exact: true }).setInputFiles(join(process.env.S10_FIXTURE_DIR!, "events.ndjson"));
  await page.getByLabel("I reviewed the retention").check();
  await page.getByRole("button", { name: "Upload and validate", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Upload validated" })).toBeVisible();
  const request = structuredClone(example);
  request.conversion.max_candidates = 4;
  request.benchmark.repeats = 1;
  request.search.max_trials = 4;
  await page.getByLabel("Assessment request JSON", { exact: true }).fill(JSON.stringify(request, null, 2));
  await page.getByRole("button", { name: "Review requirement proposals" }).click();
  await page.getByRole("button", { name: "Confirm and apply reviewed requirements" }).click();
  await expect(page.getByText(/Requirements version 1 confirmed/)).toBeVisible();
  const created = page.waitForResponse(r => r.url().endsWith("/v1/assessments") && r.request().method() === "POST");
  await page.getByRole("button", { name: "Run assessment", exact: true }).click();
  const state = await (await created).json();
  await expect(page.locator("#result-title")).toHaveText("A tested change is worth considering", { timeout: 90000 });
  await page.reload();
  const handoff = page.getByRole("region", { name: "Engineering handoff" });
  await expect(handoff).toBeVisible();
  await handoff.getByRole("button", { name: "Prepare expiring report links" }).click();
  await expect(handoff.getByText(/Links expire/)).toBeVisible();
  let bundle;
  for (const [label, file] of [["Download JSON", "bundle.json"], ["Download MARKDOWN", "report.md"], ["Download HTML", "report.html"], ["Download complete bundle (ZIP)", "handoff.zip"]]) {
    const downloaded = page.waitForEvent("download");
    await handoff.getByRole("button", { name: label, exact: true }).click();
    const download = await downloaded;
    expect(download.suggestedFilename()).toBe(file);
    const path = await download.path();
    expect(path).toBeTruthy();
    const data = readFileSync(path!);
    expect(data.length).toBeGreaterThan(100);
    if (file === "bundle.json") {
      bundle = JSON.parse(data.toString());
      expect(bundle.version).toBe("s12.1");
      expect(bundle.provenance.confirmation_id).toBe(state.intake_confirmation_id);
      expect(data.toString()).not.toContain("PRIVATE_DESCRIPTION_SECRET");
    }
  }
  const report = await (await page.request.get(`/api/v1/assessments/${state.id}/result`)).json();
  expect(bundle.original_report_fingerprint).toBe(report.report_fingerprint);
  for (let i = 0; i < report.decision.candidates.length; i++) {
    expect(bundle.decision.candidates[i].horizon_total).toBe(report.decision.candidates[i].horizon_total);
  }
  await handoff.screenshot({ path: "../docs/evidence/s12-handoff-desktop.png" });
  await page.setViewportSize({ width: 390, height: 844 });
  await handoff.screenshot({ path: "../docs/evidence/s12-handoff-narrow.png" });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.getByLabel("Local demo identity").selectOption("bob");
  await expect(page.getByRole("heading", { name: "Engineering handoff" })).toHaveCount(0);
  expect(errors).toEqual([]);
});
