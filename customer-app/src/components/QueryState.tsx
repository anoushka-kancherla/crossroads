import type { ReactNode } from "react";
import { StatusMessage } from "../brand/StatusMessage";

type Props<T> = {
  status: "pending" | "error" | "success";
  error?: unknown;
  data: T | undefined;
  /** True when the data is valid but has nothing to show (an empty list, no rows). */
  isEmpty?: (data: T) => boolean;
  emptyMessage?: string;
  children: (data: T) => ReactNode;
};

/** Every screen and data-driven component renders through this, so each one has distinct
 *  loading, empty and error states (FR-019, constitution principle VI). */
export function QueryState<T>({
  status,
  error,
  data,
  isEmpty,
  emptyMessage = "Nothing to show yet.",
  children,
}: Props<T>) {
  if (status === "pending") return <p role="status">Loading…</p>;
  if (status === "error") {
    // Show a readable message, never a stack trace or a raw response.
    const message = error instanceof Error && error.message ? error.message : "Something went wrong. Please try again.";
    return (
      <StatusMessage variant="critical" label="Error">
        {message}
      </StatusMessage>
    );
  }
  if (data === undefined || (isEmpty?.(data) ?? false)) return <p>{emptyMessage}</p>;
  return <>{children(data)}</>;
}
