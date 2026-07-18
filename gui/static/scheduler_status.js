const byId = (id) => document.getElementById(id);
const statusCard = byId("scheduler-status-card");
const labels = { healthy: "Healthy", waiting_for_schedule: "Waiting for schedule", invalid_schedule: "Invalid schedule", stale: "Stale heartbeat", unavailable: "Unavailable" };
const lifecycleLabels = { upcoming: "Upcoming", active: "Active", finished: "Finished", empty: "Empty schedule" };

function formatDateTime(value, options = {}) {
  if (!value) return "—";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short", ...options }).format(new Date(value));
}

function relativeTime(value) {
  if (!value) return "";
  const seconds = Math.max(0, Math.round((new Date(value) - new Date()) / 1000));
  if (seconds < 60) return `in ${seconds} sec`;
  if (seconds < 3600) return `in ${Math.ceil(seconds / 60)} min`;
  if (seconds < 86400) return `in ${Math.floor(seconds / 3600)} hr ${Math.ceil((seconds % 3600) / 60)} min`;
  return `in ${Math.ceil(seconds / 86400)} days`;
}

function formatBytes(value) {
  if (value === null || value === undefined) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value;
  let index = 0;
  while (size >= 1000 && index < units.length - 1) { size /= 1000; index += 1; }
  return `${size.toFixed(index < 3 ? 0 : 1)} ${units[index]}`;
}

function renderHealth(data) {
  statusCard.className = `scheduler-health scheduler-health--${data.status}`;
  byId("scheduler-status").textContent = labels[data.status] ?? data.status;
  byId("scheduler-message").textContent = data.message;
  const freshness = byId("health-freshness");
  freshness.textContent = data.age_seconds === null ? "No heartbeat received" : `Heartbeat ${Math.round(data.age_seconds)} seconds ago`;
  freshness.title = data.last_heartbeat_at ? `Last heartbeat: ${formatDateTime(data.last_heartbeat_at)}` : "";
}

function renderSchedule(data) {
  const schedule = data.schedule;
  const warning = byId("schedule-warning");
  warning.hidden = true;
  if (data.schedule_error || data.schedule_is_last_reported || data.status === "invalid_schedule") {
    warning.hidden = false;
    warning.textContent = data.schedule_error ?? (data.schedule_is_last_reported ? "Showing the schedule last reported by the scheduler. Live state cannot currently be confirmed." : "The edited schedule was rejected. The scheduler is continuing with the valid schedule shown below.");
  }
  byId("schedule-empty").hidden = Boolean(schedule);
  byId("schedule-dashboard").hidden = !schedule;
  if (!schedule) return;

  const lifecycle = byId("schedule-lifecycle");
  lifecycle.className = `lifecycle-badge lifecycle-badge--${schedule.lifecycle}`;
  lifecycle.textContent = lifecycleLabels[schedule.lifecycle] ?? schedule.lifecycle;
  byId("schedule-title").textContent = schedule.lifecycle === "finished" ? "Completed experiment schedule" : "Current experiment schedule";
  byId("schedule-range").textContent = `${schedule.start_date} → ${schedule.end_date} · ${schedule.num_days} day${schedule.num_days === 1 ? "" : "s"}`;

  const progress = schedule.progress_percent;
  byId("progress-percent").textContent = `${progress.toFixed(1)}%`;
  byId("progress-ring").style.setProperty("--progress", `${progress * 3.6}deg`);
  byId("progress-ring").setAttribute("aria-label", `${progress.toFixed(1)} percent planned schedule progress`);
  byId("progress-count").textContent = `${schedule.elapsed_captures} / ${schedule.total_captures} planned`;
  byId("progress-day").textContent = schedule.current_day ? `Day ${schedule.current_day} of ${schedule.num_days}` : (schedule.lifecycle === "finished" ? "Schedule complete" : `${schedule.num_days} scheduled days`);
  byId("metric-next").textContent = formatDateTime(schedule.next_capture_at);
  byId("metric-next-relative").textContent = relativeTime(schedule.next_capture_at);
  byId("metric-final").textContent = formatDateTime(schedule.last_capture_at);

  const capture = data.last_capture;
  const captureCard = byId("last-capture-card");
  captureCard.className = capture ? `metric-state metric-state--${capture.status}` : "";
  byId("metric-last-capture").textContent = capture ? capture.status[0].toUpperCase() + capture.status.slice(1) : "No result yet";
  byId("metric-last-capture-time").textContent = capture ? formatDateTime(capture.scheduled_at) : "Waiting for the first capture";
  if (capture?.message) captureCard.title = capture.message;

  const storage = data.storage;
  const storageCard = byId("storage-card");
  const freePercent = storage ? 100 - storage.used_percent : null;
  storageCard.className = freePercent !== null && freePercent < 5 ? "metric-state metric-state--critical" : (freePercent !== null && freePercent < 10 ? "metric-state metric-state--warning" : "");
  byId("metric-storage").textContent = storage ? `${formatBytes(storage.free_bytes)} free` : "Unavailable";
  byId("metric-storage-used").textContent = storage ? `${storage.used_percent.toFixed(1)}% used` : "Storage telemetry unavailable";

  const dayStrip = byId("day-strip");
  dayStrip.replaceChildren(...schedule.days.map((day) => {
    const element = document.createElement("div");
    element.className = `experiment-day experiment-day--${day.status}`;
    element.title = `${day.elapsed_captures} of ${day.total_captures} planned captures elapsed`;
    const number = document.createElement("strong"); number.textContent = `Day ${day.number}`;
    const date = document.createElement("span"); date.textContent = new Date(`${day.date}T12:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });
    element.append(number, date); return element;
  }));

  const activity = schedule.daily_activity;
  byId("activity-window").textContent = activity.window_label;
  byId("activity-window-duration").textContent = activity.window_duration_label;
  byId("activity-cadence").textContent = activity.cadence_label;
  byId("activity-peak").textContent = `${activity.peak_captures_per_hour} captures / hour`;
  byId("activity-legend-peak").textContent = `Peak: ${activity.peak_captures_per_hour} captures per hour`;
  const renderHours = (hours) => hours.map((hour) => {
    const tile = document.createElement("div");
    tile.className = `activity-hour${hour.capture_count ? " activity-hour--active" : ""}${hour.intensity_percent >= 45 ? " activity-hour--strong" : ""}`;
    tile.style.setProperty("--activity-intensity", `${0.08 + (hour.intensity_percent / 100) * 0.92}`);
    tile.title = `${hour.label}–${String((hour.hour + 1) % 24).padStart(2, "0")}:00: ${hour.capture_count} planned capture${hour.capture_count === 1 ? "" : "s"} across ${hour.time_point_count} time point${hour.time_point_count === 1 ? "" : "s"}`;
    tile.setAttribute("aria-label", tile.title);
    const label = document.createElement("span"); label.textContent = String(hour.hour).padStart(2, "0");
    const count = document.createElement("strong"); count.textContent = hour.capture_count || "·";
    tile.append(label, count);
    return tile;
  });
  byId("activity-am").replaceChildren(...renderHours(activity.hours.slice(0, 12)));
  byId("activity-pm").replaceChildren(...renderHours(activity.hours.slice(12)));
  byId("daily-summary").textContent = `${schedule.daily_time_points} time points and ${schedule.daily_captures} planned captures per day.`;
  byId("replicate-summary").textContent = `${schedule.replicates} capture${schedule.replicates === 1 ? "" : "s"} per time point, spaced ${schedule.replicate_interval_seconds} seconds apart.`;
  byId("replicate-burst").replaceChildren(...schedule.replicate_offsets.map((replicate) => { const item = document.createElement("div"); const dot = document.createElement("strong"); dot.textContent = replicate.number; const offset = document.createElement("span"); offset.textContent = `+${replicate.offset_seconds}s`; item.append(dot, offset); return item; }));
}

function render(data) { renderHealth(data); renderSchedule(data); }

async function refreshStatus() {
  try {
    const response = await fetch("/api/scheduler/status", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    render(await response.json());
  } catch (error) {
    console.error(error);
    render({ status: "unavailable", message: "The scheduler status endpoint could not be reached.", last_heartbeat_at: null, age_seconds: null, schedule: null, schedule_error: null, schedule_is_last_reported: false });
  }
}

render(JSON.parse(byId("initial-scheduler-status").textContent));
window.setInterval(refreshStatus, 5000);
