import pyaudiowpatch as pyaudio
import numpy as np
from scipy import signal
import librosa
import pyautogui
import time
import random
from pywinauto import Desktop
from datetime import datetime
from collections import deque
import yaml

def load_settings(path="settings.yaml"):
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    # Required keys (fail fast with clear message)
    required = [
        "WOW_TITLE_REGEX",
        "TARGET_FILE",
        "OUT_OF_RANGE_FILE",
        "OUTPUT_DEVICE_INDEX",
        "THRESHOLD",
        "WAIT_AFTER_NOT_FOUND",
        "WAIT_AFTER_TARGET_FOUND",
        "WAIT_AFTER_OUT_OF_RANGE",
        "ACTION_KEY",
        "LURE_KEY",
        "USE_LURE",
    ]
    missing = [k for k in required if k not in cfg]
    if missing:
        raise KeyError(f"Missing keys in {path}: {', '.join(missing)}")

    def as_range(name):
        v = cfg[name]
        if not isinstance(v, list) or len(v) != 2:
            raise ValueError(f"{name} must be a list like [min, max], got: {v!r}")
        a = float(v[0])
        b = float(v[1])
        if a < 0 or b < a:
            raise ValueError(f"{name} invalid range {v!r} (expected 0 <= min <= max)")
        return (a, b)

    cfg["OUTPUT_DEVICE_INDEX"] = int(cfg["OUTPUT_DEVICE_INDEX"])
    cfg["THRESHOLD"] = float(cfg["THRESHOLD"])
    cfg["WAIT_AFTER_NOT_FOUND"] = as_range("WAIT_AFTER_NOT_FOUND")
    cfg["WAIT_AFTER_TARGET_FOUND"] = as_range("WAIT_AFTER_TARGET_FOUND")
    cfg["WAIT_AFTER_OUT_OF_RANGE"] = as_range("WAIT_AFTER_OUT_OF_RANGE")
    cfg["ACTION_KEY"] = str(cfg["ACTION_KEY"])
    cfg["LURE_KEY"] = str(cfg["LURE_KEY"])
    cfg["WOW_TITLE_REGEX"] = str(cfg["WOW_TITLE_REGEX"])
    cfg["TARGET_FILE"] = str(cfg["TARGET_FILE"])
    cfg["OUT_OF_RANGE_FILE"] = str(cfg["OUT_OF_RANGE_FILE"])
    cfg["USE_LURE"] = bool(cfg["USE_LURE"])

    return cfg

# Set global settings from YAML file
SETTINGS = load_settings("settings.yaml")

WOW_TITLE_REGEX = SETTINGS["WOW_TITLE_REGEX"]
TARGET_FILE = SETTINGS["TARGET_FILE"]
OUT_OF_RANGE_FILE = SETTINGS["OUT_OF_RANGE_FILE"]
OUTPUT_DEVICE_INDEX = SETTINGS["OUTPUT_DEVICE_INDEX"]
THRESHOLD = SETTINGS["THRESHOLD"]

WAIT_AFTER_NOT_FOUND = SETTINGS["WAIT_AFTER_NOT_FOUND"]
WAIT_AFTER_TARGET_FOUND = SETTINGS["WAIT_AFTER_TARGET_FOUND"]
WAIT_AFTER_OUT_OF_RANGE = SETTINGS["WAIT_AFTER_OUT_OF_RANGE"]

ACTION_KEY = SETTINGS["ACTION_KEY"]
LURE_KEY = SETTINGS["LURE_KEY"]

USE_LURE = SETTINGS["USE_LURE"]

# Script-owned config (not in YAML)
LISTEN_DURATION = 23  # seconds
CHUNK_DURATION = 0.3  # Process audio every 0.3 seconds for faster response
LURE_COOLDOWN_SECONDS = 10 * 60 + 10 # 10 minutes 6 seconds
LURE_WAIT_TIME = (5.1, 5.5)

def log(message):
    """Print timestamped log messages"""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] {message}")

def load_target_audio(filename):
    """Load the target audio file"""
    log(f"Loading audio file: {filename}")
    target_audio, sr = librosa.load(filename, sr=None, mono=True)
    log(f"  Loaded: {len(target_audio)} samples, sample rate: {sr} Hz, duration: {len(target_audio)/sr:.3f}s")
    return target_audio, sr

def normalize_audio(audio):
    """Normalize audio to prevent amplitude differences"""
    if np.max(np.abs(audio)) > 0:
        return audio / np.max(np.abs(audio))
    return audio

def detect_sound_in_buffer(recorded_audio, target_audio, threshold=0.6):
    """
    Use cross-correlation to detect if target sound is in recorded audio
    Returns: (found, correlation_score)
    """
    if len(recorded_audio) < len(target_audio):
        return False, 0.0
    
    # Normalize both signals
    recorded_norm = normalize_audio(recorded_audio)
    target_norm = normalize_audio(target_audio)
    
    # Perform cross-correlation
    correlation = signal.correlate(recorded_norm, target_norm, mode='valid')
    
    # Normalize correlation
    if len(correlation) > 0:
        correlation = correlation / (len(target_norm) * np.std(recorded_norm) * np.std(target_norm) + 1e-10)
        peak_value = np.max(np.abs(correlation))
        
        if peak_value >= threshold:
            return True, peak_value
        return False, peak_value
    
    return False, 0.0

def press_key(key):
    """Press a keyboard key with logging"""
    log(f">> PRESSING KEY: '{key}' <<")
    pyautogui.press(key)
    time.sleep(0.1)
    log(f"Key '{key}' pressed successfully")

def random_wait(wait_range):
    """Wait for a random amount of time within the given range"""
    min_wait, max_wait = wait_range
    wait_time = random.uniform(min_wait, max_wait)
    return wait_time

def focus_wow_window():
    """Focus WoW window without moving the mouse permanently."""
    pos = pyautogui.position()
    Desktop(backend="win32").window(title_re=WOW_TITLE_REGEX).set_focus()
    pyautogui.moveTo(pos.x, pos.y, duration=0)

def record_and_detect_realtime(p, device_index, target_audio, out_of_range_audio, sample_rate, max_duration):
    """
    Record audio in chunks and detect target sounds in real-time
    Returns: (detection_type, elapsed_time)
    """
    log(f"Opening audio stream on device index {device_index}...")
    
    device_info = p.get_device_info_by_index(device_index)
    device_channels = device_info['maxInputChannels']
    
    log(f"Recording from: {device_info['name']}")
    log(f"Channels: {device_channels}")
    
    chunk_samples = int(sample_rate * CHUNK_DURATION)
    
    buffer_duration = 3.0
    max_buffer_samples = int(sample_rate * buffer_duration)
    audio_buffer = deque(maxlen=max_buffer_samples)
    
    # Try multiple sample rates (NVIDIA devices often need this)
    sample_rates_to_try = [
        int(sample_rate),      # Try requested first
        48000,                  # Most common for HDMI/Display audio
        44100,                  # CD quality
        32000,                  # Lower quality fallback
    ]
    
    # Remove duplicates while preserving order
    sample_rates_to_try = list(dict.fromkeys(sample_rates_to_try))
    
    stream = None
    working_sample_rate = None
    
    for sr in sample_rates_to_try:
        try:
            log(f"Trying sample rate: {sr} Hz...")
            stream = p.open(
                format=pyaudio.paInt16,
                channels=device_channels,
                rate=sr,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=int(sr * CHUNK_DURATION)
            )
            working_sample_rate = sr
            log(f"✓ Success with sample rate: {sr} Hz")
            break
        except Exception as e:
            log(f"✗ Failed with {sr} Hz: {e}")
            continue
    
    if stream is None or working_sample_rate is None:
        log(f"ERROR: Could not open audio stream with any sample rate")
        return None, 0
    
    # If we had to use a different sample rate, resample the target audio
    if working_sample_rate != sample_rate:
        log(f"Resampling target audio from {sample_rate} Hz to {working_sample_rate} Hz...")
        import librosa
        target_audio = librosa.resample(target_audio, orig_sr=sample_rate, target_sr=working_sample_rate)
        out_of_range_audio = librosa.resample(out_of_range_audio, orig_sr=sample_rate, target_sr=working_sample_rate)
        sample_rate = working_sample_rate
        
        # Recalculate buffer sizes
        chunk_samples = int(sample_rate * CHUNK_DURATION)
        max_buffer_samples = int(sample_rate * buffer_duration)
        audio_buffer = deque(maxlen=max_buffer_samples)
    
    log(f"Audio stream ACTIVE - ready to capture immediate sounds")
    log(f"Final sample rate: {sample_rate} Hz")
    
    log(f"Setting WoW as the active application")
    focus_wow_window()
    
    press_key(ACTION_KEY)
    
    log(f"Now listening for up to {max_duration} seconds...")
    log(f"Checking for sounds every {CHUNK_DURATION}s in real-time")
    log(">> ACTIVELY MONITORING FOR 2 SOUNDS <<")
    log(f"  [1] Target sound (target.wav) → Will press '{ACTION_KEY}' to end action")
    log(f"  [2] Out-of-range sound (out-of-range.wav) → Action ends automatically")
    
    start_time = time.time()
    chunk_count = 0
    
    log("Starting audio capture loop...")
    
    try:
        while True:
            elapsed = time.time() - start_time
            if elapsed >= max_duration:
                log(f"Timeout: {max_duration}s elapsed without detection")
                stream.stop_stream()
                stream.close()
                return None, elapsed
            
            try:
                data = stream.read(chunk_samples, exception_on_overflow=False)
            except OSError as e:
                log(f"OSError reading audio: {e}")
                log("This may mean no audio is playing or the device is not sending data.")
                time.sleep(0.1)
                continue
            except Exception as e:
                log(f"Warning: Error reading audio chunk: {e}")
                time.sleep(0.1)
                continue
            
            if not data or len(data) == 0:
                log("Warning: Received empty audio data")
                time.sleep(0.1)
                continue
            
            # Convert to numpy array
            chunk_audio = np.frombuffer(data, dtype=np.int16).astype(np.float32)
            
            # If stereo, convert to mono by averaging channels
            if device_channels == 2:
                chunk_audio = chunk_audio.reshape(-1, 2).mean(axis=1)
            
            audio_buffer.extend(chunk_audio)
            
            chunk_count += 1
            
            if chunk_count % int(2.0 / CHUNK_DURATION) == 0:
                log(f"  Still listening... {elapsed:.1f}s elapsed (buffer: {len(audio_buffer)/sample_rate:.1f}s)")
            
            buffer_array = np.array(audio_buffer)
            
            if len(audio_buffer) >= len(target_audio):
                found_target, score_target = detect_sound_in_buffer(buffer_array, target_audio, THRESHOLD)
                
                if found_target:
                    elapsed = time.time() - start_time
                    log(f"")
                    log(f"{'='*60}")
                    log(f"🐟 TARGET SOUND DETECTED!")
                    log(f"{'='*60}")
                    log(f"Detection Score: {score_target:.3f}")
                    log(f"Time to detection: {elapsed:.2f}s")
                    stream.stop_stream()
                    stream.close()
                    return 'target', elapsed
            
            if len(audio_buffer) >= len(out_of_range_audio):
                found_oor, score_oor = detect_sound_in_buffer(buffer_array, out_of_range_audio, THRESHOLD)
                
                if found_oor:
                    elapsed = time.time() - start_time
                    log(f"")
                    log(f"{'='*60}")
                    log(f"❌ OUT-OF-RANGE SOUND DETECTED!")
                    log(f"{'='*60}")
                    log(f"Detection Score: {score_oor:.3f}")
                    log(f"Time to detection: {elapsed:.2f}s")
                    stream.stop_stream()
                    stream.close()
                    return 'out_of_range', elapsed
    
    except KeyboardInterrupt:
        log("Keyboard interrupt received")
        stream.stop_stream()
        stream.close()
        raise
    except Exception as e:
        log(f"Unexpected error in audio loop: {e}")
        import traceback
        traceback.print_exc()
        stream.stop_stream()
        stream.close()
        return None, 0

def main():
    log("="*60)
    log("REAL-TIME DUAL AUDIO DETECTION PROGRAM")
    log("="*60)
    
    # Load both audio files
    target_audio, target_sr = load_target_audio(TARGET_FILE)
    out_of_range_audio, oor_sr = load_target_audio(OUT_OF_RANGE_FILE)
    
    # Ensure both files have the same sample rate
    if target_sr != oor_sr:
        log(f"WARNING: Sample rates differ! Target: {target_sr} Hz, Out-of-range: {oor_sr} Hz")
        log(f"Resampling out-of-range audio to {target_sr} Hz...")
        out_of_range_audio = librosa.resample(out_of_range_audio, orig_sr=oor_sr, target_sr=target_sr)
        log(f"Resampling complete")
    
    sample_rate = target_sr
    
    # Initialize PyAudio with WASAPI
    log("Initializing PyAudio with WASAPI loopback support...")
    p = pyaudio.PyAudio()
    
    log(f"Configuration:")
    log(f"  - Device Index: {OUTPUT_DEVICE_INDEX}")
    log(f"  - Listen Duration: {LISTEN_DURATION}s per cycle")
    log(f"  - Real-time Check Interval: {CHUNK_DURATION}s")
    log(f"  - Detection Threshold: {THRESHOLD}")
    log(f"  - Sample Rate: {sample_rate} Hz")
    log(f"  - Wait after target found: {WAIT_AFTER_TARGET_FOUND[0]}-{WAIT_AFTER_TARGET_FOUND[1]}s (random)")
    log(f"  - Wait after out-of-range: {WAIT_AFTER_OUT_OF_RANGE[0]}-{WAIT_AFTER_OUT_OF_RANGE[1]}s (random)")
    log(f"  - Wait after not found: {WAIT_AFTER_NOT_FOUND[0]}-{WAIT_AFTER_NOT_FOUND[1]}s (random)")
    log(f"  - Lure Interval: {LURE_COOLDOWN_SECONDS} seconds (applied at start of cycle when due)")
    log("")
    log("FLOW:")
    if USE_LURE:
        log(f"  1. At the start of the cycle press '{LURE_KEY}' to apply lure")
        log(f"     Then, every 10m elapsed, apply the lure with '{LURE_KEY}' again")
    else:
        log("  1. Lure disabled (USE_LURE=false)")
    log(f"  2. Start listening → Press '{ACTION_KEY}' to begin action")
    log(f"  3. If target sound → Press '{ACTION_KEY}' to end action")
    log(f"  4. If out-of-range → Action ends automatically (no '{ACTION_KEY}')")
    log("="*60)
    
    try:
        iteration = 0
        target_count = 0
        out_of_range_count = 0
        no_sound_count = 0
        last_lure_time = None
            
        while True:
            iteration += 1
            
            if USE_LURE and (last_lure_time is None or (time.time() - last_lure_time) >= LURE_COOLDOWN_SECONDS):
                log("")
                log(f"🪱 Using lure now")
                focus_wow_window()
                press_key(LURE_KEY)
                last_lure_time = time.time()
                wait_time = random_wait(LURE_WAIT_TIME)
                log(f"⌛ Waiting {wait_time:.2f} seconds to finish lure cast")
                time.sleep(wait_time)  # small buffer so the game registers it clean
                log("Cast complete, starting next cycle")
            
            log("")
            log(f"{'='*60}")
            log(f"🎣 CYCLE #{iteration} - STARTING")
            log(f"{'='*60}")
            
            # Start listening, which will press ACTION_KEY inside
            detection_type, elapsed = record_and_detect_realtime(
                p, OUTPUT_DEVICE_INDEX, target_audio, out_of_range_audio, sample_rate, LISTEN_DURATION
            )
            
            if detection_type == 'target':
                # Target sound found - press ACTION_KEY to END action, then wait random time
                target_count += 1
                log("")
                log(f"🐟 ACTION: Target detected → Setting WoW as the active application")
                
                focus_wow_window()
                    
                log(f"🐟 Pressing '{ACTION_KEY}' to reel in the fish")
                press_key(ACTION_KEY)
                
                wait_time = random_wait(WAIT_AFTER_TARGET_FOUND)
                log(f"⌛ Waiting {wait_time:.2f} seconds before next cycle...")
                
                time.sleep(wait_time)
                log("Wait complete. Starting next cycle...")
                    
            elif detection_type == 'out_of_range':
                # Out-of-range sound found - action ends automatically, NO '{ACTION_KEY}' press
                out_of_range_count += 1
                log("")
                log(f"❌ ACTION: Out-of-range detected → Action ended automatically (no '{ACTION_KEY}' press)")
                
                wait_time = random_wait(WAIT_AFTER_OUT_OF_RANGE)
                log(f"⌛ Waiting {wait_time:.2f} seconds before next cycle...")
                
                time.sleep(wait_time)
                log("Wait complete. Starting next cycle...")
                
            else:
                # No sound found - wait random time and retry
                no_sound_count += 1
                log("")
                wait_time = random_wait(WAIT_AFTER_NOT_FOUND)
                log(f"🔇 ACTION: No sound detected → ⌛ Waiting {wait_time:.2f}s before retry")
                
                time.sleep(wait_time)
                log("Retrying now...")
                
    except KeyboardInterrupt:
        log("")
        log("="*60)
        log("PROGRAM STOPPED by user (Ctrl+C)")
        log("🎣 Cycles: " + str(iteration))
        log("🐟 Fish caught: " + str(target_count))
        log("❌ Out-of-range events: " + str(out_of_range_count))
        log("🔇 No sound events: " + str(no_sound_count))
        log("="*60)
    finally:
        p.terminate()
        log("PyAudio terminated. Program ended.")

if __name__ == "__main__":
    main()
