# PaperScout minimal patch overlay

This overlay zip contains only the smallest set of changes to fix a few issues:

1) Fix `ProfileEditorDialog.edit_profile` call signature mismatch (edit action would crash).
2) Improve robustness: tolerate non-numeric values in ProfileEditorDialog numeric fields.
3) Improve UI readability: QListWidget selected item keeps dark text (no white text), and Composer QSS selector matches actual widget type.
4) Improve ChatView: reliable scroll-to-bottom after setting HTML.
5) Provide a backward-compatible shim for `paperscout.ui.settings_window.SettingsWindow`.

How to apply:
- Unzip and overwrite the existing project root (same folder that contains `pyproject.toml`).
