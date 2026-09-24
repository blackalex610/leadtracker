const numberFmt = new Intl.NumberFormat("en-US");

export function formatNumber(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : numberFmt.format(value);
}

export function formatMoney(value: number | null | undefined, currency: string): string {
  if (value === null || value === undefined) return "—";
  try {
    return new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: 2 }).format(value);
  } catch {
    return `${value.toFixed(2)} ${currency}`;
  }
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return date.toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

export function relativeTime(value: string | null | undefined, now: Date = new Date()): string {
  if (!value) return "—";
  const diff = (new Date(value).getTime() - now.getTime()) / 1000;
  const abs = Math.abs(diff);
  const units: [number, Intl.RelativeTimeFormatUnit][] = [
    [60, "second"],
    [3600, "minute"],
    [86400, "hour"],
    [604800, "day"],
    [2629800, "week"],
    [31557600, "month"],
  ];
  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  let divisor = 1;
  for (const [limit, unit] of units) {
    if (abs < limit) return rtf.format(Math.round(diff / divisor), unit);
    divisor = limit;
  }
  return rtf.format(Math.round(diff / 31557600), "year");
}

export function displayDomain(url: string | null | undefined): string {
  if (!url) return "";
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export function telHref(e164: string | null | undefined): string | undefined {
  return e164 ? `tel:${e164.replace(/[^+\d]/g, "")}` : undefined;
}

/** Google Maps search link used only when no authoritative Maps URL exists. */
export function mapsSearchUrl(name: string, address: string | null | undefined): string {
  const query = [name, address].filter(Boolean).join(", ");
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`;
}

export function healthTone(score: number | null | undefined): "bad" | "ok" | "good" | "none" {
  if (score === null || score === undefined) return "none";
  if (score < 40) return "bad";
  if (score < 70) return "ok";
  return "good";
}
