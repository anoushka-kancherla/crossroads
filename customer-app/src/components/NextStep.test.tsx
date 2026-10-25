import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Dealers, NextStepRequest } from "../api/client";
import { NextStep } from "./NextStep";

const dealers: Dealers = {
  dealers: [
    { name: "Toyota of Plano", address: "6888 State Hwy 121, Plano, TX 75024", hours: "Open · Closes 9 PM", rating: 4.5, distance_miles: 1.2 },
    { name: "Longo Toyota of Prosper", address: "2100 W University Dr, Prosper, TX 75078", hours: null, rating: null, distance_miles: 14.5 },
  ],
};

type Reply = { status?: number; body: unknown } | Error | "never";

/** Stubs fetch for the two calls the component makes and records every request. */
function stub(nextStep: Reply, dealerReply: Reply) {
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    const reply = url.endsWith("/next-step") ? nextStep : dealerReply;
    if (reply === "never") return new Promise(() => {});
    if (reply instanceof Error) throw reply;
    const status = reply.status ?? 200;
    return { ok: status < 400, status, json: async () => reply.body, init };
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

const confirmed = (text = "You chose Buy out. A Toyota Financial Services specialist will contact you with the next steps.") => ({
  body: { path_label: "Buy out", confirmation: text, step_type: "eligible_offer", step_label: "Eligible offer" },
});

function renderStep(path: NextStepRequest["path"] | null = "buy_out", inputs?: NextStepRequest["inputs"]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <NextStep customerId="cust_01" path={path} inputs={inputs} />
    </QueryClientProvider>,
  );
}

const sent = (fn: ReturnType<typeof stub>) =>
  fn.mock.calls.filter(([u]) => String(u).endsWith("/next-step")).map(([, init]) => JSON.parse(String(init?.body)));

afterEach(() => vi.unstubAllGlobals());

describe("NextStep", () => {
  it("offers the next step for the recommended path and a specialist", () => {
    stub(confirmed(), { body: dealers });
    renderStep("buy_out");
    expect(screen.getByRole("button", { name: "Start buyout" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Talk to a specialist" })).toBeInTheDocument();
  });

  it("asks for nothing, not even dealers, until a choice is made", () => {
    const fn = stub(confirmed(), { body: dealers });
    renderStep();
    expect(fn).not.toHaveBeenCalled();
    expect(screen.queryByText("Toyota dealers near you")).not.toBeInTheDocument();
  });

  it("sends the chosen path as a primary step and shows the confirmation and the dealers", async () => {
    const fn = stub(confirmed(), { body: dealers });
    renderStep("buy_out");
    fireEvent.click(screen.getByRole("button", { name: "Start buyout" }));
    expect(await screen.findByText(/You chose Buy out/)).toBeInTheDocument();
    expect(sent(fn)).toEqual([{ path: "buy_out", kind: "primary" }]);
    expect(screen.getByText("Next step type: Eligible offer")).toBeInTheDocument();
    expect(await screen.findByText("Toyota of Plano")).toBeInTheDocument();
    expect(screen.getByText("Open · Closes 9 PM · Rated 4.5 · 1.2 miles away")).toBeInTheDocument();
    expect(screen.getByText("14.5 miles away")).toBeInTheDocument(); // no hours or rating: nothing made up
    expect(screen.getByText("Toyota dealers near you")).toBeInTheDocument();
  });

  it("sends the slider values that produced the recommendation with the primary step only", async () => {
    const inputs = { monthly_budget: "600", annual_miles: 12000 };
    const fn = stub(confirmed(), { body: dealers });
    renderStep("buy_out", inputs);
    fireEvent.click(screen.getByRole("button", { name: "Start buyout" }));
    await screen.findByText(/You chose Buy out/);
    expect(sent(fn)).toEqual([{ path: "buy_out", kind: "primary", inputs }]);
  });

  it("does not send the slider values with 'Talk to a specialist'", async () => {
    const fn = stub(confirmed("A Toyota Financial Services specialist will contact you."), { body: dealers });
    renderStep("buy_out", { monthly_budget: "600" });
    fireEvent.click(screen.getByRole("button", { name: "Talk to a specialist" }));
    await screen.findByText(/specialist will contact you/);
    expect(sent(fn)).toEqual([{ path: "buy_out", kind: "specialist" }]);
  });

  it("sends 'Talk to a specialist' as its own kind", async () => {
    const fn = stub(confirmed("A Toyota Financial Services specialist will contact you."), { body: dealers });
    renderStep("buy_out");
    fireEvent.click(screen.getByRole("button", { name: "Talk to a specialist" }));
    expect(await screen.findByText(/specialist will contact you/)).toBeInTheDocument();
    expect(sent(fn)).toEqual([{ path: "buy_out", kind: "specialist" }]);
  });

  it("words the next step for staying on the current plan", () => {
    stub(confirmed(), { body: dealers });
    renderStep("keep_as_is");
    expect(screen.getByRole("button", { name: "Stay on my current plan" })).toBeInTheDocument();
  });

  it("offers only the specialist when nothing is recommended", async () => {
    const fn = stub(confirmed("A Toyota Financial Services specialist will contact you."), { body: dealers });
    renderStep(null);
    expect(screen.queryByRole("button", { name: /Start|Stay|Set up|Plan/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Talk to a specialist" }));
    await screen.findByText(/specialist will contact you/);
    expect(sent(fn)).toEqual([{ path: "keep_as_is", kind: "specialist" }]);
  });

  it("shows the confirmation even when the dealer request fails", async () => {
    stub(confirmed(), { status: 503, body: { detail: "We couldn't load nearby dealers right now." } });
    renderStep();
    fireEvent.click(screen.getByRole("button", { name: "Start buyout" }));
    expect(await screen.findByText(/You chose Buy out/)).toBeInTheDocument();
    expect(await screen.findByRole("alert")).toHaveTextContent("We couldn't load nearby dealers right now.");
  });

  it("shows a readable error, not a stack trace, when the dealer service cannot be reached", async () => {
    stub(confirmed(), new TypeError("Failed to fetch"));
    renderStep();
    fireEvent.click(screen.getByRole("button", { name: "Start buyout" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("We couldn't reach the server");
    expect(document.body).not.toHaveTextContent("TypeError");
    expect(screen.getByText(/You chose Buy out/)).toBeInTheDocument();
  });

  it("shows a loading state for the dealers while the confirmation is already there", async () => {
    stub(confirmed(), "never");
    renderStep();
    fireEvent.click(screen.getByRole("button", { name: "Start buyout" }));
    expect(await screen.findByText(/You chose Buy out/)).toBeInTheDocument();
    expect(await screen.findByRole("status")).toHaveTextContent("Loading");
  });

  it("shows an empty state when no dealers are found", async () => {
    stub(confirmed(), { body: { dealers: [] } });
    renderStep();
    fireEvent.click(screen.getByRole("button", { name: "Start buyout" }));
    expect(await screen.findByText("No Toyota dealers found near you.")).toBeInTheDocument();
  });

  it("shows a readable error and no dealers when the confirmation itself fails", async () => {
    const fn = stub({ status: 422, body: { detail: "That is not one of your options." } }, { body: dealers });
    renderStep();
    fireEvent.click(screen.getByRole("button", { name: "Start buyout" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("That is not one of your options.");
    await waitFor(() => expect(fn).toHaveBeenCalledTimes(1));
    expect(screen.queryByText("Toyota dealers near you")).not.toBeInTheDocument();
  });
});
