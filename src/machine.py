import hashlib
import platform
import subprocess
import uuid

def _linux_id():
    try:
        with open("/etc/machine-id", "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        pass
    try:
        with open("/var/lib/dbus/machine-id", "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        pass
    return None

def _darwin_id():
    try:
        out = subprocess.check_output(
            ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
            text=True
        )
        for line in out.splitlines():
            if "IOPlatformUUID" in line:
                return line.split('"')[-2]
    except (subprocess.SubprocessError, IndexError):
        pass
    return None

def _windows_id():
    try:
        out = subprocess.check_output(
            ["reg", "query", "HKLM\\SOFTWARE\\Microsoft\\Cryptography", "/v", "MachineGuid"],
            text=True
        )
        for line in out.splitlines():
            if "MachineGuid" in line:
                return line.split()[-1]
    except (subprocess.SubprocessError, IndexError):
        pass
    return None

def get_raw_id():
    system = platform.system()
    if system == "Linux":
        return _linux_id()
    if system == "Darwin":
        return _darwin_id()
    if system == "Windows":
        return _windows_id()
    return None

def get_id():
    raw = get_raw_id()
    if not raw:
        raw = str(uuid.getnode())
    return hashlib.sha256(raw.encode()).hexdigest()[:12]
