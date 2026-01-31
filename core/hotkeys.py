import keyboard

from core.actions import execute_action


def register_hotkeys(config):
    """
    Iterates through config and registers global hotkeys.
    """
    hotkeys = config.get("hotkeys", {})

    print("--- Registering Shortcuts ---")

    for key_combo, action_data in hotkeys.items():
        # We use a lambda to pass specific data to the handler
        # suppress=True prevents the keystroke from sending to other apps (optional)
        keyboard.add_hotkey(key_combo, lambda d=action_data: execute_action(d))
        print(f"[+] Registered: {key_combo}")

    print("---------------------------")
