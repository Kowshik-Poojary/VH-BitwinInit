import { createContext, useContext, useState } from "react";
import { loginRequest } from "../api";

const AuthContext = createContext(null);

function loadStoredAuth() {
  const token = localStorage.getItem("lg_token");
  const username = localStorage.getItem("lg_username");
  const role = localStorage.getItem("lg_role");
  if (!token || !role) return null;
  return { token, username, role };
}

export function AuthProvider({ children }) {
  const [auth, setAuth] = useState(loadStoredAuth);

  async function login(username, password) {
    const data = await loginRequest(username, password);
    localStorage.setItem("lg_token", data.token);
    localStorage.setItem("lg_username", data.username);
    localStorage.setItem("lg_role", data.role);
    setAuth({ token: data.token, username: data.username, role: data.role });
    return data;
  }

  function logout() {
    localStorage.removeItem("lg_token");
    localStorage.removeItem("lg_username");
    localStorage.removeItem("lg_role");
    setAuth(null);
  }

  return (
    <AuthContext.Provider value={{ auth, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
