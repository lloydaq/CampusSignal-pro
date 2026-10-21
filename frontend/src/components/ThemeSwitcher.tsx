import { Monitor, Moon, Sun, type LucideIcon } from "lucide-react";
import { useId, useState } from "react";

import { cn } from "@/lib/utils";
import { readThemePreference, saveThemePreference, type ThemePreference } from "@/lib/theme";

const OPTIONS: readonly { value: ThemePreference; label: string; Icon: LucideIcon }[] = [
  { value: "light", label: "Light", Icon: Sun },
  { value: "dark", label: "Dark", Icon: Moon },
  { value: "system", label: "System", Icon: Monitor },
];

/** Light / Dark / System choice as native radios: keyboard and screen-reader friendly. */
export function ThemeSwitcher() {
  const [preference, setPreference] = useState<ThemePreference>(readThemePreference);
  const name = useId();

  function choose(value: ThemePreference) {
    setPreference(value);
    saveThemePreference(value);
  }

  return (
    <fieldset className="flex flex-wrap items-center gap-3">
      <legend className="sr-only">Appearance</legend>
      <span aria-hidden="true" className="text-sm text-muted">
        Appearance
      </span>
      <div className="inline-flex rounded-sm border border-border-strong bg-surface p-0.5">
        {OPTIONS.map(({ value, label, Icon }) => (
          <label key={value} className="relative">
            <input
              type="radio"
              name={name}
              value={value}
              checked={preference === value}
              onChange={() => choose(value)}
              className="peer sr-only"
            />
            <span
              className={cn(
                "flex h-8 cursor-pointer items-center pointer-coarse:h-11 gap-1.5 rounded-sm px-2.5 text-sm text-muted transition-colors",
                "peer-checked:bg-primary-subtle peer-checked:font-medium peer-checked:text-primary hover:text-fg",
                "peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-focus-ring",
              )}
            >
              <Icon aria-hidden="true" strokeWidth={1.5} className="size-4" />
              {label}
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
