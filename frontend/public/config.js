// Runtime config. In Docker, the container entrypoint overwrites this file
// from the API_BASE environment variable, so one built image can point at
// any backend URL without a rebuild. For `npm run dev` the fallback in
// src/api.js takes over.
window.__LG_API_BASE__ = "";
