import { BrowserRouter, Routes, Route, NavLink, useNavigate } from "react-router-dom";
import ScanPage from "./pages/ScanPage";
import AdminDashboard from "./pages/AdminDashboard";
import RepoDetail from "./pages/RepoDetail";
import PRDetail from "./pages/PRDetail";
import Login from "./pages/Login";
import ProtectedRoute from "./components/ProtectedRoute";
import { AuthProvider, useAuth } from "./context/AuthContext";
import "./App.css";

function Nav() {
  const { auth, logout } = useAuth();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <nav className="topnav">
      <span className="brand">🛡️ LeakGuard</span>
      {auth && (
        <>
          <NavLink to="/" end className={({ isActive }) => (isActive ? "active" : "")}>
            Scan
          </NavLink>
          {auth.role === "admin" && (
            <NavLink to="/admin" className={({ isActive }) => (isActive ? "active" : "")}>
              Admin
            </NavLink>
          )}
          <span className="nav-user">{auth.username}</span>
          <button type="button" className="nav-logout" onClick={handleLogout}>
            Log out
          </button>
        </>
      )}
    </nav>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <div className="app-shell">
          <Nav />
          <main>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route
                path="/"
                element={
                  <ProtectedRoute>
                    <ScanPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/admin"
                element={
                  <ProtectedRoute requireAdmin>
                    <AdminDashboard />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/admin/repos/:repo"
                element={
                  <ProtectedRoute requireAdmin>
                    <RepoDetail />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/admin/repos/:repo/prs/:prNumber"
                element={
                  <ProtectedRoute requireAdmin>
                    <PRDetail />
                  </ProtectedRoute>
                }
              />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </AuthProvider>
  );
}
