import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import type { Explanation, PathOption, PathsResult } from "../api/client";

const customers = [{ id: "cust_01", display_name: "Maya Ortiz", vehicle_label: "RAV4 lease" }];

const option = (o: Partial<PathOption> & Pick<PathOption, "path" | "label">): PathOption => ({
  eligible: true,
  ineligible_reason: null,
  five_year_cost: "31796",
  monthly_payment: "389.00",
  upfront_cost: "0.00",
  affordable: true,
  shortfalls: [],
  tradeoff: "A trade-off line.",
  cumulative_cost: Array.from({ length: 60 }, (_, i) => String((i + 1) * 500)),
  ...o,
});

const template: Explanation = {
  headline: "Buy out: saves about $5,389 over 5 years",
  text: "Buy out is your best next move. Over 5 years it costs $25,729 in total, $5,389 less than keeping your current plan.",
  source: "template",
  verified: true,
};

const result = (over: Partial<PathsResult> = {}): PathsResult => ({
  contract_type: "lease",
  inputs_used: { miles_per_year: 14600, monthly_budget: "2250", years_to_keep: 2, financing_rate: "6.5" },
  options: [
    option({ path: "keep_as_is", label: "Keep as is", five_year_cost: "31118" }),
    option({ path: "buy_out", label: "Buy out", five_year_cost: "25729", monthly_payment: "419.69" }),
    option({
      path: "return_lease_new",
      label: "Return and lease new",
      five_year_cost: "34296",
      upfront_cost: "7296.00",
      affordable: false,
      shortfalls: [{ kind: "cash", amount: "5046.00", text: "needs $5,046 more cash upfront" }],
    }),
    option({ path: "walk_away", label: "Return and walk away", five_year_cost: "31513" }),
  ],
  recommendation: {
    path: "buy_out",
    label: "Buy out",
    runner_up: "keep_as_is",
    monthly_room_left: "1830.31",
    closest_when_none: null,
    closest_label: null,
    closest_gap: "0",
    explanation: template,
  },
  flips: [
    {
      input: "monthly_budget",
      current: "2250",
      threshold: "410",
      to_path: "keep_as_is",
      relative_change: "0.818",
      text: "If your monthly budget changed from $2,250 to $410, Keep as is would become the recommendation.",
    },
  ],
  ranges: {},
  ...over,
});

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

function renderPaths() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/paths"]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const serve =
  (paths: PathsResult, explanation: Reply = { body: template }) =>
  (url: string): Reply => {
    if (url === "/api/customers") return { body: customers };
    if (url.endsWith("/paths")) return { body: paths };
    if (url.endsWith("/explanation")) return explanation;
    return { status: 404, body: { detail: "We couldn't find that customer." } };
  };

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

describe("Your paths states", () => {
  it("shows a loading state while the paths are on the way", () => {
    stubFetch(() => "never");
    renderPaths();
    expect(screen.getAllByRole("status")[0]).toHaveTextContent("Loading");
  });

  it("asks for a customer when there are none to pick", async () => {
    stubFetch(() => ({ body: [] }));
    renderPaths();
    expect(await screen.findByText("Pick a demo customer to see their paths.")).toBeInTheDocument();
  });

  it("shows an empty state when a customer has no paths", async () => {
    stubFetch(serve(result({ options: [] })));
    renderPaths();
    expect(await screen.findByText("No paths are available for this customer.")).toBeInTheDocument();
  });

  it("shows a readable error, not a stack trace, when the server cannot be reached", async () => {
    stubFetch((url) => (url === "/api/customers" ? { body: customers } : new TypeError("Failed to fetch")));
    renderPaths();
    expect(await screen.findByRole("alert")).toHaveTextContent("We couldn't reach the server");
    expect(document.body).not.toHaveTextContent("TypeError");
  });

  it("shows the server's own message when the request fails", async () => {
    stubFetch((url) =>
      url === "/api/customers" ? { body: customers } : { status: 503, body: { detail: "Customer data is temporarily unavailable." } },
    );
    renderPaths();
    expect(await screen.findByRole("alert")).toHaveTextContent("temporarily unavailable");
  });
});

describe("Your paths", () => {
  it("shows the recommendation, a verified badge, the budget fit and what would change it", async () => {
    stubFetch(serve(result()));
    renderPaths();
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Buy out: saves about $5,389 over 5 years");
    expect(screen.getByText("Recommended next move")).toBeInTheDocument();
    expect(screen.getByText(/Over 5 years it costs \$25,729 in total/)).toBeInTheDocument();
    expect(screen.getByText("Numbers verified")).toBeInTheDocument();
    expect(screen.getByText(/Fits your budget: \$420 a month, \$1,830 room left/)).toBeInTheDocument();
    expect(screen.getByText(/If your monthly budget changed from \$2,250 to \$410/)).toBeInTheDocument();
  });

  it("lists every path with its three measures, cheapest first, and marks the recommended one", async () => {
    stubFetch(serve(result()));
    renderPaths();
    await screen.findByRole("heading", { level: 1 });
    const cards = screen.getAllByRole("article");
    expect(cards.map((c) => c.getAttribute("aria-label"))).toEqual([
      "Buy out",
      "Keep as is",
      "Return and walk away",
      "Return and lease new",
    ]);
    const buyOut = within(cards[0]);
    expect(buyOut.getByText("Recommended")).toBeInTheDocument();
    expect(buyOut.getByText("$25,729")).toBeInTheDocument();
    expect(buyOut.getByText("$420")).toBeInTheDocument();
    expect(cards[0]).toHaveClass("card-recommended");
    expect(within(cards[1]).queryByText("Recommended")).not.toBeInTheDocument();
  });

  it("keeps an unaffordable path visible with the exact reason", async () => {
    stubFetch(serve(result()));
    renderPaths();
    const card = await screen.findByRole("article", { name: "Return and lease new" });
    expect(within(card).getByText("needs $5,046 more cash upfront")).toBeInTheDocument();
    expect(within(card).queryByText("Recommended")).not.toBeInTheDocument();
  });

  it("shows a path the customer is not eligible for as dashed, with its reason", async () => {
    const loan = result({
      contract_type: "loan",
      options: [
        option({ path: "keep_as_is", label: "Keep as is", five_year_cost: "13543" }),
        option({
          path: "refinance",
          label: "Refinance",
          five_year_cost: "13306",
          eligible: false,
          ineligible_reason: "Your current rate is already lower than this refinance rate.",
        }),
      ],
      recommendation: { ...result().recommendation, path: "keep_as_is", label: "Keep as is" },
    });
    stubFetch(serve(loan));
    renderPaths();
    const card = await screen.findByRole("article", { name: "Refinance" });
    expect(card).toHaveClass("card-ineligible");
    expect(within(card).getByText("Not eligible")).toBeInTheDocument();
    expect(within(card).getByText("Your current rate is already lower than this refinance rate.")).toBeInTheDocument();
  });

  it("says so when nothing is affordable and points to the closest path", async () => {
    const none = result({
      options: result().options.map((o) => ({
        ...o,
        affordable: false,
        shortfalls: [{ kind: "cash" as const, amount: "700.00", text: "needs $700 more cash upfront" }],
      })),
      recommendation: {
        ...result().recommendation,
        path: null,
        label: null,
        runner_up: null,
        closest_when_none: "keep_as_is",
        closest_label: "Keep as is",
        closest_gap: "700.00",
        explanation: {
          headline: "No path fits your budget and cash yet",
          text: "None of your paths fit your budget and cash right now. Keep as is comes closest, and it is short by $700.",
          source: "template",
          verified: true,
        },
      },
    });
    stubFetch(serve(none));
    renderPaths();
    expect(await screen.findByText("No path fits yet")).toBeInTheDocument();
    expect(screen.getByText(/None of your paths fit your budget and cash right now/)).toBeInTheDocument();
    expect(screen.queryByText("Recommended")).not.toBeInTheDocument();
    expect(screen.queryByText(/Fits your budget/)).not.toBeInTheDocument();
    expect(within(screen.getByRole("article", { name: "Keep as is" })).getByText("Closest")).toBeInTheDocument();
    // there is no recommendation to hold steady, so it must not claim one does
    expect(screen.getByText(/There is no recommendation yet/)).toBeInTheDocument();
    expect(screen.queryByText(/holds across every setting/)).not.toBeInTheDocument();
  });

  it("says the recommendation is stable when no input would flip it", async () => {
    stubFetch(serve(result({ flips: [] })));
    renderPaths();
    expect(await screen.findByText("Your recommendation holds across every setting of the sliders.")).toBeInTheDocument();
  });
});

describe("Your paths explanation", () => {
  const model: Explanation = {
    headline: "Buy out comes out ahead",
    text: "Buy out costs $25,729 over 5 years, $5,389 less than keeping your current plan.",
    source: "gemini",
    verified: true,
  };

  it("shows the checked template at once and swaps in the model's wording when it arrives verified", async () => {
    stubFetch(serve(result(), { body: model }));
    renderPaths();
    expect(await screen.findByRole("heading", { level: 1 })).toBeInTheDocument();
    expect(await screen.findByText("Buy out comes out ahead")).toBeInTheDocument();
    expect(screen.queryByText("Buy out: saves about $5,389 over 5 years")).not.toBeInTheDocument();
  });

  it("keeps the template, with no error, when the model request fails", async () => {
    stubFetch(serve(result(), { status: 500, body: { detail: "boom" } }));
    renderPaths();
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Buy out: saves about $5,389 over 5 years");
    await vi.waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([u]) => String(u).endsWith("/explanation"))).toBe(true));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText("Numbers verified")).toBeInTheDocument();
  });

  it("ignores model wording that did not pass the number check", async () => {
    stubFetch(serve(result(), { body: { ...model, verified: false } }));
    renderPaths();
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Buy out: saves about $5,389 over 5 years");
    await vi.waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([u]) => String(u).endsWith("/explanation"))).toBe(true));
    expect(screen.queryByText("Buy out comes out ahead")).not.toBeInTheDocument();
  });

  it("falls back to the template when the model's answer is itself the template", async () => {
    stubFetch(serve(result(), { body: template }));
    renderPaths();
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Buy out: saves about $5,389 over 5 years");
  });
});
