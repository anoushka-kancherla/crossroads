import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { QueryState } from "../components/QueryState";
import { endLabel } from "./chartLabels";
import { pathRoles, roleColor } from "./chartColors";

describe("chart series roles", () => {
  it("makes the recommended path green, Keep as is grey, and the others blue then purple", () => {
    const roles = pathRoles(["keep_as_is", "buy_out", "return_lease_new", "walk_away"], "buy_out");
    expect(roleColor(roles.buy_out)).toBe("var(--chart-green)");
    expect(roleColor(roles.keep_as_is)).toBe("var(--chart-grey)");
    expect(roleColor(roles.return_lease_new)).toBe("var(--chart-blue)");
    expect(roleColor(roles.walk_away)).toBe("var(--chart-purple)");
  });

  it("keeps the same meaning when Keep as is is the recommendation: green, not grey", () => {
    const roles = pathRoles(["keep_as_is", "buy_out"], "keep_as_is");
    expect(roleColor(roles.keep_as_is)).toBe("var(--chart-green)");
    expect(roleColor(roles.buy_out)).toBe("var(--chart-blue)");
  });
});

describe("direct end labels", () => {
  it("draws its text only at the last point, as text a reader can use without the colour", () => {
    const label = endLabel("Buy out", 59);
    const { container, rerender } = render(<svg>{label({ x: 10, y: 20, index: 3 })}</svg>);
    expect(container.querySelector("text")).toBeNull();
    rerender(<svg>{label({ x: 10, y: 20, index: 59 })}</svg>);
    expect(container.querySelector("text")).toHaveTextContent("Buy out");
  });
});

describe("QueryState error", () => {
  it("is the critical status with an icon and the label, keeping the message and the alert role", () => {
    const { container } = render(
      <QueryState status="error" error={new Error("We couldn't reach the server.")} data={undefined}>
        {() => null}
      </QueryState>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Error");
    expect(screen.getByText("We couldn't reach the server.")).toBeInTheDocument();
    expect(container.querySelector(".status-critical svg")).not.toBeNull();
  });
});
