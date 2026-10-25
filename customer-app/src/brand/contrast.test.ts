import { describe, expect, it } from "vitest";
import tokens from "../styles/tokens.css?raw";

const token = (name: string): string => {
  const m = tokens.match(new RegExp(`${name}:\\s*(#[0-9A-Fa-f]{6})`));
  if (!m) throw new Error(`token ${name} not found`);
  return m[1];
};

const channel = (v: number) => {
  const c = v / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
};
const luminance = (hex: string) => {
  const [r, g, b] = [1, 3, 5].map((i) => channel(parseInt(hex.slice(i, i + 2), 16)));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const ratio = (a: string, b: string) => {
  const [hi, lo] = [luminance(token(a)), luminance(token(b))].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};

const SURFACES = ["--color-bg", "--color-surface-green", "--color-surface-grey", "--color-surface-blue"];
const TEXT_PAIRS: [string, string][] = [
  ...SURFACES.flatMap((s): [string, string][] => [["--color-text", s], ["--color-text-muted", s], ["--color-primary", s]]),
  ["--color-on-primary", "--color-primary"],
  ["--color-on-primary", "--color-primary-hover"],
  ["--color-accent-blue", "--color-bg"],
  ["--color-accent-grey", "--color-bg"],
  ["--color-accent-blue", "--color-surface-blue"],
  ["--color-positive", "--color-positive-bg"],
  ["--color-warning", "--color-warning-bg"],
  ["--color-critical", "--color-critical-bg"],
  ["--color-neutral", "--color-neutral-bg"],
];
// The landing page's two halves: dark text on the light half, white text on the primary half, and the focus ring on each.
const LANDING_PAIRS: [string, string][] = [
  ["--color-text", "--color-surface-green"],
  ["--color-primary", "--color-surface-green"],
  ["--color-on-primary", "--color-primary"],
  ["--color-on-primary", "--color-primary-hover"],
  ["--color-text-muted", "--color-surface-grey"],
  ["--color-text", "--color-surface-blue"],
];
const GRAPHIC_PAIRS: [string, string][] = [
  ["--chart-green", "--color-bg"],
  ["--chart-blue", "--color-bg"],
  ["--chart-grey", "--color-bg"],
  ["--chart-purple", "--color-bg"],
  ["--color-border-strong", "--color-bg"],
  ["--color-focus", "--color-bg"],
  ["--color-focus", "--color-surface-green"],
  ["--color-on-primary", "--color-primary"],
];

describe("brand contrast (WCAG AA)", () => {
  it.each(TEXT_PAIRS)("text %s on %s is at least 4.5:1", (fg, bg) => {
    expect(ratio(fg, bg)).toBeGreaterThanOrEqual(4.5);
  });
  it.each(LANDING_PAIRS)("landing text %s on %s is at least 4.5:1", (fg, bg) => {
    expect(ratio(fg, bg)).toBeGreaterThanOrEqual(4.5);
  });
  it.each(GRAPHIC_PAIRS)("graphic %s on %s is at least 3:1", (fg, bg) => {
    expect(ratio(fg, bg)).toBeGreaterThanOrEqual(3);
  });
});
