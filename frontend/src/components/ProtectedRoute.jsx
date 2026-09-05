import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function ProtectedRoute({ requireAdmin = false, children }) {
  const { auth } = useAuth();

  if (!auth) {
    return <Navigate to="/login" replace />;
  }
  if (requireAdmin && auth.role !== "admin") {
    return <Navigate to="/" replace />;
  }
  return children;
}
