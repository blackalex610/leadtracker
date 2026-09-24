import { Tooltip } from "@/components/ui/tooltip";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

export interface BarDatum {
  key: string;
  label: string;
  value: number;
  hint?: string;
}

/**
 * Single-series horizontal bar list (magnitude by category). One hue for every
 * bar, thin bars with a rounded data end, value at the tip. Every value is
 * printed, so the list doubles as its own table view; rows are keyboard
 * focusable and carry a tooltip.
 */
export function BarList({ data, onSelect, emptyLabel = "No data yet", className }: {
  data: BarDatum[];
  onSelect?: (key: string) => void;
  emptyLabel?: string;
  className?: string;
}) {
  const max = Math.max(1, ...data.map((d) => d.value));
  if (!data.length || data.every((d) => d.value === 0)) {
    return <p className="py-6 text-center text-xs text-muted-foreground">{emptyLabel}</p>;
  }
  return (
    <ul className={cn("flex flex-col gap-0.5", className)}>
      {data.map((d) => {
        const width = d.value === 0 ? 0 : Math.max(2, (d.value / max) * 100);
        const content = (
          <>
            <span className="truncate text-left text-xs text-muted-foreground">{d.label}</span>
            <span className="flex items-center gap-2">
              <span className="relative h-3 flex-1">
                <span
                  className="absolute inset-y-0 left-0 rounded-r-[4px] bg-series-1 transition-[width] duration-300 group-hover:opacity-80"
                  style={{ width: `${width}%` }}
                />
              </span>
              <span className="w-10 shrink-0 text-right text-xs font-medium tabular">{formatNumber(d.value)}</span>
            </span>
          </>
        );
        return (
          <li key={d.key}>
            <Tooltip content={d.hint ?? `${d.label}: ${formatNumber(d.value)}`}>
              {onSelect ? (
                <button
                  type="button"
                  onClick={() => onSelect(d.key)}
                  className="group grid w-full grid-cols-[minmax(7rem,38%)_1fr] items-center gap-2 rounded px-1 py-1 outline-none hover:bg-muted/60 focus-visible:ring-2 focus-visible:ring-ring/40"
                >
                  {content}
                </button>
              ) : (
                <div tabIndex={0} className="group grid grid-cols-[minmax(7rem,38%)_1fr] items-center gap-2 rounded px-1 py-1 outline-none focus-visible:ring-2 focus-visible:ring-ring/40">
                  {content}
                </div>
              )}
            </Tooltip>
          </li>
        );
      })}
    </ul>
  );
}
