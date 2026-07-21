const expectedScheduleHash = JSON.parse(document.getElementById("expected-schedule-hash").textContent);
const activationStartedAt = Date.now();
let activationTimer = null;
let activationTerminal = false;

function showActivationState(kind, title, message) {
  const icon = document.getElementById("activation-icon");
  icon.className = `activation-icon activation-icon--${kind}`;
  icon.textContent = kind === "confirmed" ? "✓" : kind === "rejected" ? "!" : "↻";
  document.getElementById("activation-title").textContent = title;
  document.getElementById("activation-message").textContent = message;
}

function renderActivation(data) {
  document.dispatchEvent(new CustomEvent("scheduler-status-updated", { detail: data }));
  if (data.schedule?.hash === expectedScheduleHash) {
    activationTerminal = true;
    showActivationState("confirmed", "Schedule confirmed", "The scheduler has loaded the activated schedule and is ready.");
    document.querySelectorAll(".workflow-step")[2].className = "workflow-step workflow-step--complete";
    document.querySelectorAll(".workflow-step")[2].querySelector("span").textContent = "✓";
    document.querySelectorAll(".workflow-step")[2].removeAttribute("aria-current");
    document.querySelectorAll(".workflow-step")[3].className = "workflow-step workflow-step--current";
    document.querySelectorAll(".workflow-step")[3].setAttribute("aria-current", "step");
    document.getElementById("activation-actions").hidden = false;
    document.getElementById("create-another-schedule").hidden = false;
    window.clearInterval(activationTimer);
    return;
  }
  if (data.status === "invalid_schedule" && Date.now() - activationStartedAt >= 35000) {
    activationTerminal = true;
    showActivationState("rejected", "Scheduler rejected the schedule", data.message);
    document.getElementById("activation-actions").hidden = false;
    window.clearInterval(activationTimer);
    return;
  }
  if (Date.now() - activationStartedAt >= 90000) {
    activationTerminal = true;
    showActivationState("waiting", "Schedule not yet confirmed", "The scheduler has not confirmed the schedule within 90 seconds. The schedule may still be loading.");
    document.getElementById("activation-actions").hidden = false;
    window.clearInterval(activationTimer);
    return;
  }
  if (data.status === "stale" || data.status === "unavailable") {
    showActivationState("waiting", "Confirmation paused", "The scheduler is not responding, so activation cannot currently be confirmed.");
  } else {
    showActivationState("waiting", "Waiting for scheduler confirmation", "The schedule was activated safely. Phenopi is waiting for the scheduler to report that it loaded the exact schedule.");
  }
}

async function refreshActivation() {
  try {
    const response = await fetch("/api/scheduler/status", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    renderActivation(await response.json());
  } catch (error) {
    console.error(error);
    renderActivation({ status: "unavailable", message: "Scheduler status could not be reached.", schedule: null });
  }
}

renderActivation(JSON.parse(document.getElementById("initial-scheduler-status").textContent));
if (!activationTerminal) {
  activationTimer = window.setInterval(refreshActivation, 2000);
}
