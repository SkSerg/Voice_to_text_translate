from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Config:
    # --- Audio Capture ---
    capture_channels: int = 2
    capture_rate: int = 44100
    target_rate: int = 16000
    capture_blocksize: int = 1024
    capture_device: str | None = os.getenv("CAPTURE_DEVICE", None)
    capture_gain: float = float(os.getenv("CAPTURE_GAIN", "1.0"))
    
    # --- VAD ---
    vad_aggressiveness: int = 2
    vad_frame_ms: int = 20
    min_silence_ms: int = 900
    min_speech_ms: int = 250
    
    # --- ASR ---
    asr_model: str = os.getenv("ASR_MODEL", "large-v3")
    asr_device: str = os.getenv("ASR_DEVICE", "cuda")
    asr_compute_type: str = os.getenv("ASR_COMPUTE_TYPE", "float16")
    decode_window_s: float = 8.0
    update_interval_s: float = 0.35
    stability_lag_s: float = 1.5
    asr_language: str | None = None
    asr_word_timestamps: bool = True
    asr_vad_filter: bool = False
    asr_condition_on_previous_text: bool = os.getenv("ASR_CONDITION_ON_PREVIOUS_TEXT", "false").lower() == "true"
    
    # Quality settings for better transcription
    asr_beam_size_streaming: int = int(os.getenv("ASR_BEAM_SIZE_STREAMING", "3"))  # Higher = better quality but slower
    asr_beam_size_final: int = int(os.getenv("ASR_BEAM_SIZE_FINAL", "5"))
    asr_min_word_probability: float = float(os.getenv("ASR_MIN_WORD_PROB", "0.15"))  # Lower threshold keeps more borderline-correct words
    asr_min_word_probability_final: float = float(os.getenv("ASR_MIN_WORD_PROB_FINAL", "0.0"))  # Do not drop words on final pass
    asr_repetition_penalty: float = float(os.getenv("ASR_REPETITION_PENALTY", "1.08"))
    asr_no_repeat_ngram_size: int = int(os.getenv("ASR_NO_REPEAT_NGRAM_SIZE", "3"))
    asr_hallucination_silence_threshold: float = float(os.getenv("ASR_HALLUCINATION_SILENCE_THRESHOLD", "0.35"))
    asr_initial_prompt_max_chars: int = int(os.getenv("ASR_INITIAL_PROMPT_MAX_CHARS", "120"))
    asr_temperature: float = 0.0  # Deterministic decoding
    asr_compression_ratio_threshold: float = 2.4  # Detect repetitions
    asr_log_prob_threshold: float = -1.0  # Filter low-quality segments
    asr_no_speech_threshold: float = 0.6  # Detect silence
    
    # --- Translation ---
    ollama_url: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
    translate_model: str = os.getenv("TRANSLATE_MODEL", "translategemma:12b")
    translate_temperature: float = 0.0
    translate_top_p: float = 1.0
    
    # --- Output ---
    vtt_path: str = "live.vtt"
    vtt_update_interval_s: float = 0.3
    overlay_enabled: bool = True
    terminal_output: bool = True
    
    # --- Ring Buffer ---
    ring_buffer_duration_s: float = 30.0

    # --- Hotkeys ---
    hotkey_toggle: str = os.getenv("HOTKEY_TOGGLE", os.getenv("HOTKEY_START", "f8"))
    hotkey_stop: str = os.getenv("HOTKEY_STOP", "f10")

# Global instance
cfg = Config()
