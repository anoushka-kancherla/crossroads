import { QueryClient, QueryClientProvider, focusManager } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { LiveFigures } from "../api/client";
import { LivePanel } from "./LivePanel";

const live = (over: Partial<LiveFigures> = {}): LiveFigures => ({
  accepted_customers: 0,
  customers_total: 12,
  retained_customers: 0,
  retained_pct: null,
  revenue_total: "0",
  sequence: 0,
  updated_at: "2026-10-25T12:00:00Z",
  ...over,
});

type Reply = { status?: number; body: unknown } | Error;
let replies: Reply[];
let fetchFn: ReturnType<typeof vi.fn>;

function stub() {
  fetchFn = vi.fn(async () => {
    const r = replies.length > 1 ? replies.shift()! : replies[0];
    if (r instanceof Error) throw r;
    const status = r.status ?? 200;
    return { ok: status < 400, status, json: async () => r.body, headers: new Headers() };
  });
  vi.stubGlobal("fetch", fetchFn);
}

function renderPanel() {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <LivePanel />
    </QueryClientProvider>,
  );
}

const tick = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });

beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: false }));
afterEach(() => {
  focusManager.setFocused(undefined);
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("LivePanel", () => {
  it("shows a loading state, then the figures with the time they were read", async () => {
    replies = [{ body: live({ accepted_customers: 3, retained_customers: 2, retained_pct: "67", revenue_total: "1500.50", sequence: 3 }) }];
    stub();
    renderPanel();
    expect(screen.getByRole("status")).toHaveTextContent("Loading");
    await tick(0);
    expect(screen.getByText("3 of 12")).toBeInTheDocument();
    expect(screen.getByText("67%")).toBeInTheDocument();
    expect(screen.getByText("$1,501")).toBeInTheDocument();
    expect(screen.getByText(/Updated at/)).toBeInTheDocument();
  });

  it("says nothing has been accepted yet instead of showing a retention number", async () => {
    replies = [{ body: live() }];
    stub();
    renderPanel();
    await tick(0);
    expect(screen.getByText(/No one has accepted a path yet/)).toBeInTheDocument();
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
  });

  it("asks again every 3 seconds and shows a change without a reload", async () => {
    replies = [
      { body: live() },
      { body: live({ accepted_customers: 1, retained_customers: 1, retained_pct: "100", revenue_total: "900", sequence: 1 }) },
    ];
    stub();
    renderPanel();
    await tick(0);
    expect(fetchFn).toHaveBeenCalledTimes(1);
    await tick(2900);
    expect(fetchFn).toHaveBeenCalledTimes(1);
    await tick(200);
    expect(fetchFn).toHaveBeenCalledTimes(2);
    expect(screen.getByText("100%")).toBeInTheDocument();
    expect(screen.getByText("1 of 12")).toBeInTheDocument();
  });

  it("keeps the last figures and warns when a refresh fails, then recovers", async () => {
    replies = [
      { body: live({ accepted_customers: 2, retained_customers: 2, retained_pct: "100", sequence: 2 }) },
      { status: 503, body: { detail: "We can't load the live figures right now." } },
      { body: live({ accepted_customers: 4, retained_customers: 3, retained_pct: "75", sequence: 4 }) },
    ];
    stub();
    renderPanel();
    await tick(0);
    await tick(3100);
    expect(screen.getByText("2 of 12")).toBeInTheDocument();
    expect(screen.getByText(/Live figures are paused/)).toBeInTheDocument();
    await tick(3100);
    expect(screen.queryByText(/Live figures are paused/)).not.toBeInTheDocument();
    expect(screen.getByText("4 of 12")).toBeInTheDocument();
  });

  it("shows an error, not figures, when the first read fails", async () => {
    replies = [{ status: 503, body: { detail: "We can't load the live figures right now." } }];
    stub();
    renderPanel();
    await tick(0);
    expect(screen.getByRole("alert")).toHaveTextContent("We can't load the live figures right now.");
  });

  it("ignores an older answer that arrives after a newer one", async () => {
    replies = [
      { body: live({ accepted_customers: 5, retained_customers: 4, retained_pct: "80", sequence: 5 }) },
      { body: live({ accepted_customers: 4, retained_customers: 4, retained_pct: "100", sequence: 4 }) },
    ];
    stub();
    renderPanel();
    await tick(0);
    await tick(3100);
    expect(fetchFn).toHaveBeenCalledTimes(2);
    expect(screen.getByText("5 of 12")).toBeInTheDocument();
    expect(screen.queryByText("4 of 12")).not.toBeInTheDocument();
  });

  it("stops asking while the tab is hidden and asks again when it comes back", async () => {
    replies = [{ body: live() }];
    stub();
    focusManager.setFocused(false); // the same switch the browser flips when the tab is hidden
    renderPanel();
    await tick(0);
    const before = fetchFn.mock.calls.length;
    await tick(10000);
    expect(fetchFn.mock.calls.length).toBe(before);
    await act(async () => {
      focusManager.setFocused(true);
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(fetchFn.mock.calls.length).toBeGreaterThan(before);
  });

  it("asks staff to sign in again when the session has ended", async () => {
    replies = [{ status: 401, body: { detail: "Please sign in." } }];
    stub();
    renderPanel();
    await tick(0);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByText(/of 12/)).not.toBeInTheDocument();
  });
});
