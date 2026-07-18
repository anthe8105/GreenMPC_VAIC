import { ActionPanel } from "../components/ActionPanel";
import { ForecastPanel, HistoryPanel } from "../components/Charts";
import { KpiCards } from "../components/KpiCards";
import { PlaybackControls } from "../components/PlaybackControls";
import { Topology } from "../components/Topology";
import type { CommandState, ControlPhase, ControllerId, ForecastPayload, OperationMode, PlanPayload, ScenarioId } from "../types/api";
import type { ReactNode } from "react";
import { useI18n } from "../i18n/LanguageContext";
import type { Narrative } from "../i18n/translations";

interface ControlsProps {
  mode: OperationMode;
  setMode: (value: OperationMode) => void;
  controller: ControllerId;
  setController: (value: ControllerId) => void;
  scenario: ScenarioId;
  setScenario: (value: ScenarioId) => void;
  playbackSeconds: number;
  setPlaybackSeconds: (value: number) => void;
  maxHours: number;
  setMaxHours: (value: number) => void;
  running: boolean;
  startLiveSimulation: () => void;
  startSelectedMode: () => void;
  pause: () => void;
  runGuidedDemo: () => void;
  activateStressScenario: (scenario: ScenarioId) => void;
  onReset: () => void;
  onStep: () => void;
}

export function LiveTwinPage(props: {
  state: CommandState;
  forecast: ForecastPayload | null;
  plan: PlanPayload | null;
  controls: ControlsProps;
  running: boolean;
  phase: ControlPhase;
  nextTickAt: number | null;
  nowMs: number;
  completedHours: number;
  maxHours: number;
  fallbackCount: number;
  invalidActionCount: number;
  eventBanner: Narrative | null;
  decisionReason: Narrative;
  onForecastPlan: () => void;
  onExecute: () => void;
  loading: boolean;
  error: string;
}) {
  const { t } = useI18n();
  const countdown = props.running && props.nextTickAt ? `${Math.max(0, Math.ceil((props.nextTickAt - props.nowMs) / 1000))}s` : t("countdown.paused");
  return (
    <main className="story-page">
      <section className="intro-strip">
        <div>
          <h1>{t("live.h1")}</h1>
          <p>{t("live.intro")}</p>
        </div>
        <div className="intro-actions">
          <button className="start-button" onClick={props.controls.startLiveSimulation} disabled={props.loading || props.running}>{t("action.startLiveDemo")}</button>
          <button onClick={props.controls.runGuidedDemo} disabled={props.loading}>{t("live.guidedDemo")}</button>
        </div>
      </section>

      <KpiCards state={props.state} />
      <Pipeline phase={props.phase} />

      <StorySection
        id="now"
        number="1"
        title={t("story.now.title")}
        subtitle={t("story.now.subtitle")}
        active={["READY", "UPDATED", "WAITING", "PAUSED", "EXECUTING"].includes(props.phase)}
      >
        <div className="now-layout">
          <Topology state={props.state} plan={props.plan} viewModeLabel={props.plan ? t("topology.planAvailable") : t("topology.liveExecutedFlow")} />
          <CurrentNarrative
            state={props.state}
            controls={props.controls}
            running={props.running}
            countdown={countdown}
            completedHours={props.completedHours}
            maxHours={props.maxHours}
            phase={props.phase}
            decisionReason={props.decisionReason}
            eventBanner={props.eventBanner}
            error={props.error}
            loading={props.loading}
          />
        </div>
      </StorySection>

      <StorySection
        id="forecast"
        number="2"
        title={t("story.forecast.title")}
        subtitle={t("story.forecast.subtitle")}
        active={props.phase === "FORECASTING"}
      >
        <ForecastPanel forecast={props.forecast} state={props.state} />
      </StorySection>

      <StorySection
        id="decision"
        number="3"
        title={t("story.decision.title")}
        subtitle={t("story.decision.subtitle")}
        active={["OPTIMIZING", "REVIEWING_DECISION", "EXECUTING"].includes(props.phase)}
      >
        <ActionPanel plan={props.plan} state={props.state} mode={props.controls.mode} running={props.running} countdown={countdown} onExecute={props.onExecute} />
      </StorySection>

      <StorySection
        id="value"
        number="4"
        title={t("story.value.title")}
        subtitle={t("story.value.subtitle")}
        active={props.phase === "UPDATED"}
      >
        <HistoryPanel state={props.state} completedHours={props.completedHours} fallbackCount={props.fallbackCount} invalidActionCount={props.invalidActionCount} />
      </StorySection>

      <section className="story-section stress-story">
        <div className="section-heading">
          <p className="section-kicker">{t("stress.kicker")}</p>
          <h2>{t("stress.title")}</h2>
          <p>{t("stress.desc")}</p>
        </div>
        <div className="stress-buttons">
          <button disabled={props.loading || props.running} onClick={() => props.controls.activateStressScenario("cloudy")}>{t("stress.solarDrop")}</button>
          <button disabled={props.loading || props.running} onClick={() => props.controls.activateStressScenario("production_shift")}>{t("stress.productionSurge")}</button>
          <button disabled={props.loading || props.running} onClick={() => props.controls.activateStressScenario("combined_stress")}>{t("stress.dppaReduction")}</button>
          <button disabled={props.loading || props.running} onClick={() => props.controls.activateStressScenario("combined_stress")}>{t("stress.combined")}</button>
          <button disabled={props.loading || props.running} onClick={() => props.controls.activateStressScenario("normal")}>{t("stress.restoreNormal")}</button>
        </div>
      </section>

      <details className="story-section advanced-controls">
        <summary>{t("advanced.summary")}</summary>
        <PlaybackControls {...props.controls} loading={props.loading} onForecastPlan={props.onForecastPlan} />
      </details>
    </main>
  );
}

function StorySection({
  number,
  title,
  subtitle,
  active,
  children
}: {
  id: string;
  number: string;
  title: string;
  subtitle: string;
  active: boolean;
  children: ReactNode;
}) {
  const { t } = useI18n();
  return (
    <section className={`story-section ${active ? "section-active" : ""}`}>
      <div className="section-heading">
        <p className="section-kicker">{t("section.stage", { number })}</p>
        <h2>{title}</h2>
        <p>{subtitle}</p>
      </div>
      {children}
    </section>
  );
}

function CurrentNarrative({
  state,
  controls,
  running,
  countdown,
  completedHours,
  maxHours,
  phase,
  decisionReason,
  eventBanner,
  error,
  loading
}: {
  state: CommandState;
  controls: ControlsProps;
  running: boolean;
  countdown: string;
  completedHours: number;
  maxHours: number;
  phase: ControlPhase;
  decisionReason: Narrative;
  eventBanner: Narrative | null;
  error: string;
  loading: boolean;
}) {
  const { t, tn } = useI18n();
  const kpis = state.kpis;
  return (
    <aside className="current-summary">
      <h3>{t("situation.title")}</h3>
      <dl>
        <div><dt>{t("situation.demand")}</dt><dd>{kw(kpis.park_load_kw)}</dd></div>
        <div><dt>{t("situation.solar")}</dt><dd>{Number(kpis.pv_available_kw ?? 0) <= 1 ? t("situation.solarUnavailable") : t("situation.solarAvailable", { value: kw(kpis.pv_available_kw) })}</dd></div>
        <div><dt>{t("situation.renewable")}</dt><dd>{t("situation.dppaAvailable", { value: kw(kpis.dppa_available_kw) })}</dd></div>
        <div><dt>{t("situation.battery")}</dt><dd>{t("situation.soc", { value: percent(kpis.battery_soc_fraction) })}</dd></div>
        <div><dt>{t("situation.transformer")}</dt><dd>{t("situation.utilized", { value: percent(kpis.transformer_utilization_fraction) })}</dd></div>
      </dl>
      <div className="ai-interpretation">{tn(decisionReason)}</div>
      {eventBanner && <div className="event-banner compact"><strong>{t("situation.stressActive")}</strong> {tn(eventBanner)}</div>}
      {error && <div className="alert error"><strong>{t("situation.paused")}</strong> {error}</div>}
      {!error && <div className="alert ok">{t("situation.ok")}</div>}
      <div className="live-controls">
        <div><span>{t("situation.phase")}</span><strong>{t(`phase.${phase}`)}</strong></div>
        <div><span>{t("situation.nextCycle")}</span><strong>{countdown}</strong></div>
        <div><span>{t("situation.progress")}</span><strong>{t("situation.progressValue", { done: completedHours, total: maxHours })}</strong></div>
      </div>
      <div className="control-buttons">
        <button onClick={controls.pause} disabled={!running}>{t("action.pause")}</button>
        <button onClick={controls.onStep} disabled={loading || running}>{t("action.stepOneHour")}</button>
        <button onClick={controls.onReset} disabled={loading}>{t("action.reset")}</button>
      </div>
    </aside>
  );
}

function Pipeline({ phase }: { phase: ControlPhase }) {
  const { t } = useI18n();
  const steps: Array<[string, ControlPhase[]]> = [
    [t("pipeline.observe"), ["READY", "WAITING", "PAUSED"]],
    [t("pipeline.forecast"), ["FORECASTING"]],
    [t("pipeline.optimize"), ["OPTIMIZING"]],
    [t("pipeline.validate"), ["REVIEWING_DECISION"]],
    [t("pipeline.execute"), ["EXECUTING", "UPDATED"]]
  ];
  return (
    <section className="pipeline compact-pipeline" aria-label="AI control pipeline">
      {steps.map(([label, phases]) => <div key={label} className={phases.includes(phase) ? "active" : ""}>{label}</div>)}
    </section>
  );
}

function kw(value: unknown) {
  return `${Number(value ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })} kW`;
}

function percent(value: unknown) {
  return `${(Number(value ?? 0) * 100).toFixed(1)}%`;
}
