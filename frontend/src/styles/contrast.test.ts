import { contrastRatio, tokensInBlock, type Tokens } from "./contrast";
import css from "./tokens.css?raw";

const TEXT = 4.5; // WCAG AA, normal text
const UI = 3; // WCAG AA, UI component boundaries and focus indicators

/** [foreground, background, minimum] — every pairing Design.md §3.1/§3.2 relies on. */
const PAIRS: readonly (readonly [string, string, number])[] = [
  ["--text", "--bg", TEXT],
  ["--text", "--surface", TEXT],
  ["--text", "--surface-sunken", TEXT],
  ["--text-muted", "--bg", TEXT],
  ["--text-muted", "--surface", TEXT],
  ["--text-subtle", "--bg", TEXT],
  ["--text-subtle", "--surface", TEXT],
  ["--primary", "--bg", TEXT],
  ["--primary", "--surface", TEXT],
  ["--primary", "--primary-subtle", TEXT],
  ["--on-primary", "--primary", TEXT],
  ["--on-primary", "--primary-hover", TEXT],
  ["--accent", "--surface", TEXT],
  ["--accent-fg", "--accent-subtle", TEXT],
  ["--success-fg", "--success-subtle", TEXT],
  ["--success-fg", "--surface", TEXT],
  ["--warning-fg", "--warning-subtle", TEXT],
  ["--warning-fg", "--surface", TEXT],
  ["--danger-fg", "--danger-subtle", TEXT],
  ["--danger-fg", "--surface", TEXT],
  ["--on-danger", "--danger", TEXT],
  ["--border-strong", "--surface", UI],
  ["--border-strong", "--bg", UI],
  ["--focus-ring", "--surface", UI],
  ["--focus-ring", "--bg", UI],
  ["--success", "--surface", UI],
  ["--warning", "--surface", UI],
  ["--danger", "--surface", UI],
];

const light = tokensInBlock(css, ":root");
const dark = tokensInBlock(css, ':root[data-theme="dark"]');
const darkFromSystem = tokensInBlock(css, ':root:not([data-theme="light"])');

function value(tokens: Tokens, name: string): string {
  const v = tokens[name];
  if (v === undefined) throw new Error(`Token ${name} is missing`);
  return v;
}

describe.each([
  ["light", light],
  ["dark", dark],
])("%s theme contrast", (_theme, tokens) => {
  it.each(PAIRS)("%s on %s meets %s:1", (fg, bg, minimum) => {
    expect(contrastRatio(value(tokens, fg), value(tokens, bg))).toBeGreaterThanOrEqual(minimum);
  });
});

describe("token blocks", () => {
  it("system dark preference and explicit dark theme use identical values", () => {
    expect(darkFromSystem).toEqual(dark);
  });

  it("dark theme defines every colour the light theme defines", () => {
    const colours = (t: Tokens) => Object.keys(t).filter((k) => t[k]?.startsWith("#"));
    expect(colours(dark).sort()).toEqual(colours(light).sort());
  });

  it("matches values documented in Design.md for core tokens", () => {
    expect(light["--primary"]).toBe("#1d3c8f");
    expect(light["--accent"]).toBe("#b8460b");
    expect(dark["--bg"]).toBe("#0f1420");
    expect(dark["--primary"]).toBe("#93aef5");
  });
});
