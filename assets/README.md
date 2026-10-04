# WoWFishing logo

`wowfishing.png` is the transparent source image displayed at 64 × 64 logical
pixels in the GUI. `wowfishing.ico` contains 16, 24, 32, 48, 64, 128, and 256 pixel
versions for Windows title bars and the executable. Both are bundled by
`WoWFishing.spec` and located relative to `gui.py` in source and packaged builds.

Generated with the built-in image generation tool. Prompt:

> Use case: logo-brand. Create a simple fishing bot application logo for WoWFishing, used as a Windows executable icon and a small top-left GUI logo. A single friendly robotic fish with a clear fish silhouette, a simple square robot eye and a small fishing hook integrated above it. Clean flat vector-like illustration, bold shapes, minimal detail, crisp edges, no text or letters, no watermark, no mockup. Use bright green and pale mint with a deep navy outline to fit a dark navy desktop application with green controls. Center the complete compact mark in a square canvas with modest padding, readable at 32 and 64 pixels. Genuinely transparent background outside the mark.

To regenerate the ICO after replacing the PNG, run from the project root:

```powershell
.\.venv-build\Scripts\python.exe -c "from PIL import Image; Image.open('assets/wowfishing.png').save('assets/wowfishing.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])"
```

Then run `build.ps1` to update the executable and release ZIP.
