import type { components } from "./types";

// The shapes come from the generated OpenAPI types (`npm run gen:api`), never written by hand.
export type Customer = components["schemas"]["CustomerListItem"];
export type Overview = components["schemas"]["OverviewResponse"];
export type Spending = components["schemas"]["SpendingResponse"];

const NETWORK_ERROR = "We couldn't reach the server. Please check your connection and try again.";
const GENERIC_ERROR = "Something went wrong. Please try again.";

async function detailOf(res: Response): Promise<string> {
  try {
    const body = await res.json();
    return typeof body?.detail === "string" ? body.detail : GENERIC_ERROR;
  } catch {
    return GENERIC_ERROR;
  }
}

/** Every failure becomes an Error with a message a customer can read: never a stack trace. */
async function getJson<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path);
  } catch {
    throw new Error(NETWORK_ERROR);
  }
  if (!res.ok) throw new Error(await detailOf(res));
  return (await res.json()) as T;
}

export const api = {
  customers: () => getJson<Customer[]>("/api/customers"),
  overview: (id: string) => getJson<Overview>(`/api/customers/${encodeURIComponent(id)}/overview`),
  spending: (id: string) => getJson<Spending>(`/api/customers/${encodeURIComponent(id)}/spending`),
};
