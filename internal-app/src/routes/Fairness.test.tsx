import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import type { FairnessReport } from "../api/client";

type Verdict = NonNullable<FairnessReport["verdict"]>;

const band = (key: "lower" | "middle" | "higher", label: string, customers: number, rank: string): FairnessReport["bands"][number] => ({
  key, label, customers,
  with_recommendation: customers - 3, no_affordable: 3,
  path_counts: [{ path: "buy_out", label: "Buy out", customers: customers - 3 }],
  avg_revenue: "5210.00", avg_revenue_n: customers - 3,
  with_choice: customers - 6, single_option: 3,
  avg_rank_pct: rank, avg_rank_n: customers - 6,
  most_profitable_count: 22, avg_given_up: "812.00", avg_affordable_options: "3.2", no_affordable_share_pct: "1.9",
});

const verdictOf = (o: Partial<Verdict> = {}): Verdict => ({
  outcome: "no_evidence",
  sentence: "No evidence that lower-income customers are steered toward paths that earn Toyota more interest: the lowest-income band's recommendations rank 1.4 points higher than the highest-income band's (95% interval -6.2 to 9.0, from 157 and 165 customers with a real choice).",
  interval_note: null, gap_points: "1.4", ci_low: "-6.2", ci_high: "9.0", lowest_n: 157, highest_n: 165, ...o,
});

const report = (verdict: Verdict | null = verdictOf()): FairnessReport => ({
  empty: false,
  computed_at: "2026-10-24T18:30:00Z",
  population: {
    size: 500, seed: 20261024, loans: 249, leases: 251,
    description: ["Monthly income: median $5,500.", "No market listings are used: values are estimated by depreciation."],
  },
  thresholds: { gap_points: "15", min_choice: 30, resamples: 1000, confidence_pct: 95, bootstrap_seed: 20261025 },
  bands: [
    band("lower", "Under $4,500 a month", 160, "31.2"),
    band("middle", "$4,500 to $6,499 a month", 175, "30.0"),
    band("higher", "$6,500 or more a month", 165, "29.8"),
  ],
  path_mix: [{ path: "buy_out", label: "Buy out", customers: 491 }],
  verdict,
  by_type: [
    { scope: "loan", enough: true, lowest_n: 84, highest_n: 101, gap_points: "2.0", ci_low: "-9.1", ci_high: "12.8" },
    { scope: "lease", enough: false, lowest_n: 12, highest_n: 64, gap_points: null, ci_low: null, ci_high: null },
  ],
  limits: [
    "Only income is examined. Other characteristics are not covered.",
    "The customers are synthetic. This shows how the engine behaves on this population; it cannot show that real customers are treated fairly or unfairly.",
    "This is a demonstration of the method, not a legal fair-lending finding.",
  ],
});

type Reply = { status?: number; body?: unknown } | Error | "never";

function stubFetch(routes: Partial<Record<string, Reply>>) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${url}`;
      calls.push(key);
      const reply = routes[key];
      if (reply === undefined) throw new Error(`unexpected request ${key}`);
      if (reply === "never") return new Promise(() => {});
      if (reply instanceof Error) throw reply;
      const status = reply.status ?? 200;
      return { ok: status < 400, status, headers: { get: () => null }, json: async () => reply.body };
    }),
  );
  return calls;
}

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const signedIn = { body: { user: "staff" } };
const unauthorized = { status: 401, body: { detail: "Please sign in." } };
const FAIR = "GET /api/internal/fairness";
const SESSION = "GET /api/internal/session";

afterEach(() => vi.unstubAllGlobals());

describe("fairness page states", () => {
  it("shows a loading state while the report is on the way", async () => {
    stubFetch({ [SESSION]: signedIn, [FAIR]: "never" });
    renderAt("/fairness");
    expect(await screen.findByText("Signed in as staff")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Loading");
  });

  it("shows an empty state, not zeros, when the population has no customers", async () => {
    stubFetch({ [SESSION]: signedIn, [FAIR]: { body: { ...report(null), empty: true, bands: [], by_type: [], path_mix: [] } } });
    renderAt("/fairness");
    expect(await screen.findByText(/no fairness figures are available yet/i)).toBeInTheDocument();
    expect(screen.queryByText(/No evidence/)).not.toBeInTheDocument();
  });

  it("shows a readable error, not a stack trace", async () => {
    stubFetch({ [SESSION]: signedIn, [FAIR]: { status: 503, body: { detail: "The fairness figures couldn't be computed right now." } } });
    renderAt("/fairness");
    expect(await screen.findByRole("alert")).toHaveTextContent("The fairness figures couldn't be computed right now.");
  });

  it("shows the sign-in form and makes no fairness request without a session", async () => {
    const calls = stubFetch({ [SESSION]: unauthorized });
    renderAt("/fairness");
    expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
    expect(calls.filter((c) => c.includes("fairness"))).toHaveLength(0);
  });

  it("returns to sign-in with no figures left when the session ends mid-use", async () => {
    stubFetch({ [SESSION]: signedIn, [FAIR]: unauthorized });
    renderAt("/fairness");
    expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.queryByText(/steered/)).not.toBeInTheDocument();
    expect(screen.queryByText("Under $4,500 a month")).not.toBeInTheDocument();
  });
});

describe("fairness page content", () => {
  it("leads with the verdict, in words, with the gap, the interval and both counts", async () => {
    stubFetch({ [SESSION]: signedIn, [FAIR]: { body: report() } });
    renderAt("/fairness");
    const verdict = await screen.findByRole("region", { name: "Verdict" });
    expect(within(verdict).getByRole("heading")).toHaveTextContent("No evidence of steering");
    expect(verdict).toHaveTextContent("rank 1.4 points higher than the highest-income band's");
    expect(verdict).toHaveTextContent("95% interval -6.2 to 9.0");
    expect(verdict).toHaveTextContent("from 157 and 165 customers with a real choice");
    // the verdict comes before the band table
    const all = screen.getAllByRole("region");
    expect(all[0]).toBe(verdict);
  });

  it("renders an unfavourable verdict with the same prominence and its interval note", async () => {
    const bad = verdictOf({
      outcome: "possible_steering",
      sentence: "Possible steering of lower-income customers toward paths that earn Toyota more interest, to be reviewed: gap 22.0.",
      interval_note: "The data cannot confirm the gap is beyond the 15-point threshold.",
      gap_points: "22.0", ci_low: "12.4", ci_high: "31.0",
    });
    stubFetch({ [SESSION]: signedIn, [FAIR]: { body: report(bad) } });
    renderAt("/fairness");
    const verdict = await screen.findByRole("region", { name: "Verdict" });
    expect(within(verdict).getByRole("heading")).toHaveTextContent("Possible steering, to be reviewed");
    expect(verdict).toHaveTextContent("The data cannot confirm the gap is beyond the 15-point threshold.");
    expect(verdict.className).toBe("verdict"); // the same panel as a favourable verdict
  });

  it("says which kind of population it covers", async () => {
    stubFetch({ [SESSION]: signedIn, [FAIR]: { body: report() } });
    renderAt("/fairness");
    expect(await screen.findByText(/separate synthetic population of 500 customers, not the 12 demo customers/)).toBeInTheDocument();
  });

  it("shows the three bands with ranges, counts, path mix and the rank with its count", async () => {
    stubFetch({ [SESSION]: signedIn, [FAIR]: { body: report() } });
    renderAt("/fairness");
    const table = within(await screen.findByRole("region", { name: "Income bands" })).getByRole("table");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveTextContent("Under $4,500 a month");
    expect(rows[0]).toHaveTextContent("160");
    expect(rows[0]).toHaveTextContent("157"); // with a recommendation
    expect(rows[0]).toHaveTextContent("Buy out 157");
    expect(rows[0]).toHaveTextContent("31.2% (from 154 customers with a real choice)");
    expect(rows[2]).toHaveTextContent("$6,500 or more a month");
  });

  it("shows the evidence beside its customer counts and the average-income caveat", async () => {
    stubFetch({ [SESSION]: signedIn, [FAIR]: { body: report() } });
    renderAt("/fairness");
    const ev = await screen.findByRole("region", { name: "Evidence" });
    const first = within(ev).getAllByRole("row")[1];
    expect(first).toHaveTextContent("22 of 154 with a real choice");
    expect(first).toHaveTextContent("$812 (from 154 customers)");
    expect(first).toHaveTextContent("3.2 (from 160 customers)");
    expect(first).toHaveTextContent("1.9% (of 160 customers)");
    expect(ev).toHaveTextContent("reflects contract size as well as recommendations and is not the steering measure");
  });

  it("labels the affordability figures as a separate matter from steering", async () => {
    stubFetch({ [SESSION]: signedIn, [FAIR]: { body: report() } });
    renderAt("/fairness");
    const ev = await screen.findByRole("region", { name: "Evidence" });
    for (const name of [/Average affordable options/, /Share with no affordable option/]) {
      const head = within(ev).getByRole("columnheader", { name });
      expect(head).toHaveTextContent("A separate matter from steering; not part of the verdict");
    }
  });

  it("says 'No customers' for an empty band and 'Not enough customers' where there is no real choice", async () => {
    const r = report();
    const empty = { ...band("middle", "$4,500 to $6,499 a month", 0, "0"), with_recommendation: 0, no_affordable: 0,
      path_counts: [], avg_revenue: null, avg_revenue_n: 0, with_choice: 0, single_option: 0, avg_rank_pct: null,
      avg_rank_n: 0, most_profitable_count: 0, avg_given_up: null, avg_affordable_options: null, no_affordable_share_pct: null };
    const noChoice = { ...r.bands[2], with_choice: 0, single_option: 5, avg_rank_pct: null, avg_rank_n: 0,
      most_profitable_count: 0, avg_given_up: null };
    stubFetch({ [SESSION]: signedIn, [FAIR]: { body: { ...r, bands: [r.bands[0], empty, noChoice] } } });
    renderAt("/fairness");
    const bands = within(await screen.findByRole("region", { name: "Income bands" })).getAllByRole("row").slice(1);
    expect(bands[1]).toHaveTextContent("No customers");
    expect(bands[1]).not.toHaveTextContent("0%");
    expect(bands[2]).toHaveTextContent("Not enough customers");
    const ev = within(screen.getByRole("region", { name: "Evidence" })).getAllByRole("row").slice(1);
    expect(ev[1]).toHaveTextContent("No customers");
    expect(ev[1].textContent).not.toMatch(/\(from|\(of/); // no figure and no count behind one
    expect(ev[2]).toHaveTextContent("Not enough customers");
  });

  it("shows the loan and lease gaps as unscored evidence, and no number for a type short of customers", async () => {
    stubFetch({ [SESSION]: signedIn, [FAIR]: { body: report() } });
    renderAt("/fairness");
    const sec = await screen.findByRole("region", { name: "Loan and lease" });
    expect(sec).toHaveTextContent("do not change the verdict");
    const [loan, lease] = within(sec).getAllByRole("row").slice(1);
    expect(loan).toHaveTextContent("2.0 points");
    expect(loan).toHaveTextContent("-9.1 to 12.8");
    expect(loan).toHaveTextContent("84 and 101");
    expect(lease).toHaveTextContent("Not enough customers");
    expect(lease).not.toHaveTextContent("points");
  });

  it("states the limits on the same screen", async () => {
    stubFetch({ [SESSION]: signedIn, [FAIR]: { body: report() } });
    renderAt("/fairness");
    const panel = await screen.findByRole("region", { name: "What this check does and does not show" });
    expect(panel).toHaveTextContent("Under $4,500 a month; $4,500 to $6,499 a month; $6,500 or more a month");
    expect(panel).toHaveTextContent("more than 15 points above");
    expect(panel).toHaveTextContent("fewer than 30 customers with a real choice");
    expect(panel).toHaveTextContent("percentile bootstrap, 1,000 resamples, 95% interval, fixed seed 20261025");
    expect(panel).toHaveTextContent("500 synthetic customers");
    expect(panel).toHaveTextContent("fixed seed 20261024");
    expect(panel).toHaveTextContent("Oct 24, 2026");
    expect(panel).toHaveTextContent("Only income is examined. Other characteristics are not covered.");
    expect(panel).toHaveTextContent("not a legal fair-lending finding");
    expect(panel).toHaveTextContent("No market listings are used");
    expect(screen.getByRole("note")).toHaveTextContent("Results on a small band are uncertain");
  });
});

describe("refresh", () => {
  it("pressing Refresh on the portfolio refetches the fairness report", async () => {
    let reads = 0;
    const portfolio = {
      empty: true, computed_at: null, customers_total: 0, no_recommendation: 0,
      kpis: { retained_count: 0, retained_pct: "0", revenue_total: "0", avg_savings: "0", explanations_verified_pct: "0" },
      by_path: [], next_steps: [], self_service_pct: "0", assumptions: [],
    };
    const calls = stubFetch({
      [SESSION]: signedIn,
      [FAIR]: { body: report() },
      "GET /api/internal/portfolio": { body: portfolio },
      "POST /api/internal/portfolio/refresh": { body: portfolio },
    });
    renderAt("/fairness");
    await screen.findByRole("region", { name: "Verdict" });
    reads = calls.filter((c) => c === FAIR).length;
    fireEvent.click(screen.getByRole("link", { name: "Portfolio" }));
    fireEvent.click(await screen.findByRole("button", { name: "Refresh" }));
    await vi.waitFor(() => expect(calls).toContain("POST /api/internal/portfolio/refresh"));
    fireEvent.click(screen.getByRole("link", { name: "Fairness" }));
    await screen.findByRole("region", { name: "Verdict" });
    await vi.waitFor(() => expect(calls.filter((c) => c === FAIR).length).toBeGreaterThan(reads));
  });
});
