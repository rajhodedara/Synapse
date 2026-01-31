import ctypes
import os
import subprocess
import time
import urllib.parse
import webbrowser
from datetime import datetime

import keyboard
import pyperclip


def save_note(content):
    """Appends text to a notes file on the Desktop"""
    try:
        desktop = os.path.expandvars("%USERPROFILE%/Desktop")
        file_path = os.path.join(desktop, "quick_notes.txt")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        with open(file_path, "a") as f:
            f.write(f"[{timestamp}] {content}\n")

        print(f"Note saved: {content}")

    except Exception as e:
        print(f"Error saving note: {e}")


def execute_action(action):
    """
    Main entry point to execute commands.
    """
    action_type = action.get("type")
    value = action.get("value")

    # Retrieve the argument (e.g., "chrome" from "kill chrome")
    arg = action.get("search_term", "")

    try:
        # 1. SYSTEM COMMANDS
        if action_type == "sys":
            run_system_command(value, arg)

        # 2. URL (Websites)
        elif action_type == "url":
            webbrowser.open(value)

        # 3. FILE / FOLDER (Portable Paths)
        elif action_type == "file" or action_type == "folder":
            expanded_path = os.path.expandvars(value)
            os.startfile(expanded_path)

        # 4. SMART SEARCH (Hybrid: Manual or Selection)
        elif action_type == "smart_search":
            # Pass 'arg' so we know if user typed something
            handle_smart_search(value, arg)

        # 5. COMMAND LINE / TERMINAL
        elif action_type == "cmd" or action_type == "exec":
            subprocess.Popen(value, shell=True)

        # 6. NOTES
        elif action_type == "note":
            if arg:
                save_note(arg)
            else:
                desktop = os.path.expandvars("%USERPROFILE%/Desktop")
                os.startfile(os.path.join(desktop, "quick_notes.txt"))

        # 7. SMART PASTE (Copy + Auto-Paste)
        elif action_type == "copy":
            pyperclip.copy(value)
            time.sleep(0.2)
            keyboard.send("ctrl+v")
            print(f"Pasted: {value[:10]}...")

        # 8. KILL PORT PROCESS (New Feature)
        # 8. KILL PORT PROCESS (Robust Version)
        elif action_type == "kill_port":
            port = value
            print(f"Scanning port {port}...")
            
            try:
                # 1. Get all connections on the port
                # We use check_output to get the text result of netstat
                output = subprocess.check_output(f"netstat -aon | findstr :{port}", shell=True).decode()
                
                # 2. Extract unique PIDs
                pids = set()
                for line in output.strip().split("\n"):
                    parts = line.strip().split()
                    # PID is usually the last column (index 4 or -1)
                    if len(parts) >= 5:
                        pid = parts[-1]
                        if pid.isdigit() and pid != "0": # Ignore System process (0)
                            pids.add(pid)
                
                if not pids:
                    print(f"No active process found on port {port}.")
                    return

                # 3. Kill each unique PID once
                for pid in pids:
                    print(f"Killing PID {pid}...")
                    # Capture output to prevent "Process not found" spam
                    subprocess.run(f"taskkill /f /pid {pid}", shell=True, capture_output=True)
                
                print(f"✅ Port {port} successfully cleared.")

            except subprocess.CalledProcessError:
                # subprocess raises this if 'findstr' finds nothing (exit code 1)
                print(f"ℹ️ Port {port} is already free.")
            except Exception as e:
                print(f"❌ Error clearing port: {e}")
        elif action_type == "audio":
            device_name = value
            print(f"Switching audio to: {device_name}")
            
            # Use nircmd from the vendor folder
            # 'setdefaultsounddevice' sets it for both system sounds and apps
            cmd = f'vendor\\nircmd.exe setdefaultsounddevice "{device_name}"'
            
            subprocess.run(cmd, shell=True)
            
            # Optional: Visual confirmation via print or you could play a beep
            print(f"Audio switched to {device_name}")
    # 9. VOLUME CONTROL
        elif action_type == "volume":
            # NirCmd scale is 0-65535
            nircmd_val = int(65535 * int(value) / 100)
            subprocess.run(f'vendor\\nircmd.exe setsysvolume {nircmd_val}', shell=True)
            print(f"Volume set to {value}%")

        # 10. SYSTEM MUTE
        elif action_type == "mute_system":
            # 2 = Toggle
            subprocess.run('vendor\\nircmd.exe mutesysvolume 2', shell=True)
            print("System audio toggled.")

        # 11. MIC MUTE (The Hackathon Lifesaver)
        elif action_type == "mute_mic":
            # "default_record" targets your main mic
            subprocess.run('vendor\\nircmd.exe mutesysvolume 2 "default_record"', shell=True)
            print("Microphone toggled.")

        # 12. APP MUTE (Target specific process)
        elif action_type == "mute_app":
            app_name = value if value.endswith(".exe") else f"{value}.exe"
            # muteappvolume requires process name and 1 (mute), 0 (unmute), or 2 (toggle)
            subprocess.run(f'vendor\\nircmd.exe muteappvolume "{app_name}" 2', shell=True)
            print(f"Toggled mute for {app_name}")

        # 13. MEDIA KEYS
        elif action_type == "media_control":
            key_map = {
                "next": "0xB0",  # VK_MEDIA_NEXT_TRACK
                "prev": "0xB1",  # VK_MEDIA_PREV_TRACK
                "pause": "0xB3", # VK_MEDIA_PLAY_PAUSE
                "play": "0xB3"
            }
            if value in key_map:
                key_code = key_map[value]
                subprocess.run(f'vendor\\nircmd.exe sendkeypress {key_code}', shell=True)
    except Exception as e:
        print(f"General Execution Error: {e}")
        
        


def run_system_command(cmd, arg=""):
    """
    Handles low-level Windows commands.
    """
    if cmd == "lock":
        ctypes.windll.user32.LockWorkStation()

    elif cmd == "shutdown":
        os.system("shutdown /s /t 0")

    elif cmd == "sleep":
        os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")

    elif cmd == "empty_bin":
        try:
            SHEmptyRecycleBin = ctypes.windll.shell32.SHEmptyRecycleBinW
            SHEmptyRecycleBin(None, None, 7)
        except:
            pass

    elif cmd == "kill":
        if arg:
            print(f"Killing {arg}...")
            os.system(f"taskkill /f /im {arg}.exe")


def handle_smart_search(base_url, manual_query=""):
    """
    Hybrid Search:
    1. If user typed text ('gs hello'), search immediately.
    2. If user typed nothing ('gs'), copy selected text and search.
    """
    try:
        # --- CASE A: Manual Typing (gs hello) ---
        if manual_query:
            # If URL supports queries (Google/Perplexity Search)
            if base_url.endswith("=") or "?" in base_url:
                encoded_text = urllib.parse.quote(manual_query)
                webbrowser.open_new(f"{base_url}{encoded_text}")
            # If Clean URL (Gemini Home/ChatGPT Home)
            else:
                # We can't force text into homepages, so just open them
                webbrowser.open_new(base_url)
            return

        # --- CASE B: Smart Selection (gs) ---
        pyperclip.copy("")  # Clear clipboard

        # Release modifiers to prevent stuck keys
        keyboard.release("alt")
        keyboard.release("ctrl")
        time.sleep(0.05)

        # Human-like 'Ctrl+C'
        keyboard.press("ctrl")
        keyboard.send("c")
        time.sleep(0.1)
        keyboard.release("ctrl")

        # Wait for text
        selected_text = ""
        for _ in range(10):
            time.sleep(0.05)
            selected_text = pyperclip.paste().strip()
            if selected_text:
                break

        # Logic: Google vs AI Homepages
        # If it's a search engine, we add the text to the URL.
        if "?" in base_url or "=" in base_url:
            if selected_text:
                encoded_text = urllib.parse.quote(selected_text)
                webbrowser.open_new(f"{base_url}{encoded_text}")
            else:
                webbrowser.open_new(base_url)
        # If it's an AI homepage (Clean URL), we just open it.
        # User can Paste manually (Ctrl+V) since text is in clipboard.
        else:
            webbrowser.open_new(base_url)

    except Exception as e:
        print(f"Smart Search Error: {e}")
        webbrowser.open(base_url)