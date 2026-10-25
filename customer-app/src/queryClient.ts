import { QueryClient } from "@tanstack/react-query";

// One retry, not the default three: with the database down each attempt waits for its timeout, and a
// screen stuck on "Loading…" for half a minute is worse than a clear error (FR-019).
export const queryDefaults = { queries: { retry: 1 } };

export const queryClient = new QueryClient({ defaultOptions: queryDefaults });
