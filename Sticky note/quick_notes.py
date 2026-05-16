changelog = [
    "1.00   16/05/26    Initial version",
    "1.01   16/05/26    Added floating quick notes UI, tray support, autosave, hotkey, and single-instance handling",
    "1.02   16/05/26    Added topic tabs with per-tab autosave and tab management",
    "1.03   16/05/26    Fixed frozen-app config persistence and prepared custom note icon support",
    "1.04   16/05/26    Improved shutdown handling to close cleanly from tray and quit actions",
    "1.05   16/05/26    Fixed quit persistence and applied runtime window icon",
    "1.06   16/05/26    Replaced legacy notes file setting with tab storage folder configuration",
    "1.07   16/05/26    Restore tabs by discovering note files in the configured notes folder",
    "1.08   16/05/26    Changed title-bar close action to quit instead of hiding to tray",
    "1.09   16/05/26    Use the frozen executable as the runtime icon source so the window shows the embedded app icon",
    "1.10   16/05/26    Force the custom window to appear as an app window in the Windows taskbar",
    "1.11   16/05/26    Replaced custom borderless chrome with a native window for reliable taskbar presence",
    "1.12   16/05/26    Moved config storage to a neutral per-user app-data folder with legacy fallback",
    "1.13   16/05/26    Explicitly enabled native window resizing with a minimum size"
]

import configparser as _configparser
import ctypes as _ctypes
import os as _os
import re as _re
import subprocess as _subprocess
import sys as _sys
import threading as _threading
from pathlib import Path as _Path

import tkinter as _tk
from tkinter import messagebox as _messagebox
from tkinter import simpledialog as _simpledialog
from tkinter import ttk as _ttk

from PIL import Image as _Image
from PIL import ImageDraw as _ImageDraw
import pystray as _pystray


APP_NAME = "Quick Notes"
APP_MUTEX_NAME = "QuickNotesSingleInstanceMutex"
APP_USER_MODEL_ID = "SchneiderElectric.QuickNotes"
GWL_EXSTYLE = -20
WS_EX_APPWINDOW = 0x00040000
WS_EX_TOOLWINDOW = 0x00000080
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_FRAMECHANGED = 0x0020
WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
ERROR_ALREADY_EXISTS = 183

VK_MAP = {
    "SPACE": 0x20,
    "TAB": 0x09,
    "ESC": 0x1B,
    "ESCAPE": 0x1B,
    "ENTER": 0x0D,
    "RETURN": 0x0D,
    "DELETE": 0x2E,
    "HOME": 0x24,
    "END": 0x23,
    "LEFT": 0x25,
    "RIGHT": 0x27,
    "UP": 0x26,
    "DOWN": 0x28,
}

DEFAULT_CONFIG = {
    "hotkey": "Ctrl+Alt+N",
    "notes_folder": str((_Path.home() / "Documents" / "quick_notes_topics").expanduser()),
    "opacity": "0.9",
    "always_on_top": "true",
    "window_x": "100",
    "window_y": "100",
    "window_w": "300",
    "window_h": "400",
    "log_mode": "false",
    "start_minimized": "false",
    "topics": "General",
    "active_topic": "General",
}


def _clamp(_value, _minimum, _maximum):
    """Clamp a numeric value to the given range."""
    return max(_minimum, min(_maximum, _value))


def _sanitize_topic_name(_topic_name):
    """Convert a topic name into a safe file stem."""
    _sanitized = _re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", _topic_name).strip()
    _sanitized = _sanitized.rstrip(". ")
    return _sanitized or "General"


def _get_app_directory():
    """Return a stable writable directory for config and assets."""
    if getattr(_sys, "frozen", False):
        return _Path(_sys.executable).resolve().parent
    return _Path(__file__).resolve().parent


def _get_config_directory():
    """Return a neutral per-user directory for Quick Notes settings."""
    _local_app_data = _os.environ.get("LOCALAPPDATA")
    if _local_app_data:
        return _Path(_local_app_data) / APP_NAME
    return _Path.home() / "AppData" / "Local" / APP_NAME


class _SingleInstance:
    """Prevent multiple copies of the application from running."""

    def __init__(self, _name):
        self._name = _name
        self._handle = None

    def acquire(self):
        """Acquire the mutex and return True if this is the primary instance."""
        _kernel32 = _ctypes.windll.kernel32
        self._handle = _kernel32.CreateMutexW(None, False, self._name)
        if not self._handle:
            raise OSError("Unable to create single-instance mutex.")
        return _kernel32.GetLastError() != ERROR_ALREADY_EXISTS

    def release(self):
        """Release the mutex if it was acquired."""
        if self._handle:
            _ctypes.windll.kernel32.CloseHandle(self._handle)
            self._handle = None


class _WindowsHotkey:
    """Register a Windows global hotkey and invoke a callback when pressed."""

    def __init__(self, _hotkey, _callback):
        self._hotkey = _hotkey
        self._callback = _callback
        self._thread = None
        self._thread_id = None
        self._registration_error = None
        self._hotkey_id = 1

    def start(self):
        """Start the message loop thread and attempt to register the hotkey."""
        self._thread = _threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the message loop and unregister the hotkey."""
        if self._thread_id:
            _ctypes.windll.user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _parse_hotkey(self):
        _parts = [part.strip().upper() for part in self._hotkey.split("+") if part.strip()]
        if len(_parts) < 2:
            raise ValueError(f"Unsupported hotkey: {self._hotkey}")

        _modifiers = 0
        for _part in _parts[:-1]:
            if _part == "CTRL":
                _modifiers |= MOD_CONTROL
            elif _part == "ALT":
                _modifiers |= MOD_ALT
            elif _part == "SHIFT":
                _modifiers |= MOD_SHIFT
            elif _part in {"WIN", "WINDOWS"}:
                _modifiers |= MOD_WIN
            else:
                raise ValueError(f"Unsupported hotkey modifier: {_part}")

        _key = _parts[-1]
        if len(_key) == 1 and _key.isalpha():
            _vk_code = ord(_key)
        elif len(_key) == 1 and _key.isdigit():
            _vk_code = ord(_key)
        elif _key.startswith("F") and _key[1:].isdigit():
            _fn_number = int(_key[1:])
            if 1 <= _fn_number <= 24:
                _vk_code = 0x6F + _fn_number
            else:
                raise ValueError(f"Unsupported hotkey key: {_key}")
        elif _key in VK_MAP:
            _vk_code = VK_MAP[_key]
        else:
            raise ValueError(f"Unsupported hotkey key: {_key}")

        return _modifiers, _vk_code

    def _run(self):
        _user32 = _ctypes.windll.user32
        _kernel32 = _ctypes.windll.kernel32
        self._thread_id = _kernel32.GetCurrentThreadId()

        try:
            _modifiers, _vk_code = self._parse_hotkey()
            if not _user32.RegisterHotKey(None, self._hotkey_id, _modifiers, _vk_code):
                raise OSError(f"Hotkey '{self._hotkey}' is unavailable.")

            _msg = _ctypes.wintypes.MSG()
            while _user32.GetMessageW(_ctypes.byref(_msg), None, 0, 0) != 0:
                if _msg.message == WM_HOTKEY:
                    self._callback()
                _user32.TranslateMessage(_ctypes.byref(_msg))
                _user32.DispatchMessageW(_ctypes.byref(_msg))
        except Exception as _exc:
            self._registration_error = _exc
        finally:
            try:
                _user32.UnregisterHotKey(None, self._hotkey_id)
            except Exception:
                pass


class QuickNotesApp:
    """Floating quick notes window with autosave, tray icon, and a global hotkey."""

    def __init__(self):
        self._script_dir = _get_app_directory()
        self._legacy_config_path = self._script_dir / "quick_notes.ini"
        self._config_path = _get_config_directory() / "quick_notes.ini"
        self._icon_path = self._script_dir / "quick_notes.ico"
        self._config = self._load_config()
        self._topics_dir = _Path(self._config["notes_folder"]).expanduser()
        self._legacy_notes_path = _Path(self._config["legacy_notes_file"]).expanduser()
        self._save_after_id = None
        self._geometry_after_id = None
        self._tray_icon = None
        self._is_visible = False
        self._is_quitting = False
        self._resize_origin = None
        self._tab_widgets = {}
        self._topic_files = {}
        self._active_topic = self._config["active_topic"]

        self._sync_topics_with_folder()

        self._root = _tk.Tk()
        self._root.title(APP_NAME)
        self._root.configure(bg="#d9d0bf")
        self._root.minsize(240, 220)
        self._root.resizable(True, True)
        self._apply_window_icon()
        self._root.attributes("-alpha", self._config["opacity"])
        self._root.attributes("-topmost", self._config["always_on_top"])
        self._apply_geometry()
        self._build_ui()
        self._load_notes()
        self._register_bindings()
        self._create_tray_icon()
        self._hotkey = _WindowsHotkey(self._config["hotkey"], self._schedule_toggle)
        self._hotkey.start()

        if self._config["start_minimized"]:
            self.hide_window()
        else:
            self.show_window()

        self._root.after(300, self._warn_if_hotkey_failed)

    def run(self):
        """Start the Tkinter event loop."""
        self._root.mainloop()

    def _load_config(self):
        _parser = _configparser.ConfigParser()
        _parser["QuickNotes"] = DEFAULT_CONFIG.copy()
        if self._config_path.exists():
            _parser.read(self._config_path, encoding="utf-8")
        elif self._legacy_config_path.exists():
            _parser.read(self._legacy_config_path, encoding="utf-8")
        else:
            self._write_config(_parser)

        _section = _parser["QuickNotes"]
        _legacy_notes_file = _section.get("notes_file", "").strip()
        _notes_folder = _section.get("notes_folder", "").strip()
        if not _notes_folder:
            if _legacy_notes_file:
                _legacy_path = _Path(_legacy_notes_file).expanduser()
                _notes_folder = str(_legacy_path.with_suffix("").parent / f"{_legacy_path.with_suffix('').name}_topics")
            else:
                _notes_folder = DEFAULT_CONFIG["notes_folder"]

        _config = {
            "hotkey": _section.get("hotkey", DEFAULT_CONFIG["hotkey"]),
            "notes_folder": _notes_folder,
            "legacy_notes_file": _legacy_notes_file or str((_Path.home() / "Documents" / "quick_notes.txt").expanduser()),
            "opacity": _clamp(_section.getfloat("opacity", fallback=0.9), 0.5, 1.0),
            "always_on_top": _section.getboolean("always_on_top", fallback=True),
            "window_x": _section.getint("window_x", fallback=100),
            "window_y": _section.getint("window_y", fallback=100),
            "window_w": max(_section.getint("window_w", fallback=300), 240),
            "window_h": max(_section.getint("window_h", fallback=400), 220),
            "log_mode": _section.getboolean("log_mode", fallback=False),
            "start_minimized": _section.getboolean("start_minimized", fallback=False),
            "topics": [
                _topic.strip() for _topic in _section.get("topics", DEFAULT_CONFIG["topics"]).split("|") if _topic.strip()
            ] or ["General"],
            "active_topic": _section.get("active_topic", DEFAULT_CONFIG["active_topic"]),
        }
        if _config["active_topic"] not in _config["topics"]:
            _config["active_topic"] = _config["topics"][0]
        return _config

    def _write_config(self, _parser=None):
        if _parser is None:
            _parser = _configparser.ConfigParser()
            _parser["QuickNotes"] = {
                "hotkey": self._config["hotkey"],
                "notes_folder": str(self._topics_dir),
                "opacity": f"{self._config['opacity']:.2f}",
                "always_on_top": str(self._config["always_on_top"]).lower(),
                "window_x": str(self._config["window_x"]),
                "window_y": str(self._config["window_y"]),
                "window_w": str(self._config["window_w"]),
                "window_h": str(self._config["window_h"]),
                "log_mode": str(self._config["log_mode"]).lower(),
                "start_minimized": str(self._config["start_minimized"]).lower(),
                "topics": "|".join(self._config["topics"]),
                "active_topic": self._active_topic,
            }

        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        _tmp_path = self._config_path.with_suffix(".tmp")
        with _tmp_path.open("w", encoding="utf-8") as _file_handle:
            _parser.write(_file_handle)
        _tmp_path.replace(self._config_path)

    def _sync_topics_with_folder(self):
        self._topics_dir.parent.mkdir(parents=True, exist_ok=True)
        self._topics_dir.mkdir(parents=True, exist_ok=True)

        _discovered_topics = []
        for _topic_path in sorted(self._topics_dir.glob("*.txt")):
            if _topic_path.stem:
                _discovered_topics.append(_topic_path.stem)

        _updated_topics = list(self._config["topics"])
        for _topic_name in _discovered_topics:
            if _topic_name not in _updated_topics:
                _updated_topics.append(_topic_name)

        if not _updated_topics:
            _updated_topics = ["General"]

        _config_changed = _updated_topics != self._config["topics"]
        self._config["topics"] = _updated_topics

        if self._active_topic not in self._config["topics"]:
            self._active_topic = self._config["topics"][0]
            _config_changed = True

        if _config_changed:
            self._write_config()

    def _apply_geometry(self):
        _geometry = (
            f"{self._config['window_w']}x{self._config['window_h']}"
            f"+{self._config['window_x']}+{self._config['window_y']}"
        )
        self._root.geometry(_geometry)

    def _apply_window_icon(self):
        try:
            _ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        except Exception:
            pass

        _icon_source = None
        if getattr(_sys, "frozen", False):
            _icon_source = _sys.executable
        elif self._icon_path.exists():
            _icon_source = str(self._icon_path)

        if _icon_source:
            try:
                self._root.iconbitmap(default=_icon_source)
            except Exception:
                pass

    def _configure_taskbar_window(self):
        try:
            self._root.update_idletasks()
            _hwnd = self._root.winfo_id()
            _user32 = _ctypes.windll.user32
            _ex_style = _user32.GetWindowLongW(_hwnd, GWL_EXSTYLE)
            _ex_style = (_ex_style | WS_EX_APPWINDOW) & ~WS_EX_TOOLWINDOW
            _user32.SetWindowLongW(_hwnd, GWL_EXSTYLE, _ex_style)
            _user32.SetWindowPos(
                _hwnd,
                0,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED,
            )
        except Exception:
            pass

    def _build_ui(self):
        self._container = _tk.Frame(self._root, bg="#efe7d8", bd=1, relief="solid")
        self._container.pack(fill="both", expand=True)

        self._notebook = _ttk.Notebook(self._container)
        self._notebook.pack(fill="both", expand=True, padx=6, pady=6)
        self._notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self._context_menu = _tk.Menu(self._root, tearoff=0)
        self._context_menu.add_command(label="Add topic", command=self._add_topic)
        self._context_menu.add_command(label="Rename topic", command=self._rename_topic)
        self._context_menu.add_command(label="Delete topic", command=self._delete_topic)
        self._context_menu.add_separator()
        self._context_menu.add_command(label="Clear all", command=self._clear_all)
        self._context_menu.add_command(label="Copy all", command=self._copy_all)
        self._context_menu.add_command(label="Toggle log mode", command=self._toggle_log_mode)
        self._context_menu.add_command(label="Open notes file in explorer", command=self._open_notes_file)
        self._context_menu.add_command(label="Settings", command=self._open_settings)
        self._context_menu.add_separator()
        self._context_menu.add_command(label="Quit", command=self.quit_app)

    def _register_bindings(self):
        self._root.bind("<Configure>", self._on_configure)
        self._root.bind("<Button-3>", self._show_context_menu)
        self._root.protocol("WM_DELETE_WINDOW", self.quit_app)

    def _load_notes(self):
        self._topics_dir.parent.mkdir(parents=True, exist_ok=True)
        self._topics_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_topic_files()

        for _topic_name in self._config["topics"]:
            self._create_topic_tab(_topic_name)

        if self._active_topic in self._tab_widgets:
            self._notebook.select(self._tab_widgets[self._active_topic]["frame"])
        self._focus_active_text()

    def _ensure_topic_files(self):
        _legacy_migrated = False
        if self._legacy_notes_path.exists() and not any(self._topics_dir.glob("*.txt")):
            _general_path = self._topic_file_path("General")
            _general_path.write_text(self._legacy_notes_path.read_text(encoding="utf-8"), encoding="utf-8")
            _legacy_migrated = True

        for _topic_name in self._config["topics"]:
            _topic_path = self._topic_file_path(_topic_name)
            self._topic_files[_topic_name] = _topic_path
            if not _topic_path.exists():
                if _topic_name == "General" and self._legacy_notes_path.exists() and not _legacy_migrated:
                    _topic_path.write_text(self._legacy_notes_path.read_text(encoding="utf-8"), encoding="utf-8")
                else:
                    _topic_path.write_text("", encoding="utf-8")

    def _topic_file_path(self, _topic_name):
        return self._topics_dir / f"{_sanitize_topic_name(_topic_name)}.txt"

    def _create_topic_tab(self, _topic_name, _content=None):
        _frame = _tk.Frame(self._notebook, bg="#efe7d8")
        _scrollbar = _tk.Scrollbar(_frame)
        _scrollbar.pack(side="right", fill="y")

        _text_widget = _tk.Text(
            _frame,
            wrap="word",
            yscrollcommand=_scrollbar.set,
            undo=True,
            relief="flat",
            bd=0,
            padx=10,
            pady=10,
            font=("Segoe UI", 10),
            bg="#fbf7ef",
            fg="#1f1f1f",
            insertbackground="#1f1f1f",
        )
        _text_widget.pack(side="left", fill="both", expand=True)
        _scrollbar.config(command=_text_widget.yview)
        _text_widget.bind("<<Modified>>", self._on_text_modified)
        _text_widget.bind("<Return>", self._handle_return, add="+")
        _text_widget.bind("<Button-3>", self._show_context_menu)

        if _content is None:
            _topic_path = self._topic_files.setdefault(_topic_name, self._topic_file_path(_topic_name))
            _content = _topic_path.read_text(encoding="utf-8") if _topic_path.exists() else ""

        _text_widget.insert("1.0", _content)
        _text_widget.edit_modified(False)
        self._notebook.add(_frame, text=_topic_name)
        self._tab_widgets[_topic_name] = {
            "frame": _frame,
            "text": _text_widget,
        }

    def _active_text_widget(self):
        return self._tab_widgets[self._active_topic]["text"]

    def _focus_active_text(self):
        self._active_text_widget().focus_set()

    def _save_notes(self):
        self._topics_dir.parent.mkdir(parents=True, exist_ok=True)
        self._topics_dir.mkdir(parents=True, exist_ok=True)
        for _topic_name, _widgets in self._tab_widgets.items():
            _topic_path = self._topic_files.setdefault(_topic_name, self._topic_file_path(_topic_name))
            _tmp_path = _topic_path.with_suffix(_topic_path.suffix + ".tmp")
            _content = _widgets["text"].get("1.0", "end-1c")
            _tmp_path.write_text(_content, encoding="utf-8")
            _tmp_path.replace(_topic_path)
        self._save_after_id = None

    def _schedule_save(self):
        if self._save_after_id:
            self._root.after_cancel(self._save_after_id)
        self._save_after_id = self._root.after(1000, self._save_notes)

    def _on_text_modified(self, _event=None):
        _text_widget = _event.widget if _event else None
        if _text_widget and _text_widget.edit_modified():
            _text_widget.edit_modified(False)
            self._schedule_save()

    def _handle_return(self, _event=None):
        if not self._config["log_mode"]:
            return None
        self._root.after_idle(self._maybe_insert_timestamp_separator)
        return None

    def _maybe_insert_timestamp_separator(self):
        try:
            _text_widget = self._active_text_widget()
            _line_number = int(_text_widget.index("insert").split(".")[0])
        except Exception:
            return

        if _line_number < 3:
            return

        _previous_line = _text_widget.get(f"{_line_number - 1}.0", f"{_line_number - 1}.end").strip()
        _prior_line = _text_widget.get(f"{_line_number - 2}.0", f"{_line_number - 2}.end").strip()

        if _previous_line == "" and _prior_line == "":
            _timestamp = self._current_timestamp()
            _text_widget.insert("insert", f"--- {_timestamp} ---\n")
            _text_widget.see("insert")
            self._schedule_save()

    def _current_timestamp(self):
        from datetime import datetime as _datetime

        return _datetime.now().strftime("%Y-%m-%d %H:%M")

    def _show_context_menu(self, _event):
        _topic_count = len(self._config["topics"])
        _toggle_label = "Disable log mode" if self._config["log_mode"] else "Enable log mode"
        self._context_menu.entryconfig(1, state="normal" if _topic_count > 0 else "disabled")
        self._context_menu.entryconfig(2, state="normal" if _topic_count > 1 else "disabled")
        self._context_menu.entryconfig(6, label=_toggle_label)
        self._context_menu.tk_popup(_event.x_root, _event.y_root)

    def _clear_all(self):
        if _messagebox.askyesno(APP_NAME, "Clear all notes?"):
            self._active_text_widget().delete("1.0", "end")
            self._schedule_save()

    def _copy_all(self):
        _content = self._active_text_widget().get("1.0", "end-1c")
        self._root.clipboard_clear()
        self._root.clipboard_append(_content)

    def _add_topic(self):
        _topic_name = _simpledialog.askstring(APP_NAME, "New topic name:", parent=self._root)
        if not _topic_name:
            return
        _topic_name = _topic_name.strip()
        if not _topic_name:
            return
        if _topic_name in self._tab_widgets:
            _messagebox.showwarning(APP_NAME, f"Topic '{_topic_name}' already exists.")
            return

        self._config["topics"].append(_topic_name)
        self._topic_files[_topic_name] = self._topic_file_path(_topic_name)
        self._topic_files[_topic_name].write_text("", encoding="utf-8")
        self._create_topic_tab(_topic_name, _content="")
        self._active_topic = _topic_name
        self._notebook.select(self._tab_widgets[_topic_name]["frame"])
        self._write_config()
        self._focus_active_text()

    def _rename_topic(self):
        _old_name = self._active_topic
        _new_name = _simpledialog.askstring(APP_NAME, "Rename topic:", initialvalue=_old_name, parent=self._root)
        if not _new_name:
            return
        _new_name = _new_name.strip()
        if not _new_name or _new_name == _old_name:
            return
        if _new_name in self._tab_widgets:
            _messagebox.showwarning(APP_NAME, f"Topic '{_new_name}' already exists.")
            return

        _old_path = self._topic_files[_old_name]
        _new_path = self._topic_file_path(_new_name)
        if _new_path.exists():
            _messagebox.showwarning(APP_NAME, f"A file already exists for topic '{_new_name}'.")
            return

        _old_path.replace(_new_path)
        _widgets = self._tab_widgets.pop(_old_name)
        self._tab_widgets[_new_name] = _widgets
        self._topic_files.pop(_old_name)
        self._topic_files[_new_name] = _new_path
        _topic_index = self._config["topics"].index(_old_name)
        self._config["topics"][_topic_index] = _new_name
        self._active_topic = _new_name
        self._notebook.tab(_widgets["frame"], text=_new_name)
        self._write_config()

    def _delete_topic(self):
        if len(self._config["topics"]) == 1:
            _messagebox.showwarning(APP_NAME, "At least one topic tab must remain.")
            return
        _topic_name = self._active_topic
        if not _messagebox.askyesno(APP_NAME, f"Delete topic '{_topic_name}'?"):
            return

        _widgets = self._tab_widgets.pop(_topic_name)
        self._notebook.forget(_widgets["frame"])
        _topic_path = self._topic_files.pop(_topic_name)
        if _topic_path.exists():
            _topic_path.unlink()
        self._config["topics"].remove(_topic_name)
        self._active_topic = self._config["topics"][0]
        self._notebook.select(self._tab_widgets[self._active_topic]["frame"])
        self._save_notes()
        self._write_config()
        self._focus_active_text()

    def _toggle_log_mode(self):
        self._config["log_mode"] = not self._config["log_mode"]
        self._write_config()

    def _open_notes_file(self):
        self._save_notes()
        _subprocess.Popen(["explorer", f"/select,{self._topic_files[self._active_topic]}"])

    def _open_settings(self):
        self._write_config()
        _os.startfile(str(self._config_path))

    def _start_drag(self, _event):
        self._drag_origin = (_event.x_root, _event.y_root)
        self._window_origin = (self._root.winfo_x(), self._root.winfo_y())

    def _perform_drag(self, _event):
        _delta_x = _event.x_root - self._drag_origin[0]
        _delta_y = _event.y_root - self._drag_origin[1]
        self._root.geometry(
            f"{self._root.winfo_width()}x{self._root.winfo_height()}"
            f"+{self._window_origin[0] + _delta_x}+{self._window_origin[1] + _delta_y}"
        )

    def _start_resize(self, _event):
        self._resize_origin = {
            "x": _event.x_root,
            "y": _event.y_root,
            "width": self._root.winfo_width(),
            "height": self._root.winfo_height(),
        }

    def _perform_resize(self, _event):
        if not self._resize_origin:
            return
        _new_width = max(self._resize_origin["width"] + (_event.x_root - self._resize_origin["x"]), 240)
        _new_height = max(self._resize_origin["height"] + (_event.y_root - self._resize_origin["y"]), 220)
        self._root.geometry(f"{_new_width}x{_new_height}+{self._root.winfo_x()}+{self._root.winfo_y()}")

    def _on_configure(self, _event=None):
        if self._geometry_after_id:
            self._root.after_cancel(self._geometry_after_id)
        self._geometry_after_id = self._root.after(300, self._persist_window_state)

    def _persist_window_state(self):
        self._config["window_x"] = self._root.winfo_x()
        self._config["window_y"] = self._root.winfo_y()
        self._config["window_w"] = self._root.winfo_width()
        self._config["window_h"] = self._root.winfo_height()
        self._write_config()
        self._geometry_after_id = None

    def _on_tab_changed(self, _event=None):
        _selected_tab = self._notebook.select()
        for _topic_name, _widgets in self._tab_widgets.items():
            if str(_widgets["frame"]) == _selected_tab:
                self._active_topic = _topic_name
                self._write_config()
                self._focus_active_text()
                break

    def _create_tray_icon(self):
        _image = _Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        _draw = _ImageDraw.Draw(_image)
        _draw.rounded_rectangle((8, 8, 56, 56), radius=10, fill=(239, 231, 216, 255), outline=(117, 95, 73, 255), width=3)
        _draw.line((18, 24, 46, 24), fill=(117, 95, 73, 255), width=4)
        _draw.line((18, 34, 46, 34), fill=(117, 95, 73, 255), width=4)
        _draw.line((18, 44, 38, 44), fill=(117, 95, 73, 255), width=4)

        _menu = _pystray.Menu(
            _pystray.MenuItem("Toggle", self._tray_toggle, default=True),
            _pystray.MenuItem("Show", self._tray_show),
            _pystray.MenuItem("Hide", self._tray_hide),
            _pystray.MenuItem("Quit", self._tray_quit),
        )
        self._tray_icon = _pystray.Icon("quick_notes", _image, APP_NAME, _menu)
        self._tray_icon.run_detached()

    def _tray_toggle(self, _icon=None, _item=None):
        self._schedule_toggle()

    def _tray_show(self, _icon=None, _item=None):
        self._queue_ui_action(self.show_window)

    def _tray_hide(self, _icon=None, _item=None):
        self._queue_ui_action(self.hide_window)

    def _tray_quit(self, _icon=None, _item=None):
        self._queue_ui_action(self.quit_app)

    def _queue_ui_action(self, _callback):
        if self._is_quitting:
            return
        try:
            if self._root.winfo_exists():
                self._root.after(0, _callback)
        except _tk.TclError:
            pass

    def _schedule_toggle(self):
        self._queue_ui_action(self.toggle_window)

    def toggle_window(self):
        if self._is_visible:
            self.hide_window()
        else:
            self.show_window()

    def show_window(self):
        self._root.deiconify()
        self._root.attributes("-topmost", self._config["always_on_top"])
        self._root.lift()
        self._root.focus_force()
        try:
            _ctypes.windll.user32.SetForegroundWindow(self._root.winfo_id())
        except Exception:
            pass
        self._is_visible = True

    def hide_window(self):
        self._persist_before_hide()
        self._root.withdraw()
        self._is_visible = False

    def _persist_before_hide(self):
        if self._save_after_id:
            self._root.after_cancel(self._save_after_id)
            self._save_after_id = None
            self._save_notes()
        if self._geometry_after_id:
            self._root.after_cancel(self._geometry_after_id)
            self._geometry_after_id = None
        self._persist_window_state()

    def _warn_if_hotkey_failed(self):
        if self._hotkey._registration_error:
            _messagebox.showwarning(APP_NAME, str(self._hotkey._registration_error))

    def quit_app(self):
        if self._is_quitting:
            return

        try:
            self._persist_before_hide()
        finally:
            self._is_quitting = True
            try:
                self._hotkey.stop()
            except Exception:
                pass

            try:
                if self._tray_icon:
                    self._tray_icon.visible = False
                    self._tray_icon.stop()
            except Exception:
                pass

            try:
                if self._root.winfo_exists():
                    self._root.quit()
                    self._root.destroy()
            except _tk.TclError:
                pass


def main():
    """Run the Quick Notes application."""
    if _sys.platform != "win32":
        raise OSError("Quick Notes currently supports Windows only.")

    _instance = _SingleInstance(APP_MUTEX_NAME)
    if not _instance.acquire():
        _messagebox.showinfo(APP_NAME, "Quick Notes is already running.")
        return 0

    try:
        _app = QuickNotesApp()
        _app.run()
    finally:
        _instance.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())