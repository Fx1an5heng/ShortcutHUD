"""Subprocess-only application wiring check with explicitly injected temp paths."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
from scripts.config_manager import ConfigManager
from scripts.full_guide_context import GuideSnapshot
from scripts.application_descriptor import ApplicationDescriptorFactory
from scripts.full_guide_hotkey import FullGuideHotkey, DEFAULT_GUIDE_HOTKEY


def run_probe():
    # No production store constructor is allowed to receive its default path.
    with TemporaryDirectory() as directory:
        root = Path(directory)
        shortcuts, settings = root / "shortcuts.json", root / "settings.json"
        users, selections = root / "user.json", root / "selection.json"
        config = ConfigManager(str(shortcuts), str(settings))
        config.initialize_configs()
        user_store = main.load_user_shortcut_store(users)
        user_store.save()
        selection_store = main.load_quick_hud_selection_store(selections)
        selection_store.set_selected_ids("SAMPLE.EXE", ["legacy.stale"])
        selection_store.set_selected_ids("EMPTY.EXE", [])
        selection_store.save()
        watched = (shortcuts, settings, users, selections)
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in watched}
        backend = Mock(last_error=1409)
        backend.register.return_value = True
        backend.altgr_down.return_value = False
        with patch.object(main, "ConfigManager", return_value=config), \
             patch.object(main, "load_user_shortcut_store", return_value=user_store), \
             patch.object(main, "load_quick_hud_selection_store", return_value=selection_store), \
             patch.object(main, "FullGuideHotkey", side_effect=lambda app, parent: FullGuideHotkey(app, parent, backend=backend)), \
             patch.object(main.KeyboardHandler, "start_listening"), \
             patch.object(main.WinDiscoveryProxy, "start", return_value=True), \
             patch.object(main.GuideWinInputService, "start", return_value=True), \
             patch.object(main.ApplicationIdentityRuntime, "start", return_value=True), \
             patch.object(main.ForegroundMonitor, "check_foreground_app"):
            app = main.ShortcutOverlayApplication([])
            try:
                assert app.full_guide_hotkey.spec.text == DEFAULT_GUIDE_HOTKEY
                app.full_guide_controller.context_provider = lambda: GuideSnapshot(
                    ApplicationDescriptorFactory().describe("NOTEPAD.EXE"),
                    0, "test", (0, 0, 1280, 800))
                app.full_guide_hotkey.handle_message(app.full_guide_hotkey.identifier)
                assert app.full_guide_controller.active
                app.full_guide_window.search_box.setText("save")
                app.full_guide_window._render_sections()
                app.full_guide_hotkey.handle_message(app.full_guide_hotkey.identifier)
                assert not app.full_guide_controller.active
                backend.register.return_value = False
                assert not app.apply_full_guide_hotkey("Ctrl+Shift+F9")[0]
                assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in watched} == before
                # Only an explicit, successfully registered change persists.
                backend.register.return_value = True
                assert app.apply_full_guide_hotkey("Ctrl+Shift+F9")[0]
                assert json.loads(settings.read_text())["full_guide_hotkey"] == "Ctrl+Shift+F9"
                assert all(p.read_bytes() == before[p][0] for p in (shortcuts, users, selections))
                print("FULL_GUIDE_STARTUP_NO_USER_WRITES_OK")
            finally:
                app.quit_application()


if __name__ == "__main__":
    run_probe()
