import pyaudiowpatch as pyaudio
import wave
import time

DURATION = 10.0
FILENAME = "test_loopback.wav"

def record_loopback():
    p = pyaudio.PyAudio()
    
    try:
        wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
    except OSError:
        print("WASAPI not found")
        return

    # Get default WASAPI speakers
    default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
    print(f"Default speakers: {default_speakers['name']}")
    
    if not default_speakers["isLoopbackDevice"]:
        found = False
        # iterate all devices to find the loopback for default speakers
        for i in range(p.get_device_count()):
            dev = p.get_device_info_by_index(i)
            if dev["hostApi"] == wasapi_info["index"] and dev["isLoopbackDevice"]:
                # Simple heuristic: name match or just pick first loopback
                if default_speakers["name"] in dev["name"]:
                    default_speakers = dev
                    found = True
                    break
        if not found:
            print("Loopback for default speakers not found. Picking first available loopback.")
             # Fallback: pick first loopback
            for i in range(p.get_device_count()):
                dev = p.get_device_info_by_index(i)
                if dev["hostApi"] == wasapi_info["index"] and dev["isLoopbackDevice"]:
                    default_speakers = dev
                    break
    
    print(f"Recording from: {default_speakers['name']} (Index: {default_speakers['index']})")
    
    frames = []
    
    def callback(in_data, frame_count, time_info, status):
        frames.append(in_data)
        return (in_data, pyaudio.paContinue)
        
    stream = p.open(format=pyaudio.paInt16,
                    channels=default_speakers["maxInputChannels"],
                    rate=int(default_speakers["defaultSampleRate"]),
                    input=True,
                    input_device_index=default_speakers["index"],
                    frames_per_buffer=1024,
                    stream_callback=callback)
    
    print("Recording...")
    stream.start_stream()
    time.sleep(DURATION)
    stream.stop_stream()
    stream.close()
    p.terminate()
    
    print(f"Finished. Saving to {FILENAME}...")
    
    wf = wave.open(FILENAME, 'wb')
    wf.setnchannels(default_speakers["maxInputChannels"])
    wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
    wf.setframerate(int(default_speakers["defaultSampleRate"]))
    wf.writeframes(b''.join(frames))
    wf.close()
    print("Saved.")

if __name__ == "__main__":
    record_loopback()
