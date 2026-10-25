import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { pathRoles, roleColor } from "../brand/chartColors";
import { endLabel } from "../brand/chartLabels";
import { CountUp } from "../brand/CountUp";
import { StatusMessage } from "../brand/StatusMessage";
import { useResort } from "../brand/useResort";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type PathOption, type PathsResult } from "../api/client";
import { AskBox } from "../components/AskBox";
import { NextStep } from "../components/NextStep";
import { QueryState } from "../components/QueryState";
import { Sliders, type Values, valuesOf } from "../components/Sliders";
import { useCustomer } from "../CustomerContext";
import { money } from "../format";

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
        {paths.isError && (
          <StatusMessage variant="critical" label="Error">
            {paths.error.message}
          </StatusMessage>
        )}
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
  const cardsRef = useResort<HTMLDivElement>(byCost.map((o) => o.path).join(","));

  return (
    <div className="paths">
      <section className="panel recommend" aria-labelledby="rec-title">
        <div className="recommend-head">
          <p className="eyebrow">{best ? "Recommended next move" : "No path fits yet"}</p>
          {explanation.verified && <StatusMessage variant="positive" label="Numbers verified" />}
        </div>
        <h1 id="rec-title">{explanation.headline}</h1>
        {best && (
          <p className="hero-row">
            <CountUp className="hero" value={money(best.five_year_cost)} />
            <span className="basis">5-year cost</span>
          </p>
        )}
        <p>{explanation.text}</p>
        {best && (
          <p className="basis">
            Fits your budget: {money(best.monthly_payment)} a month, {money(rec.monthly_room_left)} room left
          </p>
        )}
        <NextStep key={rec.path ?? "none"} customerId={customerId} path={rec.path} inputs={data.inputs_used} />
      </section>

      <AskBox customerId={customerId} inputs={data.inputs_used} />

      <section className="panel flips-band" aria-labelledby="flips-title">
        <h2 id="flips-title">
          <svg className="info-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
            <path d="M12 3a9 9 0 100 18 9 9 0 000-18zM12 11v6M12 7.5v.5" />
          </svg>
          What would change this recommendation
        </h2>
        {best === undefined ? (
          <p>Nothing is recommended yet. Each path below shows what's holding it back.</p>
        ) : data.flips.length === 0 ? (
          <p>Your recommendation stays the same at every slider setting.</p>
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
        <div className="cards" ref={cardsRef}>
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
        <h2 id="assumptions-title">Illustrative assumptions</h2>
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
    <article className={classes} aria-label={o.label} data-resort-key={o.path}>
      <header>
        <h3>{o.label}</h3>
        {recommended && <span className="tag">Recommended</span>}
        {closest && <span className="tag">Closest</span>}
        {!o.eligible && <span className="tag">Not eligible</span>}
      </header>
      <dl className="rows">
        <Row label="5-year cost" value={<CountUp value={money(o.five_year_cost)} />} />
        <Row label="Monthly" value={money(o.monthly_payment)} />
        <Row label="Upfront" value={money(o.upfront_cost)} />
      </dl>
      <p className="basis">{o.tradeoff}</p>
      {o.why_not && (
        <div className="why-not">
          <p className="why-not-label">Why not this one?</p>
          {!o.eligible ? (
            <StatusMessage variant="warning" label="Unavailable">
              {o.why_not}
            </StatusMessage>
          ) : !o.affordable ? (
            <StatusMessage variant="warning" label="Shortfall">
              {o.why_not}
            </StatusMessage>
          ) : (
            <p className="why-not-line">{o.why_not}</p>
          )}
        </div>
      )}
    </article>
  );
}

function Row({ label, value }: { label: string; value: ReactNode }) {
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
  const roles = pathRoles(shown.map((o) => o.path), recommended);
  // Label a line at its end only where it will not sit on top of another label; the legend names every line.
  const top = Math.max(...shown.map((o) => Number(o.cumulative_cost[months - 1])));
  const labelled = new Set<string>();
  const taken: number[] = [];
  const byPriority = [...shown].sort(
    (a, b) => Number(b.path === recommended) - Number(a.path === recommended) || Number(b.cumulative_cost[months - 1]) - Number(a.cumulative_cost[months - 1]),
  );
  for (const o of byPriority) {
    const end = Number(o.cumulative_cost[months - 1]);
    if (taken.every((t) => Math.abs(t - end) / top > 0.08)) {
      labelled.add(o.path);
      taken.push(end);
    }
  }
  return (
    <div className="chart" aria-label="Cumulative cost by path over 60 months">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={{ right: 170 }}>
          <CartesianGrid stroke={roleColor("grid")} strokeDasharray="3 3" />
          <XAxis
            dataKey="month"
            ticks={[1, 12, 24, 36, 48, 60]}
            height={52}
            label={{ value: "Months from today", position: "insideBottom", offset: 0 }}
          />
          <YAxis tickFormatter={(v) => money(String(v))} width={80} />
          <Tooltip formatter={(v) => money(String(v))} labelFormatter={(m) => `Month ${m}`} />
          <Legend verticalAlign="top" />
          {shown.map((o) => (
            <Line
              key={o.path}
              type="monotone"
              dataKey={o.path}
              name={o.label}
              stroke={roleColor(roles[o.path])}
              strokeWidth={o.path === recommended ? 4 : 2}
              dot={false}
              isAnimationActive={false}
              label={labelled.has(o.path) ? endLabel(o.label, months - 1) : undefined}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
