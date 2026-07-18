FROM python:3.11-slim

WORKDIR /app

# Install system deps for whisper + TTS
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libsndfile1 ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt flask-httpauth

# Copy app files
COPY . .

# HF Spaces expects port 7860
ENV PORT=7860
ENV HF_HUB_DISABLE_TELEMETRY=1

# Use gunicorn for production
CMD ["gunicorn", "web_ui:app", "--bind", "0.0.0.0:7860", "--workers", "2", "--threads", "4", "--worker-class", "gthread", "--timeout", "120", "--keep-alive", "60"]
