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

export function dateLabel(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
}
