import asyncio
import enum
import json
import logging
import struct
import time
import threading

import nats
import zmq
import numpy as np

from src import config
from src.transcriber import Transcriber

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class State(enum.Enum):
    IDLE = "idle"
    BUFFERING = "buffering"
    TRANSCRIBING = "transcribing"


class WhisperASRService:
    def __init__(self):
        self.state = State.IDLE
        self.nc = None
        self.transcriber = Transcriber()
        self.audio_buffer = bytearray()
        self.transcript_buffer: list[dict] = []
        self.conversation_id: str | None = None
        self.speaker_id: str | None = None
        self.last_audio_time: float = 0.0
        self._zmq_thread: threading.Thread | None = None
        self._running = False
        self._lock = threading.Lock()

    async def start(self):
        self.transcriber.load_model()

        self.nc = await nats.connect(config.NATS_URL)
        logger.info("Connected to NATS at %s", config.NATS_URL)

        await self.nc.subscribe("mordomo.wake_word.detected", cb=self._on_wake_word)
        await self.nc.subscribe("mordomo.speaker.verified", cb=self._on_speaker_verified)
        await self.nc.subscribe("mordomo.speaker.rejected", cb=self._on_speaker_rejected)
        await self.nc.subscribe("mordomo.conversation.ended", cb=self._on_conversation_ended)

        asyncio.create_task(self._heartbeat_loop())
        asyncio.create_task(self._silence_monitor())

        logger.info("Whisper ASR service started — state=IDLE")

    def _start_zmq_listener(self):
        if self._zmq_thread and self._zmq_thread.is_alive():
            return
        self._running = True
        self._zmq_thread = threading.Thread(target=self._zmq_loop, daemon=True)
        self._zmq_thread.start()

    def _stop_zmq_listener(self):
        self._running = False

    def _zmq_loop(self):
        ctx = zmq.Context()
        sock = ctx.socket(zmq.SUB)
        sock.connect(config.ZMQ_VAD_URL)
        sock.setsockopt_string(zmq.SUBSCRIBE, config.ZMQ_TOPIC)
        sock.setsockopt(zmq.RCVTIMEO, 500)
        logger.info("ZMQ SUB connected to %s", config.ZMQ_VAD_URL)

        while self._running:
            try:
                parts = sock.recv_multipart()
                if len(parts) < 2:
                    continue
                pcm_data = parts[1]
                with self._lock:
                    if self.state in (State.BUFFERING, State.TRANSCRIBING):
                        self.audio_buffer.extend(pcm_data)
                        self.last_audio_time = time.time()
                        if len(self.audio_buffer) > config.BUFFER_MAX_SAMPLES * 2:
                            self.audio_buffer = self.audio_buffer[-(config.BUFFER_MAX_SAMPLES * 2):]
            except zmq.Again:
                continue
            except Exception as e:
                logger.error("ZMQ receive error: %s", e)

        sock.close()
        ctx.term()
        logger.info("ZMQ listener stopped")

    async def _on_wake_word(self, msg):
        if self.state != State.IDLE:
            return
        try:
            data = json.loads(msg.data)
        except Exception:
            data = {}

        self.state = State.BUFFERING
        self.conversation_id = data.get("session_id") or data.get("conversation_id")
        self.speaker_id = None
        self.audio_buffer.clear()
        self.transcript_buffer.clear()
        self.last_audio_time = time.time()
        self._start_zmq_listener()
        logger.info("mordomo.wake_word.detected → BUFFERING (conv=%s)", self.conversation_id)

    async def _on_speaker_verified(self, msg):
        if self.state != State.BUFFERING:
            return
        try:
            data = json.loads(msg.data)
        except Exception:
            data = {}

        self.state = State.TRANSCRIBING
        self.speaker_id = data.get("speaker_id", "unknown")
        logger.info("mordomo.speaker.verified → TRANSCRIBING (speaker=%s)", self.speaker_id)

        await self._flush_buffer()

    async def _on_speaker_rejected(self, msg):
        if self.state != State.BUFFERING:
            return
        self.state = State.IDLE
        self.speaker_id = None
        self.audio_buffer.clear()
        self.transcript_buffer.clear()
        self._stop_zmq_listener()
        logger.info("mordomo.speaker.rejected → IDLE (buffer discarded)")

    async def _on_conversation_ended(self, msg):
        if self.state == State.IDLE:
            return

        if self.state == State.TRANSCRIBING:
            await self._flush_buffer(is_final=True)

        self.state = State.IDLE
        self.audio_buffer.clear()
        self.transcript_buffer.clear()
        self.conversation_id = None
        self._stop_zmq_listener()
        logger.info("conversation.ended → IDLE")

    async def _flush_buffer(self, is_final: bool = False):
        with self._lock:
            if len(self.audio_buffer) < config.SAMPLE_RATE * 2 * 0.3:
                return
            pcm_data = bytes(self.audio_buffer)
            self.audio_buffer.clear()

        result = await asyncio.get_event_loop().run_in_executor(
            None, self.transcriber.transcribe, pcm_data
        )

        text = result.get("text", "").strip()
        if not text:
            return

        payload = {
            "text": text,
            "speaker_id": self.speaker_id or "unknown",
            "language": result.get("language", config.WHISPER_LANGUAGE),
            "conversation_id": self.conversation_id,
            "is_final": is_final,
            "timestamp": time.time(),
            "segments": result.get("segments", []),
        }

        subject = "mordomo.speech.transcribed"
        await self.nc.publish(subject, json.dumps(payload).encode())
        logger.info(
            "Published %s: is_final=%s text='%s'",
            subject,
            is_final,
            text[:80],
        )

    async def _silence_monitor(self):
        while True:
            await asyncio.sleep(0.5)
            if self.state != State.TRANSCRIBING:
                continue

            with self._lock:
                elapsed = time.time() - self.last_audio_time if self.last_audio_time else 0
                has_audio = len(self.audio_buffer) >= config.SAMPLE_RATE * 2 * 0.3

            if elapsed > config.SILENCE_TIMEOUT_S and has_audio:
                await self._flush_buffer(is_final=True)
                logger.info("Silence detected (%.1fs) — flushed final transcript", elapsed)

            elif has_audio and len(self.audio_buffer) >= config.CHUNK_SAMPLES * 2:
                await self._flush_buffer(is_final=False)

    async def _heartbeat_loop(self):
        while True:
            await asyncio.sleep(config.HEARTBEAT_INTERVAL)
            payload = {
                "service": "whisper-asr",
                "state": self.state.value,
                "timestamp": time.time(),
                "model": config.WHISPER_MODEL,
            }
            await self.nc.publish(
                "whisper.asr.status", json.dumps(payload).encode()
            )


async def main():
    service = WhisperASRService()
    await service.start()

    stop = asyncio.Event()
    await stop.wait()


if __name__ == "__main__":
    asyncio.run(main())
