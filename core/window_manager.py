import win32gui
import win32con
import win32api
import win32process
import ctypes
from ctypes import windll, wintypes
import time
import json
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple, Callable
from enum import Enum, auto
from collections import deque
import threading

# ══════════════════════════════════════════════════════════════════════════════
# DPI AWARENESS
# ══════════════════════════════════════════════════════════════════════════════
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor DPI aware
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        ctypes.windll.user32.SetProcessDPIAware()

# ══════════════════════════════════════════════════════════════════════════════
# LOGGING SETUP (FIXED: No File Created)
# ══════════════════════════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,  # Changed to INFO to reduce noise
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],  # <--- ONLY StreamHandler (Console), NO FileHandler
)

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES & ENUMS
# ══════════════════════════════════════════════════════════════════════════════

class TileMode(Enum):
    LEFT_HALF = auto()
    RIGHT_HALF = auto()
    TOP_HALF = auto()
    BOTTOM_HALF = auto()
    LEFT_THIRD = auto()
    CENTER_THIRD = auto()
    RIGHT_THIRD = auto()
    LEFT_TWO_THIRDS = auto()
    RIGHT_TWO_THIRDS = auto()
    MAXIMIZE = auto()
    CENTER = auto()
    CENTER_SMALL = auto()

@dataclass
class Rect:
    x: int
    y: int
    width: int
    height: int

    def to_tuple(self) -> Tuple[int, int, int, int]:
        return (self.x, self.y, self.width, self.height)

    @classmethod
    def from_ltrb(cls, l: int, t: int, r: int, b: int) -> "Rect":
        return cls(l, t, r - l, b - t)

@dataclass
class WindowInfo:
    hwnd: int
    title: str
    class_name: str
    rect: Rect
    process_id: int
    is_visible: bool
    is_minimized: bool
    is_maximized: bool

@dataclass
class MonitorInfo:
    handle: int
    work_area: Rect
    full_area: Rect
    is_primary: bool
    dpi_scale: float = 1.0

@dataclass
class WindowState:
    """For undo/redo functionality"""
    hwnd: int
    rect: Rect
    timestamp: float = field(default_factory=time.time)

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Config:
    gap: int = 10
    margin: int = 15
    animation_enabled: bool = False
    animation_duration_ms: int = 150
    animation_steps: int = 10
    history_size: int = 50
    excluded_classes: List[str] = field(
        default_factory=lambda: [
            "Shell_TrayWnd",
            "Progman",
            "WorkerW",
            "Windows.UI.Core.CoreWindow",
            "ApplicationFrameWindow",
        ]
    )
    excluded_titles: List[str] = field(
        default_factory=lambda: ["Program Manager", "Windows Input Experience"]
    )

    @classmethod
    def load(cls, path: str = "wm_config.json") -> "Config":
        try:
            with open(path, "r") as f:
                data = json.load(f)
                return cls(**data)
        except FileNotFoundError:
            config = cls()
            config.save(path)
            return config
        except Exception as e:
            logger.warning(f"Failed to load config: {e}, using defaults")
            return cls()

    def save(self, path: str = "wm_config.json") -> None:
        with open(path, "w") as f:
            json.dump(self.__dict__, f, indent=2)

# ══════════════════════════════════════════════════════════════════════════════
# MONITOR MANAGER
# ══════════════════════════════════════════════════════════════════════════════

class MonitorManager:
    """Handle multi-monitor setups"""

    def __init__(self):
        self._monitors: List[MonitorInfo] = []
        self._refresh()

    def _refresh(self):
        self._monitors.clear()
        try:
            monitor_handles = win32api.EnumDisplayMonitors(None, None)
            for hMonitor, hdcMonitor, pyRect in monitor_handles:
                try:
                    info = win32api.GetMonitorInfo(hMonitor)
                    monitor_tuple = info['Monitor']
                    work_tuple = info['Work']
                    flags = info['Flags']
                    is_primary = (flags & win32con.MONITORINFOF_PRIMARY) != 0

                    full_rect = Rect.from_ltrb(*monitor_tuple)
                    work_rect = Rect.from_ltrb(*work_tuple)

                    monitor = MonitorInfo(
                        handle=hMonitor,
                        work_area=work_rect,
                        full_area=full_rect,
                        is_primary=is_primary,
                        dpi_scale=self._get_dpi_scale(hMonitor)
                    )
                    self._monitors.append(monitor)
                except Exception as e:
                    logger.error(f"Error processing monitor {hMonitor}: {e}")

            self._monitors.sort(key=lambda m: m.work_area.x)
            logger.info(f"Refreshed: Found {len(self._monitors)} monitors")

        except Exception as e:
            logger.error(f"Failed to refresh monitors: {e}")

    def _get_dpi_scale(self, hMonitor) -> float:
        try:
            dpiX = ctypes.c_uint()
            dpiY = ctypes.c_uint()
            ctypes.windll.shcore.GetDpiForMonitor(
                hMonitor, 0, ctypes.byref(dpiX), ctypes.byref(dpiY)
            )
            return dpiX.value / 96.0
        except:
            return 1.0

    @property
    def monitors(self) -> List[MonitorInfo]:
        if not self._monitors:
            self._refresh()
        return self._monitors

    @property
    def primary(self) -> Optional[MonitorInfo]:
        return next((m for m in self._monitors if m.is_primary), self._monitors[0] if self._monitors else None)

    def get_monitor_for_window(self, hwnd: int) -> Optional[MonitorInfo]:
        try:
            hMonitor = win32api.MonitorFromWindow(
                hwnd, win32con.MONITOR_DEFAULTTONEAREST)
            return next((m for m in self._monitors if m.handle == hMonitor), self.primary)
        except:
            return self.primary

    def get_next_monitor(self, current: MonitorInfo) -> MonitorInfo:
        if not self._monitors:
            return current
        try:
            idx = self._monitors.index(current)
            return self._monitors[(idx + 1) % len(self._monitors)]
        except:
            return self._monitors[0]

    def get_prev_monitor(self, current: MonitorInfo) -> MonitorInfo:
        if not self._monitors:
            return current
        try:
            idx = self._monitors.index(current)
            return self._monitors[(idx - 1) % len(self._monitors)]
        except:
            return self._monitors[0]

# ══════════════════════════════════════════════════════════════════════════════
# WINDOW UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

class WindowUtils:
    """Static utility methods for window operations"""
    DWMWA_EXTENDED_FRAME_BOUNDS = 9

    @staticmethod
    def get_extended_frame_offsets(hwnd: int) -> Tuple[int, int, int, int]:
        """Get invisible border offsets (left, top, right, bottom)"""
        rect = wintypes.RECT()
        try:
            windll.dwmapi.DwmGetWindowAttribute(
                wintypes.HWND(hwnd),
                ctypes.c_int(WindowUtils.DWMWA_EXTENDED_FRAME_BOUNDS),
                ctypes.byref(rect),
                ctypes.sizeof(rect),
            )
            l, t, r, b = win32gui.GetWindowRect(hwnd)
            return (rect.left - l, 0, r - rect.right, b - rect.bottom)
        except Exception as e:
            logger.debug(f"Could not get frame bounds: {e}")
            return (0, 0, 0, 0)

    @staticmethod
    def get_window_info(hwnd: int) -> Optional[WindowInfo]:
        """Get comprehensive window information"""
        try:
            if not win32gui.IsWindow(hwnd):
                return None
            rect = win32gui.GetWindowRect(hwnd)
            placement = win32gui.GetWindowPlacement(hwnd)
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            return WindowInfo(
                hwnd=hwnd,
                title=win32gui.GetWindowText(hwnd),
                class_name=win32gui.GetClassName(hwnd),
                rect=Rect.from_ltrb(*rect),
                process_id=pid,
                is_visible=win32gui.IsWindowVisible(hwnd),
                is_minimized=placement[1] == win32con.SW_SHOWMINIMIZED,
                is_maximized=placement[1] == win32con.SW_SHOWMAXIMIZED,
            )
        except Exception as e:
            logger.debug(f"Failed to get window info for {hwnd}: {e}")
            return None

    @staticmethod
    def enumerate_windows(filter_func: Optional[Callable[[WindowInfo], bool]] = None) -> List[WindowInfo]:
        """Get all windows, optionally filtered"""
        windows = []
        def callback(hwnd, _):
            info = WindowUtils.get_window_info(hwnd)
            if info and info.is_visible:
                if filter_func is None or filter_func(info):
                    windows.append(info)
            return True
        win32gui.EnumWindows(callback, None)
        return windows

    @staticmethod
    def set_always_on_top(hwnd: int, on_top: bool = True) -> bool:
        try:
            flag = win32con.HWND_TOPMOST if on_top else win32con.HWND_NOTOPMOST
            win32gui.SetWindowPos(
                hwnd, flag, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
            )
            return True
        except Exception as e:
            logger.error(f"Failed to set always on top: {e}")
            return False

    @staticmethod
    def set_transparency(hwnd: int, alpha: int = 255) -> bool:
        try:
            style = win32api.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            win32api.SetWindowLong(
                hwnd, win32con.GWL_EXSTYLE, style | win32con.WS_EX_LAYERED
            )
            windll.user32.SetLayeredWindowAttributes(
                hwnd, 0, alpha, 0x02)  # LWA_ALPHA
            return True
        except Exception as e:
            logger.error(f"Failed to set transparency: {e}")
            return False

    @staticmethod
    def focus_window(hwnd: int) -> bool:
        try:
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
            return True
        except Exception as e:
            logger.error(f"Failed to focus window: {e}")
            return False

# ══════════════════════════════════════════════════════════════════════════════
# LAYOUT CALCULATOR
# ══════════════════════════════════════════════════════════════════════════════

class LayoutCalculator:
    """Calculate layout rectangles"""

    def __init__(self, config: Config):
        self.config = config

    def calculate(self, mode: TileMode, work_area: Rect) -> Rect:
        """Calculate target rectangle for a tile mode"""
        gap = self.config.gap
        margin = self.config.margin
        w = work_area.width
        h = work_area.height
        x = work_area.x
        y = work_area.y
        uw = w - (margin * 2)
        uh = h - (margin * 2)

        layouts = {
            # Halves
            TileMode.LEFT_HALF: Rect(x + margin, y + margin, (uw - gap) // 2, uh),
            TileMode.RIGHT_HALF: Rect(
                x + margin + (uw + gap) // 2, y + margin, (uw - gap) // 2, uh
            ),
            TileMode.TOP_HALF: Rect(x + margin, y + margin, uw, (uh - gap) // 2),
            TileMode.BOTTOM_HALF: Rect(
                x + margin, y + margin + (uh + gap) // 2, uw, (uh - gap) // 2
            ),
            # Thirds
            TileMode.LEFT_THIRD: Rect(x + margin, y + margin, (uw - gap * 2) // 3, uh),
            TileMode.CENTER_THIRD: Rect(
                x + margin + (uw - gap * 2) // 3 + gap,
                y + margin,
                (uw - gap * 2) // 3,
                uh,
            ),
            TileMode.RIGHT_THIRD: Rect(
                x + margin + 2 * ((uw - gap * 2) // 3 + gap),
                y + margin,
                (uw - gap * 2) // 3,
                uh,
            ),
            TileMode.LEFT_TWO_THIRDS: Rect(
                x + margin, y + margin, 2 * (uw - gap * 2) // 3 + gap, uh
            ),
            TileMode.RIGHT_TWO_THIRDS: Rect(
                x + margin + (uw - gap * 2) // 3 + gap,
                y + margin,
                2 * (uw - gap * 2) // 3 + gap,
                uh,
            ),
            # Special
            TileMode.MAXIMIZE: Rect(x + margin, y + margin, uw, uh),
            TileMode.CENTER: Rect(
                x + int(w * 0.15), y + int(h * 0.1), int(w * 0.7), int(h * 0.8)
            ),
            TileMode.CENTER_SMALL: Rect(
                x + int(w * 0.25), y + int(h * 0.2), int(w * 0.5), int(h * 0.6)
            ),
        }
        return layouts[mode]

    def calculate_grid(self, row: int, col: int, rows: int, cols: int, work_area: Rect) -> Rect:
        """Calculate rectangle for grid position"""
        gap = self.config.gap
        margin = self.config.margin
        uw = work_area.width - (margin * 2) - (gap * (cols - 1))
        uh = work_area.height - (margin * 2) - (gap * (rows - 1))
        cell_w = uw // cols
        cell_h = uh // rows
        return Rect(
            work_area.x + margin + col * (cell_w + gap),
            work_area.y + margin + row * (cell_h + gap),
            cell_w,
            cell_h,
        )

# ══════════════════════════════════════════════════════════════════════════════
# ANIMATION ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class AnimationEngine:
    """Smooth window animations"""

    def __init__(self, config: Config):
        self.config = config

    def animate(self, hwnd: int, start: Rect, end: Rect, offsets: Tuple[int, int, int, int]) -> None:
        """Animate window from start to end position"""
        if not self.config.animation_enabled:
            self._apply_position(hwnd, end, offsets)
            return

        steps = self.config.animation_steps
        duration = self.config.animation_duration_ms / 1000.0
        step_time = duration / steps

        for i in range(1, steps + 1):
            t = self._ease_out_cubic(i / steps)
            current = Rect(
                int(start.x + (end.x - start.x) * t),
                int(start.y + (end.y - start.y) * t),
                int(start.width + (end.width - start.width) * t),
                int(start.height + (end.height - start.height) * t),
            )
            self._apply_position(hwnd, current, offsets)
            time.sleep(step_time)

    def _ease_out_cubic(self, t: float) -> float:
        return 1 - pow(1 - t, 3)

    def _apply_position(self, hwnd: int, rect: Rect, offsets: Tuple[int, int, int, int]) -> None:
        off_l, off_t, off_r, off_b = offsets
        win32gui.MoveWindow(
            hwnd,
            rect.x - off_l,
            rect.y - off_t,
            rect.width + off_l + off_r,
            rect.height + off_b,
            True,
        )

# ══════════════════════════════════════════════════════════════════════════════
# HISTORY MANAGER (Undo/Redo)
# ══════════════════════════════════════════════════════════════════════════════

class HistoryManager:
    """Track window position history for undo/redo"""

    def __init__(self, max_size: int = 50):
        self._history: Dict[int, deque] = {}  # hwnd -> deque of WindowState
        self._max_size = max_size

    def save_state(self, hwnd: int) -> None:
        """Save current window state"""
        info = WindowUtils.get_window_info(hwnd)
        if not info:
            return
        if hwnd not in self._history:
            self._history[hwnd] = deque(maxlen=self._max_size)
        state = WindowState(hwnd=hwnd, rect=info.rect)
        self._history[hwnd].append(state)
        logger.debug(f"Saved state for {hwnd}: {state.rect}")

    def get_previous_state(self, hwnd: int) -> Optional[WindowState]:
        """Get previous state (for undo)"""
        if hwnd not in self._history or len(self._history[hwnd]) < 2:
            return None
        self._history[hwnd].pop()  # Remove current
        return self._history[hwnd][-1]  # Return previous

    def clear(self, hwnd: Optional[int] = None) -> None:
        """Clear history"""
        if hwnd:
            self._history.pop(hwnd, None)
        else:
            self._history.clear()

# ══════════════════════════════════════════════════════════════════════════════
# SAVED LAYOUTS
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class SavedLayout:
    name: str
    windows: Dict[str, Rect]  # process_name -> rect
    timestamp: float = field(default_factory=time.time)

class LayoutStore:
    """Save and restore window layouts"""
    def __init__(self, path: str = "layouts.json"):
        self.path = Path(path)
        self._layouts: Dict[str, SavedLayout] = {}
        self._load()

    def _load(self) -> None:
        try:
            if self.path.exists():
                with open(self.path, "r") as f:
                    data = json.load(f)
                    for name, layout_data in data.items():
                        windows = {
                            k: Rect(**v) for k, v in layout_data["windows"].items()
                        }
                        self._layouts[name] = SavedLayout(
                            name=name,
                            windows=windows,
                            timestamp=layout_data.get("timestamp", 0),
                        )
        except Exception as e:
            logger.error(f"Failed to load layouts: {e}")

    def _save(self) -> None:
        try:
            data = {}
            for name, layout in self._layouts.items():
                data[name] = {
                    "windows": {k: v.__dict__ for k, v in layout.windows.items()},
                    "timestamp": layout.timestamp,
                }
            with open(self.path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save layouts: {e}")

    def save_current(self, name: str) -> None:
        """Save current window arrangement"""
        windows = WindowUtils.enumerate_windows(
            lambda w: not w.is_minimized and w.title
        )
        layout = SavedLayout(name=name, windows={
                             w.title[:50]: w.rect for w in windows})
        self._layouts[name] = layout
        self._save()
        logger.info(f"Saved layout '{name}' with {len(windows)} windows")

    def restore(self, name: str) -> bool:
        """Restore a saved layout"""
        if name not in self._layouts:
            logger.warning(f"Layout '{name}' not found")
            return False
        layout = self._layouts[name]
        current_windows = WindowUtils.enumerate_windows()
        for window in current_windows:
            title_key = window.title[:50]
            if title_key in layout.windows:
                rect = layout.windows[title_key]
                offsets = WindowUtils.get_extended_frame_offsets(window.hwnd)
                win32gui.MoveWindow(
                    window.hwnd,
                    rect.x - offsets[0],
                    rect.y,
                    rect.width + offsets[0] + offsets[2],
                    rect.height + offsets[3],
                    True,
                )
        logger.info(f"Restored layout '{name}'")
        return True

    def list_layouts(self) -> List[str]:
        return list(self._layouts.keys())

    def delete(self, name: str) -> bool:
        if name in self._layouts:
            del self._layouts[name]
            self._save()
            return True
        return False

# ══════════════════════════════════════════════════════════════════════════════
# MAIN WINDOW MANAGER
# ══════════════════════════════════════════════════════════════════════════════

class WindowManager:
    """Enhanced Window Manager with all features"""

    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config.load()
        self.monitor_manager = MonitorManager()
        self.layout_calculator = LayoutCalculator(self.config)
        self.animation_engine = AnimationEngine(self.config)
        self.history = HistoryManager(self.config.history_size)
        self.layout_store = LayoutStore()
        logger.info("WindowManager initialized")

    # ──────────────────────────────────────────────────────────────────────────
    # WINDOW VALIDATION
    # ──────────────────────────────────────────────────────────────────────────

    def _get_valid_hwnd(self, hwnd: Optional[int] = None) -> Optional[int]:
        """Get and validate window handle"""
        hwnd = hwnd or win32gui.GetForegroundWindow()
        if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
            logger.debug(f"Invalid or invisible window: {hwnd}")
            return None
        style = win32api.GetWindowLong(hwnd, win32con.GWL_STYLE)
        ex_style = win32api.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        # Filter tool windows and child windows
        if (ex_style & win32con.WS_EX_TOOLWINDOW) or (style & win32con.WS_CHILD):
            logger.debug(f"Filtered tool/child window: {hwnd}")
            return None
        # Filter by class name
        class_name = win32gui.GetClassName(hwnd)
        if class_name in self.config.excluded_classes:
            logger.debug(f"Filtered by class: {class_name}")
            return None
        # Filter by title
        title = win32gui.GetWindowText(hwnd)
        if title in self.config.excluded_titles:
            logger.debug(f"Filtered by title: {title}")
            return None
        return hwnd

    def _prepare_window(self, hwnd: int) -> None:
        """Prepare window for repositioning (restore if maximized)"""
        placement = win32gui.GetWindowPlacement(hwnd)
        if placement[1] == win32con.SW_SHOWMAXIMIZED:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            time.sleep(0.05)

    # ──────────────────────────────────────────────────────────────────────────
    # CORE TILING
    # ──────────────────────────────────────────────────────────────────────────

    def tile(self, mode: TileMode, hwnd: Optional[int] = None) -> bool:
        """Tile window to specified mode"""
        hwnd = self._get_valid_hwnd(hwnd)
        if not hwnd:
            logger.warning("No valid window to tile")
            return False
        # Save state for undo
        self.history.save_state(hwnd)
        # Get monitor and calculate layout
        monitor = self.monitor_manager.get_monitor_for_window(hwnd)
        if not monitor:
            logger.error("Could not determine monitor")
            return False
        target_rect = self.layout_calculator.calculate(mode, monitor.work_area)
        # Prepare and animate
        self._prepare_window(hwnd)
        offsets = WindowUtils.get_extended_frame_offsets(hwnd)
        current_rect = WindowUtils.get_window_info(hwnd).rect
        self.animation_engine.animate(hwnd, current_rect, target_rect, offsets)
        logger.info(f"Tiled window {hwnd} to {mode.name}")
        return True

    # ──────────────────────────────────────────────────────────────────────────
    # GRID LAYOUTS
    # ──────────────────────────────────────────────────────────────────────────

    def grid(self, row: int, col: int, rows: int = 2, cols: int = 2, hwnd: Optional[int] = None) -> bool:
        """Place window in grid position (0-indexed)"""
        hwnd = self._get_valid_hwnd(hwnd)
        if not hwnd:
            return False
        self.history.save_state(hwnd)
        monitor = self.monitor_manager.get_monitor_for_window(hwnd)
        if not monitor:
            return False
        target_rect = self.layout_calculator.calculate_grid(
            row, col, rows, cols, monitor.work_area
        )
        self._prepare_window(hwnd)
        offsets = WindowUtils.get_extended_frame_offsets(hwnd)
        current_rect = WindowUtils.get_window_info(hwnd).rect
        self.animation_engine.animate(hwnd, current_rect, target_rect, offsets)
        logger.info(f"Placed window in grid [{row},{col}] of {rows}x{cols}")
        return True

    def grid_top_left(self) -> bool:
        return self.grid(0, 0)

    def grid_top_right(self) -> bool:
        return self.grid(0, 1)

    def grid_bottom_left(self) -> bool:
        return self.grid(1, 0)

    def grid_bottom_right(self) -> bool:
        return self.grid(1, 1)

    def grid_6(self, position: int) -> bool:
        """6-grid layout (2 rows, 3 columns). Position 1-6"""
        if position < 1 or position > 6:
            return False
        pos = position - 1
        return self.grid(pos // 3, pos % 3, rows=2, cols=3)

    # ──────────────────────────────────────────────────────────────────────────
    # MULTI-MONITOR
    # ──────────────────────────────────────────────────────────────────────────

    def move_to_monitor(self, direction: str, hwnd: Optional[int] = None) -> bool:
        """Move window to next/previous monitor"""
        hwnd = self._get_valid_hwnd(hwnd)
        if not hwnd:
            return False
        self.history.save_state(hwnd)
        current_monitor = self.monitor_manager.get_monitor_for_window(hwnd)
        if not current_monitor:
            return False
        if direction == "next":
            target_monitor = self.monitor_manager.get_next_monitor(
                current_monitor)
        else:
            target_monitor = self.monitor_manager.get_prev_monitor(
                current_monitor)

        # Calculate relative position on new monitor
        info = WindowUtils.get_window_info(hwnd)
        if not info:
            return False
        rel_x = (info.rect.x - current_monitor.work_area.x) / \
            current_monitor.work_area.width
        rel_y = (info.rect.y - current_monitor.work_area.y) / \
            current_monitor.work_area.height
        rel_w = info.rect.width / current_monitor.work_area.width
        rel_h = info.rect.height / current_monitor.work_area.height

        # Apply to new monitor
        new_rect = Rect(
            int(target_monitor.work_area.x + rel_x *
                target_monitor.work_area.width),
            int(target_monitor.work_area.y + rel_y *
                target_monitor.work_area.height),
            int(rel_w * target_monitor.work_area.width),
            int(rel_h * target_monitor.work_area.height),
        )
        self._prepare_window(hwnd)
        offsets = WindowUtils.get_extended_frame_offsets(hwnd)
        self.animation_engine.animate(hwnd, info.rect, new_rect, offsets)
        logger.info(f"Moved window to {direction} monitor")
        return True

    def move_to_next_monitor(self) -> bool:
        return self.move_to_monitor("next")

    def move_to_prev_monitor(self) -> bool:
        return self.move_to_monitor("prev")

    # ──────────────────────────────────────────────────────────────────────────
    # MULTI-WINDOW OPERATIONS
    # ──────────────────────────────────────────────────────────────────────────

    def tile_all_visible(self, layout: str = "grid") -> bool:
        """Tile all visible windows"""
        windows = WindowUtils.enumerate_windows(
            lambda w: not w.is_minimized
            and w.class_name not in self.config.excluded_classes
        )
        if not windows:
            return False
        monitor = self.monitor_manager.primary
        if not monitor:
            return False
        n = len(windows)
        if layout == "grid":
            cols = int(n**0.5) + (1 if n**0.5 % 1 else 0)
            rows = (n + cols - 1) // cols
            for i, window in enumerate(windows):
                row = i // cols
                col = i % cols
                target = self.layout_calculator.calculate_grid(
                    row, col, rows, cols, monitor.work_area
                )
                self._prepare_window(window.hwnd)
                offsets = WindowUtils.get_extended_frame_offsets(window.hwnd)
                self.animation_engine._apply_position(
                    window.hwnd, target, offsets)
        elif layout == "cascade":
            offset = 30
            base_rect = Rect(
                monitor.work_area.x + self.config.margin,
                monitor.work_area.y + self.config.margin,
                int(monitor.work_area.width * 0.6),
                int(monitor.work_area.height * 0.6),
            )
            for i, window in enumerate(windows):
                target = Rect(
                    base_rect.x + i * offset,
                    base_rect.y + i * offset,
                    base_rect.width,
                    base_rect.height,
                )
                self._prepare_window(window.hwnd)
                offsets = WindowUtils.get_extended_frame_offsets(window.hwnd)
                self.animation_engine._apply_position(
                    window.hwnd, target, offsets)
        logger.info(f"Tiled {n} windows using {layout} layout")
        return True

    # ──────────────────────────────────────────────────────────────────────────
    # UNDO/REDO
    # ──────────────────────────────────────────────────────────────────────────

    def undo(self, hwnd: Optional[int] = None) -> bool:
        """Undo last window move"""
        hwnd = self._get_valid_hwnd(hwnd)
        if not hwnd:
            return False
        prev_state = self.history.get_previous_state(hwnd)
        if not prev_state:
            logger.warning("No previous state to restore")
            return False
        offsets = WindowUtils.get_extended_frame_offsets(hwnd)
        self.animation_engine._apply_position(hwnd, prev_state.rect, offsets)
        logger.info("Restored previous window position")
        return True

    # ──────────────────────────────────────────────────────────────────────────
    # WINDOW CONTROLS
    # ──────────────────────────────────────────────────────────────────────────

    def toggle_always_on_top(self, hwnd: Optional[int] = None) -> bool:
        """Toggle always on top for window"""
        hwnd = self._get_valid_hwnd(hwnd)
        if not hwnd:
            return False
        ex_style = win32api.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        is_topmost = bool(ex_style & win32con.WS_EX_TOPMOST)
        return WindowUtils.set_always_on_top(hwnd, not is_topmost)

    def set_transparency(self, alpha: int, hwnd: Optional[int] = None) -> bool:
        """Set window transparency (0-255)"""
        hwnd = self._get_valid_hwnd(hwnd)
        if not hwnd:
            return False
        return WindowUtils.set_transparency(hwnd, max(0, min(255, alpha)))

    def minimize_all_except_current(self) -> bool:
        """Minimize all windows except the focused one"""
        current = win32gui.GetForegroundWindow()
        windows = WindowUtils.enumerate_windows(
            lambda w: w.hwnd != current and not w.is_minimized
        )
        for window in windows:
            win32gui.ShowWindow(window.hwnd, win32con.SW_MINIMIZE)
        logger.info(f"Minimized {len(windows)} windows")
        return True

    def focus_next_window(self) -> bool:
        """Focus the next window"""
        current = win32gui.GetForegroundWindow()
        windows = WindowUtils.enumerate_windows(
            lambda w: not w.is_minimized
            and w.class_name not in self.config.excluded_classes
        )
        if len(windows) < 2:
            return False
        current_idx = next(
            (i for i, w in enumerate(windows) if w.hwnd == current), -1)
        next_idx = (current_idx + 1) % len(windows)
        return WindowUtils.focus_window(windows[next_idx].hwnd)

    # ──────────────────────────────────────────────────────────────────────────
    # LAYOUT PRESETS
    # ──────────────────────────────────────────────────────────────────────────

    def save_layout(self, name: str) -> None:
        """Save current window arrangement"""
        self.layout_store.save_current(name)

    def restore_layout(self, name: str) -> bool:
        """Restore a saved layout"""
        return self.layout_store.restore(name)

    def list_saved_layouts(self) -> List[str]:
        """List all saved layouts"""
        return self.layout_store.list_layouts()

    # ──────────────────────────────────────────────────────────────────────────
    # LEGACY COMPATIBILITY
    # ──────────────────────────────────────────────────────────────────────────

    def tile_legacy(self, mode: str) -> bool:
        """Legacy tile method for backward compatibility"""
        mode_map = {
            "left": TileMode.LEFT_HALF,
            "right": TileMode.RIGHT_HALF,
            "top": TileMode.TOP_HALF,
            "bottom": TileMode.BOTTOM_HALF,
            "full": TileMode.MAXIMIZE,
            "center": TileMode.CENTER,
        }
        if mode in mode_map:
            return self.tile(mode_map[mode])
        return False

# ══════════════════════════════════════════════════════════════════════════════
# KEYBOARD INTEGRATION (Optional - requires `keyboard` package)
# ══════════════════════════════════════════════════════════════════════════════

class HotkeyManager:
    """Manage keyboard shortcuts"""
    def __init__(self, wm: WindowManager):
        self.wm = wm
        self._hotkeys = {}
        self._running = False

    def register(self, hotkey: str, action: Callable) -> None:
        """Register a hotkey"""
        self._hotkeys[hotkey] = action

    def start(self) -> None:
        """Start listening for hotkeys (requires keyboard package)"""
        try:
            import keyboard
            for hotkey, action in self._hotkeys.items():
                keyboard.add_hotkey(hotkey, action)
            self._running = True
            logger.info(f"Registered {len(self._hotkeys)} hotkeys")
        except ImportError:
            logger.warning(
                "keyboard package not installed. Run: pip install keyboard")

    def stop(self) -> None:
        """Stop listening"""
        try:
            import keyboard
            keyboard.unhook_all()
            self._running = False
        except ImportError:
            pass

# ══════════════════════════════════════════════════════════════════════════════
# EXAMPLE USAGE
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("Enhanced Window Manager Demo")
    print("=" * 50)
    # Initialize
    wm = WindowManager()
    print("\nAvailable operations:")
    print("  - Tile modes: LEFT_HALF, RIGHT_HALF, TOP_HALF, BOTTOM_HALF")
    print("  - Thirds: LEFT_THIRD, CENTER_THIRD, RIGHT_THIRD")
    print("  - Grid: 2x2, 2x3, 3x3 layouts")
    print("  - Multi-monitor: move_to_next_monitor, move_to_prev_monitor")
    print("  - Extras: toggle_always_on_top, set_transparency, undo")
    print("\nDemo: Focus a window within 3 seconds...")
    time.sleep(3)
    # Demo sequence
    print("→ Tiling to left half...")
    wm.tile(TileMode.LEFT_HALF)
    time.sleep(1)
    print("→ Tiling to right half...")
    wm.tile(TileMode.RIGHT_HALF)
    time.sleep(1)
    print("→ Undoing last move...")
    wm.undo()
    time.sleep(1)
    print("→ Moving to center...")
    wm.tile(TileMode.CENTER)
    print("\nDone! No log file created.")