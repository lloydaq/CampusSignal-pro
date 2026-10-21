import { applyThemePreference, readThemePreference, saveThemePreference, THEME_STORAGE_KEY } from "./theme";

afterEach(() => {
  window.localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
});

describe("theme preference", () => {
  it("defaults to system when nothing or something invalid is stored", () => {
    expect(readThemePreference()).toBe("system");
    window.localStorage.setItem(THEME_STORAGE_KEY, "purple");
    expect(readThemePreference()).toBe("system");
  });

  it("saves an explicit choice and applies it as data-theme", () => {
    saveThemePreference("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(readThemePreference()).toBe("dark");
  });

  it("system removes the override so the OS preference applies", () => {
    saveThemePreference("light");
    saveThemePreference("system");
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
  });

  it("still applies the theme when storage is unavailable", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    expect(() => saveThemePreference("dark")).not.toThrow();
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(readThemePreference()).toBe("system");
  });

  it("applyThemePreference only touches the root attribute", () => {
    applyThemePreference("light");
    expect(document.documentElement.dataset.theme).toBe("light");
  });
});
