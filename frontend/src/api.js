export const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

let authToken = localStorage.getItem("leakguard_token") || "";

export function setToken(token) {
  authToken = token;
  if (token) {
    localStorage.setItem("leakguard_token", token);
  } else {
    localStorage.removeItem("leakguard_token");
  }
}

export function getToken() {
  return authToken || localStorage.getItem("leakguard_token") || "";
}

async function request(path, options = {}) {
  const token = getToken();
  const headers = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  };

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    throw new Error(data?.detail || `Request failed (${res.status})`);
  }
  return data;
}

/* Authentication */
export function login(username, password) {
  return request("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function getDemoAccounts() {
  return request("/api/auth/demo-accounts");
}

export function getMe() {
  return request("/api/auth/me");
}

/* User Workspace & Branches */
export function getUserBranches() {
  return request("/api/user/branches");
}

export function getBranchDetail(branchId) {
  return request(`/api/user/branches/${encodeURIComponent(branchId)}`);
}

export function triggerBranchAction(branchId, action) {
  return request(`/api/user/branches/${encodeURIComponent(branchId)}/action`, {
    method: "POST",
    body: JSON.stringify({ action }),
  });
}

/* Public Repo Scan */
export function scanRepo(repoUrl) {
  return request("/api/scan", {
    method: "POST",
    body: JSON.stringify({ repo_url: repoUrl }),
  });
}

/* Admin Dashboard & Energy Channeling Radar */
export function getOverview() {
  return request("/api/admin/overview");
}

export function getRepos() {
  return request("/api/admin/repos");
}

export function getAdminHotspots() {
  return request("/api/admin/hotspots");
}

export function getAdminBranches() {
  return request("/api/admin/branches");
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
