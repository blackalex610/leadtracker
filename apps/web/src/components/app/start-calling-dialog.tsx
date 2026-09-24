import { zodResolver } from "@hookform/resolvers/zod";
import { PRIORITIES, PRIORITY_LABELS, type CallingFilters } from "@leadtracker/shared";
import { useMutation, useQuery } from "@tanstack/react-query";
import { PhoneCallIcon } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { useNavigate } from "react-router";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { callingSchema, toCallingFilters, type CallingFormValues } from "@/features/calling/calling-schema";
import { api, errorMessage } from "@/lib/api";
import { useFacets, usePresets, useSettings } from "@/lib/queries";

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return debounced;
}

export function StartCallingDialog({ trigger, defaults }: { trigger?: ReactNode; defaults?: Partial<CallingFormValues> }) {
  const [open, setOpen] = useState(false);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {trigger ?? (
          <Button size="sm">
            <PhoneCallIcon /> Start calling session
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Start calling session</DialogTitle>
          <DialogDescription>
            One lead at a time, keyboard driven. Do-not-contact numbers are never included.
          </DialogDescription>
        </DialogHeader>
        {open && <CallingFormLoader defaults={defaults} onDone={() => setOpen(false)} />}
      </DialogContent>
    </Dialog>
  );
}

function CallingFormLoader(props: { defaults?: Partial<CallingFormValues>; onDone: () => void }) {
  const settings = useSettings();
  // Mount the form once settings are known so its defaults never overwrite user input later.
  if (!settings.data && !settings.error) return <p className="text-xs text-muted-foreground">Loading…</p>;
  return <CallingForm {...props} />;
}

function CallingForm({ defaults, onDone }: { defaults?: Partial<CallingFormValues>; onDone: () => void }) {
  const navigate = useNavigate();
  const settings = useSettings();
  const presets = usePresets();
  const facets = useFacets();
  const calling = settings.data?.runtime.calling;

  const form = useForm<CallingFormValues>({
    resolver: zodResolver(callingSchema),
    defaultValues: {
      niche_key: "any",
      city: "",
      window_start: calling?.window_start ?? "19:00",
      window_end: calling?.window_end ?? "21:00",
      open_today: true,
      priorities: ["HOT", "WARM"],
      website: "any",
      limit: calling?.default_session_limit ?? 50,
      include_unknown_hours: calling?.include_unknown_hours ?? true,
      ...defaults,
    },
  });
  const values = useWatch({ control: form.control }) as CallingFormValues;
  const parsed = callingSchema.safeParse(values);
  const debounced = useDebounced(parsed.success ? toCallingFilters(parsed.data) : null, 350);

  const preview = useQuery({
    queryKey: ["calling-preview", debounced],
    queryFn: () => api.callingPreview(debounced as Partial<CallingFilters>),
    enabled: debounced !== null,
  });

  const start = useMutation({
    mutationFn: (filters: Partial<CallingFilters>) => api.createCallingSession(filters),
    onSuccess: (session) => {
      onDone();
      navigate(`/calling/${session.id}`);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  // Picking a niche applies its calling window.
  const niche = useWatch({ control: form.control, name: "niche_key" });
  const appliedNiche = useRef<string | null>(null);
  useEffect(() => {
    // Apply a template's calling window once per selection (not on refetch).
    if (!presets.data || appliedNiche.current === niche) return;
    appliedNiche.current = niche;
    const preset = presets.data.find((p) => p.key === niche);
    if (preset?.calling_window_start && preset.calling_window_end) {
      form.setValue("window_start", preset.calling_window_start);
      form.setValue("window_end", preset.calling_window_end);
    }
  }, [niche, presets.data, form]);

  const errors = form.formState.errors;
  return (
    <form
      className="grid gap-3"
      onSubmit={form.handleSubmit((v) => start.mutate(toCallingFilters(v)))}
      noValidate
    >
      <div className="grid grid-cols-2 gap-3">
        <div className="grid gap-1">
          <Label htmlFor="calling-niche">Category</Label>
          <Controller
            control={form.control}
            name="niche_key"
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger id="calling-niche">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="any">Any category</SelectItem>
                  {presets.data?.map((p) => (
                    <SelectItem key={p.key} value={p.key}>
                      {p.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
        </div>
        <div className="grid gap-1">
          <Label htmlFor="calling-city">Location</Label>
          <Input id="calling-city" list="calling-cities" placeholder="Any city" {...form.register("city")} />
          <datalist id="calling-cities">
            {facets.data?.cities.map((c) => <option key={c.value} value={c.value} />)}
          </datalist>
        </div>
      </div>

      <div className="grid grid-cols-[1fr_1fr_auto] items-end gap-3">
        <div className="grid gap-1">
          <Label htmlFor="calling-start">Opening window</Label>
          <Input id="calling-start" aria-invalid={!!errors.window_start} {...form.register("window_start")} />
        </div>
        <div className="grid gap-1">
          <Label htmlFor="calling-end" className="sr-only">
            Window end
          </Label>
          <Input id="calling-end" aria-invalid={!!errors.window_end} {...form.register("window_end")} />
        </div>
        <label className="flex h-8 items-center gap-2 text-xs">
          <Controller
            control={form.control}
            name="open_today"
            render={({ field }) => <Switch checked={field.value} onCheckedChange={field.onChange} />}
          />
          Open today
        </label>
      </div>
      {(errors.window_start || errors.window_end) && (
        <p className="text-xs text-bad">Opening window must be HH:MM – HH:MM</p>
      )}

      <div className="grid gap-1">
        <Label>Priority</Label>
        <Controller
          control={form.control}
          name="priorities"
          render={({ field }) => (
            <div className="flex gap-4">
              {PRIORITIES.map((p) => (
                <label key={p} className="flex items-center gap-1.5 text-[13px]">
                  <Checkbox
                    checked={field.value.includes(p)}
                    onCheckedChange={(checked) =>
                      field.onChange(checked ? [...field.value, p] : field.value.filter((v) => v !== p))
                    }
                  />
                  {PRIORITY_LABELS[p]}
                </label>
              ))}
            </div>
          )}
        />
        {errors.priorities && <p className="text-xs text-bad">{errors.priorities.message}</p>}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="grid gap-1">
          <Label htmlFor="calling-website">Website</Label>
          <Controller
            control={form.control}
            name="website"
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger id="calling-website">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="any">Any</SelectItem>
                  <SelectItem value="none">No website</SelectItem>
                  <SelectItem value="poor">Poor website</SelectItem>
                </SelectContent>
              </Select>
            )}
          />
        </div>
        <div className="grid gap-1">
          <Label htmlFor="calling-limit">Limit</Label>
          <Input
            id="calling-limit"
            type="number"
            min={1}
            max={500}
            {...form.register("limit", { valueAsNumber: true })}
          />
        </div>
      </div>

      <label className="flex items-center gap-2 text-xs text-muted-foreground">
        <Controller
          control={form.control}
          name="include_unknown_hours"
          render={({ field }) => <Checkbox checked={field.value} onCheckedChange={(v) => field.onChange(v === true)} />}
        />
        Include leads without known opening hours (listed last)
      </label>

      <p className="text-xs text-muted-foreground" aria-live="polite">
        Phone required · suppressed and recently called numbers excluded ·{" "}
        {preview.isFetching ? "counting…" : preview.data ? (
          <span className="font-medium text-foreground">{preview.data.count} leads match</span>
        ) : (
          "—"
        )}
      </p>

      <DialogFooter>
        <Button type="submit" disabled={start.isPending || preview.data?.count === 0}>
          <PhoneCallIcon /> Start session
        </Button>
      </DialogFooter>
    </form>
  );
}
