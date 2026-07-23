import { useEffect, useRef, useState } from "react";
import { ErrorNotice, Loading } from "../components";
import { detectAnalysisRoi, getAnalysisConfig, previewAnalysis } from "../api";

const stageLabels = {
  original: ["Input", "Rotation and framing"],
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
    if (file.size > 8_500_000) {
      setError(new Error("The calibration image must be smaller than 8.5 MB."));
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      setFileName(file.name);
      setImageData(reader.result);
      setStages(null);
      setRoi(null);
      setError(null);
    };
    reader.onerror = () => setError(new Error("The calibration image could not be read."));
    reader.readAsDataURL(file);
  };

  const update = (key, value) => {
    setRoi(null);
    setConfig(current => ({ ...current, [key]: value }));
  };
  const detectRoi = async () => {
    setDetectingRoi(true);
    setError(null);
    try {
      const result = await detectAnalysisRoi(imageData, config);
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
