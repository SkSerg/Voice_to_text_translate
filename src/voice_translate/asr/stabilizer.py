from dataclasses import dataclass, field
from typing import List, Dict, Optional
import time
from voice_translate.models import AsrHypothesis, StableUpdate, FinalSegment
from voice_translate.config import cfg
import uuid
import re

class Stabilizer:
    def __init__(self):
        self.stable_text: str = ""
        self.stable_words: List[Dict] = []
        self.last_hypothesis: Optional[AsrHypothesis] = None
        self.last_finalized_end_ts: float = 0.0
        self.finalized_history: List[str] = []  # Keep history of finalized segments
        self.last_committed_word: Optional[Dict] = None

    @staticmethod
    def _norm_word(word: str) -> str:
        text = word.strip().lower()
        text = re.sub(r"^[^\w]+|[^\w]+$", "", text, flags=re.UNICODE)
        return text

    def _should_skip_near_duplicate(self, word: Dict) -> bool:
        prev = self.stable_words[-1] if self.stable_words else self.last_committed_word
        if not prev:
            return False

        prev_norm = self._norm_word(prev.get("word", ""))
        curr_norm = self._norm_word(word.get("word", ""))
        if not prev_norm or prev_norm != curr_norm:
            return False

        # If the same token appears again with overlapping/near-overlapping timestamps,
        # it is usually a sliding-window duplicate, not real repeated speech.
        return word["start"] <= prev["end"] + 0.12

    def _append_stable_word(self, word: Dict):
        if self._should_skip_near_duplicate(word):
            return
        self.stable_words.append(word)
        self.stable_text += word["word"]

    def get_context_for_prompt(self, max_chars: int = 120, include_live: bool = False) -> str:
        """
        Get recent text context for Whisper's initial_prompt.
        This helps maintain continuity and improve recognition quality.
        """
        # Combine recent finalized history and current stable text
        all_text = " ".join(self.finalized_history[-3:])  # Last 3 finalized segments
        if include_live and self.stable_text:
            all_text += " " + self.stable_text
        
        # Return last max_chars characters
        if len(all_text) > max_chars:
            return all_text[-max_chars:]
        return all_text

    def process(self, hypothesis: AsrHypothesis) -> StableUpdate:
        """
        Input: a new hypothesis from ASR.
        Output: update with current stable/unstable parts.
        """
        current_time = time.time()
        
        # Simple stabilization logic:
        # 1. Wait for stability_lag_s.
        # 2. Words that are "old enough" are candidates.
        # 3. We only confirm words if they match the previous hypothesis's stable candidates?
        # Simpler: just trust words older than lag if they persist?
        # The plan says: "Confirm if matches in 2 last hypotheses".
        
        # Let's say we have current words.
        # Filter words where word.end < current_time - lag
        
        candidates = []
        unstable = []
        
        cutoff_time = current_time - cfg.stability_lag_s
        
        for w in hypothesis.words:
            if w['end'] < cutoff_time:
                candidates.append(w)
            else:
                unstable.append(w)
        
        # Confirmation logic
        # Compare `candidates` with `self.last_hypothesis.candidates`?
        # Or simpler: if `candidates` starts with the same sequence as `self.stable_words` (it should!),
        # then append new stable words.
        
        # Wait, `stable_words` are already fixed. We should only look at extensions.
        # But ASR returns full text (including stable part usually, if we provide prompt? or if we feed full buffer).
        # Faster-whisper usually processes the window. If window shifts, text shifts.
        # WE NEED TO HANDLE WINDOW SHIFTING.
        # If we just feed "last 8 seconds", the text will change.
        # But we want to accumulate `stable_text`.
        # So we must match the *new* hypothesis against *accumulated* stable text?
        # Faster-whisper might re-transcribe the stable part differently.
        # Standard aproach:
        # Prompt the model with `previous_text`.
        # Then the model outputs *continuation*.
        # BUT standard streaming with faster-whisper just decodes window.
        # If we prompt with `stable_text`, we implicitly force it.
        # Let's assume `ASRWorker` handles prompting.
        # Then `hypothesis` contains NEW text (continuation).
        
        # If `ASRWorker` feeds `prompt=stable_text`, then `hypothesis` is just the *new* part?
        # Or does it return full text?
        # Faster-whisper: `initial_prompt` helps context, but output still includes the audio content.
        # However, if we process a *sliding window*, the window moves.
        # The beginning of the window might be cut off.
        # This makes matching hard.
        
        # Plan says: "ASRWorker uses decode window of 8s"
        # And "Stabilizer does pseudo-streaming".
        # Let's assume ASRWorker provides timestamps relative to *stream start* (using cumulative time)?
        # Or relative to window start?
        # If relative to window, we need absolute time.
        # `ASRWorker` MUST map window-relative timestamps to absolute stream timestamps.
        # I will implement `ASRWorker` to provide absolute timestamps.
        
        # So, `hypothesis.words` has absolute timestamps.
        # We check which words are new compared to `self.stable_words`.
        
        # 1. Find where `stable_words` ends in `hypothesis`.
        #    Ideally `hypothesis` starts *after* `stable_words` if we shift window correctly?
        #    No, window overlaps.
        #    So `hypothesis` contains some overlap with `stable_words`.
        #    We need to align.
        
        # Simple alignment: match word text?
        # Or just trust timestamps?
        # If timestamp of new word > timestamp of last stable word.
        
        # Determine where to start adding new words from
        # If we have stable words, start after the last one.
        # If not, ensure we start after the last finalized segment to avoid duplication.
        if self.stable_words:
            last_stable_ts = self.stable_words[-1]['end']
        else:
            last_stable_ts = self.last_finalized_end_ts
        
        # New words: start > last_stable_ts (approx)
        # Ideally we use a small buffer overlap to ensure continuity.
        
        new_candidates = []
        
        for w in candidates:
             # Use end timestamp so boundary words are not dropped when start overlaps prior word.
             if w['end'] > last_stable_ts + 0.02:
                 new_candidates.append(w)
        
        # Now confirmed?
        # Check if `new_candidates` matches `last_hypothesis` candidates?
        # We need `self.last_candidates`.
        
        confirmed_new = []
        
        if self.last_hypothesis:
             # Find common prefix of `new_candidates` and `last_candidates` ??
             # Actually, just taking "older than lag" is often stable enough for "pseudo-streaming".
             # The "2-pass" confirmation is safer.
             # Let's verify against `self.last_hypothesis`
             pass
        
        # For MVP, let's stick to "older than lag" logic + purely timestamp based appending.
        # It's robust enough for "transcription". 
        # Refinement: check if the word content is consistent.
        
        # Let's just append all 'candidates' that are strictly after stable_words.
        # And mark them as stable immediately? 
        # No, "older than lag".
        
        for w in new_candidates:
             self._append_stable_word(w)
             
        # Detect sentence boundary
        # If stable_text ends with ".", "?", "!" or contains them?
        # Because we append words, the punctuation is usually part of the word text like " word."
        
        finalized_segments = []
        
        # Check if stable_text contains sentence separator.
        # But we need to split by words to keep timestamps consistent.
        
        # Simple heuristic: Iterate stable_words, check if word ends with punctuation.
        
        last_cut_idx = -1
        
        for i, w in enumerate(self.stable_words):
             word_text = w['word'].strip()
             if word_text and word_text[-1] in ".?!": # Basic puntuation
                 # Found end of sentence at index i
                 # Extract segment: last_cut_idx+1 to i (inclusive)
                 
                 segment_words = self.stable_words[last_cut_idx+1 : i+1]
                 if not segment_words: 
                     continue
                     
                 segment_text = "".join([sw['word'] for sw in segment_words])
                 
                 seg = FinalSegment(
                    segment_id=str(uuid.uuid4()),
                    start_ts=segment_words[0]['start'],
                    end_ts=segment_words[-1]['end'],
                    src_text=segment_text,
                    lang=hypothesis.language, 
                    words=segment_words
                 )
                 self.last_finalized_end_ts = seg.end_ts
                 finalized_segments.append(seg)
                 
                 # Add to history for context
                 self.finalized_history.append(segment_text.strip())
                 # Keep only last 10 segments in history
                 if len(self.finalized_history) > 10:
                     self.finalized_history = self.finalized_history[-10:]

                 self.last_committed_word = segment_words[-1]
                 
                 last_cut_idx = i
                 
        if last_cut_idx != -1:
             # Remove flushed words
             self.stable_words = self.stable_words[last_cut_idx+1:]
             self.stable_text = "".join([w['word'] for w in self.stable_words]) # rebuild stable text
                 
        # Unstable is directly from hypothesis (words not yet stable)
        
        self.last_hypothesis = hypothesis
        
        unstable_text_str = "".join([w['word'] for w in unstable])
        
        result = StableUpdate(
            ts=current_time,
            stable_text=self.stable_text, # Represents only the NOT YET FINALIZED part
            unstable_text=unstable_text_str,
            stable_words=self.stable_words,
            completed_segments=finalized_segments
        )
        return result

    def finalize(self) -> FinalSegment:
        """Called on speech_end."""
        # Force all unstable to stable?
        # Or just take what we have?
        # Usually on speech_end we want to finalize everything.
        
        # If there are unstable words, assume they are correct now?
        # Or do one last decode with larger beam?
        # For simplicity: take last hypothesis, make everything stable.
        
        if self.last_hypothesis:
             # Add remaining words
             if self.stable_words:
                 last_stable_ts = self.stable_words[-1]['end']
             else:
                 last_stable_ts = self.last_finalized_end_ts
            
             for w in self.last_hypothesis.words:
                 if w['end'] > last_stable_ts + 0.02:
                     self._append_stable_word(w)
        
        seg = FinalSegment(
            segment_id=str(uuid.uuid4()),
            start_ts=self.stable_words[0]['start'] if self.stable_words else 0.0,
            end_ts=self.stable_words[-1]['end'] if self.stable_words else 0.0,
            src_text=self.stable_text,
            lang=self.last_hypothesis.language if self.last_hypothesis else "auto",
            words=self.stable_words
        )
        
        # Reset
        self.reset()
        return seg

    def reset(self):
        self.stable_text = ""
        self.stable_words = []
        self.last_hypothesis = None
        self.last_finalized_end_ts = 0.0
        # Don't reset finalized_history / last_committed_word - keep continuity across speech segments
