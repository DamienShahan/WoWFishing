"""Create the encrypted release ZIP; receive its password as UTF-8 JSON on stdin."""
import argparse
import json
from pathlib import Path
import sys
import tempfile


def create_encrypted_zip(source: Path, destination: Path, password: str) -> None:
    if not isinstance(password, str) or not password:
        raise ValueError("ZIP password must not be empty.")
    if not source.is_dir():
        raise FileNotFoundError(f"Release directory does not exist: {source}")

    import pyzipper  # Build-only dependency; the desktop app does not need it.

    # Replace the previous release only after the new archive is complete.
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".zip", delete=False) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with pyzipper.AESZipFile(
            str(temporary_path), "w", compression=pyzipper.ZIP_DEFLATED
        ) as archive:
            archive.setpassword(password.encode("utf-8"))
            archive.setencryption(pyzipper.WZ_AES, nbits=256)
            for path in sorted(source.rglob("*")):
                if path.is_file():
                    archive.write(str(path), path.relative_to(source.parent).as_posix())
        temporary_path.replace(destination)
    finally:
        temporary_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    # JSON preserves spaces, quotes, Unicode, and embedded newlines in passwords.
    password = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    create_encrypted_zip(args.source, args.destination, password)


if __name__ == "__main__":
    main()
