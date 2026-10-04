# Real-Time Audio Detection Bot

An automated audio detection system that listens for specific sounds and triggers keyboard actions. Designed for applications like game automation where audio cues need to be detected and responded to automatically.

## Features

- **Real-time audio monitoring** using WASAPI loopback
- **Dual sound detection** - monitors for two different audio files simultaneously
- **Smart key press logic** - differentiates between manual and automatic action endings
- **Randomized wait times** - makes behavior more natural and unpredictable
- **Cross-correlation detection** - robust audio matching that handles volume variations
- **Detailed logging** - timestamped events for debugging and monitoring
- **Automatic window focusing on target detection** - brings a specific application to the foreground before sending the action key, allowing you to keep working in another window/screen
- **Optional auto-lure support** - applies a lure at the start of the cycle and re-applies it every ~10m (on the next cycle start)

## How It Works

### Flow

1. **Apply Lure**:
   - If no lure has been applied yet, or **10m** have elapsed since the last lure → press `LURE_KEY` to apply lure
   - Wait ~**5.1–5.5s** so the lure cast finishes cleanly
2. **Start Cycle**: Program begins listening for audio
3. **Press Hotkey**: Automatically presses the designated `ACTION_KEY` (e.g. 'k') to start an action
4. **Listen**: Monitors audio output for 23 seconds
5. **Detect**:
   - **Target sound found** → Press `ACTION_KEY` to end action, wait 3-5 seconds, restart cycle
   - **Out-of-range sound found** → Action ends automatically (no key press), wait 1.5-2.5 seconds, restart cycle
   - **No sound found** → Wait 0.5-1.5 seconds, retry

If `USE_LURE=false`, step 1 (apply lure) is skipped entirely.

### Key Press Logic

| Event                           | Key Pressed?   | Wait Time         |
| ------------------------------- | -------------- | ----------------- |
| Apply lure (if enabled and due) | ✓ `LURE_KEY`   | 5.1–5.5s (random) |
| Cycle starts (cast)             | ✓ `ACTION_KEY` | -                 |
| Target detected (reel in)       | ✓ `ACTION_KEY` | 1.5-2.5s (random) |
| Out-of-range detected           | ✗ No press     | 1-1.5s (random)   |
| Timeout (no sound)              | ✗ No press     | 1-2s (random)     |

## Requirements

### Dependencies

```
pyaudiowpatch
numpy
scipy
librosa
pyautogui
pywinauto
pyyaml
```

### System Requirements

- **OS**: Windows (WASAPI loopback support)
- **Audio**: Active audio output device
- **Python**: 3.7+

### Game Prerequisites

- **Weakaura**: [FishingRangeAlert](https://wago.io/4jGL2hFGC)
- **AddOn**: [Better Fishing](https://www.curseforge.com/wow/addons/better-fishing)

If you enable lure usage (`USE_LURE=true`), you must also create this ingame macro and bind it to `LURE_KEY`. This uses the lure Bright Baubles and applies it to your weapon slot.

```lua
#showtooltip
/use [item:6532] Bright Baubles
/use 16
```

If `USE_LURE=false`, you do not need this macro.

## Installation

### 1. Set up Virtual Environment

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If opening the virtual environment is being blocked, you can allow it with this command:

```bash
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

### 2. Install Python Packages

```bash
pip install -r requirements.txt
```

### 3. Prepare Audio Files

In the `sounds` folder are two WAV files, of the fishing sounds to be listened for. If these sounds do not work for you, you will have to re-record them yourself.

- `target.wav` - The sound you want to detect (e.g., fishing bobber splash)
- `out-of-range.wav` - The sound indicating failure (e.g., "out of range" voice)

**Tip**: Record these directly from your application for best accuracy.

### 4. Find Your Audio Device Index

Run the device listing script:

```python
python list_devices.py
```

Look for devices marked with **⭐ WASAPI LOOPBACK** and note the index number.

## Configuration

The bot reads configuration from `settings.yaml`:

```yaml
# Configuration
WOW_TITLE_REGEX: "^World of Warcraft$"
TARGET_FILE: "sounds/target.wav"
OUT_OF_RANGE_FILE: "sounds/out-of-range.wav"
OUTPUT_DEVICE_INDEX: 38

THRESHOLD: 1.2 # Correlation threshold (adjust if needed)

# Wait times as ranges (min, max) in seconds
WAIT_AFTER_NOT_FOUND: [0.5, 1.5]
WAIT_AFTER_TARGET_FOUND: [3.0, 5.0]
WAIT_AFTER_OUT_OF_RANGE: [1.5, 2.5]

# Hotkey configuration
ACTION_KEY: "k" # Key to press which starts/ends the action
LURE_KEY: "f5" # Key to press to apply the lure

USE_LURE: false # activate (true) or deactivate (false) using a lure
```

## Usage

### Basic Usage

1. Navigate to your folder
2. Start the virtual environment
3. Start the fishing bot

```bash
cd <your folder path>
.\.venv\Scripts\Activate.ps1
python fishing.py
```

### Stop the Program

Press `Ctrl+C` to safely stop the program.

### Typical Output

```
============================================================
REAL-TIME DUAL AUDIO DETECTION PROGRAM
============================================================
[09:15:06] Loading audio file: sounds/target.wav
[09:15:07]   Loaded: 32721 samples, sample rate: 44100 Hz, duration: 0.742s
[09:15:07] Loading audio file: sounds/out-of-range.wav
[09:15:07]   Loaded: 5556 samples, sample rate: 44100 Hz, duration: 0.126s
[09:15:07] Initializing PyAudio with WASAPI loopback support...
[09:15:07] Configuration:
[09:15:07]   - Device Index: 38
[09:15:07]   - Listen Duration: 23s per cycle
[09:15:07]   - Real-time Check Interval: 0.3s
[09:15:07]   - Detection Threshold: 1.2
[09:15:07]   - Sample Rate: 44100 Hz
[09:15:07]   - Wait after target found: 1.5-2.5s (random)
[09:15:07]   - Wait after out-of-range: 1.0-1.5s (random)
[09:15:07]   - Wait after not found: 1.0-2.0s (random)
[09:15:07]   - Lure Interval: 570 seconds (applied at start of cycle when due)
[09:15:07]
[09:15:07] FLOW:
[09:15:07]   1. Lure disabled (USE_LURE=false)
[09:15:07]   2. Start listening → Press 'k' to begin action
[09:15:07]   3. If target sound → Press 'k' to end action
[09:15:07]   4. If out-of-range → Action ends automatically (no 'k')
 ============================================================

[09:15:07] 🪱 Using lure now
[09:15:08] >> PRESSING KEY: 'f5' <<
[09:15:08] Key 'f5' pressed successfully
[09:15:08] ⌛ Waiting 5.45 seconds to finish lure cast
[09:15:13] Cast complete, starting next cycle...

============================================================
🎣 CYCLE #1 - STARTING
============================================================
[01:44:15] >>> PRESSING KEY: 'k' <<<
[01:44:15] Now listening for up to 23 seconds...
[01:44:17]   Still listening... 2.1s elapsed (buffer: 2.1s)

============================================================
🐟 TARGET SOUND DETECTED!
============================================================
[01:44:19] Detection Score: 0.847
[01:44:19] >>> PRESSING KEY: 'k' <<<
[01:44:19] Waiting 4.23 seconds before next cycle...
```

## Troubleshooting

### Program Hangs After "ACTIVELY MONITORING"

**Cause**: No audio is playing through the selected device.

**Solution**:

- Make sure audio/game is playing through the correct output device
- Loopback devices only capture audio that is actively being output
- Try playing some music to verify the device is receiving audio

### "Invalid Sample Rate" Error

**Cause**: Device sample rate mismatch.

**Solution**: The latest version auto-detects and resamples. Update to the fixed code.

### Detection Not Working

**Possible causes**:

1. **Threshold too high** → Lower `THRESHOLD` (try 0.5 or 0.4)
2. **Wrong audio files** → Re-record target sounds with better quality
3. **Volume differences** → Ensure similar volume levels when recording
4. **Background noise** → Record in a quieter environment

### Wrong Device Selected

**Solution**: Run `list_devices.py` and verify you're using a loopback device (marked with ⭐).

### Keys Not Pressing

**Possible causes**:

1. **Application not in focus** → Make sure target application is the active window
2. **Admin privileges** → Some apps require running Python as administrator
3. **Wrong key** → Verify 'k' is the correct key for your application

## File Structure

```
project/
│
├── fishing.py              # Main program
├── list_devices.py         # Device listing utility
├── settings.yaml           # Configuration
├── sounds/target.wav       # Target sound file
├── sounds/out-of-range.wav # Out-of-range sound file
└── README.md               # This file
```

## Technical Details

### Audio Detection Method

The program uses **cross-correlation** to detect audio patterns:

1. Records audio in 0.3-second chunks
2. Maintains a 3-second rolling buffer
3. Compares buffer against target audio using normalized cross-correlation
4. Detects match when correlation score exceeds threshold

### Advantages

- Handles volume variations automatically (normalization)
- Robust to background noise
- Fast real-time detection (300ms chunks)
- Sample rate agnostic (auto-resamples)

## Advanced Configuration

### Adjusting Detection Sensitivity

- **More sensitive** (more false positives): `THRESHOLD = 0.6`
- **Less sensitive** (fewer false positives): `THRESHOLD = 1.8`
- **Default balanced**: `THRESHOLD = 1.2`

### Changing Wait Time Ranges

```yaml
# Faster cycles (more aggressive)
WAIT_AFTER_TARGET_FOUND: [1, 2]

# Slower cycles (more conservative)
WAIT_AFTER_TARGET_FOUND: [5, 10]
```

### Different Key Bindings

Modify the fishing hotkey in `ACTION_KEY` or the lure macro hotkey in `LURE_KEY` in the `settings.yaml` file:

```yaml
# Hotkey configuration
ACTION_KEY: "g" # Change from 'k' to 'g'
LURE_KEY: "e" # Change from 'f5' to 'e'
```

## Safety Notes

- This program simulates keyboard input - use responsibly
- Ensure you comply with the terms of service of any application you use this with
- The program can be stopped at any time with `Ctrl+C`
- Test thoroughly in a safe environment before production use
