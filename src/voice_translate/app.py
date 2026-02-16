import sys
import threading
import queue
import time
import signal
import os
import argparse
import keyboard

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

from voice_translate.config import cfg
from voice_translate.ring_buffer import RingBuffer
from voice_translate.audio.capture import AudioCapture
from voice_translate.audio.vad import PauseDetector
from voice_translate.asr.worker import AsrWorker
from voice_translate.translation.ollama_worker import TranslatorWorker
from voice_translate.output.vtt_writer import VttWriter
from voice_translate.ui.overlay import OverlayWindow
from voice_translate.transcript_store import ts_store

# Global stop event
stop_event = threading.Event()
hotkeys_registered = False

def register_hotkeys(asr: AsrWorker, app: QApplication | None):
    global hotkeys_registered
    if hotkeys_registered:
        return

    last_trigger: dict[str, float] = {"toggle": 0.0, "stop": 0.0}

    def _debounced(name: str, interval_s: float = 0.35) -> bool:
        now = time.time()
        if now - last_trigger[name] < interval_s:
            return False
        last_trigger[name] = now
        return True

    def on_toggle():
        if not _debounced("toggle"):
            return
        if asr.is_paused():
            try:
                ts_store.start_markdown_session()
            except Exception as e:
                print(f"[STORE] Failed to start markdown session: {e}")
        else:
            ts_store.stop_markdown_session()
        asr.toggle_transcription()

    def on_stop():
        if not _debounced("stop"):
            return
        print("[HOTKEY] Full stop requested")
        ts_store.stop_markdown_session()
        stop_event.set()

    try:
        keyboard.add_hotkey(cfg.hotkey_toggle, on_toggle)
        keyboard.add_hotkey(cfg.hotkey_stop, on_stop)
    except Exception as e:
        print(f"[HOTKEY] Registration failed: {e}")
        return
    hotkeys_registered = True
    print(f"Hotkeys registered: TOGGLE={cfg.hotkey_toggle.upper()} STOP={cfg.hotkey_stop.upper()}")

def unregister_hotkeys():
    global hotkeys_registered
    if hotkeys_registered:
        keyboard.unhook_all_hotkeys()
        hotkeys_registered = False

def vad_thread_func(audio_queue: queue.Queue, event_queue: queue.Queue):
    print("VAD Thread started")
    detector = PauseDetector()
    
    # We need to sync timestamps with real time for ASR.
    # ASR uses time.time().
    # So we should use time.time() for events too.
    # But buffering adds latency.
    # Let's use simple time.time() when processing chunk.
    # It's slight approximation but consistent with ASR which also uses time.time().
    
    while not stop_event.is_set():
        try:
            chunk = audio_queue.get(timeout=1.0)
            
            current_ts = time.time() 
            # ideally subtract chunk_duration to get start time
            # chunk_duration = len(chunk) / 16000
            # start_ts = current_ts - chunk_duration
            # But let's pass current_ts as "end of chunk" or "approx time".
            # PauseDetector expects "chunk_start_ts"?
            # Let's look at PauseDetector logic:
            # events.append(VadEvent(ts=current_ts..., event_type="speech_start"))
            # It uses the passed ts as recursive base.
            
            chunk_duration = len(chunk) / cfg.target_rate
            vals = detector.process(chunk, current_ts - chunk_duration)
            
            for v in vals:
                event_queue.put(v)
                
        except queue.Empty:
            continue
        except Exception as e:
            print(f"VAD Error: {e}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-overlay", action="store_true", help="Disable overlay UI")
    args = parser.parse_args()

    # 1. Setup Queues
    vad_audio_queue = queue.Queue()
    vad_event_queue = queue.Queue()
    translation_queue = queue.Queue()
    
    # 2. Setup RingBuffer
    rb = RingBuffer(size_samples=int(cfg.target_rate * cfg.ring_buffer_duration_s))
    
    # 3. Setup Components
    capture = AudioCapture(rb, vad_audio_queue)
    asr = AsrWorker(rb, vad_event_queue, translation_queue)
    translator = TranslatorWorker(translation_queue)
    vtt = VttWriter()
    
    # 4. Start Threads
    
    # VAD
    vad_thread = threading.Thread(target=vad_thread_func, args=(vad_audio_queue, vad_event_queue), daemon=True)
    vad_thread.start()
    
    # ASR
    asr.start()
    
    # Translator
    translator.start()
    
    # VTT
    vtt.start()
    
    # Capture (starts stream)
    try:
        capture.start()
    except Exception as e:
        print(f"Failed to start capture: {e}")
        return

    print("System started. Use hotkeys to control transcription.")

    # 5. UI or Wait Loop
    app = None
    if cfg.overlay_enabled and not args.no_overlay:
        app = QApplication(sys.argv)
        overlay = OverlayWindow()
        overlay.show()

        register_hotkeys(asr, app)

        # Poll stop_event from Qt thread to guarantee clean shutdown on hotkey stop.
        stop_timer = QTimer()
        stop_timer.timeout.connect(lambda: app.quit() if stop_event.is_set() else None)
        stop_timer.start(100)
        
        # Handle Ctrl+C in Qt
        signal.signal(signal.SIGINT, lambda *args: app.quit())
        
        # Start Qt loop
        app.exec() # Blocks
        
        # When closed
        stop_event.set()
    else:
        register_hotkeys(asr, app)

        # Just wait for Ctrl+C
        try:
            while not stop_event.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            stop_event.set()
            
    # Cleanup
    print("Stopping...")
    ts_store.stop_markdown_session()
    unregister_hotkeys()
    capture.stop()
    asr.stop()
    translator.stop()
    vtt.stop()
    print("Done.")

if __name__ == "__main__":
    main()
