// Display formatting only. Every figure is computed by the backend engine; nothing here does
// arithmetic on money.

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

/** A money string from the API, shown in whole dollars. */
export function money(value: string): string {
  return usd.format(Number(value));
}

export function count(n: number): string {
  return n.toLocaleString("en-US");
}

export function plural(n: number, word: string): string {
  return `${count(n)} ${word}${n === 1 ? "" : "s"}`;
}

/** "2026-09" as "Sep 2026". */
export function monthLabel(yearMonth: string): string {
  const [year, month] = yearMonth.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, 1)).toLocaleString("en-US", {
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

/** "Oct 24, 2026, 12:00 PM UTC": a time with its zone, so it reads the same wherever it is shown. */
export function dateTimeLabel(iso: string): string {
  return `${new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit", timeZone: "UTC" })} UTC`;
}

export function dateLabel(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
}
