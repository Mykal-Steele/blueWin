#!/usr/bin/env python3
"""
blueWin — Sync Bluetooth pairing keys from Windows to Linux.

Supports any Linux distro using BlueZ (/var/lib/bluetooth).
Tested: Arch, Ubuntu, Fedora, Debian, Mint.

Usage:
    sudo python3 bt_sync.py   # direct
    sudo bluewin              # after: pip install . or pipx install .

Workflow:
    1. Pair the device on Linux once (first time only — creates the record).
    2. Boot into Windows and pair the same device there.
    3. Boot back to Linux and run this script.
    4. Device connects without re-pairing. Repeat steps 2-3 any time.

IMPORTANT — disable Windows Fast Startup or keys on disk will be stale:
    Control Panel → Power Options → "Choose what the power buttons do"
    → uncheck "Turn on fast startup"
"""

import glob
import os
import re
import subprocess
import sys

VENV_DIR = "/tmp/bt_sync_venv"
HIVE_RELATIVE = "Windows/System32/config/SYSTEM"
AUTO_MOUNT = "/tmp/bt_sync_windows"


# ── Output ────────────────────────────────────────────────────────────────────


def header():
    print("bt-sync — Bluetooth dual-boot key sync")
    print("─" * 40)


def step(n, total, label):
    print(f"\n[{n}/{total}] {label}")


def info(msg):
    print(f"      {msg}")


def die(msg, *hints):
    print(f"\n  ERROR  {msg}")
    for h in hints:
        print(f"         {h}")
    sys.exit(1)


# ── Step 1: Dependencies ──────────────────────────────────────────────────────


def ensure_registry():
    """Make python-registry importable, auto-installing into a venv if needed."""
    try:
        from Registry import Registry  # noqa: F401  # type: ignore[import]

        info("python-registry ready")
        return
    except ImportError:
        pass

    venv_python = os.path.join(VENV_DIR, "bin", "python")

    if not os.path.exists(venv_python):
        info("Installing python-registry (one-time, ~5 s)...")
        try:
            import venv as _venv

            _venv.create(VENV_DIR, with_pip=True)
        except Exception as exc:
            die(
                f"Cannot create Python venv: {exc}",
                "Debian/Ubuntu:  sudo apt install python3-venv",
                "Fedora:         sudo dnf install python3",
                "Arch:           sudo pacman -S python",
            )

    result = subprocess.run(
        [venv_python, "-m", "pip", "install", "-q", "python-registry"],
        capture_output=True,
    )
    if result.returncode != 0:
        die("pip failed to install python-registry", result.stderr.decode().strip())

    # Re-exec under the venv Python so the package is importable from here on.
    os.execv(venv_python, [venv_python] + sys.argv)


# ── Step 2: Find Windows partition ───────────────────────────────────────────

MOUNT_GLOBS = [
    f"/run/media/*/*/{HIVE_RELATIVE}",  # Arch, Fedora, openSUSE
    f"/media/*/*/{HIVE_RELATIVE}",  # Ubuntu, Mint, Debian
    f"/media/*/{HIVE_RELATIVE}",  # Ubuntu (older layout)
    f"/mnt/*/{HIVE_RELATIVE}",  # manual mounts
    f"/mnt/{HIVE_RELATIVE}",  # /mnt directly
]


def _already_mounted_hive():
    for pattern in MOUNT_GLOBS:
        hits = glob.glob(pattern)
        if hits:
            return hits[0]
    # findmnt covers unusual/custom mount points
    try:
        r = subprocess.run(
            ["findmnt", "-t", "ntfs,ntfs-3g,ntfs3,fuseblk", "-o", "TARGET", "-n"],
            capture_output=True,
            text=True,
        )
        for target in r.stdout.strip().splitlines():
            candidate = os.path.join(target.strip(), HIVE_RELATIVE)
            if os.path.exists(candidate):
                return candidate
    except FileNotFoundError:
        pass
    return None


def _ntfs_devices():
    """Return block device paths that appear to be NTFS-formatted."""
    # lsblk is available on virtually all modern Linux systems
    try:
        r = subprocess.run(
            ["lsblk", "-o", "PATH,FSTYPE", "-n"],
            capture_output=True,
            text=True,
        )
        devices = []
        for line in r.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[1].lower().startswith("ntfs"):
                devices.append(parts[0])
        if devices:
            return devices
    except FileNotFoundError:
        pass

    # blkid as fallback
    try:
        r = subprocess.run(
            ["blkid", "-t", "TYPE=ntfs", "-o", "device"],
            capture_output=True,
            text=True,
        )
        return [d.strip() for d in r.stdout.splitlines() if d.strip()]
    except FileNotFoundError:
        pass

    return []


def _try_mount(device, mount_point):
    """Mount device read-only. Returns True on success."""
    os.makedirs(mount_point, exist_ok=True)
    r = subprocess.run(
        ["mount", "-o", "ro", device, mount_point],
        capture_output=True,
    )
    return r.returncode == 0


def unmount(mount_point):
    subprocess.run(["umount", mount_point], capture_output=True)
    try:
        os.rmdir(mount_point)
    except OSError:
        pass


def find_system_hive():
    """
    Return (hive_path, auto_mount_dir).
    auto_mount_dir is None if the partition was already mounted.
    Caller must unmount auto_mount_dir when done.
    """
    hive = _already_mounted_hive()
    if hive:
        mount_point = hive[: hive.index("/Windows/")]
        info(f"Found: {mount_point} (already mounted)")
        return hive, None

    info("Not found in any mounted partition — scanning for NTFS volumes...")
    devices = _ntfs_devices()
    if not devices:
        return None, None

    for device in devices:
        info(f"Trying {device} ...")
        if _try_mount(device, AUTO_MOUNT):
            candidate = os.path.join(AUTO_MOUNT, HIVE_RELATIVE)
            if os.path.exists(candidate):
                info(f"Mounted {device} at {AUTO_MOUNT}")
                return candidate, AUTO_MOUNT
            unmount(AUTO_MOUNT)
        else:
            info(f"{device} — could not mount (not Windows or permission denied)")

    return None, None


# ── Step 3: Read Windows Bluetooth keys ──────────────────────────────────────


def _active_controlset(reg):
    """Read Select\\Current to find which ControlSet Windows was last booted from."""
    try:
        val = reg.open("Select").value("Current").value()
        return f"ControlSet{val:03d}"
    except Exception:
        return None


def get_windows_keys(hive_path):
    """
    Return {adapter_mac_no_colons: {device_mac_no_colons: key_hex_upper}}.
    Reads the active ControlSet first, falls back to 001/002/003.
    """
    from Registry import Registry  # type: ignore[import]

    reg = Registry.Registry(hive_path)

    active = _active_controlset(reg)
    candidates = [active] if active else []
    for cs in ("ControlSet001", "ControlSet002", "ControlSet003"):
        if cs not in candidates:
            candidates.append(cs)

    for cs in candidates:
        try:
            root = reg.open(f"{cs}\\Services\\BTHPORT\\Parameters\\Keys")
        except Exception:
            continue

        keys = {}
        for adapter in root.subkeys():
            adapter_mac = adapter.name().lower()
            keys[adapter_mac] = {}

            # Classic BR/EDR layout: 16-byte value directly under the adapter key,
            # value name is the device MAC.
            for val in adapter.values():
                raw = val.value()
                if isinstance(raw, bytes) and len(raw) == 16:
                    keys[adapter_mac][val.name().lower()] = raw.hex().upper()

            # Alternate layout: device is a nested subkey.
            # Only fills in devices not already found above.
            for device in adapter.subkeys():
                device_mac = device.name().lower()
                if device_mac in keys[adapter_mac]:
                    continue
                for val in device.values():
                    raw = val.value()
                    if isinstance(raw, bytes) and len(raw) == 16:
                        keys[adapter_mac][device_mac] = raw.hex().upper()

        if keys:
            info(f"Using {cs}")
            total = sum(len(v) for v in keys.values())
            info(f"{total} device key(s) found in Windows registry")
            return keys

    return {}


# ── Step 4: Sync keys to Linux ───────────────────────────────────────────────


def get_linux_devices():
    """
    Return {adapter_mac_no_colons: {device_mac_no_colons: info_path}}.
    Reads BlueZ pairing records from /var/lib/bluetooth.
    """
    bt_root = "/var/lib/bluetooth"
    devices = {}
    for adapter_dir in glob.glob(f"{bt_root}/??:??:??:??:??:??"):
        adapter_mac = os.path.basename(adapter_dir).lower().replace(":", "")
        devices[adapter_mac] = {}
        for device_dir in glob.glob(f"{adapter_dir}/??:??:??:??:??:??"):
            device_mac = os.path.basename(device_dir).lower().replace(":", "")
            info_path = os.path.join(device_dir, "info")
            if os.path.exists(info_path):
                devices[adapter_mac][device_mac] = info_path
    return devices


def sync_key(info_path, new_key):
    """
    Replace the Key= value inside [LinkKey].
    Returns (old_key_or_None, status) where status is one of:
      'updated', 'already_current', 'no_linkkey'
    """
    with open(info_path) as f:
        content = f.read()

    # Allow optional whitespace between section header and Key= line
    match = re.search(r"\[LinkKey\]\s*\nKey=([0-9A-Fa-f]+)", content)
    if not match:
        return None, "no_linkkey"

    old_key = match.group(1)
    if old_key.upper() == new_key.upper():
        return old_key, "already_current"

    updated = content.replace(f"Key={old_key}", f"Key={new_key}", 1)
    with open(info_path, "w") as f:
        f.write(updated)
    return old_key, "updated"


def read_device_name(info_path):
    with open(info_path) as f:
        m = re.search(r"^Name=(.+)", f.read(), re.MULTILINE)
    return m.group(1).strip() if m else "Unknown"


def fmt_mac(mac_no_colons):
    return ":".join(mac_no_colons[i : i + 2] for i in range(0, 12, 2)).upper()


# ── Bluetooth service restart ────────────────────────────────────────────────


def restart_bluetooth():
    if _cmd_exists("systemctl"):
        subprocess.run(["systemctl", "restart", "bluetooth"], check=True)
    elif _cmd_exists("service"):
        subprocess.run(["service", "bluetooth", "restart"], check=True)
    else:
        print("\n  Could not restart Bluetooth automatically.")
        print("  Run manually:  sudo systemctl restart bluetooth")
        return
    info("Bluetooth service restarted")


def _cmd_exists(name):
    return subprocess.run(["which", name], capture_output=True).returncode == 0


# ── Main ─────────────────────────────────────────────────────────────────────


def main():
    header()

    if os.geteuid() != 0:
        cmd = sys.argv[0]
        if cmd.endswith(".py"):
            hint = f"Run:  sudo python3 {cmd}"
        else:
            hint = 'Run:  sudo env "PATH=$PATH" bluewin'
        die("Must run as root.", hint)

    # ── 1/4 Dependencies
    step(1, 4, "Checking dependencies")
    ensure_registry()

    # ── 2/4 Windows partition
    step(2, 4, "Finding Windows partition")
    hive, auto_mount = find_system_hive()
    if not hive:
        die(
            "Windows partition not found or could not be mounted.",
            "Make sure your Windows partition is accessible.",
            "Manual mount:  sudo mount -o ro /dev/sdXY /mnt/windows",
            "Then re-run this script.",
        )

    # ── 3/4 Windows BT keys
    step(3, 4, "Reading Bluetooth keys from Windows registry")
    win_keys = get_windows_keys(hive)
    if not win_keys:
        die(
            "No Bluetooth keys found in Windows registry.",
            "Pair your device in Windows (Settings → Bluetooth → Add device),",
            "then re-run this script.",
        )

    # ── 4/4 Sync
    step(4, 4, "Syncing keys to Linux")
    linux_devices = get_linux_devices()

    updated = 0
    current = 0
    skipped = []

    for adapter_mac, win_devices in win_keys.items():
        linux_adapter = linux_devices.get(adapter_mac)
        if linux_adapter is None:
            continue  # This Windows adapter isn't on this machine — skip silently

        for device_mac, new_key in win_devices.items():
            mac_label = fmt_mac(device_mac)

            if device_mac not in linux_adapter:
                skipped.append(mac_label)
                continue

            info_path = linux_adapter[device_mac]
            name = read_device_name(info_path)
            _, status = sync_key(info_path, new_key)

            if status == "updated":
                print(f"  {mac_label}  {name}  →  updated")
                updated += 1
            elif status == "already_current":
                print(f"  {mac_label}  {name}  →  already up to date")
                current += 1
            elif status == "no_linkkey":
                print(f"  {mac_label}  {name}  →  skipped (BLE device — classic key not found)")

    for mac_label in skipped:
        print(f"  {mac_label}  →  not paired on Linux yet")
        print("             Pair this device on Linux first, then re-run.")

    # ── Summary
    print()
    if updated > 0:
        restart_bluetooth()
        print(f"\n  {updated} key(s) synced. Turn your devices on — they should connect.")
    elif current > 0 and updated == 0:
        print("  All keys already match. Nothing to do.")
    else:
        print("  No matching devices found between Windows and Linux.")
        if skipped:
            print("  Pair the listed device(s) on Linux, then re-run.")

    if auto_mount:
        unmount(auto_mount)
        info(f"Unmounted {auto_mount}")


if __name__ == "__main__":
    main()
