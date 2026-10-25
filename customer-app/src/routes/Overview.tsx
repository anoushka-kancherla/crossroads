import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
import { endLabel } from "../brand/chartLabels";
import { StatusMessage } from "../brand/StatusMessage";
import { PROJECTION_DASH, SEQUENTIAL, roleColor } from "../brand/chartColors";
import { QueryState } from "../components/QueryState";
import { useCustomer } from "../CustomerContext";
import { count, dateLabel, dateTimeLabel, money, monthLabel, plural } from "../format";

type View = "mileage" | "spending" | "payments";
const VIEW_LABEL: Record<View, string> = { mileage: "Mileage", spending: "Spending", payments: "Payments" };
const VIEW_TITLE: Record<View, string> = {
  mileage: "Mileage: actual and projected to contract end",
  spending: "Spending by month",
  payments: "Payments: principal and interest",
};

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
            <h2 id="chart-title">{VIEW_TITLE[view]}</h2>
            <div role="radiogroup" aria-label="Chart">
              {(["mileage", "spending", "payments"] as const).map((v) => (
                <label key={v}>
                  <input type="radio" name="chart-view" checked={view === v} onChange={() => setView(v)} />{" "}
                  {VIEW_LABEL[v]}
                </label>
              ))}
            </div>
          </div>
          {view === "mileage" && <MileageChart mileage={mileage} />}
          {view === "spending" && <SpendingChart customerId={customerId} />}
          {view === "payments" && <PaymentsChart customerId={customerId} />}
          {lease && proj.overage_miles ? (
            <StatusMessage variant="warning" label="Over your allowance">
              {`Projection: ${count(proj.overage_miles)} miles over allowance at lease end, about ${money(proj.overage_fee ?? "0")} in fees`}
            </StatusMessage>
          ) : lease ? (
            <StatusMessage variant="positive" label="Within your allowance">
              Projection: you are within your mileage allowance at lease end.
            </StatusMessage>
          ) : (
            <StatusMessage variant="neutral" label="No allowance">
              Projection: there is no mileage allowance on a loan, so no overage fees.
            </StatusMessage>
          )}
          <p className="basis">
            {count(proj.rate_per_year)} miles a year. {proj.basis_label}.
          </p>
        </section>

        <section className="panel" aria-labelledby="money-title">
          <h2 id="money-title">Your money picture</h2>
          <p className="basis">{bank.source_label}</p>
          {bank.source === "nessie" && <SyncBank customerId={customerId} syncedAt={bank.synced_at} />}
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

      <Link className="button primary" to="/paths">
        See my options
      </Link>
    </div>
  );
}

/** "Sync from my bank" (FR-039): re-reads this customer's figures from Nessie. If it fails, the panel keeps
 *  its last values and says so in plain words. */
function SyncBank({ customerId, syncedAt }: { customerId: string; syncedAt: string | null }) {
  const qc = useQueryClient();
  const sync = useMutation({
    mutationFn: () => api.sync(customerId),
    onSuccess: (r) =>
      qc.setQueryData<OverviewData>(["overview", customerId], (o) => (o ? { ...o, money: r.money } : o)),
  });
  return (
    <div className="sync">
      <button className="secondary" onClick={() => sync.mutate()} disabled={sync.isPending}>
        {sync.isPending ? "Syncing…" : "Sync from my bank"}
      </button>{" "}
      <span className="basis">{syncedAt ? `Last synced ${dateTimeLabel(syncedAt)}` : "Not synced yet"}</span>
      {sync.isError && (
        <StatusMessage variant="critical" label="Error">
          {sync.error.message}
        </StatusMessage>
      )}
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
        <div role="note">
          <StatusMessage variant="neutral" label="Unavailable">
            No odometer history yet, so only the projection is shown. {mileage.projection.basis_label}.
          </StatusMessage>
        </div>
      )}
      <div className="chart" aria-label="Monthly miles, actual and projected">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data}>
            <CartesianGrid stroke={roleColor("grid")} strokeDasharray="3 3" />
            <XAxis dataKey="month" tickFormatter={monthLabel} />
            <YAxis />
            <Tooltip labelFormatter={(m) => monthLabel(String(m))} />
            <Legend />
            <Line
              type="monotone"
              dataKey="actual"
              name="Actual miles"
              stroke={roleColor("actual")}
              strokeWidth={3}
              dot={false}
              connectNulls
              isAnimationActive={false}
              label={endLabel("Actual", data.map((r) => r.actual !== undefined).lastIndexOf(true))}
            />
            <Line
              type="monotone"
              dataKey="projected"
              name="Projected miles"
              stroke={roleColor("actual")}
              strokeWidth={3}
              strokeDasharray={PROJECTION_DASH}
              dot={false}
              connectNulls
              isAnimationActive={false}
              label={endLabel("Projected", data.length - 1)}
            />
            {allowance !== null && (
              <ReferenceLine
                y={allowance}
                stroke={roleColor("baseline")}
                strokeWidth={2}
                label={{ value: "Allowance", position: "insideTopLeft", className: "end-label" }}
              />
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </>
  );
}

function PaymentsChart({ customerId }: { customerId: string }) {
  const payments = useQuery({ queryKey: ["payments", customerId], queryFn: () => api.payments(customerId) });
  return (
    <QueryState
      status={payments.status}
      error={payments.error}
      data={payments.data}
      isEmpty={(d) => d.months.length === 0}
      emptyMessage="No payments to show yet."
    >
      {(d) => {
        const lease = d.kind === "lease";
        // Charted as given by the server, never added up here.
        const data = d.months.map((m) => ({ month: m.month, principal: Number(m.principal), interest: Number(m.interest) }));
        return (
          <div className="chart" aria-label="Monthly payments split into principal and interest">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data}>
                <CartesianGrid stroke={roleColor("grid")} strokeDasharray="3 3" />
                <XAxis dataKey="month" tickFormatter={monthLabel} />
                <YAxis />
                <Tooltip labelFormatter={(m) => monthLabel(String(m))} />
                <Legend />
                <Bar dataKey="principal" name={lease ? "Toward the car" : "Principal"} stackId="pay" fill={roleColor("actual")} isAnimationActive={false} />
                <Bar dataKey="interest" name={lease ? "Rent charge" : "Interest"} stackId="pay" fill={roleColor("alternative")} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        );
      }}
    </QueryState>
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
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data}>
                <CartesianGrid stroke={roleColor("grid")} strokeDasharray="3 3" />
                <XAxis dataKey="month" tickFormatter={monthLabel} />
                <YAxis />
                <Tooltip labelFormatter={(m) => monthLabel(String(m))} />
                <Legend />
                {categories.map((c, i) => (
                  <Bar key={c} dataKey={c} stackId="spend" fill={SEQUENTIAL[i % SEQUENTIAL.length]} isAnimationActive={false} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        );
      }}
    </QueryState>
  );
}
