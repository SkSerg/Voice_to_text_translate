import threading
import queue
import requests
import json
import time

from voice_translate.config import cfg
from voice_translate.models import FinalSegment, TranslationResult
from voice_translate.transcript_store import ts_store

class TranslatorWorker:
    def __init__(self, translation_queue: queue.Queue):
        self.queue = translation_queue
        self.running = False
        self.thread = None
        
        # Cache to avoid re-translating same segments
        self.cache = {} # hash(src_text) -> ru_text
        
    def _run(self):
        while self.running:
            try:
                segment: FinalSegment = self.queue.get(timeout=0.5)
            except queue.Empty:
                continue
                
            if not segment:
                continue
                
            src_text = segment.src_text.strip()
            if not src_text or segment.lang == 'ru':
                # No translation needed
                continue
                
            # Check cache
            text_hash = hash(src_text)
            if text_hash in self.cache:
                # print(f"[Translator] Cache hit: {src_text[:20]}...")
                ts_store.update_translation(segment.segment_id, self.cache[text_hash])
                continue
                
            # Translate
            # print(f"[Translator] Translating: {src_text[:30]}...")
            ru_text = self._translate(src_text, segment.lang)
            
            if ru_text:
                # print(f"[Translator] Result: {ru_text[:30]}...")
                self.cache[text_hash] = ru_text
                ts_store.update_translation(segment.segment_id, ru_text)
    
    def _translate(self, text: str, src_lang: str) -> str:
        prompt = f"<start_of_turn>user\nTranslate the following text from {src_lang or 'auto'} to Russian. Output ONLY the translation, nothing else.\n\n{text}<end_of_turn>\n<start_of_turn>model\n"
        
        data = {
            "model": cfg.translate_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": cfg.translate_temperature,
                "top_p": cfg.translate_top_p
            }
        }
        
        try:
            response = requests.post(f"{cfg.ollama_url}/api/generate", json=data)
            response.raise_for_status()
            result = response.json()
            return result.get("response", "").strip()
        except Exception as e:
            print(f"[Translator] Error: {e}")
            return ""

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()
