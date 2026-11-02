import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import Intake from "./Intake";
import { Api } from "./api";
const request = { policy: { scenario: "user" } };
const proposal = {
  id: "proposal", original_description: "retention 30 days", fields: [
    { field: "retention_days", value: 30, source_quote: "retention 30 days" },
  ], questions: { workload: "Which queries should be tested?" }, summary: { description: "retention 30 days" },
  summary_fingerprint: "reviewed", source: "deterministic", status: "not_requested",
  assumption: "Review before use.",
};
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
it("requires explicit summary approval and confirmation before applying proposals", async () => {
  const api = new Api("alice", "");
  const call = vi.spyOn(api, "call").mockResolvedValueOnce(proposal).mockResolvedValueOnce({ id: "accepted", version: 1 });
  const accepted = vi.fn();
  render(<Intake api={api} projectId="project" context="retention 30 days" request={request} onConfirm={accepted} />);
  fireEvent.click(screen.getByRole("button", { name: "Review requirement proposals" }));
  const field = await screen.findByLabelText(/Proposed retention days/);
  expect(accepted).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Refine reviewed summary with AI" })).toBeDisabled();
  fireEvent.change(field, { target: { value: "" } });
  fireEvent.click(screen.getByRole("button", { name: "Confirm and apply reviewed requirements" }));
  expect(await screen.findByText(/Requirements version 1 confirmed/)).toBeVisible();
  expect(accepted.mock.calls[0][0].policy.retention_days).toBeNull();
  expect(call).toHaveBeenCalledTimes(2);
});
it("keeps the review usable when optional AI is unavailable", async () => {
  const api = new Api("alice", "");
  const call = vi.spyOn(api, "call").mockResolvedValueOnce(proposal)
    .mockResolvedValueOnce({ ...proposal, status: "missing_key" });
  render(<Intake api={api} projectId="project" context="retention 30 days" request={request} onConfirm={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Review requirement proposals" }));
  await screen.findByLabelText(/Proposed retention days/);
  fireEvent.click(screen.getByLabelText("I approve sending this summary to the configured AI provider."));
  fireEvent.click(screen.getByRole("button", { name: "Refine reviewed summary with AI" }));
  expect(await screen.findByText(/AI assistance was unavailable/)).toBeVisible();
  expect(call.mock.calls[1][1]).toEqual({ approved_summary_fingerprint: "reviewed" });
  expect(screen.getByRole("button", { name: "Confirm and apply reviewed requirements" })).toBeEnabled();
});
it("does not apply a late confirmation after switching projects", async () => {
  const api = new Api("alice", "");
  let finish: (value: unknown) => void = () => {};
  vi.spyOn(api, "call").mockResolvedValueOnce(proposal).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const accepted = vi.fn();
  const view = render(<Intake api={api} projectId="project" context="retention 30 days" request={request} onConfirm={accepted} />);
  fireEvent.click(screen.getByRole("button", { name: "Review requirement proposals" }));
  await screen.findByLabelText(/Proposed retention days/);
  fireEvent.click(screen.getByRole("button", { name: "Confirm and apply reviewed requirements" }));
  view.unmount();
  finish({ id: "accepted", version: 1 });
  await Promise.resolve();
  expect(accepted).not.toHaveBeenCalled();
});
