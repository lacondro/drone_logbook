# ---- Stage 1: build the React frontend ----
FROM node:20-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: backend + built frontend, single-port server ----
FROM python:3.12-slim AS app
# Build tools for pymavlink's optional C extension; removed after install.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y build-essential && apt-get autoremove -y

COPY backend/ ./
# Built static frontend goes where main.py looks for it (../frontend/dist).
COPY --from=frontend /app/frontend/dist /app/frontend/dist

# Shared log folder is mounted here; the DB lives alongside the logs.
ENV LOGBOOK_DEFAULT_FOLDER=/logs
EXPOSE 8137

# Bind to 0.0.0.0 so other machines on the LAN can reach it.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8137"]
