import { CALL_OUTCOMES, OUTCOME_LABELS, STATUS_LABELS, type CallOutcome, type LeadDetail } from "@leadtracker/shared";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { CallButton } from "@/components/app/phone";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api, errorMessage } from "@/lib/api";
import { useInvalidateLeads } from "@/lib/queries";

const OUTCOME_STYLE: Partial<Record<CallOutcome, "default" | "outline" | "destructive">> = {
  INTERESTED: "default",
  DO_NOT_CONTACT: "destructive",
};

export function CallPanel({ lead }: { lead: LeadDetail }) {
  const invalidate = useInvalidateLeads();
  const [note, setNote] = useState("");
  const [callbackAt, setCallbackAt] = useState("");
  const [confirmDnc, setConfirmDnc] = useState(false);

  const record = useMutation({
    mutationFn: (outcome: CallOutcome) =>
      api.recordCall(lead.id, {
        outcome,
        note: note.trim() || null,
        callback_at: outcome === "CALLBACK" && callbackAt ? new Date(callbackAt).toISOString() : null,
      }),
    onSuccess: (result, outcome) => {
      toast.success(`${OUTCOME_LABELS[outcome]} recorded · status: ${STATUS_LABELS[result.status]}`);
      setNote("");
      setCallbackAt("");
      setConfirmDnc(false);
      invalidate(lead.id);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  if (lead.suppressed) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Call</CardTitle>
        </CardHeader>
        <CardContent className="text-[13px] text-muted-foreground">
          This number is on the do-not-contact list. It will not appear in calling sessions until someone explicitly
          re-enables it (change the status).
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Call</CardTitle>
        <CallButton
          phone={lead.normalized_phone}
          display={lead.international_phone}
          isDemo={lead.is_demo}
          invalid={lead.phone_invalid}
          suppressed={lead.suppressed}
          size="sm"
          label={lead.international_phone ?? "Call"}
        />
      </CardHeader>
      <CardContent className="grid gap-2">
        <Textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Notes from the call (saved with the outcome)"
          aria-label="Call notes"
          rows={2}
        />
        <div className="grid grid-cols-[auto_1fr] items-center gap-2">
          <Label htmlFor="callback-at">Callback at</Label>
          <Input
            id="callback-at"
            type="datetime-local"
            value={callbackAt}
            onChange={(e) => setCallbackAt(e.target.value)}
            className="h-7 text-xs"
          />
        </div>
        <div className="grid grid-cols-2 gap-1.5">
          {CALL_OUTCOMES.map((outcome) => (
            <Button
              key={outcome}
              size="sm"
              variant={OUTCOME_STYLE[outcome] ?? "outline"}
              disabled={record.isPending}
              onClick={() => (outcome === "DO_NOT_CONTACT" ? setConfirmDnc(true) : record.mutate(outcome))}
            >
              {OUTCOME_LABELS[outcome]}
            </Button>
          ))}
        </div>
        <p className="text-[11px] text-muted-foreground">
          Called {lead.call_count}× {lead.last_contacted_at ? `· last ${new Date(lead.last_contacted_at).toLocaleString("en-GB")}` : ""}
        </p>
      </CardContent>
      <Dialog open={confirmDnc} onOpenChange={setConfirmDnc}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Mark as do not contact?</DialogTitle>
            <DialogDescription>
              {lead.international_phone ?? "This number"} will be permanently excluded from calling sessions for every
              business that uses it, until explicitly re-enabled.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDnc(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={() => record.mutate("DO_NOT_CONTACT")} disabled={record.isPending}>
              Do not contact
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
