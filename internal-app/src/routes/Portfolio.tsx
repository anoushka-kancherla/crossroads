import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { UnauthorizedError, api, type Portfolio as PortfolioData } from "../api/client";
import { QueryState } from "../components/QueryState";
import { count, dateLabel, money } from "../format";

/** The portfolio view (FR-015..FR-018, FR-037): every figure comes from the stored engine results. */
export default function Portfolio() {
  const qc = useQueryClient();
  const portfolio = useQuery({ queryKey: ["portfolio"], queryFn: api.portfolio, retry: false });
  const refresh = useMutation({
    mutationFn: api.refresh,
    onSuccess: (data) => qc.setQueryData(["portfolio"], data),
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
        {refresh.isError && <span role="alert">{refresh.error.message}</span>}
      </div>
      <QueryState
        status={portfolio.status}
        error={portfolio.error}
        data={portfolio.data}
        isEmpty={(d) => d.empty}
        emptyMessage="No recommendations have been computed yet. Use Refresh to compute them."
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
      </div>
      <div className="columns">
        <section className="panel" aria-label="Recommended path mix">
          <h2>Recommended path mix</h2>
          <div className="chart">
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={data.by_path} layout="vertical" margin={{ left: 24 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" allowDecimals={false} />
                <YAxis type="category" dataKey="label" width={130} />
                <Tooltip />
                <Bar dataKey="customers" name="Customers" fill="#444" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>
        <section className="panel" aria-label="Value by path">
          <h2>Value by path</h2>
          <table>
            <thead>
              <tr>
                <th>Path</th>
                <th className="num">Customers</th>
                <th>Stays with Toyota</th>
                <th className="num">Est. revenue</th>
              </tr>
            </thead>
            <tbody>
              {data.by_path.map((row) => (
                <tr key={row.path}>
                  <td>{row.label}</td>
                  <td className="num">{count(row.customers)}</td>
                  <td>{row.stays_label}</td>
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
