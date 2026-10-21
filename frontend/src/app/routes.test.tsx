import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { json, mockFetch } from "@/test/http";
import { renderRoute } from "@/test/render";

beforeEach(() => {
  mockFetch({ "/healthz": () => json({ status: "ok" }), "/readyz": () => json({ status: "ready" }) });
});

describe("routes", () => {
  it("renders the signed-out shell with one h1, the wordmark and the appearance switch", async () => {
    renderRoute("/");
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Accounts aren't open yet");
    expect(screen.getByText("CampusSignal")).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Appearance" })).toBeInTheDocument();
    await screen.findByText("Running");
  });

  it("shows a not-found page for unknown paths with a working link home", async () => {
    renderRoute("/nowhere");
    expect(screen.getByRole("heading", { level: 1, name: "Page not found" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: "Go to the start page" }));
    expect(screen.getByRole("heading", { level: 1, name: "Accounts aren't open yet" })).toBeInTheDocument();
  });

  it("theme radios switch the document theme and keep exactly one selected", async () => {
    renderRoute("/");
    await userEvent.click(screen.getByRole("radio", { name: "Dark" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(screen.getByRole("radio", { name: "Dark" })).toBeChecked();
    await userEvent.click(screen.getByRole("radio", { name: "System" }));
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
    expect(screen.getAllByRole("radio").filter((r) => (r as HTMLInputElement).checked)).toHaveLength(1);
    await screen.findByText("Running");
  });
});
