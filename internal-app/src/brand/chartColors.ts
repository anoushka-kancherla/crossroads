/** The one place that decides what each chart colour means. Charts take their colours from here and never
 *  write a colour of their own. Values are token variables, so the token file stays the only source. */
export type Role = "recommended" | "actual" | "alternative" | "further" | "baseline" | "grid" | "axis";

const COLORS: Record<Role, string> = {
  recommended: "var(--chart-green)",
  actual: "var(--chart-green)",
  alternative: "var(--chart-blue)",
  further: "var(--chart-purple)",
  baseline: "var(--chart-grey)",
  grid: "var(--chart-grid)",
  axis: "var(--chart-axis-text)",
};

export const roleColor = (role: Role): string => COLORS[role];

/** Projections are dashed in the colour of their series. */
export const PROJECTION_DASH = "6 4";

/** Low to high, for income bands and other ordered groups. */
export const SEQUENTIAL = ["var(--chart-seq-1)", "var(--chart-seq-2)", "var(--chart-seq-3)", "var(--chart-seq-4)"];

/** The role of each path's line on the paths chart: the recommended path green, "Keep as is" grey, and the
 *  others blue then purple in turn. The same meaning in every chart. */
export function pathRoles(paths: string[], recommended: string | null): Record<string, Role> {
  const roles: Record<string, Role> = {};
  let others = 0;
  for (const p of paths) {
    roles[p] = p === recommended ? "recommended" : p === "keep_as_is" ? "baseline" : others++ % 2 === 0 ? "alternative" : "further";
  }
  return roles;
}
