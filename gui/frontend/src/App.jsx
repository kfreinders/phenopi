import { Navigate, Outlet, Route, Routes } from "react-router-dom";
import { Navigation } from "./components";
import { useSchedulerHealth } from "./hooks";
import { SchedulerPage } from "./pages/SchedulerPage";
import { ScheduleBuilderPage } from "./pages/ScheduleBuilderPage";
import { ScheduleReviewPage } from "./pages/ScheduleReviewPage";
import { ActivationPage } from "./pages/ActivationPage";
import { CameraPage } from "./pages/CameraPage";
import { ExperimentDownloadPage } from "./pages/ExperimentDownloadPage";

const healthLabels = {
  healthy: "Healthy", waiting_for_schedule: "Waiting for schedule",
  invalid_schedule: "Invalid schedule", stale: "Scheduler not responding",
  unavailable: "Unavailable",
};

function Shell() {
  const { data, error } = useSchedulerHealth();
  const health = data ?? { status: error ? "unavailable" : "loading", age_seconds: null, message: error?.message ?? "Loading scheduler health" };
  const label = healthLabels[health.status] ?? "Loading";
  return <>
    <header className="topbar"><div className="topbar-inner"><div><h1>Phenopi</h1><p>Experiment setup and analysis interface</p></div>
      <a className={`status-pill status-pill--${health.status}`} href="/scheduler" title={health.message} aria-label={`${label}. ${health.message}`}>
        <span className="status-pill-dot" aria-hidden="true" /><strong>{label}</strong><small>{health.age_seconds == null ? "—" : `${Math.round(health.age_seconds)}s`}</small>
      </a></div></header>
    <main className="layout"><Navigation /><Outlet /></main>
  </>;
}

export default function App() {
  return <Routes><Route element={<Shell />}>
    <Route index element={<Navigate to="/scheduler" replace />} />
    <Route path="scheduler" element={<SchedulerPage />} />
    <Route path="schedule" element={<ScheduleBuilderPage />} />
    <Route path="schedule/edit" element={<ScheduleBuilderPage edit />} />
    <Route path="schedule/review" element={<ScheduleReviewPage />} />
    <Route path="schedule/activation" element={<ActivationPage />} />
    <Route path="camera" element={<CameraPage />} />
    <Route path="experiments/:runId" element={<ExperimentDownloadPage />} />
    <Route path="*" element={<Navigate to="/scheduler" replace />} />
  </Route></Routes>;
}
