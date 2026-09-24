import { ACTIVE_JOB_STATUSES, type LeadListQuery } from "@leadtracker/shared";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

export const keys = {
  meta: ["meta"] as const,
  me: ["me"] as const,
  users: ["users"] as const,
  dashboard: ["dashboard"] as const,
  leads: (q: LeadListQuery) => ["leads", q] as const,
  leadsAll: ["leads"] as const,
  facets: ["facets"] as const,
  lead: (id: number) => ["lead", id] as const,
  searchJobs: ["search-jobs"] as const,
  searchJob: (id: number) => ["search-job", id] as const,
  job: (id: number) => ["job", id] as const,
  callingSessions: ["calling-sessions"] as const,
  callingSession: (id: number) => ["calling-session", id] as const,
  settings: ["settings"] as const,
  presets: ["presets"] as const,
  suppression: (all: boolean) => ["suppression", all] as const,
  usage: ["usage"] as const,
};

export const useMeta = () => useQuery({ queryKey: keys.meta, queryFn: api.meta, staleTime: 5 * 60_000 });
export const useUsers = () => useQuery({ queryKey: keys.users, queryFn: api.users, staleTime: 5 * 60_000 });
export const useDashboard = () =>
  useQuery({ queryKey: keys.dashboard, queryFn: api.dashboard, refetchInterval: 60_000 });
export const useFacets = () => useQuery({ queryKey: keys.facets, queryFn: api.facets, staleTime: 60_000 });
export const usePresets = () => useQuery({ queryKey: keys.presets, queryFn: api.presets });
export const useSettings = () => useQuery({ queryKey: keys.settings, queryFn: api.settings });
export const useUsage = () => useQuery({ queryKey: keys.usage, queryFn: api.usage });
export const useSearchJobs = () =>
  useQuery({
    queryKey: keys.searchJobs,
    queryFn: () => api.searchJobs(1, 30),
    refetchInterval: (q) =>
      q.state.data?.items.some((j) => ACTIVE_JOB_STATUSES.includes(j.status)) ? 3000 : false,
  });
export const useCallingSessions = () => useQuery({ queryKey: keys.callingSessions, queryFn: api.callingSessions });

export function useLeads(query: LeadListQuery, options: { refetchInterval?: number | false; enabled?: boolean } = {}) {
  return useQuery({
    queryKey: keys.leads(query),
    queryFn: ({ signal }) => api.leads(query, signal),
    placeholderData: keepPreviousData,
    refetchInterval: options.refetchInterval,
    enabled: options.enabled ?? true,
  });
}

export function useLead(id: number) {
  return useQuery({
    queryKey: keys.lead(id),
    queryFn: () => api.lead(id),
    enabled: Number.isFinite(id),
    // Poll while a website audit for this lead is running.
    refetchInterval: (q) => (q.state.data?.active_job_id ? 2500 : false),
  });
}

export function useSearchJob(id: number | null) {
  return useQuery({
    queryKey: keys.searchJob(id ?? 0),
    queryFn: () => api.searchJob(id as number),
    enabled: id !== null,
    refetchInterval: (q) => (q.state.data && ACTIVE_JOB_STATUSES.includes(q.state.data.status) ? 1500 : false),
  });
}

export function useCallingSession(id: number) {
  return useQuery({ queryKey: keys.callingSession(id), queryFn: () => api.callingSession(id), staleTime: 10_000 });
}

/** Invalidate everything that shows lead data after a mutation. */
export function useInvalidateLeads() {
  const client = useQueryClient();
  return (leadId?: number) => {
    void client.invalidateQueries({ queryKey: keys.leadsAll });
    void client.invalidateQueries({ queryKey: keys.dashboard });
    if (leadId !== undefined) void client.invalidateQueries({ queryKey: keys.lead(leadId) });
  };
}

export function useUpdateSettings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: api.updateSettings,
    onSuccess: (data) => client.setQueryData(keys.settings, data),
  });
}
