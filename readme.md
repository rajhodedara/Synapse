
# ⌨️ Synapse

> **Never leave the keyboard.**

**Synapse** is a powerful, keyboard-centric productivity tool for Windows. It combines a Spotlight-like Application Launcher with a Tiling Window Manager, integrating system control, file search, and AI workflows into a single, high-performance Python application.

---

## 🚀 Key Features

### 🔍 The Launcher (`Ctrl` + `Space`)
A frameless, modern UI that adapts to your context. The border glows to indicate status:
*   🔵 **Blue:** Standard Search
*   🟠 **Orange:** System Warning/Alert
*   🟢 **Green:** Success/Action Completed

**Capabilities:**
*   **Universal Search:** Instant file/folder search (powered by the *Everything* engine).
*   **Web Shortcuts:** Smart keywords like `gs` (Google), `gpt` (ChatGPT), and `perp` (Perplexity).
*   **Calculator:** Type  (`500/12`) for instant answers.
*   **Clipboard Manager:** Type `clip` to access history or use Smart Paste for auto-formatting.
*   **OCR / Vision:** Type `ocr` to draw a box on the screen and capture text from images directly to your clipboard.

### 💻 Developer Tools
*   **Project Jump:** `p <name>` to quickly find and open VS Code projects.
*   **Kill Port:** `kp <port>` finds and kills the process blocking a specific TCP port (e.g., localhost:3000).
*   **Process Killer:** `kill <name>` terminates stuck applications instantly.

### 🪟 Tiling Window Manager
Manage windows without touching the mouse using standard or Vim-style bindings.
*   **Snap & Tile:** Left, Right, Maximize, Center, and Corners.
*   **Multi-Monitor:** Throw windows to the next screen instantly.
*   **Ghost Mode:** Toggle window transparency to reference content behind your active window.

### 🔊 System & Audio Control
*   **Device Switch:** Type `audio` to toggle between Headphones and Speakers.
*   **Volume Mixer:** `vol <0-100>`, `mute`, or `ma <app>` to mute specific apps.
*   **Media:** Global controls for `play`, `pause`, `next`, `prev`.
*   **Power:** Fast commands for `lock`, `off`, `zzz` (sleep), and `bin` (empty recycle bin).

---

## ⌨️ Hotkeys & Usage

### Global Hotkeys
| Key Combination | Action |
| :--- | :--- |
| <kbd>Ctrl</kbd> + <kbd>Space</kbd> | **Open Launcher** |
| <kbd>Alt</kbd> + <kbd>V</kbd> | Open Clipboard History |
| <kbd>Alt</kbd> + <kbd>1</kbd> - <kbd>4</kbd> | Quick Launch AI Tools (ChatGPT, Gemini, Claude, Arena.ai) |
| <kbd>Alt</kbd> + <kbd>G</kbd> | Smart Google Search (searches selected text) |
| <kbd>Alt</kbd> + <kbd>T</kbd> | Smart ChatGPT Search (sends selected text) |

### Window Management
| Action | Standard Keys | Vim-Style Keys |
| :--- | :--- | :--- |
| **Snap Left** | <kbd>Win</kbd> + <kbd>Alt</kbd> + <kbd>⬅️</kbd> | <kbd>Win</kbd> + <kbd>Alt</kbd> + <kbd>H</kbd> |
| **Snap Right** | <kbd>Win</kbd> + <kbd>Alt</kbd> + <kbd>➡️</kbd> | <kbd>Win</kbd> + <kbd>Alt</kbd> + <kbd>L</kbd> |
| **Maximize** | <kbd>Win</kbd> + <kbd>Alt</kbd> + <kbd>⬆️</kbd> | <kbd>Win</kbd> + <kbd>Alt</kbd> + <kbd>K</kbd> |
| **Center** | <kbd>Win</kbd> + <kbd>Alt</kbd> + <kbd>⬇️</kbd> | <kbd>Win</kbd> + <kbd>Alt</kbd> + <kbd>J</kbd> |
| **Move Monitor** | <kbd>Win</kbd> + <kbd>Alt</kbd> + <kbd>M</kbd> | — |
| **Ghost Mode** | <kbd>Win</kbd> + <kbd>Alt</kbd> + <kbd>O</kbd> | (Toggle Transparency) |

### Launcher Navigation
*   <kbd>Tab</kbd>: Autocomplete
*   <kbd>Enter</kbd>: Execute / Open
*   <kbd>Ctrl</kbd> + <kbd>Enter</kbd>: Reveal file in Explorer
*   <kbd>Alt</kbd> + <kbd>C</kbd>: Copy file path

---

## ⚙️ Configuration
Customize your experience by editing the `config.json` file located in the installation folder.

```json
{
  "theme": {
    "accent_color": "#0078D7",
    "font_size": 14
  },
  "audio_aliases": {
    "Headphones": "head",
    "Speakers": "spk"
  },
  "custom_keywords": {
    "gh": "https://github.com",
    "work": "C:\\Users\\Name\\Documents\\Work"
  }
}
```

---

## 🛠️ Technology Stack
*   **Core:** Python 3.x
*   **GUI:** PyQt6 (Modern, frameless design)
*   **Input:** `keyboard` library (Global hooks)
*   **System API:** `ctypes`, `win32api`
*   **Audio/Window Backend:** `nircmd.exe`
*   **Search Backend:** Voidtools "Everything" SDK

---

## 📥 Installation

### Option 1: Quick Start (Recommended)
No coding required.

1.  Go to the **[Releases](../../releases)** page.
2.  Download **`KeyboardOS-v1.0.zip`**.
3.  Extract the ZIP file to a permanent location (e.g., `C:\Apps\KeyboardOS`).
4.  Double-click **`KeyboardOS.exe`** to start.

> **Note:** The "Everything" search engine is included. Please allow it to index your files on the first run for instant search results.

### Option 2: Run at Startup
1.  Press <kbd>Win</kbd> + <kbd>R</kbd>.
2.  Type `shell:startup` and hit <kbd>Enter</kbd>.
3.  Right-click `KeyboardOS.exe` in your app folder and select **Create Shortcut**.
4.  Drag the shortcut into the **Startup** folder.

### Option 3: For Developers
If you want to modify the source code:

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/KeyboardOS.git

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the application
python main.py
```

---

## 📄 License
[MIT](LICENSE) © [Your Name]