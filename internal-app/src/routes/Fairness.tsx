import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { UnauthorizedError, api, type FairnessReport } from "../api/client";
import { QueryState } from "../components/QueryState";
import { count, dateLabel, money } from "../format";

const HEADLINES = {
  no_evidence: "No evidence of steering",
  possible_steering: "Possible steering, to be reviewed",
  not_enough: "Not enough customers to tell",
} as const;

const TYPE_LABELS = { loan: "Loan customers", lease: "Lease customers" } as const;

type Band = FairnessReport["bands"][number];

/** A rank or gap in points, with its sign shown. Figures arrive as exact decimal strings. */
const points = (v: string | null) => (v === null ? "not enough customers" : `${v} points`);
const SEPARATE = "A separate matter from steering; not part of the verdict";

/** What to show where a band has no figure: no customers at all, or too few with a recommendation or a choice. */
const unavailable = (b: Band) => (b.customers === 0 ? "No customers" : "Not enough customers");

/** The fairness check (feature 002): band-level figures on a separate synthetic population. Every figure
 *  and sentence comes from the server; nothing here is computed or softened. */
export default function Fairness() {
  const qc = useQueryClient();
  const report = useQuery({ queryKey: ["fairness"], queryFn: api.fairness, retry: false });

  // An expired session sends staff back to sign-in and drops every figure from memory.
  const expired = report.error instanceof UnauthorizedError;
  useEffect(() => {
    if (!expired) return;
    qc.removeQueries({ queryKey: ["fairness"] });
    qc.setQueryData(["session"], null);
  }, [expired, qc]);
  if (expired) return null;

  return (
    <QueryState
      status={report.status}
      error={report.error}
      data={report.data}
      isEmpty={(d) => d.empty}
      emptyMessage="No fairness figures are available yet: the synthetic population has no customers."
    >
      {(data) => <Report data={data} />}
    </QueryState>
  );
}

function Report({ data }: { data: FairnessReport }) {
  const [lowest, , highest] = data.bands;
  return (
    <>
      <h1>Fairness check: are lower-income customers steered toward paths that earn Toyota more?</h1>
      <p className="subtitle">
        A separate synthetic population of {count(data.population.size)} customers, not the 12 demo customers · computed{" "}
        {dateLabel(data.computed_at)}
      </p>
      {data.verdict && <VerdictPanel verdict={data.verdict} />}
      <section className="panel" aria-label="Income bands">
        <h2>Recommendations by income band</h2>
        <table>
          <thead>
            <tr>
              <th>Income band</th>
              <th className="num">Customers</th>
              <th className="num">With a recommendation</th>
              <th className="num">No affordable option</th>
              <th>Recommended paths</th>
              <th className="num">Average profitability rank</th>
            </tr>
          </thead>
          <tbody>
            {data.bands.map((b) => (
              <tr key={b.key}>
                <td>{b.label}</td>
                <td className="num">{count(b.customers)}</td>
                <td className="num">{count(b.with_recommendation)}</td>
                <td className="num">{count(b.no_affordable)}</td>
                <td>{b.path_counts.map((p) => `${p.label} ${count(p.customers)}`).join(" · ") || "none"}</td>
                <td className="num">
                  {b.avg_rank_pct === null
                    ? unavailable(b)
                    : `${b.avg_rank_pct}% (from ${count(b.avg_rank_n)} customers with a real choice)`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="note">
          Profitability rank: where the recommended path sits among that customer's own affordable options by
          Toyota's 5-year interest income. 0% is the least profitable option, 100% the most, 50% is neutral.
        </p>
        <div className="chart" aria-label="Average profitability rank by band">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={data.bands.map((b) => ({ band: b.label, rank: b.avg_rank_pct === null ? 0 : Number(b.avg_rank_pct) }))}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="band" />
              <YAxis domain={[0, 100]} unit="%" />
              <Tooltip />
              <ReferenceLine y={50} stroke="#111" strokeDasharray="6 3" label="Neutral 50%" />
              <Bar dataKey="rank" name="Average rank" fill="#444" />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="warning" role="note">
          Results on a small band are uncertain. The number of customers behind every average and share is shown
          beside it.
        </div>
      </section>
      <Evidence bands={data.bands} />
      <PerType data={data} />
      <Limits data={data} lowest={lowest} highest={highest} />
    </>
  );
}

function VerdictPanel({ verdict }: { verdict: NonNullable<FairnessReport["verdict"]> }) {
  return (
    <section className="verdict" aria-label="Verdict">
      <h2>{HEADLINES[verdict.outcome]}</h2>
      <p>{verdict.sentence}</p>
      {verdict.interval_note && <p>{verdict.interval_note}</p>}
      {verdict.gap_points !== null && (
        <p className="figures">
          Gap, lowest minus highest income band: {points(verdict.gap_points)} (95% interval {verdict.ci_low} to{" "}
          {verdict.ci_high}), from {count(verdict.lowest_n)} and {count(verdict.highest_n)} customers with a real
          choice.
        </p>
      )}
    </section>
  );
}

function Evidence({ bands }: { bands: Band[] }) {
  return (
    <section className="panel" aria-label="Evidence">
      <h2>The evidence behind it</h2>
      <table>
        <thead>
          <tr>
            <th>Income band</th>
            <th className="num">Recommended Toyota's most profitable option</th>
            <th className="num">Interest income given up, per customer</th>
            <th className="num">
              Average affordable options
              <div className="note">{SEPARATE}</div>
            </th>
            <th className="num">
              Share with no affordable option
              <div className="note">{SEPARATE}</div>
            </th>
            <th className="num">Average interest income</th>
          </tr>
        </thead>
        <tbody>
          {bands.map((b) => (
            <tr key={b.key}>
              <td>{b.label}</td>
              <td className="num">
                {b.with_choice === 0
                  ? unavailable(b)
                  : `${count(b.most_profitable_count)} of ${count(b.with_choice)} with a real choice`}
              </td>
              <td className="num">
                {b.avg_given_up === null ? unavailable(b) : `${money(b.avg_given_up)} (from ${count(b.with_choice)} customers)`}
              </td>
              <td className="num">
                {b.avg_affordable_options === null
                  ? unavailable(b)
                  : `${b.avg_affordable_options} (from ${count(b.customers)} customers)`}
              </td>
              <td className="num">
                {b.no_affordable_share_pct === null
                  ? unavailable(b)
                  : `${b.no_affordable_share_pct}% (of ${count(b.customers)} customers)`}
              </td>
              <td className="num">
                {b.avg_revenue === null ? unavailable(b) : `${money(b.avg_revenue)} (from ${count(b.avg_revenue_n)} customers)`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="note">
        Average interest income reflects contract size as well as recommendations and is not the steering measure.
        Customers with only one affordable option have no real choice, so they are left out of the rank and the
        most-profitable count.
      </p>
    </section>
  );
}

function PerType({ data }: { data: FairnessReport }) {
  return (
    <section className="panel" aria-label="Loan and lease">
      <h2>The same gap for loan and lease customers</h2>
      <p className="note">
        Evidence only, not scored: these do not change the verdict above. They show whether a gap sits in one kind of
        contract.
      </p>
      <table>
        <thead>
          <tr>
            <th>Customers</th>
            <th className="num">Gap, lowest minus highest band</th>
            <th>95% interval</th>
            <th className="num">Customers with a real choice (lowest, highest)</th>
          </tr>
        </thead>
        <tbody>
          {data.by_type.map((g) => (
            <tr key={g.scope}>
              <td>{TYPE_LABELS[g.scope]}</td>
              <td className="num">{g.enough ? points(g.gap_points) : "Not enough customers"}</td>
              <td>{g.enough ? `${g.ci_low} to ${g.ci_high}` : "none"}</td>
              <td className="num">
                {count(g.lowest_n)} and {count(g.highest_n)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function Limits({ data, lowest, highest }: { data: FairnessReport; lowest: Band; highest: Band }) {
  const t = data.thresholds;
  return (
    <section className="panel" aria-label="What this check does and does not show">
      <h2>What this check does and does not show</h2>
      <ul className="limits">
        <li>Income bands: {data.bands.map((b) => b.label).join("; ")}. A customer exactly on a boundary joins the higher band.</li>
        <li>
          Verdict rule: "possible steering" when the lowest-income band's average rank is more than {t.gap_points}{" "}
          points above the highest-income band's; otherwise "no evidence". If either compared band has fewer than{" "}
          {t.min_choice} customers with a real choice ({count(lowest.with_choice)} and {count(highest.with_choice)}{" "}
          here), the verdict is "not enough customers to tell".
        </li>
        <li>
          Interval method: percentile bootstrap, {count(t.resamples)} resamples, {t.confidence_pct}% interval, fixed
          seed {t.bootstrap_seed}.
        </li>
        <li>
          Population: {count(data.population.size)} synthetic customers ({count(data.population.loans)} loans,{" "}
          {count(data.population.leases)} leases), generated from fixed seed {data.population.seed}.
        </li>
        <li>As of {dateLabel(data.computed_at)}.</li>
      </ul>
      <h3>How the population was built</h3>
      <ul className="limits">
        {data.population.description.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      <ul className="limits">
        {data.limits.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    </section>
  );
}
