import os
import sys
import re
import subprocess
import pyperclip
import webbrowser

from PyQt6.QtCore import (
    Qt, QTimer, pyqtSignal, QObject, QEvent, QPoint,
    QPropertyAnimation, QEasingCurve, QSettings, QSize
)
from PyQt6.QtGui import (
    QFont, QKeySequence, QShortcut, QColor, QGuiApplication
)
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QScrollArea, QFrame, QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect, QSizePolicy, QSpacerItem
)

# Assumed internal modules (kept as is)
from core.snipper import Snipper
from core.actions import execute_action
from core.clipboard import ClipboardManager
from core.everything import EverythingManager

# ============================================================================
#  STYLES & CONFIGURATION
# ============================================================================

# Consistent dimensions - FIXED VALUES
ITEM_HEIGHT = 52
ITEM_SPACING = 2
HEADER_HEIGHT = 24  # FIXED: Reduced from 28 for tighter spacing
CONTENT_PADDING = 8
SHORTCUT_WIDTH = 58

STYLES = {
    "result_item_base": """
        QFrame#resultItem {
            background-color: transparent;
            border-radius: 8px;
            border: 1px solid transparent;
        }
    """,
    "result_item_selected": """
        QFrame#resultItem {
            background-color: rgba(94, 156, 255, 0.15);
            border-radius: 8px;
            border: 1px solid rgba(94, 156, 255, 0.35);
        }
    """,
    "result_item_hover": """
        QFrame#resultItem {
            background-color: rgba(255, 255, 255, 0.05);
            border-radius: 8px;
            border: 1px solid rgba(255, 255, 255, 0.08);
        }
    """,
    "icon_container": """
        QFrame#iconBox {
            background-color: rgba(255, 255, 255, 0.06);
            border-radius: 6px;
        }
    """,
    "shortcut_visible": """
        QLabel#shortcutHint {
            font-size: 10px;
            color: #5e9cff;
            padding: 2px 6px;
            background-color: rgba(94, 156, 255, 0.12);
            border-radius: 4px;
            font-weight: 500;
        }
    """,
    "shortcut_hidden": """
        QLabel#shortcutHint {
            font-size: 10px;
            color: transparent;
            background-color: transparent;
            padding: 2px 6px;
        }
    """,
    "search_input": """
        QLineEdit#searchInput {
            background-color: transparent;
            border: none;
            color: #e6e6eb;
            font-size: 17px;
            font-weight: 500;
            padding: 4px 0px;
            selection-background-color: rgba(94, 156, 255, 0.3);
        }
    """,
    "scroll_area": """
        QScrollArea {
            background-color: transparent;
            border: none;
        }
        QWidget#resultsContainer {
            background-color: transparent;
        }
        QScrollBar:vertical {
            background-color: transparent;
            width: 6px;
            margin: 4px 2px;
        }
        QScrollBar::handle:vertical {
            background-color: rgba(94, 156, 255, 0.3);
            border-radius: 3px;
            min-height: 30px;
        }
        QScrollBar::handle:vertical:hover {
            background-color: rgba(94, 156, 255, 0.5);
        }
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical,
        QScrollBar::add-page:vertical,
        QScrollBar::sub-page:vertical {
            background: none;
            height: 0px;
        }
        QScrollBar:horizontal {
            height: 0px;
            background: transparent;
        }
    """,
    "category_header": """
        QLabel#categoryHeader {
            color: #6b7280;
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 1.2px;
            background: transparent;
        }
    """,
    "no_results": """
        color: #6b7280;
        font-size: 14px;
    """,
    "loading_spinner": """
        font-size: 16px;
        color: #5e9cff;
    """
}


# ============================================================================
#  THREAD-SAFE SIGNAL BRIDGE
# ============================================================================

class LauncherSignals(QObject):
    """Signal bridge for thread-safe communication."""
    show_signal = pyqtSignal()
    show_clip_signal = pyqtSignal()
    hide_signal = pyqtSignal()


# ============================================================================
#  CUSTOM WIDGETS - FIXED
# ============================================================================

class ResultItem(QFrame):
    """A single result row with hover effects and selection state."""
    clicked = pyqtSignal()
    
    def __init__(self, icon: str, icon_color: str, label: str, subtext: str, colors: dict, query: str = "", parent=None):
        super().__init__(parent)
        self.colors = colors
        self.setObjectName("resultItem")
        self.command_ref = None
        self.full_path = ""
        self._selected = False
        self._query = query
        self._label_text = label
        
        # Fixed height for consistent spacing
        self.setFixedHeight(ITEM_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # FIX: Don't use opacity effect - it causes repaint issues
        # Instead, we'll handle opacity via stylesheets if needed
        
        # Apply base style immediately
        self.setStyleSheet(STYLES["result_item_base"])
        
        # Main horizontal layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(12)
        
        # === Icon Container (Fixed Size) ===
        icon_container = QFrame()
        icon_container.setObjectName("iconBox")
        icon_container.setFixedSize(32, 32)
        icon_container.setStyleSheet(STYLES["icon_container"])
        
        icon_layout = QHBoxLayout(icon_container)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_layout.setSpacing(0)
        
        self.icon_label = QLabel(icon)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet("font-size: 16px; background: transparent;")
        self.icon_label.setFixedSize(32, 32)
        icon_layout.addWidget(self.icon_label)
        layout.addWidget(icon_container)
        
        # === Text Container (Expanding) - FIXED ===
        text_container = QWidget()
        text_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        text_container.setFixedHeight(ITEM_HEIGHT)
        text_layout = QVBoxLayout(text_container)
        text_layout.setSpacing(2)
        text_layout.setContentsMargins(0, 8, 0, 8)
        
        # FIX: Title label - prevent text overlap
        self.title_label = QLabel()
        self.title_label.setTextFormat(Qt.TextFormat.RichText)
        self.title_label.setText(self._highlight_match(label))
        self.title_label.setStyleSheet("""
            font-size: 13px;
            font-weight: 600;
            color: #e6e6eb;
            background: transparent;
        """)
        self.title_label.setFixedHeight(18)
        self.title_label.setMinimumWidth(100)
        # FIX: Critical - prevent word wrap and set proper size policy
        self.title_label.setWordWrap(False)
        self.title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        # FIX: Path/subtext label - prevent overlap
        self.path_label = QLabel(subtext)
        self.path_label.setStyleSheet("""
            font-size: 11px;
            color: #6b7280;
            background: transparent;
        """)
        self.path_label.setFixedHeight(14)
        self.path_label.setWordWrap(False)  # FIX: Prevent wrapping
        self.path_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        # FIX: Use elide mode to handle overflow gracefully
        self.title_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        
        text_layout.addWidget(self.title_label)
        text_layout.addWidget(self.path_label)
        layout.addWidget(text_container, 1)
        
        # === Shortcut Hint (FIXED WIDTH) ===
        self.shortcut_label = QLabel()
        self.shortcut_label.setObjectName("shortcutHint")
        self.shortcut_label.setFixedSize(SHORTCUT_WIDTH, 20)
        self.shortcut_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.shortcut_label.setStyleSheet(STYLES["shortcut_hidden"])
        layout.addWidget(self.shortcut_label)
    
    def _highlight_match(self, text: str) -> str:
        """Highlight matching text with accent color."""
        if not self._query or len(self._query) < 2:
            return text
        
        try:
            # FIX: Escape HTML entities to prevent rendering issues
            import html
            text_escaped = html.escape(text)
            query_escaped = html.escape(self._query)
            
            idx = text_escaped.lower().find(query_escaped.lower())
            if idx == -1:
                return text_escaped
            
            matched = text_escaped[idx:idx + len(query_escaped)]
            return (
                f'{text_escaped[:idx]}'
                f'<span style="color:#5e9cff;font-weight:700;">{matched}</span>'
                f'{text_escaped[idx + len(query_escaped):]}'
            )
        except:
            return text
    
    def set_shortcut_hint(self, text: str):
        """Show/hide keyboard shortcut hint without layout shift."""
        if text:
            self.shortcut_label.setText(text)
            self.shortcut_label.setStyleSheet(STYLES["shortcut_visible"])
        else:
            self.shortcut_label.setText("")
            self.shortcut_label.setStyleSheet(STYLES["shortcut_hidden"])
    
    def set_selected(self, selected: bool):
        """FIX: Update selection with proper repaint."""
        if self._selected != selected:
            self._selected = selected
            self._update_style()
            # FIX: Force immediate repaint to prevent ghosting
            self.update()
    
    def _update_style(self):
        if self._selected:
            self.setStyleSheet(STYLES["result_item_selected"])
        else:
            self.setStyleSheet(STYLES["result_item_base"])
    
    def enterEvent(self, event):
        if not self._selected:
            self.setStyleSheet(STYLES["result_item_hover"])
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        self._update_style()
        super().leaveEvent(event)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)
    
    def fade_in(self, delay: int = 0):
        """FIX: Simple show without problematic opacity animation."""
        # Removed QGraphicsOpacityEffect - it causes repaint artifacts
        # If you need fade, use stylesheet opacity instead
        self.show()


class CategoryHeader(QWidget):
    """Section header for grouping results - FIXED SPACING."""
    
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(HEADER_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        layout = QHBoxLayout(self)
        # FIX: Symmetric margins - prevents uneven spacing
        layout.setContentsMargins(14, 4, 14, 2)
        layout.setSpacing(0)
        
        self.label = QLabel(title)
        self.label.setObjectName("categoryHeader")
        self.label.setStyleSheet(STYLES["category_header"])
        layout.addWidget(self.label)
        layout.addStretch()


class GlowingContainer(QFrame):
    """Main container with animated glowing border effect."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("glowContainer")
        self._border_color = "#5e9cff"
        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(25)
        self.shadow.setOffset(0, 4)
        self.setGraphicsEffect(self.shadow)
        self._update_style()
    
    def set_border_color(self, color: str):
        self._border_color = color
        self._update_style()
        
        color_map = {
            "#f9a03f": QColor(249, 160, 63, 40),
            "#7bd88f": QColor(123, 216, 143, 40),
            "#5e9cff": QColor(94, 156, 255, 50),
        }
        self.shadow.setColor(color_map.get(color, QColor(94, 156, 255, 50)))
    
    def _update_style(self):
        self.setStyleSheet(f"""
            QFrame#glowContainer {{
                background-color: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(20, 24, 33, 0.98),
                    stop:1 rgba(15, 17, 21, 0.98)
                );
                border: 1px solid {self._border_color};
                border-radius: 16px;
            }}
        """)


class SearchInput(QLineEdit):
    """Styled search input field."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("searchInput")
        self.setPlaceholderText("Search apps, files, or type a command...")
        self.setStyleSheet(STYLES["search_input"])


class LoadingSpinner(QLabel):
    """Animated loading indicator."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(STYLES["loading_spinner"])
        self.setFixedWidth(24)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self._frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self._current_frame = 0
        
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._next_frame)
        self.hide()
    
    def _next_frame(self):
        self._current_frame = (self._current_frame + 1) % len(self._frames)
        self.setText(self._frames[self._current_frame])
    
    def start(self):
        self.show()
        self._timer.start(80)
    
    def stop(self):
        self._timer.stop()
        self.hide()


class NoResultsWidget(QWidget):
    """Empty state when no results found."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(100)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 16, 0, 16)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)
        
        icon = QLabel("🔍")
        icon.setStyleSheet("font-size: 28px; background: transparent;")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        text = QLabel("No results found")
        text.setStyleSheet(STYLES["no_results"])
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        hint = QLabel("Try a different search term")
        hint.setStyleSheet("color: #4b5563; font-size: 11px; background: transparent;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        layout.addWidget(icon)
        layout.addWidget(text)
        layout.addWidget(hint)


# ============================================================================
#  MAIN LAUNCHER CLASS - FIXED
# ============================================================================

class Launcher(QWidget):
    
    def __init__(self, config):
        super().__init__()
        
        # Signal bridge for thread safety
        self.signals = LauncherSignals()
        self.signals.show_signal.connect(self._do_show)
        self.signals.show_clip_signal.connect(self._do_show_clip)
        self.signals.hide_signal.connect(self._do_hide)
        
        # Core managers
        self.everything = EverythingManager()
        self.clipboard = ClipboardManager()
        self.config = config
        self.mapping = config.get("launcher_mapping", {})
        
        # Settings for persistence
        self.settings = QSettings("Launcher", "QuickLaunch")
        
        # State
        self.last_command = ""
        self.current_query = ""
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self.perform_live_search)
        
        self.result_items = []
        self.selected_index = -1
        self.menu_active = False
        self.can_hide = False
        self.snipper = None
        
        # FIX: Track if we're currently updating to prevent recursive updates
        self._updating_selection = False
        
        # Recent searches
        self.recent_searches = self.settings.value("recent_searches", [])
        if not isinstance(self.recent_searches, list):
            self.recent_searches = []
        
        # Theme colors
        self.colors = {
            "bg": "#0f1115",
            "bg_glass": "#141821",
            "text": "#e6e6eb",
            "accent": "#5e9cff",
            "selection": "#2a3550",
            "warning": "#f9a03f",
            "success": "#7bd88f",
            "muted": "#6b7280",
            "divider": "#1f2937",
            "icon_folder": "#fbbf24",
            "icon_image": "#34d399",
            "icon_code": "#60a5fa",
            "icon_doc": "#f472b6",
            "icon_zip": "#a78bfa",
            "icon_app": "#5e9cff",
            "icon_default": "#9ca3af",
        }
        
        self.setup_window()
        self.setup_ui()
        self.setup_shortcuts()
        
    def setup_window(self):
        """Configure frameless, always-on-top window."""
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        
        theme = self.config.get("theme", {})
        self.win_width = theme.get("width", 680)
        self.base_height = 72
        self.max_list_height = 380
        
        screen = QGuiApplication.primaryScreen().geometry()
        self.win_x = (screen.width() - self.win_width) // 2
        self.win_y = screen.height() // 3
        
        self.setGeometry(self.win_x, self.win_y, self.win_width, self.base_height)
        self.setFixedWidth(self.win_width)
        
    def setup_ui(self):
        """Build all UI components."""
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 12, 12, 16)
        root_layout.setSpacing(0)
        
        self.container = GlowingContainer(self)
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        
        # Search bar
        search_bar = QWidget()
        search_layout = QHBoxLayout(search_bar)
        search_layout.setContentsMargins(20, 16, 20, 14)
        search_layout.setSpacing(14)
        
        self.search_icon = QLabel("⌘")
        self.search_icon.setStyleSheet("""
            font-size: 20px;
            color: #5e9cff;
            font-weight: bold;
        """)
        self.search_icon.setFixedWidth(24)
        search_layout.addWidget(self.search_icon)
        
        self.loading_spinner = LoadingSpinner()
        search_layout.addWidget(self.loading_spinner)
        
        self.entry = SearchInput()
        self.entry.textChanged.connect(self.on_text_changed)
        self.entry.returnPressed.connect(self.on_submit)
        search_layout.addWidget(self.entry, 1)
        
        hints_widget = QWidget()
        hints_layout = QHBoxLayout(hints_widget)
        hints_layout.setContentsMargins(0, 0, 0, 0)
        hints_layout.setSpacing(6)
        
        for hint in ["↑↓", "⏎", "ESC"]:
            hint_label = QLabel(hint)
            hint_label.setStyleSheet("""
                font-size: 9px;
                color: #4b5563;
                padding: 3px 6px;
                background-color: rgba(255, 255, 255, 0.05);
                border-radius: 4px;
                font-weight: 500;
            """)
            hints_layout.addWidget(hint_label)
        
        search_layout.addWidget(hints_widget)
        container_layout.addWidget(search_bar)
        
        # Divider
        self.divider = QFrame()
        self.divider.setFixedHeight(1)
        self.divider.setStyleSheet(f"background-color: {self.colors['divider']};")
        self.divider.hide()
        container_layout.addWidget(self.divider)
        
        # Results area - FIX: Proper setup to prevent z-index issues
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setStyleSheet(STYLES["scroll_area"])
        self.scroll_area.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.scroll_area.hide()
        
        # FIX: Create results widget with explicit opaque background
        self.results_widget = QWidget()
        self.results_widget.setObjectName("resultsContainer")
        self.results_widget.setAutoFillBackground(True)  # FIX: Ensure background is painted
        
        self.results_layout = QVBoxLayout(self.results_widget)
        self.results_layout.setContentsMargins(CONTENT_PADDING, CONTENT_PADDING, CONTENT_PADDING, CONTENT_PADDING)
        self.results_layout.setSpacing(ITEM_SPACING)
        self.results_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # FIX: Add stretch at bottom to prevent items from expanding
        self.results_layout.addStretch()
        
        self.scroll_area.setWidget(self.results_widget)
        container_layout.addWidget(self.scroll_area)
        
        root_layout.addWidget(self.container)
        self.installEventFilter(self)
        
    def setup_shortcuts(self):
        """Configure keyboard shortcuts."""
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self._do_hide)
        QShortcut(QKeySequence("Ctrl+Return"), self, self.on_ctrl_submit)
        QShortcut(QKeySequence("Alt+C"), self, self.on_copy_path)
        QShortcut(QKeySequence("Tab"), self, self.on_tab_complete)
    
    def eventFilter(self, obj, event):
        """Handle window focus loss."""
        if event.type() == QEvent.Type.WindowDeactivate:
            if self.can_hide:
                self._do_hide()
        return super().eventFilter(obj, event)
    
    def keyPressEvent(self, event):
        """Handle arrow key navigation."""
        key = event.key()
        
        if key == Qt.Key.Key_Down:
            self.nav_down()
            event.accept()
            return
        elif key == Qt.Key.Key_Up:
            self.nav_up()
            event.accept()
            return
        
        super().keyPressEvent(event)

    # ========================================================================
    #  THREAD-SAFE PUBLIC API
    # ========================================================================
    
    def show_launcher(self):
        self.signals.show_signal.emit()
    
    def open_clip_mode(self):
        self.signals.show_clip_signal.emit()
    
    def hide_launcher(self):
        self.signals.hide_signal.emit()

    # ========================================================================
    #  INTERNAL SHOW/HIDE
    # ========================================================================
    
    def _do_show(self):
        """Internal show - always runs on main thread."""
        self.can_hide = False
        self.entry.clear()
        self.reset_ui()
        
        self.show()
        self.raise_()
        self.activateWindow()
        self.entry.setFocus()
        
        self.show_recent_searches()
        QTimer.singleShot(50, self._force_focus)
        QTimer.singleShot(250, lambda: setattr(self, 'can_hide', True))
    
    def _force_focus(self):
        """Force window focus."""
        self.raise_()
        self.activateWindow()
        self.entry.setFocus()
    
    def _do_show_clip(self):
        """Internal clipboard mode."""
        self._do_show()
        self.entry.setText("clip")
        QTimer.singleShot(100, self.perform_live_search)
    
    def _do_hide(self):
        """Internal hide."""
        self.loading_spinner.stop()
        self.hide()
    
    def reset_ui(self):
        """Reset to initial empty state."""
        self.menu_active = False
        self.selected_index = -1
        self.current_query = ""
        self._clear_results()
        
        self.scroll_area.hide()
        self.divider.hide()
        
        self.setFixedHeight(self.base_height + 24)
        self.container.set_border_color(self.colors["accent"])
        
        self.search_icon.show()
        self.loading_spinner.stop()
    
    def _clear_results(self):
        """FIX: Clear all result items with immediate visual update."""
        # Clear items list first
        self.result_items.clear()
        
        # Remove all widgets from layout (except the stretch)
        while self.results_layout.count() > 1:  # Keep the stretch
            item = self.results_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.hide()  # FIX: Hide immediately before deletion
                widget.setParent(None)
                widget.deleteLater()
        
        # FIX: Force immediate layout update
        self.results_widget.updateGeometry()
        QApplication.processEvents()  # Process pending deletions

    # ========================================================================
    #  RECENT SEARCHES
    # ========================================================================
    
    def add_to_recent(self, query: str):
        """Add a search query to recent searches."""
        query = query.strip()
        if not query or len(query) < 2:
            return
        
        if query in self.recent_searches:
            self.recent_searches.remove(query)
        self.recent_searches.insert(0, query)
        self.recent_searches = self.recent_searches[:5]
        self.settings.setValue("recent_searches", self.recent_searches)
    
    def show_recent_searches(self):
        """Display recent searches when input is empty."""
        if not self.recent_searches:
            return
        
        self._clear_results()
        self.menu_active = True
        
        # FIX: More accurate height calculation
        needed_height = (
            len(self.recent_searches) * (ITEM_HEIGHT + ITEM_SPACING) +
            HEADER_HEIGHT +
            CONTENT_PADDING * 2
        )
        frame_height = min(needed_height, self.max_list_height)
        
        self.divider.show()
        self.scroll_area.show()
        self.scroll_area.setFixedHeight(frame_height)
        self.setFixedHeight(self.base_height + frame_height + 28)
        
        # FIX: Insert before the stretch (at position 0, not append)
        header = CategoryHeader("🕐  Recent Searches")
        self.results_layout.insertWidget(0, header)
        
        for i, term in enumerate(self.recent_searches):
            item = ResultItem("🔍", self.colors["muted"], term, "Recent search", self.colors)
            item.command_ref = lambda t=term: self._use_recent(t)
            item.clicked.connect(item.command_ref)
            
            # FIX: Insert at correct position (after header)
            self.results_layout.insertWidget(i + 1, item)
            self.result_items.append(item)
        
        self.selected_index = 0
        self._update_selection()
    
    def _use_recent(self, term: str):
        """Use a recent search term."""
        self.entry.setText(term)
        self.perform_live_search()

    # ========================================================================
    #  SEARCH LOGIC
    # ========================================================================
    
    def on_text_changed(self, text):
        """Handle input text changes with debouncing."""
        text = text.strip()
        self.current_query = text
        
        
        if not text:
            self.reset_ui()
            self.show_recent_searches()
            return
        
        cmd = text.split(" ")[0].lower()
        
        
        if cmd in ["lock", "kill", "bin", "off"]:
            self.container.set_border_color(self.colors["warning"])
        elif cmd in self.mapping or cmd in [ "g", "p", "clip"] or any(c in text for c in "+-*/"):
            self.container.set_border_color(self.colors["success"])
        else:
            self.container.set_border_color(self.colors["accent"])
        
        self.search_icon.hide()
        self.loading_spinner.start()
        
        self.search_timer.stop()
        self.search_timer.start(200)
    
    def perform_live_search(self):
        """Execute the actual search."""
        self.loading_spinner.stop()
        self.search_icon.show()
        
        query = self.entry.text().strip()
        if not query:
            return
        
        parts = query.split(" ")
        cmd = parts[0].lower()
        arg = " ".join(parts[1:]) if len(parts) > 1 else ""
        
        # OCR Command
        if cmd == "ocr":
            self.show_selection_menu([{
                "label": "OCR: Draw Box & Copy Text", 
                "value": "start_ocr", 
                "action_type": "ocr_trigger"
            }], category="👁️  Vision")
            return
            
        # Kill Port
        if cmd == "kp" and arg:
            if arg.isdigit():
                self.show_selection_menu([{
                    "label": f"Kill Process on Port {arg}", 
                    "value": arg, 
                    "action_type": "kill_port"
                }], category="⚡  System")
                return

        # Mapped Commands
        if cmd in self.mapping:
            self.reset_ui()
            return
            
        # Audio Switcher
        if cmd == "audio":
            devices = self.config.get("audio_devices", {
                "head": "Headphones", 
                "spk": "Speakers"
            })
            
            opts = []
            for key, dev_name in devices.items():
                if not arg or arg in key or arg.lower() in dev_name.lower():
                    opts.append({
                        "label": f"Switch Audio: {dev_name}", 
                        "value": dev_name, 
                        "action_type": "audio"
                    })
            if opts:
                self.show_selection_menu(opts, category="🔊  Audio")
                return
        
        # Volume Control
        if cmd == "vol" and arg.isdigit():
            val = int(arg)
            if 0 <= val <= 100:
                self.show_selection_menu([{
                    "label": f"Set Volume to {val}%", 
                    "value": val, 
                    "action_type": "volume"
                }], category="🔊  Audio")
                return

        # System Mute
        if cmd == "mute":
            self.show_selection_menu([{
                "label": "Toggle System Sound", 
                "value": "toggle", 
                "action_type": "mute_system"
            }], category="🔊  Audio")
            return

        # Mic Mute
        if cmd == "mic":
            self.show_selection_menu([{
                "label": "Toggle Microphone Mute", 
                "value": "toggle", 
                "action_type": "mute_mic"
            }], category="🎙️  Microphone")
            return

        # App Mute
        if cmd == "ma" and arg:
            self.show_selection_menu([{
                "label": f"Mute Application: {arg}", 
                "value": arg, 
                "action_type": "mute_app"
            }], category="🔕  App Audio")
            return

        # Media Controls
        if cmd in ["next", "prev", "pause", "play"]:
            self.show_selection_menu([{
                "label": f"Media: {cmd.capitalize()}", 
                "value": cmd, 
                "action_type": "media_control"
            }], category="🎵  Media")
            return
        
        # System Commands
        if cmd in ["lock", "kill", "bin", "off", "zzz", "clip"]:
            self.reset_ui()
            return
        
        # Project Search
        if cmd == "p" and arg:
            results = self.everything.search(f"folder:*{arg}*")
            if results:
                opts = [
                    {
                        "label": r["label"],
                        "value": f'code "{r["value"]}"',
                        "action_type": "cmd",
                    }
                    for r in results
                ]
                self.show_selection_menu(opts, category="💻  Projects")
            else:
                self.show_no_results()
            return
        
        # Standard File Search
        results = self.everything.search(query)
        if results:
            # 1. Use the new FAST logic
            optimized_results = self.prioritize_results(results)
            
            # 2. Pass directly to show_selection_menu
            self.show_selection_menu(optimized_results)
        else:
            self.reset_ui()
    
    def prioritize_results(self, results):
        """
        FAST LOGIC (Ported from Tkinter):
        1. No os.path.isdir() calls (prevents lag).
        2. Strict .exe/.lnk priority.
        3. Hard limit of 15 items.
        """
        apps = []
        others = []
        
        # Fast junk filters (String match only)
        junk_patterns = [
            "\\AppData\\Local\\Temp", ".sys", ".dll", ".cab", 
            "$Recycle", "AppCrash", "Uninstall", "setup.exe", "install.exe"
        ]
        
        # Process ONLY the first 100 items to guarantee 0 lag
        for res in results[:100]:
            path_val = res.get("value", "")
            if not path_val:
                continue
                
            path_lower = path_val.lower()
            
            # 1. Soft Filter: Skip garbage
            if any(junk.lower() in path_lower for junk in junk_patterns):
                continue
            
            # 2. Sorting: Apps vs Files (String check only - INSTANT)
            if path_lower.endswith(".exe") or path_lower.endswith(".lnk"):
                # Clean label (remove .exe extension from name)
                if "." in res["label"]:
                    res["label"] = res["label"].rsplit(".", 1)[0]
                
                res["category"] = "app"
                res["action_type"] = "file"
                apps.append(res)
            else:
                # Assume it's a generic file/folder for now to save speed
                # We let the UI renderer decide the icon later
                res["category"] = "file" 
                res["action_type"] = "file"
                others.append(res)
        
        # 3. Sort Apps by length (Shortest = Most likely match)
        # e.g. "Discord" (7 chars) beats "Discord Crash Handler" (21 chars)
        apps.sort(key=lambda x: len(x["label"]))
        
        # 4. Merge and Chop (Apps first, then others, max 15 total)
        final_list = (apps + others)[:15]
        
        return final_list
    
    def _calculate_results_height(self, item_count: int, header_count: int) -> int:
        """FIX: More accurate height calculation."""
        items_height = item_count * (ITEM_HEIGHT + ITEM_SPACING)
        headers_height = header_count * HEADER_HEIGHT
        # FIX: Add spacing after headers, not multiply
        header_spacing = header_count * ITEM_SPACING
        padding = CONTENT_PADDING * 2
        return items_height + headers_height + header_spacing + padding
    
    def show_categorized_results(self, categorized: dict):
        """Display results grouped by category."""
        self._clear_results()
        self.menu_active = True
        
        total_items = sum(len(v) for v in categorized.values())
        if total_items == 0:
            self.show_no_results()
            return
        
        num_headers = sum(1 for v in categorized.values() if v)
        needed_height = self._calculate_results_height(total_items, num_headers)
        frame_height = min(needed_height, self.max_list_height)
        
        self.divider.show()
        self.scroll_area.show()
        self.scroll_area.setFixedHeight(frame_height)
        self.setFixedHeight(self.base_height + frame_height + 28)
        
        insert_index = 0
        
        # Apps section
        if categorized.get("apps"):
            header = CategoryHeader("🚀  Applications")
            self.results_layout.insertWidget(insert_index, header)
            insert_index += 1
            
            for option in categorized["apps"]:
                item = self._create_result_item(option, len(self.result_items))
                self.results_layout.insertWidget(insert_index, item)
                insert_index += 1
                self.result_items.append(item)
        
        # Folders section
        if categorized.get("folders"):
            header = CategoryHeader("📁  Folders")
            self.results_layout.insertWidget(insert_index, header)
            insert_index += 1
            
            for option in categorized["folders"]:
                item = self._create_result_item(option, len(self.result_items))
                self.results_layout.insertWidget(insert_index, item)
                insert_index += 1
                self.result_items.append(item)
        
        # Files section
        if categorized.get("files"):
            header = CategoryHeader("📄  Files")
            self.results_layout.insertWidget(insert_index, header)
            insert_index += 1
            
            for option in categorized["files"]:
                item = self._create_result_item(option, len(self.result_items))
                self.results_layout.insertWidget(insert_index, item)
                insert_index += 1
                self.result_items.append(item)
        
        if self.result_items:
            self.selected_index = 0
            self._update_selection()
    
    def _create_result_item(self, option: dict, index: int) -> ResultItem:
        """Create a single result item."""
        label = option.get("label", "Unknown")
        raw_val = str(option.get("value", option.get("url", "")))
        
        icon, icon_col, subtext = self._get_item_display(option, label, raw_val)
        
        item = ResultItem(icon, icon_col, label, subtext, self.colors, self.current_query)
        item.full_path = raw_val
        item.command_ref = self._make_command(option)
        item.clicked.connect(item.command_ref)
        
        return item
    
    def show_no_results(self):
        """Display empty state when no results found."""
        self._clear_results()
        self.menu_active = False
        
        self.divider.show()
        self.scroll_area.show()
        self.scroll_area.setFixedHeight(100)
        self.setFixedHeight(self.base_height + 100 + 28)
        
        no_results = NoResultsWidget()
        self.results_layout.insertWidget(0, no_results)

    # ========================================================================
    #  RESULTS DISPLAY
    # ========================================================================
    
    def show_selection_menu(self, options, search_arg="", category=""):
        """Display search results list."""
        self._clear_results()
        self.menu_active = True
        
        header_count = 1 if category else 0
        needed_height = self._calculate_results_height(len(options), header_count)
        frame_height = min(needed_height, self.max_list_height)
        
        self.divider.show()
        self.scroll_area.show()
        self.scroll_area.setFixedHeight(frame_height)
        self.setFixedHeight(self.base_height + frame_height + 28)
        
        insert_index = 0
        
        if category:
            header = CategoryHeader(category)
            self.results_layout.insertWidget(insert_index, header)
            insert_index += 1
        
        for i, option in enumerate(options):
            label = option.get("label", "Unknown")
            raw_val = str(option.get("value", option.get("url", "")))
            
            icon, icon_col, subtext = self._get_item_display(option, label, raw_val)
            
            item = ResultItem(icon, icon_col, label, subtext, self.colors, self.current_query)
            item.full_path = raw_val
            item.command_ref = self._make_command(option, search_arg)
            item.clicked.connect(item.command_ref)
            
            self.results_layout.insertWidget(insert_index, item)
            insert_index += 1
            self.result_items.append(item)
        
        self.selected_index = 0
        self._update_selection()
    
    def _get_item_display(self, option, label, raw_val):
        """Determine icon, color, and subtext for result item."""
        icon = "📄"
        icon_col = self.colors["icon_default"]
        subtext = raw_val
        
        action_type = option.get("action_type", "")
        
        if action_type == "cmd" and "code" in raw_val:
            icon, icon_col = "💻", self.colors["icon_code"]
            subtext = self._smart_truncate(raw_val.replace('code "', "").replace('"', ""))
        elif action_type == "file":
            is_folder = os.path.isdir(raw_val) if os.path.exists(raw_val) else False
            icon, icon_col = self._get_file_style(label, is_folder, raw_val)
            subtext = self._smart_truncate(raw_val)
        elif action_type == "copy":
            icon, icon_col = "📋", self.colors["icon_doc"]
            subtext = "Press Enter to copy to clipboard"
        elif "url" in option:
            icon, icon_col = "🌐", self.colors["accent"]
        elif action_type == "ocr_trigger":
            icon, icon_col = "👁️", self.colors["warning"]
            subtext = "Select area on screen to capture text"
        elif action_type == "volume":
            icon, icon_col = "🔊", self.colors["success"]
            subtext = "Adjust system volume"
        elif action_type in ["mute_system", "mute_mic", "mute_app"]:
            icon, icon_col = "🔇", self.colors["warning"]
            subtext = "Toggle mute state"
        elif action_type == "media_control":
            icon, icon_col = "🎵", self.colors["accent"]
            subtext = "Control media playback"
        elif action_type == "audio":
            icon, icon_col = "🎧", self.colors["success"]
            subtext = "Switch audio output device"
        elif action_type == "kill_port":
            icon, icon_col = "⚡", self.colors["warning"]
            subtext = f"Terminate process on port {raw_val}"
            
        return icon, icon_col, subtext
    
    def _get_file_style(self, filename, is_folder=False, full_path=""):
        """Get icon and color based on file type."""
        if is_folder:
            return "📂", self.colors["icon_folder"]
        
        path_lower = full_path.lower()
        if path_lower.endswith((".exe", ".lnk")):
            return "🚀", self.colors["icon_app"]
        
        ext = filename.split(".")[-1].lower() if "." in filename else ""
        
        ext_map = {
            "icon_image": ["png", "jpg", "jpeg", "gif", "webp", "svg", "ico", "bmp"],
            "icon_code": ["py", "js", "ts", "html", "css", "json", "jsx", "tsx", "vue", "cpp", "c", "h", "java", "go", "rs"],
            "icon_doc": ["pdf", "doc", "docx", "txt", "md", "rtf", "odt", "xls", "xlsx"],
            "icon_zip": ["zip", "rar", "7z", "tar", "gz", "bz2"],
        }
        
        icons = {
            "icon_image": "🖼️",
            "icon_code": "📄",
            "icon_doc": "📝",
            "icon_zip": "📦",
        }
        
        for color_key, extensions in ext_map.items():
            if ext in extensions:
                return icons.get(color_key, "📄"), self.colors.get(color_key, self.colors["icon_default"])
        
        return "📄", self.colors["icon_default"]
    
    def _smart_truncate(self, path, max_chars=55):
        """Intelligently truncate long paths."""
        if not path or len(path) <= max_chars:
            return path
        
        parts = path.replace("\\", "/").split("/")
        if len(parts) < 4:
            return path[:max_chars - 3] + "..."
        
        return f"{parts[0]}/…/{parts[-2]}/{parts[-1]}"
    
    def _make_command(self, option, search_arg=""):
        """Create callback function for result item."""
        def callback():
            if self.current_query:
                self.add_to_recent(self.current_query)
            
            self._do_hide()
            if option.get("action_type") == "ocr_trigger":
                self.snipper = Snipper() 
                return
            if "action_type" in option:
                execute_action({
                    "type": option["action_type"],
                    "value": option.get("value", "")
                })
            elif "url" in option:
                url = option["url"]
                if search_arg:
                    url += search_arg.replace(" ", "+")
                execute_action({"type": "url", "value": url})
        return callback

    # ========================================================================
    #  NAVIGATION - FIXED
    # ========================================================================
    
    def nav_down(self):
        """Move selection down."""
        if not self.menu_active or not self.result_items:
            return
        
        self.selected_index = (self.selected_index + 1) % len(self.result_items)
        self._update_selection()
    
    def nav_up(self):
        """Move selection up, or recall last command if no results."""
        if self.menu_active and self.result_items:
            self.selected_index = (self.selected_index - 1) % len(self.result_items)
            self._update_selection()
        elif self.last_command and not self.menu_active:
            self.entry.setText(self.last_command)
            self.entry.setCursorPosition(len(self.last_command))
    
    def _update_selection(self):
        """FIX: Update visual selection with proper repaint handling."""
        if self._updating_selection:
            return
        
        self._updating_selection = True
        
        try:
            # Update all items
            for i, item in enumerate(self.result_items):
                is_selected = (i == self.selected_index)
                item.set_selected(is_selected)
                item.set_shortcut_hint("↵ Open" if is_selected else "")
            
            # FIX: Force repaint of scroll area viewport
            self.scroll_area.viewport().update()
            
            # Scroll to selected item
            self._scroll_to_selected()
            
        finally:
            self._updating_selection = False
    
    def _scroll_to_selected(self):
        """FIX: Scroll to ensure selected item is visible."""
        if not (0 <= self.selected_index < len(self.result_items)):
            return
        
        selected_item = self.result_items[self.selected_index]
        
        # FIX: Use ensureWidgetVisible for more reliable scrolling
        self.scroll_area.ensureWidgetVisible(
            selected_item, 
            xMargin=0, 
            yMargin=ITEM_SPACING + 4
        )
        
        # FIX: Force horizontal scroll to 0
        h_scrollbar = self.scroll_area.horizontalScrollBar()
        if h_scrollbar.value() != 0:
            h_scrollbar.setValue(0)

    # ========================================================================
    #  ACTIONS
    # ========================================================================
    
    def on_submit(self):
        """Handle Enter key press."""
        if self.menu_active and 0 <= self.selected_index < len(self.result_items):
            self.result_items[self.selected_index].command_ref()
            return
        
        query = self.entry.text().strip()
        if not query:
            self._do_hide()
            return
        
        # Calculator
        if any(c in query for c in "+-*/") and not query.startswith("http"):
            if re.match(r'^[\d+\-*/().% ]+$', query):
                try:
                    result = str(eval(query, {"__builtins__": None}, {}))
                    self.entry.setText(result)
                    self.entry.selectAll()
                    return
                except Exception:
                    pass
        
        self.last_command = query
        parts = query.split(" ", 1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""
        if cmd == "yt" and arg:
            url = f"https://www.youtube.com/results?search_query={arg}"
            webbrowser.open(url)
            self._do_hide()
            return
        if cmd == "p" and arg:
            results = self.everything.search(f"folder:*{arg}*")
            if results:
                self.show_selection_menu([
                    {"label": r["label"], "value": f'code "{r["value"]}"', "action_type": "cmd"}
                    for r in results
                ], category="💻  Projects")
                return
        
        if cmd in self.mapping:
            action = self.mapping[cmd]
            if action.get("type") == "search_selection" and arg:
                self.show_selection_menu(action["value"], arg)
                return
            self._do_hide()
            action["search_term"] = arg
            execute_action(action)
            return
        
        if cmd == "clip":
            hist = self.clipboard.get_history()
            if not hist:
                self._do_hide()
                return
            self.show_selection_menu([
                {
                    "label": h[:50].replace("\n", " ").strip() + ("…" if len(h) > 50 else ""),
                    "value": h,
                    "action_type": "copy",
                }
                for h in hist
            ], category="📋  Clipboard History")
            return
        
        results = self.everything.search(query)
        if results:
            results = self.prioritize_results(results)
            self.show_categorized_results(results)
        else:
            self.show_no_results()
    
    def on_ctrl_submit(self):
        """Ctrl+Enter: Open file location in Explorer."""
        if self.menu_active and 0 <= self.selected_index < len(self.result_items):
            path = self.result_items[self.selected_index].full_path
            path = path.replace('code "', "").replace('"', "")
            if path and os.path.exists(path):
                subprocess.Popen(f'explorer /select,"{path}"')
                self._do_hide()
    
    def on_copy_path(self):
        """Alt+C: Copy selected path to clipboard."""
        if self.menu_active and 0 <= self.selected_index < len(self.result_items):
            path = self.result_items[self.selected_index].full_path
            path = path.replace('code "', "").replace('"', "")
            pyperclip.copy(path)
            
            self.container.set_border_color(self.colors["success"])
            QTimer.singleShot(300, self._do_hide)
    
    def on_tab_complete(self):
        """Tab: Autocomplete with selected item."""
        if self.menu_active and 0 <= self.selected_index < len(self.result_items):
            item = self.result_items[self.selected_index]
            title = item._label_text
            self.entry.setText(title)
            self.entry.setCursorPosition(len(title))
    
    def run(self):
        """Legacy method for compatibility."""
        pass


# ============================================================================
#  STANDALONE TESTING
# ============================================================================

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI Variable Display", 10))
    
    test_config = {
        "theme": {"width": 680},
        "launcher_mapping": {}
    }
    
    launcher = Launcher(test_config)
    launcher.show_launcher()
    
    sys.exit(app.exec())