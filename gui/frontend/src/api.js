export async function api(path, options = {}) {
  const headers = new Headers(options.headers);
  if (options.body) headers.set("Content-Type", "application/json");
  if (["POST", "PUT", "PATCH", "DELETE"].includes(options.method?.toUpperCase())) {
    headers.set("X-Phenopi-Request", "1");
  }
  const response = await fetch(path, {
    cache: "no-store",
    ...options,
    headers,
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const payload = await response.json();
      if (typeof payload.detail === "string") message = payload.detail;
      else if (Array.isArray(payload.detail) && payload.detail[0]?.msg) {
        message = payload.detail[0].msg.replace(/^Value error, /, "");
      }
    } catch {}
    throw new Error(message);
  }
  return response.status === 204 ? null : response.json();
}

export const getSchedulerStatus = () => api("/api/scheduler/status");
export const getSchedulerHealth = () => api("/api/scheduler/health");
