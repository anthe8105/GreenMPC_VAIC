export function ScenarioBenchmarkPage({
  benchmark,
  provenance,
  valuationPrice,
  setValuationPrice
}: {
  benchmark: Record<string, unknown> | null;
  provenance: Record<string, unknown> | null;
  valuationPrice: number;
  setValuationPrice: (value: number) => void;
}) {
  const rows = Array.isArray(benchmark?.rows) ? benchmark.rows as Array<Record<string, unknown>> : [];
  const data = (provenance?.data ?? {}) as Record<string, unknown>;
  const disclosures = Array.isArray(data.disclosures) ? data.disclosures as string[] : [];
  return (
    <main className="story-page">
      <section className="story-section">
        <div>
          <p className="section-kicker">Results and Evidence</p>
          <h1>Controller benchmark evidence</h1>
          <p>Read-only Stage 6 realized histories. Changing valuation recalculates terminal battery inventory diagnostics only.</p>
        </div>
        <label className="valuation-select">Terminal valuation
          <select value={valuationPrice} onChange={(event) => setValuationPrice(Number(event.target.value))}>
            <option value={1100}>1,100 VND/kWh</option>
            <option value={1500}>1,500 VND/kWh</option>
            <option value={2000}>2,000 VND/kWh</option>
            <option value={2500}>2,500 VND/kWh</option>
          </select>
        </label>
      </section>

      <section className="story-section">
        <h2>Controller comparison by scenario</h2>
        <div className="benchmark-grid" role="table" aria-label="controller benchmark comparison">
          <div className="table-head">Scenario</div>
          <div className="table-head">Controller</div>
          <div className="table-head">Raw cost</div>
          <div className="table-head">Inventory-adjusted cost</div>
          <div className="table-head">Renewable share</div>
          <div className="table-head">Peak grid</div>
          <div className="table-head">Fallbacks</div>
          {rows.map((row, index) => (
            <BenchmarkRow key={index} row={row} />
          ))}
        </div>
      </section>

      <section className="story-section subtle-section">
        <h2>How to interpret the results</h2>
        <p>Rule-based is the transparent baseline. Deterministic MPC is the stable operational default. Conservative GreenMPC is a quantile-conservative stress comparison and may fall back under hard forecast infeasibility.</p>
        <p>No controller is universally best. Raw operating cost is unchanged by the terminal inventory diagnostic.</p>
      </section>

      <section className="story-section subtle-section">
        <h2>Data trust and provenance</h2>
        <div className="provenance-line">
          <span>Dataset version: <strong>{String(data.dataset_version ?? "unknown")}</strong></span>
          <span>Model registry: <strong>{String(data.model_version ?? "unknown")}</strong></span>
          <span>PV formula: <strong>{String(data.pv_formula_version ?? "simple_capacity_factor_v2")}</strong></span>
        </div>
        <ul className="disclosure-list">
          {disclosures.map((item) => <li key={item}>{item}</li>)}
          <li>NASA POWER weather and irradiance are public source inputs; PV is derived rather than measured inverter output.</li>
          <li>Tariff, DPPA volume, DPPA price, tenant labels, tenant scaling, and stress events are transparent scenario assumptions.</li>
        </ul>
      </section>
    </main>
  );
}

function BenchmarkRow({ row }: { row: Record<string, unknown> }) {
  return (
    <>
      <div>{String(row.scenario_id ?? "")}</div>
      <div>{String(row.controller_id ?? "")}</div>
      <div>{money(row.total_realized_operating_cost_vnd ?? row.total_operating_cost_vnd)}</div>
      <div>{money(row.inventory_adjusted_operating_cost_vnd)}</div>
      <div>{pct(row.renewable_share_fraction ?? row.park_renewable_share)}</div>
      <div>{kw(row.peak_grid_import_kw)}</div>
      <div>{String(row.fallback_count ?? 0)}</div>
    </>
  );
}

function money(value: unknown) {
  return `${(Number(value ?? 0) / 1_000_000).toFixed(2)}M VND`;
}

function pct(value: unknown) {
  return `${(Number(value ?? 0) * 100).toFixed(1)}%`;
}

function kw(value: unknown) {
  return `${Number(value ?? 0).toFixed(0)} kW`;
}
