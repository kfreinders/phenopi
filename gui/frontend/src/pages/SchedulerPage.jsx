import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { ErrorNotice, Loading } from "../components";
import { useSchedulerStatus } from "../hooks";
import { formatBytes, formatDateTime, relativeFutureTime } from "../format";

const lifecycleLabels = { upcoming: "Upcoming", active: "Active", finished: "Finished", empty: "Empty schedule" };

function NextAction({ schedule, draftState, summary }) {
  if (draftState === "ready") return <section className="card schedule-action"><div><span className="eyebrow">Schedule draft</span><h3>Draft ready for review</h3><p>Continue reviewing the saved draft before activating it.</p></div><Link className="primary-link" to="/schedule/review">Review draft</Link></section>;
  if (draftState === "invalid") return <section className="card schedule-action"><div><span className="eyebrow">Schedule draft</span><h3>Draft needs attention</h3><p>Open the schedule builder to correct the saved draft.</p></div><Link className="primary-link" to="/schedule">Open schedule builder</Link></section>;
  if (schedule?.lifecycle !== "finished") return null;
  const issues = summary && summary.failed + summary.missed + summary.elapsed_unreported > 0;
  return <section className="card schedule-action"><div><span className="eyebrow">Experiment complete</span><h3>{issues ? "Experiment finished with capture issues" : "Experiment finished"}</h3><p>{issues ? "Review the capture outcomes below before closing this dataset." : "This completed schedule remains available below for reference."}</p></div><Link className="primary-link" to="/schedule">Create next schedule</Link></section>;
}

export function SchedulerPage() {
  const { data, error } = useSchedulerStatus();
  if (!data && !error) return <Loading label="Loading scheduler overview" />;
  if (!data) return <ErrorNotice error={error} />;
  const schedule = data.schedule;
  const storageRisk = schedule && data.storage && schedule.estimated_remaining_storage_bytes > data.storage.free_bytes;
  return <section className="scheduler-page" aria-live="polite">
    <div className="scheduler-heading"><div><h2>Scheduler overview</h2><p>Live service health and planned experiment progress.</p></div></div>
    {data.status === "unavailable" && <div className="health-alert" role="alert">{data.message}</div>}
    {(data.schedule_error || data.schedule_is_last_reported || data.status === "invalid_schedule") && <div className="schedule-warning">{data.schedule_error ?? (data.schedule_is_last_reported ? "Showing the last reported schedule; live state cannot currently be confirmed." : "The edited schedule was rejected. The valid schedule remains active.")}</div>}
    {storageRisk && <div className="storage-risk" role="alert">Storage risk: remaining captures need approximately {formatBytes(schedule.estimated_remaining_storage_bytes)}, but only {formatBytes(data.storage.free_bytes)} is free.</div>}
    <NextAction schedule={schedule} draftState={data.draft_state} summary={data.capture_summary} />
    {!schedule ? <section className="card schedule-empty"><h3>No schedule loaded</h3><Link className="primary-link" to={data.draft_state === "ready" ? "/schedule/review" : "/schedule"}>{data.draft_state === "ready" ? "Review draft" : "Create a schedule"}</Link></section> : <Dashboard data={data} />}
  </section>;
}

function Dashboard({ data }) {
  const s = data.schedule; const storage = data.storage; const capture = data.last_capture;
  const details = [s.run?.researcher, s.run?.notes].filter(Boolean).join(" · ");
  return <div id="schedule-dashboard">
    <section className="schedule-hero card"><div className="schedule-identity"><span className={`lifecycle-badge lifecycle-badge--${s.lifecycle}`}>{lifecycleLabels[s.lifecycle] ?? s.lifecycle}</span><h3>{s.run?.name ?? (s.lifecycle === "finished" ? "Completed experiment schedule" : "Current experiment schedule")}</h3><p>{s.start_date} → {s.end_date} · {s.num_days} day{s.num_days === 1 ? "" : "s"}</p>{details && <p className="schedule-run-details">{details}</p>}</div>
      <div className="progress-ring" style={{ "--progress": `${s.progress_percent * 3.6}deg` }} role="img" aria-label={`${s.progress_percent}% planned schedule progress`}><div><strong>{s.progress_percent.toFixed(1)}%</strong><span>{s.elapsed_captures} / {s.total_captures} planned elapsed</span><small>{s.current_day ? `Day ${s.current_day} of ${s.num_days}` : s.lifecycle === "finished" ? "Schedule complete" : `${s.num_days} scheduled days`}</small></div></div></section>
    <section className="metric-grid" aria-label="Schedule statistics">
      <article><span>Next capture</span><strong>{formatDateTime(s.next_capture_at)}</strong><small>{relativeFutureTime(s.next_capture_at)}</small></article>
      <article><span>Final capture</span><strong>{formatDateTime(s.last_capture_at)}</strong></article>
      <article className={capture ? `metric-state metric-state--${capture.status}` : ""}><span>Latest actual capture</span><strong>{capture ? capture.status[0].toUpperCase() + capture.status.slice(1) : "No result yet"}</strong><small>{capture ? formatDateTime(capture.scheduled_at) : "Waiting for the first capture"}</small></article>
      <article className={storage?.used_percent >= 95 ? "metric-state metric-state--critical" : storage?.used_percent >= 90 ? "metric-state metric-state--warning" : ""}><span>Capture storage</span><strong>{storage ? `${formatBytes(storage.free_bytes)} free` : "Unavailable"}</strong><small>{storage ? `${storage.used_percent.toFixed(1)}% used` : "Storage telemetry unavailable"}</small>{storage && <div className={`storage-meter${storage.used_percent >= 95 ? " storage-meter--critical" : storage.used_percent >= 90 ? " storage-meter--warning" : ""}`} role="progressbar" aria-valuenow={storage.used_percent}><i className="storage-meter-fill" style={{ width: `${Math.min(100, storage.used_percent)}%` }} /></div>}</article>
    </section>
    <CaptureResults summary={data.capture_summary} recent={data.recent_captures ?? []} />
    <section className="card overview-card"><div className="section-heading"><div><h3>Experiment timeline</h3><p>Planned progress across each experiment day.</p></div></div><div className="experiment-days">{s.days.map(day => <div className={`experiment-day experiment-day--${day.status}`} title={`${day.elapsed_captures} of ${day.total_captures} captures elapsed`} key={day.number}><strong>Day {day.number}</strong><span>{new Date(`${day.date}T12:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</span></div>)}</div><div className="day-legend"><span className="complete">Complete</span><span className="current">Current</span><span className="upcoming">Upcoming</span></div></section>
    <DailyActivity schedule={s} />
    <StopExperiment schedule={s} initiallyPending={data.cancellation_pending} />
  </div>;
}

function StopExperiment({ schedule, initiallyPending }) {
  const [confirming, setConfirming] = useState(false);
  const [accepted, setAccepted] = useState(false);
  const [pending, setPending] = useState(initiallyPending);
  const [error, setError] = useState(null);
  if (!["active", "upcoming"].includes(schedule.lifecycle)) return null;
  const upcoming = schedule.lifecycle === "upcoming";
  const title = upcoming ? "Cancel scheduled experiment" : "Stop experiment";
  const description = upcoming
    ? "Prevent this experiment from starting. Its schedule will be archived."
    : "Cancel all remaining captures while preserving data already collected.";
  const confirmation = upcoming
    ? "I understand that no captures will be taken for this experiment."
    : "I understand that this experiment cannot be resumed.";
  const stop = async () => {
    setPending(true); setError(null);
    try {
      await api("/api/scheduler/cancel", { method: "POST", body: JSON.stringify({ schedule_hash: schedule.hash }) });
      setConfirming(false);
    } catch (reason) {
      setPending(false); setError(reason);
    }
  };
  return <section className="card stop-experiment">
    <div><h3>{title}</h3><p>{description}</p>{error && <small className="blocked-copy">{error.message}</small>}</div>
    {!confirming ? <div className="stop-actions"><Link className="button-link secondary" to="/schedule">Replace schedule…</Link><button className="danger-button" disabled={pending || initiallyPending} onClick={() => setConfirming(true)}>{pending || initiallyPending ? (upcoming ? "Cancelling schedule…" : "Stopping experiment…") : title}</button></div> : <div className="stop-confirmation"><label><input type="checkbox" checked={accepted} onChange={event => setAccepted(event.target.checked)} /> {confirmation}</label><div><button className="secondary" onClick={() => { setConfirming(false); setAccepted(false); }}>{upcoming ? "Keep schedule" : "Keep running"}</button><button className="danger-button" disabled={!accepted || pending} onClick={stop}>{upcoming ? "Cancel experiment" : "Stop remaining captures"}</button></div></div>}
  </section>;
}

function CaptureResults({ summary, recent }) {
  if (!summary) return null;
  return <section className="card capture-results"><div className="section-heading"><div><h3>Capture results</h3><p>Recorded outcomes for the current experiment run.</p></div></div><div className="capture-result-grid">
    {[["success", "Successful", summary.succeeded], ["failure", "Failed", summary.failed], ["missed", "Missed", summary.missed], ["", "Remaining", summary.remaining], ["warning", "Awaiting result", summary.elapsed_unreported]].map(([kind, label, value]) => <div className={`capture-result${kind ? ` capture-result--${kind}` : ""}`} key={label}><span>{label}</span><strong>{value}</strong></div>)}
  </div>{recent.length > 0 && <div className="recent-captures-shell"><h4>Recent outcomes</h4><div className="recent-captures">{recent.map((item, index) => <div className={`recent-capture recent-capture--${item.status}`} key={`${item.scheduled_at}-${index}`}><strong>{item.status}</strong><span>{formatDateTime(item.scheduled_at)}</span><small>{item.message}</small></div>)}</div></div>}</section>;
}

function DailyActivity({ schedule: s }) {
  const activity = s.daily_activity;
  const hours = values => values.map(hour => <div className={`activity-hour${hour.capture_count ? " activity-hour--active" : ""}${hour.intensity_percent >= 45 ? " activity-hour--strong" : ""}`} style={{ "--activity-intensity": 0.08 + hour.intensity_percent / 100 * .92 }} title={`${hour.label}: ${hour.capture_count} planned captures`} key={hour.hour}><span>{String(hour.hour).padStart(2, "0")}</span><strong>{hour.capture_count || "·"}</strong></div>);
  return <section className="dashboard-grid"><section className="card overview-card activity-card"><div className="section-heading"><div><h3>Daily imaging window</h3><p>{s.daily_time_points} time points and {s.daily_captures} planned captures per day.</p></div></div><div className="activity-summary"><div><span>Imaging window</span><strong>{activity.window_label}</strong><small>{activity.window_duration_label}</small></div><div><span>Cadence</span><strong>{activity.cadence_label}</strong></div><div><span>Peak load</span><strong>{activity.peak_captures_per_hour} captures / hour</strong></div></div><div className="activity-profile-shell" role="img" aria-label="Hourly daily imaging activity"><div className="activity-period"><span>00–11</span><div className="activity-hours">{hours(activity.hours.slice(0, 12))}</div></div><div className="activity-period"><span>12–23</span><div className="activity-hours">{hours(activity.hours.slice(12))}</div></div></div><div className="activity-legend"><span>No captures</span><i /><span>Peak: {activity.peak_captures_per_hour} captures per hour</span></div><div className="replicate-compact"><div><strong>Technical replicates</strong><p>{s.replicates} capture{s.replicates === 1 ? "" : "s"} per time point, spaced {s.replicate_interval_seconds} seconds apart.</p></div><div className="replicate-burst">{s.replicate_offsets.map(item => <div key={item.number}><strong>{item.number}</strong><span>+{item.offset_seconds}s</span></div>)}</div></div></section></section>;
}
