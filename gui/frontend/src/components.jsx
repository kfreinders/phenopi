import { NavLink } from "react-router-dom";

export function WorkflowSteps({ current }) {
  const steps = ["Configure", "Review", "Activate", "Confirmed"];
  return <ol className="workflow-steps" aria-label="Schedule activation progress">
    {steps.map((label, index) => {
      const number = index + 1;
      const complete = number < current;
      const currentStep = number === current;
      return <li key={label} className={`workflow-step${complete ? " workflow-step--complete" : ""}${currentStep ? " workflow-step--current" : ""}`} aria-current={currentStep ? "step" : undefined}>
        <span>{complete ? "✓" : number}</span><strong>{label}</strong>
      </li>;
    })}
  </ol>;
}

export function Loading({ label = "Loading" }) {
  return <section className="card react-loading" role="status"><span className="react-spinner" />{label}</section>;
}

export function ErrorNotice({ error }) {
  return error ? <section className="alert error" role="alert">{error.message ?? error}</section> : null;
}

export function SchedulePreview({ preview }) {
  return <section className="preview-panel">
    <div className="summary-grid">
      {[
        [preview.daily_time_points, "Daily time points"],
        [preview.replicates, "Replicates per time point"],
        [preview.daily_captures, "Daily captures"],
        [preview.total_captures, "Total captures"],
        [preview.first_time, "First time"],
        [preview.last_time, "Last time"],
      ].map(([value, label]) => <div className="summary-card" key={label}><strong>{value}</strong><span>{label}</span></div>)}
    </div>
    <div className="visual-preview-grid">
      <section className="schedule-graphic-card">
        <div className="graphic-card-header"><h3>Daily imaging window</h3><p>{preview.summary_sentence}</p></div>
        <div className="timeline-shell" aria-label="Daily capture timeline">
          <div className="timeline-axis">{preview.timeline_points.map(point => <span className="timeline-point" style={{ left: `${point.percent}%` }} title={point.time} key={point.time} />)}</div>
          <div className="timeline-labels"><span>{preview.first_time}</span><span>{preview.last_time}</span></div>
        </div>
        <div className="day-strip" aria-label="Scheduled experiment days">{Array.from({ length: preview.num_days }, (_, index) => <span className="day-pill" key={index}>Day {index + 1}</span>)}</div>
      </section>
      <section className="schedule-graphic-card">
        <div className="graphic-card-header"><h3>Technical replicates</h3><p>Each time point triggers {preview.replicates} capture{preview.replicates === 1 ? "" : "s"}, spaced {preview.replicate_interval_seconds} seconds apart.</p></div>
        <div className="replicate-burst"><div className="replicate-time">{preview.first_time}</div><div className="replicate-dots">
          {preview.replicate_offsets.map(item => <div className="replicate-dot-block" key={item.number}><span className="replicate-dot">{item.number}</span><small>+{item.offset_seconds} s</small></div>)}
        </div></div>
      </section>
    </div>
  </section>;
}

export function Navigation() {
  return <nav className="tabs" aria-label="Phenopi sections">
    <NavLink className={({ isActive }) => `tab${isActive ? " active" : ""}`} to="/scheduler">Scheduler status</NavLink>
    <NavLink className={({ isActive }) => `tab${isActive ? " active" : ""}`} to="/schedule">Schedule builder</NavLink>
    <NavLink className={({ isActive }) => `tab${isActive ? " active" : ""}`} to="/camera">Camera preview</NavLink>
  </nav>;
}

