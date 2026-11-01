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

### Password-protected ZIP

To create an AES-256 encrypted ZIP, pass `-Password` (or its short alias `-p`):

```powershell
.\build.ps1 -p 'testpassword'
```

For interactive builds, prefer the hidden prompt so the password does not appear
in PowerShell command history:

```powershell
.\build.ps1 -PromptForPassword
```

Choose one password option; empty passwords are rejected. Without either option,
`.\build.ps1` creates the usual unencrypted ZIP. Both modes replace
`dist/WoWFishing-Windows.zip`. The script installs the build-only `pyzipper`
dependency automatically; no separate archive program is needed to build.

Recipients need [7-Zip](https://www.7-zip.org/) or another extractor that supports
AES-encrypted ZIPs. Windows' built-in extractor does not support encrypted archives
([Microsoft documentation](https://support.microsoft.com/en-us/windows/experience/storage-filemanagement/zip-and-unzip-files)).
ZIP encryption protects file contents; file names remain visible. The unpacked
`dist/WoWFishing` folder remains unencrypted.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s . -p "test_*.py" -v
```

Controller tests use fake audio and keyboard input; they do not send keys to WoW.
They cover cast/reel sequencing, lure scheduling, retries, cancellation, resource
cleanup, automatic stopping, settings validation, and foreground checks.

After installing `requirements-build.txt` in `.venv-build`, verify ZIP encryption
and password handling without rebuilding the app:

```powershell
.\.venv-build\Scripts\python.exe -m unittest test_release_zip -v
```

## Other tools

- [Audio detector experiments and tuning](audio-detector.md)
- [Classic implementation](../classic/README.md) (legacy; not bundled with the desktop app)
