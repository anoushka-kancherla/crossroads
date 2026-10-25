import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PathsInputs } from "../api/client";
import { AskBox } from "./AskBox";

type Reply = { status?: number; body: unknown; headers?: Record<string, string> } | Error | "never";

function stub(reply: Reply) {
  const fn = vi.fn(async (...args: [string, RequestInit?]) => {
    void args;
    if (reply === "never") return new Promise(() => {});
    if (reply instanceof Error) throw reply;
    const status = reply.status ?? 200;
    return {
      ok: status < 400,
      status,
      headers: { get: (n: string) => reply.headers?.[n] ?? null },
      json: async () => reply.body,
    };
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

const inputs = { miles_per_year: 14600, monthly_budget: "2250", years_to_keep: 2, financing_rate: "6.5" } as PathsInputs;

function renderBox(customerInputs: PathsInputs = inputs) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const ui = (i: PathsInputs) => (
    <QueryClientProvider client={client}>
      <AskBox customerId="cust_01" inputs={i} />
    </QueryClientProvider>
  );
  const view = render(ui(customerInputs));
  return { rerenderWith: (i: PathsInputs) => view.rerender(ui(i)) };
}

const type = (text: string) =>
  fireEvent.change(screen.getByLabelText("Your question"), { target: { value: text } });
const submit = () => fireEvent.click(screen.getByRole("button", { name: "Ask" }));
const sentBody = (fn: ReturnType<typeof stub>) => JSON.parse(String(fn.mock.calls[0][1]?.body));

afterEach(() => vi.unstubAllGlobals());

describe("Ask about your options", () => {
  it("asks nothing until a question is sent, and will not send an empty one", () => {
    const fn = stub({ body: {} });
    renderBox();
    expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();
    type("   ");
    expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();
    expect(fn).not.toHaveBeenCalled();
  });

  it("limits the question to 300 characters and shows the count", () => {
    stub({ body: {} });
    renderBox();
    expect(screen.getByLabelText("Your question")).toHaveAttribute("maxlength", "300");
    type("hello");
    expect(screen.getByText(/5 of 300 characters/)).toBeInTheDocument();
  });

  it("sends the question with the current slider settings and shows the checked answer", async () => {
    const fn = stub({
      body: { answer: "Buy out would cost $420 a month.", verified: true, message: null },
    });
    renderBox();
    type("  Can I afford it?  ");
    submit();
    expect(await screen.findByText("Buy out would cost $420 a month.")).toBeInTheDocument();
    expect(screen.getByText("Numbers verified")).toBeInTheDocument();
    expect(String(fn.mock.calls[0][0])).toBe("/api/customers/cust_01/ask");
    expect(sentBody(fn)).toEqual({ ...inputs, question: "Can I afford it?" });
  });

  it("shows a loading state while the answer is on the way", async () => {
    stub("never");
    renderBox();
    type("Q?");
    submit();
    expect(await screen.findByRole("status")).toHaveTextContent("Thinking");
    expect(screen.getByRole("button", { name: "Thinking…" })).toBeDisabled();
  });

  it("says plainly when there is no reliable answer, and shows nothing from the model", async () => {
    stub({ body: { answer: null, verified: false, message: "I can't answer that reliably." } });
    renderBox();
    type("Will I save $9,999?");
    submit();
    expect(await screen.findByText("I can't answer that reliably.")).toBeInTheDocument();
    expect(screen.queryByText("Numbers verified")).not.toBeInTheDocument();
  });

  it("shows a readable error when the server cannot be reached", async () => {
    stub(new TypeError("Failed to fetch"));
    renderBox();
    type("Q?");
    submit();
    expect(await screen.findByRole("alert")).toHaveTextContent("We couldn't reach the server");
    expect(document.body).not.toHaveTextContent("Failed to fetch");
  });

  it("says how long to wait when the limit is reached", async () => {
    stub({
      status: 429,
      body: { detail: "You've made a lot of requests. Please try again later." },
      headers: { "Retry-After": "3600" },
    });
    renderBox();
    type("Q?");
    submit();
    expect(await screen.findByRole("alert")).toHaveTextContent("Please try again later. Try again in 60 minutes.");
  });

  it("flags an answer given for earlier slider settings", async () => {
    stub({ body: { answer: "An answer.", verified: true, message: null } });
    const { rerenderWith } = renderBox();
    type("Q?");
    submit();
    await screen.findByText("An answer.");
    expect(screen.queryByText(/earlier slider settings/)).not.toBeInTheDocument();
    rerenderWith({ ...inputs, miles_per_year: 9000 });
    expect(screen.getByText(/This answer was for your earlier slider settings/)).toBeInTheDocument();
  });
});
