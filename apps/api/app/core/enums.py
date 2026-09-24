"""Domain enumerations and their human-readable labels.

Labels are phrased as observations ("No website detected"), never as claims
about what a business needs.
"""

from __future__ import annotations

from enum import StrEnum


class LeadStatus(StrEnum):
    NEW = "NEW"
    CALLED = "CALLED"
    NO_ANSWER = "NO_ANSWER"
    CALLBACK = "CALLBACK"
    INTERESTED = "INTERESTED"
    QUALIFIED = "QUALIFIED"
    PROPOSAL = "PROPOSAL"
    WON = "WON"
    LOST = "LOST"
    DO_NOT_CONTACT = "DO_NOT_CONTACT"


class CallOutcome(StrEnum):
    NO_ANSWER = "NO_ANSWER"
    INTERESTED = "INTERESTED"
    CALLBACK = "CALLBACK"
    NOT_INTERESTED = "NOT_INTERESTED"
    WRONG_NUMBER = "WRONG_NUMBER"
    ALREADY_HAS_PROVIDER = "ALREADY_HAS_PROVIDER"
    DO_NOT_CONTACT = "DO_NOT_CONTACT"


class Priority(StrEnum):
    HOT = "HOT"
    WARM = "WARM"
    COLD = "COLD"


PRIORITY_RANK: dict[Priority, int] = {Priority.HOT: 0, Priority.WARM: 1, Priority.COLD: 2}


class OpportunityType(StrEnum):
    NO_WEBSITE = "NO_WEBSITE"
    BROKEN_WEBSITE = "BROKEN_WEBSITE"
    OUTDATED_WEBSITE = "OUTDATED_WEBSITE"
    WEBSITE_REDESIGN = "WEBSITE_REDESIGN"
    MOBILE_PROBLEM = "MOBILE_PROBLEM"
    NO_BOOKING = "NO_BOOKING"
    NO_CONTACT_CTA = "NO_CONTACT_CTA"
    WEAK_CONVERSION = "WEAK_CONVERSION"
    SLOW_WEBSITE = "SLOW_WEBSITE"
    GOOGLE_PROFILE = "GOOGLE_PROFILE"
    LOW_REVIEWS = "LOW_REVIEWS"
    MISSING_BUSINESS_INFO = "MISSING_BUSINESS_INFO"


OPPORTUNITY_LABELS: dict[OpportunityType, str] = {
    OpportunityType.NO_WEBSITE: "No website",
    OpportunityType.BROKEN_WEBSITE: "Broken website",
    OpportunityType.OUTDATED_WEBSITE: "Outdated website",
    OpportunityType.WEBSITE_REDESIGN: "Website redesign",
    OpportunityType.MOBILE_PROBLEM: "Mobile problem",
    OpportunityType.NO_BOOKING: "No online booking",
    OpportunityType.NO_CONTACT_CTA: "No contact CTA",
    OpportunityType.WEAK_CONVERSION: "Weak conversion path",
    OpportunityType.SLOW_WEBSITE: "Slow website",
    OpportunityType.GOOGLE_PROFILE: "Google profile gaps",
    OpportunityType.LOW_REVIEWS: "Low review volume",
    OpportunityType.MISSING_BUSINESS_INFO: "Missing business info",
}

GOOGLE_OPPORTUNITIES = frozenset(
    {OpportunityType.GOOGLE_PROFILE, OpportunityType.LOW_REVIEWS, OpportunityType.MISSING_BUSINESS_INFO}
)
WEBSITE_PROBLEM_OPPORTUNITIES = frozenset(
    {
        OpportunityType.BROKEN_WEBSITE,
        OpportunityType.OUTDATED_WEBSITE,
        OpportunityType.WEBSITE_REDESIGN,
        OpportunityType.MOBILE_PROBLEM,
        OpportunityType.SLOW_WEBSITE,
    }
)


class DataQuality(StrEnum):
    EXCELLENT = "EXCELLENT"
    GOOD = "GOOD"
    PARTIAL = "PARTIAL"
    POOR = "POOR"


class WebsiteStatus(StrEnum):
    NONE = "none"  # no website listed
    UNAUDITED = "unaudited"  # website listed, not audited yet
    OK = "ok"  # audit succeeded
    BROKEN = "broken"  # unreachable / error page / parked
    SKIPPED = "skipped"  # e.g. robots.txt disallows


class AuditStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class JobKind(StrEnum):
    SEARCH = "search"
    AUDIT = "audit"
    RESCORE = "rescore"
    MAINTENANCE = "maintenance"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_JOB_STATUSES = frozenset(
    {JobStatus.COMPLETED, JobStatus.PARTIAL, JobStatus.FAILED, JobStatus.CANCELLED}
)


class PhoneSource(StrEnum):
    GOOGLE_PLACES = "google_places"
    WEBSITE = "website"
    IMPORT = "import"
    MANUAL = "manual"
    DEMO = "demo"


class UserRole(StrEnum):
    ADMIN = "admin"
    SALES = "sales"


class Severity(StrEnum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    INFO = "info"
