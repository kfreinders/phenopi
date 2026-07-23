import { useEffect, useRef, useState } from "react";
import { ErrorNotice, Loading } from "../components";
import { detectAnalysisRoi, getAnalysisConfig, previewAnalysis } from "../api";

const stageLabels = {
  channel: ["LAB channel", "Values used for thresholding"],
  mask: ["Plant mask", "White pixels are selected"],
  overlay: ["Segmentation overlay", "Selected plant material"],
};

export function AnalysisSetupPage() {
  const [config, setConfig] = useState(null);
  const [imageData, setImageData] = useState(null);
  const [fileName, setFileName] = useState("");
  const [stages, setStages] = useState(null);
  const [roi, setRoi] = useState(null);
  const [analysisCrop, setAnalysisCrop] = useState({ x: 0, y: 0, width: 1, height: 1 });
  const [detectingRoi, setDetectingRoi] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const requestNumber = useRef(0);

  useEffect(() => {
    getAnalysisConfig()
      .then(payload => setConfig(payload.config))
      .catch(setError);
  }, []);

  useEffect(() => {
    if (!imageData || !config) return;
    const controller = new AbortController();
    const currentRequest = ++requestNumber.current;
    const timer = window.setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const result = await previewAnalysis(imageData, config, controller.signal);
        if (currentRequest === requestNumber.current) setStages(result.stages);
      } catch (reason) {
        if (reason.name !== "AbortError" && currentRequest === requestNumber.current) setError(reason);
      } finally {
        if (currentRequest === requestNumber.current) setLoading(false);
      }
    }, 350);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [imageData, config]);

  const selectImage = event => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setError(new Error("Choose a JPEG or PNG calibration image."));
      return;
    }
    if (file.size > 10_000_000) {
      setError(new Error("The calibration image must be 10 MB or smaller."));
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      setFileName(file.name);
      setImageData(reader.result);
      setStages(null);
      setRoi(null);
      setAnalysisCrop({ x: 0, y: 0, width: 1, height: 1 });
      setError(null);
    };
    reader.onerror = () => setError(new Error("The calibration image could not be read."));
    reader.readAsDataURL(file);
  };

  const update = (key, value) => {
    setRoi(null);
    if (key === "rotate_angle") setAnalysisCrop({ x: 0, y: 0, width: 1, height: 1 });
    setConfig(current => ({ ...current, [key]: value }));
  };
  const updateCrop = value => {
    setRoi(null);
    setAnalysisCrop(value);
  };
  const detectRoi = async () => {
    setDetectingRoi(true);
    setError(null);
    try {
      const result = await detectAnalysisRoi(imageData, config, analysisCrop);
      setRoi(result);
    } catch (reason) {
      setError(reason);
    } finally {
      setDetectingRoi(false);
    }
  };
  if (!config) return <Loading label="Loading analysis settings" />;

  return <section className="analysis-page">
    <header className="react-page-heading"><h2>Analysis setup</h2><p>Tune plant segmentation using a representative calibration image.</p></header>
    <ErrorNotice error={error} />
    <div className="analysis-setup-layout">
      <aside className="card analysis-controls">
        <div className="analysis-image-picker">
          <strong>Calibration image</strong>
          <p>Use an image with the same lighting, camera position and plants as the experiment.</p>
          <label className="button-link secondary analysis-file-button">
            {fileName ? "Choose another image" : "Choose image"}
            <input type="file" accept="image/jpeg,image/png" onChange={selectImage} />
          </label>
          {fileName && <small title={fileName}>{fileName}</small>}
        </div>
        <fieldset disabled={!imageData}>
          <legend>Segmentation</legend>
          <label className="analysis-control"><span>LAB channel <output>{config.sepchannel.toUpperCase()}</output></span>
            <select value={config.sepchannel} onChange={event => update("sepchannel", event.target.value)}>
              <option value="l">L — lightness</option><option value="a">A — green to magenta</option><option value="b">B — blue to yellow</option>
            </select>
          </label>
          <RangeControl label="Threshold" value={config.threshold} min={0} max={255} onChange={value => update("threshold", value)} />
          <RangeControl label="Remove small regions" value={config.fill_size} min={0} max={2000} step={10} onChange={value => update("fill_size", value)} />
          <RangeControl label="Rotation" value={config.rotate_angle} min={-10} max={10} step={0.1} suffix="°" onChange={value => update("rotate_angle", value)} />
        </fieldset>
        <fieldset disabled={!imageData}>
          <legend>ROI grid</legend>
          <p className="analysis-roi-note">Draw the analysis area around the tray first, excluding labels, calibration cards and surrounding equipment.</p>
          <div className="analysis-grid-size">
            <label>Rows<input type="number" min="1" max="30" value={config.roi_rows} onChange={event => update("roi_rows", Number(event.target.value))} /></label>
            <label>Columns<input type="number" min="1" max="30" value={config.roi_cols} onChange={event => update("roi_cols", Number(event.target.value))} /></label>
          </div>
          <button type="button" className="analysis-detect-button" onClick={detectRoi} disabled={detectingRoi}>{detectingRoi ? "Detecting ROI grid…" : roi ? "Detect ROI grid again" : "Detect ROI grid"}</button>
          <p className="analysis-roi-note">PlantCV performs this slower detection once. The resulting grid is reused for every image in the experiment.</p>
        </fieldset>
      </aside>
      <section className={`analysis-preview-area${loading ? " is-updating" : ""}`} aria-live="polite">
        {!imageData && <div className="card analysis-empty"><span aria-hidden="true">◫</span><h3>Select a calibration image</h3><p>The segmentation stages will appear here as you adjust the controls.</p></div>}
        {imageData && !stages && <Loading label="Generating analysis preview" />}
        {stages && <div className="analysis-stage-grid">
          <article className="card analysis-stage analysis-stage--crop">
            <header><div><h3>Analysis area</h3><p>Drag across the image to isolate the tray</p></div><button type="button" className="text-button analysis-crop-reset" onClick={() => updateCrop({ x: 0, y: 0, width: 1, height: 1 })}>Reset</button></header>
            <CropSelector image={stages.original} crop={analysisCrop} onChange={updateCrop} />
          </article>
          {Object.entries(stageLabels).map(([key, [title, description]]) => <article className="card analysis-stage" key={key}>
            <header><div><h3>{title}</h3><p>{description}</p></div>{loading && key === "overlay" && <span className="analysis-updating">Updating…</span>}</header>
            <div className="analysis-stage-image"><img src={stages[key]} alt={`${title} analysis preview`} /></div>
          </article>)}
          {roi && <article className="card analysis-stage analysis-stage--roi">
            <header><div><h3>Automatic ROI grid</h3><p>{roi.definition.rows} × {roi.definition.columns} reusable regions</p></div><span className="analysis-roi-ready">Detected</span></header>
            <div className="analysis-stage-image"><img src={roi.overlay} alt="Automatically detected PlantCV ROI grid" /></div>
          </article>}
        </div>}
      </section>
    </div>
  </section>;
}

function RangeControl({ label, value, min, max, step = 1, suffix = "", onChange }) {
  return <label className="analysis-control"><span>{label}<output>{value}{suffix}</output></span>
    <input type="range" value={value} min={min} max={max} step={step} onChange={event => onChange(Number(event.target.value))} />
  </label>;
}

function CropSelector({ image, crop, onChange }) {
  const element = useRef(null);
  const drag = useRef(null);
  const position = event => {
    const bounds = element.current.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width)),
      y: Math.max(0, Math.min(1, (event.clientY - bounds.top) / bounds.height)),
    };
  };
  const start = event => {
    const action = event.target.dataset.cropAction;
    if (!action) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = {
      action,
      handle: event.target.dataset.cropHandle,
      point: position(event),
      crop,
    };
  };
  const move = event => {
    if (!drag.current) return;
    const point = position(event);
    onChange(adjustCrop(
      drag.current.crop,
      drag.current.action,
      drag.current.handle,
      point.x - drag.current.point.x,
      point.y - drag.current.point.y,
    ));
  };
  const finish = () => {
    drag.current = null;
  };
  return <div ref={element} className="analysis-crop-canvas" onPointerDown={start} onPointerMove={move} onPointerUp={finish} onPointerCancel={finish}>
    <img src={image} alt="Calibration image for selecting the analysis area" draggable={false} />
    <span className="analysis-crop-selection" data-crop-action="move" style={{ left: `${crop.x * 100}%`, top: `${crop.y * 100}%`, width: `${crop.width * 100}%`, height: `${crop.height * 100}%` }}>
      <i data-crop-action="resize" data-crop-handle="nw" /><i data-crop-action="resize" data-crop-handle="ne" /><i data-crop-action="resize" data-crop-handle="se" /><i data-crop-action="resize" data-crop-handle="sw" />
    </span>
  </div>;
}

export function adjustCrop(crop, action, handle, deltaX, deltaY, minimum = 0.02) {
  const clamp = (value, lower, upper) => Math.max(lower, Math.min(upper, value));
  const normalized = value => Math.round(value * 1_000_000) / 1_000_000;
  if (action === "move") {
    return {
      ...crop,
      x: normalized(clamp(crop.x + deltaX, 0, 1 - crop.width)),
      y: normalized(clamp(crop.y + deltaY, 0, 1 - crop.height)),
    };
  }
  let left = crop.x;
  let right = crop.x + crop.width;
  let top = crop.y;
  let bottom = crop.y + crop.height;
  if (handle?.includes("w")) left = clamp(left + deltaX, 0, right - minimum);
  if (handle?.includes("e")) right = clamp(right + deltaX, left + minimum, 1);
  if (handle?.includes("n")) top = clamp(top + deltaY, 0, bottom - minimum);
  if (handle?.includes("s")) bottom = clamp(bottom + deltaY, top + minimum, 1);
  return {
    x: normalized(left),
    y: normalized(top),
    width: normalized(right - left),
    height: normalized(bottom - top),
  };
}
