import type { ImportPreview, ImportResult } from "@leadtracker/shared";
import { useMutation } from "@tanstack/react-query";
import { CheckCircle2Icon, FileUpIcon, UploadIcon } from "lucide-react";
import { useRef, useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";

import { PageHeader } from "@/components/app/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, errorMessage } from "@/lib/api";
import { useInvalidateLeads } from "@/lib/queries";
import { cn } from "@/lib/utils";

const FIELD_LABELS: Record<string, string> = {
  name: "Business name *",
  phone: "Phone",
  website: "Website",
  address: "Address",
  city: "City",
  category: "Category",
  rating: "Rating",
  reviews: "Reviews",
  google_maps_url: "Google Maps URL",
  notes: "Notes",
};
const IGNORE = "__ignore";
const STATUS_VARIANT = { new: "good", duplicate: "warm", invalid: "hot" } as const;

export default function ImportPage() {
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [strategy, setStrategy] = useState<"skip" | "fill_empty">("skip");
  const [audit, setAudit] = useState(true);
  const [skipRows, setSkipRows] = useState<Set<number>>(new Set());
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const invalidate = useInvalidateLeads();

  const upload = useMutation({
    mutationFn: api.importPreview,
    onSuccess: (data) => {
      setPreview(data);
      setResult(null);
      setSkipRows(new Set());
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const remap = useMutation({
    mutationFn: (mapping: Record<string, string | null>) =>
      api.importRemap({ batch_id: preview!.batch_id, mapping, duplicate_strategy: strategy, audit_websites: audit, skip_rows: [] }),
    onSuccess: setPreview,
    onError: (e) => toast.error(errorMessage(e)),
  });
  const commit = useMutation({
    mutationFn: () =>
      api.importCommit({
        batch_id: preview!.batch_id,
        mapping: preview!.mapping,
        duplicate_strategy: strategy,
        audit_websites: audit,
        skip_rows: [...skipRows],
      }),
    onSuccess: (data) => {
      setResult(data);
      invalidate();
      toast.success(`Imported ${data.created} new lead(s)`);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const onFile = (file: File | undefined) => {
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      toast.error("File too large (max 5 MB)");
      return;
    }
    upload.mutate(file);
  };

  return (
    <div className="flex flex-col">
      <PageHeader
        title="Import CSV"
        description="Existing lead lists are de-duplicated against your database — nothing is overwritten blindly"
        actions={
          <Button size="sm" variant="outline" asChild>
            <Link to="/leads">Back to leads</Link>
          </Button>
        }
      />
      <div className="grid max-w-6xl gap-4 p-5">
        {result ? (
          <Card>
            <CardContent className="flex flex-col items-start gap-2 py-6">
              <p className="flex items-center gap-2 text-sm font-semibold">
                <CheckCircle2Icon className="size-4 text-good" /> Import complete
              </p>
              <p className="text-[13px] text-muted-foreground">
                {result.created} created · {result.merged} merged (empty fields filled) · {result.skipped_duplicates} duplicates
                skipped · {result.invalid} invalid rows
                {result.audit_job_id && " · website audits running in the background"}
              </p>
              <div className="flex gap-2">
                <Button size="sm" asChild>
                  <Link to="/leads?sort=created_at&order=desc">View leads</Link>
                </Button>
                <Button size="sm" variant="outline" onClick={() => { setPreview(null); setResult(null); }}>
                  Import another file
                </Button>
              </div>
            </CardContent>
          </Card>
        ) : !preview ? (
          <Card
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => { e.preventDefault(); setDragging(false); onFile(e.dataTransfer.files[0]); }}
            className={cn("border-dashed", dragging && "bg-accent")}
          >
            <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
              <FileUpIcon className="size-6 text-muted-foreground" aria-hidden />
              <p className="text-sm font-medium">Drop a CSV file here</p>
              <p className="max-w-md text-xs text-muted-foreground">
                UTF-8 or Windows-1251, comma or semicolon separated, up to 10,000 rows. Columns such as name, business,
                company, phone, telephone, website, url, address (English or Bulgarian headers) are mapped automatically.
              </p>
              <input ref={inputRef} type="file" accept=".csv,text/csv" className="sr-only" aria-label="CSV file"
                onChange={(e) => onFile(e.target.files?.[0])} />
              <Button size="sm" onClick={() => inputRef.current?.click()} disabled={upload.isPending}>
                <UploadIcon /> {upload.isPending ? "Reading…" : "Choose file"}
              </Button>
            </CardContent>
          </Card>
        ) : (
          <>
            <Card>
              <CardHeader>
                <CardTitle>
                  {preview.filename} · {preview.total_rows} rows
                </CardTitle>
                <div className="flex gap-1.5">
                  <Badge variant="good">{preview.counts.new ?? 0} new</Badge>
                  <Badge variant="warm">{preview.counts.duplicate ?? 0} duplicates</Badge>
                  <Badge variant="hot">{preview.counts.invalid ?? 0} invalid</Badge>
                </div>
              </CardHeader>
              <CardContent className="grid gap-4">
                <div className="grid gap-2 sm:grid-cols-5">
                  {preview.target_fields.map((field) => (
                    <div key={field} className="grid gap-1">
                      <Label>{FIELD_LABELS[field] ?? field}</Label>
                      <Select
                        value={preview.mapping[field] ?? IGNORE}
                        onValueChange={(value) => remap.mutate({ ...preview.mapping, [field]: value === IGNORE ? null : value })}
                      >
                        <SelectTrigger size="sm" aria-label={`Column for ${field}`}>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value={IGNORE}>— not imported</SelectItem>
                          {preview.columns.map((c) => (
                            <SelectItem key={c} value={c}>
                              {c}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  ))}
                </div>
                <div className="flex flex-wrap items-center gap-4 border-t pt-3">
                  <div className="flex items-center gap-2">
                    <Label htmlFor="strategy">Duplicates</Label>
                    <Select value={strategy} onValueChange={(v) => setStrategy(v as "skip" | "fill_empty")}>
                      <SelectTrigger id="strategy" size="sm" className="w-64">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="skip">Skip duplicates (recommended)</SelectItem>
                        <SelectItem value="fill_empty">Merge: only fill empty fields</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <label className="flex items-center gap-2 text-[13px]">
                    <Checkbox checked={audit} onCheckedChange={(v) => setAudit(v === true)} /> Audit websites after import
                  </label>
                  <Button className="ml-auto" size="sm" onClick={() => commit.mutate()}
                    disabled={commit.isPending || !preview.mapping.name}>
                    {commit.isPending ? "Importing…" : `Import ${preview.total_rows - skipRows.size} rows`}
                  </Button>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Preview</CardTitle>
                <span className="text-xs text-muted-foreground">First {preview.rows.length} rows · untick to skip a row</span>
              </CardHeader>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-8" />
                    <TableHead>Row</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Name</TableHead>
                    <TableHead>Phone</TableHead>
                    <TableHead>Website</TableHead>
                    <TableHead>Address</TableHead>
                    <TableHead>Notes</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {preview.rows.map((row) => (
                    <TableRow key={row.index} className={skipRows.has(row.index) ? "opacity-50" : ""}>
                      <TableCell>
                        <Checkbox
                          aria-label={`Import row ${row.index + 2}`}
                          checked={!skipRows.has(row.index)}
                          onCheckedChange={(v) => {
                            const next = new Set(skipRows);
                            if (v === true) next.delete(row.index);
                            else next.add(row.index);
                            setSkipRows(next);
                          }}
                        />
                      </TableCell>
                      <TableCell className="text-muted-foreground tabular">{row.index + 2}</TableCell>
                      <TableCell>
                        <Badge variant={STATUS_VARIANT[row.status]}>{row.status}</Badge>
                        {row.status === "duplicate" && (
                          <p className="text-[11px] text-muted-foreground">
                            {row.duplicate_of ? (
                              <Link to={`/leads/${row.duplicate_of}`} className="underline" target="_blank">
                                {row.duplicate_name}
                              </Link>
                            ) : (
                              row.duplicate_name
                            )}{" "}
                            · {row.match_reason?.replaceAll("_", " ")}
                          </p>
                        )}
                        {row.issues.map((issue) => (
                          <p key={issue} className="text-[11px] text-bad">{issue}</p>
                        ))}
                      </TableCell>
                      <TableCell className="font-medium">{row.values.name ?? "—"}</TableCell>
                      <TableCell className="tabular">{row.values.phone ?? "—"}</TableCell>
                      <TableCell className="max-w-40 truncate">{row.values.website ?? "—"}</TableCell>
                      <TableCell className="max-w-56 truncate text-muted-foreground">{row.values.address ?? "—"}</TableCell>
                      <TableCell className="max-w-40 truncate text-muted-foreground">{row.values.notes ?? ""}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Card>
          </>
        )}
      </div>
    </div>
  );
}
