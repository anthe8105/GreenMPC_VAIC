export function ProvenancePage({ provenance }: { provenance: Record<string, unknown> | null }) {
  const data = (provenance?.data ?? {}) as Record<string, unknown>;
  const disclosures = Array.isArray(data.disclosures) ? data.disclosures as string[] : [];
  return (
    <main className="page-grid">
      <section className="hero compact">
        <div>
          <h1>Data Trust and Provenance</h1>
          <p>Offline traceability for dataset, model, controller, assumptions, and benchmark evidence.</p>
        </div>
        <span className="healthy">offline runtime</span>
      </section>

      <section className="provenance-grid">
        <InfoCard label="Dataset version" value={String(data.dataset_version ?? "unknown")} />
        <InfoCard label="Model registry" value={String(data.model_version ?? "unknown")} />
        <InfoCard label="Controller version" value={String(data.controller_version ?? "GreenMPC")} />
        <InfoCard label="PV formula" value={String(data.pv_formula_version ?? "simple_capacity_factor_v2")} />
        <InfoCard label="Tenant fingerprint" value={short(String(data.tenant_dataset_fingerprint ?? "unknown"))} />
        <InfoCard label="Park fingerprint" value={short(String(data.park_dataset_fingerprint ?? "unknown"))} />
      </section>

      <section className="panel note-panel">
        <div className="panel-title">Required Disclosures</div>
        <ul className="disclosure-list">
          {disclosures.map((item) => <li key={item}>{item}</li>)}
          <li>NASA POWER weather and irradiance are public source inputs; PV is derived rather than measured inverter output.</li>
          <li>Tariff, DPPA volume, DPPA price, tenant labels, tenant scaling, and stress events are transparent scenario assumptions.</li>
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
