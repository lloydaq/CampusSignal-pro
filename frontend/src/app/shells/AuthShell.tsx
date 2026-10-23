import { Outlet } from "react-router";

import { TextLink } from "@/components/TextLink";
import { ThemeSwitcher } from "@/components/ThemeSwitcher";
import { Wordmark } from "@/components/Wordmark";

/** Layout for the signed-out screens and, until the campus shell (Phase 3), the account page: one centred column, max 400 px, no marketing panel (Design.md §5). */
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
        <footer className="mt-12 space-y-4 border-t border-border pt-6">
          <ThemeSwitcher />
          <p className="text-sm text-muted">
            <TextLink to="/status">Service status</TextLink>
          </p>
        </footer>
      </div>
    </div>
  );
}
