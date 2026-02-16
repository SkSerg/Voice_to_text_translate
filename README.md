# Voice Translate

Real-time system audio transcription (WASAPI loopback), translation via Ollama, and output to overlay/VTT.

## Project Structure

```text
.
├─ main.py                         # Entry point
├─ requirements.txt
├─ .env.example
├─ assets/
│  └─ silero_vad.onnx
├─ src/
│  └─ voice_translate/
│     ├─ app.py                    # Thread/hotkey orchestration
│     ├─ config.py                 # Config loaded from .env
│     ├─ models.py                 # Dataclass models
│     ├─ ring_buffer.py
│     ├─ transcript_store.py       # Store + markdown sessions
│     ├─ audio/
│     │  ├─ capture.py
│     │  └─ vad.py
│     ├─ asr/
│     │  ├─ worker.py
│     │  └─ stabilizer.py
│     ├─ translation/
│     │  └─ ollama_worker.py
│     ├─ output/
│     │  └─ vtt_writer.py
│     └─ ui/
│        └─ overlay.py
└─ tests/
   ├─ test_capture.py
   └─ test_stabilizer_duplication.py
```

## Installation

Ollama must be installed for translation features to work.
Official installation page: `https://ollama.com/download`

```powershell
python -m venv .venv
.\.venv\Scripts\activate
.\.venv\Scripts\python -m pip install -r requirements.txt
```

## Configuration

1. Copy the template:

```powershell
Copy-Item .env.example .env
```

2. Key `.env` parameters:
- `ASR_MODEL` (`small|medium|large-v3`)
- `ASR_DEVICE` (`cuda|cpu`)
- `OLLAMA_URL`
- `TRANSLATE_MODEL`
- `HOTKEY_TOGGLE` (default: `f8`)
- `HOTKEY_STOP` (default: `f10`)

## Run

```powershell
.\.venv\Scripts\python main.py
```

## Controls

- `F8` (`HOTKEY_TOGGLE`) — start/pause transcription
- `F10` (`HOTKEY_STOP`) — full app shutdown

## Markdown Output

When a session starts (`F8` from pause), files are created:

- `Documents\Voice_to_translate\YYYY-MM-DD_HH-MM_original.md`
- `Documents\Voice_to_translate\YYYY-MM-DD_HH-MM_translation.md`

Filenames contain the session start time with minute precision.

## Tests

```powershell
.\.venv\Scripts\python -m unittest tests.test_stabilizer_duplication
```

## Notes

- Global hotkeys on Windows may require running the terminal as Administrator.
- If F-keys are reserved by your system/keyboard, set custom combos (for example, `ctrl+alt+s`) in `.env`.
