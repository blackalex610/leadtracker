import { describe, expect, it } from "vitest";

import { formatMoney, healthTone, mapsSearchUrl, relativeTime, telHref } from "@/lib/format";
import { activeFilterCount, parseLeadQuery, QUICK_FILTERS, serializeLeadQuery, withoutPaging } from "@/lib/lead-query";
import { searchSchema, toSearchRequest } from "@/features/search/search-schema";

describe("lead query <-> URL", () => {
  it("parses typed filters and drops unknown values", () => {
    const params = new URLSearchParams(
      "priority=HOT&priority=BOGUS&opportunity=NO_WEBSITE&has_phone=true&contacted=false&min_rating=4.5&sort=rating&order=asc&page=2&evil=1",
    );
    expect(parseLeadQuery(params)).toEqual({
      priority: ["HOT"],
      opportunity: ["NO_WEBSITE"],
      has_phone: true,
      contacted: false,
      min_rating: 4.5,
      sort: "rating",
      order: "asc",
      page: 2,
    });
  });

  it("round-trips through the URL", () => {
    const query = { priority: ["HOT" as const, "WARM" as const], q: "бела", has_website: false };
    expect(parseLeadQuery(serializeLeadQuery(query))).toEqual(query);
  });

  it("quick filters toggle and reset paging", () => {
    const noWebsite = QUICK_FILTERS.find((f) => f.id === "no-website")!;
    const on = noWebsite.toggle({ page: 3 });
    expect(on).toEqual({ opportunity: ["NO_WEBSITE"], page: undefined });
    expect(noWebsite.isActive(on)).toBe(true);
    expect(noWebsite.toggle(on).opportunity).toBeUndefined();
    const contacted = QUICK_FILTERS.find((f) => f.id === "contacted")!;
    expect(contacted.toggle({ contacted: true }).contacted).toBeUndefined();
  });

  it("parses lead categories and the 'needs a website' quick filter", () => {
    expect(parseLeadQuery(new URLSearchParams("lead_category=NO_SITE&lead_category=NOPE&target_key=plumbers"))).toEqual({
      lead_category: ["NO_SITE"],
      target_key: "plumbers",
    });
    const needsSite = QUICK_FILTERS.find((f) => f.id === "needs-site")!;
    const on = needsSite.toggle({});
    expect(on.lead_category).toEqual(["BROKEN_SITE", "NO_SITE", "SOCIAL_ONLY", "NEW_BUSINESS", "PLATFORM_ONLY"]);
    expect(needsSite.isActive(on)).toBe(true);
    expect(needsSite.isActive({ lead_category: ["NO_SITE"] })).toBe(false);
    expect(needsSite.toggle(on).lead_category).toBeUndefined();
  });

  it("counts active filters and strips paging for export", () => {
    const query = { priority: ["HOT" as const], sort: "name" as const, page: 2, page_size: 100 };
    expect(activeFilterCount(query)).toBe(1);
    expect(withoutPaging(query)).toEqual({ priority: ["HOT"], sort: "name" });
  });
});

describe("formatting helpers", () => {
  it("builds tel: links from E.164", () => {
    expect(telHref("+359 88 812 3456")).toBe("tel:+359888123456");
    expect(telHref(null)).toBeUndefined();
  });

  it("only builds Maps search links (never fake place URLs)", () => {
    expect(mapsSearchUrl("Bella Nails", "ul. Vitosha 1")).toBe(
      "https://www.google.com/maps/search/?api=1&query=Bella%20Nails%2C%20ul.%20Vitosha%201",
    );
  });

  it("classifies health scores", () => {
    expect([healthTone(20), healthTone(55), healthTone(90), healthTone(null)]).toEqual(["bad", "ok", "good", "none"]);
  });

  it("formats money and relative time", () => {
    expect(formatMoney(1.5, "EUR")).toBe("€1.50");
    expect(relativeTime("2026-09-24T09:00:00Z", new Date("2026-09-24T10:00:00Z"))).toBe("1 hour ago");
  });
});

describe("search form schema", () => {
  const base = { location: "Sofia", target_leads: 150, max_queries: 30, use_neighborhoods: true, audit_websites: true };

  it("maps form values to the API request", () => {
    expect(toSearchRequest(searchSchema.parse({ ...base, location: "  Plovdiv " }))).toEqual({ ...base, location: "Plovdiv" });
  });

  it("rejects invalid input", () => {
    expect(searchSchema.safeParse({ ...base, location: "" }).success).toBe(false);
    expect(searchSchema.safeParse({ ...base, target_leads: 0 }).success).toBe(false);
    expect(searchSchema.safeParse({ ...base, target_leads: Number.NaN }).success).toBe(false);
    expect(searchSchema.safeParse({ ...base, max_queries: 500 }).success).toBe(false);
  });
});
