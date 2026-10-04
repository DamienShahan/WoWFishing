import pyaudiowpatch as pyaudio
import numpy as np
import wave
import librosa
import soundfile as sf
from datetime import datetime

# Configuration
OUTPUT_DEVICE_INDEX = 42  # Change to your device index
RECORD_DURATION = 30  # seconds
OUTPUT_FILE = "full_recording.wav"

def log(message):
    """Print timestamped log messages"""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] {message}")

def record_audio(device_index, duration, output_file):
    """Record audio from specified device"""
    log("="*60)
    log("AUDIO RECORDER")
    log("="*60)

    p = pyaudio.PyAudio()

    # Get device info
    try:
        device_info = p.get_device_info_by_index(device_index)
        sample_rate = int(device_info['defaultSampleRate'])
        log(f"Device: {device_info['name']}")
        log(f"Sample Rate: {sample_rate} Hz")
    except Exception as e:
        log(f"ERROR: Could not get device info for index {device_index}")
        log(f"Error: {e}")
        p.terminate()
        return None

    log(f"Recording for {duration} seconds...")
    log("Make sure your audio/game is playing!")
    log("")

    # Open stream
    chunk_size = 1024
    stream = p.open(
        format=pyaudio.paInt16,
        channels=2,  # Stereo
        rate=sample_rate,
        input=True,
        input_device_index=device_index,
        frames_per_buffer=chunk_size
    )

    log("🔴 RECORDING STARTED")
    log("")

    frames = []
    chunks_to_record = int(sample_rate / chunk_size * duration)

    for i in range(chunks_to_record):
        try:
            data = stream.read(chunk_size, exception_on_overflow=False)
            frames.append(data)

            # Progress update every second
            elapsed = (i * chunk_size) / sample_rate
            if i % int(sample_rate / chunk_size) == 0:
                remaining = duration - elapsed
                log(f"  Recording... {elapsed:.0f}s elapsed, {remaining:.0f}s remaining")
        except Exception as e:
            log(f"Error reading audio: {e}")
            continue

    log("")
    log("⏹️  RECORDING STOPPED")

    stream.stop_stream()
    stream.close()
    p.terminate()

    # Save as WAV file
    log(f"Saving to {output_file}...")
    wf = wave.open(output_file, 'wb')
    wf.setnchannels(2)
    wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
    wf.setframerate(sample_rate)
    wf.writeframes(b''.join(frames))
    wf.close()

    log(f"✓ Saved: {output_file}")
    log(f"Duration: {duration}s, Sample Rate: {sample_rate} Hz")

    return output_file, sample_rate

def extract_segment(input_file, start_time, end_time, output_file):
    """Extract a segment from the recorded audio"""
    log("")
    log("="*60)
    log("EXTRACTING SEGMENT")
    log("="*60)

    log(f"Loading {input_file}...")
    audio, sr = librosa.load(input_file, sr=None, mono=True)

    duration = len(audio) / sr
    log(f"Total duration: {duration:.2f}s")
    log(f"Sample rate: {sr} Hz")
    log("")

    # Validate times
    if start_time < 0 or end_time > duration or start_time >= end_time:
        log(f"ERROR: Invalid times!")
        log(f"  Start time: {start_time}s")
        log(f"  End time: {end_time}s")
        log(f"  Total duration: {duration:.2f}s")
        return False

    log(f"Extracting from {start_time}s to {end_time}s...")

    # Extract segment
    start_sample = int(start_time * sr)
    end_sample = int(end_time * sr)
    segment = audio[start_sample:end_sample]

    segment_duration = len(segment) / sr
    log(f"Segment duration: {segment_duration:.3f}s")

    # Save segment
    log(f"Saving to {output_file}...")
    sf.write(output_file, segment, sr)

    log(f"✓ Saved: {output_file}")
    log("")
    log("="*60)
    log("DONE! You can now use this file in your detection program.")
    log("="*60)

    return True

def main():
    print("="*60)
    print("AUDIO RECORDING AND EXTRACTION TOOL")
    print("="*60)
    print("")
    print("This tool will:")
    print("  1. Record audio from your WASAPI loopback device")
    print("  2. Let you extract the exact segment you need")
    print("")
    print("="*60)
    print("")

    # Step 1: Record
    input("Press ENTER to start recording...")
    recorded_file, sr = record_audio(OUTPUT_DEVICE_INDEX, RECORD_DURATION, OUTPUT_FILE)

    if not recorded_file:
        log("Recording failed!")
        return

    print("")
    print("="*60)
    print("PLAYBACK INSTRUCTIONS")
    print("="*60)
    print(f"1. Open '{OUTPUT_FILE}' in an audio player (e.g., Windows Media Player)")
    print("2. Find the exact moment you want to capture")
    print("3. Note the START and END times (in seconds)")
    print("")
    print("Example: If your target sound occurs from 12.5s to 13.0s")
    print("  Start time: 12.5")
    print("  End time: 13.0")
    print("="*60)
    print("")

    # Step 2: Extract segment
    while True:
        try:
            print("Enter extraction details (or 'q' to quit):")
            start_input = input("  Start time (seconds): ").strip()

            if start_input.lower() == 'q':
                log("Exiting...")
                break

            end_input = input("  End time (seconds): ").strip()
            output_name = input("  Output filename (e.g., target.wav): ").strip()

            start_time = float(start_input)
            end_time = float(end_input)

            if not output_name:
                output_name = "extracted.wav"

            success = extract_segment(recorded_file, start_time, end_time, output_name)

            if success:
                print("")
                extract_more = input("Extract another segment? (y/n): ").strip().lower()
                if extract_more != 'y':
                    break
            else:
                print("Try again with different times.")

        except ValueError:
            log("ERROR: Please enter valid numbers for times")
        except Exception as e:
            log(f"ERROR: {e}")

    log("")
    log("Program ended. Thank you!")

if __name__ == "__main__":
    main()