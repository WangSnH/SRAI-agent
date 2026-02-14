# PaperScout (UI scaffold)

A PySide6 desktop app scaffold with a QQ-like layout:
- Left: big selection list (models)
- Right: top message/display area
- Right: bottom chat composer area with a small toolbar and send button

## Run (dev)
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m paperscout
```

## Next steps
- Replace mock "send message" with pipeline hooks
- Add sources tab/imports in the left pane or toolbar
- Add settings persistence
