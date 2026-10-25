import { useMutation, useQuery } from "@tanstack/react-query";
import { api, type NextStepRequest } from "../api/client";
import { QueryState } from "./QueryState";

// Button wording for the recommended path. No figures: those come from the server.
const PRIMARY: Record<string, string> = {
  keep_as_is: "Stay on my current plan",
  buy_out: "Start buyout",
  return_lease_new: "Start a new lease",
  trade_in_early: "Start my trade-in",
  refinance: "Start refinance",
  extra_principal: "Set up extra payments",
  walk_away: "Plan my return",
};

type Props = { customerId: string; path: NextStepRequest["path"] | null };

/** The next-step button and "Talk to a specialist". Either one shows a confirmation, then the three
 *  nearest Toyota dealers. The confirmation never waits on the dealers: they load separately, with
 *  their own loading, empty and error states (FR-014, FR-035). */
export function NextStep({ customerId, path }: Props) {
  const step = useMutation({ mutationFn: (body: NextStepRequest) => api.nextStep(customerId, body) });
  const dealers = useQuery({
    queryKey: ["dealers", customerId],
    queryFn: () => api.dealers(customerId),
    enabled: step.isSuccess,
    retry: false,
  });

  return (
    <div className="next-step">
      <div className="actions">
        {path && (
          <button type="button" className="primary" disabled={step.isPending} onClick={() => step.mutate({ path, kind: "primary" })}>
            {PRIMARY[path] ?? "Next step"}
          </button>
        )}
        <button
          type="button"
          className="secondary"
          disabled={step.isPending}
          onClick={() => step.mutate({ path: path ?? "keep_as_is", kind: "specialist" })}
        >
          Talk to a specialist
        </button>
      </div>

      <div aria-live="polite">
        {step.isPending && <p role="status">Sending…</p>}
        {step.isError && <p role="alert">{step.error.message}</p>}
        {step.isSuccess && (
          <>
            <p className="confirmation">{step.data.confirmation}</p>
            <p className="basis">Next step type: {step.data.step_label}</p>
            <section aria-labelledby="dealers-title">
              <h3 id="dealers-title">Toyota dealers near you</h3>
              <QueryState
                status={dealers.status}
                error={dealers.error}
                data={dealers.data}
                isEmpty={(d) => d.dealers.length === 0}
                emptyMessage="No Toyota dealers found near you."
              >
                {(d) => (
                  <ul className="dealers">
                    {d.dealers.map((dealer) => (
                      <li key={`${dealer.name}-${dealer.address}`}>
                        <strong>{dealer.name}</strong>
                        <div>{dealer.address}</div>
                        <div className="basis">
                          {[
                            dealer.hours,
                            dealer.rating !== null ? `Rated ${dealer.rating}` : null,
                            `${dealer.distance_miles.toLocaleString("en-US", { maximumFractionDigits: 1 })} miles away`,
                          ]
                            .filter(Boolean)
                            .join(" · ")}
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </QueryState>
            </section>
          </>
        )}
      </div>
    </div>
  );
}
