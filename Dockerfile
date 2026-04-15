FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libsndfile1 ffmpeg && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download whisper base model at build time
RUN python -c "from faster_whisper import WhisperModel; \
    WhisperModel('base', device='cpu', compute_type='int8')"

COPY src/ src/

CMD ["python", "-m", "src.main"]
