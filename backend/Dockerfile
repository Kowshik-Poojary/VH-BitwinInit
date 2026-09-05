FROM python:3.12-slim

# git is required at runtime because scan_service.py shells out to `git clone`
# to fetch the target repository into a temp directory before analysis.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install the leakguard analyzer package from the repo root. The backend
# imports `from leakguard.analyzer import analyze_project`, so this must
# happen before the backend requirements.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Backend web layer.
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/app ./backend/app
COPY backend/scripts ./backend/scripts

WORKDIR /app/backend

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
