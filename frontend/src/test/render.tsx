import { QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";

import { createQueryClient } from "@/app/queryClient";
import { routes } from "@/app/routes";

/**
 * Render the real route tree at `path` with the app's query client (including its 401
 * handling), minus retries so failures show at once. Returns the router for URL checks.
 */
export function renderRoute(path = "/") {
  const queryClient = createQueryClient();
  queryClient.setDefaultOptions({ ...queryClient.getDefaultOptions(), queries: { ...queryClient.getDefaultOptions().queries, retry: false } });
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const result = render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { ...result, router, queryClient };
}
