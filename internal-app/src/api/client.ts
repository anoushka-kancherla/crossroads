import type { components } from "./types";

// The shapes come from the generated OpenAPI types (`npm run gen:api`), never written by hand.
export type Portfolio = components["schemas"]["PortfolioResponse"];
export type PathRow = components["schemas"]["PathRowOut"];
export type FairnessReport = components["schemas"]["FairnessResponse"];
export type LiveFigures = components["schemas"]["LiveResponse"];
export type Session = components["schemas"]["SessionOut"];

const NETWORK_ERROR = "We couldn't reach the server. Please check your connection and try again.";
const GENERIC_ERROR = "Something went wrong. Please try again.";
const LOGIN = "/api/internal/login";

/** The server says the staff session is missing, expired or signed out. */
export class UnauthorizedError extends Error {
  constructor(message = "Please sign in.") {
    super(message);
    this.name = "UnauthorizedError";
  }
}

async function detailOf(res: Response): Promise<string> {
  try {
    const body = await res.json();
    return typeof body?.detail === "string" ? body.detail : GENERIC_ERROR;
  } catch {
    return GENERIC_ERROR;
  }
}

/** "Try again in 15 minutes." from the Retry-After seconds, or nothing when the header is missing. */
export function retryHint(header: string | null | undefined): string {
  const seconds = Number(header);
  if (!header || !Number.isFinite(seconds) || seconds <= 0) return "";
  const minutes = Math.ceil(seconds / 60);
  return seconds < 60 ? `Try again in ${Math.ceil(seconds)} seconds.` : `Try again in ${minutes} minute${minutes === 1 ? "" : "s"}.`;
}

/** Every failure becomes an Error with a message staff can read: never a stack trace. */
async function send(path: string, init?: RequestInit): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(path, { credentials: "same-origin", ...init });
  } catch {
    throw new Error(NETWORK_ERROR);
  }
  if (res.ok) return res;
  const detail = await detailOf(res);
  if (res.status === 429) throw new Error(`${detail} ${retryHint(res.headers?.get("Retry-After"))}`.trim());
  // A 401 from sign-in itself is a wrong password, not an expired session.
  throw res.status === 401 && path !== LOGIN ? new UnauthorizedError() : new Error(detail);
}

const json = async <T>(res: Response) => (await res.json()) as T;

export const api = {
  /** The signed-in staff member, or null when there is no valid session. */
  session: async (): Promise<Session | null> => {
    try {
      return await json<Session>(await send("/api/internal/session"));
    } catch (e) {
      if (e instanceof UnauthorizedError) return null;
      throw e;
    }
  },
  login: async (username: string, password: string): Promise<void> => {
    await send(LOGIN, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
  },
  logout: async (): Promise<void> => {
    await send("/api/internal/logout", { method: "POST" });
  },
  portfolio: async () => json<Portfolio>(await send("/api/internal/portfolio")),
  fairness: async () => json<FairnessReport>(await send("/api/internal/fairness")),
  live: async () => json<LiveFigures>(await send("/api/internal/live")),
  refresh: async () => json<Portfolio>(await send("/api/internal/portfolio/refresh", { method: "POST" })),
};
