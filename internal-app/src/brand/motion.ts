/** True under "reduce motion", and also where the browser cannot say (the test environment): then every
 *  value and order simply changes at once. */
export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return true;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** A motion token such as --motion-count, in milliseconds (0 under reduced motion, from the token file). */
export function motionMs(token: "--motion-count" | "--motion-resort"): number {
  const ms = parseMs(getComputedStyle(document.documentElement).getPropertyValue(token));
  return ms ?? (token === "--motion-count" ? 300 : 200);
}

/** "300ms" and the minified ".3s" both mean the same time; anything else is unknown. */
export function parseMs(raw: string): number | null {
  const m = /^\s*(-?\d*\.?\d+)(ms|s)\s*$/.exec(raw);
  if (!m) return null;
  return parseFloat(m[1]) * (m[2] === "s" ? 1000 : 1);
}
