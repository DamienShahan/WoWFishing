# Development

[Back to the user guide](../README.md)

## Run from source

Use Python 3.11 or 3.12 on Windows. Create the environment once:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe gui.py
```

## Build the Windows release

Use Python 3.11 or 3.12 on Windows, with a root `.venv` already created:

```powershell
.\build.ps1
```

Run these commands from the project root. The script creates a separate `.venv-build`, installs `requirements-build.txt`,
and runs `WoWFishing.spec`. This avoids collecting unrelated packages from a
development environment. Output: `dist/WoWFishing/WoWFishing.exe` and
`dist/WoWFishing-Windows.zip`. Current target sounds, code, and the fishing logo
in `assets/` are included. The logo appears in the top-left header and is embedded
as the executable icon. Builds are unsigned. Validate a release on another Windows computer
before distributing broadly.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s . -p "test_*.py" -v
```

Controller tests use fake audio and keyboard input; they do not send keys to WoW.
They cover cast/reel sequencing, lure scheduling, retries, cancellation, resource
cleanup, automatic stopping, settings validation, and foreground checks.

## Other tools

- [Audio detector experiments and tuning](audio-detector.md)
- [Classic implementation](../classic/README.md) (legacy; not bundled with the desktop app)
