"""Start ATOM quietly when Windows starts.

python autostart.py on    -> adds ATOM to your Startup folder
python autostart.py off   -> removes it
"""

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STARTUP = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
LINK = STARTUP / "ATOM.lnk"


def turn_on():
    import win32com.client
    pythonw = HERE / ".venv" / "Scripts" / "pythonw.exe"
    if not pythonw.exists():
        pythonw = Path(sys.executable).with_name("pythonw.exe")
    shell = win32com.client.Dispatch("WScript.Shell")
    link = shell.CreateShortCut(str(LINK))
    link.Targetpath = str(pythonw)
    link.Arguments = f'"{HERE / "atom.py"}"'
    link.WorkingDirectory = str(HERE)
    link.save()
    print("ATOM will start with Windows:", LINK)


def turn_off():
    if LINK.exists():
        LINK.unlink()
    print("ATOM won't start with Windows anymore.")


choice = sys.argv[1].lower() if len(sys.argv) > 1 else "on"
turn_off() if choice == "off" else turn_on()
