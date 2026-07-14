# ─── Stage 1: Build the React frontend ─────────────────────────────
FROM node:20-alpine AS frontend-build

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build


# ─── Stage 2: Python backend + sas-mcp-server sidecar ──────────────
FROM python:3.12-slim

# tesseract → the Document Processing agent's real OCR (Arabic + English)
# poppler  → PDF text fallback for the knowledge index
# git      → pip install of the sas-mcp-server package branch
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-ara tesseract-ocr-eng poppler-utils git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/backend/requirements.txt && \
    # the sas-mcp-server sidecar (direct HTTP mode + refresh-token auth) —
    # provides score_data against SAS Viya's Micro Analytic Score service
    pip install --no-cache-dir \
        "git+https://github.com/raedaldweik/sas-mcp-server@claude/mcp-package"

COPY backend/ /app/backend/
COPY knowledge_base/ /app/knowledge_base/
COPY start.sh /app/start.sh
COPY --from=frontend-build /app/frontend/dist /app/frontend/dist
RUN chmod +x /app/start.sh

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

WORKDIR /app/backend
EXPOSE 8000
CMD ["/app/start.sh"]
