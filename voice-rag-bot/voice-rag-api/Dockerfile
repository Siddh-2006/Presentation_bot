FROM python:3.11-slim-bookworm

# Prevent interactive prompts during apt-get
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

# Install system audio libraries and build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    espeak-ng \
    libsndfile1 \
    pulseaudio \
    libasound2 \
    libasound2-plugins \
    curl \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1. Install lightweight CPU PyTorch wheel and Python requirements
COPY requirements.txt .
RUN python -m pip install --upgrade pip && \
    python -m pip install torch --index-url https://download.pytorch.org/whl/cpu && \
    python -m pip install -r requirements.txt

# 2. Install Playwright browser and system-level browser deps
RUN python -m pip install playwright && \
    playwright install-deps chromium && \
    playwright install chromium

# 3. Copy application codebase (venv is excluded by .dockerignore)
COPY . .

# Ensure runtime directories exist
RUN mkdir -p /app/static /app/data/chroma_db /app/bot_chrome_profile

EXPOSE 8000

# Start FastAPI ASGI server
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
