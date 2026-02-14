from __future__ import annotations

# Backward-compatible shim:
# Some code/tools may import SettingsWindow from `paperscout.ui.settings_window`.
# The actual implementation lives in `paperscout.ui.settings.settings_window`.

from paperscout.ui.settings.settings_window import SettingsWindow

__all__ = ["SettingsWindow"]
