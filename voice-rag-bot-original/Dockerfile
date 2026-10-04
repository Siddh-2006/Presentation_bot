# Use NVIDIA CUDA base image for GPU acceleration
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
ENV HUGGINGFACE_HUB_CACHE=/data/huggingface
ENV OLLAMA_MODELS=/data/ollama

# Create data directory for HuggingFace caching
RUN mkdir -p /data && chmod 777 /data

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3-pip \
    python3.11-venv \
    ffmpeg \
    curl \
    git \
    zstd \
    espeak-ng \
    && rm -rf /var/lib/apt/lists/*

# Set python3 as default
RUN ln -s /usr/bin/python3.11 /usr/bin/python

# Install Ollama binary
RUN curl -fsSL https://ollama.com/install.sh | sh

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY voice-rag-api/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt
# Ensure torch uses CUDA
RUN pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# Copy application code
COPY voice-rag-api/ .

# Expose Hugging Face Space port
EXPOSE 7860
EXPOSE 11434

# Copy boot script
COPY start.sh /app/start.sh
RUN sed -i 's/\r$//' /app/start.sh && chmod +x /app/start.sh

# Start the services
CMD ["/app/start.sh"]
