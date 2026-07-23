export async function api(path, options = {}) {
  const response = await fetch(path, {
    cache: "no-store",
    headers: options.body ? { "Content-Type": "application/json", ...options.headers } : options.headers,
    ...options,
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const payload = await response.json();
      message = typeof payload.detail === "string" ? payload.detail : message;
    } catch {}
    throw new Error(message);
  }
  return response.status === 204 ? null : response.json();
}

export const getSchedulerStatus = () => api("/api/scheduler/status");
export const getSchedulerHealth = () => api("/api/scheduler/health");

