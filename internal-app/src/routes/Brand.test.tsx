import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";

const verdict = (outcome: string) => ({
  outcome, sentence: "A fixed sentence.", interval_note: null, gap_points: "1.4", ci_low: "-6.2", ci_high: "9.0", lowest_n: 157, highest_n: 165,
});

const band = (key: string) => ({
  key, label: `Band ${key}`, customers: 160, with_recommendation: 157, no_affordable: 3, path_counts: [], avg_revenue: "5210.00",
  avg_revenue_n: 157, with_choice: 154, single_option: 3, avg_rank_pct: "31.2", avg_rank_n: 154, most_profitable_count: 22,
  avg_given_up: "812.00", avg_affordable_options: "3.2", no_affordable_share_pct: "1.9",
});

const fairness = (outcome = "no_evidence") => ({
  empty: false, computed_at: "2026-10-24T18:30:00Z",
  population: { size: 500, seed: 20261024, loans: 249, leases: 251, description: ["Monthly income: median $5,500."] },
  thresholds: { gap_points: "15", min_choice: 30, resamples: 1000, confidence_pct: 95, bootstrap_seed: 20261025 },
  bands: (["lower", "middle", "higher"] as const).map((key) => band(key)), path_mix: [], verdict: verdict(outcome), by_type: [], limits: ["Only income is examined."],
});

const portfolio = {
  empty: false, computed_at: "2026-10-24T12:00:00Z", customers_total: 12, no_recommendation: 1,
  kpis: { retained_count: 9, retained_pct: "75", revenue_total: "58211.40", avg_savings: "2150", explanations_verified_pct: "100" },
  by_path: [{ path: "buy_out", label: "Buy out", customers: 4, share_pct: "33", stays_with_toyota: true, stays_label: "Yes (Toyota loan)", next_step: "eligible_offer", next_step_label: "Eligible offer", revenue: "58211.40" }],
  next_steps: [{ step: "self_service", label: "Self-service", customers: 5, share_pct: "42" }],
  self_service_pct: "42", assumptions: ["Values are illustrative."],
};

const QUIET_LIVE = {
  accepted_customers: 0, customers_total: 12, retained_customers: 0, retained_pct: null,
  revenue_total: "0", sequence: 0, updated_at: "2026-10-25T12:00:00Z",
};

type Reply = { status?: number; body?: unknown } | "never";
function serve(routes: Record<string, Reply>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${url}`;
      const reply = routes[key] ?? (key === "GET /api/internal/live" ? { body: QUIET_LIVE } : undefined);
      if (reply === undefined) throw new Error(`unexpected request ${url}`);
      if (reply === "never") return new Promise(() => {});
      const status = reply.status ?? 200;
      return { ok: status < 400, status, headers: { get: () => null }, json: async () => reply.body };
    }),
  );
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

const SESSION = "GET /api/internal/session";
const signedIn = { body: { user: "staff" } };
const unauthorized = { status: 401, body: { detail: "Please sign in." } };

afterEach(() => vi.unstubAllGlobals());

describe("internal header", () => {
  it.each([
    ["sign-in", "/", { [SESSION]: unauthorized }],
    ["Business value", "/", { [SESSION]: signedIn, "GET /api/internal/portfolio": { body: portfolio } }],
    ["fairness check", "/fairness", { [SESSION]: signedIn, "GET /api/internal/fairness": { body: fairness() } }],
  ] as const)("shows the logo slot, the product name and 'Staff only' on %s", async (_name, path, routes) => {
    serve(routes as Record<string, Reply>);
    renderAt(path);
    const header = screen.getByRole("banner");
    expect(header).toHaveTextContent("Your logo");
    expect(header).toHaveTextContent("Crossroads Internal");
    expect(within(header).getByText("Staff only")).toHaveClass("staff-badge");
    await screen.findByRole("heading", { level: 1 });
  });
});

describe("sign-in card", () => {
  it("has its own logo slot above the title and one primary button", async () => {
    serve({ [SESSION]: unauthorized });
    const { container } = renderAt("/");
    const form = await screen.findByRole("form", { name: "Staff sign-in" });
    expect(form.querySelector(".logo-card")).not.toBeNull();
    expect(container.querySelectorAll("button.primary")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Sign in" })).toHaveClass("primary");
  });
});

describe("Business value", () => {
  it("has no primary button; Refresh and Sign out are secondary", async () => {
    serve({ [SESSION]: signedIn, "GET /api/internal/portfolio": { body: portfolio } });
    const { container } = renderAt("/");
    await screen.findByText(/Portfolio view/);
    expect(container.querySelectorAll(".primary")).toHaveLength(0);
    expect(screen.getByRole("button", { name: "Refresh" })).toHaveClass("secondary");
    expect(screen.getByRole("button", { name: "Sign out" })).toHaveClass("secondary");
  });

  it("has a grey-header table with numbers, and an 'Illustrative assumptions' line under it", async () => {
    serve({ [SESSION]: signedIn, "GET /api/internal/portfolio": { body: portfolio } });
    renderAt("/");
    const table = await screen.findByRole("table");
    expect(within(table).getAllByRole("columnheader").length).toBeGreaterThan(3);
    expect(table.querySelector("td.num")).not.toBeNull();
    const label = screen.getByText("Illustrative assumptions");
    expect(table.compareDocumentPosition(label) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

describe("fairness verdict banner", () => {
  it.each([
    ["no_evidence", "status-positive", "No evidence found"],
    ["possible_steering", "status-warning", "To review"],
    ["not_enough", "status-neutral", "Not enough data"],
  ])("%s uses the %s style with an icon and the label '%s'", async (outcome, cls, label) => {
    serve({ [SESSION]: signedIn, "GET /api/internal/fairness": { body: fairness(outcome) } });
    const { container } = renderAt("/fairness");
    const banner = await screen.findByRole("region", { name: "Verdict" });
    const status = banner.querySelector(`.${cls}`)!;
    expect(status).not.toBeNull();
    expect(status.querySelector("svg")).not.toBeNull();
    expect(status).toHaveTextContent(label);
    expect(container.querySelectorAll(".primary")).toHaveLength(0);
  });
});

describe("states", () => {
  it("shows a loading state on Business value", async () => {
    serve({ [SESSION]: signedIn, "GET /api/internal/portfolio": "never" });
    renderAt("/");
    await screen.findByText(/Signed in as/);
    // the live panel loads beside the portfolio, so more than one status can be on screen
    expect(screen.getAllByRole("status").some((el) => /Loading/.test(el.textContent ?? ""))).toBe(true);
  });

  it("shows an empty state on Business value", async () => {
    serve({ [SESSION]: signedIn, "GET /api/internal/portfolio": { body: { ...portfolio, empty: true } } });
    renderAt("/");
    expect(await screen.findByText(/No recommendations yet/)).toBeInTheDocument();
  });

  it("shows a readable error on Business value", async () => {
    serve({ [SESSION]: signedIn, "GET /api/internal/portfolio": { status: 500, body: { detail: "We can't load the data right now." } } });
    renderAt("/");
    expect(await screen.findByRole("alert")).toHaveTextContent("We can't load the data right now.");
  });
});
