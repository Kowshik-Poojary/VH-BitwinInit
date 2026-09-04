import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getRepoLogs, getRepoIssues } from "../api";

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

export default function RepoDetail() {
  const { repo: encodedRepo } = useParams();
  const repo = decodeURIComponent(encodedRepo);

  const [logs, setLogs] = useState([]);
  const [issues, setIssues] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([getRepoLogs(repo), getRepoIssues(repo)])
      .then(([l, i]) => {
        setLogs(l);
        setIssues(i);
      })
      .catch((err) => setError(err.message));
  }, [repo]);

  return (
    <div className="page">
      <Link to="/admin" className="back-link">
        ← Back to dashboard
      </Link>
      <div className="hero">
        <h1>{repo}</h1>
        <p className="subtitle">
          Run history and issue attribution for this repository.
        </p>
      </div>

      {error && <div className="error-banner">{error}</div>}

      <h2>Current issues</h2>
      <p className="subtitle" style={{ marginTop: 0 }}>
        From the most recent run. "New" means introduced by that run's user;
        "pre-existing" means it was already there, first reported by an
        earlier user.
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Rule</th>
              <th>Location</th>
              <th>Message</th>
              <th>Status</th>
              <th>First reported by</th>
            </tr>
          </thead>
          <tbody>
            {!issues || issues.issues.length === 0 ? (
              <tr>
                <td colSpan={5} className="empty-row">
                  {issues ? "No open issues in the latest run." : "Loading…"}
                </td>
              </tr>
            ) : (
              issues.issues.map((issue) => (
                <tr key={issue.fingerprint}>
                  <td className="mono">{issue.rule_id}</td>
                  <td className="mono">
                    {issue.location.file}:{issue.location.line}
                  </td>
                  <td>{issue.message}</td>
                  <td>
                    {issue.is_new ? (
                      <span className="badge badge-new">new, this run</span>
                    ) : (
                      <span className="badge badge-past">pre-existing</span>
                    )}
                  </td>
                  <td>
                    {issue.first_seen_user.name}
                    <span className="activity-time">
                      {" "}
                      · {formatTime(issue.first_seen_at)}
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <h2>Run log</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>When</th>
              <th>User</th>
              <th>PR</th>
              <th>Findings</th>
              <th>Result</th>
            </tr>
          </thead>
          <tbody>
            {logs.length === 0 ? (
              <tr>
                <td colSpan={5} className="empty-row">
                  No runs recorded yet.
                </td>
              </tr>
            ) : (
              logs.map((run) => (
                <tr key={run._id}>
                  <td>{formatTime(run.received_at)}</td>
                  <td>{run.user.name}</td>
                  <td>{run.pr_number != null ? `#${run.pr_number}` : "push"}</td>
                  <td className="num">{run.finding_count}</td>
                  <td>
                    <ConclusionBadge conclusion={run.conclusion} />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
