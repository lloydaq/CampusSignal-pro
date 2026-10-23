import { useEffect } from "react";

const APP_NAME = "CampusSignal";

/** Each screen names itself in the tab title (WCAG 2.4.2). */
export function usePageTitle(title: string): void {
  useEffect(() => {
    document.title = `${title} · ${APP_NAME}`;
  }, [title]);
}
