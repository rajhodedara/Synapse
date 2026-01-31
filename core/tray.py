from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QBrush
from PyQt6.QtCore import Qt, QSize
import sys

def create_programmatic_icon():
    """Generates a QIcon programmatically (Dark square with cyan dot)"""
    # Create a 64x64 pixmap
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    # Background (Dark Grey)
    # Note: On Windows 10/11, tray icons usually look better transparent or simple
    # But we'll stick to your design:
    brush = QBrush(QColor("#1e1e1e"))
    painter.setBrush(brush)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(0, 0, 64, 64, 12, 12)
    
    # Cyan Dot
    brush = QBrush(QColor("#00bcd4"))
    painter.setBrush(brush)
    painter.drawEllipse(16, 16, 32, 32)
    
    painter.end()
    return QIcon(pixmap)

class SystemTray:
    def __init__(self, app, quit_callback):
        self.app = app
        self.quit_callback = quit_callback
        
        # 1. Create Icon
        self.tray_icon = QSystemTrayIcon(app)
        self.tray_icon.setIcon(create_programmatic_icon())
        self.tray_icon.setToolTip("Keyboard OS")
        
        # 2. Create Context Menu
        self.menu = QMenu()
        
        # Title Action (Disabled, just for show)
        title_action = self.menu.addAction("Keyboard OS")
        title_action.setEnabled(False)
        
        self.menu.addSeparator()
        
        # Exit Action
        exit_action = self.menu.addAction("Exit")
        exit_action.triggered.connect(self.on_exit)
        
        # 3. Attach Menu to Icon
        self.tray_icon.setContextMenu(self.menu)
        self.tray_icon.show()
        
    def on_exit(self):
        self.tray_icon.hide()
        if self.quit_callback:
            self.quit_callback()

def setup_tray(app, on_quit):
    """
    Helper function to initialize the tray.
    In PyQt, we just instantiate the class and keep a reference.
    """
    return SystemTray(app, on_quit)