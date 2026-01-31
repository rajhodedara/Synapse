import sys
import os
import traceback
import time
import json
import keyboard

# PyQt6 Imports
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QObject, pyqtSignal # Required for thread safety

# Core Imports
from core.window_manager import WindowManager, TileMode
from core.hotkeys import register_hotkeys
from core.launcher import Launcher
from core.tray import setup_tray 

# Windows Specifics
import ctypes 
from win32event import CreateMutex
from win32api import GetLastError
from winerror import ERROR_ALREADY_EXISTS

# --- 1. THREAD BRIDGE (The Fix) ---
# Signals must be defined in a class inheriting from QObject
class HotkeyBridge(QObject):
    # Define a signal for every action you need to trigger from a hotkey
    show_launcher_sig = pyqtSignal()
    open_clip_sig = pyqtSignal()
    
    # Window Manager Signals (Optional but recommended for stability)
    tile_sig = pyqtSignal(object) # Pass the TileMode
    grid_sig = pyqtSignal(str)    # Pass a string ID for the grid position

# --- 2. SYSTEM INITIALIZATION ---
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()

if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))
os.chdir(application_path)

# Single Instance Check
mutex = CreateMutex(None, False, "Global\\KeyboardOS_Daemon_v3")
if GetLastError() == ERROR_ALREADY_EXISTS:
    sys.exit(0)

CONFIG_PATH = "config.json"

def load_config():
    try:
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"theme": {"font": "Segoe UI", "font_size": 20, "width": 640}}

def main():
    qt_app = QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)

    config = load_config()

    # --- INITIALIZE MODULES ---
    wm = WindowManager()
    launcher = Launcher(config)
    
    # Initialize the Bridge
    bridge = HotkeyBridge()

    # --- CONNECT SIGNALS (Thread -> UI) ---
    # When the signal fires, PyQt runs the function on the Main Thread safely
    bridge.show_launcher_sig.connect(lambda: launcher.show_launcher())
    bridge.open_clip_sig.connect(lambda: launcher.open_clip_mode())
    
    # We can also bridge the WM calls if they touch GUI
    bridge.tile_sig.connect(lambda mode: wm.tile(mode))
    
    tray = setup_tray(qt_app, on_quit=lambda: qt_app.quit())

    # =========================================================================
    #  HOTKEYS (The Controller Layer)
    # =========================================================================
    
    # NOTE: We now emit signals instead of calling functions directly.
    # 'suppress=True' stops the keys from reaching other apps (optional but good for global hotkeys)

    # --- 1. LAUNCHER TRIGGERS ---
    keyboard.add_hotkey('ctrl+space', bridge.show_launcher_sig.emit, suppress=True)
    keyboard.add_hotkey('alt+v', bridge.open_clip_sig.emit, suppress=True)

    # --- 2. WINDOW MANAGER ---
    # We bridge these too just to be safe, though WM often uses pure Win32 API (which is thread-neutral)
    # If wm.tile() touches PyQt widgets, you MUST use the bridge. If it only uses win32gui, you can call direct.
    # Assuming direct is fine for WM if it's pure Win32, but here is the bridge pattern:
    
    keyboard.add_hotkey('win+alt+left', lambda: wm.tile(TileMode.LEFT_HALF), suppress=True)
    keyboard.add_hotkey('win+alt+right', lambda: wm.tile(TileMode.RIGHT_HALF), suppress=True)
    keyboard.add_hotkey('win+alt+up', lambda: wm.tile(TileMode.MAXIMIZE), suppress=True)
    keyboard.add_hotkey('win+alt+down', lambda: wm.tile(TileMode.CENTER), suppress=True)

    # Vim Keys (HJKL)
    keyboard.add_hotkey('win+alt+h', lambda: wm.tile(TileMode.LEFT_HALF), suppress=True)
    keyboard.add_hotkey('win+alt+l', lambda: wm.tile(TileMode.RIGHT_HALF), suppress=True)
    keyboard.add_hotkey('win+alt+k', lambda: wm.tile(TileMode.MAXIMIZE), suppress=True)
    keyboard.add_hotkey('win+alt+j', lambda: wm.tile(TileMode.CENTER), suppress=True)

    # Grid System
    keyboard.add_hotkey('ctrl+alt+1', lambda: wm.grid_top_left())
    keyboard.add_hotkey('ctrl+alt+2', lambda: wm.grid_top_right())
    keyboard.add_hotkey('ctrl+alt+3', lambda: wm.grid_bottom_left())
    keyboard.add_hotkey('ctrl+alt+4', lambda: wm.grid_bottom_right())

    # Power User Features
    keyboard.add_hotkey('win+alt+z', lambda: wm.undo())
    keyboard.add_hotkey('win+alt+m', lambda: wm.move_to_next_monitor())
    
    # Transparency
    keyboard.add_hotkey('win+alt+o', lambda: wm.set_transparency(200))
    keyboard.add_hotkey('win+alt+p', lambda: wm.set_transparency(255))

    # --- 3. CUSTOM HOTKEYS ---
    register_hotkeys(config)

    # --- START EXECUTION ---
    sys.exit(qt_app.exec())

if __name__ == "__main__":
    try:
        # Clear any sticky hooks from previous runs
        keyboard.unhook_all()
        main()
    except Exception:
        log_path = os.path.join(application_path, "crash_log.txt")
        with open(log_path, "w") as f:
            f.write(f"Crash Time: {time.ctime()}\n")
            f.write(traceback.format_exc())
        