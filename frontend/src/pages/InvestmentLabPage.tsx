import { useMemo, useState } from "react";
import { useInvestmentLab } from "../hooks/useInvestmentLab";
import type { InvestmentCandidate } from "../types/api";
import { useI18n } from "../i18n/LanguageContext";
import type { I18n } from "../i18n/LanguageContext";

export function InvestmentLabPage() {
  const { t } = useI18n();
  const lab = useInvestmentLab();
  const [selectedTenant, setSelectedTenant] = useState("all");
  const result = lab.result;
  const tenantRows = result?.tenant_summary ?? [];
  const tenants = Array.from(new Set(tenantRows.map((row) => String(row.tenant_id))));
  const filteredTenantRows = selectedTenant === "all" ? tenantRows : tenantRows.filter((row) => row.tenant_id === selectedTenant);
  const summaryText = useMemo(() => result ? executiveSummary(result, t) : "", [result, t]);

  if (!lab.defaults || !lab.candidate || !lab.financial) {
    return <main className="story-page"><section className="loading-panel">{t("inv.loading")}</section></main>;
  }

  return (
    <main className="story-page investment-page">
      <section className="intro-strip investment-intro">
        <div>
          <p className="section-kicker">{t("inv.kicker")}</p>
          <h1>{t("inv.h1")}</h1>
          <p>{t("inv.intro")}</p>
        </div>
        <div className="intro-actions">
          <button className="start-button" onClick={lab.runAnalysis} disabled={lab.job?.status === "running"}>{t("inv.run")}</button>
          <button onClick={lab.resetToBaseline}>{t("inv.resetBaseline")}</button>
        </div>
      </section>

      {lab.error && <section className="alert-banner error">{lab.error}</section>}

      <section className="story-section investment-setup">
        <div className="section-heading">
          <p className="section-kicker">{t("inv.step1")}</p>
          <h2>{t("inv.step1Title")}</h2>
          <p>{t("inv.step1Desc")}</p>
        </div>
        <div className="investment-grid">
          <div className="setup-panel">
            <label>{t("inv.renewableTarget")}
              <input type="number" min="0" max="1" step="0.01" value={lab.candidate.renewable_target_fraction} onChange={(event) => lab.updateCandidate({ renewable_target_fraction: Number(event.target.value) })} />
            </label>
            <label>{t("inv.scenario")}
              <select value={lab.scenario} onChange={(event) => lab.setScenario(event.target.value as any)}>
                <option value="normal">{t("scenario.normal")}</option>
                <option value="cloudy">{t("scenario.cloudy")}</option>
                <option value="production_shift">{t("scenario.production_shift")}</option>
                <option value="combined_stress">{t("scenario.combined_stress")}</option>
              </select>
            </label>
            <label>{t("inv.duration")}
              <select value={lab.durationHours} onChange={(event) => lab.setDurationHours(Number(event.target.value))}>
                <option value={6}>{t("inv.dur6")}</option>
                <option value={24}>{t("inv.dur24")}</option>
                <option value={72}>{t("inv.dur72")}</option>
              </select>
            </label>
            <label>{t("inv.controller")}
              <select value={lab.controller} onChange={(event) => lab.setController(event.target.value as any)}>
                <option value="deterministic_mpc">{t("controller.deterministic_mpc")}</option>
                <option value="greenmpc_conservative">{t("controller.greenmpc_conservative")}</option>
                <option value="rule_based">{t("controller.rule_based")}</option>
              </select>
            </label>
          </div>
          <BaselineSystem baseline={lab.defaults.baseline} />
        </div>
      </section>

      <section className="story-section">
        <div className="section-heading">
          <p className="section-kicker">{t("inv.step2")}</p>
          <h2>{t("inv.step2Title")}</h2>
          <p>{t("inv.step2Desc")}</p>
        </div>
        <div className="proposal-grid">
          <NumberField label={t("inv.pvCapacity")} suffix="kW" value={lab.candidate.pv_capacity_kw} onChange={(value) => lab.updateCandidate({ pv_capacity_kw: value })} />
          <NumberField label={t("inv.bessEnergy")} suffix="kWh" value={lab.candidate.battery_energy_capacity_kwh} onChange={(value) => lab.updateCandidate({ battery_energy_capacity_kwh: value })} />
          <NumberField label={t("inv.bessPower")} suffix="kW" value={lab.candidate.battery_power_kw} onChange={(value) => lab.updateCandidate({ battery_power_kw: value })} />
          <NumberField label={t("inv.dppaVolume")} suffix="kW" value={lab.candidate.dppa_available_kw} onChange={(value) => lab.updateCandidate({ dppa_available_kw: value })} />
          <NumberField label={t("inv.dppaPrice")} suffix="VND/kWh" value={lab.candidate.dppa_price_vnd_per_kwh} onChange={(value) => lab.updateCandidate({ dppa_price_vnd_per_kwh: value })} />
          <NumberField label={t("inv.terminalValuation")} suffix="VND/kWh" value={lab.candidate.terminal_inventory_valuation_vnd_per_kwh} onChange={(value) => lab.updateCandidate({ terminal_inventory_valuation_vnd_per_kwh: value })} />
        </div>
        <details className="technical-details">
          <summary>{t("inv.advancedAssumptions")}</summary>
          <div className="proposal-grid">
            <NumberField label={t("inv.transformerCapacity")} suffix="kW" value={lab.candidate.transformer_capacity_kw} onChange={(value) => lab.updateCandidate({ transformer_capacity_kw: value })} />
            <NumberField label={t("inv.minSOC")} suffix="fraction" value={lab.candidate.minimum_soc_fraction} step={0.01} onChange={(value) => lab.updateCandidate({ minimum_soc_fraction: value })} />
            <NumberField label={t("inv.initialSOC")} suffix="fraction" value={lab.candidate.initial_soc_fraction} step={0.01} onChange={(value) => lab.updateCandidate({ initial_soc_fraction: value })} />
            <NumberField label={t("inv.annualOperatingDays")} suffix="days" value={lab.financial.annual_operating_days} onChange={(value) => lab.updateFinancial({ annual_operating_days: value })} />
            <NumberField label={t("inv.pvCapex")} suffix="VND/kW" value={lab.financial.pv_capex_vnd_per_kwp} onChange={(value) => lab.updateFinancial({ pv_capex_vnd_per_kwp: value })} />
            <NumberField label={t("inv.bessEnergyCapex")} suffix="VND/kWh" value={lab.financial.bess_energy_capex_vnd_per_kwh} onChange={(value) => lab.updateFinancial({ bess_energy_capex_vnd_per_kwh: value })} />
          </div>
          <p className="fine-print">{t("inv.finePrint")}</p>
        </details>
        {!result && (
          <div className="expected-direction">
            <strong>{t("inv.expectedDirection")}</strong>
            <p>{t("inv.expectedDirectionDesc")}</p>
          </div>
        )}
      </section>

      <section className="story-section">
        <div className="section-heading">
          <p className="section-kicker">{t("inv.step3")}</p>
          <h2>{t("inv.step3Title")}</h2>
        </div>
        <ProgressPanel job={lab.job} stale={lab.resultStale} />
      </section>

      {result && (
        <>
          <section className="story-section">
            <div className="section-heading">
              <p className="section-kicker">{t("inv.step4")}</p>
              <h2>{t("inv.step4Title")}</h2>
              <p>{summaryText}</p>
            </div>
            <ComparisonPanels result={result} financialAssumptions={lab.financial} valuationPrice={lab.candidate.terminal_inventory_valuation_vnd_per_kwh} />
          </section>

          <section className="story-section">
            <div className="section-heading">
              <p className="section-kicker">{t("inv.step5")}</p>
              <h2>{t("inv.step5Title")}</h2>
              <p>{t("inv.step5Desc")}</p>
            </div>
            <div className="evidence-toolbar">
              <label>{t("inv.tenant")}
                <select value={selectedTenant} onChange={(event) => setSelectedTenant(event.target.value)}>
                  <option value="all">{t("inv.allTenants")}</option>
                  {tenants.map((tenant) => <option key={tenant} value={tenant}>{readableTenant(tenant)}</option>)}
                </select>
              </label>
              <a className="primary-link" href={`/api/v1/investment/analyses/${result.analysis_id}/export`}>{t("inv.downloadZip")}</a>
            </div>
            <div className="tenant-evidence-list">
              {filteredTenantRows.map((row) => (
                <article key={`${row.case}-${row.tenant_id}`} className="tenant-evidence-row">
                  <strong>{readableTenant(String(row.tenant_id))} · {String(row.case)}</strong>
                  <span>{t("inv.evidenceLoad")} {num(row.load_served_kwh)} kWh</span>
                  <span>{t("inv.evidenceRenewableShare")} {pct(row.renewable_share)}</span>
                  <span>{t("inv.evidenceGrid")} {num(row.grid_energy_kwh)} kWh</span>
                  <span>{t("inv.evidenceShortfall")} {num(row.shortfall_kwh)} kWh</span>
                </article>
              ))}
            </div>
            <p className="fine-print">{t("inv.evidenceFinePrint")}</p>
          </section>
        </>
      )}
    </main>
  );
}

function BaselineSystem({ baseline }: { baseline: InvestmentCandidate }) {
  const { t } = useI18n();
  return (
    <aside className="baseline-panel">
      <p className="section-kicker">{t("inv.baselineSystem")}</p>
      <dl>
        <div><dt>{t("inv.baselineRooftopPV")}</dt><dd>{num(baseline.pv_capacity_kw)} kW</dd></div>
        <div><dt>{t("inv.baselineBessEnergy")}</dt><dd>{num(baseline.battery_energy_capacity_kwh)} kWh</dd></div>
        <div><dt>{t("inv.baselineBessPower")}</dt><dd>{num(baseline.battery_power_kw)} kW</dd></div>
        <div><dt>{t("inv.baselineTransformer")}</dt><dd>{num(baseline.transformer_capacity_kw)} kW</dd></div>
        <div><dt>{t("inv.dppaVolume")}</dt><dd>{num(baseline.dppa_available_kw)} kW</dd></div>
        <div><dt>{t("inv.dppaPrice")}</dt><dd>{num(baseline.dppa_price_vnd_per_kwh)} VND/kWh</dd></div>
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
  const { t } = useI18n();
  if (!job) return <p>{t("inv.progressIdle")}</p>;
  return (
    <div className="progress-panel">
      <div className="progress-head">
        <strong>{job.current_phase}</strong>
        <span>{job.status}{stale ? t("inv.progressStaleSuffix") : ""}</span>
      </div>
      <div className="progress-track"><div style={{ width: `${Math.max(0, Math.min(100, job.progress_percentage ?? 0))}%` }} /></div>
      <p>{t("inv.progressHours", { done: job.completed_hours ?? 0, total: job.requested_hours ?? 0, sec: Number(job.elapsed_seconds ?? 0).toFixed(1) })}</p>
    </div>
  );
}

function ComparisonPanels({ result, financialAssumptions, valuationPrice }: { result: any; financialAssumptions: any; valuationPrice: number }) {
  const { t } = useI18n();
  const baseline = withAdjustedInventoryCost(result.technical_metrics.baseline, valuationPrice);
  const proposal = withAdjustedInventoryCost(result.technical_metrics.proposal, valuationPrice);
  const financial = recalculateFinancial(result, financialAssumptions, valuationPrice);
  return (
    <div className="comparison-grid">
      <div>
        <h3>{t("inv.operatingOutcome")}</h3>
        <ComparisonRow label={t("inv.inventoryAdjustedCost")} baseline={baseline.inventory_adjusted_operating_cost_vnd} proposal={proposal.inventory_adjusted_operating_cost_vnd} format={money} />
        <ComparisonRow label={t("inv.evidenceRenewableShare")} baseline={baseline.park_renewable_share} proposal={proposal.park_renewable_share} format={pct} />
        <ComparisonRow label={t("inv.peakGridImport")} baseline={baseline.peak_grid_import_kw} proposal={proposal.peak_grid_import_kw} format={(v) => `${num(v)} kW`} />
        <ComparisonRow label={t("inv.renewableShortfall")} baseline={baseline.renewable_shortfall_total_kwh} proposal={proposal.renewable_shortfall_total_kwh} format={(v) => `${num(v)} kWh`} />
      </div>
      <div>
        <h3>{t("inv.energySourceMix")}</h3>
        <SourceMix label={t("inv.baseline")} metrics={baseline} />
        <SourceMix label={t("inv.proposal")} metrics={proposal} />
      </div>
      <div>
        <h3>{t("inv.financialSummary")}</h3>
        <dl className="financial-list">
          <div><dt>{t("inv.incrementalCapex")}</dt><dd>{money(financial.incremental_capex_vnd)}</dd></div>
          <div><dt>{t("inv.annualizedSavings")}</dt><dd>{money(financial.annualized_operating_savings_vnd)}</dd></div>
          <div><dt>{t("inv.annualOmChange")}</dt><dd>{money(financial.incremental_annual_om_vnd)}</dd></div>
          <div><dt>{t("inv.netAnnualSavings")}</dt><dd>{money(financial.net_annual_savings_vnd)}</dd></div>
          <div><dt>{t("inv.simplePayback")}</dt><dd>{financial.simple_payback_years ? t("inv.paybackYears", { years: Number(financial.simple_payback_years).toFixed(1) }) : t("inv.paybackNone")}</dd></div>
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
  const { t } = useI18n();
  const total = Math.max(1, Number(metrics.total_load_served_kwh ?? 0));
  const parts = [
    [t("source.solar"), metrics.direct_pv_delivery_kwh ?? 0, "#0f766e"],
    [t("source.dppa"), metrics.realized_dppa_energy_kwh ?? 0, "#d97706"],
    [t("source.battery"), metrics.battery_delivery_kwh ?? 0, "#4f46e5"],
    [t("source.grid"), metrics.realized_grid_energy_kwh ?? 0, "#2563eb"]
  ];
  return (
    <div className="source-mix">
      <span>{label}</span>
      <div>{parts.map(([name, value, color]) => <i key={String(name)} title={`${name}: ${num(value)} kWh`} style={{ width: `${100 * Number(value) / total}%`, background: String(color) }} />)}</div>
    </div>
  );
}

function executiveSummary(result: any, t: I18n["t"]) {
  const b = result.technical_metrics.baseline;
  const p = result.technical_metrics.proposal;
  const renewableDelta = 100 * (Number(p.park_renewable_share) - Number(b.park_renewable_share));
  const peakDelta = Number(p.peak_grid_import_kw) - Number(b.peak_grid_import_kw);
  const savings = Number(result.financial_metrics.annualized_operating_savings_vnd);
  return t("inv.summary", { renew: renewableDelta.toFixed(1), peak: peakDelta.toFixed(0), cost: money(savings) });
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
