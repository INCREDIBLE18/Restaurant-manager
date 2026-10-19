# Multi-stage Dockerfile for Restaurant Operations Manager
# Stage 1: Build the React + TypeScript frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# Stage 2: Python backend + serve built frontend SPA
FROM python:3.11-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python requirements
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r ./backend/requirements.txt

# Copy backend code, scripts, configuration
COPY backend/ ./backend/
COPY scripts/ ./scripts/
COPY .env.example ./.env.example

# Copy compiled frontend from builder stage
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Ensure persistence data directory exists
RUN mkdir -p /app/data

EXPOSE 8000

# Run alembic migrations and start FastAPI server
CMD ["sh", "-c", "cd backend && python -m alembic upgrade head && python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
