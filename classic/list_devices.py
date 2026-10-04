import pyaudiowpatch as pyaudio

def list_audio_devices():
    """List all audio devices with details about loopback capability"""
    print("="*70)
    print("AVAILABLE AUDIO DEVICES")
    print("="*70)
    
    p = pyaudio.PyAudio()
    
    # Get default devices
    try:
        default_input = p.get_default_input_device_info()
        default_input_index = default_input['index']
    except:
        default_input_index = None
    
    try:
        default_output = p.get_default_output_device_info()
        default_output_index = default_output['index']
    except:
        default_output_index = None
    
    # Check for WASAPI loopback devices
    try:
        wasapi_info = p.get_default_wasapi_loopback()
        wasapi_loopback_index = wasapi_info['index']
    except:
        wasapi_loopback_index = None
    
    print(f"\nDefault Input Device Index: {default_input_index}")
    print(f"Default Output Device Index: {default_output_index}")
    print(f"Default WASAPI Loopback Index: {wasapi_loopback_index}")
    print("\n" + "="*70)
    
    device_count = p.get_device_count()
    
    loopback_devices = []
    
    for i in range(device_count):
        try:
            info = p.get_device_info_by_index(i)
            
            name = info['name']
            max_input_channels = info['maxInputChannels']
            max_output_channels = info['maxOutputChannels']
            sample_rate = int(info['defaultSampleRate'])
            
            # Check if it's a loopback device
            is_loopback = False
            is_wasapi_loopback = False
            
            if max_input_channels > 0:
                if "loopback" in name.lower() or "(loopback)" in name.lower():
                    is_loopback = True
                    is_wasapi_loopback = True
                elif i == wasapi_loopback_index:
                    is_wasapi_loopback = True
                    is_loopback = True
            
            # Print device info
            print(f"\nIndex: {i}")
            print(f"  Name: {name}")
            print(f"  Input Channels: {max_input_channels}")
            print(f"  Output Channels: {max_output_channels}")
            print(f"  Sample Rate: {sample_rate} Hz")
            
            # Mark special devices
            markers = []
            if i == default_input_index:
                markers.append("DEFAULT INPUT")
            if i == default_output_index:
                markers.append("DEFAULT OUTPUT")
            if is_wasapi_loopback:
                markers.append("⭐ WASAPI LOOPBACK")
                loopback_devices.append(i)
            elif is_loopback:
                markers.append("🔊 LOOPBACK")
                loopback_devices.append(i)
            
            if markers:
                print(f"  → {' | '.join(markers)}")
            
        except Exception as e:
            print(f"\nIndex: {i}")
            print(f"  Error reading device: {e}")
    
    print("\n" + "="*70)
    print("RECOMMENDED DEVICES FOR AUDIO OUTPUT CAPTURE:")
    print("="*70)
    
    if loopback_devices:
        print("\nThe following device indices support loopback recording:")
        print("(These can capture what your computer is playing)\n")
        for idx in loopback_devices:
            info = p.get_device_info_by_index(idx)
            print(f"  Index {idx}: {info['name']}")
    else:
        print("\nNo loopback devices found!")
        print("\nTip: Look for devices with 'Stereo Mix', 'What U Hear',")
        print("or devices that have input channels and are output devices.")
    
    print("\n" + "="*70)
    print("\nTo use a device, set OUTPUT_DEVICE_INDEX = <index> in your script")
    print("="*70)
    
    p.terminate()

if __name__ == "__main__":
    list_audio_devices()
