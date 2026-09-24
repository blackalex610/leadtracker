/**
 * Friendly aliases over the types generated from the FastAPI OpenAPI schema.
 * Regenerate with `pnpm gen:api` after changing backend schemas.
 */
import type { components, operations } from "./generated/api";

type S = components["schemas"];

export type LeadStatus = S["LeadStatus"];
export type CallOutcome = S["CallOutcome"];
export type Priority = S["Priority"];
export type OpportunityType = S["OpportunityType"];
export type DataQuality = S["DataQuality"];
export type JobStatus = S["JobStatus"];
export type RuleKey = S["RuleKey"];

export type LeadSummary = S["LeadSummary"];
export type LeadDetail = S["LeadDetail"];
export type LeadUpdate = S["LeadUpdate"];
export type ScoreReason = S["ScoreReason"];
export type AuditOut = S["AuditOut"];
export type ContactOut = S["ContactOut"];
export type CallOut = S["CallOut"];
export type CallCreate = S["CallCreate"];
export type CallResult = S["CallResult"];
export type NoteOut = S["NoteOut"];
export type EventOut = S["EventOut"];
export type PitchOut = S["PitchOut"];
export type LeadPage = S["Page_LeadSummary_"];
export type BulkLeadUpdate = S["BulkLeadUpdate"];
export type BulkResult = S["BulkResult"];
export type JobRef = S["JobRef"];

export type SearchRequest = S["SearchRequest"];
export type SearchEstimate = S["SearchEstimate"];
export type JobOut = S["JobOut"];
export type JobPage = S["Page_JobOut_"];
export type SearchJobDetail = S["SearchJobDetail"];
export type SearchQueryOut = S["SearchQueryOut"];

export type CallingFilters = S["CallingFilters"];
export type CallingCard = S["CallingCard"];
export type CallingSession = S["CallingSessionOut"];
export type CallingSessionSummary = S["CallingSessionSummary"];
export type CallingPreview = S["CallingPreview"];

export type Dashboard = S["DashboardOut"];
export type DashboardKpis = S["DashboardKpis"];
export type CostEstimate = S["CostEstimate"];
export type Usage = S["UsageOut"];
export type Facets = S["FacetsOut"];

export type SettingsOut = S["SettingsOut"];
export type RuntimeSettings = S["RuntimeSettings"];
export type ScoringConfig = S["ScoringConfig"];
export type Preset = S["PresetOut"];
export type PresetCreate = S["PresetCreate"];
export type PresetUpdate = S["PresetUpdate"];
export type SuppressionEntry = S["SuppressionOut"];
export type SuppressionCreate = S["SuppressionCreate"];

export type ImportPreview = S["ImportPreview"];
export type ImportPreviewRow = S["ImportPreviewRow"];
export type ImportCommit = S["ImportCommit"];
export type ImportResult = S["ImportResult"];

export type Meta = S["MetaOut"];
export type WorkerRun = S["WorkerRunOut"];
export type User = S["UserOut"];
export type MeResponse = S["MeResponse"];

export type LeadListQuery = NonNullable<operations["get_leads_api_leads_get"]["parameters"]["query"]>;
export type SortField = NonNullable<LeadListQuery["sort"]>;

/** Standard error envelope returned by the API. */
export interface ApiErrorBody {
  detail: { code: string; message: string; errors?: { loc: (string | number)[]; msg: string }[] };
}
