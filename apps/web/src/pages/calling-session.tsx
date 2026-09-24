import { OUTCOME_LABELS, OUTCOME_SHORTCUTS, type CallOutcome, type CallingCard } from "@leadtracker/shared";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeftIcon, ArrowRightIcon, ExternalLinkIcon, MapIcon, PhoneIcon, XIcon } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { toast } from "sonner";

import { OpportunityTags, PriorityBadge, Rating } from "@/components/app/badges";
import { ErrorState, PageFallback } from "@/components/app/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { api, errorMessage } from "@/lib/api";
import { displayDomain, formatDateTime, mapsSearchUrl, telHref } from "@/lib/format";
import { keys, useCallingSession, useInvalidateLeads } from "@/lib/queries";
import { cn } from "@/lib/utils";

const OUTCOME_BUTTONS: { outcome: CallOutcome; variant: "default" | "outline" | "destructive" }[] = [
  { outcome: "NO_ANSWER", variant: "outline" },
  { outcome: "CALLBACK", variant: "outline" },
  { outcome: "INTERESTED", variant: "default" },
  { outcome: "NOT_INTERESTED", variant: "outline" },
  { outcome: "DO_NOT_CONTACT", variant: "destructive" },
];
const SECONDARY_OUTCOMES: CallOutcome[] = ["WRONG_NUMBER", "ALREADY_HAS_PROVIDER"];
const KEY_TO_OUTCOME = Object.fromEntries(
  Object.entries(OUTCOME_SHORTCUTS).map(([outcome, key]) => [key, outcome as CallOutcome]),
) as Record<string, CallOutcome>;

function isTyping(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  return !!el && (el.tagName === "TEXTAREA" || el.tagName === "INPUT" || el.tagName === "SELECT" || el.isContentEditable);
}

export default function CallingSessionPage() {
  const { id } = useParams();
  const sessionId = Number(id);
  const session = useCallingSession(sessionId);
  if (session.isPending) return <PageFallback />;
  if (session.error) {
    return (
      <div className="p-6">
        <Link to="/" className="text-xs text-muted-foreground hover:underline">
          ← Dashboard
        </Link>
        <ErrorState error={session.error} onRetry={() => void session.refetch()} />
      </div>
    );
  }
  return <CallingRunner sessionId={sessionId} cards={session.data.cards} initialPosition={session.data.position} endedAt={session.data.ended_at} />;
}

function CallingRunner({ sessionId, cards, initialPosition, endedAt }: {
  sessionId: number;
  cards: CallingCard[];
  initialPosition: number;
  endedAt: string | null;
}) {
  const navigate = useNavigate();
  const client = useQueryClient();
  const invalidate = useInvalidateLeads();
  const [index, setIndex] = useState(Math.min(initialPosition, Math.max(0, cards.length - 1)));
  const [recorded, setRecorded] = useState<Record<number, CallOutcome>>({});
  const [note, setNote] = useState("");
  const [callbackAt, setCallbackAt] = useState("");
  const [confirmDnc, setConfirmDnc] = useState(false);
  const [autoAdvance, setAutoAdvance] = useState(true);
  const noteRef = useRef<HTMLTextAreaElement>(null);

  const card = cards[index];
  const finished = index >= cards.length;
  const lead = card?.lead;

  const persistPosition = useMutation({ mutationFn: (position: number) => api.updateCallingSession(sessionId, position) });
  const goTo = useCallback(
    (next: number) => {
      const clamped = Math.max(0, Math.min(cards.length, next));
      setIndex(clamped);
      setNote("");
      setCallbackAt("");
      setConfirmDnc(false);
      persistPosition.mutate(clamped);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [cards.length, sessionId],
  );

  const record = useMutation({
    mutationFn: ({ leadId, outcome }: { leadId: number; outcome: CallOutcome }) =>
      api.recordCall(leadId, {
        outcome,
        session_id: sessionId,
        note: note.trim() || null,
        callback_at: outcome === "CALLBACK" && callbackAt ? new Date(callbackAt).toISOString() : null,
      }),
    onSuccess: (_result, { leadId, outcome }) => {
      setRecorded((r) => ({ ...r, [leadId]: outcome }));
      toast.success(`${OUTCOME_LABELS[outcome]} · ${lead?.name ?? ""}`, { duration: 1500 });
      invalidate(leadId);
      void client.invalidateQueries({ queryKey: keys.callingSession(sessionId) });
      if (autoAdvance) goTo(index + 1);
      else {
        setNote("");
        setConfirmDnc(false);
      }
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const submitOutcome = useCallback(
    (outcome: CallOutcome) => {
      if (!card || !lead || record.isPending) return;
      if (!card.callable) {
        toast.error(card.not_callable_reason ?? "This lead cannot be called");
        return;
      }
      if (outcome === "DO_NOT_CONTACT" && !confirmDnc) {
        setConfirmDnc(true);
        return;
      }
      record.mutate({ leadId: lead.id, outcome });
    },
    [card, lead, record, confirmDnc],
  );

  const dial = useCallback(() => {
    if (!card || !lead) return;
    if (!card.callable) {
      toast.error(card.not_callable_reason ?? "Cannot call");
      return;
    }
    if (lead.is_demo) {
      toast("Demo record — dialing disabled");
      return;
    }
    const href = telHref(lead.normalized_phone);
    if (href) window.location.href = href;
  }, [card, lead]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (isTyping(e.target)) {
        if (e.key === "Escape") (e.target as HTMLElement).blur();
        return;
      }
      const key = e.key.toLowerCase();
      if (key === "arrowright") {
        e.preventDefault();
        goTo(index + 1);
      } else if (key === "arrowleft") {
        e.preventDefault();
        goTo(index - 1);
      } else if (key === "c") {
        e.preventDefault();
        dial();
      } else if (key === "/") {
        e.preventDefault();
        noteRef.current?.focus();
      } else if (key === "escape") {
        setConfirmDnc(false);
      } else if (key === "enter" && confirmDnc) {
        e.preventDefault();
        submitOutcome("DO_NOT_CONTACT");
      } else if (KEY_TO_OUTCOME[key]) {
        e.preventDefault();
        submitOutcome(KEY_TO_OUTCOME[key]);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [index, goTo, dial, submitOutcome, confirmDnc]);

  const stats = useMemo(() => {
    const values = Object.values(recorded);
    return {
      calls: values.length,
      interested: values.filter((o) => o === "INTERESTED").length,
      callbacks: values.filter((o) => o === "CALLBACK").length,
    };
  }, [recorded]);

  const end = useMutation({
    mutationFn: () => api.endCallingSession(sessionId),
    onSuccess: () => navigate("/campaigns?tab=calling"),
  });

  return (
    <div className="flex h-dvh flex-col bg-background">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-2">
        <div className="flex items-center gap-3">
          <Link to="/" className="text-xs text-muted-foreground hover:text-foreground" aria-label="Exit calling mode">
            <XIcon className="size-4" />
          </Link>
          <span className="text-[13px] font-semibold">Calling session</span>
          <span className="text-xs text-muted-foreground tabular">
            {Math.min(index + 1, cards.length)} / {cards.length}
          </span>
          <Progress value={(Math.min(index, cards.length) / Math.max(1, cards.length)) * 100} className="w-40" />
        </div>
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <span className="tabular">
            <b className="text-foreground">{stats.calls}</b> calls · <b className="text-foreground">{stats.interested}</b> interested ·{" "}
            <b className="text-foreground">{stats.callbacks}</b> callbacks
          </span>
          <label className="flex items-center gap-1.5">
            <Switch checked={autoAdvance} onCheckedChange={setAutoAdvance} /> Auto-advance
          </label>
          <Button size="xs" variant="outline" onClick={() => end.mutate()} disabled={!!endedAt}>
            {endedAt ? "Ended" : "End session"}
          </Button>
        </div>
      </header>

      {finished || !card || !lead ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 text-center">
          <p className="text-lg font-semibold">Session complete</p>
          <p className="text-sm text-muted-foreground">
            {stats.calls} calls logged · {stats.interested} interested · {stats.callbacks} callbacks
          </p>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => goTo(cards.length - 1)}>
              <ArrowLeftIcon /> Back to last lead
            </Button>
            <Button onClick={() => end.mutate()}>Finish</Button>
          </div>
        </div>
      ) : (
        <main className="mx-auto grid w-full max-w-5xl flex-1 gap-6 overflow-y-auto px-6 py-6 lg:grid-cols-[3fr_2fr]">
          <section className="flex min-w-0 flex-col gap-5" aria-live="polite">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <PriorityBadge priority={lead.priority} />
                {recorded[lead.id] && <Badge variant="good">Recorded: {OUTCOME_LABELS[recorded[lead.id]!]}</Badge>}
                {!card.callable && <Badge variant="hot">{card.not_callable_reason}</Badge>}
                {lead.is_demo && <Badge variant="muted">DEMO</Badge>}
              </div>
              <h1 className="mt-2 text-3xl font-bold tracking-tight">{lead.name}</h1>
              <p className="mt-1 text-sm text-muted-foreground">
                {[lead.category, lead.neighborhood, lead.city].filter(Boolean).join(" · ")} ·{" "}
                <Rating rating={lead.rating} reviews={lead.review_count} />
              </p>
            </div>

            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Phone</p>
              <a
                href={card.callable && !lead.is_demo ? telHref(lead.normalized_phone) : undefined}
                className={cn("text-3xl font-semibold tabular", card.callable && !lead.is_demo && "hover:underline")}
              >
                {lead.international_phone ?? lead.normalized_phone}
              </a>
              <p className="mt-1 text-xs text-muted-foreground">
                {card.hours_today ?? "Hours not listed"}
                {card.open_in_window_today !== null && (
                  <span className={cn("ml-2", card.open_in_window_today ? "text-good" : "text-bad")}>
                    {card.open_in_window_today ? "open in calling window" : "closed in calling window"}
                  </span>
                )}
              </p>
            </div>

            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Why we're calling</p>
              <OpportunityTags types={lead.opportunity_types} max={6} className="mt-1.5 [&_[data-slot=badge]]:text-xs" />
              <ul className="mt-2 grid gap-1 text-[15px]">
                {card.reasons.map((r, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="text-muted-foreground tabular">{i + 1}.</span>
                    {r.text}
                  </li>
                ))}
              </ul>
              {card.website_summary && <p className="mt-2 text-xs text-muted-foreground">Website: {card.website_summary}</p>}
            </div>

            {card.pitch && (
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Opener</p>
                <blockquote className="mt-1 border-l-2 pl-3 text-[14px] leading-relaxed">{card.pitch.text}</blockquote>
              </div>
            )}

            {card.last_call_outcome && (
              <p className="text-xs text-muted-foreground">
                Last call: {OUTCOME_LABELS[card.last_call_outcome as CallOutcome] ?? card.last_call_outcome} ·{" "}
                {formatDateTime(card.last_call_at)}
                {card.last_note && ` — “${card.last_note}”`}
              </p>
            )}

            <div className="flex flex-wrap gap-2 text-xs">
              <Link to={`/leads/${lead.id}`} target="_blank" className="inline-flex items-center gap-1 text-muted-foreground hover:underline">
                Full lead <ExternalLinkIcon className="size-3" />
              </Link>
              <a
                href={lead.google_maps_url ?? mapsSearchUrl(lead.name, lead.address)}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-muted-foreground hover:underline"
              >
                <MapIcon className="size-3" /> Google Maps
              </a>
              {lead.website_url && (
                <a href={lead.website_url} target="_blank" rel="noopener noreferrer nofollow" className="inline-flex items-center gap-1 text-muted-foreground hover:underline">
                  <ExternalLinkIcon className="size-3" /> {displayDomain(lead.website_url)}
                </a>
              )}
            </div>
          </section>

          <aside className="flex flex-col gap-3">
            <Button size="lg" className="h-14 text-base" onClick={dial} disabled={!card.callable}>
              <PhoneIcon className="size-5" /> Call <kbd className="ml-2">C</kbd>
            </Button>
            {confirmDnc && (
              <div role="alert" className="rounded-md border border-bad/40 bg-hot-soft px-3 py-2 text-xs">
                Press <kbd>D</kbd> or <kbd>Enter</kbd> again to permanently mark this number do-not-contact. <kbd>Esc</kbd> cancels.
              </div>
            )}
            <div className="grid grid-cols-2 gap-2">
              {OUTCOME_BUTTONS.map(({ outcome, variant }) => (
                <Button
                  key={outcome}
                  variant={variant}
                  className={cn("h-11 justify-between", outcome === "DO_NOT_CONTACT" && "col-span-2")}
                  disabled={!card.callable || record.isPending}
                  onClick={() => submitOutcome(outcome)}
                >
                  {OUTCOME_LABELS[outcome]}
                  <kbd>{OUTCOME_SHORTCUTS[outcome]?.toUpperCase()}</kbd>
                </Button>
              ))}
            </div>
            <div className="flex gap-2">
              {SECONDARY_OUTCOMES.map((outcome) => (
                <Button key={outcome} size="sm" variant="ghost" className="flex-1" disabled={!card.callable || record.isPending}
                  onClick={() => submitOutcome(outcome)}>
                  {OUTCOME_LABELS[outcome]}
                </Button>
              ))}
            </div>
            <Textarea
              ref={noteRef}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Notes (press / to focus, Esc to leave) — saved with the outcome"
              rows={3}
              aria-label="Call notes"
            />
            <label className="grid grid-cols-[auto_1fr] items-center gap-2 text-xs text-muted-foreground">
              Callback at
              <Input type="datetime-local" value={callbackAt} onChange={(e) => setCallbackAt(e.target.value)} className="h-7 text-xs" />
            </label>
            <div className="mt-auto flex items-center justify-between">
              <Button variant="outline" onClick={() => goTo(index - 1)} disabled={index === 0}>
                <ArrowLeftIcon /> Prev
              </Button>
              <span className="text-[11px] text-muted-foreground">
                <kbd>←</kbd> <kbd>→</kbd> navigate
              </span>
              <Button variant="outline" onClick={() => goTo(index + 1)}>
                Next <ArrowRightIcon />
              </Button>
            </div>
          </aside>
        </main>
      )}
    </div>
  );
}
