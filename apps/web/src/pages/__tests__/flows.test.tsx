import type { CallCreate, LeadSummary } from "@leadtracker/shared";
import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import CallingSessionPage from "@/pages/calling-session";
import { FindLeadsPage } from "@/pages/find-leads";
import { LeadDetailPage } from "@/pages/lead-detail";
import { LeadsPage } from "@/pages/leads";
import { fixtures, makeCard, makeJob, makeLead, makeSession } from "@/test/fixtures";
import { renderPage } from "@/test/render";
import { server } from "@/test/server";

function page(items: LeadSummary[], total = items.length) {
  return { items, total, page: 1, page_size: 50 };
}

describe("Search → results", () => {
  it("starts a search job and shows result cards with the opportunity", async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post("*/api/search/estimate", () =>
        HttpResponse.json({
          queries: 1, max_requests: 3, sku: "text_search_enterprise", estimated_max_cost: 0.105, currency: "USD",
          display_currency: "EUR", estimated_max_cost_display: 0.09, free_units_remaining: 1000,
          provider_configured: true, demo_mode: false,
        }),
      ),
      http.post("*/api/search", async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(makeJob({ status: "queued", progress_total: 0, progress_processed: 0 }), { status: 202 });
      }),
      http.get("*/api/search-jobs/7", () => HttpResponse.json({ ...makeJob(), queries: [] })),
      http.get("*/api/leads", ({ request }) => {
        const url = new URL(request.url);
        expect(url.searchParams.get("job_id")).toBe("7");
        return HttpResponse.json(page([makeLead(), makeLead({ id: 2, name: "Pulse Fitness", priority: "WARM", opportunity_types: ["LOW_REVIEWS"] })]));
      }),
    );
    const { user, router } = renderPage(<FindLeadsPage />, { path: "/search" , url: "/search" });

    const location = await screen.findByLabelText("Location");
    await user.clear(location);
    await user.type(location, "Sofia");
    await screen.findByText(/free requests left this month/);
    await user.click(screen.getByRole("button", { name: "Search" }));

    expect(await screen.findByText("Bella Nails")).toBeInTheDocument();
    expect(screen.getByText("Pulse Fitness")).toBeInTheDocument();
    const card = screen.getByRole("link", { name: "Bella Nails" });
    expect(within(card).getByText("NO_WEBSITE")).toBeInTheDocument();
    expect(within(card).getByText("Hot")).toBeInTheDocument();
    expect(screen.getByText(/2 \/ 2 businesses processed/)).toBeInTheDocument();
    expect(router.state.location.search).toBe("?job=7");
    expect(body).toMatchObject({ category: "gyms", location: "Sofia", preset_key: "gyms", min_rating: 4 });
  });

  it("explains when the provider is not configured", async () => {
    server.use(http.get("*/api/meta", () => HttpResponse.json({ ...fixtures.meta, provider: { name: "google_places", configured: false, demo_mode: false, field_tier: "enterprise" } })));
    renderPage(<FindLeadsPage />, { path: "/search", url: "/search" });
    expect(await screen.findByText("Provider not configured")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Search" })).toBeDisabled());
  });
});

describe("Lead filtering", () => {
  it("applies quick filters server-side and keeps them in the URL", async () => {
    const requests: URLSearchParams[] = [];
    server.use(
      http.get("*/api/leads", ({ request }) => {
        const params = new URL(request.url).searchParams;
        requests.push(params);
        const noWebsite = params.getAll("opportunity").includes("NO_WEBSITE");
        return HttpResponse.json(
          noWebsite ? page([makeLead()]) : page([makeLead(), makeLead({ id: 2, name: "Pulse Fitness", opportunity_types: ["LOW_REVIEWS"] })]),
        );
      }),
    );
    const { user, router } = renderPage(<LeadsPage />, { path: "/leads", url: "/leads" });
    expect(await screen.findByText("Pulse Fitness")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "No website" }));
    await waitFor(() => expect(screen.queryByText("Pulse Fitness")).not.toBeInTheDocument());
    expect(screen.getByText("Bella Nails")).toBeInTheDocument();
    expect(router.state.location.search).toContain("opportunity=NO_WEBSITE");
    const last = requests.at(-1)!;
    expect(last.get("sort")).toBe("priority");
    expect(last.get("page_size")).toBe("50");
    expect(screen.getByRole("button", { name: "No website" })).toHaveAttribute("aria-pressed", "true");
  });

  it("export link carries the active filters (without paging)", async () => {
    server.use(http.get("*/api/leads", () => HttpResponse.json(page([makeLead()]))));
    renderPage(<LeadsPage />, { path: "/leads", url: "/leads?priority=HOT&has_phone=true&page=2" });
    const link = await screen.findByRole("link", { name: /Export CSV/ });
    const href = new URL(link.getAttribute("href")!, "http://localhost");
    expect(href.pathname).toBe("/api/export");
    expect(href.searchParams.get("priority")).toBe("HOT");
    expect(href.searchParams.get("has_phone")).toBe("true");
    expect(href.searchParams.get("page")).toBeNull();
    expect(link).toHaveAttribute("download");
  });

  it("sorts by clicking a column header", async () => {
    const sorts: string[] = [];
    server.use(
      http.get("*/api/leads", ({ request }) => {
        const params = new URL(request.url).searchParams;
        sorts.push(`${params.get("sort")}:${params.get("order")}`);
        return HttpResponse.json(page([makeLead()]));
      }),
    );
    const { user } = renderPage(<LeadsPage />, { path: "/leads", url: "/leads" });
    await screen.findByText("Bella Nails");
    await user.click(screen.getByRole("button", { name: /Reviews/ }));
    await waitFor(() => expect(sorts.at(-1)).toBe("review_count:desc"));
    await user.click(screen.getByRole("button", { name: /Reviews/ }));
    await waitFor(() => expect(sorts.at(-1)).toBe("review_count:asc"));
  });
});

describe("Lead details", () => {
  it("answers 'why this lead' and records a call outcome", async () => {
    let posted: CallCreate | null = null;
    server.use(
      http.get("*/api/leads/101", () => HttpResponse.json(fixtures.leadDetail)),
      http.post("*/api/leads/101/call", async ({ request }) => {
        posted = (await request.json()) as CallCreate;
        return HttpResponse.json({
          call: { id: 1, outcome: "INTERESTED", note: posted.note, phone_dialed: "+359888123456", callback_at: null, user_id: 1, user_name: "Default user", session_id: null, created_at: new Date().toISOString() },
          status: "INTERESTED",
          suppressed: false,
          next_callback_at: null,
        });
      }),
      http.get("*/api/leads", () => HttpResponse.json(page([]))),
      http.get("*/api/dashboard", () => HttpResponse.json({})),
    );
    const { user } = renderPage(<LeadDetailPage />, { path: "/leads/:id", url: "/leads/101" });

    expect(await screen.findByRole("heading", { name: "Iron Gym Lozenets" })).toBeInTheDocument();
    expect(screen.getByText("Why this lead?")).toBeInTheDocument();
    expect(screen.getByText("Website Health 18/100 (below 40)")).toBeInTheDocument();
    const why = screen.getByText("Why this lead?").closest('[data-slot="card"]') as HTMLElement;
    expect(within(why).getByText(/No online booking mechanism detected/)).toBeInTheDocument();
    expect(within(why).getByText(/^HOT:/)).toBeInTheDocument();
    expect(screen.getByText("Suggested pitch")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open in Google Maps/ })).toHaveAttribute("href", "https://maps.google.com/?cid=101");
    expect(screen.getByText("Problems observed", { exact: false })).toBeInTheDocument();

    await user.type(screen.getByLabelText("Call notes"), "Owner answered, send examples");
    await user.click(screen.getByRole("button", { name: "Interested" }));
    await waitFor(() => expect(posted).toEqual({ outcome: "INTERESTED", note: "Owner answered, send examples", callback_at: null }));
  });

  it("asks for confirmation before marking do not contact", async () => {
    let calls = 0;
    server.use(
      http.get("*/api/leads/101", () => HttpResponse.json(fixtures.leadDetail)),
      http.post("*/api/leads/101/call", () => {
        calls += 1;
        return HttpResponse.json({}, { status: 500 });
      }),
    );
    const { user } = renderPage(<LeadDetailPage />, { path: "/leads/:id", url: "/leads/101" });
    await screen.findByRole("heading", { name: "Iron Gym Lozenets" });
    const panel = screen.getByRole("heading", { name: "Call" }).closest('[data-slot="card"]') as HTMLElement;
    await user.click(within(panel).getByRole("button", { name: "Do not contact" }));
    expect(await screen.findByText("Mark as do not contact?")).toBeInTheDocument();
    expect(calls).toBe(0);
  });
});

describe("Calling workflow", () => {
  it("records outcomes with keyboard shortcuts and advances", async () => {
    const first = makeLead({ id: 11, name: "First Gym" });
    const second = makeLead({ id: 12, name: "Second Salon" });
    const third = makeLead({ id: 13, name: "Third Barber" });
    const posted: { id: string; body: CallCreate }[] = [];
    server.use(
      http.get("*/api/calling-sessions/3", () => HttpResponse.json(makeSession([makeCard(first), makeCard(second), makeCard(third)]))),
      http.patch("*/api/calling-sessions/3", () => HttpResponse.json({ id: 3, started_at: "", ended_at: null, total: 3, position: 1, stats: {}, filters: {} })),
      http.post("*/api/leads/:id/call", async ({ params, request }) => {
        const body = (await request.json()) as CallCreate;
        posted.push({ id: String(params.id), body });
        return HttpResponse.json({ call: { id: posted.length, outcome: body.outcome, note: null, phone_dialed: null, callback_at: null, user_id: 1, user_name: null, session_id: 3, created_at: new Date().toISOString() }, status: "NO_ANSWER", suppressed: body.outcome === "DO_NOT_CONTACT", next_callback_at: null });
      }),
      http.get("*/api/leads", () => HttpResponse.json(page([]))),
      http.get("*/api/dashboard", () => HttpResponse.json({})),
    );
    const { user } = renderPage(<CallingSessionPage />, { path: "/calling/:id", url: "/calling/3" });

    expect(await screen.findByRole("heading", { name: "First Gym" })).toBeInTheDocument();
    expect(screen.getByText("Why we're calling")).toBeInTheDocument();
    expect(screen.getByText("1 / 3")).toBeInTheDocument();

    await user.keyboard("n");
    expect(await screen.findByRole("heading", { name: "Second Salon" })).toBeInTheDocument();
    expect(posted[0]).toEqual({ id: "11", body: { outcome: "NO_ANSWER", session_id: 3, note: null, callback_at: null } });

    // Typing a note must not trigger shortcuts
    await user.click(screen.getByLabelText("Call notes"));
    await user.keyboard("nib");
    expect(posted).toHaveLength(1);
    await user.keyboard("{Escape}");

    await user.keyboard("i");
    expect(await screen.findByRole("heading", { name: "Third Barber" })).toBeInTheDocument();
    expect(posted[1]!.body).toMatchObject({ outcome: "INTERESTED", note: "nib" });

    // Do not contact needs a second press
    await user.keyboard("d");
    expect(await screen.findByText(/permanently mark this number/)).toBeInTheDocument();
    expect(posted).toHaveLength(2);
    await user.keyboard("d");
    await waitFor(() => expect(posted[2]!.body.outcome).toBe("DO_NOT_CONTACT"));
    expect(await screen.findByText("Session complete")).toBeInTheDocument();
  });

  it("never lets a suppressed lead be called", async () => {
    const blocked = makeLead({ id: 21, name: "Blocked Spa", suppressed: true });
    server.use(
      http.get("*/api/calling-sessions/3", () =>
        HttpResponse.json(makeSession([makeCard(blocked, { callable: false, not_callable_reason: "On the do-not-contact list" })])),
      ),
    );
    const { user } = renderPage(<CallingSessionPage />, { path: "/calling/:id", url: "/calling/3" });
    expect(await screen.findByText("On the do-not-contact list")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Call C" })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Interested/ })).toBeDisabled();
    await user.keyboard("i");
    expect(await screen.findAllByText(/On the do-not-contact list/)).not.toHaveLength(0);
  });
});
