"""Check release archive encryption without building the executable."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from release_zip import create_encrypted_zip

try:
    import pyzipper
except ImportError:
    pyzipper = None


@unittest.skipIf(pyzipper is None, "Install requirements-build.txt to test encrypted ZIPs.")
class ReleaseZipTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "WoWFishing"
        (self.source / "_internal").mkdir(parents=True)
        (self.source / "WoWFishing.exe").write_bytes(b"example executable")
        (self.source / "_internal" / "settings.yaml").write_bytes(b"k\n")
        (self.source / "QUICKSTART.txt").write_bytes(b"Extract the whole folder.")
        self.destination = self.root / "WoWFishing-Windows.zip"

    def test_every_file_uses_aes256_and_requires_the_right_password(self):
        create_encrypted_zip(self.source, self.destination, "testpassword")
        with pyzipper.AESZipFile(str(self.destination)) as archive:
            self.assertEqual(set(archive.namelist()), {
                "WoWFishing/WoWFishing.exe",
                "WoWFishing/_internal/settings.yaml",
                "WoWFishing/QUICKSTART.txt",
            })
            for entry in archive.infolist():
                with self.subTest(filename=entry.filename):
                    self.assertTrue(entry.flag_bits & 1)
                    self.assertEqual(entry.wz_aes_strength, 3)
                    self.assertEqual(entry.wz_aes_version, 2)
                    self.assertEqual(entry.CRC, 0)
                    with self.assertRaises(RuntimeError):
                        archive.read(entry.filename)
                    with self.assertRaises(RuntimeError):
                        archive.read(entry.filename, pwd=b"wrong-password")
                    original = self.root / entry.filename
                    self.assertEqual(archive.read(entry.filename, pwd=b"testpassword"), original.read_bytes())

    def test_cli_preserves_unicode_quotes_spaces_and_newlines(self):
        password = '  p\u00e4ss "quoted" \\ $`\n\u79d8\u5bc6  '
        result = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("release_zip.py")),
             str(self.source), str(self.destination)],
            input=json.dumps(password).encode("utf-8"), capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8"))
        self.assertEqual(result.stdout, b"")
        with pyzipper.AESZipFile(str(self.destination)) as archive:
            self.assertEqual(archive.read("WoWFishing/WoWFishing.exe", pwd=password.encode("utf-8")),
                             b"example executable")

    def test_rebuilding_replaces_old_entries_and_password(self):
        create_encrypted_zip(self.source, self.destination, "old-password")
        (self.source / "QUICKSTART.txt").unlink()
        create_encrypted_zip(self.source, self.destination, "new-password")
        with pyzipper.AESZipFile(str(self.destination)) as archive:
            self.assertNotIn("WoWFishing/QUICKSTART.txt", archive.namelist())
            with self.assertRaises(RuntimeError):
                archive.read("WoWFishing/WoWFishing.exe", pwd=b"old-password")
            self.assertEqual(archive.read("WoWFishing/WoWFishing.exe", pwd=b"new-password"),
                             b"example executable")

    def test_empty_password_and_missing_source_leave_previous_zip_untouched(self):
        self.destination.write_bytes(b"previous release")
        with self.assertRaises(ValueError):
            create_encrypted_zip(self.source, self.destination, "")
        with self.assertRaises(FileNotFoundError):
            create_encrypted_zip(self.root / "missing", self.destination, "password")
        self.assertEqual(self.destination.read_bytes(), b"previous release")

    def test_write_failure_keeps_previous_zip_and_cleans_temporary_file(self):
        self.destination.write_bytes(b"previous release")
        before = set(self.root.iterdir())
        with patch.object(pyzipper.AESZipFile, "write", side_effect=OSError("Disk full")):
            with self.assertRaises(OSError):
                create_encrypted_zip(self.source, self.destination, "password")
        self.assertEqual(self.destination.read_bytes(), b"previous release")
        self.assertEqual(set(self.root.iterdir()), before)


if __name__ == "__main__":
    unittest.main()
