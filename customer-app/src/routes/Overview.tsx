import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, type Overview as OverviewData } from "../api/client";
import { QueryState } from "../components/QueryState";
import { useCustomer } from "../CustomerContext";
import { count, dateLabel, money, monthLabel, plural } from "../format";

type View = "mileage" | "spending";
const COLORS = ["#1f6feb", "#d97706", "#059669", "#9333ea", "#dc2626"];

export default function Overview() {
  const { customerId } = useCustomer();
  const [view, setView] = useState<View>("mileage");
  const overview = useQuery({
    queryKey: ["overview", customerId],
    queryFn: () => api.overview(customerId as string),
    enabled: customerId !== null,
  });

  if (customerId === null) return <p>Pick a demo customer to see where they stand.</p>;
  return (
    <QueryState status={overview.status} error={overview.error} data={overview.data}>
      {(o) => <OverviewBody o={o} customerId={customerId} view={view} setView={setView} />}
    </QueryState>
  );
}

function OverviewBody({
  o,
  customerId,
  view,
  setView,
}: {
  o: OverviewData;
  customerId: string;
  view: View;
  setView: (v: View) => void;
}) {
  const { customer, tiles, mileage, money: bank, market_value: mv } = o;
  const proj = mileage.projection;
  const lease = customer.contract_type === "lease";
  return (
    <div className="overview">
      <h1>Hi {customer.first_name}, here&apos;s where you stand</h1>
      <p className="subtitle">
        {customer.vehicle} · {lease ? "Lease" : "Loan"} · {plural(customer.months_left, "month")} left
      </p>

      <div className="tiles">
        <Tile label="Monthly payment" value={money(tiles.monthly_payment)} sub={`${tiles.payments_made} of ${tiles.payments_total} paid`} />
        <Tile label="Months left" value={count(tiles.months_left)} sub={`Ends ${monthLabel(tiles.ends_on.slice(0, 7))}`} />
        <Tile label="Payoff or buyout" value={money(tiles.payoff_or_buyout)} sub="As of today" />
        <Tile
          label="Miles driven"
          value={count(tiles.miles_driven)}
          sub={tiles.allowance === null ? "No mileage allowance" : `Allowance ${count(tiles.allowance)}`}
        />
        <Tile label="Equity" value={money(tiles.equity)} sub="Market value minus payoff" />
      </div>

      <div className="columns">
        <section className="panel" aria-labelledby="chart-title">
          <div className="panel-head">
            <h2 id="chart-title">{view === "mileage" ? "Mileage: actual and projected to contract end" : "Spending by month"}</h2>
            <div role="radiogroup" aria-label="Chart">
              {(["mileage", "spending"] as const).map((v) => (
                <label key={v}>
                  <input type="radio" name="chart-view" checked={view === v} onChange={() => setView(v)} />{" "}
                  {v === "mileage" ? "Mileage" : "Spending"}
                </label>
              ))}
            </div>
          </div>
          {view === "mileage" ? <MileageChart mileage={mileage} /> : <SpendingChart customerId={customerId} />}
          <p className="note">
            {lease
              ? proj.overage_miles
                ? `Projection: ${count(proj.overage_miles)} miles over allowance at lease end, about ${money(proj.overage_fee ?? "0")} in fees`
                : "Projection: you are within your mileage allowance at lease end."
              : "Projection: there is no mileage allowance on a loan, so no overage fees."}
          </p>
          <p className="basis">
            {count(proj.rate_per_year)} miles a year. {proj.basis_label}.
          </p>
        </section>

        <section className="panel" aria-labelledby="money-title">
          <h2 id="money-title">Your money picture</h2>
          <p className="basis">{bank.source_label}</p>
          <dl className="rows">
            <Row label="Checking balance" value={money(bank.checking)} />
            <Row label="Savings balance" value={money(bank.savings)} />
            <Row label="Monthly income" value={money(bank.monthly_income)} />
            <Row label="Monthly bills" value={money(bank.monthly_bills)} />
            <Row label="Room for a car payment" value={money(bank.room_for_payment)} />
          </dl>
          <h3>Your car&apos;s market value</h3>
          <p className="big">
            {mv.low !== null && mv.high !== null ? `${money(mv.low)} to ${money(mv.high)}` : `${money(mv.median)} (estimated)`}
          </p>
          <p className="basis">
            {mv.basis_label}
            {mv.updated_at ? ` · updated ${dateLabel(mv.updated_at)}` : ""}
            {mv.basis === "listings" ? ` · ${mv.source_label}` : ""}
          </p>
        </section>
      </div>

      <Link className="button" to="/paths">
        See my options
      </Link>
    </div>
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

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="row">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function MileageChart({ mileage }: { mileage: OverviewData["mileage"] }) {
  const { actual_monthly: actual, projected_monthly: projected, allowance_per_month: allowance } = mileage;
  if (actual.length === 0 && projected.length === 0) return <p>Nothing to chart yet.</p>;
  const rows = new Map<string, { month: string; actual?: number; projected?: number }>();
  for (const p of actual) rows.set(p.month, { month: p.month, actual: p.miles });
  // Start the projected line at the last actual point so the two lines join.
  const last = actual.at(-1);
  if (last) rows.set(last.month, { month: last.month, actual: last.miles, projected: last.miles });
  for (const p of projected) rows.set(p.month, { month: p.month, projected: p.miles });
  const data = [...rows.values()].sort((a, b) => a.month.localeCompare(b.month));
  return (
    <>
      {actual.length === 0 && (
        <p role="note">No odometer history yet, so only the projection is shown. {mileage.projection.basis_label}.</p>
      )}
      <div className="chart" aria-label="Monthly miles, actual and projected">
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="month" tickFormatter={monthLabel} />
            <YAxis />
            <Tooltip labelFormatter={(m) => monthLabel(String(m))} />
            <Legend />
            <Line type="monotone" dataKey="actual" name="Actual miles" stroke={COLORS[0]} dot={false} connectNulls isAnimationActive={false} />
            <Line
              type="monotone"
              dataKey="projected"
              name="Projected miles"
              stroke={COLORS[0]}
              strokeDasharray="6 4"
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
            {allowance !== null && <ReferenceLine y={allowance} stroke={COLORS[4]} strokeDasharray="4 4" label="Allowance" />}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </>
  );
}

function SpendingChart({ customerId }: { customerId: string }) {
  const spending = useQuery({ queryKey: ["spending", customerId], queryFn: () => api.spending(customerId) });
  return (
    <QueryState
      status={spending.status}
      error={spending.error}
      data={spending.data}
      isEmpty={(d) => d.months.length === 0}
      emptyMessage="No spending to show yet."
    >
      {(d) => {
        const categories = [...new Set(d.months.map((p) => p.category))];
        const byMonth = new Map<string, Record<string, number | string>>();
        for (const p of d.months) {
          const row = byMonth.get(p.month) ?? { month: p.month };
          row[p.category] = Number(p.amount); // charted, never added up here
          byMonth.set(p.month, row);
        }
        const data = [...byMonth.values()].sort((a, b) => String(a.month).localeCompare(String(b.month)));
        return (
          <div className="chart" aria-label="Spending by month and category">
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={data}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="month" tickFormatter={monthLabel} />
                <YAxis />
                <Tooltip labelFormatter={(m) => monthLabel(String(m))} />
                <Legend />
                {categories.map((c, i) => (
                  <Bar key={c} dataKey={c} stackId="spend" fill={COLORS[i % COLORS.length]} isAnimationActive={false} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        );
      }}
    </QueryState>
  );
}
