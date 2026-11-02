import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import App from "./App";
import { Api } from "./api";
const config = {
  auth_mode: "local",
  max_raw_upload_bytes: 1048576,
  max_decompressed_bytes: 4194304,
  default_retention_days: 7,
};
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  sessionStorage.clear();
});
describe("dashboard error and session boundaries", () => {
  it("shows API startup failure with retry", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new Error("API is not reachable")),
    );
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "API is not reachable",
    );
    expect(
      screen.getByRole("button", { name: "Retry connection" }),
    ).toBeVisible();
  });
  it("keeps project inputs after a real-shaped service error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async (url: string) =>
          new Response(
            JSON.stringify(
              url.endsWith("/config")
                ? config
                : url.endsWith("/projects")
                  ? { items: [] }
                  : {},
            ),
          ),
      ),
    );
    render(<App />);
    const name = await screen.findByLabelText("Project name");
    fireEvent.change(name, { target: { value: "Preserved context" } });
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({
              message: "A required service is temporarily unavailable.",
            }),
            { status: 503 },
          ),
        ),
    );
    fireEvent.click(screen.getByRole("button", { name: "Create project" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("503");
    expect(name).toHaveValue("Preserved context");
  });
  it("requires a memory-only verified session in JWT mode", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify({ ...config, auth_mode: "jwt" })),
        ),
    );
    render(<App />);
    expect(
      await screen.findByLabelText("Verified session token"),
    ).toHaveAttribute("type", "password");
    expect(
      screen.queryByLabelText("Local demo identity"),
    ).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Project name")).not.toBeInTheDocument();
  });
  it("API carries one credential and exposes dependency failures", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ message: "Temporarily unavailable." }), {
          status: 503,
        }),
      );
    vi.stubGlobal("fetch", fetch);
    await expect(
      new Api("alice", "verified-token").call("/v1/projects"),
    ).rejects.toThrow("503: Temporarily unavailable.");
    expect(fetch.mock.calls[0][1].headers.Authorization).toBe(
      "Bearer verified-token",
    );
    expect(fetch.mock.calls[0][1].headers["X-Local-Identity"]).toBeUndefined();
  });
});
