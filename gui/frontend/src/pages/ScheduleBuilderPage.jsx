import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { ErrorNotice, Loading, WorkflowSteps } from "../components";

const numericFields = new Set(["num_days", "replicates", "replicate_interval_seconds", "every_step_minutes", "duration_minutes", "duration_step_minutes", "centered_before_minutes", "centered_after_minutes", "centered_step_minutes"]);

export function ScheduleBuilderPage({ edit = false }) {
  const navigate = useNavigate(); const [form, setForm] = useState(null); const [minimum, setMinimum] = useState(""); const [error, setError] = useState(null); const [saving, setSaving] = useState(false);
  useEffect(() => { api(`/api/schedule/configure?edit=${edit}`).then(data => { if (!edit && data.draft_state === "ready") navigate("/schedule/review", { replace: true }); else { setForm(data.form); setMinimum(data.minimum_start_date); } }).catch(setError); }, [edit, navigate]);
  if (!form && !error) return <Loading label="Loading schedule builder" />;
  const update = event => {
    const { name, value } = event.target; let next = numericFields.has(name) ? Number(value) : value;
    setForm(current => {
      const changed = { ...current, [name]: next };
      if (name === "replicates") changed.replicate_interval_seconds = next > 1 ? (current.replicate_interval_seconds || 30) : 0;
      return changed;
    });
  };
  const submit = async event => { event.preventDefault(); setSaving(true); setError(null); try { await api("/api/schedule/draft", { method: "POST", body: JSON.stringify(form) }); navigate("/schedule/review"); } catch (reason) { setError(reason); } finally { setSaving(false); } };
  return <><WorkflowSteps current={1} /><section className="card"><div className="card-header"><div><h2>Schedule builder</h2><p>Step 1: configure when Phenopi should capture images.</p></div></div><ErrorNotice error={error} />{form && <form className="schedule-form" onSubmit={submit}>
    <fieldset><legend>Schedule mode</legend><div className="radio-row">{[["every", "Every n minutes"], ["duration", "Fixed duration"], ["centered", "Centered window"]].map(([value, label]) => <label key={value}><input type="radio" name="mode" value={value} checked={form.mode === value} onChange={update} /> {label}</label>)}</div></fieldset>
    <fieldset><legend>Experiment</legend><div className="grid experiment-details"><TextField label="Experiment name" name="experiment_name" value={form.experiment_name} onChange={update} required maxLength={80} /><TextField label="Researcher" optional name="researcher" value={form.researcher ?? ""} onChange={update} maxLength={80} /></div><label><span className="field-label">Notes <span className="optional">Optional</span></span><textarea name="notes" maxLength="1000" rows="3" value={form.notes ?? ""} onChange={update} /></label><div className="grid schedule-timing-fields"><Field label="Start date" type="date" name="start_date" value={form.start_date} min={minimum} onChange={update} /><Field label="Number of days" type="number" name="num_days" value={form.num_days} min="1" max="3650" onChange={update} /><Field label="Replicates" type="number" name="replicates" value={form.replicates} min="1" max="100" onChange={update} /><label className={`replicate-interval-control${form.replicates <= 1 ? " is-inactive" : ""}`}>Replicate interval (s)<input type="number" name="replicate_interval_seconds" min="0" max="86400" value={form.replicate_interval_seconds} readOnly={form.replicates <= 1} aria-disabled={form.replicates <= 1} onChange={update} required /></label></div></fieldset>
    {form.mode === "every" && <fieldset><legend>Every n minutes</legend><div className="grid"><Field label="Start time" type="time" name="every_start" value={form.every_start} onChange={update} /><Field label="End time" type="time" name="every_end" value={form.every_end} onChange={update} /><Field label="Step minutes" type="number" name="every_step_minutes" value={form.every_step_minutes} min="1" max="1440" onChange={update} /></div></fieldset>}
    {form.mode === "duration" && <fieldset><legend>Fixed duration</legend><div className="grid"><Field label="Start time" type="time" name="duration_start" value={form.duration_start} onChange={update} /><Field label="Duration minutes" type="number" name="duration_minutes" value={form.duration_minutes} min="0" max="1439" onChange={update} /><Field label="Step minutes" type="number" name="duration_step_minutes" value={form.duration_step_minutes} min="1" max="1440" onChange={update} /></div></fieldset>}
    {form.mode === "centered" && <fieldset><legend>Centered window</legend><div className="grid"><Field label="Center time" type="time" name="centered_center" value={form.centered_center} onChange={update} /><Field label="Before minutes" type="number" name="centered_before_minutes" value={form.centered_before_minutes} min="0" max="1439" onChange={update} /><Field label="After minutes" type="number" name="centered_after_minutes" value={form.centered_after_minutes} min="0" max="1439" onChange={update} /><Field label="Step minutes" type="number" name="centered_step_minutes" value={form.centered_step_minutes} min="1" max="1440" onChange={update} /></div></fieldset>}
    <div className="actions"><button type="submit" disabled={saving}>{saving ? "Preparing review…" : "Continue to review"}</button></div>
  </form>}</section></>;
}

function Field({ label, ...props }) { return <label>{label}<input {...props} required /></label>; }
function TextField({ label, optional, ...props }) { return <label><span className="field-label">{label} {optional && <span className="optional">Optional</span>}</span><input type="text" {...props} /></label>; }

