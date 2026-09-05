import { useState } from "react";
import { BrowserRouter, Routes, Route, NavLink, Navigate, useNavigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./AuthContext";
import LoginPage from "./pages/LoginPage";
import UserDashboard from "./pages/UserDashboard";
import AdminDashboard from "./pages/AdminDashboard";
import RepoDetail from "./pages/RepoDetail";
import PRDetail from "./pages/PRDetail";
import ScanPage from "./pages/ScanPage";
import "./App.css";

function TopNav() {
  const { user, logout, login } = useAuth();
  const [switcherOpen, setSwitcherOpen] = useState(false);
  const navigate = useNavigate();

  const demoAccounts = [
    { username: "Kowshik-Poojary", name: "Kowshik Poojary (Admin)", role: "admin", avatar: "https://github.com/Kowshik-Poojary.png" },
    { username: "vinayakpotdar79", name: "Vinayak Potdar (Developer)", role: "developer", avatar: "https://github.com/vinayakpotdar79.png" },
    { username: "Nikhil-2x", name: "Nikhil Yadav (Developer)", role: "developer", avatar: "https://github.com/Nikhil-2x.png" },
    { username: "Rohit-Khaire", name: "Rohit Khaire (Developer)", role: "developer", avatar: "https://github.com/Rohit-Khaire.png" },
  ];

  async function handleSwitch(account) {
    setSwitcherOpen(false);
    try {
      const u = await login(account.username, "password123");
      if (u.role === "admin") {
        navigate("/admin");
      } else {
        navigate("/my-branch");
      }
    } catch (e) {
      console.error(e);
    }
  }

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <nav className="topnav">
      <div className="brand-group">
        <span className="brand">🛡️ LeakGuard</span>
        <span className="brand-tag">Kowshik-Poojary/VH-BitwinInit</span>
      </div>

      <div className="nav-links">
        {user && (
          <>
            <NavLink to="/my-branch" className={({ isActive }) => (isActive ? "active" : "")}>
              🌿 Branch CI/CD
            </NavLink>
            <NavLink to="/scan" className={({ isActive }) => (isActive ? "active" : "")}>
              🔍 Scan Repo
            </NavLink>
            {user.role === "admin" && (
              <NavLink to="/admin" className={({ isActive }) => (isActive ? "active" : "")}>
                🎯 Admin Radar
              </NavLink>
            )}
          </>
        )}
      </div>

      <div className="nav-user-controls">
        {user ? (
          <div className="user-profile-menu">
            <button
              type="button"
              className="user-pill-btn"
              onClick={() => setSwitcherOpen(!switcherOpen)}
              title="Click to switch between GitHub team members"
            >
              <img
                src={user.avatar}
                alt={user.username}
                className="nav-avatar-img"
                onError={(e) => {
                  e.target.style.display = "none";
                }}
              />
              <span className="nav-username">{user.name?.split(" ")[0]}</span>
              <span className={`role-badge ${user.role === "admin" ? "role-admin" : "role-dev"}`}>
                {user.role === "admin" ? "Admin" : "Dev"}
              </span>
              <span className="caret">▾</span>
            </button>

            {switcherOpen && (
              <div className="quick-switch-dropdown">
                <div className="dropdown-title">Switch GitHub Team Member</div>
                {demoAccounts.map((acc) => (
                  <button
                    key={acc.username}
                    type="button"
                    className={`dropdown-item ${user.username === acc.username ? "active" : ""}`}
                    onClick={() => handleSwitch(acc)}
                  >
                    <img src={acc.avatar} alt={acc.username} className="dropdown-avatar-img" />
                    <div className="item-text">
                      <div className="item-name">{acc.name}</div>
                      <div className="item-role">@{acc.username}</div>
                    </div>
                  </button>
                ))}
                <div className="dropdown-divider" />
                <button type="button" className="dropdown-logout" onClick={handleLogout}>
                  Sign Out
                </button>
              </div>
            )}
          </div>
        ) : (
          <NavLink to="/login" className="btn-signin">
            Sign In
          </NavLink>
        )}
      </div>
    </nav>
  );
}

function ProtectedRoute({ children, requireAdmin = false }) {
  const { user, loading } = useAuth();

  if (loading) {
    return <div className="page"><div className="spinner"></div></div>;
  }
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  if (requireAdmin && user.role !== "admin") {
    return <Navigate to="/my-branch" replace />;
  }
  return children;
}

function HomeRedirect() {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!user) return <Navigate to="/login" replace />;
  return user.role === "admin" ? <Navigate to="/admin" replace /> : <Navigate to="/my-branch" replace />;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <div className="app-shell">
          <TopNav />
          <main>
            <Routes>
              <Route path="/" element={<HomeRedirect />} />
              <Route path="/login" element={<LoginPage />} />
              <Route
                path="/my-branch"
                element={
                  <ProtectedRoute>
                    <UserDashboard />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/admin"
                element={
                  <ProtectedRoute requireAdmin={true}>
                    <AdminDashboard />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/admin/repos/:repo"
                element={
                  <ProtectedRoute requireAdmin={true}>
                    <RepoDetail />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/admin/repos/:repo/prs/:prNumber"
                element={
                  <ProtectedRoute requireAdmin={true}>
                    <PRDetail />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/scan"
                element={
                  <ProtectedRoute>
                    <ScanPage />
                  </ProtectedRoute>
                }
              />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </AuthProvider>
  );
}
