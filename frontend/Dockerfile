# --- Build stage ---------------------------------------------------------
FROM node:20-alpine AS build

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# --- Serve stage ---------------------------------------------------------
FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html

# SPA fallback so React Router deep links work.
RUN printf 'server {\n\
    listen 80;\n\
    root /usr/share/nginx/html;\n\
    index index.html;\n\
    location / {\n\
        try_files $uri $uri/ /index.html;\n\
    }\n\
}\n' > /etc/nginx/conf.d/default.conf

# Runtime API base injection: overwrite the shipped config.js with a value
# from the API_BASE env var so one image can point at any backend.
COPY frontend/docker-entrypoint.sh /docker-entrypoint.d/40-write-config.sh
RUN chmod +x /docker-entrypoint.d/40-write-config.sh

EXPOSE 80
