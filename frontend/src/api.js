const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

async function request(path, options) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    throw new Error(data?.detail || `Request failed (${res.status})`);
  }
  return data;
}

export function scanRepo(repoUrl) {
  return request("/api/scan", {
    method: "POST",
    body: JSON.stringify({ repo_url: repoUrl }),
  });
}

export function getOverview() {
  return request("/api/admin/overview");
}

export function getRepos() {
  return request("/api/admin/repos");
}

export function getRecent() {
  return request("/api/admin/recent");
}

export function getUsers() {
  return request("/api/admin/users");
}

export function getRepoLogs(repo) {
  return request(`/api/admin/repos/${encodeURIComponent(repo)}/logs`);
}

export function getRepoIssues(repo) {
  return request(`/api/admin/repos/${encodeURIComponent(repo)}/issues`);
}
