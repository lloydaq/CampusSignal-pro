/**
 * Theme preference (Design.md §3.2): System by default, with a Light/Dark override kept in
 * localStorage (a UI preference, not sensitive). "system" removes `data-theme`, so the
 * prefers-color-scheme media query in tokens.css decides. Storage can be unavailable
 * (private mode, blocked site data); the theme still applies for the current page.
 */

export const THEME_PREFERENCES = ["light", "dark", "system"] as const;
export type ThemePreference = (typeof THEME_PREFERENCES)[number];

export const THEME_STORAGE_KEY = "campussignal.theme";

function isThemePreference(value: unknown): value is ThemePreference {
  return typeof value === "string" && (THEME_PREFERENCES as readonly string[]).includes(value);
}

export function readThemePreference(): ThemePreference {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isThemePreference(stored) ? stored : "system";
  } catch {
    return "system";
  }
}

export function applyThemePreference(preference: ThemePreference): void {
  const root = document.documentElement;
  if (preference === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", preference);
}

export function saveThemePreference(preference: ThemePreference): void {
  applyThemePreference(preference);
  try {
    if (preference === "system") window.localStorage.removeItem(THEME_STORAGE_KEY);
    else window.localStorage.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    // Storage unavailable: the choice applies until the page is reloaded.
  }
}
