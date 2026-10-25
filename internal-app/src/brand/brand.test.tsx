import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CountUp } from "./CountUp";
import { LogoSlot } from "./LogoSlot";
import { StatusMessage } from "./StatusMessage";
import { PROJECTION_DASH, SEQUENTIAL, roleColor } from "./chartColors";
import { parseMs } from "./motion";
import { animateMoves } from "./useResort";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("LogoSlot", () => {
  it("shows a placeholder reading 'Your logo' when no logo is set", () => {
    render(<LogoSlot />);
    expect(screen.getByText("Your logo")).toBeInTheDocument();
  });

  it("keeps the same box (same classes) whether or not a logo is set", () => {
    const { container: empty } = render(<LogoSlot size="card" />);
    vi.stubEnv("VITE_LOGO_URL", "/logo.png");
    const { container: set } = render(<LogoSlot size="card" />);
    expect(empty.firstElementChild?.className).toBe(set.firstElementChild?.className);
    expect(empty.firstElementChild?.className).toContain("logo-card");
    expect(set.querySelector("img")).toHaveAttribute("src", "/logo.png");
  });

  it("falls back to the placeholder when the image fails to load", () => {
    vi.stubEnv("VITE_LOGO_URL", "/missing.png");
    const { container } = render(<LogoSlot />);
    fireEvent.error(container.querySelector("img")!);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText("Your logo")).toBeInTheDocument();
  });
});

describe("StatusMessage", () => {
  it.each([
    ["positive", "Verified"],
    ["warning", "Warning"],
    ["critical", "Error"],
    ["neutral", "Not enough data"],
  ] as const)("%s shows an icon, the label and the message", (variant, label) => {
    const { container } = render(
      <StatusMessage variant={variant} label={label}>
        Something to say
      </StatusMessage>,
    );
    expect(container.querySelector("svg")).not.toBeNull();
    expect(screen.getByText(label)).toBeInTheDocument();
    expect(screen.getByText("Something to say")).toBeInTheDocument();
    expect(container.firstElementChild?.className).toContain(`status-${variant}`);
  });

  it("only a critical message is an alert", () => {
    const { rerender } = render(<StatusMessage variant="critical" label="Error">x</StatusMessage>);
    expect(screen.getByRole("alert")).toHaveTextContent("Error");
    rerender(<StatusMessage variant="warning" label="Warning">x</StatusMessage>);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("CountUp", () => {
  it("shows the value at once on first render", () => {
    render(<CountUp value="$1,234" />);
    expect(screen.getByText("$1,234")).toBeInTheDocument();
  });

  it("shows the exact final text immediately when motion cannot be animated (no media-query support)", () => {
    const { rerender } = render(<CountUp value="$1,234" />);
    rerender(<CountUp value="$2,310" />);
    expect(screen.getByText("$2,310")).toBeInTheDocument();
  });

  it("shows the exact final text immediately under reduced motion", () => {
    vi.stubGlobal("matchMedia", () => ({ matches: true }));
    const { rerender } = render(<CountUp value="$1,234" />);
    rerender(<CountUp value="$2,310" />);
    expect(screen.getByText("$2,310")).toBeInTheDocument();
  });

  it("counts up in steps and ends on the exact text when motion is allowed", async () => {
    vi.stubGlobal("matchMedia", () => ({ matches: false }));
    let now = 0;
    const frames: FrameRequestCallback[] = [];
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => frames.push(cb));
    vi.stubGlobal("cancelAnimationFrame", () => {});
    vi.spyOn(performance, "now").mockImplementation(() => now);
    const { rerender } = render(<CountUp value="$1,000" />);
    rerender(<CountUp value="$2,000" />);
    now = 150;
    await act(async () => frames.shift()?.(now));
    const mid = Number(screen.getByText(/^\$/).textContent!.replace(/[$,]/g, ""));
    expect(mid).toBeGreaterThan(1000);
    expect(mid).toBeLessThan(2000);
    now = 400;
    await act(async () => frames.shift()?.(now));
    expect(screen.getByText("$2,000")).toBeInTheDocument();
  });
});

describe("chartColors", () => {
  it("gives each role its fixed token colour", () => {
    expect(roleColor("recommended")).toBe("var(--chart-green)");
    expect(roleColor("actual")).toBe("var(--chart-green)");
    expect(roleColor("alternative")).toBe("var(--chart-blue)");
    expect(roleColor("further")).toBe("var(--chart-purple)");
    expect(roleColor("baseline")).toBe("var(--chart-grey)");
    expect(roleColor("grid")).toBe("var(--chart-grid)");
    expect(roleColor("axis")).toBe("var(--chart-axis-text)");
  });

  it("dashes projections and has a four-step sequential scale", () => {
    expect(PROJECTION_DASH).toBe("6 4");
    expect(SEQUENTIAL).toEqual(["var(--chart-seq-1)", "var(--chart-seq-2)", "var(--chart-seq-3)", "var(--chart-seq-4)"]);
  });
});

describe("animateMoves (re-sort slide)", () => {
  it("moves each item from its old place to its new one, and does nothing when motion is reduced", () => {
    const a = document.createElement("div");
    a.dataset.resortKey = "a";
    const rect = (top: number) => ({ top, left: 0 }) as DOMRect;
    vi.spyOn(a, "getBoundingClientRect").mockReturnValue(rect(100));
    const container = document.createElement("div");
    container.append(a);
    animateMoves(container, new Map([["a", rect(300)]]), false);
    expect(a.style.transform).toBe("translate(0px, 200px)");
    const b = document.createElement("div");
    b.dataset.resortKey = "b";
    vi.spyOn(b, "getBoundingClientRect").mockReturnValue(rect(100));
    container.replaceChildren(b);
    animateMoves(container, new Map([["b", rect(300)]]), true);
    expect(b.style.transform).toBe("");
  });
});

describe("parseMs", () => {
  it("reads the motion token however the build wrote it", () => {
    expect(parseMs("300ms")).toBe(300);
    expect(parseMs(".3s")).toBe(300);
    expect(parseMs("0.2s")).toBe(200);
    expect(parseMs("0ms")).toBe(0);
    expect(parseMs("0s")).toBe(0);
    expect(parseMs("")).toBeNull();
    expect(parseMs("fast")).toBeNull();
  });
});
