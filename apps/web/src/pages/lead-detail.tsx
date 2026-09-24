import { LEAD_STATUSES, STATUS_LABELS, type LeadDetail, type LeadStatus, type LeadUpdate } from "@leadtracker/shared";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeftIcon,
  ExternalLinkIcon,
  MapIcon,
  MoreHorizontalIcon,
  RefreshCwIcon,
} from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { toast } from "sonner";

import { DemoBadge, OpportunityTags, PriorityBadge } from "@/components/app/badges";
import { CallButton } from "@/components/app/phone";
import { ErrorState, PageFallback } from "@/components/app/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { AuditCard } from "@/features/lead/audit-card";
import { BusinessCard, GoogleProfileCard } from "@/features/lead/business-card";
import { CallPanel } from "@/features/lead/call-panel";
import { ActivityCard, NotesCard } from "@/features/lead/notes-activity";
import { PitchCard } from "@/features/lead/pitch-card";
import { WhyCard } from "@/features/lead/why-card";
import { ApiError, api, errorMessage } from "@/lib/api";
import { displayDomain, mapsSearchUrl } from "@/lib/format";
import { keys, useInvalidateLeads, useLead, useSettings, useUsers } from "@/lib/queries";

export function LeadDetailPage() {
  const { id } = useParams();
  const leadId = Number(id);
  const lead = useLead(leadId);
  const settings = useSettings();

  if (lead.isPending) return <PageFallback />;
  if (lead.error) {
    return (
      <div className="p-5">
        <Link to="/leads" className="text-xs text-muted-foreground hover:underline">
          ← Leads
        </Link>
        <ErrorState error={lead.error} onRetry={() => void lead.refetch()} />
      </div>
    );
  }
  const data = lead.data;
  return (
    <div className="flex flex-col">
      <LeadHeader lead={data} />
      <div className="grid gap-4 p-5 xl:grid-cols-[minmax(0,2fr)_minmax(20rem,1fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          <WhyCard lead={data} />
          <PitchCard lead={data} defaultLanguage={settings.data?.runtime.general.pitch_language} />
          <AuditCard lead={data} />
          <GoogleProfileCard lead={data} />
        </div>
        <div className="flex min-w-0 flex-col gap-4">
          <CallPanel lead={data} />
          <BusinessCard lead={data} />
          <NotesCard lead={data} />
          <ActivityCard lead={data} />
        </div>
      </div>
    </div>
  );
}

function LeadHeader({ lead }: { lead: LeadDetail }) {
  const navigate = useNavigate();
  const client = useQueryClient();
  const invalidate = useInvalidateLeads();
  const users = useUsers();
  const [pendingStatus, setPendingStatus] = useState<LeadStatus | null>(null);
  const [editWebsite, setEditWebsite] = useState(false);

  const update = useMutation({
    mutationFn: (body: LeadUpdate) => api.updateLead(lead.id, body),
    onSuccess: (data) => {
      client.setQueryData(keys.lead(lead.id), data);
      invalidate();
      setPendingStatus(null);
      toast.success("Lead updated");
    },
    onError: (e, body) => {
      if (e instanceof ApiError && e.code === "reenable_confirmation_required" && body.status) {
        setPendingStatus(body.status);
        return;
      }
      toast.error(errorMessage(e));
    },
  });
  const action = (fn: () => Promise<unknown>, success: string) => () =>
    fn()
      .then(() => {
        toast.success(success);
        invalidate(lead.id);
      })
      .catch((e: unknown) => toast.error(errorMessage(e)));

  const mapsUrl = lead.google_maps_url ?? mapsSearchUrl(lead.name, lead.address);

  return (
    <div className="sticky top-0 z-20 border-b bg-background/95 px-5 py-3 backdrop-blur">
      <button
        type="button"
        onClick={() => (window.history.length > 1 ? navigate(-1) : navigate("/leads"))}
        className="mb-1 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
      >
        <ArrowLeftIcon className="size-3" /> Back
      </button>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-lg font-semibold">{lead.name}</h1>
            <PriorityBadge priority={lead.priority} reason={lead.priority_reason} />
            {lead.is_demo && <DemoBadge />}
            {lead.suppressed && <Badge variant="hot">Do not contact</Badge>}
          </div>
          <p className="text-xs text-muted-foreground">
            {[lead.niche_label ?? lead.category, lead.neighborhood, lead.city].filter(Boolean).join(" · ")}
          </p>
          <OpportunityTags types={lead.opportunity_types} max={6} className="mt-1.5" />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Select
            value={lead.status}
            onValueChange={(v) => update.mutate({ status: v as LeadStatus })}
          >
            <SelectTrigger size="sm" className="w-40" aria-label="Lead status">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {LEAD_STATUSES.map((s) => (
                <SelectItem key={s} value={s}>
                  {STATUS_LABELS[s]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={lead.assigned_to_id ? String(lead.assigned_to_id) : "none"}
            onValueChange={(v) => update.mutate(v === "none" ? { unassign: true } : { assigned_to_id: Number(v) })}
          >
            <SelectTrigger size="sm" className="w-36" aria-label="Assigned to">
              <SelectValue placeholder="Unassigned" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="none">Unassigned</SelectItem>
              {users.data?.map((u) => (
                <SelectItem key={u.id} value={String(u.id)}>
                  {u.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <CallButton
            phone={lead.normalized_phone}
            display={lead.international_phone}
            isDemo={lead.is_demo}
            invalid={lead.phone_invalid}
            suppressed={lead.suppressed}
            size="sm"
          />
          <Button size="sm" variant="outline" asChild>
            <a href={mapsUrl} target="_blank" rel="noopener noreferrer">
              <MapIcon /> {lead.google_maps_url ? "Open in Google Maps" : "Search in Google Maps"}
            </a>
          </Button>
          {lead.website_url && (
            <Button size="sm" variant="outline" asChild>
              <a href={lead.website_url} target="_blank" rel="noopener noreferrer nofollow">
                <ExternalLinkIcon /> {displayDomain(lead.website_url)}
              </a>
            </Button>
          )}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button size="icon-sm" variant="outline" aria-label="More actions">
                <MoreHorizontalIcon />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem
                disabled={!lead.website_url || lead.website_kind !== "own"}
                onSelect={action(() => api.auditLead(lead.id), "Website audit started")}
              >
                <RefreshCwIcon /> Re-audit website
              </DropdownMenuItem>
              <DropdownMenuItem
                disabled={lead.provider !== "google_places" || !lead.provider_place_id}
                onSelect={action(() => api.refreshLead(lead.id), "Refreshed from Google")}
              >
                Refresh from Google (1 request)
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={action(() => api.rescoreLead(lead.id), "Rescored")}>Rescore</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => setEditWebsite(true)}>Edit website URL</DropdownMenuItem>
              <DropdownMenuSeparator />
              {!lead.suppressed && (
                <DropdownMenuItem variant="destructive" onSelect={() => update.mutate({ status: "DO_NOT_CONTACT" })}>
                  Mark do not contact
                </DropdownMenuItem>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      <Dialog open={pendingStatus !== null} onOpenChange={(open) => !open && setPendingStatus(null)}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Re-enable this number?</DialogTitle>
            <DialogDescription>
              This lead is on the do-not-contact list. Changing its status to{" "}
              {pendingStatus ? STATUS_LABELS[pendingStatus] : ""} removes the number from the suppression list and makes
              it callable again.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPendingStatus(null)}>
              Keep suppressed
            </Button>
            <Button
              variant="destructive"
              onClick={() => pendingStatus && update.mutate({ status: pendingStatus, confirm_reenable: true })}
            >
              Re-enable
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <WebsiteDialog lead={lead} open={editWebsite} onOpenChange={setEditWebsite} onSave={(url) => update.mutate({ website_url: url })} />
    </div>
  );
}

function WebsiteDialog({ lead, open, onOpenChange, onSave }: {
  lead: LeadDetail;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (url: string) => void;
}) {
  const [value, setValue] = useState(lead.website_url ?? "");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Website URL</DialogTitle>
          <DialogDescription>Saving a new URL re-runs the website audit.</DialogDescription>
        </DialogHeader>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            onSave(value.trim());
            onOpenChange(false);
          }}
          className="grid gap-3"
        >
          <Input value={value} onChange={(e) => setValue(e.target.value)} placeholder="https://example.bg" aria-label="Website URL" />
          <DialogFooter>
            <Button type="submit">Save</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
