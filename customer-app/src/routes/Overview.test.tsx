import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import type { Overview } from "../api/client";

const customers = [
  { id: "cust_01", display_name: "Maya Ortiz", vehicle_label: "RAV4 lease" },
  { id: "cust_07", display_name: "Sam Lee", vehicle_label: "Camry loan" },
];

const lease: Overview = {
  customer: { id: "cust_01", first_name: "Maya", vehicle: "2023 RAV4 XLE", contract_type: "lease", months_left: 14 },
  tiles: {
    monthly_payment: "389.00", payments_made: 22, payments_total: 36, months_left: 14, ends_on: "2027-12-24",
    payoff_or_buyout: "26896.00", miles_driven: 31200, allowance: 36000, equity: "-4296.00",
  },
  mileage: {
    actual_monthly: [{ month: "2026-08", miles: 1200 }, { month: "2026-09", miles: 1300 }],
    projected_monthly: [{ month: "2026-10", miles: 1217 }],
    allowance_per_month: 1000,
    projection: {
      rate_per_year: 14600, basis: "history", basis_label: "Based on your odometer history",
      end_miles: 48000, overage_miles: 12000, overage_fee: "3000.00",
    },
  },
  money: {
    checking: "3100.00", savings: "1800.00", monthly_income: "5200.00", monthly_bills: "2650.00",
    room_for_payment: "2250.00", source: "nessie", source_label: "Balances, income and bills from Capital One Nessie (sandbox)",
  },
  market_value: {
    low: "21244.00", median: "22600.00", high: "23956.00", n_listings: 8, updated_at: "2026-10-24T12:00:00Z",
    basis: "listings", basis_label: "From 8 local listings", source: "serpapi", source_label: "Google results via SerpApi",
  },
};

const loan: Overview = {
  ...lease,
  customer: { id: "cust_07", first_name: "Sam", vehicle: "2021 Camry LE", contract_type: "loan", months_left: 30 },
  tiles: { ...lease.tiles, allowance: null, payoff_or_buyout: "12400.00", equity: "5200.00" },
  mileage: {
    ...lease.mileage,
    allowance_per_month: null,
    projection: { ...lease.mileage.projection, overage_miles: null, overage_fee: null },
  },
};

type Reply = { status?: number; body: unknown } | Error | "never";

function stubFetch(handler: (url: string) => Reply) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const reply = handler(url);
      if (reply === "never") return new Promise(() => {});
      if (reply instanceof Error) throw reply;
      const status = reply.status ?? 200;
      return { ok: status < 400, status, json: async () => reply.body };
    }),
  );
}

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const happy = (url: string): Reply => {
  if (url === "/api/customers") return { body: customers };
  if (url.endsWith("/cust_01/overview")) return { body: lease };
  if (url.endsWith("/cust_07/overview")) return { body: loan };
  return { status: 404, body: { detail: "We couldn't find that customer." } };
};

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

describe("Customer overview states", () => {
  it("labels the picker as a demo customer", () => {
    stubFetch(() => "never");
    renderApp();
    expect(screen.getByText("Demo customer")).toBeInTheDocument();
  });

  it("shows a loading state while the data is on the way", () => {
    stubFetch(() => "never");
    renderApp();
    expect(screen.getAllByRole("status")[0]).toHaveTextContent("Loading");
  });

  it("shows an empty state when there are no demo customers", async () => {
    stubFetch(() => ({ body: [] }));
    renderApp();
    expect(await screen.findByText("No demo customers are available.")).toBeInTheDocument();
    expect(screen.getByText("Pick a demo customer to see where they stand.")).toBeInTheDocument();
  });

  it("shows a readable error, not a stack trace, when the server cannot be reached", async () => {
    stubFetch(() => new TypeError("Failed to fetch"));
    renderApp();
    const alerts = await screen.findAllByRole("alert");
    expect(alerts[0]).toHaveTextContent("We couldn't reach the server");
    expect(document.body).not.toHaveTextContent("TypeError");
    expect(document.body).not.toHaveTextContent("Failed to fetch");
  });

  it("shows the server's own message when a request fails", async () => {
    stubFetch((url) =>
      url === "/api/customers"
        ? { body: customers }
        : { status: 503, body: { detail: "Customer data is temporarily unavailable. Please try again in a moment." } },
    );
    renderApp();
    expect(await screen.findByRole("alert")).toHaveTextContent("temporarily unavailable");
  });
});

describe("Customer overview", () => {
  it("shows the contract, money and market value for the first customer", async () => {
    stubFetch(happy);
    renderApp();
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Hi Maya, here's where you stand");
    expect(screen.getByText("2023 RAV4 XLE · Lease · 14 months left")).toBeInTheDocument();
    expect(screen.getByText("$389")).toBeInTheDocument();
    expect(screen.getByText("22 of 36 paid")).toBeInTheDocument();
    expect(screen.getByText("$26,896")).toBeInTheDocument();
    expect(screen.getByText("-$4,296")).toBeInTheDocument();
    expect(screen.getByText("Allowance 36,000")).toBeInTheDocument();
    expect(screen.getByText("$21,244 to $23,956")).toBeInTheDocument();
    expect(screen.getByText(/From 8 local listings.*· Google results via SerpApi/)).toBeInTheDocument();
    expect(screen.getByText("$2,250")).toBeInTheDocument();
    expect(screen.getByText("Balances, income and bills from Capital One Nessie (sandbox)")).toBeInTheDocument();
    expect(screen.getByText(/12,000 miles over allowance at lease end, about \$3,000 in fees/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See my options" })).toHaveAttribute("href", "/paths");
  });

  it("replaces everything when another customer is picked, with nothing left over", async () => {
    stubFetch(happy);
    renderApp();
    await screen.findByText("Hi Maya, here's where you stand");
    fireEvent.change(screen.getByLabelText("Demo customer"), { target: { value: "cust_07" } });
    expect(await screen.findByText("Hi Sam, here's where you stand")).toBeInTheDocument();
    expect(screen.queryByText(/Hi Maya/)).not.toBeInTheDocument();
    expect(screen.queryByText("-$4,296")).not.toBeInTheDocument();
  });

  it("shows a loan without an allowance or a made-up zero overage", async () => {
    stubFetch(happy);
    renderApp();
    await screen.findByText("Hi Maya, here's where you stand");
    fireEvent.change(screen.getByLabelText("Demo customer"), { target: { value: "cust_07" } });
    expect(await screen.findByText("No mileage allowance")).toBeInTheDocument();
    expect(screen.getByText(/no mileage allowance on a loan, so no overage fees/)).toBeInTheDocument();
    expect(screen.queryByText(/in fees/)).not.toBeInTheDocument();
  });

  it("says so when there is no odometer history, and still shows the projection", async () => {
    const noHistory: Overview = { ...lease, mileage: { ...lease.mileage, actual_monthly: [] } };
    stubFetch((url) => (url.endsWith("/overview") ? { body: noHistory } : happy(url)));
    renderApp();
    expect(await screen.findByText(/No odometer history yet, so only the projection is shown/)).toBeInTheDocument();
  });

  it("shows an empty state for spending when there is none", async () => {
    stubFetch((url) => (url.endsWith("/spending") ? { body: { months: [] } } : happy(url)));
    renderApp();
    await screen.findByText("Hi Maya, here's where you stand");
    fireEvent.click(screen.getByLabelText("Spending"));
    expect(await screen.findByText("No spending to show yet.")).toBeInTheDocument();
  });

  it("shows a readable error for spending that fails", async () => {
    stubFetch((url) => (url.endsWith("/spending") ? { status: 503, body: { detail: "Try again soon." } } : happy(url)));
    renderApp();
    await screen.findByText("Hi Maya, here's where you stand");
    fireEvent.click(screen.getByLabelText("Spending"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Try again soon.");
  });

  it("falls back to an estimate when there are no listings", async () => {
    const none: Overview = {
      ...lease,
      market_value: {
        low: null, median: "16696.06", high: null, n_listings: 0, updated_at: null, basis: "original_price",
        basis_label: "Estimated from the original price with an illustrative 12% yearly depreciation; no local listings found",
        source: "demo", source_label: "Demo data",
      },
    };
    stubFetch((url) => (url.endsWith("/overview") ? { body: none } : happy(url)));
    renderApp();
    expect(await screen.findByText("$16,696 (estimated)")).toBeInTheDocument();
    expect(screen.getByText(/illustrative 12% yearly depreciation/)).toBeInTheDocument();
  });
});
