import { useEffect, useRef, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

const SEVERITY_CLASS = {
  ERROR: "sev-error",
  WARNING: "sev-warning",
  INFO: "sev-info",
};

function stepLabel(evt) {
  const d = evt;
  switch (evt.step) {
    case "validated":
      return `Validating repository URL: ${d.repo_url}`;
    case "cloning":
      return `Cloning ${d.repo_url} (--depth 1)…`;
    case "cloned":
      return "Clone complete";
    case "discovering_files":
      return "Discovering Python files…";
    case "discovered_files":
      return `Found ${d.count} Python file(s)`;
    case "analyzing_file":
      return `Analyzing ${d.file}  (${d.index}/${d.total})`;
    case "building_cfg":
      return `Building control-flow graphs for ${d.files} file(s)`;
    case "lifecycle_analysis":
      return "Running resource lifecycle analysis…";
    case "analysis_complete":
      return `Analysis complete — ${d.findings} finding(s)`;
    case "summarizing":
      return "Summarizing results";
    case "saving":
      return "Saving report";
    case "done":
      return "Done";
    case "error":
      return `Error: ${d.message}`;
    default:
      return evt.step;
  }
}

function groupByFile(findings) {
  const groups = new Map();
  for (const finding of findings) {
    const file = finding.location?.file || "unknown";
    if (!groups.has(file)) groups.set(file, []);
    groups.get(file).push(finding);
  }
  return groups;
}

export default function ScanPage() {
  const [repoUrl, setRepoUrl] = useState("");
  const [scanning, setScanning] = useState(false);
  const [log, setLog] = useState([]);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [expanded, setExpanded] = useState(new Set());
  const [logCollapsed, setLogCollapsed] = useState(false);
  const logEndRef = useRef(null);
  const esRef = useRef(null);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ block: "end" });
  }, [log]);

  useEffect(() => () => esRef.current?.close(), []);

  function toggleExpanded(key) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function handleSubmit(e) {
    e.preventDefault();
    const url = repoUrl.trim();
    if (!url || scanning) return;

    esRef.current?.close();
    setScanning(true);
    setError(null);
    setResult(null);
    setLog([]);
    setLogCollapsed(false);

    const es = new EventSource(
      `${API_BASE}/api/scan/stream?repo_url=${encodeURIComponent(url)}`
    );
    esRef.current = es;

    es.onmessage = (msg) => {
      const evt = JSON.parse(msg.data);
      setLog((prev) => [...prev, evt]);

      if (evt.step === "error") {
        setError(evt.message);
        setScanning(false);
        es.close();
      } else if (evt.step === "result") {
        setResult(evt.result);
        setScanning(false);
        setLogCollapsed(true);
        es.close();
      }
    };

    es.onerror = () => {
      setScanning(false);
      es.close();
      setError((prev) => prev || "Connection to the scan stream was lost.");
    };
  }

  return (
    <div className="page">
      <div className="hero">
        <h1>Scan a repository</h1>
        <p className="subtitle">
          Paste a public GitHub repo URL to check it for unclosed resource
          leaks — files, sockets, DB connections, temp files — using LeakGuard's
          CFG-based lifecycle analyzer.
        </p>

        <form className="scan-form" onSubmit={handleSubmit}>
          <input
            type="text"
            placeholder="https://github.com/owner/repo"
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
            disabled={scanning}
          />
          <button type="submit" disabled={scanning || !repoUrl.trim()}>
            {scanning ? "Scanning…" : "Scan"}
          </button>
        </form>
      </div>

      {log.length > 0 && (
        <div className={`terminal ${logCollapsed ? "terminal-collapsed" : ""}`}>
          <div
            className="terminal-titlebar"
            onClick={() => setLogCollapsed((c) => !c)}
          >
            <span className="terminal-dot dot-red" />
            <span className="terminal-dot dot-yellow" />
            <span className="terminal-dot dot-green" />
            <span className="terminal-title">
              leakguard scan {repoUrl || ""}
            </span>
            <span className="terminal-toggle">
              {logCollapsed ? "show log ▾" : "hide log ▴"}
            </span>
          </div>
          {!logCollapsed && (
            <div className="terminal-body">
              {log.map((evt, i) => (
                <div
                  key={i}
                  className={`terminal-line ${evt.step === "error" ? "line-error" : ""}`}
                >
                  <span className="terminal-caret">
                    {evt.step === "error"
                      ? "✕"
                      : i === log.length - 1 && scanning
                      ? "▸"
                      : "✓"}
                  </span>
                  {stepLabel(evt)}
                </div>
              ))}
              <div ref={logEndRef} />
            </div>
          )}
        </div>
      )}

      {error && <div className="error-banner">{error}</div>}

      {result && (
        <div className="results">
          <div className="summary-strip">
            <div className="stat">
              <span className="stat-value">{result.summary.total}</span>
              <span className="stat-label">total</span>
            </div>
            <div className="stat sev-error">
              <span className="stat-value">{result.summary.errors}</span>
              <span className="stat-label">errors</span>
            </div>
            <div className="stat sev-warning">
              <span className="stat-value">{result.summary.warnings}</span>
              <span className="stat-label">warnings</span>
            </div>
            <div className="stat sev-info">
              <span className="stat-value">{result.summary.info}</span>
              <span className="stat-label">info</span>
            </div>
          </div>

          {result.by_rule && result.by_rule.length > 0 && (
            <div className="rule-breakdown">
              {result.by_rule.map((r) => (
                <span className="rule-pill" key={r.rule_id}>
                  {r.rule_id} × <strong>{r.count}</strong>
                </span>
              ))}
            </div>
          )}

          {result.findings.length === 0 ? (
            <p className="all-clear">✓ No resource leaks detected.</p>
          ) : (
            [...groupByFile(result.findings)].map(([file, findings]) => (
              <div className="file-group card" key={file}>
                <h3>{file}</h3>
                <ul className="finding-list">
                  {findings.map((f, i) => {
                    const key = `${file}:${i}`;
                    const isOpen = expanded.has(key);
                    const trace = f.details?.path_trace || [];
                    return (
                      <li
                        key={key}
                        className={`finding ${SEVERITY_CLASS[f.severity] || ""}`}
                      >
                        <button
                          type="button"
                          className="finding-header"
                          onClick={() => trace.length && toggleExpanded(key)}
                        >
                          <span className="finding-loc">
                            line {f.location.line}
                          </span>
                          <span className="finding-rule">{f.rule_id}</span>
                          <span className="finding-msg">{f.message}</span>
                          {f.details?.confidence && (
                            <span className="confidence-tag">
                              {f.details.confidence}
                            </span>
                          )}
                          {trace.length > 0 && (
                            <span className="confidence-tag">
                              {isOpen ? "hide trace ▲" : "show trace ▼"}
                            </span>
                          )}
                        </button>
                        {isOpen && trace.length > 0 && (
                          <div className="finding-trace">
                            {trace.map((step, si) => (
                              <div key={si}>
                                line {step.line}: {step.event}
                              </div>
                            ))}
                          </div>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
