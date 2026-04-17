FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libsndfile1 ffmpeg && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download whisper base model at build time (files only, avoid engine init crash in QEMU)
RUN python -c "from faster_whisper.utils import download_model; \
    download_model('base', output_dir='/app/models/whisper-base')"

ENV WHISPER_MODEL=/app/models/whisper-base

COPY src/ src/

CMD ["python", "-m", "src.main"]
