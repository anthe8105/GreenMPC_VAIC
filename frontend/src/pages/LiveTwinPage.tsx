import { ActionPanel } from "../components/ActionPanel";
import { ForecastPanel, HistoryPanel } from "../components/Charts";
import { KpiCards } from "../components/KpiCards";
import { PlaybackControls } from "../components/PlaybackControls";
import { Topology } from "../components/Topology";
import type { CommandState, ControlPhase, ControllerId, ForecastPayload, OperationMode, PlanPayload, ScenarioId } from "../types/api";
import type { ReactNode } from "react";
import { controllerLabel, phaseLabel, scenarioLabel } from "../types/labels";

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
  eventBanner: string | null;
  decisionReason: string;
  onForecastPlan: () => void;
  onExecute: () => void;
  loading: boolean;
  error: string;
}) {
  const countdown = props.running && props.nextTickAt ? `${Math.max(0, Math.ceil((props.nextTickAt - props.nowMs) / 1000))}s` : "paused";
  return (
    <main className="story-page">
      <section className="intro-strip">
        <div>
          <h1>See GreenMPC forecast, optimize, and control the park in real time.</h1>
          <p>Follow one industrial park as GreenMPC observes current conditions, predicts the next six hours, chooses an energy mix, and executes one validated simulated hour.</p>
        </div>
        <div className="intro-actions">
          <button className="start-button" onClick={props.controls.startLiveSimulation} disabled={props.loading || props.running}>Start Live Demo</button>
          <button onClick={props.controls.runGuidedDemo} disabled={props.loading}>Run 3-Hour Guided Demo</button>
        </div>
      </section>

      <KpiCards state={props.state} />
      <Pipeline phase={props.phase} />

      <StorySection
        id="now"
        number="1"
        title="WHAT IS HAPPENING NOW?"
        subtitle="Live energy flow across the industrial park"
        active={["READY", "UPDATED", "WAITING", "PAUSED", "EXECUTING"].includes(props.phase)}
      >
        <div className="now-layout">
          <Topology state={props.state} plan={props.plan} viewModeLabel={props.plan ? "Next-hour AI plan available" : "Live executed flow"} />
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
        title="WHAT WILL HAPPEN NEXT?"
        subtitle="AI forecast for the next six hours"
        active={props.phase === "FORECASTING"}
      >
        <ForecastPanel forecast={props.forecast} state={props.state} />
      </StorySection>

      <StorySection
        id="decision"
        number="3"
        title="WHAT DOES GREENMPC DECIDE?"
        subtitle="Recommended dispatch for the next operating hour"
        active={["OPTIMIZING", "REVIEWING_DECISION", "EXECUTING"].includes(props.phase)}
      >
        <ActionPanel plan={props.plan} state={props.state} mode={props.controls.mode} running={props.running} countdown={countdown} onExecute={props.onExecute} />
      </StorySection>

      <StorySection
        id="value"
        number="4"
        title="WHAT VALUE IS GREENMPC CREATING?"
        subtitle="Executed operating outcomes from the simulated period"
        active={props.phase === "UPDATED"}
      >
        <HistoryPanel state={props.state} completedHours={props.completedHours} fallbackCount={props.fallbackCount} invalidActionCount={props.invalidActionCount} />
      </StorySection>

      <section className="story-section stress-story">
        <div className="section-heading">
          <p className="section-kicker">Test a stress event</p>
          <h2>See how the controller responds to disruption</h2>
          <p>Stress events are synthetic and unannounced. If selected, the demo restarts clearly so the approved event model can apply safely.</p>
        </div>
        <div className="stress-buttons">
          <button disabled={props.loading || props.running} onClick={() => props.controls.activateStressScenario("cloudy")}>Solar Drop</button>
          <button disabled={props.loading || props.running} onClick={() => props.controls.activateStressScenario("production_shift")}>Production Surge</button>
          <button disabled={props.loading || props.running} onClick={() => props.controls.activateStressScenario("combined_stress")}>DPPA Reduction</button>
          <button disabled={props.loading || props.running} onClick={() => props.controls.activateStressScenario("combined_stress")}>Combined Stress</button>
          <button disabled={props.loading || props.running} onClick={() => props.controls.activateStressScenario("normal")}>Restore Normal</button>
        </div>
      </section>

      <details className="story-section advanced-controls">
        <summary>Advanced Settings</summary>
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
  return (
    <section className={`story-section ${active ? "section-active" : ""}`}>
      <div className="section-heading">
        <p className="section-kicker">Stage {number}</p>
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
  decisionReason: string;
  eventBanner: string | null;
  error: string;
  loading: boolean;
}) {
  const kpis = state.kpis;
  return (
    <aside className="current-summary">
      <h3>Current situation</h3>
      <dl>
        <div><dt>Demand</dt><dd>{kw(kpis.park_load_kw)}</dd></div>
        <div><dt>Solar</dt><dd>{Number(kpis.pv_available_kw ?? 0) <= 1 ? "unavailable" : `${kw(kpis.pv_available_kw)} available`}</dd></div>
        <div><dt>Renewable supply</dt><dd>{kw(kpis.dppa_available_kw)} DPPA available</dd></div>
        <div><dt>Battery</dt><dd>{percent(kpis.battery_soc_fraction)} SOC</dd></div>
        <div><dt>Transformer</dt><dd>{percent(kpis.transformer_utilization_fraction)} utilized</dd></div>
      </dl>
      <div className="ai-interpretation">{decisionReason}</div>
      {eventBanner && <div className="event-banner compact"><strong>Stress active:</strong> {eventBanner}</div>}
      {error && <div className="alert error"><strong>Paused:</strong> {error}</div>}
      {!error && <div className="alert ok">System operating within configured limits.</div>}
      <div className="live-controls">
        <div><span>Phase</span><strong>{phaseLabel(phase)}</strong></div>
        <div><span>Next cycle</span><strong>{countdown}</strong></div>
        <div><span>Progress</span><strong>{completedHours} / {maxHours} hours</strong></div>
      </div>
      <div className="control-buttons">
        <button onClick={controls.pause} disabled={!running}>Pause</button>
        <button onClick={controls.onStep} disabled={loading || running}>Step One Hour</button>
        <button onClick={controls.onReset} disabled={loading}>Reset</button>
      </div>
    </aside>
  );
}

function Pipeline({ phase }: { phase: ControlPhase }) {
  const steps: Array<[string, ControlPhase[]]> = [
    ["Observe", ["READY", "WAITING", "PAUSED"]],
    ["Forecast", ["FORECASTING"]],
    ["Optimize", ["OPTIMIZING"]],
    ["Validate", ["REVIEWING_DECISION"]],
    ["Execute", ["EXECUTING", "UPDATED"]]
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
