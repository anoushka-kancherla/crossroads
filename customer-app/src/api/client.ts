import type { components } from "./types";

// The shapes come from the generated OpenAPI types (`npm run gen:api`), never written by hand.
export type Customer = components["schemas"]["CustomerListItem"];
export type Overview = components["schemas"]["OverviewResponse"];
export type Spending = components["schemas"]["SpendingResponse"];
export type PathsResult = components["schemas"]["PathsResponse"];
export type PathOption = components["schemas"]["OptionOut"];
export type PathsInputs = components["schemas"]["PathsRequest"];
export type Explanation = components["schemas"]["ExplanationOut"];
export type Dealer = components["schemas"]["DealerOut"];
export type Dealers = components["schemas"]["DealersResponse"];
export type NextStepRequest = components["schemas"]["NextStepRequest"];
export type NextStepResult = components["schemas"]["NextStepResponse"];
export type SyncResult = components["schemas"]["SyncResponse"];
export type Payments = components["schemas"]["PaymentsResponse"];
export type AskRequest = components["schemas"]["AskRequest"];
export type AskResult = components["schemas"]["AskResponse"];

const NETWORK_ERROR = "We couldn't reach the server. Please check your connection and try again.";
const GENERIC_ERROR = "Something went wrong. Please try again.";

/** "Try again in 15 minutes." from the Retry-After seconds, or nothing when the header is missing. */
export function retryHint(header: string | null | undefined): string {
  const seconds = Number(header);
  if (!header || !Number.isFinite(seconds) || seconds <= 0) return "";
  if (seconds < 60) return `Try again in ${Math.ceil(seconds)} seconds.`;
  const minutes = Math.ceil(seconds / 60);
  return `Try again in ${minutes} minute${minutes === 1 ? "" : "s"}.`;
}

async function detailOf(res: Response): Promise<string> {
  try {
    const body = await res.json();
    return typeof body?.detail === "string" ? body.detail : GENERIC_ERROR;
  } catch {
    return GENERIC_ERROR;
  }
}

/** Every failure becomes an Error with a message a customer can read: never a stack trace. */
async function send<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    throw new Error(NETWORK_ERROR);
  }
  if (!res.ok) {
    const detail = await detailOf(res);
    throw new Error(res.status === 429 ? `${detail} ${retryHint(res.headers?.get("Retry-After"))}`.trim() : detail);
  }
  return (await res.json()) as T;
}

const getJson = <T>(path: string) => send<T>(path);
const postJson = <T>(path: string, body: unknown) =>
  send<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

const customer = (id: string) => `/api/customers/${encodeURIComponent(id)}`;

export const api = {
  customers: () => getJson<Customer[]>("/api/customers"),
  overview: (id: string) => getJson<Overview>(`${customer(id)}/overview`),
  spending: (id: string) => getJson<Spending>(`${customer(id)}/spending`),
  /** Leave `inputs` out for the customer's own defaults, which come back in `inputs_used`. */
  paths: (id: string, inputs: PathsInputs = {}) => postJson<PathsResult>(`${customer(id)}/paths`, inputs),
  explanation: (id: string, inputs: PathsInputs = {}) => postJson<Explanation>(`${customer(id)}/explanation`, inputs),
  dealers: (id: string) => getJson<Dealers>(`${customer(id)}/dealers`),
  nextStep: (id: string, body: NextStepRequest) => postJson<NextStepResult>(`${customer(id)}/next-step`, body),
  /** Re-read this customer's bank figures from Nessie. */
  sync: (id: string) => postJson<SyncResult>(`${customer(id)}/sync`, {}),
  payments: (id: string) => getJson<Payments>(`${customer(id)}/payments`),
  ask: (id: string, body: AskRequest) => postJson<AskResult>(`${customer(id)}/ask`, body),
};
