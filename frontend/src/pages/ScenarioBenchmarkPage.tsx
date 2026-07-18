import { Fragment, useEffect, useState } from "react";
import { listInvestmentAnalyses } from "../api/client";
import type { InvestmentJobStatus } from "../types/api";
import { useI18n } from "../i18n/LanguageContext";
import type { I18n } from "../i18n/LanguageContext";

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
  const { t } = useI18n();
  const rows = Array.isArray(benchmark?.rows) ? benchmark.rows as Array<Record<string, unknown>> : [];
  const data = (provenance?.data ?? {}) as Record<string, unknown>;
  const disclosures = Array.isArray(data.disclosures) ? data.disclosures as string[] : [];
  const [analyses, setAnalyses] = useState<InvestmentJobStatus[]>([]);
  useEffect(() => {
    void listInvestmentAnalyses().then((payload) => setAnalyses(payload.analyses ?? [])).catch(() => setAnalyses([]));
  }, []);
  return (
    <main className="story-page">
      <section className="story-section">
        <div>
          <p className="section-kicker">{t("bench.kicker")}</p>
          <h1>{t("bench.h1")}</h1>
          <p>{t("bench.desc")}</p>
        </div>
        <label className="valuation-select">{t("bench.terminalValuation")}
          <select value={valuationPrice} onChange={(event) => setValuationPrice(Number(event.target.value))}>
            <option value={1100}>1,100 VND/kWh</option>
            <option value={1500}>1,500 VND/kWh</option>
            <option value={2000}>2,000 VND/kWh</option>
            <option value={2500}>2,500 VND/kWh</option>
          </select>
        </label>
      </section>

      <section className="story-section">
        <h2>{t("bench.savedTitle")}</h2>
        <p>{t("bench.savedDesc")}</p>
        <div className="benchmark-grid investment-saved-grid" role="table" aria-label="saved investment analyses">
          <div className="table-head">{t("bench.colAnalysis")}</div>
          <div className="table-head">{t("bench.colStatus")}</div>
          <div className="table-head">{t("bench.colCompletedHours")}</div>
          <div className="table-head">{t("bench.colElapsed")}</div>
          <div className="table-head">{t("bench.colCache")}</div>
          {analyses.length === 0 && <div className="empty-row">{t("bench.noAnalyses")}</div>}
          {analyses.map((row) => (
            <Fragment key={row.analysis_id}>
              <div>{row.analysis_id}</div>
              <div>{row.status}</div>
              <div>{row.completed_hours} / {row.requested_hours}</div>
              <div>{Number(row.elapsed_seconds ?? 0).toFixed(1)}s</div>
              <div>{row.loaded_from_cache ? t("bench.cached") : t("bench.runtime")}</div>
            </Fragment>
          ))}
        </div>
      </section>

      <section className="story-section">
        <h2>{t("bench.comparisonTitle")}</h2>
        <div className="benchmark-grid" role="table" aria-label="controller benchmark comparison">
          <div className="table-head">{t("bench.colScenario")}</div>
          <div className="table-head">{t("bench.colController")}</div>
          <div className="table-head">{t("bench.colRawCost")}</div>
          <div className="table-head">{t("bench.colInvAdjCost")}</div>
          <div className="table-head">{t("bench.colRenewableShare")}</div>
          <div className="table-head">{t("bench.colPeakGrid")}</div>
          <div className="table-head">{t("bench.colFallbacks")}</div>
          {rows.map((row, index) => (
            <BenchmarkRow key={index} row={row} t={t} />
          ))}
        </div>
      </section>

      <section className="story-section subtle-section">
        <h2>{t("bench.interpretTitle")}</h2>
        <p>{t("bench.interpret1")}</p>
        <p>{t("bench.interpret2")}</p>
      </section>

      <section className="story-section subtle-section">
        <h2>{t("bench.provenanceTitle")}</h2>
        <div className="provenance-line">
          <span>{t("bench.datasetVersion")} <strong>{String(data.dataset_version ?? t("common.unknown"))}</strong></span>
          <span>{t("bench.modelRegistry")} <strong>{String(data.model_version ?? t("common.unknown"))}</strong></span>
          <span>{t("bench.pvFormula")} <strong>{String(data.pv_formula_version ?? "simple_capacity_factor_v2")}</strong></span>
        </div>
        <ul className="disclosure-list">
          {disclosures.map((item) => <li key={item}>{item}</li>)}
          <li>{t("disclosure.nasa")}</li>
          <li>{t("disclosure.tariff")}</li>
        </ul>
      </section>
    </main>
  );
}

function benchLabel(prefix: "scenario" | "controller", id: string, t: I18n["t"]) {
  if (!id) return "";
  const key = `${prefix}.${id}`;
  const label = t(key);
  return label === key ? id : label;
}

function BenchmarkRow({ row, t }: { row: Record<string, unknown>; t: I18n["t"] }) {
  return (
    <>
      <div>{benchLabel("scenario", String(row.scenario_id ?? ""), t)}</div>
      <div>{benchLabel("controller", String(row.controller_id ?? ""), t)}</div>
      <div>{money(row.total_realized_operating_cost_proxy_vnd)}</div>
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
