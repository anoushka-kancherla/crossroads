import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { retryHint, type Portfolio } from "../api/client";

const LABELS: [string, string, boolean][] = [
  ["keep_as_is", "Keep as is", true],
  ["buy_out", "Buy out", true],
  ["return_lease_new", "Return and lease new", true],
  ["trade_in_early", "Trade in early", true],
  ["refinance", "Refinance", true],
  ["extra_principal", "Pay extra principal", true],
  ["walk_away", "Return and walk away", false],
];

const STEP: Record<string, string> = {
  keep_as_is: "self_service", extra_principal: "self_service", buy_out: "eligible_offer",
  refinance: "eligible_offer", return_lease_new: "specialist_follow_up", trade_in_early: "specialist_follow_up",
  walk_away: "specialist_follow_up",
};
const STEP_LABEL: Record<string, string> = {
  self_service: "Self-service", eligible_offer: "Eligible offer", specialist_follow_up: "Specialist follow-up",
};

const portfolio: Portfolio = {
  empty: false,
  computed_at: "2026-10-24T12:00:00Z",
  customers_total: 12,
  no_recommendation: 1,
  kpis: {
    retained_count: 9,
    retained_pct: "75",
    revenue_total: "58211.40",
    avg_savings: "2150",
    explanations_verified_pct: "100",
  },
  by_path: LABELS.map(([path, label, stays], i) => ({
    path: path as Portfolio["by_path"][number]["path"],
    label,
    customers: i === 1 ? 4 : i === 6 ? 1 : 0,
    share_pct: "0",
    stays_with_toyota: stays,
    stays_label: path === "buy_out" ? "Yes (Toyota loan)" : stays ? "Yes" : "No",
    next_step: STEP[path] as Portfolio["next_steps"][number]["step"],
    next_step_label: STEP_LABEL[STEP[path]],
    revenue: path === "buy_out" ? "58211.40" : "0",
  })),
  next_steps: [
    { step: "self_service", label: "Self-service", customers: 5, share_pct: "42" },
    { step: "eligible_offer", label: "Eligible offer", customers: 4, share_pct: "33" },
    { step: "specialist_follow_up", label: "Specialist follow-up", customers: 2, share_pct: "17" },
  ],
  self_service_pct: "42",
  assumptions: ["A customer is retained when the recommended path keeps a Toyota contract.", "Values are illustrative."],
};

const empty: Portfolio = { ...portfolio, empty: true, customers_total: 0, computed_at: null };

type Reply = { status?: number; body?: unknown; headers?: Record<string, string> } | Error | "never";
type Routes = Partial<Record<string, Reply | (() => Reply)>>;

/** Stubs fetch; the key is "METHOD path". Every call is recorded so a test can say what was never requested. */
const QUIET_LIVE = {
  accepted_customers: 0, customers_total: 12, retained_customers: 0, retained_pct: null,
  revenue_total: "0", sequence: 0, updated_at: "2026-10-25T12:00:00Z",
};

function stubFetch(routes: Routes) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${url}`;
      calls.push(key);
      const entry = routes[key] ?? (key === "GET /api/internal/live" ? { body: QUIET_LIVE } : undefined);
      const reply = typeof entry === "function" ? entry() : entry;
      if (reply === undefined) throw new Error(`unexpected request ${key}`);
      if (reply === "never") return new Promise(() => {});
      if (reply instanceof Error) throw reply;
      const status = reply.status ?? 200;
      const headers = { get: (name: string) => reply.headers?.[name] ?? null };
      return { ok: status < 400, status, headers, json: async () => reply.body };
    }),
  );
  return calls;
}

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const signedIn = { body: { user: "staff" } };
const unauthorized = { status: 401, body: { detail: "Please sign in." } };

function signIn(user = "staff", password = "typed-in-the-test") {
  fireEvent.change(screen.getByLabelText("Username"), { target: { value: user } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: password } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
}

afterEach(() => vi.unstubAllGlobals());

describe("portfolio dashboard", () => {
  it("shows a loading state while the session is checked", () => {
    stubFetch({ "GET /api/internal/session": "never" });
    renderApp();
    expect(screen.getByRole("status")).toHaveTextContent("Loading");
  });

  it("shows a loading state while the portfolio loads", async () => {
    stubFetch({ "GET /api/internal/session": signedIn, "GET /api/internal/portfolio": "never" });
    renderApp();
    expect(await screen.findByText("Signed in as staff")).toBeInTheDocument();
    // the live panel loads beside the portfolio, so more than one status can be on screen
    expect(screen.getAllByRole("status").some((el) => /Loading/.test(el.textContent ?? ""))).toBe(true);
  });

  it("shows the sign-in form, and asks for no portfolio, when there is no session", async () => {
    const calls = stubFetch({ "GET /api/internal/session": unauthorized });
    renderApp();
    expect(await screen.findByRole("form", { name: "Staff sign-in" })).toBeInTheDocument();
    expect(calls).toEqual(["GET /api/internal/session"]);
    expect(screen.queryByText("Sign out")).not.toBeInTheDocument();
  });

  it("shows an empty state, with Refresh still available, before anything is computed", async () => {
    stubFetch({ "GET /api/internal/session": signedIn, "GET /api/internal/portfolio": { body: empty } });
    renderApp();
    expect(await screen.findByText(/No recommendations yet/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Refresh" })).toBeEnabled();
  });

  it("shows a readable error when the portfolio cannot be loaded", async () => {
    stubFetch({
      "GET /api/internal/session": signedIn,
      "GET /api/internal/portfolio": { status: 503, body: { detail: "The data is not available right now." } },
    });
    renderApp();
    expect(await screen.findByRole("alert")).toHaveTextContent("The data is not available right now.");
  });

  it("shows a readable error when the server cannot be reached", async () => {
    stubFetch({ "GET /api/internal/session": signedIn, "GET /api/internal/portfolio": new Error("boom") });
    renderApp();
    expect(await screen.findByRole("alert")).toHaveTextContent("couldn't reach the server");
    expect(screen.queryByText(/boom/)).not.toBeInTheDocument();
  });

  it("shows the four figures, all seven paths and the assumptions", async () => {
    stubFetch({ "GET /api/internal/session": signedIn, "GET /api/internal/portfolio": { body: portfolio } });
    renderApp();
    expect(await screen.findByText("Customers retained")).toBeInTheDocument();
    expect(screen.getByText("75%")).toBeInTheDocument();
    expect(screen.getByText("Est. revenue kept").nextSibling).toHaveTextContent("$58,211");
    expect(screen.getByText("Avg. savings · 11 customers with an affordable option").nextSibling).toHaveTextContent(
      "$2,150",
    );
    expect(screen.getByText("Explanations verified").nextSibling).toHaveTextContent("100%");
    expect(screen.getByText(/Across 12 synthetic customers/)).toHaveTextContent("Oct 24, 2026");

    const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(7);
    expect(within(rows[1]).getByText("Yes (Toyota loan)")).toBeInTheDocument();
    expect(within(rows[6]).getByText("No")).toBeInTheDocument();
    expect(screen.queryByText(/default risk/i)).not.toBeInTheDocument();
    expect(screen.getByText("1 customer with no affordable path.")).toBeInTheDocument();
    expect(screen.getByText("Values are illustrative.")).toBeInTheDocument();
  });

  it("shows how many recommendations need no specialist, and each path's next step", async () => {
    stubFetch({ "GET /api/internal/session": signedIn, "GET /api/internal/portfolio": { body: portfolio } });
    renderApp();
    const tile = (await screen.findByText("Need no specialist")).parentElement as HTMLElement;
    expect(tile).toHaveTextContent("42%");
    expect(tile).toHaveTextContent("5 self-service · 4 eligible offer · 2 specialist follow-up");
    const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    expect(within(rows[1]).getByText("Eligible offer")).toBeInTheDocument();
    expect(within(rows[5]).getByText("Self-service")).toBeInTheDocument();
    expect(within(rows[6]).getByText("Specialist follow-up")).toBeInTheDocument();
  });

  it("returns to sign-in with no figures left when the session ends mid-use", async () => {
    stubFetch({ "GET /api/internal/session": signedIn, "GET /api/internal/portfolio": unauthorized });
    renderApp();
    expect(await screen.findByRole("form", { name: "Staff sign-in" })).toBeInTheDocument();
    expect(screen.queryByText("Customers retained")).not.toBeInTheDocument();
    expect(screen.queryByText("Sign out")).not.toBeInTheDocument();
  });

  it("clears the figures and returns to sign-in on sign out", async () => {
    const calls = stubFetch({
      "GET /api/internal/session": signedIn,
      "GET /api/internal/portfolio": { body: portfolio },
      "POST /api/internal/logout": { status: 204 },
    });
    renderApp();
    await screen.findByText("Customers retained");
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("form", { name: "Staff sign-in" })).toBeInTheDocument();
    expect(screen.queryByText("Customers retained")).not.toBeInTheDocument();
    expect(calls).toContain("POST /api/internal/logout");
  });

  it("replaces the figures when Refresh recomputes them", async () => {
    const later = { ...portfolio, kpis: { ...portfolio.kpis, retained_pct: "83" } };
    stubFetch({
      "GET /api/internal/session": signedIn,
      "GET /api/internal/portfolio": { body: portfolio },
      "POST /api/internal/portfolio/refresh": { body: later },
    });
    renderApp();
    await screen.findByText("75%");
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    expect(await screen.findByText("83%")).toBeInTheDocument();
    expect(screen.queryByText("75%")).not.toBeInTheDocument();
  });

  it("keeps the old figures and says so when Refresh fails", async () => {
    stubFetch({
      "GET /api/internal/session": signedIn,
      "GET /api/internal/portfolio": { body: portfolio },
      "POST /api/internal/portfolio/refresh": { status: 503, body: { detail: "The data is not available right now." } },
    });
    renderApp();
    await screen.findByText("75%");
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The data is not available right now.");
    expect(screen.getByText("75%")).toBeInTheDocument();
  });
});

describe("staff sign-in", () => {
  it("shows one generic message for a failed sign-in, and nothing about which part was wrong", async () => {
    stubFetch({
      "GET /api/internal/session": unauthorized,
      "POST /api/internal/login": { status: 401, body: { detail: "Invalid credentials" } },
    });
    renderApp();
    await screen.findByRole("form", { name: "Staff sign-in" });
    signIn("staff", "not-the-password");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Invalid credentials");
    expect(alert).not.toHaveTextContent(/username|password/i);
  });

  it("shows the dashboard after a successful sign-in", async () => {
    let signed = false;
    stubFetch({
      "GET /api/internal/session": () => (signed ? signedIn : unauthorized),
      "POST /api/internal/login": () => {
        signed = true;
        return { status: 204 };
      },
      "GET /api/internal/portfolio": { body: portfolio },
    });
    renderApp();
    await screen.findByRole("form", { name: "Staff sign-in" });
    signIn();
    expect(await screen.findByText("Customers retained")).toBeInTheDocument();
    expect(screen.getByText("Signed in as staff")).toBeInTheDocument();
  });

  it("says so, in plain words, when too many attempts have locked the address", async () => {
    stubFetch({
      "GET /api/internal/session": unauthorized,
      "POST /api/internal/login": {
        status: 429,
        body: { detail: "Too many attempts. Please try again later." },
        headers: { "Retry-After": "900" },
      },
    });
    renderApp();
    await screen.findByRole("form", { name: "Staff sign-in" });
    signIn("staff", "x");
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Too many attempts. Please try again later. Try again in 15 minutes.",
    );
  });

  it("counts the delay down to seconds, and copes with a missing Retry-After", () => {
    expect(retryHint("45")).toBe("Try again in 45 seconds.");
    expect(retryHint("60")).toBe("Try again in 1 minute.");
    expect(retryHint("61")).toBe("Try again in 2 minutes.");
    expect(retryHint(null)).toBe("");
    expect(retryHint("soon")).toBe("");
  });

  it("says when sign-in is not set up", async () => {
    stubFetch({
      "GET /api/internal/session": unauthorized,
      "POST /api/internal/login": { status: 503, body: { detail: "Staff sign-in isn't set up yet." } },
    });
    renderApp();
    await screen.findByRole("form", { name: "Staff sign-in" });
    signIn("staff", "x");
    expect(await screen.findByRole("alert")).toHaveTextContent("isn't set up");
  });
});
