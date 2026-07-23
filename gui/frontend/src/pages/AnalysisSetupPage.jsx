import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ErrorNotice, Loading, WorkflowSteps } from "../components";
import { attachDraftAnalysis, detectAnalysisRoi, getAnalysisConfig, previewAnalysis, saveAnalysisProfile } from "../api";

const stageLabels = {
  channel: ["LAB channel", "Values used for thresholding"],
  mask: ["Plant mask", "White pixels are selected"],
  overlay: ["Segmentation overlay", "Selected plant material"],
};

export function AnalysisSetupPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const scheduleWorkflow = params.get("workflow") === "schedule";
  const [config, setConfig] = useState(null);
  const [imageData, setImageData] = useState(null);
  const [fileName, setFileName] = useState("");
  const [stages, setStages] = useState(null);
  const [roi, setRoi] = useState(null);
  const [analysisCrop, setAnalysisCrop] = useState({ x: 0, y: 0, width: 1, height: 1 });
  const [maskExclusions, setMaskExclusions] = useState([]);
  const [brushRadius, setBrushRadius] = useState(0.015);
  const [detectingRoi, setDetectingRoi] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const requestNumber = useRef(0);
  const roiResult = useRef(null);

  useEffect(() => {
    getAnalysisConfig()
      .then(payload => { setConfig(payload.config); setSaved(payload.profile_saved); })
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
        const result = await previewAnalysis(imageData, config, analysisCrop, maskExclusions, controller.signal);
        if (currentRequest === requestNumber.current) setStages(result.stages);
      } catch (reason) {
        if (reason.name !== "AbortError" && currentRequest === requestNumber.current) setError(reason);
      } finally {
        if (currentRequest === requestNumber.current) setLoading(false);
      }
    }, 350);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [imageData, config, analysisCrop, maskExclusions]);

  useEffect(() => {
    if (!roi || !roiResult.current) return;
    const frame = window.requestAnimationFrame(() => {
      roiResult.current?.focus({ preventScroll: true });
      const reducedMotion = window.matchMedia?.(
        "(prefers-reduced-motion: reduce)"
      ).matches;
      roiResult.current?.scrollIntoView({
        behavior: reducedMotion ? "auto" : "smooth",
        block: "start",
      });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [roi]);

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
      setSaved(false);
      setAnalysisCrop({ x: 0, y: 0, width: 1, height: 1 });
      setMaskExclusions([]);
      setError(null);
    };
    reader.onerror = () => setError(new Error("The calibration image could not be read."));
    reader.readAsDataURL(file);
  };

  const update = (key, value) => {
    setRoi(null);
    setSaved(false);
    if (key === "rotate_angle") {
      setAnalysisCrop({ x: 0, y: 0, width: 1, height: 1 });
      setMaskExclusions([]);
    }
    setConfig(current => ({ ...current, [key]: value }));
  };
  const updateCrop = value => {
    setRoi(null);
    setSaved(false);
    setMaskExclusions([]);
    setAnalysisCrop(value);
  };
  const updateMaskExclusions = updater => {
    setRoi(null);
    setSaved(false);
    setMaskExclusions(updater);
  };
  const detectRoi = async () => {
    setDetectingRoi(true);
    setError(null);
    try {
      const result = await detectAnalysisRoi(imageData, config, analysisCrop, maskExclusions);
      setRoi(result);
    } catch (reason) {
      setError(reason);
    } finally {
      setDetectingRoi(false);
    }
  };
  const saveProfile = async () => {
    setSaving(true);
    setError(null);
    try {
      await saveAnalysisProfile(config, roi.definition);
      setSaved(true);
      if (scheduleWorkflow) {
        await attachDraftAnalysis();
        navigate("/schedule/review");
      }
    } catch (reason) {
      setError(reason);
    } finally {
      setSaving(false);
    }
  };
  const useSavedProfile = async () => {
    setSaving(true);
    setError(null);
    try {
      await attachDraftAnalysis();
      navigate("/schedule/review");
    } catch (reason) {
      setError(reason);
    } finally {
      setSaving(false);
    }
  };
  if (!config) return <Loading label="Loading analysis settings" />;

  return <section className="analysis-page">
    {scheduleWorkflow && <WorkflowSteps current={2} analysisEnabled />}
    <header className="react-page-heading analysis-page-heading"><div><h2>{scheduleWorkflow ? "Calibrate canopy analysis" : "Analysis setup"}</h2><p>Tune plant segmentation using a representative calibration image.</p></div>{scheduleWorkflow && <Link className="button-link secondary" to="/schedule/edit"><span aria-hidden="true">←</span> Back to configure</Link>}</header>
    <ErrorNotice error={error} />
    {scheduleWorkflow && <section className={`card analysis-workflow-intro${saved ? " analysis-workflow-intro--saved" : ""}`}><div><span aria-hidden="true">{saved ? "✓" : "2"}</span><div><h3>{saved ? "A saved calibration is available" : "Calibration required"}</h3><p>{saved ? "Use it for this experiment if the camera, tray and lighting setup have not changed, or create a new calibration below." : "Canopy measurements cannot start until segmentation and the ROI grid have been calibrated."}</p></div></div>{saved && <button type="button" onClick={useSavedProfile} disabled={saving}>{saving ? "Attaching…" : "Use saved calibration"}</button>}</section>}
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
          <legend>Image orientation</legend>
          <p className="analysis-control-group-note">Rotation is applied before cropping or segmentation and updates every preview.</p>
          <RangeControl label="Rotation" value={config.rotate_angle} min={-10} max={10} step={0.1} suffix="°" onChange={value => update("rotate_angle", value)} />
        </fieldset>
        <fieldset disabled={!imageData}>
          <legend>LAB channel</legend>
          <p className="analysis-control-group-note">Choose the color component shown in the <strong>LAB channel</strong> preview. This becomes the input for thresholding.</p>
          <label className="analysis-control"><span>Channel <output>{config.sepchannel.toUpperCase()}</output></span>
            <select value={config.sepchannel} onChange={event => update("sepchannel", event.target.value)}>
              <option value="l">L — lightness</option><option value="a">A — green to magenta</option><option value="b">B — blue to yellow</option>
            </select>
          </label>
        </fieldset>
        <fieldset disabled={!imageData}>
          <legend>Plant mask</legend>
          <p className="analysis-control-group-note">These controls determine which pixels remain white in the <strong>Plant mask</strong> preview.</p>
          <RangeControl label="Threshold" value={config.threshold} min={0} max={255} onChange={value => update("threshold", value)} />
          <RangeControl label="Remove small regions" value={config.fill_size} min={0} max={2000} step={10} onChange={value => update("fill_size", value)} />
        </fieldset>
        <fieldset disabled={!imageData}>
          <legend>ROI grid</legend>
          <p className="analysis-control-group-note">Set the tray layout, then detect plant regions from the edited mask. Draw the analysis area around the tray first.</p>
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
            {key === "mask" ? <MaskEditor image={stages.mask} strokes={maskExclusions} setStrokes={updateMaskExclusions} radius={brushRadius} setRadius={setBrushRadius} /> : <div className="analysis-stage-image"><img src={stages[key]} alt={`${title} analysis preview`} /></div>}
          </article>)}
          {roi && <article ref={roiResult} className="card analysis-stage analysis-stage--roi" tabIndex="-1">
            <header><div><h3>Automatic ROI grid</h3><p>{roi.definition.rows} × {roi.definition.columns} reusable regions</p></div><span className="analysis-roi-ready">Detected</span></header>
            <div className="analysis-stage-image"><img src={roi.overlay} alt="Automatically detected PlantCV ROI grid" /></div>
            <footer className="analysis-save-profile"><div><strong>{saved ? "Analysis setup saved" : "Ready to save"}</strong><p>{scheduleWorkflow ? "This calibration will be stored with this experiment." : saved ? "New analysis-enabled experiments can use this calibration." : "Save this calibration for a future analysis-enabled experiment."}</p></div><button type="button" onClick={saveProfile} disabled={saving || saved}>{saving ? "Saving…" : saved ? "Saved" : scheduleWorkflow ? "Save and continue to review" : "Save analysis setup"}</button></footer>
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

function MaskEditor({ image, strokes, setStrokes, radius, setRadius }) {
  const surface = useRef(null);
  const canvas = useRef(null);
  const drawing = useRef(false);
  const [cursor, setCursor] = useState(null);

  useEffect(() => {
    const redraw = () => {
      const bounds = surface.current?.getBoundingClientRect();
      const context = canvas.current?.getContext("2d");
      if (!bounds || !context) return;
      const scale = window.devicePixelRatio || 1;
      canvas.current.width = Math.max(1, Math.round(bounds.width * scale));
      canvas.current.height = Math.max(1, Math.round(bounds.height * scale));
      context.scale(scale, scale);
      context.clearRect(0, 0, bounds.width, bounds.height);
      context.strokeStyle = "rgba(0, 0, 0, .88)";
      context.fillStyle = "rgba(0, 0, 0, .88)";
      context.lineCap = "round";
      context.lineJoin = "round";
      for (const stroke of strokes) {
        const brush = stroke.radius * Math.min(bounds.width, bounds.height);
        context.lineWidth = brush * 2;
        context.beginPath();
        stroke.points.forEach((point, index) => {
          const x = point.x * bounds.width;
          const y = point.y * bounds.height;
          if (index === 0) context.moveTo(x, y);
          else context.lineTo(x, y);
        });
        context.stroke();
        if (stroke.points.length === 1) {
          const point = stroke.points[0];
          context.beginPath();
          context.arc(point.x * bounds.width, point.y * bounds.height, brush, 0, Math.PI * 2);
          context.fill();
        }
      }
      if (cursor) {
        const brush = radius * Math.min(bounds.width, bounds.height);
        context.beginPath();
        context.arc(
          cursor.x * bounds.width,
          cursor.y * bounds.height,
          brush,
          0,
          Math.PI * 2,
        );
        context.strokeStyle = "#fff";
        context.lineWidth = 2;
        context.shadowColor = "rgba(0, 0, 0, .8)";
        context.shadowBlur = 3;
        context.stroke();
        context.shadowBlur = 0;
      }
    };
    redraw();
    const observer = new ResizeObserver(redraw);
    if (surface.current) observer.observe(surface.current);
    return () => observer.disconnect();
  }, [strokes, image, cursor, radius]);

  const point = event => {
    const bounds = surface.current.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width)),
      y: Math.max(0, Math.min(1, (event.clientY - bounds.top) / bounds.height)),
    };
  };
  const start = event => {
    drawing.current = true;
    event.currentTarget.setPointerCapture(event.pointerId);
    const nextPoint = point(event);
    setCursor(nextPoint);
    setStrokes(current => [...current, { radius, points: [nextPoint] }]);
  };
  const move = event => {
    const nextPoint = point(event);
    setCursor(nextPoint);
    if (!drawing.current) return;
    setStrokes(current => {
      const next = [...current];
      const stroke = next[next.length - 1];
      const previous = stroke.points[stroke.points.length - 1];
      if (Math.hypot(nextPoint.x - previous.x, nextPoint.y - previous.y) < 0.002) return current;
      next[next.length - 1] = { ...stroke, points: [...stroke.points, nextPoint] };
      return next;
    });
  };
  const finish = () => { drawing.current = false; };

  return <div className="analysis-mask-editor">
    <div className="analysis-mask-tools">
      <label>Brush size<input type="range" min="0.002" max="0.06" step="0.002" value={radius} onChange={event => setRadius(Number(event.target.value))} /></label>
      <button type="button" className="secondary" disabled={!strokes.length} onClick={() => setStrokes(current => current.slice(0, -1))}>Undo stroke</button>
      <button type="button" className="text-button" disabled={!strokes.length} onClick={() => setStrokes([])}>Clear edits</button>
    </div>
    <p className="analysis-mask-hint">Brush over white artefacts to exclude them from ROI calibration.</p>
    <div ref={surface} className="analysis-mask-surface" onPointerDown={start} onPointerMove={move} onPointerEnter={event => setCursor(point(event))} onPointerLeave={() => setCursor(null)} onPointerUp={finish} onPointerCancel={finish}>
      <img src={image} alt="Editable plant-mask analysis preview" draggable={false} />
      <canvas ref={canvas} />
    </div>
  </div>;
}
