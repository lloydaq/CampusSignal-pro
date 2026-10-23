import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { signedOut } from "@/test/auth";
import { json, mockFetch } from "@/test/http";
import { renderRoute } from "@/test/render";

beforeEach(() => {
  mockFetch({
    "/healthz": () => json({ status: "ok" }),
    "/readyz": () => json({ status: "ready" }),
    "/api/v1/me": signedOut,
  });
});

describe("routes", () => {
  it("renders the shell with one h1, the wordmark, the appearance switch and a status link", async () => {
    renderRoute("/status");
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Service status");
    expect(screen.getByText("CampusSignal")).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Appearance" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Service status" })).toHaveAttribute("href", "/status");
    await screen.findByText("Running");
  });

  it("shows a not-found page for unknown paths with a working link home", async () => {
    renderRoute("/nowhere");
    expect(screen.getByRole("heading", { level: 1, name: "Page not found" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: "Go to the start page" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Sign in" })).toBeInTheDocument();
  });

  it("theme radios switch the document theme and keep exactly one selected", async () => {
    renderRoute("/status");
    await userEvent.click(screen.getByRole("radio", { name: "Dark" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(screen.getByRole("radio", { name: "Dark" })).toBeChecked();
    await userEvent.click(screen.getByRole("radio", { name: "System" }));
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
    expect(screen.getAllByRole("radio").filter((r) => (r as HTMLInputElement).checked)).toHaveLength(1);
    await screen.findByText("Running");
  });
});
