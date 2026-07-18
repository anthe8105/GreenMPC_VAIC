# syntax=docker/dockerfile:1

# ---- Stage 1: build the React/Vite SPA ----
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build
# Fail the build immediately if the SPA bundle was not produced.
RUN test -f dist/index.html && ls -la dist

# ---- Stage 2: Python runtime (FastAPI + core library) ----
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# cvxpy / highspy / scikit-learn all ship manylinux wheels, so no compiler
# toolchain is needed. libgomp1 provides the OpenMP runtime the native solver /
# sklearn code links against (the slim base omits it).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# setuptools/wheel are required for the editable install below.
RUN pip install --upgrade pip setuptools wheel

# Dependency layer (cached unless requirements change)
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Application source. frontend/dist is excluded via .dockerignore and replaced
# with the freshly built bundle from stage 1.
COPY . .
COPY --from=frontend /app/frontend/dist ./frontend/dist
# Fail loudly (and print the tree) if the built SPA did not land in the image.
RUN test -f frontend/dist/index.html && ls -la frontend/dist

# Editable install keeps greenmpc.__file__ under /app/src so that
# PROJECT_ROOT (= parents[3]) resolves to /app, where models/ and data/ live.
RUN pip install -e . --no-build-isolation

# Bind to all interfaces and honor the platform-injected $PORT (Render sets it).
EXPOSE 8000
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
