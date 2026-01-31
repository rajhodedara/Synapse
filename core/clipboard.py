import threading
import time

import pyperclip


class ClipboardManager:
    def __init__(self, max_items=20):
        self.history = []
        self.max_items = max_items
        self.last_text = ""

        # Start the listener in a background thread
        # daemon=True means it dies when the main app closes
        self.thread = threading.Thread(target=self.monitor_clipboard, daemon=True)
        self.thread.start()

    def monitor_clipboard(self):
        """Checks every 0.5s if the clipboard content changed"""
        while True:
            try:
                # Get current clipboard content
                current_text = pyperclip.paste()

                # If it's valid text and different from the last thing we saw
                if (
                    current_text
                    and current_text.strip()
                    and current_text != self.last_text
                ):
                    self.last_text = current_text
                    self.add_to_history(current_text)

            except Exception as e:
                print(f"Clipboard Error: {e}")

            # Sleep to save CPU
            time.sleep(0.5)

    def add_to_history(self, text):
        # Remove duplicates if they exist (move to top)
        if text in self.history:
            self.history.remove(text)

        # Add to the front (Top of the list)
        self.history.insert(0, text)

        # Keep list size manageable
        if len(self.history) > self.max_items:
            self.history.pop()

    def get_history(self):
        return self.history
