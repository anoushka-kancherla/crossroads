import { QueryClient, QueryObserver } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { queryDefaults } from "./queryClient";

describe("the app's query defaults", () => {
  it("try a failing request twice in all, then show the error (not the default four attempts)", async () => {
    const client = new QueryClient({ defaultOptions: queryDefaults });
    const queryFn = vi.fn().mockRejectedValue(new Error("Customer data is temporarily unavailable."));
    const observer = new QueryObserver(client, { queryKey: ["customers"], queryFn });
    const done = new Promise<string>((resolve) =>
      observer.subscribe((r) => {
        if (r.status === "error") resolve(r.error.message);
      }),
    );
    await expect(done).resolves.toBe("Customer data is temporarily unavailable.");
    expect(queryFn).toHaveBeenCalledTimes(2);
  });
});
