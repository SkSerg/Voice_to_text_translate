from dataclasses import dataclass, field
from typing import List, Dict, Optional
import numpy as np

@dataclass
class AudioChunk:
    ts: float            # timestamp of the chunk start
    samples: np.ndarray  # PCM float32 mono 16kHz
    sample_rate: int

@dataclass
class VadEvent:
    ts: float
    event: str           # "speech_start" | "speech_end"

@dataclass
class AsrHypothesis:
    ts: float
    words: List[Dict]    # [{"word": "...", "start": float, "end": float, "probability": float}, ...]
    text: str
    language: str = "auto"

@dataclass
class StableUpdate:
    ts: float
    stable_text: str     # fixed part of the transcription
    unstable_text: str   # active/changing part
    stable_words: List[Dict]
    completed_segments: List['FinalSegment'] = field(default_factory=list)

@dataclass
class FinalSegment:
    segment_id: str      # uuid
    start_ts: float
    end_ts: float
    src_text: str
    lang: str            # ISO 639-1 (en, he, uk, ...)
    words: List[Dict]

@dataclass
class TranslationResult:
    segment_id: str
    ru_text: str
