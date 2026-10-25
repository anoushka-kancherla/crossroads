import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import type { Overview, PathOption, PathsResult } from "../api/client";

const customers = [{ id: "cust_01", display_name: "Maya Ortiz", vehicle_label: "RAV4 lease" }];

const option = (o: Partial<PathOption> & Pick<PathOption, "path" | "label">): PathOption => ({
  eligible: true, ineligible_reason: null, five_year_cost: "31796", monthly_payment: "389.00", upfront_cost: "0.00",
  affordable: true, shortfalls: [], tradeoff: "A trade-off line.",
  cumulative_cost: Array.from({ length: 60 }, (_, i) => String((i + 1) * 500)), ...o,
});

const paths: PathsResult = {
  contract_type: "lease",
  inputs_used: { miles_per_year: 14600, monthly_budget: "2250", years_to_keep: 2, financing_rate: "6.5" },
  options: [
    option({ path: "keep_as_is", label: "Keep as is", five_year_cost: "31118" }),
    option({ path: "buy_out", label: "Buy out", five_year_cost: "25729", monthly_payment: "419.69" }),
    option({ path: "walk_away", label: "Return and walk away", five_year_cost: "28000" }),
  ],
  recommendation: {
    path: "buy_out", label: "Buy out", runner_up: "keep_as_is", monthly_room_left: "1830.31", closest_when_none: null,
    closest_label: null, closest_gap: "0",
    explanation: { headline: "Buy out: saves about $5,389 over 5 years", text: "Buy out is your best next move.", source: "template", verified: true },
  },
  flips: [],
  ranges: {
    miles_per_year: { min: "5000", max: "25000", step: "100" }, monthly_budget: { min: "200", max: "2250", step: "10" },
    years_to_keep: { min: "1", max: "8", step: "1" }, financing_rate: { min: "3", max: "12", step: "0.25" },
  },
  assumptions: ["Illustrative: 12% yearly depreciation."],
};

const overview = {
  customer: { id: "cust_01", first_name: "Maya", vehicle: "2023 RAV4 XLE", contract_type: "lease", months_left: 14 },
  tiles: { monthly_payment: "389.00", payments_made: 22, payments_total: 36, months_left: 14, ends_on: "2027-12-24", payoff_or_buyout: "26896.00", miles_driven: 31200, allowance: 36000, equity: "-4296.00" },
  mileage: { actual_monthly: [], projected_monthly: [], allowance_per_month: 1000, projection: { rate_per_year: 14600, basis: "history", basis_label: "Based on your odometer history", end_miles: 48000, overage_miles: 0, overage_fee: "0.00" } },
  money: { checking: "3100.00", savings: "1800.00", monthly_income: "5200.00", monthly_bills: "2650.00", room_for_payment: "2250.00", source: "nessie", source_label: "From Nessie", synced_at: null },
  market_value: { low: "21244.00", median: "22600.00", high: "23956.00", n_listings: 8, updated_at: "2026-10-24T12:00:00Z", basis: "listings", basis_label: "From 8 local listings", source: "serpapi", source_label: "Google results via SerpApi" },
} as unknown as Overview;

function serve(over: Record<string, unknown> = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const body =
        url in over ? over[url]
        : url === "/api/customers" ? customers
        : url.endsWith("/overview") ? overview
        : url.endsWith("/paths") ? paths
        : url.endsWith("/explanation") ? paths.recommendation.explanation
        : null;
      if (body === "never") return new Promise(() => {});
      if (body === null) return { ok: false, status: 404, json: async () => ({ detail: "We couldn't find that customer." }) };
      return { ok: true, status: 200, headers: { get: () => null }, json: async () => body };
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

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

describe("branded header", () => {
  it.each(["/overview", "/paths"])("holds a logo slot and the product name on %s", async (path) => {
    serve();
    renderAt(path);
    const header = screen.getByRole("banner");
    expect(header).toHaveTextContent("Your logo");
    expect(header.querySelector(".brand")).toHaveTextContent("Crossroads");
    await screen.findByRole("heading", { level: 1 });
  });
});

describe("Overview buttons", () => {
  it("has exactly one primary button, and the sync button is secondary", async () => {
    serve();
    const { container } = renderAt("/overview");
    await screen.findByRole("link", { name: "See my options" });
    expect(container.querySelectorAll(".primary")).toHaveLength(1);
    expect(screen.getByRole("link", { name: "See my options" })).toHaveClass("primary");
    expect(screen.getByRole("button", { name: "Sync from my bank" })).toHaveClass("secondary");
  });
});

describe("Your paths", () => {
  it("has exactly one primary button; the other actions are secondary", async () => {
    serve();
    const { container } = renderAt("/paths");
    await screen.findByRole("button", { name: "Start buyout" });
    expect(container.querySelectorAll("button.primary")).toHaveLength(1);
    for (const name of ["Reset to my data", "Talk to a specialist", "Ask"]) {
      expect(screen.getByRole("button", { name })).toHaveClass("secondary");
    }
  });

  it("shows the recommendation card with the 5-year cost as the one hero figure and a verified badge", async () => {
    serve();
    const { container } = renderAt("/paths");
    const card = await screen.findByRole("region", { name: /Buy out: saves about/ });
    expect(card).toHaveClass("recommend");
    const hero = container.querySelectorAll(".hero");
    expect(hero).toHaveLength(1);
    expect(hero[0]).toHaveTextContent("$25,729");
    expect(card).toHaveTextContent("5-year cost");
    const badge = card.querySelector(".status-positive")!;
    expect(badge).toHaveTextContent("Numbers verified");
    expect(badge.querySelector("svg")).not.toBeNull();
  });

  it("lists the paths by 5-year cost and marks the recommended one", async () => {
    serve();
    renderAt("/paths");
    await screen.findByRole("article", { name: "Buy out" });
    const order = screen.getAllByRole("article").map((a) => a.getAttribute("aria-label"));
    expect(order).toEqual(["Buy out", "Return and walk away", "Keep as is"]);
    const best = screen.getByRole("article", { name: "Buy out" });
    expect(best).toHaveClass("card-recommended");
    expect(best).toHaveTextContent("Recommended");
    expect(screen.getByRole("article", { name: "Keep as is" })).not.toHaveClass("card-recommended");
  });

  it("keeps an 'Illustrative assumptions' line visible under the results", async () => {
    serve();
    renderAt("/paths");
    const region = await screen.findByRole("region", { name: "Illustrative assumptions" });
    expect(region).toHaveTextContent("12% yearly depreciation");
  });

  it("shows the what-would-change block as the info band", async () => {
    serve({ "/api/customers/cust_01/paths": { ...paths, flips: [{ input: "monthly_budget", current: "2250", threshold: "410", to_path: "keep_as_is", relative_change: "0.8", text: "If your budget changed, Keep as is would win." }] } });
    renderAt("/paths");
    const band = await screen.findByRole("region", { name: /What would change this recommendation/ });
    expect(band).toHaveClass("flips-band");
    expect(band.querySelector("svg")).not.toBeNull();
  });

  it("keeps distinct loading and error states", async () => {
    serve({ "/api/customers/cust_01/paths": "never" });
    renderAt("/paths");
    expect(screen.getAllByRole("status")[0]).toHaveTextContent("Loading");
    vi.unstubAllGlobals();
    vi.stubGlobal("fetch", vi.fn(async (url: string) => (url === "/api/customers" ? { ok: true, status: 200, headers: { get: () => null }, json: async () => customers } : { ok: false, status: 500, json: async () => ({ detail: "Something went wrong." }) })));
    renderAt("/paths");
    await waitFor(() => expect(screen.getAllByRole("alert").length).toBeGreaterThan(0));
  });
});
