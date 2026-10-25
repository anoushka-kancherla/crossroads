import { describe, expect, it } from "vitest";
import { staffUrl } from "./staffUrl";

const at = (protocol: string, hostname: string, port = "") => ({ protocol, hostname, port });

describe("staffUrl", () => {
  it("uses the override when one is set", () => {
    expect(staffUrl(at("https:", "app.example.tech"), "https://staff.example.org/")).toBe("https://staff.example.org/");
  });
  it("swaps app. for internal. on a live host, keeping https", () => {
    expect(staffUrl(at("https:", "app.1.2.3.4.nip.io"))).toBe("https://internal.1.2.3.4.nip.io/");
    expect(staffUrl(at("https:", "app.crossroads.tech"))).toBe("https://internal.crossroads.tech/");
  });
  it("maps the local Compose and dev ports", () => {
    expect(staffUrl(at("http:", "localhost", "8080"))).toBe("http://localhost:8081/");
    expect(staffUrl(at("http:", "localhost", "5173"))).toBe("http://localhost:5174/");
  });
  it("returns null for a layout it does not recognise, never the page itself", () => {
    expect(staffUrl(at("http:", "localhost", "3000"))).toBeNull();
    expect(staffUrl(at("https:", "example.com"))).toBeNull();
  });
});
