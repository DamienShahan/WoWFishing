"""Windows Tk lifecycle checks with fake devices and no real keyboard input."""
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch, Mock

from app_settings import load
import gui
from windows_control import GameWindow


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.path = Path(self.directory.name) / "settings.yaml"
        self.window = GameWindow(123, 44, "World of Warcraft")
        backend = Mock()
        backend.__enter__ = Mock(return_value=backend)
        backend.__exit__ = Mock(return_value=False)
        backend.p.get_loopback_device_info_generator.return_value = iter([])
        self.patches = [patch("gui.list_windows", return_value=[self.window]),
                        patch("gui.AudioBackend", return_value=backend)]
        for p in self.patches:
            p.start()
        gui.ctk.set_appearance_mode("dark")
        self.app = gui.App(self.path)
        self.app.withdraw()
        self.pump(.3)

    def pump(self, duration):
        end = time.monotonic() + duration
        while time.monotonic() < end:
            self.app.update()
            time.sleep(.01)

    def tearDown(self):
        try:
            if self.app.winfo_exists():
                if self.app.session:
                    self.app.session.stop()
                    self.app.worker.join(2)
                # CTk schedules global DPI callbacks; cancel them before creating
                # the next test's independent Tcl interpreter.
                for callback in self.app.tk.call("after", "info"):
                    self.app.tk.call("after", "cancel", callback)
                self.app.destroy()
        finally:
            for p in reversed(self.patches):
                p.stop()
            self.directory.cleanup()

    def test_settings_validation_and_persistence(self):
        self.app.open_settings()
        dialog = self.app.dialog
        self.pump(.15)
        entry = dialog.entries["ACTION_KEY"][0]
        entry.delete(0, "end")
        entry.insert(0, "not a key")
        dialog.commit()
        self.assertIn("ACTION_KEY", dialog.error.cget("text"))
        entry.delete(0, "end")
        entry.insert(0, "f2")
        dialog.commit()
        self.assertEqual(load(self.path)["ACTION_KEY"], "f2")
        self.assertEqual(self.app.settings["ACTION_KEY"], "f2")

    def test_stop_button_waits_for_worker_then_can_restart(self):
        sessions = []

        class Session:
            def __init__(self, cfg, window, emit):
                from threading import Event
                self.stop_event = Event()
                self.emit = emit
                sessions.append(self)

            def run(self):
                self.emit("state", "Listening")
                self.stop_event.wait(2)
                self.emit("done", None)

            def stop(self):
                self.stop_event.set()

        with patch("gui.BotSession", Session):
            for _ in range(2):
                self.app.toggle()
                self.assertIsNotNone(self.app.worker)
                self.assertEqual(self.app.settings_button.cget("state"), "disabled")
                self.app.toggle()
                self.pump(.2)
                self.assertIsNone(self.app.worker)
                self.assertEqual(self.app.start_button.cget("state"), "normal")
        self.assertEqual(len(sessions), 2)

    def test_missing_saved_device_needs_explicit_selection(self):
        self.app.settings["OUTPUT_DEVICE_NAME"] = "Disconnected output"
        self.app.settings["OUTPUT_DEVICE_INDEX"] = 99
        self.app.discovered(([self.window], [], []))
        self.assertNotIn(self.app.audio_combo.get(), self.app.devices)
        with patch("gui.messagebox.showerror") as error:
            self.app.toggle()
        error.assert_called_once()
        self.assertIsNone(self.app.worker)

    def test_failed_sessions_show_cards_and_summary_and_can_restart(self):
        from bot import BotSession

        def session(cfg, window, emit):
            return BotSession(cfg, window, emit, keyboard=Mock(),
                              detector_factory=Mock(side_effect=RuntimeError("Missing references")))

        with patch("gui.BotSession", side_effect=session):
            for count in (1, 2):
                self.app.toggle()
                self.pump(.2)
                self.assertIsNone(self.app.worker)
                events = [card.event for card in self.app.activity.cards]
                self.assertTrue(any(event["kind"] == "error" and event["body"] == "Missing references" for event in events))
                summaries = [event for event in events if event["kind"] == "summary"]
                self.assertEqual(len(summaries), count)
                self.assertEqual(summaries[0]["body"], "Stopped because of an error.")
                self.assertIn(("Casts", 0), summaries[0]["stats"])
                self.assertEqual(self.app.activity.current_title.cget("text"), "Session stopped with an error")

    def test_activity_details_history_limit_and_clear_preserve_status(self):
        feed = self.app.activity
        feed.MAX_CARDS = 3
        for count in range(5):
            feed.add({"kind": "cast", "title": f"Cast {count}", "body": "Waiting for a bite.",
                      "details": "Match score and reference go here."})
        self.pump(.1)
        self.assertEqual([card.event["title"] for card in feed.cards], ["Cast 4", "Cast 3", "Cast 2"])
        latest = feed.cards[0]
        self.assertFalse(latest.details_visible)
        latest.toggle_details()
        self.assertTrue(latest.details_visible)
        self.assertTrue(latest.details.winfo_manager())
        latest.toggle_details()
        self.assertFalse(latest.details.winfo_manager())
        self.app.clear_log()
        self.assertEqual(feed.cards, [])
        self.assertEqual(feed.current_title.cget("text"), "Cast 4")

    def test_summary_is_one_card_and_history_does_not_replace_current_status(self):
        feed = self.app.activity
        feed.summary({"elapsed": 3661, "reason": "Stopped by user.", "failed": False,
                      "casts": 8, "bites": 5, "timeouts": 2, "interrupted": 1, "lures": 1})
        self.pump(.1)
        self.assertEqual(feed.cards[0].event["title"], "Session summary")
        self.assertIn(("Run time", "01:01:01"), feed.cards[0].event["stats"])
        self.app.log("Saved.", title="Settings saved", current=False)
        self.assertEqual(feed.current_title.cget("text"), "Session ended")


if __name__ == "__main__":
    unittest.main()
