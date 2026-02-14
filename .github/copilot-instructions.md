# PaperScout: AI Coding Agent Instructions

## Project Overview

**PaperScout** is a PySide6 desktop application scaffold providing a QQ-like chat interface for multi-task, multi-model LLM interactions. The UI layout uses:
- **Left pane** (300px fixed): Task sidebar for selecting domains (forecasting, RL, paper digest)
- **Right pane** (expandable): Chat header + message view + composer with toolbar

**Key status**: UI scaffold with mock chat backend. Production hookup to DeepSeek/OpenAI/Gemini/豆包 APIs pending.

## Architecture Essentials

### Core Data Flow
1. **Settings** → LLM profiles (JSON config at `%APPDATA%/paperscout/settings.json`)
2. **ChatController** → In-memory message history (no persistence currently)
3. **UI Layer** → Components emit signals → MainWindow slots handle state updates
4. **Render Loop** → `MainWindow._refresh()` regenerates HTML from controller → ChatView display

### Key Components

| Module | Purpose | Pattern |
|--------|---------|---------|
| `config/settings.py` | Profile/agent config management | Lazy loading + format migration (v1→v5 backward compat) |
| `controllers/chat_controller.py` | Message accumulation + HTML rendering | Stateful controller with 200-message history window |
| `components/` | Reusable UI widgets | Signal-based composition (no inheritance chains) |
| `ui/menus/model_menu.py` | Dynamic profile/agent selection UI | Callback-driven menu building |
| `ui/settings/` | LLM config editor windows | Dialog-based CRUD for profiles/agents |

### Signal-Slot Architecture

**MainWindow** orchestrates via Qt signals (no global state):
```
Sidebar.task_changed → MainWindow.on_task_changed()
Composer.send_clicked → MainWindow.on_send()
Composer.model_clicked → MainWindow.open_profile_menu()
ChatHeader.settings_clicked → MainWindow.open_settings()
```

**Why this pattern**: Decouples components; each emits intent, MainWindow updates shared state (`self.settings`, `self.chat`).

## Critical Patterns & Conventions

### Settings/Config Hierarchy
```
settings["llm"] = {
    "active_profile_id": "p_xxxxx",
    "profiles": [
        {
            "id": "p_xxxxx",
            "name": "Config Set A",
            "default_agent": "deepseek",
            "agents": {
                "deepseek": {"model": "deepseek-chat", "api_key": "...", "temperature": 0.2, ...},
                "openai": {...},
                "google": {...},
                "doubao": {...}
            }
        }
    ]
}
```
**To use**: Call `MainWindow._llm()`, `_active_profile()`, `_active_default_agent_info()` helpers—**never access settings dict directly**.

### HTML Rendering for Chat
- **Location**: `ChatController.render_html(task_name, model_name)`
- **Pattern**: Escape user text → build inline-styled divs → return full HTML
- **Constraints**: Max 200 messages; UTF-8 safe; CSS is inline (no external sheets)

**When adding features**: Regenerate HTML via `self.chat.render_html()` then call `self.view.set_html_and_scroll_bottom(html)`.

### UI Component Composition
- **No inheritance**: Components are QWidget compositions using layouts + child widgets
- **Signal-only output**: Emit signals for parent to handle; accept `parent=None` param
- **Placeholder buttons**: Many toolbar icons (📥 📏 ▶️ 📤) have `icon_btn()` helpers; connect signals as needed

### State Updates
**Always call `self._refresh()` after mutations** to sync header subtitle, chat HTML, and message view:
```python
# Pattern: mutate settings → persist → add system message → _refresh()
self.settings["llm"]["active_profile_id"] = new_id
save_settings(self.settings)
self.chat.add("system", "Updated profile...")
self._refresh()
```

## Developer Workflows

### Run Development Mode
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m paperscout
```

### Add a New Feature
1. **UI Component**: Create in `ui/components/` as `my_feature.py` emitting signals
2. **Controller Logic**: Add methods to relevant controller or create new one
3. **Wire in MainWindow**: Connect signals to new slots; call `self._refresh()` when needed
4. **Persist if needed**: Save to `self.settings` via `save_settings()` in event handler

### Add LLM Provider Integration
1. **Define agent config**: Add entry to `DEFAULT_AGENT_CFG` in `config/settings.py`
2. **Settings UI**: Extend `LLMPage` form fields in `ui/settings/pages/llm_page.py` for new provider
3. **Invoke logic**: In `MainWindow.on_send()`, read `_active_default_agent_info()` and call provider API (replace mock response)

### Testing Note
**Current limitation**: No automated tests. Manual QA only. If adding critical logic, add docstrings + type hints.

## Conventions & Pitfalls

### DO
- Use `@dataclass` for structured data (ChatMessage, TaskItem)
- Prefix private methods with `_` (e.g., `_refresh()`, `_llm()`)
- Call `Signal(type1, type2)` with explicit types for slot clarity
- Escape HTML in `render_html()` helpers to prevent injection

### DON'T
- Modify `self.settings` without calling `save_settings()` afterward
- Access settings dict depth directly—use `_llm()`, `_active_profile()` helpers
- Hardcode window sizes; use `resize()` and `setFixedWidth()`
- Add new globals; store state in MainWindow instance vars only

### File Naming
- **Components**: `component_name.py` (snake_case)
- **Controllers**: `component_name_controller.py`
- **Dialogs**: `thing_dialog.py`

## Key Integration Points (Next Steps)

- **Mock → Real API**: Replace `on_send()` placeholder response with actual DeepSeek/OpenAI client calls
- **Message Persistence**: Add SQLite backend or load/save messages on startup
- **Streaming**: Wrap API calls in QThread to avoid UI blocking; emit progress signals
- **Advanced**: Task-specific system prompts, source imports, ranking UI in sidebar

## File Locations Cheat Sheet

| Purpose | Location |
|---------|----------|
| App entry | `__main__.py`, `app.py` |
| Main UI layout | `ui/main_window.py` |
| Chat state | `controllers/chat_controller.py` |
| Settings schema + I/O | `config/settings.py` |
| Reusable widgets | `ui/components/` |
| Profile menu builder | `ui/menus/model_menu.py` |
| QSS styles | `ui/styles.qss` |
| Settings dialog | `ui/settings/settings_window.py` + `pages/llm_page.py` |
