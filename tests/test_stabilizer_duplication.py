
import unittest
from typing import List, Dict
import time
from voice_translate.asr.stabilizer import Stabilizer
from voice_translate.models import AsrHypothesis, StableUpdate

class TestStabilizerDuplication(unittest.TestCase):
    def test_duplication_avoidance(self):
        stabilizer = Stabilizer()
        
        # timestamps
        t0 = 1000.0
        
        # 1. First hypothesis: "Hello world."
        words1 = [
            {'word': 'Hello', 'start': t0 + 0.1, 'end': t0 + 0.5, 'probability': 0.9},
            {'word': ' world', 'start': t0 + 0.6, 'end': t0 + 1.0, 'probability': 0.9},
            {'word': '.', 'start': t0 + 1.0, 'end': t0 + 1.1, 'probability': 0.9},
        ]
        hyp1 = AsrHypothesis(ts=t0+1.2, words=words1, text="Hello world.", language="en")
        
        # Process hyp1. Should detect "." and finalize "Hello world."
        # We need to simulate time passing or force it?
        # The code checks for punctuation in `stable_words`.
        # `process` appends words to `stable_words` if they are older than lag?
        # No, my simplified logic just checks `start > last_stable_ts`.
        # Wait, the code still has:
        # `cutoff_time = current_time - cfg.stability_lag_s`
        # `if w['end'] < cutoff_time: candidates.append(w)`
        
        # So I need to mock `cfg.stability_lag_s` or set current_time large enough.
        # But `process` uses `time.time()`.
        # I can't easily mock `time.time()` inside `stabilizer.py` without patching.
        # However, `process` uses `current_time` only for cutoff calculation.
        # If I set `cfg.stability_lag_s` to 0 temporarily?
        
        from voice_translate.config import cfg
        orig_lag = cfg.stability_lag_s
        cfg.stability_lag_s = 0.0 # Make everything stable immediately
        
        try:
            update1 = stabilizer.process(hyp1)
            
            # Should have finalized segment "Hello world."
            self.assertEqual(len(update1.completed_segments), 1)
            self.assertEqual(update1.completed_segments[0].src_text, "Hello world.")
            
            # `stable_words` should be empty now
            self.assertEqual(len(stabilizer.stable_words), 0)
            
            # Check last_finalized_end_ts
            self.assertAlmostEqual(stabilizer.last_finalized_end_ts, 1000.0 + 1.1)
            
            # 2. Second hypothesis: "Hello world. How are"
            # Overlapping window, still contains "Hello world."
            words2 = list(words1) + [
                {'word': ' How', 'start': t0 + 1.2, 'end': t0 + 1.5, 'probability': 0.9},
                {'word': ' are', 'start': t0 + 1.6, 'end': t0 + 1.9, 'probability': 0.9},
            ]
            hyp2 = AsrHypothesis(ts=t0+2.0, words=words2, text="Hello world. How are", language="en")
            
            update2 = stabilizer.process(hyp2)
            
            # Should NOT finalize "Hello world." again
            self.assertEqual(len(update2.completed_segments), 0)
            
            # Should add " How are" to stable words (since lag=0)
            self.assertEqual(update2.stable_text, " How are")
            self.assertEqual(len(stabilizer.stable_words), 2)
            self.assertEqual(stabilizer.stable_words[0]['word'], ' How')
            
            # 3. Finalize on speech end
            # Should NOT add "Hello world." again from last_hypothesis (which is hyp2)
            # hyp2 has "Hello world. How are".
            segment = stabilizer.finalize()
            
            # Should contain ONLY " How are" (plus any remaining)
            # "Hello world." starts before last_finalized_end_ts, so it should be skipped.
            self.assertEqual(segment.src_text, " How are")
            
        finally:
            cfg.stability_lag_s = orig_lag

    def test_skip_near_overlapping_repeated_word(self):
        stabilizer = Stabilizer()
        t0 = 2000.0

        from voice_translate.config import cfg
        orig_lag = cfg.stability_lag_s
        cfg.stability_lag_s = 0.0

        try:
            # "עכשיו" appears twice with overlapping timing (common overlap artifact).
            words = [
                {'word': ' עכשיו', 'start': t0 + 0.10, 'end': t0 + 0.40, 'probability': 0.9},
                {'word': ' עכשיו', 'start': t0 + 0.46, 'end': t0 + 0.70, 'probability': 0.9},
                {'word': '.', 'start': t0 + 0.72, 'end': t0 + 0.78, 'probability': 0.9},
            ]
            hyp = AsrHypothesis(ts=t0 + 0.9, words=words, text=" עכשיו עכשיו.", language="he")

            update = stabilizer.process(hyp)
            self.assertEqual(len(update.completed_segments), 1)
            self.assertEqual(update.completed_segments[0].src_text, " עכשיו.")
        finally:
            cfg.stability_lag_s = orig_lag

if __name__ == '__main__':
    unittest.main()
