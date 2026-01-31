import os
import sys
import threading

import pystray
from PIL import Image, ImageDraw


def create_icon():
    """Generates a simple icon (black box with a cyan dot)"""
    width = 64
    height = 64
    color1 = "#1e1e1e"  # Dark Grey
    color2 = "#00bcd4"  # Cyan

    image = Image.new("RGB", (width, height), color1)
    dc = ImageDraw.Draw(image)

    # Draw a circle in the middle
    dc.ellipse((width // 4, height // 4, 3 * width // 4, 3 * height // 4), fill=color2)

    return image


def setup_tray(on_quit):
    """
    Creates the system tray icon with a menu.
    on_quit: A function to call when 'Exit' is clicked.
    """

    def exit_action(icon, item):
        icon.stop()
        on_quit()

    image = create_icon()

    menu = pystray.Menu(
        pystray.MenuItem("Keyboard OS", lambda: None, enabled=False),  # Title
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "Reload Config", lambda: print("Reloading... (Not implemented yet)")
        ),
        pystray.MenuItem("Exit", exit_action),
    )

    icon = pystray.Icon("KeyboardOS", image, "Keyboard OS", menu)
    icon.run()  # This blocks the thread it runs on!
