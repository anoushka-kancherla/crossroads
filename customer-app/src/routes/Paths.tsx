import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type PathOption, type PathsResult } from "../api/client";
import { NextStep } from "../components/NextStep";
import { QueryState } from "../components/QueryState";
import { Sliders, type Values, valuesOf } from "../components/Sliders";
import { useCustomer } from "../CustomerContext";
import { money } from "../format";

const COLORS = ["#1f6feb", "#d97706", "#059669", "#9333ea", "#dc2626"];
const DEBOUNCE_MS = 250;

function useDebounced<T>(value: T, ms: number): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setSettled(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return settled;
}

export default function Paths() {
  const { customerId } = useCustomer();
  if (customerId === null) return <p>Pick a demo customer to see their paths.</p>;
  // Keyed by customer, so switching customers starts again from that customer's own defaults.
  return <PathsScreen key={customerId} customerId={customerId} />;
}

function PathsScreen({ customerId }: { customerId: string }) {
  // null means "the customer's own defaults"; the server reports them back in `inputs_used`.
  const [inputs, setInputs] = useState<Values | null>(null);
  const settled = useDebounced(inputs, DEBOUNCE_MS);
  const paths = useQuery({
    queryKey: ["paths", customerId, settled],
    queryFn: () => api.paths(customerId, settled ?? {}),
    placeholderData: keepPreviousData, // the old results stay while the new ones load
    retry: false,
  });

  // The last results that came back fine: if a new request is rejected they stay on screen.
  const lastGood = useRef<PathsResult>();
  useEffect(() => {
    if (paths.data) lastGood.current = paths.data;
  }, [paths.data]);
  const shown = paths.data ?? lastGood.current;

  if (shown === undefined) {
    return (
      <QueryState status={paths.status} error={paths.error} data={undefined}>
        {() => null}
      </QueryState>
    );
  }
  if (shown.options.length === 0) return <p>No paths are available for this customer.</p>;

  return (
    <div className="paths-layout">
      <aside>
        <Sliders
          values={inputs ?? valuesOf(shown.inputs_used)}
          ranges={shown.ranges}
          contractType={shown.contract_type}
          busy={paths.isFetching}
          onChange={setInputs}
          onReset={() => setInputs(null)}
        />
      </aside>
      <div className="paths-main">
        {paths.isError && <p role="alert">{paths.error.message}</p>}
        <PathsBody data={shown} customerId={customerId} />
      </div>
    </div>
  );
}

function PathsBody({ data, customerId }: { data: PathsResult; customerId: string }) {
  const rec = data.recommendation;
  const best = data.options.find((o) => o.path === rec.path);

  // The checked template is already on screen. The model's wording replaces it only if it arrives
  // and has passed the number check; a slow or failed request changes nothing and shows no error.
  const model = useQuery({
    queryKey: ["explanation", customerId, data.inputs_used],
    queryFn: () => api.explanation(customerId, data.inputs_used),
    staleTime: Infinity,
    retry: false,
  });
  const explanation = model.data && model.data.source === "gemini" && model.data.verified ? model.data : rec.explanation;

  const byCost = [...data.options].sort((a, b) => Number(a.five_year_cost) - Number(b.five_year_cost));

  return (
    <div className="paths">
      <section className="panel recommend" aria-labelledby="rec-title">
        <p className="eyebrow">{best ? "Recommended next move" : "No path fits yet"}</p>
        <h1 id="rec-title">{explanation.headline}</h1>
        <p>{explanation.text}</p>
        <p className="basis">
          {explanation.verified && <span className="badge">Numbers verified</span>}{" "}
          {best && (
            <span>
              Fits your budget: {money(best.monthly_payment)} a month, {money(rec.monthly_room_left)} room left
            </span>
          )}
        </p>
        <NextStep key={rec.path ?? "none"} customerId={customerId} path={rec.path} />
      </section>

      <section className="panel" aria-labelledby="flips-title">
        <h2 id="flips-title">What would change this recommendation</h2>
        {best === undefined ? (
          <p>There is no recommendation yet. Each path below shows what is holding it back.</p>
        ) : data.flips.length === 0 ? (
          <p>Your recommendation holds across every setting of the sliders.</p>
        ) : (
          <ul className="flips">
            {data.flips.map((f) => (
              <li key={f.input}>{f.text}</li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="all-title">
        <div className="panel-head">
          <h2 id="all-title">All your paths</h2>
          <span className="basis">Sorted by 5-year cost</span>
        </div>
        <div className="cards">
          {byCost.map((o) => (
            <PathCard key={o.path} option={o} recommended={o.path === rec.path} closest={o.path === rec.closest_when_none} />
          ))}
        </div>
      </section>

      <section className="panel" aria-labelledby="chart-title">
        <h2 id="chart-title">Cost over time, by path</h2>
        <p className="basis">Cumulative cost per path over 60 months, recommended path highlighted</p>
        <CostChart options={data.options} recommended={rec.path} />
      </section>

      <section className="panel" aria-labelledby="assumptions-title">
        <h2 id="assumptions-title">Assumptions behind these numbers</h2>
        <ul className="assumptions">
          {data.assumptions.map((a) => (
            <li key={a}>{a}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function PathCard({ option: o, recommended, closest }: { option: PathOption; recommended: boolean; closest: boolean }) {
  const classes = ["card", recommended ? "card-recommended" : "", o.eligible ? "" : "card-ineligible"].join(" ");
  return (
    <article className={classes} aria-label={o.label}>
      <header>
        <h3>{o.label}</h3>
        {recommended && <span className="tag">Recommended</span>}
        {closest && <span className="tag">Closest</span>}
        {!o.eligible && <span className="tag">Not eligible</span>}
      </header>
      <dl className="rows">
        <Row label="5-year cost" value={money(o.five_year_cost)} />
        <Row label="Monthly" value={money(o.monthly_payment)} />
        <Row label="Upfront" value={money(o.upfront_cost)} />
      </dl>
      <p className="basis">{o.tradeoff}</p>
      {!o.eligible && o.ineligible_reason && <p className="why">{o.ineligible_reason}</p>}
      {o.eligible && !o.affordable && (
        <ul className="why">
          {o.shortfalls.map((s) => (
            <li key={s.kind}>{s.text}</li>
          ))}
        </ul>
      )}
    </article>
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

function CostChart({ options, recommended }: { options: PathOption[]; recommended: string | null }) {
  const shown = options.filter((o) => o.eligible);
  if (shown.length === 0) return <p>Nothing to chart yet.</p>;
  const months = shown[0].cumulative_cost.length;
  const rows = Array.from({ length: months }, (_, i) => {
    const row: Record<string, number> = { month: i + 1 };
    for (const o of shown) row[o.path] = Number(o.cumulative_cost[i]); // charted as given, never added up here
    return row;
  });
  return (
    <div className="chart" aria-label="Cumulative cost by path over 60 months">
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={rows}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis
            dataKey="month"
            ticks={[1, 12, 24, 36, 48, 60]}
            height={52}
            label={{ value: "Months from today", position: "insideBottom", offset: 0 }}
          />
          <YAxis tickFormatter={(v) => money(String(v))} width={80} />
          <Tooltip formatter={(v) => money(String(v))} labelFormatter={(m) => `Month ${m}`} />
          <Legend verticalAlign="top" />
          {shown.map((o, i) => (
            <Line
              key={o.path}
              type="monotone"
              dataKey={o.path}
              name={o.label}
              stroke={COLORS[i % COLORS.length]}
              strokeWidth={o.path === recommended ? 4 : 1.5}
              dot={false}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
