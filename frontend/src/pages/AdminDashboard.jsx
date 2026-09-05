import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  getAdminBranches,
  getAdminHotspots,
  getOverview,
  getRecent,
  getRepos,
  getUsers,
} from "../api";

function StatTile({ icon, label, value, subtext }) {
  return (
    <div className="stat-tile">
      <div className="stat-tile-icon">{icon}</div>
      <div className="stat-tile-value">{value ?? "—"}</div>
      <div className="stat-tile-label">{label}</div>
      {subtext && <div className="stat-tile-sub">{subtext}</div>}
    </div>
  );
}

function ConclusionBadge({ conclusion }) {
  const isPass = conclusion === "pass" || conclusion === "PASSED";
  const isWarn = conclusion === "WARNED";
  const isBlock = conclusion === "BLOCKED" || conclusion === "fail";

  const cls = isPass ? "badge-good" : isWarn ? "badge-warning" : "badge-critical";
  const symbol = isPass ? "✓" : isWarn ? "⚠" : "✕";

  return (
    <span className={`badge ${cls}`}>
      {symbol} {conclusion}
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
  const [hotspots, setHotspots] = useState(null);
  const [branches, setBranches] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      getOverview(),
      getRepos(),
      getRecent(),
      getUsers(),
      getAdminHotspots(),
      getAdminBranches(),
    ])
      .then(([o, r, a, u, h, b]) => {
        setOverview(o);
        setRepos(r);
        setRecent(a);
        setUsers(u);
        setHotspots(h);
        setBranches(b);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="page">
        <div className="loading-state">
          <div className="spinner"></div>
          <div>Aggregating real-time CI/CD telemetry across all branches...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page">
        <h1>Admin Security Intelligence Dashboard</h1>
        <div className="error-banner">{error}</div>
      </div>
    );
  }

  return (
    <div className="page admin-dashboard">
      <div className="hero">
        <div className="admin-hero-badge">🛡️ Executive CI/CD Oversight</div>
        <h1>Resource Leak Intelligence & Energy Channeling</h1>
        <p className="subtitle">
          Real-time deterministic AST analytics aggregated across all active branches,
          repositories, and PR gates.
        </p>
      </div>

      {/* Top Telemetry Stats */}
      <div className="stat-tile-row">
        <StatTile icon="📦" label="Tracked Repos" value={overview?.total_repos} />
        <StatTile icon="🌿" label="Active Branches" value={branches.length} />
        <StatTile icon="🔀" label="PRs Scanned" value={overview?.total_pr_runs} />
        <StatTile icon="🐞" label="Leaks Detected" value={overview?.total_findings} />
        <StatTile icon="👥" label="Developers" value={users.length} />
      </div>

      {/* ENERGY CHANNELING RADAR (Core Hackathon Feature) */}
      <div className="energy-radar-panel">
        <div className="radar-header">
          <div>
            <h2>🎯 Where to Channel Energy: Strategic Tech-Debt Radar</h2>
            <p className="radar-subtitle">
              Prioritized recommendations based on static resource lifecycle risk,
              preventing production connection and file descriptor exhaustion.
            </p>
          </div>
          <span className="live-pill">⚡ Dynamic AI/AST Insights</span>
        </div>

        {/* Strategic Guidance Cards */}
        <div className="guidance-grid">
          {hotspots?.recommendations?.map((rec, idx) => (
            <div key={idx} className={`guidance-card priority-${rec.priority.toLowerCase()}`}>
              <div className="guidance-top">
                <span className={`priority-tag p-${rec.priority.toLowerCase()}`}>
                  {rec.priority} PRIORITY
                </span>
                <span className="guidance-area">{rec.area}</span>
              </div>
              <p className="guidance-action">{rec.action}</p>
            </div>
          ))}
        </div>

        {/* Visual Metrics Row */}
        <div className="radar-metrics-row">
          {/* Resource Breakdown Card */}
          <div className="radar-subcard">
            <h3>Resource Vulnerability Distribution</h3>
            <div className="vuln-bars">
              <div className="vuln-item">
                <div className="vuln-meta">
                  <span>🔌 Sockets (`socket.socket`)</span>
                  <span>{hotspots?.resource_breakdown?.socket || 0}</span>
                </div>
                <div className="vuln-track">
                  <div
                    className="vuln-fill fill-socket"
                    style={{
                      width: `${Math.min(100, (hotspots?.resource_breakdown?.socket || 0) * 25)}%`,
                    }}
                  />
                </div>
              </div>

              <div className="vuln-item">
                <div className="vuln-meta">
                  <span>🗄️ Databases (`sqlite3.connect`)</span>
                  <span>{hotspots?.resource_breakdown?.db || 0}</span>
                </div>
                <div className="vuln-track">
                  <div
                    className="vuln-fill fill-db"
                    style={{
                      width: `${Math.min(100, (hotspots?.resource_breakdown?.db || 0) * 20)}%`,
                    }}
                  />
                </div>
              </div>

              <div className="vuln-item">
                <div className="vuln-meta">
                  <span>📄 Files (`open()`)</span>
                  <span>{hotspots?.resource_breakdown?.file || 0}</span>
                </div>
                <div className="vuln-track">
                  <div
                    className="vuln-fill fill-file"
                    style={{
                      width: `${Math.min(100, (hotspots?.resource_breakdown?.file || 0) * 15)}%`,
                    }}
                  />
                </div>
              </div>

              <div className="vuln-item">
                <div className="vuln-meta">
                  <span>📁 Temp Files (`NamedTemporaryFile`)</span>
                  <span>{hotspots?.resource_breakdown?.tempfile || 0}</span>
                </div>
                <div className="vuln-track">
                  <div
                    className="vuln-fill fill-tempfile"
                    style={{
                      width: `${Math.min(100, (hotspots?.resource_breakdown?.tempfile || 0) * 30)}%`,
                    }}
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Critical Working Branches Card */}
          <div className="radar-subcard">
            <h3>High-Risk Working Branches Requiring Intervention</h3>
            {hotspots?.critical_branches?.length === 0 ? (
              <div className="empty-subcard">All active branches are clean!</div>
            ) : (
              <div className="crit-branch-list">
                {hotspots?.critical_branches?.map((cb, idx) => (
                  <div key={idx} className="crit-branch-item">
                    <div className="crit-branch-left">
                      <span className="crit-branch-name">🌿 {cb.branch}</span>
                      <span className="crit-branch-meta">
                        {cb.repo} • PR #{cb.pr_number} by {cb.user_name}
                      </span>
                    </div>
                    <div className="crit-branch-right">
                      <span className="badge badge-critical">{cb.errors} leak(s)</span>
                      <ConclusionBadge conclusion={cb.gate_status} />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ALL WORKING BRANCHES AUDIT TABLE */}
      <h2>Active Working Branches Across Repositories</h2>
      <p className="subtitle" style={{ marginTop: -8 }}>
        Live state of branches where developers are actively committing and raising PRs.
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Repository</th>
              <th>Branch</th>
              <th>PR Title</th>
              <th>Developer</th>
              <th>Gatekeeper Status</th>
              <th>Unresolved Leaks</th>
              <th>Last Checked</th>
            </tr>
          </thead>
          <tbody>
            {branches.length === 0 ? (
              <tr>
                <td colSpan={7} className="empty-row">
                  No active working branches tracked yet.
                </td>
              </tr>
            ) : (
              branches.map((b) => (
                <tr key={b._id}>
                  <td>
                    <Link to={`/admin/repos/${encodeURIComponent(b.repo)}`}>
                      {b.repo}
                    </Link>
                  </td>
                  <td className="code-font">🌿 {b.branch}</td>
                  <td>
                    PR #{b.pr_number}: {b.pr_title}
                  </td>
                  <td>{b.user_name}</td>
                  <td>
                    <ConclusionBadge conclusion={b.gate_status || b.status} />
                  </td>
                  <td className="num">
                    {b.summary?.errors > 0 ? (
                      <span className="badge badge-critical">
                        {b.summary.errors} Error(s)
                      </span>
                    ) : (
                      <span className="badge badge-good">Clean</span>
                    )}
                  </td>
                  <td>{formatTime(b.updated_at)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* REPOSITORIES OVERVIEW TABLE */}
      <h2>Repositories</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Repo</th>
              <th>CI Runs</th>
              <th>PRs</th>
              <th>Accumulated Errors</th>
              <th>Last Action Run</th>
              <th>Latest Result</th>
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

      {/* RECENT CI ACTIVITY */}
      <h2>Recent CI/CD Action Activity</h2>
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
