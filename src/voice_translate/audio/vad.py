import onnxruntime
import numpy as np
import collections
from typing import List, Optional
from dataclasses import dataclass
import time
import os

from voice_translate.config import cfg

@dataclass
class VadEvent:
    ts: float
    event_type: str  # "speech_start", "speech_end"

class Vad:
    def __init__(self, aggressiveness=2, sample_rate=16000):
        self.sample_rate = sample_rate
        self.frame_size = 512 
        self.frame_duration_ms = (self.frame_size / self.sample_rate) * 1000.0
        
        # Audio buffer
        self.buffer = np.array([], dtype=np.float32)
        
        # RMS Threshold for speech activity
        # Digital loopback is very clean. 0.005 is usually good.
        self.threshold = 0.005

    def process_chunk(self, float_chunk: np.ndarray) -> List[bool]:
        """
        Process a chunk of float32 audio.
        Returns a list of booleans (is_speech) corresponding to frames found in the chunk.
        """
        if float_chunk.dtype != np.float32:
            float_chunk = float_chunk.astype(np.float32)
            
        self.buffer = np.concatenate((self.buffer, float_chunk))
        
        results = []
        
        while len(self.buffer) >= self.frame_size:
            chunk = self.buffer[:self.frame_size]
            self.buffer = self.buffer[self.frame_size:]
            
            # Simple RMS calculation
            rms = np.sqrt(np.mean(chunk**2))
            
            is_speech = rms > self.threshold
            
            # Optional debug for tuning
            if is_speech:
                 # print(f"[VAD] RMS Activity: {rms:.4f}")
                 pass
            
            results.append(is_speech)
            
        return results


class PauseDetector:
    def __init__(self):
        self.vad = Vad(aggressiveness=cfg.vad_aggressiveness, sample_rate=cfg.target_rate)
        
        # State
        self.triggered = False
        self.speech_start_ts = 0.0
        
        # Frame counters
        self.num_voiced = 0
        self.num_silence = 0
        
        # Limits in frames
        # Use actual frame duration from VAD
        self.frame_duration_ms = self.vad.frame_duration_ms
        
        self.min_speech_frames = int(cfg.min_speech_ms / self.frame_duration_ms)
        self.min_silence_frames = int(cfg.min_silence_ms / self.frame_duration_ms)
        
    def process(self, chunk: np.ndarray, chunk_start_ts: float) -> List[VadEvent]:
        events = []
        
        frame_duration_s = self.frame_duration_ms / 1000.0
        
        vad_results = self.vad.process_chunk(chunk)
        
        # Approximate timestamp: start at chunk_start_ts
        # Note: chunk processing might have buffered data from PREVIOUS chunks
        # which means the events generated now correspond to PAST time or current time?
        # Silero VAD buffer is small (32ms). 
        # Ideally we track time more precisely, but for real-time app, 
        # emitting events with 'current' time relative to chunk_start is okay.
        
        current_ts = chunk_start_ts
        
        for is_speech in vad_results:
            if self.triggered:
                if is_speech:
                    self.num_silence = 0
                else:
                    self.num_silence += 1
                    
                if self.num_silence > self.min_silence_frames:
                     # Speech ended
                     self.triggered = False
                     events.append(VadEvent(ts=current_ts, event_type="speech_end"))
                     self.num_silence = 0
            else:
                if is_speech:
                    self.num_voiced += 1
                else:
                    self.num_voiced = 0
                    
                if self.num_voiced > self.min_speech_frames:
                    # Speech started
                    self.triggered = True
                    # Backtrack timestamp for start
                    start_ts = current_ts - (self.num_voiced * frame_duration_s)
                    events.append(VadEvent(ts=start_ts, event_type="speech_start"))
                    self.num_voiced = 0
            
            current_ts += frame_duration_s
            
        return events
