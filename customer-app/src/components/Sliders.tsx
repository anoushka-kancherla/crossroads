import type { PathsResult } from "../api/client";
import { count, money } from "../format";

type Name = "miles_per_year" | "monthly_budget" | "years_to_keep" | "financing_rate";
export type Values = Record<Name, number>;

/** The slider positions as plain numbers, from the values the server says it used. */
export function valuesOf(used: PathsResult["inputs_used"]): Values {
  return {
    miles_per_year: used.miles_per_year,
    monthly_budget: Number(used.monthly_budget),
    years_to_keep: used.years_to_keep,
    financing_rate: Number(used.financing_rate),
  };
}

type Props = {
  values: Values;
  ranges: PathsResult["ranges"];
  contractType: "lease" | "loan";
  busy: boolean;
  onChange: (next: Values) => void;
  onReset: () => void;
};

/** "Adjust your situation": the four inputs. The ranges and steps come from the server, which also
 *  raises the budget maximum to a customer's own default. */
export function Sliders({ values, ranges, contractType, busy, onChange, onReset }: Props) {
  const rows: { name: Name; label: string; show: (n: number) => string }[] = [
    { name: "miles_per_year", label: "Miles per year", show: count },
    { name: "monthly_budget", label: "Monthly budget", show: (n) => money(String(n)) },
    { name: "years_to_keep", label: "Years you plan to keep a car", show: (n) => String(n) },
    {
      name: "financing_rate",
      label: contractType === "lease" ? "Financing rate" : "Refinance rate",
      show: (n) => `${n}%`,
    },
  ];
  return (
    <section className="panel sliders" aria-labelledby="sliders-title" aria-busy={busy}>
      <h2 id="sliders-title">Adjust your situation</h2>
      {rows.map(({ name, label, show }) => {
        const r = ranges[name];
        if (!r) return null;
        const id = `slider-${name}`;
        return (
          <div className="slider" key={name}>
            <div className="slider-head">
              <label htmlFor={id}>{label}</label>
              <output htmlFor={id}>{show(values[name])}</output>
            </div>
            <input
              id={id}
              type="range"
              min={Number(r.min)}
              max={Number(r.max)}
              step={Number(r.step)}
              value={values[name]}
              aria-valuetext={show(values[name])}
              onChange={(e) => onChange({ ...values, [name]: Number(e.target.value) })}
            />
            <div className="slider-ends">
              <span>{show(Number(r.min))}</span>
              <span>{show(Number(r.max))}</span>
            </div>
          </div>
        );
      })}
      <button type="button" className="secondary" onClick={onReset}>
        Reset to my data
      </button>
      {busy && <p className="basis">Updating…</p>}
    </section>
  );
}
