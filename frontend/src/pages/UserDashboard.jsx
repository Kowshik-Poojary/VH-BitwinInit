import { useEffect, useRef, useState } from "react";
import { useAuth } from "../AuthContext";
import { API_BASE, getUserBranches, triggerBranchAction } from "../api";

export default function UserDashboard() {
  const { user } = useAuth();
  const [branches, setBranches] = useState([]);
  const [selectedBranch, setSelectedBranch] = useState(null);
  const [streaming, setStreaming] = useState(false);
  const [logs, setLogs] = useState([]);
  const [gateStatus, setGateStatus] = useState("WARNED");
  const [findings, setFindings] = useState([]);
  const [actionError, setActionError] = useState(null);
  const [expandedFinding, setExpandedFinding] = useState(null);
  const logEndRef = useRef(null);
  const esRef = useRef(null);

  useEffect(() => {
    loadBranches();
    return () => esRef.current?.close();
  }, [user]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  async function loadBranches() {
    try {
      const list = await getUserBranches();
      setBranches(list);
      if (list.length > 0) {
        selectBranch(list[0]);
      }
    } catch (err) {
      console.error(err);
    }
  }

  function selectBranch(b) {
    setSelectedBranch(b);
    setGateStatus(b.gate_status || b.status || "WARNED");
    setFindings(b.findings || []);
    setLogs(b.logs || []);
    setExpandedFinding(b.findings?.[0]?.rule_id || null);
  }

  function handleStartStream() {
    if (!selectedBranch || streaming) return;

    esRef.current?.close();
    setStreaming(true);
    setActionError(null);
    setLogs([`[RUN] Initializing real-time AST analysis for branch '${selectedBranch.branch}'...`]);

    const es = new EventSource(
      `${API_BASE}/api/user/branches/${encodeURIComponent(selectedBranch._id)}/stream`
    );
    esRef.current = es;

    es.onmessage = (msg) => {
      try {
        const evt = JSON.parse(msg.data);
        if (evt.message) {
          setLogs((prev) => [...prev, `[${new Date().toLocaleTimeString()}] ${evt.message}`]);
        }
        if (evt.gate_status) {
          setGateStatus(evt.gate_status);
        }
        if (evt.findings) {
          setFindings(evt.findings);
        }
        if (evt.step === "completed" || evt.step === "error") {
          setStreaming(false);
          es.close();
        }
      } catch (err) {
        console.error(err);
      }
    };

    es.onerror = () => {
      setStreaming(false);
      es.close();
    };
  }

  async function handleAction(action) {
    if (!selectedBranch) return;
    setActionError(null);
    try {
      const updated = await triggerBranchAction(selectedBranch._id, action);
      setSelectedBranch(updated);
      setGateStatus(updated.gate_status);
      setFindings(updated.findings || []);
      setLogs(updated.logs || []);
    } catch (err) {
      setActionError(err.message || "Action failed");
    }
  }

  return (
    <div className="page user-dashboard">
      <div className="hero">
        <div className="user-welcome-row">
          <div>
            <h1>Developer CI/CD Workspace</h1>
            <p className="subtitle">
              Real-time deterministic AST leak verification on your active branch & PR.
            </p>
          </div>
          <div className="user-badge-card">
            <img
              src={user?.avatar}
              alt={user?.username}
              className="user-avatar-lg-img"
              onError={(e) => {
                e.target.style.display = "none";
              }}
            />
            <div>
              <div className="user-card-name">{user?.name}</div>
              <div className="user-card-role">@{user?.username} • {user?.badge}</div>
            </div>
          </div>
        </div>
      </div>

      {actionError && <div className="error-banner">{actionError}</div>}

      {/* Branch Tabs */}
      <div className="branch-selector-bar">
        <div className="branch-tabs-label">Working Branches:</div>
        <div className="branch-tabs">
          {branches.map((b) => (
            <button
              key={b._id}
              className={`branch-tab-btn ${selectedBranch?._id === b._id ? "active" : ""}`}
              onClick={() => selectBranch(b)}
            >
              <span className="branch-icon">🌿</span>
              <span className="branch-name">{b.branch}</span>
              <span
                className={`tab-status-dot dot-${b.gate_status?.toLowerCase() || "warned"}`}
              />
            </button>
          ))}
        </div>
      </div>

      {selectedBranch && (
        <div className="branch-detail-grid">
          {/* Main Column */}
          <div className="branch-main-col">
            {/* Gatekeeper Card */}
            <div className={`gatekeeper-card gate-${gateStatus.toLowerCase()}`}>
              <div className="gate-header">
                <div className="gate-title-group">
                  <span className="gate-icon">
                    {gateStatus === "PASSED" ? "🟢" : gateStatus === "WARNED" ? "🟡" : "🔴"}
                  </span>
                  <div>
                    <div className="gate-status-text">
                      CI GATEKEEPER: {gateStatus}
                    </div>
                    <div className="gate-repo-meta">
                      {selectedBranch.repo} • PR #{selectedBranch.pr_number}: {selectedBranch.pr_title}
                    </div>
                  </div>
                </div>
                <div className="gate-actions">
                  <button
                    className="btn-primary"
                    onClick={handleStartStream}
                    disabled={streaming}
                  >
                    {streaming ? "⏳ Analyzing AST..." : "⚡ Run Real-Time Scan"}
                  </button>
                  <button
                    className="btn-secondary"
                    onClick={() => handleAction("attempt_merge")}
                  >
                    🔀 Verify & Merge PR
                  </button>
                  {gateStatus !== "PASSED" && (
                    <button
                      className="btn-patch"
                      onClick={() => handleAction("resolve_fix")}
                    >
                      🔧 Auto-Fix with Context Manager
                    </button>
                  )}
                </div>
              </div>

              {gateStatus === "BLOCKED" && (
                <div className="gate-block-warning">
                  <strong>🛑 MERGE FORBIDDEN BY GATEKEEPER:</strong> Critical unclosed resource leaks detected in this PR.
                  To prevent file descriptor exhaustion in production, AST checks must pass before merge.
                </div>
              )}
              {gateStatus === "WARNED" && (
                <div className="gate-warn-banner">
                  <strong>⚠️ RESOURCE LEAKS DETECTED:</strong> AST analysis found {findings.length} unclosed resource lifecycle path(s).
                  Review the path traces below and remediate before merging.
                </div>
              )}
              {gateStatus === "PASSED" && (
                <div className="gate-pass-banner">
                  <strong>✅ ZERO LEAKS FOUND:</strong> All resource allocations (`open`, `socket`, `sqlite3`, `tempfile`) have deterministic cleanup handlers on every execution path.
                </div>
              )}
            </div>

            {/* Real-time Streaming Terminal */}
            <div className="terminal-card">
              <div className="terminal-header">
                <div className="terminal-buttons">
                  <span className="t-dot t-red"></span>
                  <span className="t-dot t-yellow"></span>
                  <span className="t-dot t-green"></span>
                </div>
                <div className="terminal-title">
                  🖥️ CI/CD Real-Time AST Runner Logs ({selectedBranch.branch} @ {selectedBranch.sha})
                </div>
                {streaming && <div className="terminal-pulse">LIVE STREAM</div>}
              </div>
              <div className="terminal-body">
                {logs.length === 0 ? (
                  <div className="terminal-empty">Press 'Run Real-Time Scan' to stream AST lifecycle logs...</div>
                ) : (
                  logs.map((line, idx) => (
                    <div
                      key={idx}
                      className={`terminal-line ${
                        line.includes("BLOCKED") || line.includes("Critical") || line.includes("ERROR")
                          ? "term-err"
                          : line.includes("WARN") || line.includes("leak")
                          ? "term-warn"
                          : line.includes("PASSED") || line.includes("APPROVED") || line.includes("Safe")
                          ? "term-good"
                          : ""
                      }`}
                    >
                      {line}
                    </div>
                  ))
                )}
                <div ref={logEndRef} />
              </div>
            </div>

            {/* Path Trace Findings */}
            <div className="findings-section">
              <h3>
                🔍 Actionable Path-Sensitive Findings ({findings.length})
              </h3>
              {findings.length === 0 ? (
                <div className="clean-state-box">
                  <div className="clean-icon">✨</div>
                  <div className="clean-text">All resources safely closed across every branch and return!</div>
                </div>
              ) : (
                <div className="findings-list">
                  {findings.map((f, i) => (
                    <div key={i} className="finding-card">
                      <div
                        className="finding-summary-bar"
                        onClick={() =>
                          setExpandedFinding(expandedFinding === f.rule_id ? null : f.rule_id)
                        }
                      >
                        <div className="finding-header-left">
                          <span className="badge badge-critical">{f.rule_id}</span>
                          <span className="badge badge-accent">{f.resource_type}</span>
                          <span className="finding-file-line">
                            {f.location?.file}:{f.location?.line}
                          </span>
                        </div>
                        <span className="toggle-arrow">
                          {expandedFinding === f.rule_id ? "▲" : "▼"}
                        </span>
                      </div>
                      <div className="finding-message">{f.message}</div>

                      {/* Path Trace Timeline */}
                      {expandedFinding === f.rule_id && f.details?.path_trace && (
                        <div className="path-trace-container">
                          <div className="path-trace-title">
                            📍 CFG Execution Path Leading to Resource Leak:
                          </div>
                          <div className="timeline-steps">
                            {f.details.path_trace.map((step, sIdx) => (
                              <div key={sIdx} className="timeline-step">
                                <div className="step-marker">{sIdx + 1}</div>
                                <div className="step-content">
                                  <span className="step-location">
                                    {step.file}:{step.line}
                                  </span>
                                  <span className="step-event">{step.event}</span>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Sidebar */}
          <div className="branch-side-col">
            <div className="side-card">
              <h4>📋 GitHub PR Context</h4>
              <div className="meta-row">
                <span className="meta-label">Repository:</span>
                <a
                  href={`https://github.com/${selectedBranch.repo}`}
                  target="_blank"
                  rel="noreferrer"
                  className="meta-val github-link"
                >
                  🐙 {selectedBranch.repo} ↗
                </a>
              </div>
              <div className="meta-row">
                <span className="meta-label">Branch:</span>
                <a
                  href={`https://github.com/${selectedBranch.repo}/tree/${selectedBranch.branch}`}
                  target="_blank"
                  rel="noreferrer"
                  className="meta-val code-font github-link"
                >
                  🌿 {selectedBranch.branch} ↗
                </a>
              </div>
              <div className="meta-row">
                <span className="meta-label">Target PR:</span>
                <a
                  href={`https://github.com/${selectedBranch.repo}/pull/${selectedBranch.pr_number}`}
                  target="_blank"
                  rel="noreferrer"
                  className="meta-val github-link"
                >
                  #{selectedBranch.pr_number} ↗
                </a>
              </div>
              <div className="meta-row">
                <span className="meta-label">Author:</span>
                <span className="meta-val author-val">
                  <img
                    src={selectedBranch.avatar}
                    alt=""
                    className="author-avatar-sm"
                    onError={(e) => {
                      e.target.style.display = "none";
                    }}
                  />
                  {selectedBranch.user_name}
                </span>
              </div>
              <div className="meta-row">
                <span className="meta-label">Commit SHA:</span>
                <a
                  href={`https://github.com/${selectedBranch.repo}/commit/${selectedBranch.sha}`}
                  target="_blank"
                  rel="noreferrer"
                  className="meta-val code-font github-link"
                >
                  {selectedBranch.sha} ↗
                </a>
              </div>
            </div>

            <div className="side-card">
              <h4>🎯 AST Differentiator</h4>
              <p className="side-desc">
                Unlike linters (Pylint/Sonar) that merely check syntax, LeakGuard walks every
                path in the Control Flow Graph. Even if <code>close()</code> exists on line 50,
                an early return on line 35 is caught deterministically with zero false alarms on
                <code>try/finally</code>.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
