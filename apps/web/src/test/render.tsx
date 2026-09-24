import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";

import { RequireAuth } from "@/lib/auth";
import { makeQueryClient, Providers } from "@/providers";

/**
 * Render a page inside the real providers and a memory router.
 * `path` is the route pattern (e.g. "/leads/:id"), `url` the initial location.
 */
export function renderPage(element: ReactElement, { path = "/", url = "/" }: { path?: string; url?: string } = {}) {
  const client = makeQueryClient();
  client.setDefaultOptions({ queries: { retry: false, staleTime: 0, refetchOnWindowFocus: false } });
  const router = createMemoryRouter(
    [
      { path, element: <RequireAuth>{element}</RequireAuth> },
      { path: "*", element: <div>Navigated away</div> },
    ],
    { initialEntries: [url] },
  );
  const user = userEvent.setup();
  const result = render(
    <Providers client={client}>
      <RouterProvider router={router} />
    </Providers>,
  );
  return { ...result, user, router, client };
}
