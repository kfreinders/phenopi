function updateModeSections() {
  const mode = document.querySelector('input[name="mode"]:checked')?.value;
  for (const section of document.querySelectorAll("[data-mode-section]")) {
    section.hidden = section.dataset.modeSection !== mode;
  }
}

function updateReplicateInterval() {
  const replicates = document.getElementById("replicates");
  const interval = document.getElementById("replicate-interval");
  const control = document.getElementById("replicate-interval-control");
  const hasReplicates = Number(replicates.value) > 1;

  interval.readOnly = !hasReplicates;
  interval.setAttribute("aria-disabled", String(!hasReplicates));
  control.classList.toggle("is-inactive", !hasReplicates);
  if (hasReplicates && Number(interval.value) === 0) interval.value = "30";
  if (!hasReplicates) interval.value = "0";
}

for (const radio of document.querySelectorAll('input[name="mode"]')) {
  radio.addEventListener("change", updateModeSections);
}
document.getElementById("replicates").addEventListener("input", updateReplicateInterval);
updateModeSections();
updateReplicateInterval();
