import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import ScanPage from "./pages/ScanPage";
import AdminDashboard from "./pages/AdminDashboard";
import RepoDetail from "./pages/RepoDetail";
import "./App.css";

export default function App() {
  return (
    <BrowserRouter>
      <div className="app-shell">
        <nav className="topnav">
          <span className="brand">🛡️ LeakGuard</span>
          <NavLink to="/" end className={({ isActive }) => (isActive ? "active" : "")}>
            Scan
          </NavLink>
          <NavLink to="/admin" className={({ isActive }) => (isActive ? "active" : "")}>
            Admin
          </NavLink>
        </nav>
        <main>
          <Routes>
            <Route path="/" element={<ScanPage />} />
            <Route path="/admin" element={<AdminDashboard />} />
            <Route path="/admin/repos/:repo" element={<RepoDetail />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
