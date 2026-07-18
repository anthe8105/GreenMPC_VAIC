import { useMemo, useState } from "react";
import { useInvestmentLab } from "../hooks/useInvestmentLab";
import type { InvestmentCandidate } from "../types/api";
import { controllerLabel, scenarioLabel } from "../types/labels";

export function InvestmentLabPage() {
  const lab = useInvestmentLab();
  const [selectedTenant, setSelectedTenant] = useState("all");
  const result = lab.result;
  const tenantRows = result?.tenant_summary ?? [];
  const tenants = Array.from(new Set(tenantRows.map((row) => String(row.tenant_id))));
  const filteredTenantRows = selectedTenant === "all" ? tenantRows : tenantRows.filter((row) => row.tenant_id === selectedTenant);
  const summaryText = useMemo(() => result ? executiveSummary(result) : "", [result]);

  if (!lab.defaults || !lab.candidate || !lab.financial) {
    return <main className="story-page"><section className="loading-panel">Loading Investment Lab assumptions...</section></main>;
  }

  return (
    <main className="story-page investment-page">
      <section className="intro-strip investment-intro">
        <div>
          <p className="section-kicker">Investment Scenario Lab</p>
          <h1>Compare today’s energy system against a cleaner proposal.</h1>
          <p>Run an offline digital-twin analysis, estimate operating impact, and export tenant-level renewable allocation evidence.</p>
        </div>
        <div className="intro-actions">
          <button className="start-button" onClick={lab.runAnalysis} disabled={lab.job?.status === "running"}>Run Investment Analysis</button>
          <button onClick={lab.resetToBaseline}>Reset to Baseline</button>
        </div>
      </section>

      {lab.error && <section className="alert-banner error">{lab.error}</section>}

      <section className="story-section investment-setup">
        <div className="section-heading">
          <p className="section-kicker">1. Define the Target</p>
          <h2>Choose the operating question</h2>
          <p>Baseline values are loaded from the approved GreenMPC configuration and remain immutable during an analysis.</p>
        </div>
        <div className="investment-grid">
          <div className="setup-panel">
            <label>Renewable target
              <input type="number" min="0" max="1" step="0.01" value={lab.candidate.renewable_target_fraction} onChange={(event) => lab.updateCandidate({ renewable_target_fraction: Number(event.target.value) })} />
            </label>
            <label>Scenario
              <select value={lab.scenario} onChange={(event) => lab.setScenario(event.target.value as any)}>
                <option value="normal">{scenarioLabel("normal")}</option>
                <option value="cloudy">{scenarioLabel("cloudy")}</option>
                <option value="production_shift">{scenarioLabel("production_shift")}</option>
                <option value="combined_stress">{scenarioLabel("combined_stress")}</option>
              </select>
            </label>
            <label>Analysis duration
              <select value={lab.durationHours} onChange={(event) => lab.setDurationHours(Number(event.target.value))}>
                <option value={6}>6-hour smoke</option>
                <option value={24}>24-hour quick analysis</option>
                <option value={72}>72-hour evidence analysis</option>
              </select>
            </label>
            <label>Controller
              <select value={lab.controller} onChange={(event) => lab.setController(event.target.value as any)}>
                <option value="deterministic_mpc">{controllerLabel("deterministic_mpc")}</option>
                <option value="greenmpc_conservative">{controllerLabel("greenmpc_conservative")}</option>
                <option value="rule_based">{controllerLabel("rule_based")}</option>
              </select>
            </label>
          </div>
          <BaselineSystem baseline={lab.defaults.baseline} />
        </div>
      </section>

      <section className="story-section">
        <div className="section-heading">
          <p className="section-kicker">2. Configure the Energy System</p>
          <h2>Proposal inputs</h2>
          <p>No global configuration is mutated. These values are applied only to isolated baseline/proposal simulator instances.</p>
        </div>
        <div className="proposal-grid">
          <NumberField label="Rooftop PV capacity" suffix="kW" value={lab.candidate.pv_capacity_kw} onChange={(value) => lab.updateCandidate({ pv_capacity_kw: value })} />
          <NumberField label="BESS energy capacity" suffix="kWh" value={lab.candidate.battery_energy_capacity_kwh} onChange={(value) => lab.updateCandidate({ battery_energy_capacity_kwh: value })} />
          <NumberField label="BESS power rating" suffix="kW" value={lab.candidate.battery_power_kw} onChange={(value) => lab.updateCandidate({ battery_power_kw: value })} />
          <NumberField label="DPPA volume" suffix="kW" value={lab.candidate.dppa_available_kw} onChange={(value) => lab.updateCandidate({ dppa_available_kw: value })} />
          <NumberField label="DPPA price" suffix="VND/kWh" value={lab.candidate.dppa_price_vnd_per_kwh} onChange={(value) => lab.updateCandidate({ dppa_price_vnd_per_kwh: value })} />
          <NumberField label="Terminal battery valuation" suffix="VND/kWh" value={lab.candidate.terminal_inventory_valuation_vnd_per_kwh} onChange={(value) => lab.updateCandidate({ terminal_inventory_valuation_vnd_per_kwh: value })} />
        </div>
        <details className="technical-details">
          <summary>Advanced assumptions</summary>
          <div className="proposal-grid">
            <NumberField label="Transformer capacity" suffix="kW" value={lab.candidate.transformer_capacity_kw} onChange={(value) => lab.updateCandidate({ transformer_capacity_kw: value })} />
            <NumberField label="Minimum SOC" suffix="fraction" value={lab.candidate.minimum_soc_fraction} step={0.01} onChange={(value) => lab.updateCandidate({ minimum_soc_fraction: value })} />
            <NumberField label="Initial SOC" suffix="fraction" value={lab.candidate.initial_soc_fraction} step={0.01} onChange={(value) => lab.updateCandidate({ initial_soc_fraction: value })} />
            <NumberField label="Annual operating days" suffix="days" value={lab.financial.annual_operating_days} onChange={(value) => lab.updateFinancial({ annual_operating_days: value })} />
            <NumberField label="PV CAPEX" suffix="VND/kW" value={lab.financial.pv_capex_vnd_per_kwp} onChange={(value) => lab.updateFinancial({ pv_capex_vnd_per_kwp: value })} />
            <NumberField label="BESS energy CAPEX" suffix="VND/kWh" value={lab.financial.bess_energy_capex_vnd_per_kwh} onChange={(value) => lab.updateFinancial({ bess_energy_capex_vnd_per_kwh: value })} />
          </div>
          <p className="fine-print">Editable demonstration assumptions — not supplier quotations or investment advice.</p>
        </details>
        {!result && (
          <div className="expected-direction">
            <strong>Expected direction</strong>
            <p>More PV can increase renewable supply but may increase curtailment. More BESS can reduce curtailment and peaks but increases CAPEX. More DPPA can raise renewable supply while changing procurement cost depending on the assumed price.</p>
          </div>
        )}
      </section>

      <section className="story-section">
        <div className="section-heading">
          <p className="section-kicker">3. Run the Digital-Twin Analysis</p>
          <h2>Progress</h2>
        </div>
        <ProgressPanel job={lab.job} stale={lab.resultStale} />
      </section>

      {result && (
        <>
          <section className="story-section">
            <div className="section-heading">
              <p className="section-kicker">4. Compare Baseline and Proposal</p>
              <h2>Result storyline</h2>
              <p>{summaryText}</p>
            </div>
            <ComparisonPanels result={result} financialAssumptions={lab.financial} valuationPrice={lab.candidate.terminal_inventory_valuation_vnd_per_kwh} />
          </section>

          <section className="story-section">
            <div className="section-heading">
              <p className="section-kicker">5. Review and Export Tenant Evidence</p>
              <h2>Tenant renewable allocation</h2>
              <p>Uses realized source-level simulator accounting, including renewable battery delivery tracked by the digital twin.</p>
            </div>
            <div className="evidence-toolbar">
              <label>Tenant
                <select value={selectedTenant} onChange={(event) => setSelectedTenant(event.target.value)}>
                  <option value="all">All tenants</option>
                  {tenants.map((tenant) => <option key={tenant} value={tenant}>{readableTenant(tenant)}</option>)}
                </select>
              </label>
              <a className="primary-link" href={`/api/v1/investment/analyses/${result.analysis_id}/export`}>Download evidence ZIP</a>
            </div>
            <div className="tenant-evidence-list">
              {filteredTenantRows.map((row) => (
                <article key={`${row.case}-${row.tenant_id}`} className="tenant-evidence-row">
                  <strong>{readableTenant(String(row.tenant_id))} · {String(row.case)}</strong>
                  <span>Load {num(row.load_served_kwh)} kWh</span>
                  <span>Renewable share {pct(row.renewable_share)}</span>
                  <span>Grid {num(row.grid_energy_kwh)} kWh</span>
                  <span>Shortfall {num(row.shortfall_kwh)} kWh</span>
                </article>
              ))}
            </div>
            <p className="fine-print">Evidence package is scenario-based and is not an official certificate, legal DPPA settlement, or actual VRG operating record.</p>
          </section>
        </>
      )}
    </main>
  );
}

function BaselineSystem({ baseline }: { baseline: InvestmentCandidate }) {
  return (
    <aside className="baseline-panel">
      <p className="section-kicker">Baseline System</p>
      <dl>
        <div><dt>Rooftop PV</dt><dd>{num(baseline.pv_capacity_kw)} kW</dd></div>
        <div><dt>BESS energy</dt><dd>{num(baseline.battery_energy_capacity_kwh)} kWh</dd></div>
        <div><dt>BESS power</dt><dd>{num(baseline.battery_power_kw)} kW</dd></div>
        <div><dt>Transformer</dt><dd>{num(baseline.transformer_capacity_kw)} kW</dd></div>
        <div><dt>DPPA volume</dt><dd>{num(baseline.dppa_available_kw)} kW</dd></div>
        <div><dt>DPPA price</dt><dd>{num(baseline.dppa_price_vnd_per_kwh)} VND/kWh</dd></div>
      </dl>
    </aside>
  );
}

function NumberField({ label, suffix, value, step = 50, onChange }: { label: string; suffix: string; value: number; step?: number; onChange: (value: number) => void }) {
  return (
    <label className="number-field">{label}
      <div>
        <input type="number" step={step} value={value} onChange={(event) => onChange(Number(event.target.value))} />
        <span>{suffix}</span>
      </div>
    </label>
  );
}

function ProgressPanel({ job, stale }: { job: any; stale: boolean }) {
  if (!job) return <p>Adjust the proposal, then run one bounded digital-twin analysis. Physical changes require a new analysis; financial-only sensitivity updates do not mutate simulation results.</p>;
  return (
    <div className="progress-panel">
      <div className="progress-head">
        <strong>{job.current_phase}</strong>
        <span>{job.status}{stale ? " · physical inputs changed since result" : ""}</span>
      </div>
      <div className="progress-track"><div style={{ width: `${Math.max(0, Math.min(100, job.progress_percentage ?? 0))}%` }} /></div>
      <p>{job.completed_hours ?? 0} / {job.requested_hours ?? 0} simulated hours · elapsed {Number(job.elapsed_seconds ?? 0).toFixed(1)}s</p>
    </div>
  );
}

function ComparisonPanels({ result, financialAssumptions, valuationPrice }: { result: any; financialAssumptions: any; valuationPrice: number }) {
  const baseline = withAdjustedInventoryCost(result.technical_metrics.baseline, valuationPrice);
  const proposal = withAdjustedInventoryCost(result.technical_metrics.proposal, valuationPrice);
  const financial = recalculateFinancial(result, financialAssumptions, valuationPrice);
  return (
    <div className="comparison-grid">
      <div>
        <h3>Operating outcome</h3>
        <ComparisonRow label="Inventory-adjusted cost" baseline={baseline.inventory_adjusted_operating_cost_vnd} proposal={proposal.inventory_adjusted_operating_cost_vnd} format={money} />
        <ComparisonRow label="Renewable share" baseline={baseline.park_renewable_share} proposal={proposal.park_renewable_share} format={pct} />
        <ComparisonRow label="Peak grid import" baseline={baseline.peak_grid_import_kw} proposal={proposal.peak_grid_import_kw} format={(v) => `${num(v)} kW`} />
        <ComparisonRow label="Renewable shortfall" baseline={baseline.renewable_shortfall_total_kwh} proposal={proposal.renewable_shortfall_total_kwh} format={(v) => `${num(v)} kWh`} />
      </div>
      <div>
        <h3>Energy source mix</h3>
        <SourceMix label="Baseline" metrics={baseline} />
        <SourceMix label="Proposal" metrics={proposal} />
      </div>
      <div>
        <h3>Financial summary</h3>
        <dl className="financial-list">
          <div><dt>Incremental CAPEX</dt><dd>{money(financial.incremental_capex_vnd)}</dd></div>
          <div><dt>Annualized gross savings</dt><dd>{money(financial.annualized_operating_savings_vnd)}</dd></div>
          <div><dt>Annual O&M change</dt><dd>{money(financial.incremental_annual_om_vnd)}</dd></div>
          <div><dt>Net annual savings</dt><dd>{money(financial.net_annual_savings_vnd)}</dd></div>
          <div><dt>Simple payback</dt><dd>{financial.simple_payback_years ? `${Number(financial.simple_payback_years).toFixed(1)} years` : financial.payback_status}</dd></div>
        </dl>
      </div>
    </div>
  );
}

function recalculateFinancial(result: any, financial: any, valuationPrice: number) {
  const baseline = result.baseline_configuration;
  const proposal = result.proposal_configuration;
  const baselineCapex = assetCapex(baseline, financial);
  const proposalCapex = assetCapex(proposal, financial);
  const incrementalCapex = proposalCapex - baselineCapex;
  const baselineCost = withAdjustedInventoryCost(result.technical_metrics.baseline, valuationPrice).inventory_adjusted_operating_cost_vnd;
  const proposalCost = withAdjustedInventoryCost(result.technical_metrics.proposal, valuationPrice).inventory_adjusted_operating_cost_vnd;
  const periodSavings = baselineCost - proposalCost;
  const annualizedSavings = periodSavings * Number(financial.annual_operating_days) * 24 / Number(result.duration_hours);
  const incrementalOm = annualOm(proposal, financial) - annualOm(baseline, financial);
  const netAnnualSavings = annualizedSavings - incrementalOm;
  return {
    incremental_capex_vnd: incrementalCapex,
    annualized_operating_savings_vnd: annualizedSavings,
    incremental_annual_om_vnd: incrementalOm,
    net_annual_savings_vnd: netAnnualSavings,
    simple_payback_years: incrementalCapex > 0 && netAnnualSavings > 0 ? incrementalCapex / netAnnualSavings : null,
    payback_status: incrementalCapex > 0 && netAnnualSavings > 0 ? "calculated" : "no payback under current assumptions"
  };
}

function withAdjustedInventoryCost(metrics: any, valuationPrice: number) {
  const energyChange = Number(metrics.final_battery_energy_kwh ?? 0) - Number(metrics.initial_battery_energy_kwh ?? 0);
  return {
    ...metrics,
    terminal_inventory_adjustment_vnd: -energyChange * Number(valuationPrice),
    inventory_adjusted_operating_cost_vnd: Number(metrics.raw_operating_cost_vnd ?? metrics.total_realized_operating_cost_proxy_vnd ?? 0) - energyChange * Number(valuationPrice)
  };
}

function assetCapex(candidate: any, financial: any) {
  return Number(candidate.pv_capacity_kw) * Number(financial.pv_capex_vnd_per_kwp)
    + Number(candidate.battery_energy_capacity_kwh) * Number(financial.bess_energy_capex_vnd_per_kwh)
    + Number(candidate.battery_power_kw) * Number(financial.bess_power_capex_vnd_per_kw)
    + Number(financial.fixed_implementation_cost_vnd ?? 0);
}

function annualOm(candidate: any, financial: any) {
  const pv = Number(candidate.pv_capacity_kw) * Number(financial.pv_capex_vnd_per_kwp) * Number(financial.annual_pv_om_fraction ?? 0);
  const battery = (
    Number(candidate.battery_energy_capacity_kwh) * Number(financial.bess_energy_capex_vnd_per_kwh)
    + Number(candidate.battery_power_kw) * Number(financial.bess_power_capex_vnd_per_kw)
  ) * Number(financial.annual_bess_om_fraction ?? 0);
  return pv + battery;
}

function ComparisonRow({ label, baseline, proposal, format }: { label: string; baseline: number; proposal: number; format: (value: number) => string }) {
  return <div className="comparison-row"><span>{label}</span><strong>{format(baseline)}</strong><strong>{format(proposal)}</strong></div>;
}

function SourceMix({ label, metrics }: { label: string; metrics: Record<string, number> }) {
  const total = Math.max(1, Number(metrics.total_load_served_kwh ?? 0));
  const parts = [
    ["Solar", metrics.direct_pv_delivery_kwh ?? 0, "#0f766e"],
    ["DPPA", metrics.realized_dppa_energy_kwh ?? 0, "#d97706"],
    ["Battery", metrics.battery_delivery_kwh ?? 0, "#4f46e5"],
    ["Grid", metrics.realized_grid_energy_kwh ?? 0, "#2563eb"]
  ];
  return (
    <div className="source-mix">
      <span>{label}</span>
      <div>{parts.map(([name, value, color]) => <i key={String(name)} title={`${name}: ${num(value)} kWh`} style={{ width: `${100 * Number(value) / total}%`, background: String(color) }} />)}</div>
    </div>
  );
}

function executiveSummary(result: any) {
  const b = result.technical_metrics.baseline;
  const p = result.technical_metrics.proposal;
  const renewableDelta = 100 * (Number(p.park_renewable_share) - Number(b.park_renewable_share));
  const peakDelta = Number(p.peak_grid_import_kw) - Number(b.peak_grid_import_kw);
  const savings = Number(result.financial_metrics.annualized_operating_savings_vnd);
  return `The proposed system changes renewable share by ${renewableDelta.toFixed(1)} percentage points, changes peak grid import by ${peakDelta.toFixed(0)} kW, and changes annualized operating cost by ${money(savings)} under the selected assumptions.`;
}

function readableTenant(id: string) {
  return id.replace("_", " ");
}

function num(value: unknown) {
  return Number(value ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function money(value: unknown) {
  return `${(Number(value ?? 0) / 1_000_000).toLocaleString(undefined, { maximumFractionDigits: 2 })}M VND`;
}

function pct(value: unknown) {
  return `${(Number(value ?? 0) * 100).toFixed(1)}%`;
}
