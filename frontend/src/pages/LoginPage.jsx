import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../AuthContext";
import { getDemoAccounts } from "../api";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [demoAccounts, setDemoAccounts] = useState([]);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    getDemoAccounts()
      .then(setDemoAccounts)
      .catch(() => {
        // Fallback real GitHub team accounts
        setDemoAccounts([
          {
            username: "Kowshik-Poojary",
            name: "Kowshik Poojary (Repo Owner & Admin)",
            role: "admin",
            avatar: "https://github.com/Kowshik-Poojary.png",
            badge: "Admin",
          },
          {
            username: "vinayakpotdar79",
            name: "Vinayak Potdar (Developer)",
            role: "developer",
            avatar: "https://github.com/vinayakpotdar79.png",
            badge: "Developer",
          },
          {
            username: "Nikhil-2x",
            name: "Nikhil Yadav (Developer)",
            role: "developer",
            avatar: "https://github.com/Nikhil-2x.png",
            badge: "Developer",
          },
          {
            username: "Rohit-Khaire",
            name: "Rohit Khaire (Developer)",
            role: "developer",
            avatar: "https://github.com/Rohit-Khaire.png",
            badge: "Developer",
          },
        ]);
      });
  }, []);

  async function handleLogin(u, p) {
    setError(null);
    setSubmitting(true);
    try {
      const user = await login(u, p);
      if (user.role === "admin") {
        navigate("/admin");
      } else {
        navigate("/my-branch");
      }
    } catch (err) {
      setError(err.message || "Login failed");
    } finally {
      setSubmitting(false);
    }
  }

  function handleFormSubmit(e) {
    e.preventDefault();
    if (!username.trim() || !password.trim()) return;
    handleLogin(username.trim(), password.trim());
  }

  function handleQuickSelect(account) {
    const pwd = "password123";
    setUsername(account.username);
    setPassword(pwd);
    handleLogin(account.username, pwd);
  }

  return (
    <div className="login-container">
      <div className="login-card">
        <div className="login-header">
          <div className="login-brand-icon">🛡️</div>
          <h1>LeakGuard</h1>
          <p className="login-subtitle">
            GitHub Resource-Leak Gatekeeper & CI/CD Intelligence Platform
          </p>
          <div className="repo-pill-badge">
            <span className="github-icon">🐙</span> Kowshik-Poojary/VH-BitwinInit
          </div>
        </div>

        {error && <div className="error-banner">{error}</div>}

        <form onSubmit={handleFormSubmit} className="login-form">
          <div className="form-group">
            <label htmlFor="username">GitHub Username</label>
            <input
              id="username"
              type="text"
              placeholder="e.g. Kowshik-Poojary, vinayakpotdar79, Nikhil-2x, Rohit-Khaire"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          <button type="submit" className="btn-primary login-btn" disabled={submitting}>
            {submitting ? "Authenticating with GitHub Account..." : "Sign In to Workspace →"}
          </button>
        </form>

        <div className="demo-accounts-section">
          <div className="demo-divider">
            <span>⚡ Real GitHub Team Accounts</span>
          </div>
          <div className="demo-account-grid">
            {demoAccounts.map((acc) => (
              <button
                key={acc.username}
                type="button"
                className={`demo-account-card ${acc.role === "admin" ? "demo-admin" : "demo-user"}`}
                onClick={() => handleQuickSelect(acc)}
              >
                <img
                  src={acc.avatar}
                  alt={acc.username}
                  className="demo-avatar-img"
                  onError={(e) => {
                    e.target.style.display = "none";
                  }}
                />
                <div className="demo-info">
                  <div className="demo-name">{acc.name}</div>
                  <div className="demo-meta">
                    <span className={`badge ${acc.role === "admin" ? "badge-critical" : "badge-accent"}`}>
                      {acc.badge}
                    </span>
                    <span className="demo-uname">@{acc.username}</span>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
