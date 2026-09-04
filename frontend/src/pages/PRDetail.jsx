import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getPRLogs, getPRIssues } from "../api";

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

export default function PRDetail() {
  const { repo: encodedRepo, prNumber } = useParams();
  const repo = decodeURIComponent(encodedRepo);

  const [logs, setLogs] = useState([]);
  const [issues, setIssues] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([getPRLogs(repo, prNumber), getPRIssues(repo, prNumber)])
      .then(([l, i]) => {
        setLogs(l);
        setIssues(i);
      })
      .catch((err) => setError(err.message));
  }, [repo, prNumber]);

  const newCount = issues?.issues.filter((i) => i.is_new).length ?? 0;
  const preExistingCount = issues?.issues.filter((i) => !i.is_new).length ?? 0;

  return (
    <div className="page">
      <Link to={`/admin/repos/${encodeURIComponent(repo)}`} className="back-link">
        ← Back to {repo}
      </Link>
      <div className="hero">
        <h1>
          {repo} · PR #{prNumber}
        </h1>
        <p className="subtitle">
          Every LeakGuard run reported for this pull request, and the current
          issue breakdown from its most recent run.
        </p>
      </div>

      {error && <div className="error-banner">{error}</div>}

      <h2>Issues on latest run</h2>
      <p className="subtitle" style={{ marginTop: 0 }}>
        <span className="badge badge-new">new, this PR</span> means this
        exact issue (rule + file + line) has never been reported anywhere in
        this repo before — this PR is the first place it showed up.{" "}
        <span className="badge badge-past">pre-existing</span> means the
        issue already existed in the repo before this PR — this PR's branch
        just happens to still contain it, so the author touching it now
        isn't who introduced it. The "first reported by" column always
        points at whoever's run actually introduced it, wherever that was.
      </p>
      {issues && issues.issues.length > 0 && (
        <p className="subtitle" style={{ marginTop: 0 }}>
          {newCount} new · {preExistingCount} pre-existing
        </p>
      )}
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
                  {issues ? "No open issues on the latest run of this PR." : "Loading…"}
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
                      <span className="badge badge-new">new, this PR</span>
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

      <h2>Run log for this PR</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>When</th>
              <th>User</th>
              <th>Findings</th>
              <th>Result</th>
            </tr>
          </thead>
          <tbody>
            {logs.length === 0 ? (
              <tr>
                <td colSpan={4} className="empty-row">
                  No runs recorded yet for this PR.
                </td>
              </tr>
            ) : (
              logs.map((run) => (
                <tr key={run._id}>
                  <td>{formatTime(run.received_at)}</td>
                  <td>{run.user.name}</td>
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
