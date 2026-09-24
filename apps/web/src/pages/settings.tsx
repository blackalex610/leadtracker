import { zodResolver } from "@hookform/resolvers/zod";
import type { RuleKey, RuntimeSettings, SettingsOut } from "@leadtracker/shared";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2Icon, KeyRoundIcon, RefreshCwIcon, ShieldOffIcon, XCircleIcon } from "lucide-react";
import { useState, type ReactNode } from "react";
import {
  Controller,
  useForm,
  type FieldValues,
  type Path,
  type UseFormReturn,
} from "react-hook-form";
import { useSearchParams } from "react-router";
import { toast } from "sonner";
import { z } from "zod";

import { ErrorState, PageFallback, PageHeader } from "@/components/app/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, errorMessage, type SettingsPatch } from "@/lib/api";
import { formatDateTime, formatMoney, formatNumber } from "@/lib/format";
import { keys, useMeta, useSettings, useUpdateSettings, useUsage, useUsers } from "@/lib/queries";

const TABS = [
  ["general", "General"],
  ["provider", "Provider"],
  ["scoring", "Scoring"],
  ["audit", "Website audit"],
  ["search", "Search & cache"],
  ["csv", "CSV"],
  ["pricing", "Pricing & usage"],
  ["suppression", "Do not contact"],
  ["users", "Users"],
] as const;

export default function SettingsPage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "general";
  const settings = useSettings();
  return (
    <div className="flex flex-col">
      <PageHeader title="Settings" description="Runtime preferences are stored in the database; secrets only in backend environment variables" />
      {settings.error ? (
        <ErrorState error={settings.error} onRetry={() => void settings.refetch()} />
      ) : !settings.data ? (
        <PageFallback />
      ) : (
        <Tabs value={tab} onValueChange={(t) => setParams({ tab: t }, { replace: true })} className="px-5 pt-3 pb-8">
          <TabsList className="flex-wrap">
            {TABS.map(([value, label]) => (
              <TabsTrigger key={value} value={value}>
                {label}
              </TabsTrigger>
            ))}
          </TabsList>
          <TabsContent value="general"><GeneralTab data={settings.data} /></TabsContent>
          <TabsContent value="provider"><ProviderTab data={settings.data} /></TabsContent>
          <TabsContent value="scoring"><ScoringTab data={settings.data} /></TabsContent>
          <TabsContent value="audit"><AuditTab data={settings.data} /></TabsContent>
          <TabsContent value="search"><SearchTab data={settings.data} /></TabsContent>
          <TabsContent value="csv"><CsvTab data={settings.data} /></TabsContent>
          <TabsContent value="pricing"><PricingTab data={settings.data} /></TabsContent>
          <TabsContent value="suppression"><SuppressionTab /></TabsContent>
          <TabsContent value="users"><UsersTab data={settings.data} /></TabsContent>
        </Tabs>
      )}
    </div>
  );
}

// --- form helpers --------------------------------------------------------------------------------

function Field({ label, hint, children, htmlFor }: { label: string; hint?: ReactNode; children: ReactNode; htmlFor?: string }) {
  return (
    <div className="grid gap-1">
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
      {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  );
}

function NumberInput<T extends FieldValues>({ form, name, label, hint, step = 1 }: {
  form: UseFormReturn<T>;
  name: Path<T>;
  label: string;
  hint?: ReactNode;
  step?: number;
}) {
  const error = form.formState.errors[name];
  return (
    <Field label={label} hint={error ? <span className="text-bad">{String(error.message)}</span> : hint} htmlFor={name}>
      <Input id={name} type="number" step={step} aria-invalid={!!error} {...form.register(name, { valueAsNumber: true })} />
    </Field>
  );
}

function TextInput<T extends FieldValues>({ form, name, label, hint }: {
  form: UseFormReturn<T>;
  name: Path<T>;
  label: string;
  hint?: ReactNode;
}) {
  const error = form.formState.errors[name];
  return (
    <Field label={label} hint={error ? <span className="text-bad">{String(error.message)}</span> : hint} htmlFor={name}>
      <Input id={name} aria-invalid={!!error} {...form.register(name)} />
    </Field>
  );
}

function SwitchInput<T extends FieldValues>({ form, name, label, hint }: {
  form: UseFormReturn<T>;
  name: Path<T>;
  label: string;
  hint?: ReactNode;
}) {
  return (
    <div className="grid gap-1">
      <label className="flex items-center gap-2 text-[13px]">
        <Controller control={form.control} name={name}
          render={({ field }) => <Switch checked={!!field.value} onCheckedChange={field.onChange} />} />
        {label}
      </label>
      {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  );
}

function useGroupSave<K extends keyof RuntimeSettings>(group: K) {
  const update = useUpdateSettings();
  return {
    pending: update.isPending,
    save: (values: Record<string, unknown>, onSaved?: () => void) =>
      update.mutate({ [group]: values } as SettingsPatch, {
        onSuccess: () => {
          toast.success("Settings saved");
          onSaved?.();
        },
        onError: (e) => toast.error(errorMessage(e)),
      }),
  };
}

function SaveBar({ pending, dirty, extra }: { pending: boolean; dirty: boolean; extra?: ReactNode }) {
  return (
    <div className="flex items-center gap-2 border-t pt-3">
      <Button type="submit" size="sm" disabled={pending || !dirty}>
        {pending ? "Saving…" : "Save"}
      </Button>
      {extra}
    </div>
  );
}

const hhmm = z.string().regex(/^([01]?\d|2[0-3]):[0-5]\d$/, "Use HH:MM");
const int = (min: number, max: number) => z.number({ message: "Enter a number" }).int().min(min).max(max);

// --- tabs --------------------------------------------------------------------------------------------

const generalSchema = z.object({
  default_country: z.string().length(2, "2-letter country code"),
  default_city: z.string().min(1).max(120),
  timezone: z.string().min(1),
  provider_language: z.string().min(2).max(10),
  pitch_language: z.enum(["en", "bg"]),
  window_start: hhmm,
  window_end: hhmm,
  recall_cooldown_hours: int(0, 720),
  default_session_limit: int(1, 500),
  include_unknown_hours: z.boolean(),
});

function GeneralTab({ data }: { data: SettingsOut }) {
  const { general, calling } = data.runtime;
  const update = useUpdateSettings();
  const form = useForm<z.infer<typeof generalSchema>>({
    resolver: zodResolver(generalSchema),
    defaultValues: {
      default_country: general.default_country,
      default_city: general.default_city,
      timezone: general.timezone,
      provider_language: general.provider_language,
      pitch_language: general.pitch_language,
      window_start: calling.window_start,
      window_end: calling.window_end,
      recall_cooldown_hours: calling.recall_cooldown_hours,
      default_session_limit: calling.default_session_limit,
      include_unknown_hours: calling.include_unknown_hours,
    },
  });
  const submit = form.handleSubmit((v) =>
    update.mutate(
      {
        general: {
          default_country: v.default_country.toUpperCase(),
          default_city: v.default_city,
          timezone: v.timezone,
          provider_language: v.provider_language,
          pitch_language: v.pitch_language,
        },
        calling: {
          window_start: v.window_start,
          window_end: v.window_end,
          recall_cooldown_hours: v.recall_cooldown_hours,
          default_session_limit: v.default_session_limit,
          include_unknown_hours: v.include_unknown_hours,
        },
      },
      {
        onSuccess: () => {
          toast.success("Settings saved — rescore leads to apply a new calling window to scores");
          form.reset(v);
        },
        onError: (e) => toast.error(errorMessage(e)),
      },
    ),
  );
  return (
    <form onSubmit={submit} className="grid max-w-3xl gap-4" noValidate>
      <Card>
        <CardHeader><CardTitle>Region</CardTitle></CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-3">
          <TextInput form={form} name="default_country" label="Default country" hint="Phone parsing and search region (e.g. BG)" />
          <TextInput form={form} name="default_city" label="Default city" />
          <TextInput form={form} name="timezone" label="Timezone" hint="IANA name, e.g. Europe/Sofia" />
          <TextInput form={form} name="provider_language" label="Provider language" hint="Language of names/addresses (bg, en)" />
          <Field label="Pitch language" htmlFor="pitch_language">
            <Controller control={form.control} name="pitch_language"
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger id="pitch_language"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="en">English</SelectItem>
                    <SelectItem value="bg">Bulgarian</SelectItem>
                  </SelectContent>
                </Select>
              )} />
          </Field>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Calling hours</CardTitle></CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-3">
          <TextInput form={form} name="window_start" label="Window start" />
          <TextInput form={form} name="window_end" label="Window end" />
          <NumberInput form={form} name="recall_cooldown_hours" label="Re-call cooldown (hours)" hint="Called leads are hidden from sessions for this long" />
          <NumberInput form={form} name="default_session_limit" label="Default session size" />
          <div className="sm:col-span-2">
            <SwitchInput form={form} name="include_unknown_hours" label="Include leads with unknown opening hours in sessions" />
          </div>
        </CardContent>
      </Card>
      <SaveBar pending={update.isPending} dirty={form.formState.isDirty} />
    </form>
  );
}

function ProviderTab({ data }: { data: SettingsOut }) {
  const env = data.environment;
  const meta = useMeta();
  const configured = env.provider.configured;
  return (
    <div className="grid max-w-3xl gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Business data provider</CardTitle>
          {env.demo_mode ? (
            <Badge variant="warm">Demo mode</Badge>
          ) : configured ? (
            <Badge variant="good"><CheckCircle2Icon /> Configured</Badge>
          ) : (
            <Badge variant="hot"><XCircleIcon /> Provider not configured</Badge>
          )}
        </CardHeader>
        <CardContent className="grid gap-3 text-[13px]">
          <dl className="grid grid-cols-[10rem_1fr] gap-y-1">
            <dt className="text-muted-foreground">Provider</dt>
            <dd>Google Places API (New) — places.googleapis.com/v1</dd>
            <dt className="text-muted-foreground">API key</dt>
            <dd className="flex items-center gap-1.5">
              <KeyRoundIcon className="size-3.5 text-muted-foreground" />
              {env.provider_api_key_set ? "Set via PROVIDER_API_KEY (hidden)" : "Not set"}
            </dd>
            <dt className="text-muted-foreground">Field tier</dt>
            <dd>
              {env.places_field_tier}{" "}
              <span className="text-muted-foreground">
                {env.places_field_tier === "enterprise"
                  ? "(phone, website, rating, reviews, hours — returned by Text Search itself)"
                  : "(also requests the editorial description — more expensive)"}
              </span>
            </dd>
            <dt className="text-muted-foreground">PageSpeed Insights</dt>
            <dd>{meta.data?.pagespeed_configured ? "PAGESPEED_API_KEY set" : "Not configured (optional)"}</dd>
            <dt className="text-muted-foreground">Lat/lng retention</dt>
            <dd>{env.google_latlng_retention_days} days (Google Maps Platform terms)</dd>
          </dl>
          <div className="rounded-md bg-muted/50 p-3 text-xs leading-relaxed">
            <p className="font-medium text-foreground">Setup</p>
            <ol className="mt-1 list-decimal space-y-0.5 pl-4 text-muted-foreground">
              <li>In Google Cloud, enable <b>Places API (New)</b> and billing for your project.</li>
              <li>Create an API key restricted to the Places API (New) (and to your server IP if possible).</li>
              <li>Set <code>PROVIDER_API_KEY</code> in the backend environment and restart the API/worker.</li>
            </ol>
            <p className="mt-2">
              Keys are never sent to or stored in the browser, and are redacted from logs. Without a key, searches return
              “Provider not configured” — no fake data. <code>DEMO_MODE=true</code> enables clearly synthetic test data.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

const RULE_ORDER: RuleKey[] = [
  "no_website", "website_broken", "low_health", "no_booking", "no_contact_cta", "mobile_problem", "weak_conversion",
  "outdated_website", "slow_website", "incomplete_google", "missing_business_info", "low_reviews",
  "discovery_category", "open_in_calling_window", "phone_available",
];

function ScoringTab({ data }: { data: SettingsOut }) {
  const meta = useMeta();
  const client = useQueryClient();
  const scoring = data.runtime.scoring;
  const { save, pending } = useGroupSave("scoring");
  const [justSaved, setJustSaved] = useState(false);
  const form = useForm({
    defaultValues: {
      rules: Object.fromEntries(RULE_ORDER.map((k) => [k, { points: scoring.rules?.[k]?.points ?? 0, enabled: scoring.rules?.[k]?.enabled ?? true }])),
      hot_min_score: scoring.hot_min_score ?? 50,
      warm_min_score: scoring.warm_min_score ?? 25,
      hot_requires_phone: scoring.hot_requires_phone ?? true,
      hot_requires_strong_category: scoring.hot_requires_strong_category ?? true,
      hot_requires_major_opportunity: scoring.hot_requires_major_opportunity ?? true,
      warm_requires_phone: scoring.warm_requires_phone ?? true,
      low_health_threshold: scoring.low_health_threshold ?? 40,
      outdated_threshold: scoring.outdated_threshold ?? 50,
      low_review_threshold: scoring.low_review_threshold ?? 20,
      weak_conversion_min_missing: scoring.weak_conversion_min_missing ?? 3,
      few_photos_threshold: scoring.few_photos_threshold ?? 3,
      strong_types: (scoring.strong_types ?? []).join(", "),
      booking_types: (scoring.booking_types ?? []).join(", "),
    },
  });
  const rescore = useMutation({
    mutationFn: api.rescoreAll,
    onSuccess: () => {
      toast.success("Rescoring all leads in the background");
      setJustSaved(false);
      void client.invalidateQueries({ queryKey: keys.leadsAll });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const submit = form.handleSubmit((v) => {
    const list = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
    save(
      {
        ...v,
        rules: Object.fromEntries(Object.entries(v.rules).map(([k, r]) => [k, { points: Number(r.points), enabled: r.enabled }])),
        strong_types: list(v.strong_types),
        booking_types: list(v.booking_types),
      },
      () => {
        form.reset(v);
        setJustSaved(true);
      },
    );
  });
  const ruleMeta = meta.data?.rule_meta ?? {};
  return (
    <form onSubmit={submit} className="grid max-w-4xl gap-4" noValidate>
      <Card>
        <CardHeader>
          <CardTitle>Opportunity rules</CardTitle>
          <span className="text-xs text-muted-foreground">Deterministic — score = sum of fired rules, capped at 100</span>
        </CardHeader>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Rule</TableHead>
              <TableHead>Tier</TableHead>
              <TableHead>Tag</TableHead>
              <TableHead className="w-24">Points</TableHead>
              <TableHead className="w-16">On</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {RULE_ORDER.map((key) => {
              const m = ruleMeta[key] as { label?: string; tier?: string; opportunity?: string | null; description?: string } | undefined;
              return (
                <TableRow key={key}>
                  <TableCell>
                    <p className="font-medium">{m?.label ?? key}</p>
                    <p className="text-[11px] text-muted-foreground">{m?.description}</p>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">{m?.tier?.replace("_", " ")}</TableCell>
                  <TableCell className="font-mono text-[10px]">{m?.opportunity ?? "—"}</TableCell>
                  <TableCell>
                    <Input type="number" min={0} max={100} className="h-7 w-20" aria-label={`${m?.label ?? key} points`}
                      {...form.register(`rules.${key}.points` as const, { valueAsNumber: true, min: 0, max: 100 })} />
                  </TableCell>
                  <TableCell>
                    <Controller control={form.control} name={`rules.${key}.enabled` as const}
                      render={({ field }) => <Switch checked={!!field.value} onCheckedChange={field.onChange} aria-label={`${key} enabled`} />} />
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </Card>
      <Card>
        <CardHeader><CardTitle>Priority</CardTitle></CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2">
          <NumberInput form={form} name="hot_min_score" label="HOT minimum score" />
          <NumberInput form={form} name="warm_min_score" label="WARM minimum score" />
          <SwitchInput form={form} name="hot_requires_phone" label="HOT requires a phone number" />
          <SwitchInput form={form} name="hot_requires_strong_category" label="HOT requires a discovery-dependent category" />
          <SwitchInput form={form} name="hot_requires_major_opportunity" label="HOT requires a major issue (no/broken website, low health, no booking)" />
          <SwitchInput form={form} name="warm_requires_phone" label="WARM requires a phone number" />
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Thresholds</CardTitle></CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-3">
          <NumberInput form={form} name="low_health_threshold" label="Low Website Health below" />
          <NumberInput form={form} name="outdated_threshold" label="Outdated index at or above" />
          <NumberInput form={form} name="low_review_threshold" label="Low review count below" />
          <NumberInput form={form} name="weak_conversion_min_missing" label="Weak conversion: missing elements" />
          <NumberInput form={form} name="few_photos_threshold" label="Few photos below" />
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Category knowledge</CardTitle></CardHeader>
        <CardContent className="grid gap-3">
          <TextInput form={form} name="strong_types" label="Discovery-dependent Google types" hint="Used when a lead has no niche template" />
          <TextInput form={form} name="booking_types" label="Booking-oriented Google types" />
        </CardContent>
      </Card>
      <SaveBar
        pending={pending}
        dirty={form.formState.isDirty}
        extra={
          <Button type="button" size="sm" variant={justSaved ? "default" : "outline"} onClick={() => rescore.mutate()} disabled={rescore.isPending}>
            <RefreshCwIcon /> Rescore all leads
          </Button>
        }
      />
    </form>
  );
}

const auditSchema = z.object({
  timeout_ms: int(1000, 60000),
  max_pages: int(1, 10),
  max_concurrent: int(1, 20),
  respect_robots: z.boolean(),
  max_response_kb: int(64, 10240),
  slow_threshold_ms: int(100, 60000),
  very_slow_threshold_ms: int(200, 60000),
  cache_days: int(0, 365),
  check_assets: z.boolean(),
  max_asset_checks: int(0, 20),
  pagespeed_enabled: z.boolean(),
});

function AuditTab({ data }: { data: SettingsOut }) {
  const { save, pending } = useGroupSave("audit");
  const form = useForm<z.infer<typeof auditSchema>>({ resolver: zodResolver(auditSchema), defaultValues: data.runtime.audit });
  return (
    <form onSubmit={form.handleSubmit((v) => save(v, () => form.reset(v)))} className="grid max-w-3xl gap-4" noValidate>
      <Card>
        <CardHeader><CardTitle>Limits</CardTitle></CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-3">
          <NumberInput form={form} name="timeout_ms" label="Request timeout (ms)" />
          <NumberInput form={form} name="max_pages" label="Max pages per site" hint="Homepage + relevant pages" />
          <NumberInput form={form} name="max_concurrent" label="Concurrent audits" />
          <NumberInput form={form} name="max_response_kb" label="Max response size (KB)" />
          <NumberInput form={form} name="slow_threshold_ms" label="Slow threshold (ms)" />
          <NumberInput form={form} name="very_slow_threshold_ms" label="Very slow threshold (ms)" />
          <NumberInput form={form} name="cache_days" label="Re-audit after (days)" />
          <NumberInput form={form} name="max_asset_checks" label="Images/links checked" />
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Behaviour</CardTitle></CardHeader>
        <CardContent className="grid gap-3">
          <SwitchInput form={form} name="respect_robots" label="Respect robots.txt" hint="Recommended. Disallowed sites are skipped, not flagged." />
          <SwitchInput form={form} name="check_assets" label="Check images and internal links for breakage" />
          <SwitchInput form={form} name="pagespeed_enabled" label="Run Google PageSpeed Insights (mobile)" hint="Requires PAGESPEED_API_KEY; adds ~10–30s per site." />
          <p className="text-[11px] text-muted-foreground">
            Audits never reach private/internal addresses (SSRF protection), follow at most 5 redirects and stop reading
            after the size limit.
          </p>
        </CardContent>
      </Card>
      <SaveBar pending={pending} dirty={form.formState.isDirty} />
    </form>
  );
}

const searchSettingsSchema = z.object({
  default_max_results: int(1, 1000),
  max_results_limit: int(1, 2000),
  provider_concurrency: int(1, 10),
  provider_requests_per_second: z.number().gt(0).max(50),
  cache_ttl_hours: int(0, 720),
  audit_after_search: z.boolean(),
});

function SearchTab({ data }: { data: SettingsOut }) {
  const { save, pending } = useGroupSave("search");
  const form = useForm<z.infer<typeof searchSettingsSchema>>({ resolver: zodResolver(searchSettingsSchema), defaultValues: data.runtime.search });
  return (
    <form onSubmit={form.handleSubmit((v) => save(v, () => form.reset(v)))} className="grid max-w-3xl gap-4" noValidate>
      <Card>
        <CardHeader><CardTitle>Search jobs</CardTitle></CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-3">
          <NumberInput form={form} name="default_max_results" label="Default max results" />
          <NumberInput form={form} name="max_results_limit" label="Max results limit" hint="Hard cap per search (cost control)" />
          <NumberInput form={form} name="provider_requests_per_second" label="Provider requests / second" step={0.5} />
          <NumberInput form={form} name="provider_concurrency" label="Provider concurrency" />
          <NumberInput form={form} name="cache_ttl_hours" label="Result cache (hours)" hint="Identical searches within this window cost nothing" />
          <div className="sm:col-span-3">
            <SwitchInput form={form} name="audit_after_search" label="Audit websites automatically after each search" />
          </div>
        </CardContent>
      </Card>
      <SaveBar pending={pending} dirty={form.formState.isDirty} />
    </form>
  );
}

function CsvTab({ data }: { data: SettingsOut }) {
  const { save, pending } = useGroupSave("csv");
  const form = useForm({ defaultValues: data.runtime.csv });
  return (
    <form onSubmit={form.handleSubmit((v) => save(v, () => form.reset(v)))} className="grid max-w-xl gap-4">
      <Card>
        <CardHeader><CardTitle>CSV export</CardTitle></CardHeader>
        <CardContent className="grid gap-3">
          <Field label="Delimiter" htmlFor="delimiter" hint="Bulgarian Excel usually expects semicolons">
            <Controller control={form.control} name="delimiter"
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger id="delimiter"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value=",">Comma (,)</SelectItem>
                    <SelectItem value=";">Semicolon (;)</SelectItem>
                    <SelectItem value={"\t"}>Tab</SelectItem>
                  </SelectContent>
                </Select>
              )} />
          </Field>
          <SwitchInput form={form} name="include_bom" label="Include UTF-8 BOM" hint="Makes Excel open Cyrillic text correctly" />
        </CardContent>
      </Card>
      <SaveBar pending={pending} dirty={form.formState.isDirty} />
    </form>
  );
}

function PricingTab({ data }: { data: SettingsOut }) {
  const usage = useUsage();
  const { save, pending } = useGroupSave("pricing");
  const pricing = data.runtime.pricing;
  const form = useForm({
    defaultValues: {
      currency: pricing.currency ?? "USD",
      display_currency: pricing.display_currency ?? "EUR",
      exchange_rate: pricing.exchange_rate ?? 1,
      skus: pricing.skus ?? {},
    },
  });
  const skus = Object.keys(pricing.skus ?? {});
  return (
    <div className="grid max-w-4xl gap-4">
      <Card>
        <CardHeader>
          <CardTitle>This month</CardTitle>
          {usage.data && <span className="text-xs text-muted-foreground">since {formatDateTime(usage.data.period_start)}</span>}
        </CardHeader>
        <CardContent>
          {usage.data ? (
            <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>SKU</TableHead>
                    <TableHead className="text-right">Requests</TableHead>
                    <TableHead className="text-right">Free</TableHead>
                    <TableHead className="text-right">Billable</TableHead>
                    <TableHead className="text-right">Cost</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {usage.data.cost.lines.map((l) => (
                    <TableRow key={l.sku}>
                      <TableCell className="font-mono text-xs">{l.sku}</TableCell>
                      <TableCell className="text-right tabular">{formatNumber(l.units)}</TableCell>
                      <TableCell className="text-right tabular">{formatNumber(l.free_units ?? 0)}</TableCell>
                      <TableCell className="text-right tabular">{formatNumber(l.billable_units)}</TableCell>
                      <TableCell className="text-right tabular">{formatMoney(l.cost, usage.data.cost.currency)}</TableCell>
                    </TableRow>
                  ))}
                  {usage.data.cost.lines.length === 0 && (
                    <TableRow><TableCell colSpan={5} className="text-center text-muted-foreground">No billable requests yet</TableCell></TableRow>
                  )}
                </TableBody>
              </Table>
              <div className="rounded-md bg-muted/50 px-4 py-3 text-right">
                <p className="text-xs text-muted-foreground">Estimated</p>
                <p className="text-2xl font-semibold">{formatMoney(usage.data.cost.display_total, usage.data.cost.display_currency)}</p>
                <p className="text-xs text-muted-foreground">
                  {formatNumber(usage.data.api_calls)} calls · {formatNumber(usage.data.cached_calls)} served from cache
                </p>
              </div>
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">Loading…</p>
          )}
        </CardContent>
      </Card>
      <form onSubmit={form.handleSubmit((v) => save(v as Record<string, unknown>, () => form.reset(v)))}>
        <Card>
          <CardHeader>
            <CardTitle>Pricing table</CardTitle>
            <span className="text-xs text-muted-foreground">Verify against Google's current price list</span>
          </CardHeader>
          <CardContent className="grid gap-3">
            <div className="grid gap-3 sm:grid-cols-3">
              <TextInput form={form} name="currency" label="Price currency" />
              <TextInput form={form} name="display_currency" label="Display currency" />
              <NumberInput form={form} name="exchange_rate" label="Exchange rate" step={0.01} hint="Display units per 1 price unit" />
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>SKU</TableHead>
                  <TableHead>Price / 1,000</TableHead>
                  <TableHead>Free / month</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {skus.map((sku) => (
                  <TableRow key={sku}>
                    <TableCell className="font-mono text-xs">{sku}</TableCell>
                    <TableCell>
                      <Input type="number" step="0.01" className="h-7 w-28" aria-label={`${sku} price`}
                        {...form.register(`skus.${sku}.price_per_1000` as const, { valueAsNumber: true })} />
                    </TableCell>
                    <TableCell>
                      <Input type="number" className="h-7 w-28" aria-label={`${sku} free units`}
                        {...form.register(`skus.${sku}.free_per_month` as const, { valueAsNumber: true })} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <SaveBar pending={pending} dirty={form.formState.isDirty} />
          </CardContent>
        </Card>
      </form>
    </div>
  );
}

function SuppressionTab() {
  const client = useQueryClient();
  const [showInactive, setShowInactive] = useState(false);
  const [phone, setPhone] = useState("");
  const [reason, setReason] = useState("");
  const list = useSuppressionList(showInactive);
  const add = useMutation({
    mutationFn: () => api.addSuppression({ phone, reason: reason || null }),
    onSuccess: () => {
      setPhone("");
      setReason("");
      toast.success("Number suppressed");
      void client.invalidateQueries({ queryKey: ["suppression"] });
      void client.invalidateQueries({ queryKey: keys.leadsAll });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const reenable = useMutation({
    mutationFn: (id: number) => api.reenableSuppression(id),
    onSuccess: () => {
      toast.success("Number re-enabled");
      void client.invalidateQueries({ queryKey: ["suppression"] });
      void client.invalidateQueries({ queryKey: keys.leadsAll });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <div className="grid max-w-3xl gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Add number</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); if (phone.trim()) add.mutate(); }}>
            <Field label="Phone" htmlFor="sup-phone">
              <Input id="sup-phone" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="0888 123 456" className="w-44" />
            </Field>
            <Field label="Reason" htmlFor="sup-reason">
              <Input id="sup-reason" value={reason} onChange={(e) => setReason(e.target.value)} className="w-64" />
            </Field>
            <Button type="submit" size="sm" disabled={!phone.trim() || add.isPending}>
              <ShieldOffIcon /> Suppress
            </Button>
          </form>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Do-not-contact list</CardTitle>
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Switch checked={showInactive} onCheckedChange={setShowInactive} /> Show re-enabled
          </label>
        </CardHeader>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Phone</TableHead>
              <TableHead>Reason</TableHead>
              <TableHead>Added</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {list.data?.map((e) => (
              <TableRow key={e.id} className={e.active ? "" : "opacity-60"}>
                <TableCell className="tabular">{e.normalized_phone ?? `lead #${e.business_id}`}</TableCell>
                <TableCell className="text-muted-foreground">{e.reason ?? "—"}</TableCell>
                <TableCell className="text-muted-foreground">{formatDateTime(e.created_at)}</TableCell>
                <TableCell className="text-right">
                  {e.active ? (
                    <Button size="xs" variant="outline" onClick={() => {
                      if (window.confirm(`Re-enable ${e.normalized_phone ?? "this lead"}? It will become callable again.`)) reenable.mutate(e.id);
                    }}>
                      Re-enable
                    </Button>
                  ) : (
                    <span className="text-xs text-muted-foreground">re-enabled {formatDateTime(e.deactivated_at)}</span>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {list.data?.length === 0 && (
              <TableRow><TableCell colSpan={4} className="text-center text-muted-foreground">No suppressed numbers</TableCell></TableRow>
            )}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}

function useSuppressionList(all: boolean) {
  return useQuery({ queryKey: keys.suppression(all), queryFn: () => api.suppression(all) });
}

function UsersTab({ data }: { data: SettingsOut }) {
  const users = useUsers();
  return (
    <div className="grid max-w-3xl gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Users</CardTitle>
          <Badge variant="muted">AUTH_MODE={data.environment.auth_mode}</Badge>
        </CardHeader>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Email</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Last login</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {users.data?.map((u) => (
              <TableRow key={u.id}>
                <TableCell className="font-medium">{u.name}</TableCell>
                <TableCell className="text-muted-foreground">{u.email}</TableCell>
                <TableCell>{u.role}</TableCell>
                <TableCell className="text-muted-foreground">{formatDateTime(u.last_login_at)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <CardContent className="border-t text-xs text-muted-foreground">
          Create salespeople with <code>python -m app.cli create-user --email … --name …</code>. Each gets an access token;
          set <code>AUTH_MODE=token</code> to require sign-in. Leads record who created, contacted and owns them.
        </CardContent>
      </Card>
    </div>
  );
}
