import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { envelope, json, mockFetch } from "@/test/http";
import { renderRoute } from "@/test/render";

function row(name: string): HTMLElement {
  const term = screen.getByText(name, { selector: "dt" });
  return term.parentElement as HTMLElement;
}

describe("Service status", () => {
  it("shows API running and database ready", async () => {
    mockFetch({ "/healthz": () => json({ status: "ok" }), "/readyz": () => json({ status: "ready" }) });
    renderRoute("/");
    await screen.findByText("Running");
    expect(row("API")).toHaveTextContent("Running");
    expect(row("Database")).toHaveTextContent("Ready");
  });

  it("reports pending migrations as a state, not an error", async () => {
    mockFetch({
      "/healthz": () => json({ status: "ok" }),
      "/readyz": () => envelope(503, "not_ready", "The service is not ready.", { migrations: "pending" }),
    });
    renderRoute("/");
    expect(await screen.findByText("Migrations pending")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("reports an unreachable database", async () => {
    mockFetch({
      "/healthz": () => json({ status: "ok" }),
      "/readyz": () => envelope(503, "not_ready", "The service is not ready.", { database: "unreachable" }),
    });
    renderRoute("/");
    await screen.findByText("Running");
    expect(row("Database")).toHaveTextContent("Unreachable");
  });

  it("reports the API as unreachable when the server can't be contacted", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));
    renderRoute("/");
    expect(await screen.findByText("Unknown while the API is unreachable")).toBeInTheDocument();
    expect(row("API")).toHaveTextContent("Unreachable");
  });

  it("shows an error with the request ID and retries on request", async () => {
    let calls = 0;
    mockFetch({
      "/healthz": () => {
        calls += 1;
        return calls === 1 ? envelope(500, "internal_error", "Something went wrong on our side.", null, "req-500") : json({ status: "ok" });
      },
      "/readyz": () => json({ status: "ready" }),
    });
    renderRoute("/");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Couldn't check service status");
    expect(alert).toHaveTextContent("Something went wrong on our side.");
    expect(alert).toHaveTextContent("Request ID req-500");

    await userEvent.click(within(alert).getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Running")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("checks again on request", async () => {
    const fetchMock = mockFetch({ "/healthz": () => json({ status: "ok" }), "/readyz": () => json({ status: "ready" }) });
    renderRoute("/");
    await screen.findByText("Running");
    await userEvent.click(screen.getByRole("button", { name: "Check again" }));
    await screen.findByRole("button", { name: "Check again" });
    expect(fetchMock.mock.calls.filter(([url]) => url === "/healthz")).toHaveLength(2);
  });

  it("announces that it is checking while the first request is in flight", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => undefined)));
    renderRoute("/");
    expect(screen.getByRole("status")).toHaveTextContent("Checking service status");
  });
});
