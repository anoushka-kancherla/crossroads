import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";

function stubLocation(href: string) {
  const u = new URL(href);
  vi.stubGlobal("location", { protocol: u.protocol, hostname: u.hostname, port: u.port, href });
}

function serve() {
  const fn = vi.fn(async () => new Response(JSON.stringify([]), { status: 200 }));
  vi.stubGlobal("fetch", fn);
  return fn;
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

describe("role landing page", () => {
  it("shows a bare split screen at / and asks for nothing", () => {
    const fetch = serve();
    stubLocation("http://localhost:8080/");
    renderAt("/");
    expect(screen.queryByRole("banner")).toBeNull();
    expect(screen.getByRole("link", { name: /customer/i })).toHaveAttribute("href", "/overview");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("takes a customer from the landing page to the Overview", async () => {
    serve();
    stubLocation("http://localhost:8080/");
    renderAt("/");
    fireEvent.click(screen.getByRole("link", { name: /customer/i }));
    expect(await screen.findByRole("banner")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /staff/i })).toBeNull();
  });

  it("still opens a deep link straight to Your paths, with no landing page", async () => {
    serve();
    stubLocation("http://localhost:8080/");
    renderAt("/paths");
    expect(await screen.findByRole("banner")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /staff/i })).toBeNull();
  });

  it("sends staff to the dashboard's own address, worked out from where the page is", () => {
    serve();
    stubLocation("https://app.1.2.3.4.nip.io/");
    renderAt("/");
    expect(screen.getByRole("link", { name: /staff/i })).toHaveAttribute("href", "https://internal.1.2.3.4.nip.io/");
  });

  it("shows the Staff half disabled, not as a link, when the staff address is unknown", () => {
    serve();
    stubLocation("https://example.com/");
    renderAt("/");
    expect(screen.queryByRole("link", { name: /staff/i })).toBeNull();
    expect(screen.getByText(/staff address is not configured/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /customer/i })).toBeInTheDocument();
  });

  it("has exactly two choices, each one tab stop", () => {
    serve();
    stubLocation("http://localhost:8080/");
    renderAt("/");
    expect(screen.getAllByRole("link")).toHaveLength(2);
  });
});
