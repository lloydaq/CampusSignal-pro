import { retryAfterText, safeNextPath, signInPathFor } from "./navigation";

describe("safeNextPath", () => {
  it.each(["/account", "/account?tab=security", "/notices/1#top"])("keeps same-site path %s", (path) => {
    expect(safeNextPath(path)).toBe(path);
  });

  it.each([
    null,
    "",
    "account",
    "https://evil.example/",
    "//evil.example/",
    "/\\evil.example",
    "/\t/evil.example",
    "/\n//evil.example",
    "javascript:alert(1)",
  ])("falls back to the account page for %j", (value) => {
    expect(safeNextPath(value)).toBe("/account");
  });

  it("round-trips the current location through the sign-in URL", () => {
    const url = new URL(signInPathFor({ pathname: "/account", search: "?tab=1" }), "http://x");
    expect(safeNextPath(url.searchParams.get("next"))).toBe("/account?tab=1");
  });
});

describe("retryAfterText", () => {
  it.each([
    [null, "Try again later."],
    [1, "Try again in 1 second."],
    [45, "Try again in 45 seconds."],
    [60, "Try again in 1 minute."],
    [61, "Try again in 2 minutes."],
    [900, "Try again in 15 minutes."],
  ])("%j → %s", (seconds, text) => {
    expect(retryAfterText(seconds)).toBe(text);
  });
});
