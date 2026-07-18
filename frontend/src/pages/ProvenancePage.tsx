import { useI18n } from "../i18n/LanguageContext";

export function ProvenancePage({ provenance }: { provenance: Record<string, unknown> | null }) {
  const { t } = useI18n();
  const data = (provenance?.data ?? {}) as Record<string, unknown>;
  const disclosures = Array.isArray(data.disclosures) ? data.disclosures as string[] : [];
  return (
    <main className="page-grid">
      <section className="hero compact">
        <div>
          <h1>{t("prov.h1")}</h1>
          <p>{t("prov.desc")}</p>
        </div>
        <span className="healthy">{t("prov.offlineRuntime")}</span>
      </section>

      <section className="provenance-grid">
        <InfoCard label={t("prov.datasetVersion")} value={String(data.dataset_version ?? t("common.unknown"))} />
        <InfoCard label={t("prov.modelRegistry")} value={String(data.model_version ?? t("common.unknown"))} />
        <InfoCard label={t("prov.controllerVersion")} value={String(data.controller_version ?? "GreenMPC")} />
        <InfoCard label={t("prov.pvFormula")} value={String(data.pv_formula_version ?? "simple_capacity_factor_v2")} />
        <InfoCard label={t("prov.tenantFingerprint")} value={short(String(data.tenant_dataset_fingerprint ?? t("common.unknown")))} />
        <InfoCard label={t("prov.parkFingerprint")} value={short(String(data.park_dataset_fingerprint ?? t("common.unknown")))} />
      </section>

      <section className="panel note-panel">
        <div className="panel-title">{t("prov.requiredDisclosures")}</div>
        <ul className="disclosure-list">
          {disclosures.map((item) => <li key={item}>{item}</li>)}
          <li>{t("disclosure.nasa")}</li>
          <li>{t("disclosure.tariff")}</li>
        </ul>
      </section>
    </main>
  );
}

function InfoCard({ label, value }: { label: string; value: string }) {
  return <section className="panel info-card"><span>{label}</span><strong>{value}</strong></section>;
}

function short(value: string) {
  return value.length > 20 ? `${value.slice(0, 12)}...${value.slice(-6)}` : value;
}
