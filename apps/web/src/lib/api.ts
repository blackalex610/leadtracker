import type {
  ApiErrorBody,
  BulkLeadUpdate,
  BulkResult,
  CallCreate,
  CallResult,
  CallingFilters,
  CallingPreview,
  CallingSession,
  CallingSessionSummary,
  Dashboard,
  Facets,
  ImportCommit,
  ImportPreview,
  ImportResult,
  JobOut,
  JobPage,
  JobRef,
  LeadDetail,
  LeadListQuery,
  LeadPage,
  LeadUpdate,
  MeResponse,
  Meta,
  NoteOut,
  Preset,
  PresetCreate,
  PresetUpdate,
  RuntimeSettings,
  SearchEstimate,
  SearchJobDetail,
  SearchRequest,
  SettingsOut,
  SuppressionCreate,
  SuppressionEntry,
  Usage,
  User,
  WorkerRun,
} from "@leadtracker/shared";

const BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export const UNAUTHORIZED_EVENT = "lt:unauthorized";

type QueryValue = string | number | boolean | null | undefined | readonly (string | number)[];
export type Query = Record<string, QueryValue>;

export function toSearchParams(query?: Query): URLSearchParams {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      for (const item of value) params.append(key, String(item));
    } else {
      params.set(key, String(value));
    }
  }
  return params;
}

export function apiUrl(path: string, query?: Query): string {
  const qs = toSearchParams(query).toString();
  return `${BASE}${path}${qs ? `?${qs}` : ""}`;
}

async function request<T>(
  method: string,
  path: string,
  options: { query?: Query; body?: unknown; form?: FormData; signal?: AbortSignal } = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(apiUrl(path, options.query), {
      method,
      credentials: "include",
      headers: options.body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: options.form ?? (options.body !== undefined ? JSON.stringify(options.body) : undefined),
      signal: options.signal,
    });
  } catch (error) {
    if ((error as Error).name === "AbortError") throw error;
    throw new ApiError(0, "network_error", "Cannot reach the API. Is the backend running?");
  }
  if (!response.ok) {
    let code = "http_error";
    let message = `Request failed (${response.status})`;
    try {
      const data = (await response.json()) as ApiErrorBody;
      code = data.detail?.code ?? code;
      message = data.detail?.message ?? message;
    } catch {
      /* not JSON */
    }
    if (response.status === 401) window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT));
    throw new ApiError(response.status, code, message);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

let onJobQueued: (() => void) | null = null;

/** Called after a request that queues a background job (see lib/worker-pump.ts). */
export function setJobQueuedListener(listener: (() => void) | null): void {
  onJobQueued = listener;
}

function queuesJob<T>(promise: Promise<T>): Promise<T> {
  return promise.then((result) => {
    onJobQueued?.();
    return result;
  });
}

const get = <T,>(path: string, query?: Query, signal?: AbortSignal) => request<T>("GET", path, { query, signal });
const post = <T,>(path: string, body?: unknown) => request<T>("POST", path, { body: body ?? {} });
const patch = <T,>(path: string, body: unknown) => request<T>("PATCH", path, { body });
const del = <T,>(path: string) => request<T>("DELETE", path);

export type SettingsPatch = { [K in keyof RuntimeSettings]?: Record<string, unknown> };

export const api = {
  meta: () => get<Meta>("/api/meta"),
  runWorker: () => post<WorkerRun>("/api/worker/run"),
  me: () => get<MeResponse>("/api/auth/me"),
  login: (token: string) => post<MeResponse>("/api/auth/login", { token }),
  logout: () => post<{ ok: boolean }>("/api/auth/logout"),
  users: () => get<User[]>("/api/users"),

  dashboard: () => get<Dashboard>("/api/dashboard"),

  leads: (query: LeadListQuery, signal?: AbortSignal) => get<LeadPage>("/api/leads", query as Query, signal),
  facets: () => get<Facets>("/api/leads/facets"),
  lead: (id: number) => get<LeadDetail>(`/api/leads/${id}`),
  updateLead: (id: number, body: LeadUpdate) => patch<LeadDetail>(`/api/leads/${id}`, body),
  bulkUpdate: (body: BulkLeadUpdate) => post<BulkResult>("/api/leads/bulk", body),
  auditLead: (id: number) => queuesJob(post<JobRef>(`/api/leads/${id}/audit`)),
  auditMany: (ids: number[]) => queuesJob(post<JobRef>("/api/leads/audit", { ids, force: true })),
  rescoreLead: (id: number) => post<LeadDetail>(`/api/leads/${id}/rescore`),
  refreshLead: (id: number) => post<LeadDetail>(`/api/leads/${id}/refresh`),
  recordCall: (id: number, body: CallCreate) => post<CallResult>(`/api/leads/${id}/call`, body),
  addNote: (id: number, body: string) => post<NoteOut>(`/api/leads/${id}/notes`, { body }),
  exportUrl: (query: Omit<LeadListQuery, "page" | "page_size">) => apiUrl("/api/export", query as Query),

  estimateSearch: (body: SearchRequest) => post<SearchEstimate>("/api/search/estimate", body),
  createSearch: (body: SearchRequest) => queuesJob(post<JobOut>("/api/search", body)),
  searchJobs: (page = 1, pageSize = 20) => get<JobPage>("/api/search-jobs", { page, page_size: pageSize }),
  searchJob: (id: number) => get<SearchJobDetail>(`/api/search-jobs/${id}`),
  cancelJob: (id: number) => post<JobOut>(`/api/search-jobs/${id}/cancel`),
  retryJob: (id: number) => queuesJob(post<JobOut>(`/api/search-jobs/${id}/retry`)),
  job: (id: number) => get<JobOut>(`/api/jobs/${id}`),

  callingPreview: (filters: Partial<CallingFilters>) => post<CallingPreview>("/api/calling-sessions/preview", filters),
  createCallingSession: (filters: Partial<CallingFilters>) => post<CallingSession>("/api/calling-sessions", filters),
  callingSessions: () => get<CallingSessionSummary[]>("/api/calling-sessions"),
  callingSession: (id: number) => get<CallingSession>(`/api/calling-sessions/${id}`),
  updateCallingSession: (id: number, position: number) =>
    patch<CallingSessionSummary>(`/api/calling-sessions/${id}`, { position }),
  endCallingSession: (id: number) => post<CallingSessionSummary>(`/api/calling-sessions/${id}/end`),

  settings: () => get<SettingsOut>("/api/settings"),
  updateSettings: (body: SettingsPatch) => patch<SettingsOut>("/api/settings", body),
  rescoreAll: () => queuesJob(post<JobRef>("/api/settings/rescore")),
  usage: () => get<Usage>("/api/usage"),

  presets: () => get<Preset[]>("/api/presets"),
  createPreset: (body: PresetCreate) => post<Preset>("/api/presets", body),
  updatePreset: (id: number, body: PresetUpdate) => patch<Preset>(`/api/presets/${id}`, body),
  deletePreset: (id: number) => del<{ ok: boolean }>(`/api/presets/${id}`),

  suppression: (includeInactive = false) =>
    get<SuppressionEntry[]>("/api/suppression", { include_inactive: includeInactive }),
  addSuppression: (body: SuppressionCreate) => post<SuppressionEntry>("/api/suppression", body),
  reenableSuppression: (id: number) => del<SuppressionEntry>(`/api/suppression/${id}`),

  importPreview: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<ImportPreview>("POST", "/api/import/preview", { form });
  },
  importRemap: (body: ImportCommit) => post<ImportPreview>("/api/import/remap", body),
  importCommit: (body: ImportCommit) => queuesJob(post<ImportResult>("/api/import", body)),
};

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong";
}
