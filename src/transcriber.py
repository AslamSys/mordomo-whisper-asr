import logging
import numpy as np
from faster_whisper import WhisperModel
from src import config

logger = logging.getLogger(__name__)


class Transcriber:
    def __init__(self):
        self.model: WhisperModel | None = None

    def load_model(self):
        logger.info(
            "Loading faster-whisper model=%s device=%s compute=%s",
            config.WHISPER_MODEL,
            config.WHISPER_DEVICE,
            config.WHISPER_COMPUTE_TYPE,
        )
        self.model = WhisperModel(
            config.WHISPER_MODEL,
            device=config.WHISPER_DEVICE,
            compute_type=config.WHISPER_COMPUTE_TYPE,
        )
        logger.info("Whisper model loaded")

    def transcribe(self, pcm_bytes: bytes) -> dict:
        audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0

        if len(audio) < config.SAMPLE_RATE * 0.3:
            return {"text": "", "language": config.WHISPER_LANGUAGE, "segments": []}

        segments, info = self.model.transcribe(
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

        full_text = " ".join(full_text_parts)

        return {
            "text": full_text,
            "language": info.language,
            "language_probability": info.language_probability,
            "segments": segment_list,
        }
