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
  const base = {
    preset_key: "gyms",
    location: "Sofia",
    neighborhoods: ["Lozenets"],
    category: "gyms",
    keywords: "",
    min_rating: 4,
    min_reviews: Number.NaN,
    max_reviews: Number.NaN,
    has_website: "no" as const,
    open_in_window: false,
    window_start: "19:00",
    window_end: "21:00",
    lead_quality: "high" as const,
    max_results: 60,
    audit_websites: true,
  };

  it("maps form values to the API request", () => {
    const parsed = searchSchema.parse(base);
    expect(toSearchRequest(parsed)).toMatchObject({
      category: "gyms",
      location: "Sofia",
      neighborhoods: ["Lozenets"],
      preset_key: "gyms",
      min_rating: 4,
      min_reviews: null,
      max_reviews: null,
      keywords: null,
      has_website: "no",
      lead_quality: "high",
    });
  });

  it("rejects invalid input", () => {
    expect(searchSchema.safeParse({ ...base, location: "" }).success).toBe(false);
    expect(searchSchema.safeParse({ ...base, min_reviews: 50, max_reviews: 10 }).success).toBe(false);
    expect(searchSchema.safeParse({ ...base, window_start: "25:00" }).success).toBe(false);
  });
});
