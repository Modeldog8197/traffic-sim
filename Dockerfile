FROM node:22.18.0-bookworm-slim AS ui
WORKDIR /app/frontend
RUN npm install -g pnpm@10.15.0
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend ./
RUN pnpm run build
FROM python:3.12.11-slim-bookworm
WORKDIR /app
COPY requirements.lock.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt
COPY backend ./backend
COPY scripts ./scripts
COPY README.md ./
COPY docs ./docs
COPY frontend/pnpm-lock.yaml ./frontend/pnpm-lock.yaml
COPY examples ./examples
COPY --from=ui /app/frontend/dist ./frontend/dist
ENV CITYLAB_DATA=/app/data
EXPOSE 8000
CMD ["uvicorn", "backend.api:app", "--host", "0.0.0.0", "--port", "8000"]
