import os
import subprocess
import sys  # <--- Make sure sys is imported!
import threading


class EverythingManager:
    def __init__(self):
        # --- PATH FIX START ---
        if getattr(sys, "frozen", False):
            # We are running as an EXE (ProductivityLauncher.exe)
            # The base path is the folder containing the .exe
            base_path = os.path.dirname(sys.executable)
        else:
            # We are running as a script (VS Code)
            # The base path is the project root (up one level from 'core')
            base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        self.es_path = os.path.join(base_path, "vendor", "es.exe")
        self.exe_path = os.path.join(base_path, "vendor", "Everything.exe")
        # --- PATH FIX END ---

        self.current_process = None

        # Start engine silently if needed
        threading.Thread(target=self.ensure_running, daemon=True).start()

    def ensure_running(self):
        try:
            output = subprocess.check_output("tasklist", shell=True).decode()
            if "Everything.exe" not in output:
                if os.path.exists(self.exe_path):
                    subprocess.Popen([self.exe_path, "-startup"])
        except:
            pass

    def search(self, query, limit=100):
        if not query:
            return []

        # Debounce
        if self.current_process and self.current_process.poll() is None:
            try:
                self.current_process.kill()
            except:
                pass

        try:
            # FIX 2: NO MANUAL QUOTES (The Quote Bug)
            # We pass the raw query. Python handles spaces/quotes automatically.
            cmd = [
                self.es_path,
                query,
                "-sort",
                "run-count-descending",
                "-n",
                str(limit),
            ]

            # Basic Filters
            cmd += ["!node_modules", "!$Recycle.Bin", "!Windows\\Installer"]

            # Windows-specific startup flags to hide the console window
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",  # Prevents crashes on weird filenames
                startupinfo=startupinfo,
            )

            stdout, _ = self.current_process.communicate()

            results = []
            if stdout:
                lines = stdout.strip().split("\n")
                for line in lines:
                    if line.strip():
                        full_path = line.strip()
                        filename = os.path.basename(full_path)

                        # Just append results (Sorting happens in Python/Launcher now)
                        results.append(
                            {"label": filename, "value": full_path, "type": "file"}
                        )
            return results

        except Exception as e:
            print(f"Search Crash: {e}")
            return []
