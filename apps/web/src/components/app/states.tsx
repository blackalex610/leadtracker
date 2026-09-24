import { AlertTriangleIcon, InboxIcon, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";

export function PageHeader({ title, description, actions, className }: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-wrap items-center justify-between gap-3 border-b px-5 py-3", className)}>
      <div className="min-w-0">
        <h1 className="truncate text-[15px] font-semibold">{title}</h1>
        {description && <p className="text-xs text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function EmptyState({ icon: Icon = InboxIcon, title, description, action, className }: {
  icon?: LucideIcon;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-2 px-6 py-12 text-center", className)}>
      <Icon className="size-6 text-muted-foreground" aria-hidden />
      <p className="text-sm font-medium">{title}</p>
      {description && <p className="max-w-md text-xs text-muted-foreground">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry, className }: { error: unknown; onRetry?: () => void; className?: string }) {
  return (
    <div role="alert" className={cn("flex flex-col items-center gap-2 px-6 py-10 text-center", className)}>
      <AlertTriangleIcon className="size-5 text-bad" aria-hidden />
      <p className="text-sm font-medium">Could not load data</p>
      <p className="max-w-md text-xs text-muted-foreground">{errorMessage(error)}</p>
      {onRetry && (
        <Button size="sm" variant="outline" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}

export function InlineNotice({ tone = "info", title, children, action }: {
  tone?: "info" | "warning" | "error";
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  const toneClass = {
    info: "border-border bg-muted/40",
    warning: "border-warm/40 bg-warm-soft",
    error: "border-bad/40 bg-hot-soft",
  }[tone];
  return (
    <div role={tone === "error" ? "alert" : "status"} className={cn("flex items-start justify-between gap-3 rounded-md border px-3 py-2", toneClass)}>
      <div className="min-w-0">
        <p className="text-[13px] font-medium">{title}</p>
        {children && <div className="text-xs text-muted-foreground">{children}</div>}
      </div>
      {action}
    </div>
  );
}

export function PageFallback() {
  return (
    <div className="space-y-3 p-5" aria-busy="true">
      <Skeleton className="h-6 w-48" />
      <Skeleton className="h-32 w-full" />
    </div>
  );
}
