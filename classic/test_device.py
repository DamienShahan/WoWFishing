import pyaudiowpatch as pyaudio
import time

def test_device(device_index):
    """Test opening a stream with various configurations"""
    print("="*60)
    print(f"TESTING DEVICE INDEX {device_index}")
    print("="*60)

    p = pyaudio.PyAudio()

    # Get device info
    try:
        info = p.get_device_info_by_index(device_index)
        print(f"\nDevice: {info['name']}")
        print(f"Max Input Channels: {info['maxInputChannels']}")
        print(f"Max Output Channels: {info['maxOutputChannels']}")
        print(f"Default Sample Rate: {info['defaultSampleRate']}")
    except Exception as e:
        print(f"ERROR getting device info: {e}")
        p.terminate()
        return

    # Test configurations
    sample_rates = [44100, 48000, 16000, 22050, 32000]
    channels_options = [1, 2]

    print("\n" + "="*60)
    print("TESTING CONFIGURATIONS")
    print("="*60)

    successful_configs = []

    for sr in sample_rates:
        for ch in channels_options:
            config = f"SR={sr}, Channels={ch}"
            try:
                stream = p.open(
                    format=pyaudio.paInt16,
                    channels=ch,
                    rate=sr,
                    input=True,
                    input_device_index=device_index,
                    frames_per_buffer=1024
                )

                # Try to read a bit of data
                data = stream.read(1024, exception_on_overflow=False)

                stream.stop_stream()
                stream.close()

                print(f"✓ {config} - SUCCESS")
                successful_configs.append((sr, ch))

            except Exception as e:
                print(f"✗ {config} - FAILED: {e}")

    print("\n" + "="*60)
    print("RESULTS")
    print("="*60)

    if successful_configs:
        print(f"\n✓ Found {len(successful_configs)} working configuration(s):")
        for sr, ch in successful_configs:
            print(f"  - Sample Rate: {sr} Hz, Channels: {ch}")

        print("\nRECOMMENDED CONFIGURATION:")
        # Prefer native sample rate and stereo if available
        best = successful_configs[0]
        for sr, ch in successful_configs:
            if sr == int(info['defaultSampleRate']):
                best = (sr, ch)
                break

        print(f"  Sample Rate: {best[0]} Hz")
        print(f"  Channels: {best[1]}")
    else:
        print("\n✗ No working configurations found!")
        print("This device may not support loopback recording.")

    p.terminate()

if __name__ == "__main__":
    # Change this to your device index
    DEVICE_INDEX = 38

    test_device(DEVICE_INDEX)