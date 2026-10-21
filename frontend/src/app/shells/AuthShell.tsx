import { Outlet } from "react-router";

import { ThemeSwitcher } from "@/components/ThemeSwitcher";
import { Wordmark } from "@/components/Wordmark";

/** Signed-out layout: one centred column, max 400 px, no marketing panel (Design.md §5). */
export function AuthShell() {
  return (
    <div className="flex min-h-dvh flex-col px-4 py-10 sm:px-6">
      <div className="mx-auto flex w-full max-w-auth flex-1 flex-col">
        <header>
          <Wordmark />
        </header>
        <main className="mt-12 flex-1">
          <Outlet />
        </main>
        <footer className="mt-12 border-t border-border pt-6">
          <ThemeSwitcher />
        </footer>
      </div>
    </div>
  );
}
