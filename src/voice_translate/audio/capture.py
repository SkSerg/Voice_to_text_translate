import threading
import time
import queue
import numpy as np
import pyaudiowpatch as pyaudio
import scipy.signal
import scipy.io.wavfile as wavfile
from typing import Optional, List

from voice_translate.config import cfg
from voice_translate.ring_buffer import RingBuffer

class AudioCapture:
    def __init__(self, ring_buffer: RingBuffer, vad_audio_queue: Optional[queue.Queue] = None):
        self.ring_buffer = ring_buffer
        self.vad_audio_queue = vad_audio_queue
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.p = pyaudio.PyAudio()
        self.stream = None
        self.device_info = None
        
    def find_loopback_device(self):
        """Find the default WASAPI loopback device."""
        try:
            # Get default WASAPI info
            wasapi_info = self.p.get_host_api_info_by_type(pyaudio.paWASAPI)
        except OSError:
            print("WASAPI not found")
            return None
            
        default_speakers = wasapi_info.get("defaultOutputDevice")
        
        if not default_speakers:
            print("No default output device found")
            return None
            
        default_device = self.p.get_device_info_by_index(default_speakers)
        print(f"Default Output Device: {default_device['name']}")
        
        candidates = []
        for i in range(self.p.get_device_count()):
            dev = self.p.get_device_info_by_index(i)
            if dev["hostApi"] == wasapi_info["index"]:
                if dev["isLoopbackDevice"]:
                    print(f"Found loopback candidate: {dev['name']}")
                    candidates.append(dev)

        if not candidates:
            print("No loopback device found.")
            return None
        
        # Priority 1: Configured device
        if cfg.capture_device:
            print(f"Searching for configured device: '{cfg.capture_device}'")
            for dev in candidates:
                if cfg.capture_device.lower() in dev['name'].lower():
                     print(f"Selected loopback device (matched config): {dev['name']}")
                     return dev
            print(f"Warning: Configured device '{cfg.capture_device}' not found in candidates.")

        # Priority 2: Match Default Output Device
        for dev in candidates:
            if default_device['name'] in dev['name']:
                print(f"Selected loopback device (matched default): {dev['name']}")
                return dev
                
        # Priority 3: Fuzzy Match Default Output Device
        for dev in candidates:
            def_tokens = set(default_device['name'].split())
            dev_tokens = set(dev['name'].split())
            if len(def_tokens.intersection(dev_tokens)) >= 2: # at least 2 words match
                 print(f"Selected loopback device (fuzzy match): {dev['name']}")
                 return dev
                 
        # Priority 4: First Available
        print(f"Warning: Could not match default output device. Selecting first available: {candidates[0]['name']}")
        return candidates[0]

    def _callback(self, in_data, frame_count, time_info, status):
        """Callback for PyAudio stream."""
        # in_data is bytes
        audio_data = np.frombuffer(in_data, dtype=np.float32)
        
        # Resample logic
        # If capture rate != target rate, we need to resample.
        # Ideally, we chunk this.
        # But scipy.signal.resample is for fixed size.
        
        # Simple downsampling if integer ratio? No, usually 44100/48000 -> 16000.
        
        # We need to reshape to (frames, channels)
        num_channels = self.device_info["maxInputChannels"] # Captured channels
        if num_channels > 1:
             audio_data = audio_data.reshape(-1, num_channels)
             # Downmix to mono: average channels
             audio_data = audio_data.mean(axis=1)
        
        # Now we have mono float32
        
        # Resample
        # NOTE: resampling inside callback might be heavy. 
        # Better design: put into a raw queue, resample in a separate thread.
        # But for MVP, let's try simple resampling if needed.
        # 1024 samples at 48k is tiny. Resampling 1024 samples is fast.
        
        if int(self.device_info["defaultSampleRate"]) != cfg.target_rate:
            # Calculate number of samples
            num_samples = len(audio_data)
            duration_s = num_samples / int(self.device_info["defaultSampleRate"])
            target_samples = int(duration_s * cfg.target_rate)
            
            # Use minimal resample function or fast one
            audio_data = scipy.signal.resample(audio_data, target_samples)
            
        # Apply Gain
        if cfg.capture_gain != 1.0:
            audio_data = audio_data * cfg.capture_gain

        if self.vad_audio_queue:
            self.vad_audio_queue.put(audio_data.astype(np.float32))
            
        self.ring_buffer.write(audio_data.astype(np.float32))
        
        return (in_data, pyaudio.paContinue)

    def start(self):
        self.device_info = self.find_loopback_device()
        if not self.device_info:
            raise RuntimeError("Cannot find loopback device")
            
        print(f"Starting capture on: {self.device_info['name']}")
        
        self.stream = self.p.open(
            format=pyaudio.paFloat32,
            channels=self.device_info["maxInputChannels"],
            rate=int(self.device_info["defaultSampleRate"]),
            input=True,
            input_device_index=self.device_info["index"],
            frames_per_buffer=cfg.capture_blocksize,
            stream_callback=self._callback
        )
        self.running = True
        self.stream.start_stream()

    def stop(self):
        self.running = False
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
        if self.p:
            self.p.terminate()
    
    def _print_rms(self, interval=2.0):
        # Background thread to print RMS every N seconds
        import time
        while self.running:
             time.sleep(interval)
             # This is tricky because we don't have access to current 'chunk' easily
             # without modifying callback.
             # Instead, modify _callback to compute RMS and update a shared variable?
             # Let's modify _callback instead.
             pass

if __name__ == "__main__":
    # Test capture
    import time
    
    rb = RingBuffer(size_samples=16000 * 30) # 30 sec buffer
    cap = AudioCapture(rb)
    
    try:
        cap.start()
        print("Capturing... Speak or play audio.")
        while True:
            time.sleep(1)
            # print last 1 sec volume
            last_sec = rb.get_last_n_samples(16000)
            vol = np.sqrt(np.mean(last_sec**2))
            print(f"RMS Volume: {vol:.5f}")
            
    except KeyboardInterrupt:
        cap.stop()
        print("Stopped.")

