# Build frontend
FROM node:20-slim AS fe
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY frontend/ .
RUN npm run build

# Runtime
FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY --from=fe /app/frontend/dist frontend/dist
WORKDIR /app/backend
EXPOSE 8000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
