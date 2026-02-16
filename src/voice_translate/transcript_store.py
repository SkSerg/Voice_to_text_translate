from dataclasses import dataclass, field
from typing import List, Dict, Optional
import threading
from pathlib import Path
from datetime import datetime
import os
from voice_translate.models import FinalSegment, TranslationResult

@dataclass
class TranscriptItem:
    segment: FinalSegment
    translation: Optional[TranslationResult] = None

@dataclass
class MarkdownSession:
    session_id: str
    started_at: datetime
    original_path: Path
    translation_path: Path

class TranscriptStore:
    def __init__(self):
        self.segments: List[TranscriptItem] = []
        self.lock = threading.Lock()
        self.current_session_id: Optional[str] = None
        self.sessions: Dict[str, MarkdownSession] = {}
        self.segment_to_session: Dict[str, str] = {}
        
        # Live state for display
        self.live_stable: str = ""
        self.live_unstable: str = ""
        self.live_translation: str = "" # Partial translation if any?

    def _get_documents_dir(self) -> Path:
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
            ) as key:
                docs, _ = winreg.QueryValueEx(key, "Personal")
                docs = os.path.expandvars(docs)
                return Path(docs)
        except Exception:
            pass
        return Path.home() / "Documents"

    def _make_unique_session_paths(self, base_dir: Path, started_at: datetime) -> tuple[Path, Path]:
        stamp = started_at.strftime("%Y-%m-%d_%H-%M")
        idx = 0
        while True:
            suffix = "" if idx == 0 else f"_{idx:02d}"
            original = base_dir / f"{stamp}{suffix}_original.md"
            translation = base_dir / f"{stamp}{suffix}_translation.md"
            if not original.exists() and not translation.exists():
                return original, translation
            idx += 1

    def start_markdown_session(self):
        with self.lock:
            base_dir = self._get_documents_dir() / "Voice_to_translate"
            base_dir.mkdir(parents=True, exist_ok=True)

            started_at = datetime.now()
            original_path, translation_path = self._make_unique_session_paths(base_dir, started_at)
            session_id = started_at.strftime("%Y%m%d%H%M%S%f")

            session = MarkdownSession(
                session_id=session_id,
                started_at=started_at,
                original_path=original_path,
                translation_path=translation_path,
            )
            self.sessions[session_id] = session
            self.current_session_id = session_id

            started_label = started_at.strftime("%Y-%m-%d %H:%M")
            original_path.write_text(
                f"# Original Transcript\n\nStarted: {started_label}\n\n",
                encoding="utf-8",
            )
            translation_path.write_text(
                f"# Translation\n\nStarted: {started_label}\n\n",
                encoding="utf-8",
            )
            print(f"[STORE] Session started: {original_path}")
            print(f"[STORE] Session started: {translation_path}")

    def stop_markdown_session(self):
        with self.lock:
            self.current_session_id = None

    def _append_original(self, session: MarkdownSession, segment: FinalSegment):
        ts = datetime.fromtimestamp(segment.start_ts).strftime("%H:%M:%S")
        text = segment.src_text.strip()
        if not text:
            return
        with session.original_path.open("a", encoding="utf-8") as f:
            f.write(f"- [{ts}] {text}\n")

    def _append_translation(self, session: MarkdownSession, ru_text: str, segment: Optional[FinalSegment]):
        if not ru_text.strip():
            return
        if segment:
            ts = datetime.fromtimestamp(segment.start_ts).strftime("%H:%M:%S")
        else:
            ts = datetime.now().strftime("%H:%M:%S")
        with session.translation_path.open("a", encoding="utf-8") as f:
            f.write(f"- [{ts}] {ru_text.strip()}\n")
    
    def add_segment(self, segment: FinalSegment):
        with self.lock:
            self.segments.append(TranscriptItem(segment=segment))
            if self.current_session_id and self.current_session_id in self.sessions:
                session = self.sessions[self.current_session_id]
                self.segment_to_session[segment.segment_id] = session.session_id
                self._append_original(session, segment)
            
    def update_translation(self, segment_id: str, ru_text: str):
        with self.lock:
            segment_obj: Optional[FinalSegment] = None
            for item in self.segments:
                if item.segment.segment_id == segment_id:
                    item.translation = TranslationResult(segment_id=segment_id, ru_text=ru_text)
                    segment_obj = item.segment
                    break

            session_id = self.segment_to_session.get(segment_id, self.current_session_id)
            if session_id and session_id in self.sessions:
                session = self.sessions[session_id]
                self._append_translation(session, ru_text, segment_obj)
            
    def update_live(self, stable: str, unstable: str):
        with self.lock:
            self.live_stable = stable
            self.live_unstable = unstable
            
    def get_latest(self, n=5) -> List[TranscriptItem]:
        with self.lock:
            return self.segments[-n:]
            
ts_store = TranscriptStore()
