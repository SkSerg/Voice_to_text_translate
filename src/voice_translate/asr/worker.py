import threading
import time
import queue
import numpy as np
from faster_whisper import WhisperModel
import os

from voice_translate.config import cfg
from voice_translate.ring_buffer import RingBuffer
from voice_translate.asr.stabilizer import Stabilizer
from voice_translate.models import AsrHypothesis, VadEvent, FinalSegment, StableUpdate
from voice_translate.transcript_store import ts_store

class AsrWorker:
    def __init__(self, ring_buffer: RingBuffer, vad_queue: queue.Queue, translation_queue: queue.Queue):
        self.ring_buffer = ring_buffer
        self.vad_queue = vad_queue
        self.translation_queue = translation_queue
        
        self.running = False
        self.thread = None
        
        self.model = None
        self.stabilizer = Stabilizer()
        self.paused = True
        self.pause_lock = threading.Lock()
        self.control_queue: queue.Queue[str] = queue.Queue()
        
        self.is_speech_active = False
        self.speech_start_ts = 0.0
        
    def _load_model(self):
        print(f"Loading Whisper model: {cfg.asr_model} on {cfg.asr_device}...")
        try:
            self.model = WhisperModel(
                cfg.asr_model, 
                device=cfg.asr_device, 
                compute_type=cfg.asr_compute_type
            )
            print("Model loaded.")
        except Exception as e:
            print(f"Failed to load model: {e}")
            raise e

    def _run(self):
        self._load_model()
        
        while self.running:
            self._apply_control_commands()

            if self.is_paused():
                self._sync_vad_state_only()
                time.sleep(0.05)
                continue

            # Check VAD events
            self._process_vad_events_with_finalize()
            
            # Decoding loop
            if self.is_speech_active:
                start_time = time.time()
                self._decode_step()
                
                # Sleep rest of interval
                elapsed = time.time() - start_time
                sleep_time = max(0.0, cfg.update_interval_s - elapsed)
                time.sleep(sleep_time)
            else:
                time.sleep(0.05) # Idle wait

    def _drain_vad_events(self):
        try:
            while True:
                self.vad_queue.get_nowait()
        except queue.Empty:
            pass

    def _set_paused_internal(self, value: bool):
        with self.pause_lock:
            self.paused = value

    def _apply_control_commands(self):
        try:
            while True:
                cmd = self.control_queue.get_nowait()
                if cmd == "resume":
                    self._set_paused_internal(False)
                    self.stabilizer.reset()
                    print("[ASR] Transcription resumed")
                elif cmd == "pause":
                    self._set_paused_internal(True)
                    self.stabilizer.reset()
                    ts_store.update_live("", "")
                    print("[ASR] Transcription paused")
                elif cmd == "toggle":
                    if self.is_paused():
                        self._set_paused_internal(False)
                        self.stabilizer.reset()
                        print("[ASR] Transcription resumed")
                    else:
                        self._set_paused_internal(True)
                        self.stabilizer.reset()
                        ts_store.update_live("", "")
                        print("[ASR] Transcription paused")
        except queue.Empty:
            pass

    def _sync_vad_state_only(self):
        """Process VAD queue to keep speech activity state current without finalizing segments."""
        try:
            while True:
                event: VadEvent = self.vad_queue.get_nowait()
                if event.event_type == "speech_start":
                    if not self.is_speech_active:
                        self.is_speech_active = True
                        self.speech_start_ts = event.ts
                elif event.event_type == "speech_end":
                    if self.is_speech_active:
                        self.is_speech_active = False
        except queue.Empty:
            pass

    def _process_vad_events_with_finalize(self):
        """Finalize segments on speech_end while ASR is running."""
        try:
            while True:
                event: VadEvent = self.vad_queue.get_nowait()
                if event.event_type == "speech_start":
                    if not self.is_speech_active:
                        self.is_speech_active = True
                        self.speech_start_ts = event.ts
                        print(f"[ASR] Speech started at {event.ts:.2f}")
                        self.stabilizer.reset()
                elif event.event_type == "speech_end":
                    if self.is_speech_active:
                        self.is_speech_active = False
                        print(f"[ASR] Speech ended at {event.ts:.2f}")
                        self._decode_step(final=True)
                        seg = self.stabilizer.finalize()
                        if seg.src_text.strip():
                            print(f"[ASR] Final Segment: {seg.src_text}")
                            ts_store.add_segment(seg)
                            if seg.lang != 'ru' and cfg.translate_model:
                                self.translation_queue.put(seg)
        except queue.Empty:
            pass

    def is_paused(self) -> bool:
        with self.pause_lock:
            return self.paused

    def resume_transcription(self):
        self.control_queue.put("resume")

    def pause_transcription(self):
        self.control_queue.put("pause")

    def toggle_transcription(self):
        self.control_queue.put("toggle")

    def _decode_step(self, final=False):
        # Get audio from buffer
        # Use last N seconds
        window_size_samples = int(cfg.decode_window_s * cfg.target_rate)
        audio = self.ring_buffer.get_last_n_samples(window_size_samples)
        
        if len(audio) < 16000: # ignore very short
            return

        # Prepare for whisper
        # Normalize? faster-whisper handles float32 normalized to -1..1
        
        # Transcribe
        # timestamps relative to beginning of 'audio'
        # We need absolute timestamps.
        # Assume audio ends at 'now'?
        # Yes, get_last_n_samples returns *most recent*.
        # So audio_end_ts = time.time()
        # audio_start_ts = audio_end_ts - (len(audio)/rate)
        
        audio_end_ts = time.time()
        audio_start_ts = audio_end_ts - (len(audio) / cfg.target_rate)
        
        # Get context from stabilizer for better continuity
        initial_prompt = self.stabilizer.get_context_for_prompt(
            max_chars=cfg.asr_initial_prompt_max_chars,
            include_live=final
        )
        
        # Use better parameters for quality transcription
        segments, info = self.model.transcribe(
            audio,
            language=cfg.asr_language,
            task="transcribe",
            beam_size=cfg.asr_beam_size_final if final else cfg.asr_beam_size_streaming,
            word_timestamps=True,
            vad_filter=cfg.asr_vad_filter,  # False, we use own VAD
            temperature=cfg.asr_temperature,  # Deterministic decoding for better quality
            compression_ratio_threshold=cfg.asr_compression_ratio_threshold,  # Helps detect repetitions
            log_prob_threshold=cfg.asr_log_prob_threshold,  # Filters low-quality segments
            no_speech_threshold=cfg.asr_no_speech_threshold,  # Detects silence
            condition_on_previous_text=cfg.asr_condition_on_previous_text,
            initial_prompt=initial_prompt,  # Add context from previous text
            repetition_penalty=cfg.asr_repetition_penalty,
            no_repeat_ngram_size=cfg.asr_no_repeat_ngram_size,
            hallucination_silence_threshold=cfg.asr_hallucination_silence_threshold,
            
        )
        
        # Collect words
        words = []
        full_text = ""
        
        min_word_prob = cfg.asr_min_word_probability_final if final else cfg.asr_min_word_probability

        for seg in segments:
            full_text += seg.text
            if seg.words:
                for w in seg.words:
                    # Keep all words on final pass to avoid losing valid low-confidence boundaries.
                    if w.probability >= min_word_prob:
                        words.append({
                            "word": w.word,
                            "start": audio_start_ts + w.start,
                            "end": audio_start_ts + w.end,
                            "probability": w.probability
                        })
        
        # Send to stabilizer
        hyp = AsrHypothesis(
            ts=time.time(),
            words=words,
            text=full_text,
            language=info.language
        )
        
        update = self.stabilizer.process(hyp)
        
        # Handle finalized segments from Stabilizer (partial flush)
        if update.completed_segments:
             for seg in update.completed_segments:
                 # Update language if available from model? 
                 # Faster-whisper info has language. 
                 # But segments are created in stabilizer without knowledge of "info".
                 # We can assume "auto" or pass it?
                 # ideally we pass 'info.language' to stabilizer process()
                 pass
                 
                 # print(f"[ASR] Finalized Sentence: {seg.src_text}")
                 ts_store.add_segment(seg)
                 if cfg.translate_model:
                      self.translation_queue.put(seg)
        
        # Update live store (stable_text is now only the REMAINING part)
        ts_store.update_live(update.stable_text, update.unstable_text)
        
        # Display logic to avoid terminal mess
        # visible_stable = update.stable_text[-50:]
        # if len(update.stable_text) > 50:
        #     visible_stable = "..." + visible_stable
            
        # print(f"\r[Live] {visible_stable} | {update.unstable_text}" + " " * 10, end="", flush=True)

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()
