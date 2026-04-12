FROM python:3.11-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy everything (filtered by .dockerignore)
COPY . .

# Install dependencies and project
RUN uv sync --no-dev --frozen

CMD ["uv", "run", "bliq", "scan-whales", "--loop", "5", "--top-n", "20"]
