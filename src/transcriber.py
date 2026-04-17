"""
Dual-backend ASR transcriber.

Primary:  Groq Cloud ASR (whisper-large-v3-turbo) — higher quality, low latency
Fallback: Local faster-whisper (base, INT8) — always warm in RAM, offline capable

Flow: try Groq → timeout/error → fallback to local → return result
"""
import io
import logging
import struct
import time

import httpx
import numpy as np
from faster_whisper import WhisperModel

from src import config

logger = logging.getLogger(__name__)


class Transcriber:
    def __init__(self):
        self.local_model: WhisperModel | None = None
        self._groq_available = bool(config.GROQ_API_KEY)
        self._groq_failures = 0  # consecutive failures — back off after 5

    def load_model(self):
        """Load local whisper model (always, as fallback)."""
        logger.info(
            "Loading local faster-whisper model=%s device=%s compute=%s",
            config.WHISPER_MODEL,
            config.WHISPER_DEVICE,
            config.WHISPER_COMPUTE_TYPE,
        )
        self.local_model = WhisperModel(
            config.WHISPER_MODEL,
            device=config.WHISPER_DEVICE,
            compute_type=config.WHISPER_COMPUTE_TYPE,
        )
        logger.info("Local Whisper model loaded (fallback ready)")
        if self._groq_available:
            logger.info("Groq ASR configured as primary (model=%s)", config.GROQ_ASR_MODEL)
        else:
            logger.warning("GROQ_API_KEY not set — using local Whisper only")

    def transcribe(self, pcm_bytes: bytes) -> dict:
        """Transcribe PCM audio. Tries Groq first, falls back to local."""
        audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0

        if len(audio) < config.SAMPLE_RATE * 0.3:
            return {"text": "", "language": config.WHISPER_LANGUAGE, "segments": [], "backend": "skipped"}

        # Try Groq if available and not in backoff
        if self._groq_available and self._groq_failures < 5:
            try:
                result = self._transcribe_groq(pcm_bytes)
                self._groq_failures = 0
                return result
            except Exception as exc:
                self._groq_failures += 1
                logger.warning(
                    "Groq ASR failed (%d/5): %s — falling back to local",
                    self._groq_failures, exc,
                )
        elif self._groq_failures >= 5:
            # Reset backoff every 30s to retry Groq
            self._groq_failures = 0
            logger.info("Groq backoff reset — will retry on next request")

        return self._transcribe_local(audio)

    def _transcribe_groq(self, pcm_bytes: bytes) -> dict:
        """Send audio to Groq Cloud ASR. Synchronous (called from executor)."""
        # Convert PCM int16 to WAV in memory for Groq API
        wav_buffer = self._pcm_to_wav(pcm_bytes)

        with httpx.Client(timeout=config.GROQ_ASR_TIMEOUT) as client:
            resp = client.post(
                config.GROQ_ASR_URL,
                headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"},
                files={"file": ("audio.wav", wav_buffer, "audio/wav")},
                data={
                    "model": config.GROQ_ASR_MODEL,
                    "language": config.WHISPER_LANGUAGE,
                    "response_format": "verbose_json",
                    "temperature": 0.0,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        text = data.get("text", "").strip()
        segments = []
        for seg in data.get("segments", []):
            segments.append({
                "start": seg.get("start", 0),
                "end": seg.get("end", 0),
                "text": seg.get("text", "").strip(),
            })

        return {
            "text": text,
            "language": data.get("language", config.WHISPER_LANGUAGE),
            "language_probability": 1.0,
            "segments": segments,
            "backend": "groq",
        }

    def _transcribe_local(self, audio: np.ndarray) -> dict:
        """Transcribe using local faster-whisper model."""
        segments, info = self.local_model.transcribe(
            audio,
            language=config.WHISPER_LANGUAGE,
            beam_size=config.WHISPER_BEAM_SIZE,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )

        segment_list = []
        full_text_parts = []
        for seg in segments:
            segment_list.append({
                "start": seg.start,
                "end": seg.end,
                "text": seg.text.strip(),
            })
            full_text_parts.append(seg.text.strip())

        return {
            "text": " ".join(full_text_parts),
            "language": info.language,
            "language_probability": info.language_probability,
            "segments": segment_list,
            "backend": "local",
        }

    @staticmethod
    def _pcm_to_wav(pcm_bytes: bytes) -> io.BytesIO:
        """Convert raw PCM int16 mono 16kHz to WAV in memory."""
        buf = io.BytesIO()
        num_samples = len(pcm_bytes) // 2
        data_size = num_samples * 2
        # WAV header (44 bytes)
        buf.write(b"RIFF")
        buf.write(struct.pack("<I", 36 + data_size))
        buf.write(b"WAVE")
        buf.write(b"fmt ")
        buf.write(struct.pack("<I", 16))          # chunk size
        buf.write(struct.pack("<H", 1))            # PCM format
        buf.write(struct.pack("<H", 1))            # mono
        buf.write(struct.pack("<I", 16000))        # sample rate
        buf.write(struct.pack("<I", 16000 * 2))    # byte rate
        buf.write(struct.pack("<H", 2))            # block align
        buf.write(struct.pack("<H", 16))           # bits per sample
        buf.write(b"data")
        buf.write(struct.pack("<I", data_size))
        buf.write(pcm_bytes)
        buf.seek(0)
        return buf
