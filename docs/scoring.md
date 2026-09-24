# Scores and rules

Three different numbers, never mixed up:

| Score | Range | Direction | Answers |
|---|---|---|---|
| **Website Health** | 0–100 | higher = healthier | How good is the site technically and commercially? |
| **Outdated index** | 0–100 | higher = more outdated | How dated does the site measurably look? |
| **Opportunity Score** | 0–100 | higher = better sales opportunity | Is there a specific, defensible reason to call? |

Everything is deterministic and explained by stored reasons. Weights and thresholds are
edited in **Settings → Scoring**; after changing them press *Rescore all leads*.

## Website Health

Five categories, each starting at its maximum and losing the penalties of the signals
observed in it (floored at 0):

| Category | Max | Example signals (penalty) |
|---|---|---|
| Technical | 25 | not HTTPS (10), SSL error (10), very slow (8), slow (4), missing title (4), broken images (4), broken links (4), mixed content (3), missing meta description / H1 (2) |
| Mobile | 20 | no viewport (14), fixed-width viewport (10), Flash (10), fixed-width table layout (6), fixed-width CSS container (4), zoom disabled (2) |
| Conversion | 25 | no phone (7), no contact CTA (6), no booking (6, only for booking-oriented categories), no services section (4), no contact form (3), no location (3), no prices (2), no hours (2), phone not tappable (2) |
| Content | 15 | under construction / parked / server default page (15), placeholder text (8), copyright 3+ years old (6), very little text (5), prices only in BGN after 1 Jan 2026 (5), unfinished `#` links (4), generic template wording (3) |
| Trust | 15 | neither phone nor address (8), no privacy/cookie policy (4), no testimonials (3), no "About" (3) |

Parked domains, server default pages and "coming soon" pages are capped at 10 and treated
as a broken website. The full catalog is `apps/api/app/audit/signals.py`.

## Outdated index

Sum of observable signals, capped at 100: copyright 5+ years (25) / 3–4 (15) / 2 (8);
obsolete tags like `<font>`, `<center>`, `<marquee>` (20 or 10); not mobile-ready (20);
Flash (20); legacy doctype (10); table layout (10); no HTTPS (10); very slow (10) / slow (5);
placeholder content (10); no modern CTA (10); broken images (5); dead links (5);
presentational attributes (5); jQuery 1.x (5); IE-era markup (5); WordPress < 5 (5);
prices not updated for the euro (5).

Bands: 0–19 modern/healthy · 20–39 some issues · 40–59 needs improvement ·
60–79 clearly outdated · 80–100 severe problems.

## Opportunity rules (defaults)

| Rule | Points | Tag | Fires when |
|---|---|---|---|
| no_website | 35 | NO_WEBSITE | no website, or listing links only to a social / link-hub / booking-platform page |
| website_broken | 30 | BROKEN_WEBSITE | DNS/SSL/connection failure, 4xx/5xx, parked, under construction (not for bot-blocked sites) |
| low_health | 25 | WEBSITE_REDESIGN | Website Health < 40 |
| no_booking | 15 | NO_BOOKING | booking-oriented category and no booking detected (or no working site) |
| no_contact_cta | 10 | NO_CONTACT_CTA | no call/contact/book element |
| mobile_problem | 10 | MOBILE_PROBLEM | no/fixed viewport or Flash |
| weak_conversion | 10 | WEAK_CONVERSION | ≥ 3 conversion elements missing |
| outdated_website | 10 | OUTDATED_WEBSITE | Outdated index ≥ 50 |
| slow_website | 5 | SLOW_WEBSITE | homepage slower than the "very slow" threshold |
| incomplete_google | 5 | GOOGLE_PROFILE | few photos, missing description (when requested), category mismatch |
| missing_business_info | 5 | MISSING_BUSINESS_INFO | hours, phone or address missing on the listing |
| low_reviews | 5 | LOW_REVIEWS | reviews < 20 — a social-proof opportunity, not a quality verdict |
| discovery_category | 5 | — | category relies on online discovery |
| open_in_calling_window | 5 | — | open during the calling window on ≥ 3 weekdays |
| phone_available | 5 | — | valid phone number |

Score = sum of fired rules, capped at 100.

## Priority

* **HOT** — phone available **and** discovery-dependent category **and** a major issue
  (no website, broken website, low health, no booking) **and** score ≥ 50.
* **WARM** — phone available and score ≥ 25.
* **COLD** — everything else, and any business listed as temporarily/permanently closed.

Each requirement is a toggle. The written reason is stored, e.g.
`HOT: phone available · strong category · major issue: NO_WEBSITE · score 65 ≥ 50`.

## Category knowledge

A lead's niche comes from the search template that found it or from its Google primary
type matching a template's `match_types`. Templates say whether customers *book* and
whether the category *relies on online discovery*. Without a template, the
`strong_types` / `booking_types` lists in Settings → Scoring are used.

## Wording

Reasons and pitches state observations, never assumptions:
"No booking mechanism detected", not "Customers cannot book online".
The pitch (EN/BG) only mentions signals that were actually observed.
