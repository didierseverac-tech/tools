Floating Quick Notes — Specification
Purpose: A lightweight always-on-top floating note window for jotting reminders while screening emails, without context-switching.
Core Behavior

Single-file Python script
On launch, opens a small always-on-top window (roughly 300×400px default)
Window is resizable and draggable, remembers last position and size between sessions
Global hotkey to toggle show/hide (default: Ctrl+Alt+N, configurable in .ini)
Starts minimized to system tray on Windows launch (optional, configurable)
Single-instance enforcement prevents multiple copies from running

Topics And Note Areas

Supports multiple topics instead of a single note
Each topic has its own scrollable plain-text editor, with no formatting
The top of the window contains a custom horizontal tab bar made from tk.Label widgets
Clicking a tab switches the single content area below to that topic's editor
Auto-saves each topic to its own local .txt file on every change (debounced, about 1 second after last keystroke)
Topic files are stored in a configurable notes folder, default: ~/Documents/quick_notes_topics
On launch, existing topic files in the notes folder are discovered and restored
If a legacy single notes file exists, its content is migrated into the General topic when appropriate

Tab Appearance And Colors

Each topic tab always shows its assigned background color
Active tab uses bolder text and slightly taller presentation
Inactive tabs keep the same background color with more muted text
Right-clicking a tab opens the context menu for that topic, including Change tab color
Each topic color is stored in the .ini file under a dedicated [Topics] section

Entry Log Mode (optional, togglable)

When enabled, pressing Enter twice (blank line) inserts a timestamp separator: --- 2026-05-16 14:32 ---
Useful for keeping a chronological log of notes during a mail screening session

UI

Minimal chrome: no menu bar, no toolbar
Semi-transparent background (opacity configurable, default 90%)
Right-click context menu with: Add topic, Rename topic, Delete topic, Change tab color, Clear all, Copy all, Toggle log mode, Open notes file in explorer, Settings, Quit
Uses a normal native window instead of custom borderless chrome
Closing the window quits the app cleanly

Configuration (.ini file)

hotkey — global toggle hotkey
notes_folder — folder containing one .txt file per topic
opacity — window opacity (0.5 to 1.0)
always_on_top — true/false
window_x, window_y, window_w, window_h — last geometry
log_mode — true/false for timestamp separators
start_minimized — true/false
topics — pipe-delimited ordered list of topic names
active_topic — currently selected topic on startup
legacy notes_file is still read as a migration fallback
The [Topics] section stores one color value per topic name
Default .ini created on first run if missing

System Tray

Tray icon with tooltip "Quick Notes"
Tray menu commands: Toggle, Show, Hide, Quit

Technical Notes

Python 3.10+, Windows 10/11
Tkinter for UI
pystray + Pillow for system tray
ctypes RegisterHotKey approach for the global hotkey
Config stored in a per-user local app-data folder, with legacy config fallback
Graceful shutdown saves note content and geometry on exit

Out of Scope

Rich text / markdown rendering
Cloud sync
Encryption
