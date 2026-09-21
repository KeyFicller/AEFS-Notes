# DeskPet Selection Chip Implementation Plan

> **For agentic workers:** Implement task-by-task. Steps use checkbox syntax.

**Goal:** After text selection, show a clickable chip near the cursor that triggers the existing explain bubble (Easydict-style, click only).

**Architecture:** Global/local `leftMouseUp` → AX selected text → `SelectionChipPanel` → click → reuse `explainDroppedText`.

**Tech Stack:** AppKit, ApplicationServices (AX), existing ExplainClient / SpeechBubble.

## Global Constraints

- Click to explain only (no hover trigger)
- AX only (no Force ⌘C)
- Keep drag-to-pet path
- Cache selected text before chip click (avoid focus loss clearing selection)

---

### Task 1: SelectionWatcher + SelectionChipPanel

**Files:**
- Create `deskpet/native/SelectionWatcher.swift`
- Create `deskpet/native/SelectionChipPanel.swift`
- Modify `deskpet/__main__.py` — add `-framework ApplicationServices`

- [ ] Implement AX selected-text read + mouseUp debounce
- [ ] Implement 28×28 chip panel with tap callback + timeout hide
- [ ] Compile with ApplicationServices

### Task 2: Wire AppDelegate + menu

**Files:**
- Modify `deskpet/native/main.swift`

- [ ] Start watcher on launch; onTap → `explainDroppedText`
- [ ] Ignore selections over DeskPet windows
- [ ] Right-click menu: 授予辅助功能权限…
- [ ] Compile and smoke-check
