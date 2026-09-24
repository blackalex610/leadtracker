import type { LeadDetail } from "@leadtracker/shared";
import { CopyIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function PitchCard({ lead, defaultLanguage = "en" }: { lead: LeadDetail; defaultLanguage?: string }) {
  const languages = Object.keys(lead.pitches);
  const [language, setLanguage] = useState(languages.includes(defaultLanguage) ? defaultLanguage : languages[0] ?? "en");
  const pitch = lead.pitches[language];
  if (!pitch) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Suggested pitch</CardTitle>
        <div className="flex items-center gap-1">
          {languages.map((l) => (
            <button
              key={l}
              type="button"
              aria-pressed={l === language}
              onClick={() => setLanguage(l)}
              className={cn(
                "rounded px-1.5 py-0.5 text-[11px] font-medium uppercase",
                l === language ? "bg-foreground text-background" : "text-muted-foreground hover:bg-accent",
              )}
            >
              {l}
            </button>
          ))}
          <Button
            size="icon-sm"
            variant="ghost"
            aria-label="Copy pitch"
            onClick={() => {
              void navigator.clipboard?.writeText(pitch.text).then(() => toast.success("Pitch copied"));
            }}
          >
            <CopyIcon />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="grid gap-2">
        <blockquote className="border-l-2 pl-3 text-[13px] leading-relaxed">{pitch.text}</blockquote>
        <p className="text-[11px] text-muted-foreground">
          Built only from observed signals — adapt it, never claim more than what was observed.
        </p>
      </CardContent>
    </Card>
  );
}
