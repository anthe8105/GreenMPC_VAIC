import type { CommandState } from "../types/api";

export function KpiCards({ state }: { state: CommandState }) {
  const kpis = state.kpis;
  const items = [
    ["Park demand", kw(kpis.park_load_kw)],
    ["Renewable share", percent(kpis.renewable_share_fraction)],
    ["Battery SOC", percent(kpis.battery_soc_fraction)],
    ["Operating cost", `${millions(kpis.operating_cost_vnd)}M VND`]
  ];
  return (
    <section className="headline-metrics" aria-label="Live headline metrics">
      {items.map(([label, value], index) => (
        <div key={label} className="headline-metric">
          {index > 0 && <span className="metric-separator" aria-hidden="true" />}
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </section>
  );
}

function number(value: unknown) {
  return Number(value ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function kw(value: unknown) {
  return `${number(value)} kW`;
}

function percent(value: unknown) {
  return `${(Number(value ?? 0) * 100).toFixed(1)}%`;
}

function millions(value: unknown) {
  return (Number(value ?? 0) / 1_000_000).toLocaleString(undefined, { maximumFractionDigits: 2 });
}
