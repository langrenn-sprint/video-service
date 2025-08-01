FROM python:3.13-slim

RUN apt-get update && apt-get install -y \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*
# Install uv.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy the application into the container.
ADD . /app

# Install the application dependencies.
WORKDIR /app
RUN uv sync --frozen

# Expose the application port.
EXPOSE 8080

# Docker label
LABEL org.opencontainers.image.source=https://github.com/langrenn-sprint/video-service
LABEL org.opencontainers.image.description="video-service"
LABEL org.opencontainers.image.licenses=Apache-2.0

# Run the application.
CMD ["/app/.venv/bin/python", "-m", "video_service.app"] 
