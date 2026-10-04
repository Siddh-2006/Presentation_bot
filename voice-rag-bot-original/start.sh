#!/bin/bash

# Start Ollama service in the background
echo "Starting Ollama daemon..."
OLLAMA_HOST=0.0.0.0:11434 ollama serve &
OLLAMA_PID=$!

# Wait for Ollama to be ready
echo "Waiting for Ollama to start..."
until curl -s http://localhost:11434/api/tags > /dev/null; do
    sleep 2
done
echo "Ollama is running!"

# Pull required models if they don't exist
echo "Pulling models..."
ollama pull gemma2:2b
ollama pull qwen2.5:3b

# Start FastAPI app on Hugging Face port 7860
echo "Starting FastAPI on port 7860..."
uvicorn main:app --host 0.0.0.0 --port 7860
