import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

import { fixtures } from "./fixtures";

/** Default handlers shared by all tests; individual tests override with server.use(). */
export const defaultHandlers = [
  http.get("*/api/auth/me", () => HttpResponse.json({ user: fixtures.user, auth_mode: "none" })),
  http.get("*/api/meta", () => HttpResponse.json(fixtures.meta)),
  http.get("*/api/presets", () => HttpResponse.json(fixtures.presets)),
  http.get("*/api/settings", () => HttpResponse.json(fixtures.settings)),
  http.get("*/api/users", () => HttpResponse.json([fixtures.user])),
  http.get("*/api/leads/facets", () =>
    HttpResponse.json({ categories: [{ value: "Gym", count: 2 }], cities: [{ value: "Sofia", count: 2 }], niches: ["gyms"] }),
  ),
];

export const server = setupServer(...defaultHandlers);
