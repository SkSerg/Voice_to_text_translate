import time
import threading
from datetime import timedelta
from voice_translate.transcript_store import ts_store
from voice_translate.config import cfg

class VttWriter:
    def __init__(self):
        self.path = cfg.vtt_path
        self.running = False
        self.thread = None
        
    def _format_time(self, seconds: float) -> str:
        # VTT time format: HH:MM:SS.mmm
        # But for live VTT, timestamps are relative to stream start or wall clock?
        # Standard VTT uses 00:00:00.000 relative to file start.
        # Live VTT usually refreshes content.
        # We can use large duration for the "current" cue to make it stick.
        # Or just update file content repeatedly.
        # ObS "Text (GDI+)" reads file content directly, ignoring timestamps if not using "Subtitle Source".
        # If using "Browser Source" with a player, timestamps matter.
        # But plan says: "Text (from file)". This means it just displays the TEXT in the file.
        # So we don't need valid VTT format for Text Source?
        # "OBS Text Source" reads raw text.
        # "VLC" needs VTT.
        # Let's support both or just VTT.
        # Plan says: "live.vtt (for OBS/VLC)".
        # Valid VTT:
        # WEBVTT
        # 
        # 00:00:00.000 --> 99:59:59.999
        # content
        
        return "00:00:00.000"

    def _run(self):
        while self.running:
            try:
                # Build content
                lines = []
                
                # History (last 2 segments?)
                segments = ts_store.get_latest(n=2)
                for item in segments:
                    # Original + Translation
                    text = item.segment.src_text
                    if item.translation:
                         text += f"\n{item.translation.ru_text}"
                    lines.append(text)
                
                # Live
                live_text = ts_store.live_stable + ts_store.live_unstable
                if live_text.strip():
                     lines.append(f"LIVE: {live_text}")
                
                content = "\n\n".join(lines)
                
                # Write VTT valid structure if needed, or just text?
                # For OBS Text GDI+, just text is best.
                # But file extension .vtt implies VTT.
                # Let's write valid VTT with a single long cue containing the text.
                
                vtt_content = "WEBVTT\n\n00:00:00.000 --> 99:59:59.999\n" + content
                
                with open(self.path, "w", encoding="utf-8") as f:
                    f.write(vtt_content)
                    
            except Exception as e:
                print(f"VTT Write Error: {e}")
                
            time.sleep(cfg.vtt_update_interval_s)

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()
