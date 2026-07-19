function updateModeSections() {
  const mode = document.querySelector('input[name="mode"]:checked')?.value;
  for (const section of document.querySelectorAll("[data-mode-section]")) {
    section.hidden = section.dataset.modeSection !== mode;
  }
}

for (const radio of document.querySelectorAll('input[name="mode"]')) {
  radio.addEventListener("change", updateModeSections);
}
updateModeSections();
