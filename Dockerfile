FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libsndfile1 ffmpeg && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download whisper base model at build time (files only, avoid faster-whisper/ctranslate2 import crash in QEMU)
RUN pip install huggingface_hub && \
    python -c "from huggingface_hub import snapshot_download; \
    snapshot_download(repo_id='Systran/faster-whisper-base', local_dir='/app/models/whisper-base')"

ENV WHISPER_MODEL=/app/models/whisper-base

COPY src/ src/

CMD ["python", "-m", "src.main"]
