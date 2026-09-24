import { PhoneIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";
import { telHref } from "@/lib/format";
import { cn } from "@/lib/utils";

interface PhoneProps {
  phone: string | null | undefined;
  display?: string | null;
  isDemo?: boolean;
  invalid?: boolean;
  suppressed?: boolean;
  className?: string;
}

function blockedReason({ phone, isDemo, invalid, suppressed }: PhoneProps): string | null {
  if (!phone) return "No phone number";
  if (suppressed) return "On the do-not-contact list";
  if (invalid) return "Marked as wrong number";
  if (isDemo) return "Demo record — dialing disabled";
  return null;
}

/** Clickable tel: link (plain text when dialing is not allowed). */
export function PhoneLink(props: PhoneProps) {
  const { phone, display, className } = props;
  if (!phone) return <span className="text-muted-foreground">—</span>;
  const reason = blockedReason(props);
  const text = display ?? phone;
  if (reason) {
    return (
      <Tooltip content={reason}>
        <span className={cn("tabular whitespace-nowrap text-muted-foreground", props.invalid && "line-through", className)}>
          {text}
        </span>
      </Tooltip>
    );
  }
  return (
    <a
      href={telHref(phone)}
      onClick={(e) => e.stopPropagation()}
      className={cn("tabular whitespace-nowrap font-medium hover:underline", className)}
    >
      {text}
    </a>
  );
}

export function CallButton(props: PhoneProps & { size?: "default" | "sm" | "lg"; onCall?: () => void; label?: string }) {
  const reason = blockedReason(props);
  if (reason) {
    return (
      <Tooltip content={reason}>
        <span>
          <Button size={props.size} disabled className={props.className}>
            <PhoneIcon /> {props.label ?? "Call"}
          </Button>
        </span>
      </Tooltip>
    );
  }
  return (
    <Button size={props.size} asChild className={props.className}>
      <a href={telHref(props.phone)} onClick={props.onCall}>
        <PhoneIcon /> {props.label ?? "Call"}
      </a>
    </Button>
  );
}
