import os

NATS_URL = os.getenv("NATS_URL", "nats://nats:4222")

# ZeroMQ - VAD audio stream
ZMQ_VAD_URL = os.getenv("ZMQ_VAD_URL", "tcp://audio-capture-vad:5555")
ZMQ_TOPIC = os.getenv("ZMQ_TOPIC", "audio.raw")

# Groq Cloud ASR (primary)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_ASR_MODEL = os.getenv("GROQ_ASR_MODEL", "whisper-large-v3-turbo")
GROQ_ASR_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_ASR_TIMEOUT = float(os.getenv("GROQ_ASR_TIMEOUT", "5.0"))

# Local Whisper (fallback — always loaded in memory)
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "pt")
WHISPER_BEAM_SIZE = int(os.getenv("WHISPER_BEAM_SIZE", "5"))

# Audio
SAMPLE_RATE = 16000
CHUNK_DURATION_S = float(os.getenv("CHUNK_DURATION_S", "2.0"))
CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_DURATION_S)
SILENCE_TIMEOUT_S = float(os.getenv("SILENCE_TIMEOUT_S", "1.5"))
BUFFER_MAX_S = float(os.getenv("BUFFER_MAX_S", "30.0"))
BUFFER_MAX_SAMPLES = int(SAMPLE_RATE * BUFFER_MAX_S)

# Heartbeat
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "10"))
