import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { StatusMessage } from "../brand/StatusMessage";
import { UnauthorizedError, api, type LiveFigures } from "../api/client";
import { count, money, timeLabel } from "../format";
import { QueryState } from "./QueryState";

const EVERY_MS = 3000;
const KEY = ["live"];

/** The live acceptance figures (feature 005). They sit beside the recommendation-based tiles, never in place of
 *  them. The browser revalidates with the server's ETag, so an unchanged answer costs almost nothing. */
export function LivePanel() {
  const qc = useQueryClient();
  const live = useQuery({
    queryKey: KEY,
    queryFn: async () => {
      const next = await api.live();
      // An answer that was already in flight when a newer one landed must not move the figures backwards.
      const shown = qc.getQueryData<LiveFigures>(KEY);
      return shown && next.sequence < shown.sequence ? shown : next;
    },
    retry: false,
    refetchInterval: EVERY_MS,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
  });

  const expired = live.error instanceof UnauthorizedError;
  useEffect(() => {
    if (!expired) return;
    qc.removeQueries({ queryKey: KEY });
    qc.setQueryData(["session"], null);
  }, [expired, qc]);
  if (expired) return null;

  return (
    <section className="live" aria-label="Live acceptances">
      <h2>Live: accepted paths</h2>
      <QueryState status={live.data ? "success" : live.status} error={live.error} data={live.data}>
        {(d) => (
          <>
            <div className="tiles">
              <Tile label="Customers accepted" value={`${count(d.accepted_customers)} of ${count(d.customers_total)}`} sub="Latest accepted path per customer" />
              <Tile
                label="Retained among accepted"
                value={d.retained_pct === null ? "None yet" : `${d.retained_pct}%`}
                sub={d.retained_pct === null ? "No one has accepted a path yet" : `${count(d.retained_customers)} of ${count(d.accepted_customers)} stay with Toyota`}
              />
              <Tile label="Est. revenue from accepted" value={money(d.revenue_total)} sub="5-year interest income" />
            </div>
            <p className="note">Updated at {timeLabel(d.updated_at)}</p>
            {live.isError && (
              <StatusMessage variant="warning" label="Paused">
                Live figures are paused. We'll keep trying every few seconds.
              </StatusMessage>
            )}
          </>
        )}
      </QueryState>
    </section>
  );
}

function Tile({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="tile">
      <div className="tile-label">{label}</div>
      <div className="tile-value">{value}</div>
      <div className="tile-sub">{sub}</div>
    </div>
  );
}
