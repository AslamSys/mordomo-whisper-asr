# 🗣️ Whisper ASR (STT)

## 🔗 Navegação

**[🏠 AslamSys](https://github.com/AslamSys)** → **[📚 _system](https://github.com/AslamSys/_system)** → **[📂 Aslam (Orange Pi 5 16GB)](https://github.com/AslamSys/_system/blob/main/hardware/aslam/README.md)** → **mordomo-whisper-asr**

### Containers Relacionados (aslam)
- [mordomo-audio-bridge](https://github.com/AslamSys/mordomo-audio-bridge)
- [mordomo-audio-capture-vad](https://github.com/AslamSys/mordomo-audio-capture-vad)
- [mordomo-wake-word-detector](https://github.com/AslamSys/mordomo-wake-word-detector)
- [mordomo-speaker-verification](https://github.com/AslamSys/mordomo-speaker-verification)
- [mordomo-speaker-id-diarization](https://github.com/AslamSys/mordomo-speaker-id-diarization)
- [mordomo-source-separation](https://github.com/AslamSys/mordomo-source-separation)
- [mordomo-core-gateway](https://github.com/AslamSys/mordomo-core-gateway)
- [mordomo-orchestrator](https://github.com/AslamSys/mordomo-orchestrator)
- [mordomo-brain](https://github.com/AslamSys/mordomo-brain)
- [mordomo-tts-engine](https://github.com/AslamSys/mordomo-tts-engine)
- [mordomo-system-watchdog](https://github.com/AslamSys/mordomo-system-watchdog)
- [mordomo-dashboard-ui](https://github.com/AslamSys/mordomo-dashboard-ui)
- [mordomo-openclaw-agent](https://github.com/AslamSys/mordomo-openclaw-agent)
- [mordomo-action-dispatcher](https://github.com/AslamSys/mordomo-action-dispatcher)
- [mordomo-skills-runner](https://github.com/AslamSys/mordomo-skills-runner)

---

**Container:** `whisper-asr`  
**Ecossistema:** Mordomo  
**Posição no Fluxo:** Quarto - Speech-to-Text

---

## 📋 Propósito

**Transcritor com processamento paralelo** - Inicia transcrição imediatamente após `wake_word.detected`, mas mantém resultados em buffer interno até receber `speaker.verified` (GATE). Isso reduz latência total em ~200-300ms, pois processa em paralelo com Speaker Verification.

**Ganho de Performance:** Primeira transcrição disponível em ~500ms (vs ~1000ms sequencial).

---

## 🎯 Responsabilidades

- ✅ **Escutar evento `speaker.verified`** do NATS para ativar transcrição
- ✅ **Consumir áudio do VAD** via ZeroMQ (mesma fonte que Wake Word)
- ✅ **Transcrever em tempo real** com chunks de 300ms
- ✅ **Publicar transcrições parciais** no NATS (streaming)
- ✅ **Detectar fim de frase** (silêncio > 1s) e publicar `is_final=true`
- ✅ **Encerrar ao receber `conversation.ended`** e voltar ao estado IDLE
- ✅ **Passar áudio+texto** para Speaker ID (diarização)

---

## 🔄 Estados do Whisper ASR

```
┌─────────────────────────────────────────────┐
│  IDLE (Aguardando)                          │
│  - Escuta NATS: wake_word.detected          │
│  - NÃO processa áudio                       │
└──────────────┬──────────────────────────────┘
               ↓ (recebeu wake_word.detected)
┌─────────────────────────────────────────────┐
│  BUFFERING (Processando em paralelo)        │
│  - Consome áudio do VAD (ZeroMQ)            │
│  - Processa com Whisper.cpp                 │
│  - Mantém transcrições em buffer interno    │
│  - Aguarda speaker.verified (GATE)          │
│  - Se speaker.rejected → descarta buffer    │
└──────────────┬──────────────────────────────┘
               ↓ (recebeu speaker.verified)
┌─────────────────────────────────────────────┐
│  TRANSCRIBING (Publicando)                  │
│  - Publica buffer acumulado no NATS         │
│  - Continua processando chunks em tempo real│
│  - Publica chunks no NATS (streaming)       │
│  - Envia áudio+texto para Speaker ID        │
└──────────────┬──────────────────────────────┘
               ↓ (silêncio OU conversation.ended)
┌─────────────────────────────────────────────┐
│  IDLE (volta a aguardar)                    │
└─────────────────────────────────────────────┘
```

**Latência Otimizada:**
- Sequencial: wake → verification (200ms) → whisper inicia → first chunk (+500ms) = **700ms**
- Paralelo: wake → [verification + whisper simultâneos] → gate abre → buffer pronto = **~500ms** ✅

---

## 🔧 Tecnologias

**Linguagem:** Python

**Principal:** `faster-whisper` (CTranslate2)
- **Engine:** CTranslate2 (Inference Engine otimizado para Transformers)
- **Performance:** ~4x a 8x mais rápido que `openai-whisper` original
- **Quantização:** INT8 (Padrão) - Perda imperceptível, ganho massivo de velocidade
- **VRAM/RAM:** Uso reduzido de memória

**Modelos:**
- `tiny` - Rápido, precisão ok
- `base` - Balanceado (recomendado para testes)
- `small` - Alta precisão (recomendado para produção)
- `medium` - Melhor para ditados longos

**Performance:** Processamento em **C++ puro** (CTranslate2), Python apenas gerencia I/O (ZeroMQ, NATS).

---

## 📊 Especificações

```yaml
Input:
  Sample Rate: 16000 Hz
  Format: PCM 16-bit mono
  Chunk Size: 4800 samples (300ms)
  Buffer: 80000 samples (5s para contexto)

Transcription:
  Model: whisper-base (150MB)
  Language: pt-BR
  Task: transcribe
  Beam Size: 5
  Quantization: int8
  
Performance (Orange Pi 5):
  CPU: 30-50% (4 cores ARM)
  RAM: ~ 500 MB (base model)
  Latency: 300-500ms per chunk
  Real-time Factor: 0.4x (2.5x mais rápido que tempo real)
  First Chunk: < 800ms (após ativação)
```

---

## 🔄 Fluxo Completo de uma Conversa (Paralelo)

```
1. Usuário: "ASLAM"  
   ↓
   VAD → distribui áudio (ZeroMQ)
   ↓
   Wake Word → detecta → NATS: wake_word.detected
   ↓
   ┌──────────────────────────────────────┐
   │ PROCESSAMENTO PARALELO (200ms)       │
   ├─→ Speaker Verification (200ms)       │
   ├─→ Whisper: IDLE → BUFFERING          │
   │   └─ Conecta VAD (ZeroMQ SUB)        │
   │   └─ Já processando áudio            │
   └─→ Speaker ID: standby                │
   └──────────────────────────────────────┘
   ↓
   [✅ speaker.verified] ← GATE ABRE (t=200ms)
   ↓
2. Whisper: BUFFERING → TRANSCRIBING
   └─ Publica buffer acumulado (já tem ~200ms processados)
   ↓
3. Usuário: "qual a temperatura?"
   ↓
   VAD → áudio (frames 30ms)
   ↓
   Whisper processa chunks de 300ms:
     - Buffer: "qual" → NATS partial (imediato!)
     - Chunk 1: "qual a" → NATS partial (+100ms)
     - Chunk 2: "qual a temperatura" → NATS partial (+300ms)
   ↓
   Silêncio detectado (1.5s)
   ↓
   Whisper: NATS final "qual a temperatura?"
   ↓
   Whisper → Speaker ID (gRPC): áudio + texto
   ↓
4. Speaker ID → identifica user_1 (paralelo com Whisper)
   ↓
   Conversation Manager → Brain → TTS
   ↓
5. Conversa termina
   ↓
   Conversation Manager → NATS: conversation.ended
   ↓
   Whisper: TRANSCRIBING → IDLE (limpa buffer, para consumo VAD)
```

**Ganho Total:** ~500ms até primeira transcrição (vs ~1000ms sequencial)

---

## 🔌 Interfaces

### Input 1: Eventos NATS (Ativação/Desativação)
```python
# Inicia buffer (processamento paralelo)

## 🔗 Navegação

**[🏠 AslamSys](https://github.com/AslamSys)** → **[📚 _system](https://github.com/AslamSys/_system)** → **[📂 Aslam (Orange Pi 5 16GB)](https://github.com/AslamSys/_system/blob/main/hardware/aslam/README.md)** → **mordomo-whisper-asr**

### Containers Relacionados (aslam)
- [mordomo-audio-bridge](https://github.com/AslamSys/mordomo-audio-bridge)
- [mordomo-audio-capture-vad](https://github.com/AslamSys/mordomo-audio-capture-vad)
- [mordomo-wake-word-detector](https://github.com/AslamSys/mordomo-wake-word-detector)
- [mordomo-speaker-verification](https://github.com/AslamSys/mordomo-speaker-verification)
- [mordomo-speaker-id-diarization](https://github.com/AslamSys/mordomo-speaker-id-diarization)
- [mordomo-source-separation](https://github.com/AslamSys/mordomo-source-separation)
- [mordomo-core-gateway](https://github.com/AslamSys/mordomo-core-gateway)
- [mordomo-orchestrator](https://github.com/AslamSys/mordomo-orchestrator)
- [mordomo-brain](https://github.com/AslamSys/mordomo-brain)
- [mordomo-tts-engine](https://github.com/AslamSys/mordomo-tts-engine)
- [mordomo-system-watchdog](https://github.com/AslamSys/mordomo-system-watchdog)
- [mordomo-dashboard-ui](https://github.com/AslamSys/mordomo-dashboard-ui)
- [mordomo-openclaw-agent](https://github.com/AslamSys/mordomo-openclaw-agent)
- [mordomo-action-dispatcher](https://github.com/AslamSys/mordomo-action-dispatcher)
- [mordomo-skills-runner](https://github.com/AslamSys/mordomo-skills-runner)

---
subject: "wake_word.detected"
payload: {
  "timestamp": 1732723200.000,
  "session_id": "uuid",
  "conversation_id": "conv_uuid"  # ID único da conversa
}
# Estado: IDLE → BUFFERING

## 🔗 Navegação

**[🏠 AslamSys](https://github.com/AslamSys)** → **[📚 _system](https://github.com/AslamSys/_system)** → **[📂 Aslam (Orange Pi 5 16GB)](https://github.com/AslamSys/_system/blob/main/hardware/aslam/README.md)** → **mordomo-whisper-asr**

### Containers Relacionados (aslam)
- [mordomo-audio-bridge](https://github.com/AslamSys/mordomo-audio-bridge)
- [mordomo-audio-capture-vad](https://github.com/AslamSys/mordomo-audio-capture-vad)
- [mordomo-wake-word-detector](https://github.com/AslamSys/mordomo-wake-word-detector)
- [mordomo-speaker-verification](https://github.com/AslamSys/mordomo-speaker-verification)
- [mordomo-speaker-id-diarization](https://github.com/AslamSys/mordomo-speaker-id-diarization)
- [mordomo-source-separation](https://github.com/AslamSys/mordomo-source-separation)
- [mordomo-core-gateway](https://github.com/AslamSys/mordomo-core-gateway)
- [mordomo-orchestrator](https://github.com/AslamSys/mordomo-orchestrator)
- [mordomo-brain](https://github.com/AslamSys/mordomo-brain)
- [mordomo-tts-engine](https://github.com/AslamSys/mordomo-tts-engine)
- [mordomo-system-watchdog](https://github.com/AslamSys/mordomo-system-watchdog)
- [mordomo-dashboard-ui](https://github.com/AslamSys/mordomo-dashboard-ui)
- [mordomo-openclaw-agent](https://github.com/AslamSys/mordomo-openclaw-agent)
- [mordomo-action-dispatcher](https://github.com/AslamSys/mordomo-action-dispatcher)
- [mordomo-skills-runner](https://github.com/AslamSys/mordomo-skills-runner)

---

# Libera resultados (gate aberto)

## 🔗 Navegação

**[🏠 AslamSys](https://github.com/AslamSys)** → **[📚 _system](https://github.com/AslamSys/_system)** → **[📂 Aslam (Orange Pi 5 16GB)](https://github.com/AslamSys/_system/blob/main/hardware/aslam/README.md)** → **mordomo-whisper-asr**

### Containers Relacionados (aslam)
- [mordomo-audio-bridge](https://github.com/AslamSys/mordomo-audio-bridge)
- [mordomo-audio-capture-vad](https://github.com/AslamSys/mordomo-audio-capture-vad)
- [mordomo-wake-word-detector](https://github.com/AslamSys/mordomo-wake-word-detector)
- [mordomo-speaker-verification](https://github.com/AslamSys/mordomo-speaker-verification)
- [mordomo-speaker-id-diarization](https://github.com/AslamSys/mordomo-speaker-id-diarization)
- [mordomo-source-separation](https://github.com/AslamSys/mordomo-source-separation)
- [mordomo-core-gateway](https://github.com/AslamSys/mordomo-core-gateway)
- [mordomo-orchestrator](https://github.com/AslamSys/mordomo-orchestrator)
- [mordomo-brain](https://github.com/AslamSys/mordomo-brain)
- [mordomo-tts-engine](https://github.com/AslamSys/mordomo-tts-engine)
- [mordomo-system-watchdog](https://github.com/AslamSys/mordomo-system-watchdog)
- [mordomo-dashboard-ui](https://github.com/AslamSys/mordomo-dashboard-ui)
- [mordomo-openclaw-agent](https://github.com/AslamSys/mordomo-openclaw-agent)
- [mordomo-action-dispatcher](https://github.com/AslamSys/mordomo-action-dispatcher)
- [mordomo-skills-runner](https://github.com/AslamSys/mordomo-skills-runner)

---
subject: "speaker.verified"
payload: {
  "user_id": "user_1",
  "confidence": 0.82,
  "timestamp": 1732723200.200,  # +200ms
  "session_id": "uuid",
  "conversation_id": "conv_uuid"
}
# Estado: BUFFERING → TRANSCRIBING (publica buffer)

## 🔗 Navegação

**[🏠 AslamSys](https://github.com/AslamSys)** → **[📚 _system](https://github.com/AslamSys/_system)** → **[📂 Aslam (Orange Pi 5 16GB)](https://github.com/AslamSys/_system/blob/main/hardware/aslam/README.md)** → **mordomo-whisper-asr**

### Containers Relacionados (aslam)
- [mordomo-audio-bridge](https://github.com/AslamSys/mordomo-audio-bridge)
- [mordomo-audio-capture-vad](https://github.com/AslamSys/mordomo-audio-capture-vad)
- [mordomo-wake-word-detector](https://github.com/AslamSys/mordomo-wake-word-detector)
- [mordomo-speaker-verification](https://github.com/AslamSys/mordomo-speaker-verification)
- [mordomo-speaker-id-diarization](https://github.com/AslamSys/mordomo-speaker-id-diarization)
- [mordomo-source-separation](https://github.com/AslamSys/mordomo-source-separation)
- [mordomo-core-gateway](https://github.com/AslamSys/mordomo-core-gateway)
- [mordomo-orchestrator](https://github.com/AslamSys/mordomo-orchestrator)
- [mordomo-brain](https://github.com/AslamSys/mordomo-brain)
- [mordomo-tts-engine](https://github.com/AslamSys/mordomo-tts-engine)
- [mordomo-system-watchdog](https://github.com/AslamSys/mordomo-system-watchdog)
- [mordomo-dashboard-ui](https://github.com/AslamSys/mordomo-dashboard-ui)
- [mordomo-openclaw-agent](https://github.com/AslamSys/mordomo-openclaw-agent)
- [mordomo-action-dispatcher](https://github.com/AslamSys/mordomo-action-dispatcher)
- [mordomo-skills-runner](https://github.com/AslamSys/mordomo-skills-runner)

---

# Descarta buffer (gate fechado)

## 🔗 Navegação

**[🏠 AslamSys](https://github.com/AslamSys)** → **[📚 _system](https://github.com/AslamSys/_system)** → **[📂 Aslam (Orange Pi 5 16GB)](https://github.com/AslamSys/_system/blob/main/hardware/aslam/README.md)** → **mordomo-whisper-asr**

### Containers Relacionados (aslam)
- [mordomo-audio-bridge](https://github.com/AslamSys/mordomo-audio-bridge)
- [mordomo-audio-capture-vad](https://github.com/AslamSys/mordomo-audio-capture-vad)
- [mordomo-wake-word-detector](https://github.com/AslamSys/mordomo-wake-word-detector)
- [mordomo-speaker-verification](https://github.com/AslamSys/mordomo-speaker-verification)
- [mordomo-speaker-id-diarization](https://github.com/AslamSys/mordomo-speaker-id-diarization)
- [mordomo-source-separation](https://github.com/AslamSys/mordomo-source-separation)
- [mordomo-core-gateway](https://github.com/AslamSys/mordomo-core-gateway)
- [mordomo-orchestrator](https://github.com/AslamSys/mordomo-orchestrator)
- [mordomo-brain](https://github.com/AslamSys/mordomo-brain)
- [mordomo-tts-engine](https://github.com/AslamSys/mordomo-tts-engine)
- [mordomo-system-watchdog](https://github.com/AslamSys/mordomo-system-watchdog)
- [mordomo-dashboard-ui](https://github.com/AslamSys/mordomo-dashboard-ui)
- [mordomo-openclaw-agent](https://github.com/AslamSys/mordomo-openclaw-agent)
- [mordomo-action-dispatcher](https://github.com/AslamSys/mordomo-action-dispatcher)
- [mordomo-skills-runner](https://github.com/AslamSys/mordomo-skills-runner)

---
subject: "speaker.rejected"
payload: {
  "reason": "unknown_voice",
  "timestamp": 1732723200.200,
  "session_id": "uuid",
  "conversation_id": "conv_uuid"
}
# Estado: BUFFERING → IDLE (descarta tudo)

## 🔗 Navegação

**[🏠 AslamSys](https://github.com/AslamSys)** → **[📚 _system](https://github.com/AslamSys/_system)** → **[📂 Aslam (Orange Pi 5 16GB)](https://github.com/AslamSys/_system/blob/main/hardware/aslam/README.md)** → **mordomo-whisper-asr**

### Containers Relacionados (aslam)
- [mordomo-audio-bridge](https://github.com/AslamSys/mordomo-audio-bridge)
- [mordomo-audio-capture-vad](https://github.com/AslamSys/mordomo-audio-capture-vad)
- [mordomo-wake-word-detector](https://github.com/AslamSys/mordomo-wake-word-detector)
- [mordomo-speaker-verification](https://github.com/AslamSys/mordomo-speaker-verification)
- [mordomo-speaker-id-diarization](https://github.com/AslamSys/mordomo-speaker-id-diarization)
- [mordomo-source-separation](https://github.com/AslamSys/mordomo-source-separation)
- [mordomo-core-gateway](https://github.com/AslamSys/mordomo-core-gateway)
- [mordomo-orchestrator](https://github.com/AslamSys/mordomo-orchestrator)
- [mordomo-brain](https://github.com/AslamSys/mordomo-brain)
- [mordomo-tts-engine](https://github.com/AslamSys/mordomo-tts-engine)
- [mordomo-system-watchdog](https://github.com/AslamSys/mordomo-system-watchdog)
- [mordomo-dashboard-ui](https://github.com/AslamSys/mordomo-dashboard-ui)
- [mordomo-openclaw-agent](https://github.com/AslamSys/mordomo-openclaw-agent)
- [mordomo-action-dispatcher](https://github.com/AslamSys/mordomo-action-dispatcher)
- [mordomo-skills-runner](https://github.com/AslamSys/mordomo-skills-runner)

---

# Desativa transcrição (reseta gate)

## 🔗 Navegação

**[🏠 AslamSys](https://github.com/AslamSys)** → **[📚 _system](https://github.com/AslamSys/_system)** → **[📂 Aslam (Orange Pi 5 16GB)](https://github.com/AslamSys/_system/blob/main/hardware/aslam/README.md)** → **mordomo-whisper-asr**

### Containers Relacionados (aslam)
- [mordomo-audio-bridge](https://github.com/AslamSys/mordomo-audio-bridge)
- [mordomo-audio-capture-vad](https://github.com/AslamSys/mordomo-audio-capture-vad)
- [mordomo-wake-word-detector](https://github.com/AslamSys/mordomo-wake-word-detector)
- [mordomo-speaker-verification](https://github.com/AslamSys/mordomo-speaker-verification)
- [mordomo-speaker-id-diarization](https://github.com/AslamSys/mordomo-speaker-id-diarization)
- [mordomo-source-separation](https://github.com/AslamSys/mordomo-source-separation)
- [mordomo-core-gateway](https://github.com/AslamSys/mordomo-core-gateway)
- [mordomo-orchestrator](https://github.com/AslamSys/mordomo-orchestrator)
- [mordomo-brain](https://github.com/AslamSys/mordomo-brain)
- [mordomo-tts-engine](https://github.com/AslamSys/mordomo-tts-engine)
- [mordomo-system-watchdog](https://github.com/AslamSys/mordomo-system-watchdog)
- [mordomo-dashboard-ui](https://github.com/AslamSys/mordomo-dashboard-ui)
- [mordomo-openclaw-agent](https://github.com/AslamSys/mordomo-openclaw-agent)
- [mordomo-action-dispatcher](https://github.com/AslamSys/mordomo-action-dispatcher)
- [mordomo-skills-runner](https://github.com/AslamSys/mordomo-skills-runner)

---
subject: "conversation.ended"
payload: {
  "session_id": "uuid",
  "conversation_id": "conv_uuid",
  "duration": 45.2,
  "timestamp": 1732723245.323
}
# Estado: TRANSCRIBING → IDLE

## 🔗 Navegação

**[🏠 AslamSys](https://github.com/AslamSys)** → **[📚 _system](https://github.com/AslamSys/_system)** → **[📂 Aslam (Orange Pi 5 16GB)](https://github.com/AslamSys/_system/blob/main/hardware/aslam/README.md)** → **mordomo-whisper-asr**

### Containers Relacionados (aslam)
- [mordomo-audio-bridge](https://github.com/AslamSys/mordomo-audio-bridge)
- [mordomo-audio-capture-vad](https://github.com/AslamSys/mordomo-audio-capture-vad)
- [mordomo-wake-word-detector](https://github.com/AslamSys/mordomo-wake-word-detector)
- [mordomo-speaker-verification](https://github.com/AslamSys/mordomo-speaker-verification)
- [mordomo-speaker-id-diarization](https://github.com/AslamSys/mordomo-speaker-id-diarization)
- [mordomo-source-separation](https://github.com/AslamSys/mordomo-source-separation)
- [mordomo-core-gateway](https://github.com/AslamSys/mordomo-core-gateway)
- [mordomo-orchestrator](https://github.com/AslamSys/mordomo-orchestrator)
- [mordomo-brain](https://github.com/AslamSys/mordomo-brain)
- [mordomo-tts-engine](https://github.com/AslamSys/mordomo-tts-engine)
- [mordomo-system-watchdog](https://github.com/AslamSys/mordomo-system-watchdog)
- [mordomo-dashboard-ui](https://github.com/AslamSys/mordomo-dashboard-ui)
- [mordomo-openclaw-agent](https://github.com/AslamSys/mordomo-openclaw-agent)
- [mordomo-action-dispatcher](https://github.com/AslamSys/mordomo-action-dispatcher)
- [mordomo-skills-runner](https://github.com/AslamSys/mordomo-skills-runner)

---
# Ações:

## 🔗 Navegação

**[🏠 AslamSys](https://github.com/AslamSys)** → **[📚 _system](https://github.com/AslamSys/_system)** → **[📂 Aslam (Orange Pi 5 16GB)](https://github.com/AslamSys/_system/blob/main/hardware/aslam/README.md)** → **mordomo-whisper-asr**

### Containers Relacionados (aslam)
- [mordomo-audio-bridge](https://github.com/AslamSys/mordomo-audio-bridge)
- [mordomo-audio-capture-vad](https://github.com/AslamSys/mordomo-audio-capture-vad)
- [mordomo-wake-word-detector](https://github.com/AslamSys/mordomo-wake-word-detector)
- [mordomo-speaker-verification](https://github.com/AslamSys/mordomo-speaker-verification)
- [mordomo-speaker-id-diarization](https://github.com/AslamSys/mordomo-speaker-id-diarization)
- [mordomo-source-separation](https://github.com/AslamSys/mordomo-source-separation)
- [mordomo-core-gateway](https://github.com/AslamSys/mordomo-core-gateway)
- [mordomo-orchestrator](https://github.com/AslamSys/mordomo-orchestrator)
- [mordomo-brain](https://github.com/AslamSys/mordomo-brain)
- [mordomo-tts-engine](https://github.com/AslamSys/mordomo-tts-engine)
- [mordomo-system-watchdog](https://github.com/AslamSys/mordomo-system-watchdog)
- [mordomo-dashboard-ui](https://github.com/AslamSys/mordomo-dashboard-ui)
- [mordomo-openclaw-agent](https://github.com/AslamSys/mordomo-openclaw-agent)
- [mordomo-action-dispatcher](https://github.com/AslamSys/mordomo-action-dispatcher)
- [mordomo-skills-runner](https://github.com/AslamSys/mordomo-skills-runner)

---
#  - Para de consumir VAD

## 🔗 Navegação

**[🏠 AslamSys](https://github.com/AslamSys)** → **[📚 _system](https://github.com/AslamSys/_system)** → **[📂 Aslam (Orange Pi 5 16GB)](https://github.com/AslamSys/_system/blob/main/hardware/aslam/README.md)** → **mordomo-whisper-asr**

### Containers Relacionados (aslam)
- [mordomo-audio-bridge](https://github.com/AslamSys/mordomo-audio-bridge)
- [mordomo-audio-capture-vad](https://github.com/AslamSys/mordomo-audio-capture-vad)
- [mordomo-wake-word-detector](https://github.com/AslamSys/mordomo-wake-word-detector)
- [mordomo-speaker-verification](https://github.com/AslamSys/mordomo-speaker-verification)
- [mordomo-speaker-id-diarization](https://github.com/AslamSys/mordomo-speaker-id-diarization)
- [mordomo-source-separation](https://github.com/AslamSys/mordomo-source-separation)
- [mordomo-core-gateway](https://github.com/AslamSys/mordomo-core-gateway)
- [mordomo-orchestrator](https://github.com/AslamSys/mordomo-orchestrator)
- [mordomo-brain](https://github.com/AslamSys/mordomo-brain)
- [mordomo-tts-engine](https://github.com/AslamSys/mordomo-tts-engine)
- [mordomo-system-watchdog](https://github.com/AslamSys/mordomo-system-watchdog)
- [mordomo-dashboard-ui](https://github.com/AslamSys/mordomo-dashboard-ui)
- [mordomo-openclaw-agent](https://github.com/AslamSys/mordomo-openclaw-agent)
- [mordomo-action-dispatcher](https://github.com/AslamSys/mordomo-action-dispatcher)
- [mordomo-skills-runner](https://github.com/AslamSys/mordomo-skills-runner)

---
#  - Limpa buffer interno

## 🔗 Navegação

**[🏠 AslamSys](https://github.com/AslamSys)** → **[📚 _system](https://github.com/AslamSys/_system)** → **[📂 Aslam (Orange Pi 5 16GB)](https://github.com/AslamSys/_system/blob/main/hardware/aslam/README.md)** → **mordomo-whisper-asr**

### Containers Relacionados (aslam)
- [mordomo-audio-bridge](https://github.com/AslamSys/mordomo-audio-bridge)
- [mordomo-audio-capture-vad](https://github.com/AslamSys/mordomo-audio-capture-vad)
- [mordomo-wake-word-detector](https://github.com/AslamSys/mordomo-wake-word-detector)
- [mordomo-speaker-verification](https://github.com/AslamSys/mordomo-speaker-verification)
- [mordomo-speaker-id-diarization](https://github.com/AslamSys/mordomo-speaker-id-diarization)
- [mordomo-source-separation](https://github.com/AslamSys/mordomo-source-separation)
- [mordomo-core-gateway](https://github.com/AslamSys/mordomo-core-gateway)
- [mordomo-orchestrator](https://github.com/AslamSys/mordomo-orchestrator)
- [mordomo-brain](https://github.com/AslamSys/mordomo-brain)
- [mordomo-tts-engine](https://github.com/AslamSys/mordomo-tts-engine)
- [mordomo-system-watchdog](https://github.com/AslamSys/mordomo-system-watchdog)
- [mordomo-dashboard-ui](https://github.com/AslamSys/mordomo-dashboard-ui)
- [mordomo-openclaw-agent](https://github.com/AslamSys/mordomo-openclaw-agent)
- [mordomo-action-dispatcher](https://github.com/AslamSys/mordomo-action-dispatcher)
- [mordomo-skills-runner](https://github.com/AslamSys/mordomo-skills-runner)

---
#  - Reseta gate (pronto para próxima wake_word.detected)

## 🔗 Navegação

**[🏠 AslamSys](https://github.com/AslamSys)** → **[📚 _system](https://github.com/AslamSys/_system)** → **[📂 Aslam (Orange Pi 5 16GB)](https://github.com/AslamSys/_system/blob/main/hardware/aslam/README.md)** → **mordomo-whisper-asr**

### Containers Relacionados (aslam)
- [mordomo-audio-bridge](https://github.com/AslamSys/mordomo-audio-bridge)
- [mordomo-audio-capture-vad](https://github.com/AslamSys/mordomo-audio-capture-vad)
- [mordomo-wake-word-detector](https://github.com/AslamSys/mordomo-wake-word-detector)
- [mordomo-speaker-verification](https://github.com/AslamSys/mordomo-speaker-verification)
- [mordomo-speaker-id-diarization](https://github.com/AslamSys/mordomo-speaker-id-diarization)
- [mordomo-source-separation](https://github.com/AslamSys/mordomo-source-separation)
- [mordomo-core-gateway](https://github.com/AslamSys/mordomo-core-gateway)
- [mordomo-orchestrator](https://github.com/AslamSys/mordomo-orchestrator)
- [mordomo-brain](https://github.com/AslamSys/mordomo-brain)
- [mordomo-tts-engine](https://github.com/AslamSys/mordomo-tts-engine)
- [mordomo-system-watchdog](https://github.com/AslamSys/mordomo-system-watchdog)
- [mordomo-dashboard-ui](https://github.com/AslamSys/mordomo-dashboard-ui)
- [mordomo-openclaw-agent](https://github.com/AslamSys/mordomo-openclaw-agent)
- [mordomo-action-dispatcher](https://github.com/AslamSys/mordomo-action-dispatcher)
- [mordomo-skills-runner](https://github.com/AslamSys/mordomo-skills-runner)

---
#  - Volta ao estado inicial

## 🔗 Navegação

**[🏠 AslamSys](https://github.com/AslamSys)** → **[📚 _system](https://github.com/AslamSys/_system)** → **[📂 Aslam (Orange Pi 5 16GB)](https://github.com/AslamSys/_system/blob/main/hardware/aslam/README.md)** → **mordomo-whisper-asr**

### Containers Relacionados (aslam)
- [mordomo-audio-bridge](https://github.com/AslamSys/mordomo-audio-bridge)
- [mordomo-audio-capture-vad](https://github.com/AslamSys/mordomo-audio-capture-vad)
- [mordomo-wake-word-detector](https://github.com/AslamSys/mordomo-wake-word-detector)
- [mordomo-speaker-verification](https://github.com/AslamSys/mordomo-speaker-verification)
- [mordomo-speaker-id-diarization](https://github.com/AslamSys/mordomo-speaker-id-diarization)
- [mordomo-source-separation](https://github.com/AslamSys/mordomo-source-separation)
- [mordomo-core-gateway](https://github.com/AslamSys/mordomo-core-gateway)
- [mordomo-orchestrator](https://github.com/AslamSys/mordomo-orchestrator)
- [mordomo-brain](https://github.com/AslamSys/mordomo-brain)
- [mordomo-tts-engine](https://github.com/AslamSys/mordomo-tts-engine)
- [mordomo-system-watchdog](https://github.com/AslamSys/mordomo-system-watchdog)
- [mordomo-dashboard-ui](https://github.com/AslamSys/mordomo-dashboard-ui)
- [mordomo-openclaw-agent](https://github.com/AslamSys/mordomo-openclaw-agent)
- [mordomo-action-dispatcher](https://github.com/AslamSys/mordomo-action-dispatcher)
- [mordomo-skills-runner](https://github.com/AslamSys/mordomo-skills-runner)

---
```

### Input 2: Áudio do VAD (ZeroMQ SUB)
```python
# Mesma fonte que Wake Word Detector

## 🔗 Navegação

**[🏠 AslamSys](https://github.com/AslamSys)** → **[📚 _system](https://github.com/AslamSys/_system)** → **[📂 Aslam (Orange Pi 5 16GB)](https://github.com/AslamSys/_system/blob/main/hardware/aslam/README.md)** → **mordomo-whisper-asr**

### Containers Relacionados (aslam)
- [mordomo-audio-bridge](https://github.com/AslamSys/mordomo-audio-bridge)
- [mordomo-audio-capture-vad](https://github.com/AslamSys/mordomo-audio-capture-vad)
- [mordomo-wake-word-detector](https://github.com/AslamSys/mordomo-wake-word-detector)
- [mordomo-speaker-verification](https://github.com/AslamSys/mordomo-speaker-verification)
- [mordomo-speaker-id-diarization](https://github.com/AslamSys/mordomo-speaker-id-diarization)
- [mordomo-source-separation](https://github.com/AslamSys/mordomo-source-separation)
- [mordomo-core-gateway](https://github.com/AslamSys/mordomo-core-gateway)
- [mordomo-orchestrator](https://github.com/AslamSys/mordomo-orchestrator)
- [mordomo-brain](https://github.com/AslamSys/mordomo-brain)
- [mordomo-tts-engine](https://github.com/AslamSys/mordomo-tts-engine)
- [mordomo-system-watchdog](https://github.com/AslamSys/mordomo-system-watchdog)
- [mordomo-dashboard-ui](https://github.com/AslamSys/mordomo-dashboard-ui)
- [mordomo-openclaw-agent](https://github.com/AslamSys/mordomo-openclaw-agent)
- [mordomo-action-dispatcher](https://github.com/AslamSys/mordomo-action-dispatcher)
- [mordomo-skills-runner](https://github.com/AslamSys/mordomo-skills-runner)

---
endpoint: "tcp://audio-capture-vad:5555"
topic: "audio.raw"

# Payload (30ms frames)

## 🔗 Navegação

**[🏠 AslamSys](https://github.com/AslamSys)** → **[📚 _system](https://github.com/AslamSys/_system)** → **[📂 Aslam (Orange Pi 5 16GB)](https://github.com/AslamSys/_system/blob/main/hardware/aslam/README.md)** → **mordomo-whisper-asr**

### Containers Relacionados (aslam)
- [mordomo-audio-bridge](https://github.com/AslamSys/mordomo-audio-bridge)
- [mordomo-audio-capture-vad](https://github.com/AslamSys/mordomo-audio-capture-vad)
- [mordomo-wake-word-detector](https://github.com/AslamSys/mordomo-wake-word-detector)
- [mordomo-speaker-verification](https://github.com/AslamSys/mordomo-speaker-verification)
- [mordomo-speaker-id-diarization](https://github.com/AslamSys/mordomo-speaker-id-diarization)
- [mordomo-source-separation](https://github.com/AslamSys/mordomo-source-separation)
- [mordomo-core-gateway](https://github.com/AslamSys/mordomo-core-gateway)
- [mordomo-orchestrator](https://github.com/AslamSys/mordomo-orchestrator)
- [mordomo-brain](https://github.com/AslamSys/mordomo-brain)
- [mordomo-tts-engine](https://github.com/AslamSys/mordomo-tts-engine)
- [mordomo-system-watchdog](https://github.com/AslamSys/mordomo-system-watchdog)
- [mordomo-dashboard-ui](https://github.com/AslamSys/mordomo-dashboard-ui)
- [mordomo-openclaw-agent](https://github.com/AslamSys/mordomo-openclaw-agent)
- [mordomo-action-dispatcher](https://github.com/AslamSys/mordomo-action-dispatcher)
- [mordomo-skills-runner](https://github.com/AslamSys/mordomo-skills-runner)

---
{
  "timestamp": 1732723200.123,
  "sample_rate": 16000,
  "channels": 1,
  "format": "int16",
  "data": b"<raw PCM bytes>",
  "vad_active": true,
  "energy": 0.45
}
```

### Output 1: Transcrições Parciais (NATS Streaming)
```python
# Publicado a cada 300ms de áudio processado

## 🔗 Navegação

**[🏠 AslamSys](https://github.com/AslamSys)** → **[📚 _system](https://github.com/AslamSys/_system)** → **[📂 Aslam (Orange Pi 5 16GB)](https://github.com/AslamSys/_system/blob/main/hardware/aslam/README.md)** → **mordomo-whisper-asr**

### Containers Relacionados (aslam)
- [mordomo-audio-bridge](https://github.com/AslamSys/mordomo-audio-bridge)
- [mordomo-audio-capture-vad](https://github.com/AslamSys/mordomo-audio-capture-vad)
- [mordomo-wake-word-detector](https://github.com/AslamSys/mordomo-wake-word-detector)
- [mordomo-speaker-verification](https://github.com/AslamSys/mordomo-speaker-verification)
- [mordomo-speaker-id-diarization](https://github.com/AslamSys/mordomo-speaker-id-diarization)
- [mordomo-source-separation](https://github.com/AslamSys/mordomo-source-separation)
- [mordomo-core-gateway](https://github.com/AslamSys/mordomo-core-gateway)
- [mordomo-orchestrator](https://github.com/AslamSys/mordomo-orchestrator)
- [mordomo-brain](https://github.com/AslamSys/mordomo-brain)
- [mordomo-tts-engine](https://github.com/AslamSys/mordomo-tts-engine)
- [mordomo-system-watchdog](https://github.com/AslamSys/mordomo-system-watchdog)
- [mordomo-dashboard-ui](https://github.com/AslamSys/mordomo-dashboard-ui)
- [mordomo-openclaw-agent](https://github.com/AslamSys/mordomo-openclaw-agent)
- [mordomo-action-dispatcher](https://github.com/AslamSys/mordomo-action-dispatcher)
- [mordomo-skills-runner](https://github.com/AslamSys/mordomo-skills-runner)

---
subject: "speech.transcription.partial.{conversation_id}"
payload: {
  "text": "qual a",              # transcrição parcial
  "confidence": 0.88,
  "speaker_id": "user_1",
  "session_id": "uuid",
  "conversation_id": "conv_uuid",  # ID da conversa
  "timestamp": 1732723200.423,
  "is_final": false,
  "sequence": 1                  # ordem do chunk
}
```

### Output 2: Transcrição Final (NATS Event)
```python
# Publicado quando detecta fim de frase (silêncio > 1s)

## 🔗 Navegação

**[🏠 AslamSys](https://github.com/AslamSys)** → **[📚 _system](https://github.com/AslamSys/_system)** → **[📂 Aslam (Orange Pi 5 16GB)](https://github.com/AslamSys/_system/blob/main/hardware/aslam/README.md)** → **mordomo-whisper-asr**

### Containers Relacionados (aslam)
- [mordomo-audio-bridge](https://github.com/AslamSys/mordomo-audio-bridge)
- [mordomo-audio-capture-vad](https://github.com/AslamSys/mordomo-audio-capture-vad)
- [mordomo-wake-word-detector](https://github.com/AslamSys/mordomo-wake-word-detector)
- [mordomo-speaker-verification](https://github.com/AslamSys/mordomo-speaker-verification)
- [mordomo-speaker-id-diarization](https://github.com/AslamSys/mordomo-speaker-id-diarization)
- [mordomo-source-separation](https://github.com/AslamSys/mordomo-source-separation)
- [mordomo-core-gateway](https://github.com/AslamSys/mordomo-core-gateway)
- [mordomo-orchestrator](https://github.com/AslamSys/mordomo-orchestrator)
- [mordomo-brain](https://github.com/AslamSys/mordomo-brain)
- [mordomo-tts-engine](https://github.com/AslamSys/mordomo-tts-engine)
- [mordomo-system-watchdog](https://github.com/AslamSys/mordomo-system-watchdog)
- [mordomo-dashboard-ui](https://github.com/AslamSys/mordomo-dashboard-ui)
- [mordomo-openclaw-agent](https://github.com/AslamSys/mordomo-openclaw-agent)
- [mordomo-action-dispatcher](https://github.com/AslamSys/mordomo-action-dispatcher)
- [mordomo-skills-runner](https://github.com/AslamSys/mordomo-skills-runner)

---
subject: "speech.transcription.final.{conversation_id}"
payload: {
  "text": "qual a temperatura lá fora",  # frase completa
  "confidence": 0.91,
  "speaker_id": "user_1",
  "session_id": "uuid",
  "conversation_id": "conv_uuid",  # ID da conversa
  "duration": 2.3,
  "timestamp": 1732723202.723,
  "is_final": true
}
```

### Output 3: Para Speaker ID (gRPC)
```python
# Envia áudio + transcrição para diarização

## 🔗 Navegação

**[🏠 AslamSys](https://github.com/AslamSys)** → **[📚 _system](https://github.com/AslamSys/_system)** → **[📂 Aslam (Orange Pi 5 16GB)](https://github.com/AslamSys/_system/blob/main/hardware/aslam/README.md)** → **mordomo-whisper-asr**

### Containers Relacionados (aslam)
- [mordomo-audio-bridge](https://github.com/AslamSys/mordomo-audio-bridge)
- [mordomo-audio-capture-vad](https://github.com/AslamSys/mordomo-audio-capture-vad)
- [mordomo-wake-word-detector](https://github.com/AslamSys/mordomo-wake-word-detector)
- [mordomo-speaker-verification](https://github.com/AslamSys/mordomo-speaker-verification)
- [mordomo-speaker-id-diarization](https://github.com/AslamSys/mordomo-speaker-id-diarization)
- [mordomo-source-separation](https://github.com/AslamSys/mordomo-source-separation)
- [mordomo-core-gateway](https://github.com/AslamSys/mordomo-core-gateway)
- [mordomo-orchestrator](https://github.com/AslamSys/mordomo-orchestrator)
- [mordomo-brain](https://github.com/AslamSys/mordomo-brain)
- [mordomo-tts-engine](https://github.com/AslamSys/mordomo-tts-engine)
- [mordomo-system-watchdog](https://github.com/AslamSys/mordomo-system-watchdog)
- [mordomo-dashboard-ui](https://github.com/AslamSys/mordomo-dashboard-ui)
- [mordomo-openclaw-agent](https://github.com/AslamSys/mordomo-openclaw-agent)
- [mordomo-action-dispatcher](https://github.com/AslamSys/mordomo-action-dispatcher)
- [mordomo-skills-runner](https://github.com/AslamSys/mordomo-skills-runner)

---
service SpeakerDiarization {
  rpc DiarizeAudio(DiarizeRequest) returns (DiarizeResponse);
}

message DiarizeRequest {
  bytes audio = 1;              # áudio bruto da frase
  string transcript = 2;        # texto transcrito
  string session_id = 3;
  string conversation_id = 4;   # ID da conversa
  int64 timestamp = 5;
}
```

---

## ⚙️ Configuração

```yaml
whisper:
  model: "base"  # tiny, base, small (recomendado: base)
  model_path: "/models/ggml-base.bin"
  language: "pt"  # português brasileiro
  task: "transcribe"
  
  # Otimizações para latência
  beam_size: 5        # qualidade vs velocidade
  best_of: 5
  temperature: 0.0    # determinístico
  no_speech_threshold: 0.6  # ignora ruído
  
streaming:
  chunk_duration_ms: 300      # processa a cada 300ms
  max_silence_ms: 1500        # 1.5s de silêncio = fim de frase
  buffer_size_ms: 5000        # buffer para contexto
  
performance:
  n_threads: 4                # Orange Pi 5: 4 threads
  use_gpu: false              # CPU only (sem GPU no Orange Pi)
  quantization: "int8"        # modelo quantizado
  
input:
  # ZeroMQ - Áudio do VAD
  zeromq_endpoint: "tcp://audio-capture-vad:5555"
  zeromq_topic: "audio.raw"
  
  # NATS - Eventos de controle
  nats_url: "nats://nats:4222"
  nats_activate: "speaker.verified"
  nats_deactivate: "conversation.ended"
  
output:
  # NATS - Transcrições
  nats_url: "nats://nats:4222"
  nats_partial: "speech.transcription.partial.{conversation_id}"
  nats_final: "speech.transcription.final.{conversation_id}"
  
  # gRPC - Speaker ID
  speaker_id_grpc: "speaker-id-diarization:50052"
```

---

## 📈 Métricas

```python
# Estados

## 🔗 Navegação

**[🏠 AslamSys](https://github.com/AslamSys)** → **[📚 _system](https://github.com/AslamSys/_system)** → **[📂 Aslam (Orange Pi 5 16GB)](https://github.com/AslamSys/_system/blob/main/hardware/aslam/README.md)** → **mordomo-whisper-asr**

### Containers Relacionados (aslam)
- [mordomo-audio-bridge](https://github.com/AslamSys/mordomo-audio-bridge)
- [mordomo-audio-capture-vad](https://github.com/AslamSys/mordomo-audio-capture-vad)
- [mordomo-wake-word-detector](https://github.com/AslamSys/mordomo-wake-word-detector)
- [mordomo-speaker-verification](https://github.com/AslamSys/mordomo-speaker-verification)
- [mordomo-speaker-id-diarization](https://github.com/AslamSys/mordomo-speaker-id-diarization)
- [mordomo-source-separation](https://github.com/AslamSys/mordomo-source-separation)
- [mordomo-core-gateway](https://github.com/AslamSys/mordomo-core-gateway)
- [mordomo-orchestrator](https://github.com/AslamSys/mordomo-orchestrator)
- [mordomo-brain](https://github.com/AslamSys/mordomo-brain)
- [mordomo-tts-engine](https://github.com/AslamSys/mordomo-tts-engine)
- [mordomo-system-watchdog](https://github.com/AslamSys/mordomo-system-watchdog)
- [mordomo-dashboard-ui](https://github.com/AslamSys/mordomo-dashboard-ui)
- [mordomo-openclaw-agent](https://github.com/AslamSys/mordomo-openclaw-agent)
- [mordomo-action-dispatcher](https://github.com/AslamSys/mordomo-action-dispatcher)
- [mordomo-skills-runner](https://github.com/AslamSys/mordomo-skills-runner)

---
whisper_state  # 0=IDLE, 1=TRANSCRIBING (gauge)
whisper_active_sessions  # número de sessões ativas

# Performance

## 🔗 Navegação

**[🏠 AslamSys](https://github.com/AslamSys)** → **[📚 _system](https://github.com/AslamSys/_system)** → **[📂 Aslam (Orange Pi 5 16GB)](https://github.com/AslamSys/_system/blob/main/hardware/aslam/README.md)** → **mordomo-whisper-asr**

### Containers Relacionados (aslam)
- [mordomo-audio-bridge](https://github.com/AslamSys/mordomo-audio-bridge)
- [mordomo-audio-capture-vad](https://github.com/AslamSys/mordomo-audio-capture-vad)
- [mordomo-wake-word-detector](https://github.com/AslamSys/mordomo-wake-word-detector)
- [mordomo-speaker-verification](https://github.com/AslamSys/mordomo-speaker-verification)
- [mordomo-speaker-id-diarization](https://github.com/AslamSys/mordomo-speaker-id-diarization)
- [mordomo-source-separation](https://github.com/AslamSys/mordomo-source-separation)
- [mordomo-core-gateway](https://github.com/AslamSys/mordomo-core-gateway)
- [mordomo-orchestrator](https://github.com/AslamSys/mordomo-orchestrator)
- [mordomo-brain](https://github.com/AslamSys/mordomo-brain)
- [mordomo-tts-engine](https://github.com/AslamSys/mordomo-tts-engine)
- [mordomo-system-watchdog](https://github.com/AslamSys/mordomo-system-watchdog)
- [mordomo-dashboard-ui](https://github.com/AslamSys/mordomo-dashboard-ui)
- [mordomo-openclaw-agent](https://github.com/AslamSys/mordomo-openclaw-agent)
- [mordomo-action-dispatcher](https://github.com/AslamSys/mordomo-action-dispatcher)
- [mordomo-skills-runner](https://github.com/AslamSys/mordomo-skills-runner)

---
whisper_transcription_latency_seconds  # histogram
whisper_chunk_processing_time_seconds  # tempo por chunk
whisper_realtime_factor  # quanto mais rápido que realtime

# Qualidade

## 🔗 Navegação

**[🏠 AslamSys](https://github.com/AslamSys)** → **[📚 _system](https://github.com/AslamSys/_system)** → **[📂 Aslam (Orange Pi 5 16GB)](https://github.com/AslamSys/_system/blob/main/hardware/aslam/README.md)** → **mordomo-whisper-asr**

### Containers Relacionados (aslam)
- [mordomo-audio-bridge](https://github.com/AslamSys/mordomo-audio-bridge)
- [mordomo-audio-capture-vad](https://github.com/AslamSys/mordomo-audio-capture-vad)
- [mordomo-wake-word-detector](https://github.com/AslamSys/mordomo-wake-word-detector)
- [mordomo-speaker-verification](https://github.com/AslamSys/mordomo-speaker-verification)
- [mordomo-speaker-id-diarization](https://github.com/AslamSys/mordomo-speaker-id-diarization)
- [mordomo-source-separation](https://github.com/AslamSys/mordomo-source-separation)
- [mordomo-core-gateway](https://github.com/AslamSys/mordomo-core-gateway)
- [mordomo-orchestrator](https://github.com/AslamSys/mordomo-orchestrator)
- [mordomo-brain](https://github.com/AslamSys/mordomo-brain)
- [mordomo-tts-engine](https://github.com/AslamSys/mordomo-tts-engine)
- [mordomo-system-watchdog](https://github.com/AslamSys/mordomo-system-watchdog)
- [mordomo-dashboard-ui](https://github.com/AslamSys/mordomo-dashboard-ui)
- [mordomo-openclaw-agent](https://github.com/AslamSys/mordomo-openclaw-agent)
- [mordomo-action-dispatcher](https://github.com/AslamSys/mordomo-action-dispatcher)
- [mordomo-skills-runner](https://github.com/AslamSys/mordomo-skills-runner)

---
whisper_confidence_avg  # confiança média
whisper_words_per_minute  # velocidade de fala
whisper_sentences_total  # frases completas

# Volume

## 🔗 Navegação

**[🏠 AslamSys](https://github.com/AslamSys)** → **[📚 _system](https://github.com/AslamSys/_system)** → **[📂 Aslam (Orange Pi 5 16GB)](https://github.com/AslamSys/_system/blob/main/hardware/aslam/README.md)** → **mordomo-whisper-asr**

### Containers Relacionados (aslam)
- [mordomo-audio-bridge](https://github.com/AslamSys/mordomo-audio-bridge)
- [mordomo-audio-capture-vad](https://github.com/AslamSys/mordomo-audio-capture-vad)
- [mordomo-wake-word-detector](https://github.com/AslamSys/mordomo-wake-word-detector)
- [mordomo-speaker-verification](https://github.com/AslamSys/mordomo-speaker-verification)
- [mordomo-speaker-id-diarization](https://github.com/AslamSys/mordomo-speaker-id-diarization)
- [mordomo-source-separation](https://github.com/AslamSys/mordomo-source-separation)
- [mordomo-core-gateway](https://github.com/AslamSys/mordomo-core-gateway)
- [mordomo-orchestrator](https://github.com/AslamSys/mordomo-orchestrator)
- [mordomo-brain](https://github.com/AslamSys/mordomo-brain)
- [mordomo-tts-engine](https://github.com/AslamSys/mordomo-tts-engine)
- [mordomo-system-watchdog](https://github.com/AslamSys/mordomo-system-watchdog)
- [mordomo-dashboard-ui](https://github.com/AslamSys/mordomo-dashboard-ui)
- [mordomo-openclaw-agent](https://github.com/AslamSys/mordomo-openclaw-agent)
- [mordomo-action-dispatcher](https://github.com/AslamSys/mordomo-action-dispatcher)
- [mordomo-skills-runner](https://github.com/AslamSys/mordomo-skills-runner)

---
whisper_chunks_processed_total
whisper_partial_transcriptions_total
whisper_final_transcriptions_total

# Ativação/Desativação

## 🔗 Navegação

**[🏠 AslamSys](https://github.com/AslamSys)** → **[📚 _system](https://github.com/AslamSys/_system)** → **[📂 Aslam (Orange Pi 5 16GB)](https://github.com/AslamSys/_system/blob/main/hardware/aslam/README.md)** → **mordomo-whisper-asr**

### Containers Relacionados (aslam)
- [mordomo-audio-bridge](https://github.com/AslamSys/mordomo-audio-bridge)
- [mordomo-audio-capture-vad](https://github.com/AslamSys/mordomo-audio-capture-vad)
- [mordomo-wake-word-detector](https://github.com/AslamSys/mordomo-wake-word-detector)
- [mordomo-speaker-verification](https://github.com/AslamSys/mordomo-speaker-verification)
- [mordomo-speaker-id-diarization](https://github.com/AslamSys/mordomo-speaker-id-diarization)
- [mordomo-source-separation](https://github.com/AslamSys/mordomo-source-separation)
- [mordomo-core-gateway](https://github.com/AslamSys/mordomo-core-gateway)
- [mordomo-orchestrator](https://github.com/AslamSys/mordomo-orchestrator)
- [mordomo-brain](https://github.com/AslamSys/mordomo-brain)
- [mordomo-tts-engine](https://github.com/AslamSys/mordomo-tts-engine)
- [mordomo-system-watchdog](https://github.com/AslamSys/mordomo-system-watchdog)
- [mordomo-dashboard-ui](https://github.com/AslamSys/mordomo-dashboard-ui)
- [mordomo-openclaw-agent](https://github.com/AslamSys/mordomo-openclaw-agent)
- [mordomo-action-dispatcher](https://github.com/AslamSys/mordomo-action-dispatcher)
- [mordomo-skills-runner](https://github.com/AslamSys/mordomo-skills-runner)

---
whisper_activations_total  # speaker.verified recebidos
whisper_deactivations_total  # conversation.ended recebidos
```

---

## 🔗 Integração

**Ativado por:** Speaker Verification (NATS: `speaker.verified`)

**Recebe áudio de:** Audio Capture VAD (ZeroMQ)

**Envia para:**
- Conversation Manager (NATS: transcriptions)
- Speaker ID (gRPC: áudio + texto)

**Desativado por:** Conversation Manager (NATS: `conversation.ended`)

**Monitora:** Prometheus (métricas), Loki (logs)

---

## 🐳 Docker

```dockerfile
FROM debian:bookworm-slim

# Whisper.cpp dependencies

## 🔗 Navegação

**[🏠 AslamSys](https://github.com/AslamSys)** → **[📚 _system](https://github.com/AslamSys/_system)** → **[📂 Aslam (Orange Pi 5 16GB)](https://github.com/AslamSys/_system/blob/main/hardware/aslam/README.md)** → **mordomo-whisper-asr**

### Containers Relacionados (aslam)
- [mordomo-audio-bridge](https://github.com/AslamSys/mordomo-audio-bridge)
- [mordomo-audio-capture-vad](https://github.com/AslamSys/mordomo-audio-capture-vad)
- [mordomo-wake-word-detector](https://github.com/AslamSys/mordomo-wake-word-detector)
- [mordomo-speaker-verification](https://github.com/AslamSys/mordomo-speaker-verification)
- [mordomo-speaker-id-diarization](https://github.com/AslamSys/mordomo-speaker-id-diarization)
- [mordomo-source-separation](https://github.com/AslamSys/mordomo-source-separation)
- [mordomo-core-gateway](https://github.com/AslamSys/mordomo-core-gateway)
- [mordomo-orchestrator](https://github.com/AslamSys/mordomo-orchestrator)
- [mordomo-brain](https://github.com/AslamSys/mordomo-brain)
- [mordomo-tts-engine](https://github.com/AslamSys/mordomo-tts-engine)
- [mordomo-system-watchdog](https://github.com/AslamSys/mordomo-system-watchdog)
- [mordomo-dashboard-ui](https://github.com/AslamSys/mordomo-dashboard-ui)
- [mordomo-openclaw-agent](https://github.com/AslamSys/mordomo-openclaw-agent)
- [mordomo-action-dispatcher](https://github.com/AslamSys/mordomo-action-dispatcher)
- [mordomo-skills-runner](https://github.com/AslamSys/mordomo-skills-runner)

---
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    wget

# Build whisper.cpp

## 🔗 Navegação

**[🏠 AslamSys](https://github.com/AslamSys)** → **[📚 _system](https://github.com/AslamSys/_system)** → **[📂 Aslam (Orange Pi 5 16GB)](https://github.com/AslamSys/_system/blob/main/hardware/aslam/README.md)** → **mordomo-whisper-asr**

### Containers Relacionados (aslam)
- [mordomo-audio-bridge](https://github.com/AslamSys/mordomo-audio-bridge)
- [mordomo-audio-capture-vad](https://github.com/AslamSys/mordomo-audio-capture-vad)
- [mordomo-wake-word-detector](https://github.com/AslamSys/mordomo-wake-word-detector)
- [mordomo-speaker-verification](https://github.com/AslamSys/mordomo-speaker-verification)
- [mordomo-speaker-id-diarization](https://github.com/AslamSys/mordomo-speaker-id-diarization)
- [mordomo-source-separation](https://github.com/AslamSys/mordomo-source-separation)
- [mordomo-core-gateway](https://github.com/AslamSys/mordomo-core-gateway)
- [mordomo-orchestrator](https://github.com/AslamSys/mordomo-orchestrator)
- [mordomo-brain](https://github.com/AslamSys/mordomo-brain)
- [mordomo-tts-engine](https://github.com/AslamSys/mordomo-tts-engine)
- [mordomo-system-watchdog](https://github.com/AslamSys/mordomo-system-watchdog)
- [mordomo-dashboard-ui](https://github.com/AslamSys/mordomo-dashboard-ui)
- [mordomo-openclaw-agent](https://github.com/AslamSys/mordomo-openclaw-agent)
- [mordomo-action-dispatcher](https://github.com/AslamSys/mordomo-action-dispatcher)
- [mordomo-skills-runner](https://github.com/AslamSys/mordomo-skills-runner)

---
WORKDIR /build
RUN git clone https://github.com/ggerganov/whisper.cpp.git && \
    cd whisper.cpp && \
    make

# Download model

## 🔗 Navegação

**[🏠 AslamSys](https://github.com/AslamSys)** → **[📚 _system](https://github.com/AslamSys/_system)** → **[📂 Aslam (Orange Pi 5 16GB)](https://github.com/AslamSys/_system/blob/main/hardware/aslam/README.md)** → **mordomo-whisper-asr**

### Containers Relacionados (aslam)
- [mordomo-audio-bridge](https://github.com/AslamSys/mordomo-audio-bridge)
- [mordomo-audio-capture-vad](https://github.com/AslamSys/mordomo-audio-capture-vad)
- [mordomo-wake-word-detector](https://github.com/AslamSys/mordomo-wake-word-detector)
- [mordomo-speaker-verification](https://github.com/AslamSys/mordomo-speaker-verification)
- [mordomo-speaker-id-diarization](https://github.com/AslamSys/mordomo-speaker-id-diarization)
- [mordomo-source-separation](https://github.com/AslamSys/mordomo-source-separation)
- [mordomo-core-gateway](https://github.com/AslamSys/mordomo-core-gateway)
- [mordomo-orchestrator](https://github.com/AslamSys/mordomo-orchestrator)
- [mordomo-brain](https://github.com/AslamSys/mordomo-brain)
- [mordomo-tts-engine](https://github.com/AslamSys/mordomo-tts-engine)
- [mordomo-system-watchdog](https://github.com/AslamSys/mordomo-system-watchdog)
- [mordomo-dashboard-ui](https://github.com/AslamSys/mordomo-dashboard-ui)
- [mordomo-openclaw-agent](https://github.com/AslamSys/mordomo-openclaw-agent)
- [mordomo-action-dispatcher](https://github.com/AslamSys/mordomo-action-dispatcher)
- [mordomo-skills-runner](https://github.com/AslamSys/mordomo-skills-runner)

---
RUN cd whisper.cpp/models && \
    bash download-ggml-model.sh base

# Python para gRPC

## 🔗 Navegação

**[🏠 AslamSys](https://github.com/AslamSys)** → **[📚 _system](https://github.com/AslamSys/_system)** → **[📂 Aslam (Orange Pi 5 16GB)](https://github.com/AslamSys/_system/blob/main/hardware/aslam/README.md)** → **mordomo-whisper-asr**

### Containers Relacionados (aslam)
- [mordomo-audio-bridge](https://github.com/AslamSys/mordomo-audio-bridge)
- [mordomo-audio-capture-vad](https://github.com/AslamSys/mordomo-audio-capture-vad)
- [mordomo-wake-word-detector](https://github.com/AslamSys/mordomo-wake-word-detector)
- [mordomo-speaker-verification](https://github.com/AslamSys/mordomo-speaker-verification)
- [mordomo-speaker-id-diarization](https://github.com/AslamSys/mordomo-speaker-id-diarization)
- [mordomo-source-separation](https://github.com/AslamSys/mordomo-source-separation)
- [mordomo-core-gateway](https://github.com/AslamSys/mordomo-core-gateway)
- [mordomo-orchestrator](https://github.com/AslamSys/mordomo-orchestrator)
- [mordomo-brain](https://github.com/AslamSys/mordomo-brain)
- [mordomo-tts-engine](https://github.com/AslamSys/mordomo-tts-engine)
- [mordomo-system-watchdog](https://github.com/AslamSys/mordomo-system-watchdog)
- [mordomo-dashboard-ui](https://github.com/AslamSys/mordomo-dashboard-ui)
- [mordomo-openclaw-agent](https://github.com/AslamSys/mordomo-openclaw-agent)
- [mordomo-action-dispatcher](https://github.com/AslamSys/mordomo-action-dispatcher)
- [mordomo-skills-runner](https://github.com/AslamSys/mordomo-skills-runner)

---
RUN apt-get install -y python3 python3-pip && \
    pip3 install grpcio grpcio-tools pynats

WORKDIR /app
COPY src/ ./src/
COPY --from=0 /build/whisper.cpp/models/ ./models/

EXPOSE 50051 8002

CMD ["python3", "src/server.py"]
```

---

## 🚀 Status do Projeto

✅ **Ambiente configurado**
- Python 3.13 com venv
- faster-whisper instalado e testado
- Modelo Whisper tiny validado (transcrição PT-BR funcionando)

🔄 **Próximos passos**
1. Implementar serviço principal (`src/server.py`)
2. Integração ZeroMQ (consumir áudio do VAD)
3. Integração NATS (eventos e streaming)
4. Implementação do gate (BUFFERING → TRANSCRIBING)
5. Integração gRPC com Speaker ID
6. Métricas Prometheus
7. Containerização Docker

---

**Versão:** 1.0 (em desenvolvimento)
