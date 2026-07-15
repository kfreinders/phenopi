const video = document.getElementById("camera-preview");
const placeholder = document.getElementById("camera-placeholder");
const startButton = document.getElementById("start-camera");
const stopButton = document.getElementById("stop-camera");
const statusText = document.getElementById("camera-status");
const resolutionText = document.getElementById("camera-resolution");

let activeStream = null;

function setStatus(message) {
  statusText.textContent = message;
}

function setPreviewActive(isActive) {
  placeholder.hidden = isActive;
  video.hidden = !isActive;
  startButton.disabled = isActive;
  stopButton.disabled = !isActive;
}

function updateResolution() {
  if (!video.videoWidth || !video.videoHeight) {
    resolutionText.textContent = "—";
    return;
  }

  resolutionText.textContent = `${video.videoWidth} × ${video.videoHeight}`;
}

async function startCamera() {
  try {
    setStatus("Requesting camera access...");

    activeStream = await navigator.mediaDevices.getUserMedia({
      video: {
        width: { ideal: 1280 },
        height: { ideal: 720 },
      },
      audio: false,
    });

    video.srcObject = activeStream;

    video.addEventListener(
      "loadedmetadata",
      () => {
        updateResolution();
        setPreviewActive(true);
        setStatus("Live");
      },
      { once: true },
    );
  } catch (error) {
    console.error(error);
    setStatus("Camera access failed");
    setPreviewActive(false);

    if (error.name === "NotAllowedError") {
      alert("Camera access was denied by the browser.");
    } else if (error.name === "NotFoundError") {
      alert("No webcam was found.");
    } else {
      alert(`Could not start camera preview: ${error.message}`);
    }
  }
}

function stopCamera() {
  if (activeStream) {
    for (const track of activeStream.getTracks()) {
      track.stop();
    }
  }

  activeStream = null;
  video.srcObject = null;

  setPreviewActive(false);
  setStatus("Inactive");
  resolutionText.textContent = "—";
}

startButton.addEventListener("click", startCamera);
stopButton.addEventListener("click", stopCamera);

setPreviewActive(false);
