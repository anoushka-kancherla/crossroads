import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
  ranges: {
    miles_per_year: { min: "5000", max: "25000", step: "100" },
    monthly_budget: { min: "200", max: "2250", step: "10" },
    years_to_keep: { min: "1", max: "8", step: "1" },
    financing_rate: { min: "3", max: "12", step: "0.25" },
  },
  assumptions: ["A car you give up before the five years are up is replaced by a lease at $450 a month with $3,000 due at signing (illustrative)."],
  ...over,
});

type Reply = { status?: number; body: unknown } | Error | "never";

function stubFetch(handler: (url: string, init?: RequestInit) => Reply) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const reply = handler(url, init);
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
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([u]) => String(u).endsWith("/explanation"))).toBe(true));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText("Numbers verified")).toBeInTheDocument();
  });

  it("ignores model wording that did not pass the number check", async () => {
    stubFetch(serve(result(), { body: { ...model, verified: false } }));
    renderPaths();
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Buy out: saves about $5,389 over 5 years");
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([u]) => String(u).endsWith("/explanation"))).toBe(true));
    expect(screen.queryByText("Buy out comes out ahead")).not.toBeInTheDocument();
  });

  it("falls back to the template when the model's answer is itself the template", async () => {
    stubFetch(serve(result(), { body: template }));
    renderPaths();
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Buy out: saves about $5,389 over 5 years");
  });
});

// --- sliders, reset, and the assumptions (T056, T057, T059) ---

const bodyOf = (init?: RequestInit) => JSON.parse(String(init?.body ?? "{}"));
const pathsCalls = () =>
  vi.mocked(fetch).mock.calls.filter(([u]) => String(u).endsWith("/paths")).map(([, init]) => bodyOf(init));

const moved = (miles: number): PathsResult =>
  result({
    inputs_used: { miles_per_year: miles, monthly_budget: "2250", years_to_keep: 2, financing_rate: "6.5" },
    recommendation: { ...result().recommendation, explanation: { ...template, headline: "Keep as is: stays your best move" } },
  });

describe("Your paths sliders", () => {
  it("starts the four inputs at the customer's own defaults, with the server's ranges", async () => {
    stubFetch(serve(result()));
    renderPaths();
    const miles = (await screen.findByLabelText("Miles per year")) as HTMLInputElement;
    expect([miles.value, miles.min, miles.max, miles.step]).toEqual(["14600", "5000", "25000", "100"]);
    const budget = screen.getByLabelText("Monthly budget") as HTMLInputElement;
    expect([budget.value, budget.min, budget.max, budget.step]).toEqual(["2250", "200", "2250", "10"]);
    expect((screen.getByLabelText("Years you plan to keep a car") as HTMLInputElement).value).toBe("2");
    const rate = screen.getByLabelText("Financing rate") as HTMLInputElement;
    expect([rate.value, rate.min, rate.max, rate.step]).toEqual(["6.5", "3", "12", "0.25"]);
  });

  it("shows each value in words a customer reads, with the range ends under the slider", async () => {
    stubFetch(serve(result()));
    renderPaths();
    await screen.findByLabelText("Miles per year");
    const panel = within(screen.getByRole("region", { name: "Adjust your situation" }));
    expect(panel.getByText("14,600")).toBeInTheDocument();
    expect(panel.getByText("6.5%")).toBeInTheDocument();
    expect(panel.getAllByText("$2,250").length).toBeGreaterThan(0);
    expect(panel.getByText("25,000")).toBeInTheDocument();
  });

  it("calls the rate a refinance rate for a loan customer", async () => {
    stubFetch(serve(result({ contract_type: "loan" })));
    renderPaths();
    expect(await screen.findByLabelText("Refinance rate")).toBeInTheDocument();
    expect(screen.queryByLabelText("Financing rate")).not.toBeInTheDocument();
  });

  it("sends all four inputs after a short pause and swaps in the new results", async () => {
    stubFetch((url, init) => {
      if (url.endsWith("/paths") && bodyOf(init).miles_per_year === 20000) return { body: moved(20000) };
      return serve(result())(url);
    });
    renderPaths();
    const miles = await screen.findByLabelText("Miles per year");
    fireEvent.change(miles, { target: { value: "20000" } });
    expect((miles as HTMLInputElement).value).toBe("20000"); // the slider answers at once
    expect(await screen.findByText("Keep as is: stays your best move")).toBeInTheDocument();
    expect(pathsCalls().at(-1)).toEqual({ miles_per_year: 20000, monthly_budget: 2250, years_to_keep: 2, financing_rate: 6.5 });
  });

  it("does not send a request for every step of a drag", async () => {
    stubFetch(serve(result()));
    renderPaths();
    const miles = await screen.findByLabelText("Miles per year");
    const before = pathsCalls().length;
    for (const v of ["15000", "16000", "17000", "18000"]) fireEvent.change(miles, { target: { value: v } });
    await waitFor(() => expect(pathsCalls().length).toBe(before + 1));
    expect(pathsCalls().at(-1)?.miles_per_year).toBe(18000);
    await waitFor(() => expect(screen.queryByText("Updating…")).not.toBeInTheDocument()); // let it settle
  });

  it("returns to the customer's own data when reset", async () => {
    stubFetch((url, init) => {
      if (url.endsWith("/paths") && bodyOf(init).miles_per_year === 20000) return { body: moved(20000) };
      return serve(result())(url);
    });
    renderPaths();
    fireEvent.change(await screen.findByLabelText("Miles per year"), { target: { value: "20000" } });
    await screen.findByText("Keep as is: stays your best move");
    fireEvent.click(screen.getByRole("button", { name: "Reset to my data" }));
    expect(await screen.findByText("Buy out: saves about $5,389 over 5 years")).toBeInTheDocument();
    expect(pathsCalls().at(-1)).toEqual({});
    expect((screen.getByLabelText("Miles per year") as HTMLInputElement).value).toBe("14600");
  });

  it("keeps the previous results and says why when the server rejects an input", async () => {
    stubFetch((url, init) => {
      if (url.endsWith("/paths") && bodyOf(init).miles_per_year === 20000) {
        return { status: 422, body: { detail: "Miles per year: Input should be a multiple of 100" } };
      }
      return serve(result())(url);
    });
    renderPaths();
    fireEvent.change(await screen.findByLabelText("Miles per year"), { target: { value: "20000" } });
    expect(await screen.findByRole("alert")).toHaveTextContent("Miles per year: Input should be a multiple of 100");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Buy out: saves about $5,389 over 5 years");
    expect(screen.getAllByRole("article").length).toBe(4);
  });

  it("starts again from the next customer's own defaults", async () => {
    const two = [...customers, { id: "cust_07", display_name: "Sam Lee", vehicle_label: "Camry loan" }];
    stubFetch((url, init) => {
      if (url === "/api/customers") return { body: two };
      if (url.endsWith("/cust_07/paths")) return { body: moved(11000) };
      if (url.endsWith("/cust_01/paths") && bodyOf(init).miles_per_year === 20000) return { body: moved(20000) };
      return serve(result())(url);
    });
    renderPaths();
    fireEvent.change(await screen.findByLabelText("Miles per year"), { target: { value: "20000" } });
    await screen.findByText("Keep as is: stays your best move");
    fireEvent.change(screen.getByLabelText("Demo customer"), { target: { value: "cust_07" } });
    await waitFor(() => expect((screen.getByLabelText("Miles per year") as HTMLInputElement).value).toBe("11000"));
    const forSam = vi.mocked(fetch).mock.calls.filter(([u]) => String(u).endsWith("/cust_07/paths"));
    expect(forSam.map(([, init]) => bodyOf(init))).toEqual([{}]); // defaults, not the first customer's 20,000
    await waitFor(() => expect(screen.queryByText("Updating…")).not.toBeInTheDocument()); // let it settle
  });
});

describe("Your paths assumptions", () => {
  it("shows the illustrative values behind the numbers", async () => {
    stubFetch(serve(result()));
    renderPaths();
    const section = await screen.findByRole("region", { name: "Assumptions behind these numbers" });
    expect(within(section).getByText(/\$450 a month with \$3,000 due at signing \(illustrative\)/)).toBeInTheDocument();
  });
});
