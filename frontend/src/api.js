const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export function getToken() {
  return localStorage.getItem("lg_token");
}

async function request(path, options) {
  const token = getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    ...options,
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    throw new Error(data?.detail || `Request failed (${res.status})`);
  }
  return data;
}

export function loginRequest(username, password) {
  return request("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
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

export function getTeam() {
  return request("/api/admin/team");
}

export function addTeamMember(username, password) {
  return request("/api/admin/team", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function getRepoLogs(repo) {
  return request(`/api/admin/repos/${encodeURIComponent(repo)}/logs`);
}

export function getRepoIssues(repo) {
  return request(`/api/admin/repos/${encodeURIComponent(repo)}/issues`);
}

export function getRepoPRs(repo) {
  return request(`/api/admin/repos/${encodeURIComponent(repo)}/prs`);
}

export function getPRLogs(repo, prNumber) {
  return request(
    `/api/admin/repos/${encodeURIComponent(repo)}/prs/${prNumber}/logs`
  );
}

export function getPRIssues(repo, prNumber) {
  return request(
    `/api/admin/repos/${encodeURIComponent(repo)}/prs/${prNumber}/issues`
  );
}
