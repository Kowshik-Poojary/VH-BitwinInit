import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getOverview, getRepos, getRecent, getUsers } from "../api";

function StatTile({ icon, label, value }) {
  return (
    <div className="stat-tile">
      <div className="stat-tile-icon">{icon}</div>
      <div className="stat-tile-value">{value ?? "—"}</div>
      <div className="stat-tile-label">{label}</div>
    </div>
  );
}

function initials(name) {
  return name
    .split(" ")
    .map((p) => p[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

function ConclusionBadge({ conclusion }) {
  const isPass = conclusion === "pass";
  return (
    <span className={`badge ${isPass ? "badge-good" : "badge-critical"}`}>
      {isPass ? "✓" : "✕"} {conclusion}
    </span>
  );
}

function formatTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

export default function AdminDashboard() {
  const [overview, setOverview] = useState(null);
  const [repos, setRepos] = useState([]);
  const [recent, setRecent] = useState([]);
  const [users, setUsers] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([getOverview(), getRepos(), getRecent(), getUsers()])
      .then(([o, r, a, u]) => {
        setOverview(o);
        setRepos(r);
        setRecent(a);
        setUsers(u);
      })
      .catch((err) => setError(err.message));
  }, []);

  if (error) {
    return (
      <div className="page">
        <h1>Admin Dashboard</h1>
        <div className="error-banner">{error}</div>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="hero">
        <h1>Admin Dashboard</h1>
        <p className="subtitle">
          Aggregated from every LeakGuard GitHub Action run that reports back
          to this backend.
        </p>
      </div>

      <div className="stat-tile-row">
        <StatTile icon="📦" label="repos tracked" value={overview?.total_repos} />
        <StatTile icon="🔁" label="total runs" value={overview?.total_action_runs} />
        <StatTile icon="🔀" label="PR runs" value={overview?.total_pr_runs} />
        <StatTile icon="🐞" label="findings found" value={overview?.total_findings} />
        <StatTile icon="👤" label="users" value={users.length} />
      </div>

      <h2>Repositories</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Repo</th>
              <th>Runs</th>
              <th>PRs</th>
              <th>Errors (total)</th>
              <th>Last run</th>
              <th>Last result</th>
            </tr>
          </thead>
          <tbody>
            {repos.length === 0 ? (
              <tr>
                <td colSpan={6} className="empty-row">
                  No repos have reported a run yet.
                </td>
              </tr>
            ) : (
              repos.map((r) => (
                <tr key={r.repo}>
                  <td>
                    <Link to={`/admin/repos/${encodeURIComponent(r.repo)}`}>
                      {r.repo}
                    </Link>
                  </td>
                  <td className="num">{r.run_count}</td>
                  <td className="num">{r.pr_count}</td>
                  <td className="num">{r.total_errors}</td>
                  <td>{formatTime(r.last_run_at)}</td>
                  <td>
                    <ConclusionBadge conclusion={r.last_conclusion} />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <h2>Users</h2>
      {users.length === 0 ? (
        <div className="table-wrap">
          <div className="empty-row">No users yet.</div>
        </div>
      ) : (
        <div className="user-grid">
          {users.map((u) => (
            <div className="user-chip" key={u._id}>
              <span className="user-avatar">{initials(u.name)}</span>
              <div>
                <div className="user-chip-name">{u.name}</div>
                <div className="user-chip-id">{u._id}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      <h2>Recent activity</h2>
      <ul className="activity-list">
        {recent.length === 0 ? (
          <li className="empty-row">No activity yet.</li>
        ) : (
          recent.map((run) => (
            <li key={run._id} className="activity-item">
              <ConclusionBadge conclusion={run.conclusion} />
              <Link
                to={`/admin/repos/${encodeURIComponent(run.repo)}`}
                className="activity-repo"
              >
                {run.repo}
              </Link>
              {run.pr_number != null && (
                <Link
                  to={`/admin/repos/${encodeURIComponent(run.repo)}/prs/${run.pr_number}`}
                  className="activity-pr"
                >
                  PR #{run.pr_number}
                </Link>
              )}
              <span className="activity-summary">
                {run.summary.total} finding(s)
              </span>
              <span className="activity-time">
                {formatTime(run.received_at)}
              </span>
            </li>
          ))
        )}
      </ul>
    </div>
  );
}
