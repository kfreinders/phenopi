const schedulerHealthLabels = {
  healthy: "Healthy",
  waiting_for_schedule: "Waiting for schedule",
  invalid_schedule: "Invalid schedule",
  stale: "Scheduler not responding",
  unavailable: "Unavailable",
};

function renderSchedulerHealth(data) {
  const pill = document.getElementById("scheduler-status-pill");
  const label = schedulerHealthLabels[data.status] ?? data.status;
  pill.className = `status-pill status-pill--${data.status}`;
  document.getElementById("scheduler-status").textContent = label;
  document.getElementById("health-freshness").textContent =
    data.age_seconds === null ? "no heartbeat" : `${Math.round(data.age_seconds)}s`;
  pill.title = data.message;
  pill.setAttribute("aria-label", `${label}. ${data.message}`);
}

async function refreshSchedulerHealth() {
  try {
    const response = await fetch("/api/scheduler/health", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    renderSchedulerHealth(await response.json());
  } catch (error) {
    console.error(error);
    renderSchedulerHealth({
      status: "unavailable",
      message: "The scheduler status endpoint could not be reached.",
      age_seconds: null,
    });
  }
}

const initialSchedulerStatus = document.getElementById("initial-scheduler-status");
if (initialSchedulerStatus) {
  renderSchedulerHealth(JSON.parse(initialSchedulerStatus.textContent));
  document.addEventListener("scheduler-status-updated", (event) => {
    renderSchedulerHealth(event.detail);
  });
} else {
  refreshSchedulerHealth();
  window.setInterval(refreshSchedulerHealth, 5000);
}
