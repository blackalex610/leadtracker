import { OUTCOME_LABELS, STATUS_LABELS, type LeadDetail, type LeadStatus } from "@leadtracker/shared";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { api, errorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useInvalidateLeads } from "@/lib/queries";

export function NotesCard({ lead }: { lead: LeadDetail }) {
  const invalidate = useInvalidateLeads();
  const [body, setBody] = useState("");
  const add = useMutation({
    mutationFn: () => api.addNote(lead.id, body.trim()),
    onSuccess: () => {
      setBody("");
      invalidate(lead.id);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle>Notes</CardTitle>
        <span className="text-xs text-muted-foreground">{lead.notes.length}</span>
      </CardHeader>
      <CardContent className="grid gap-2">
        <form
          className="grid gap-1.5"
          onSubmit={(e) => {
            e.preventDefault();
            if (body.trim()) add.mutate();
          }}
        >
          <Textarea value={body} onChange={(e) => setBody(e.target.value)} placeholder="Add a note" rows={2} aria-label="New note" />
          <Button size="xs" type="submit" disabled={!body.trim() || add.isPending} className="justify-self-end">
            Add note
          </Button>
        </form>
        <ul className="grid gap-2">
          {lead.notes.map((n) => (
            <li key={n.id} className="border-l-2 pl-2 text-[13px]">
              <p className="whitespace-pre-wrap">{n.body}</p>
              <p className="text-[11px] text-muted-foreground">
                {n.user_name ?? "—"} · {formatDateTime(n.created_at)}
              </p>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function describeEvent(type: string, data: Record<string, unknown>): string {
  switch (type) {
    case "created":
      return `Discovered via ${String(data.provider ?? "search")}`;
    case "call": {
      const outcome = OUTCOME_LABELS[data.outcome as keyof typeof OUTCOME_LABELS] ?? String(data.outcome);
      const to = STATUS_LABELS[data.to as LeadStatus] ?? String(data.to);
      return `Call: ${outcome} → ${to}`;
    }
    case "website_audit":
      return data.status === "success"
        ? `Website audited · health ${String(data.health)} · outdated ${String(data.outdated)}`
        : `Website audit ${String(data.status)} (${String(data.error)})`;
    case "suppressed":
      return "Added to do-not-contact list";
    case "unsuppressed":
      return "Re-enabled for contact";
    case "refreshed":
      return "Refreshed from provider";
    case "updated": {
      const status = data.status as { from?: string; to?: string } | undefined;
      if (status?.to) return `Status: ${STATUS_LABELS[status.from as LeadStatus] ?? status.from} → ${STATUS_LABELS[status.to as LeadStatus] ?? status.to}`;
      return `Updated ${Object.keys(data).join(", ")}`;
    }
    default:
      return type;
  }
}

export function ActivityCard({ lead }: { lead: LeadDetail }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Activity</CardTitle>
      </CardHeader>
      <CardContent>
        {lead.events.length ? (
          <ol className="grid gap-1.5">
            {lead.events.map((e) => (
              <li key={e.id} className="grid grid-cols-[6.5rem_1fr] gap-2 text-xs">
                <span className="text-muted-foreground tabular">{formatDateTime(e.created_at)}</span>
                <span>{describeEvent(e.type, e.data)}</span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-xs text-muted-foreground">No activity yet.</p>
        )}
      </CardContent>
    </Card>
  );
}
