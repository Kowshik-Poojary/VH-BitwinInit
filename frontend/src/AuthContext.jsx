import { createContext, useContext, useEffect, useState } from "react";
import { getMe, login as apiLogin, setToken, getToken } from "./api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try {
      const saved = localStorage.getItem("leakguard_user");
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = getToken();
    if (token) {
      getMe()
        .then((u) => {
          setUser(u);
          localStorage.setItem("leakguard_user", JSON.stringify(u));
        })
        .catch(() => {
          setToken("");
          setUser(null);
          localStorage.removeItem("leakguard_user");
        })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  async function login(username, password) {
    const res = await apiLogin(username, password);
    setToken(res.token);
    setUser(res.user);
    localStorage.setItem("leakguard_user", JSON.stringify(res.user));
    return res.user;
  }

  function logout() {
    setToken("");
    setUser(null);
    localStorage.removeItem("leakguard_user");
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
