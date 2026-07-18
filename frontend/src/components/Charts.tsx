import type { ForecastPayload, CommandState } from "../types/api";

export function ForecastPanel({ forecast, state }: { forecast: ForecastPayload | null; state: CommandState }) {
  if (!forecast?.aggregate?.length) {
    return (
      <div className="empty-guidance">
        <strong>Forecast appears here during the first live cycle.</strong>
        <span>Press Start Live Demo and GreenMPC will forecast demand and solar availability for the next six hours.</span>
      </div>
    );
  }
  const load = forecast.aggregate.filter((row) => row.series === "Total load");
  const solar = forecast.aggregate.filter((row) => row.series === "Solar PV");
  const allValues = [...load, ...solar].flatMap((row) => [row.p10_kw, row.p50_kw, row.p90_kw, Number(row.current_observed_kw ?? 0)]);
  const maxY = Math.max(1, ...allValues.map(Number)) * 1.12;
  const loadPeak = maxRow(load);
  const solarPeak = maxRow(solar);
  return (
    <div className="forecast-card">
      <div className="insight-row">
        <Insight label="Demand insight" value={`Demand is expected to peak at ${kw(loadPeak?.p50_kw)} around t+${loadPeak?.horizon_hours ?? 0}.`} />
        <Insight label="Solar insight" value={`Solar availability is expected to reach ${kw(solarPeak?.p50_kw)} around t+${solarPeak?.horizon_hours ?? 0}.`} />
      </div>
      <svg viewBox="0 0 920 360" className="forecast-chart" role="img" aria-label="six hour load and solar forecast">
        <line x1="70" x2="875" y1="300" y2="300" className="axis" />
        <line x1="70" x2="70" y1="40" y2="300" className="axis" />
        {[0, 0.25, 0.5, 0.75, 1].map((tick) => (
          <g key={tick}>
            <line x1="70" x2="875" y1={300 - tick * 260} y2={300 - tick * 260} className="grid-line" />
            <text x="54" y={304 - tick * 260} className="axis-text">{Math.round(maxY * tick).toLocaleString()}</text>
          </g>
        ))}
        <ForecastBand rows={load} maxY={maxY} className="load-band" />
        <ForecastBand rows={solar} maxY={maxY} className="solar-band" />
        <ForecastLine rows={load} maxY={maxY} className="load-line" />
        <ForecastLine rows={solar} maxY={maxY} className="solar-line" />
        {load.map((row, index) => <text key={index} x={x(index)} y="326" className="axis-text">t+{row.horizon_hours}</text>)}
        <circle cx="70" cy={y(Number(state.kpis.park_load_kw ?? 0), maxY)} r="5" className="load-dot" />
        <circle cx="70" cy={y(Number(state.kpis.pv_available_kw ?? 0), maxY)} r="5" className="solar-dot" />
        <g transform="translate(660 36)">
          <rect width="205" height="58" rx="10" className="legend-box" />
          <line x1="14" x2="46" y1="20" y2="20" className="load-line" /><text x="55" y="24" className="legend-text">Load P50 + P10-P90</text>
          <line x1="14" x2="46" y1="42" y2="42" className="solar-line" /><text x="55" y="46" className="legend-text">Solar P50 + P10-P90</text>
        </g>
      </svg>
    </div>
  );
}

function ForecastBand({ rows, maxY, className }: { rows: Array<Record<string, any>>; maxY: number; className: string }) {
  if (!rows.length) return null;
  const upper = rows.map((row, index) => `${x(index)},${y(Number(row.p90_kw), maxY)}`).join(" ");
  const lower = rows.slice().reverse().map((row, reverseIndex) => `${x(rows.length - 1 - reverseIndex)},${y(Number(row.p10_kw), maxY)}`).join(" ");
  return <polygon points={`${upper} ${lower}`} className={className} />;
}

function ForecastLine({ rows, maxY, className }: { rows: Array<Record<string, any>>; maxY: number; className: string }) {
  const d = rows.map((row, index) => `${index === 0 ? "M" : "L"}${x(index)},${y(Number(row.p50_kw), maxY)}`).join(" ");
  return <path d={d} className={className} />;
}

export function HistoryPanel({
  state,
  completedHours,
  fallbackCount,
  invalidActionCount
}: {
  state: CommandState;
  completedHours: number;
  fallbackCount: number;
  invalidActionCount: number;
}) {
  const rows = state.history.slice(-24);
  if (!rows.length) {
    return (
      <div className="empty-guidance">
        <strong>The outcome timeline will grow after the first executed hour.</strong>
        <span>This chart shows demand served, grid import, renewable supply, battery power, and SOC over the live run.</span>
      </div>
    );
  }
  const maxY = Math.max(1, ...rows.flatMap((row) => [Number(row.park_load_kw ?? 0), Number(row.grid_import_kw ?? 0), Number(row.dppa_import_kw ?? 0), Number(row.pv_to_tenants_kw ?? 0)])) * 1.12;
  return (
    <div className="outcome-layout">
      <svg viewBox="0 0 920 320" className="history-chart" role="img" aria-label="executed operating history timeline">
        <line x1="64" x2="880" y1="260" y2="260" className="axis" />
        <line x1="64" x2="64" y1="40" y2="260" className="axis" />
        <HistoryLine rows={rows} field="park_load_kw" maxY={maxY} className="load-line" />
        <HistoryLine rows={rows} field="grid_import_kw" maxY={maxY} className="grid-line-series" />
        <HistoryLine rows={rows} field="dppa_import_kw" maxY={maxY} className="dppa-line-series" />
        <HistoryLine rows={rows} field="battery_power_kw" maxY={maxY} className="battery-line-series" />
        <g transform="translate(612 34)">
          <rect width="260" height="78" rx="10" className="legend-box" />
          <text x="14" y="24" className="legend-text">Demand / Grid / DPPA / Battery power</text>
          <text x="14" y="50" className="legend-text">One point per executed simulated hour</text>
        </g>
      </svg>
      <div className="outcome-copy">
        <p>This timeline shows how GreenMPC has supplied demand and adapted its source mix during the simulated operating period.</p>
        <div className="outcome-metrics">
          <span><strong>{completedHours}</strong> simulated hours</span>
          <span><strong>{money(state.kpis.operating_cost_vnd)}</strong> operating cost</span>
          <span><strong>{kw(state.kpis.grid_import_kw_last_peak)}</strong> grid peak</span>
          <span><strong>{kwh(state.kpis.renewable_energy_to_tenants_kwh)}</strong> renewable energy</span>
          <span><strong>{kwh(state.kpis.renewable_shortfall_kwh)}</strong> renewable shortfall</span>
          <span><strong>{fallbackCount}</strong> fallbacks · <strong>{invalidActionCount}</strong> invalid actions</span>
        </div>
      </div>
    </div>
  );
}

function HistoryLine({ rows, field, maxY, className }: { rows: Array<Record<string, any>>; field: string; maxY: number; className: string }) {
  const d = rows.map((row, index) => `${index === 0 ? "M" : "L"}${70 + index * (780 / Math.max(1, rows.length - 1))},${260 - (Number(row[field] ?? 0) / maxY) * 210}`).join(" ");
  return <path d={d} className={className} />;
}

function Insight({ label, value }: { label: string; value: string }) {
  return <div className="forecast-insight"><span>{label}</span><strong>{value}</strong></div>;
}

function maxRow(rows: Array<Record<string, any>>) {
  return rows.reduce((best, row) => Number(row.p50_kw) > Number(best?.p50_kw ?? -1) ? row : best, rows[0]);
}

function x(index: number) {
  return 90 + index * 126;
}

function y(value: number, maxY: number) {
  return 300 - (value / maxY) * 250;
}

function kw(value: unknown) {
  return `${Number(value ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })} kW`;
}

function kwh(value: unknown) {
  return `${Number(value ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })} kWh`;
}

function money(value: unknown) {
  return `${(Number(value ?? 0) / 1_000_000).toFixed(2)}M VND`;
}
