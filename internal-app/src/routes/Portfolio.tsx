import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { roleColor } from "../brand/chartColors";
import { StatusMessage } from "../brand/StatusMessage";
import { UnauthorizedError, api, type Portfolio as PortfolioData } from "../api/client";
import { LivePanel } from "../components/LivePanel";
import { QueryState } from "../components/QueryState";
import { count, dateLabel, money } from "../format";

/** The portfolio view (FR-015..FR-018, FR-037): every figure comes from the stored engine results. */
export default function Portfolio() {
  const qc = useQueryClient();
  const portfolio = useQuery({ queryKey: ["portfolio"], queryFn: api.portfolio, retry: false });
  const refresh = useMutation({
    mutationFn: api.refresh,
    onSuccess: (data) => {
      qc.setQueryData(["portfolio"], data);
      void qc.invalidateQueries({ queryKey: ["fairness"] }); // the server recomputed it too (FR-015)
    },
  });

  // An expired or ended session sends staff back to sign-in and drops every figure from memory.
  const expired = portfolio.error instanceof UnauthorizedError || refresh.error instanceof UnauthorizedError;
  useEffect(() => {
    if (!expired) return;
    qc.removeQueries({ queryKey: ["portfolio"] });
    qc.setQueryData(["session"], null);
  }, [expired, qc]);
  if (expired) return null;

  return (
    <>
      <div className="actions">
        <button className="secondary" onClick={() => refresh.mutate()} disabled={refresh.isPending}>
          {refresh.isPending ? "Refreshing…" : "Refresh"}
        </button>
        {refresh.isError && (
          <StatusMessage variant="critical" label="Error">
            {refresh.error.message}
          </StatusMessage>
        )}
      </div>
      <LivePanel />
      <QueryState
        status={portfolio.status}
        error={portfolio.error}
        data={portfolio.data}
        isEmpty={(d) => d.empty}
        emptyMessage="No recommendations yet. Press Refresh to work them out."
      >
        {(data) => <Dashboard data={data} />}
      </QueryState>
    </>
  );
}

function Dashboard({ data }: { data: PortfolioData }) {
  const k = data.kpis;
  return (
    <>
      <h1>Portfolio view: what customers choose and what it's worth</h1>
      <p className="subtitle">
        Across {count(data.customers_total)} synthetic customers · recommendations as of{" "}
        {data.computed_at ? dateLabel(data.computed_at) : "not yet computed"}
      </p>
      <div className="tiles">
        <Tile label="Customers retained" value={`${k.retained_pct}%`} sub="Recommended path keeps them with Toyota" />
        <Tile label="Est. revenue kept" value={money(k.revenue_total)} sub="Over 5 years" />
        <Tile
          label={`Avg. savings · ${count(data.customers_total - data.no_recommendation)} customers with an affordable option`}
          value={money(k.avg_savings)}
          sub="Versus doing nothing"
        />
        <Tile label="Explanations verified" value={`${k.explanations_verified_pct}%`} sub="Passed the number check" />
        <Tile
          label="Need no specialist"
          value={`${data.self_service_pct}%`}
          sub={data.next_steps.map((s) => `${count(s.customers)} ${s.label.toLowerCase()}`).join(" · ")}
        />
      </div>
      <div className="columns">
        <section className="panel" aria-label="Recommended path mix">
          <h2>Recommended path mix</h2>
          <div className="chart chart-tall">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.by_path} layout="vertical" margin={{ left: 24 }}>
                <CartesianGrid stroke={roleColor("grid")} strokeDasharray="3 3" />
                <XAxis type="number" allowDecimals={false} />
                <YAxis type="category" dataKey="label" width={130} />
                <Tooltip />
                <Bar dataKey="customers" name="Customers" fill={roleColor("actual")} isAnimationActive={false}>
                  {data.by_path.map((row) => (
                    // Paths where the customer leaves Toyota are grey; the counts are also in the table beside it.
                    <Cell key={row.path} fill={row.stays_with_toyota ? roleColor("actual") : roleColor("baseline")} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>
        <section className="panel panel-table" aria-label="Value by path">
          <h2>Value by path</h2>
          <table>
            <thead>
              <tr>
                <th>Path</th>
                <th className="num">Customers</th>
                <th>Stays with Toyota</th>
                <th>Next step</th>
                <th className="num">Est. revenue</th>
              </tr>
            </thead>
            <tbody>
              {data.by_path.map((row) => (
                <tr key={row.path}>
                  <td>{row.label}</td>
                  <td className="num">{count(row.customers)}</td>
                  <td>
                    <span className={row.stays_with_toyota ? "pill" : "pill pill-no"}>{row.stays_label}</span>
                  </td>
                  <td>{row.next_step_label}</td>
                  <td className="num">{money(row.revenue)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.no_recommendation > 0 && (
            <p className="subtitle">
              {count(data.no_recommendation)} customer{data.no_recommendation === 1 ? "" : "s"} with no affordable
              path.
            </p>
          )}
        </section>
      </div>
      <p className="assumptions-label">Illustrative assumptions</p>
      <ul className="assumptions" aria-label="Assumptions">
        {data.assumptions.map((a) => (
          <li key={a}>{a}</li>
        ))}
      </ul>
    </>
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
