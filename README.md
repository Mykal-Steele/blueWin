<pre>
 /$$       /$$                     /$$      /$$ /$$
| $$      | $$                    | $$  /$ | $$|__/
| $$$$$$$ | $$ /$$   /$$  /$$$$$$ | $$ /$$$| $$ /$$ /$$$$$$$
| $$__  $$| $$| $$  | $$ /$$__  $$| $$/$$ $$ $$| $$| $$__  $$
| $$  \ $$| $$| $$  | $$| $$$$$$$$| $$$$_  $$$$| $$| $$  \ $$
| $$  | $$| $$| $$  | $$| $$_____/| $$$/ \  $$$| $$| $$  | $$
| $$$$$$$/| $$|  $$$$$$/|  $$$$$$$| $$/   \  $$| $$| $$  | $$
|_______/ |__/ \______/  \_______/|__/     \__/|__/|__/  |__/
</pre>

# blueWin

[![CI](https://github.com/Mykal-Steele/blueWin/actions/workflows/ci.yml/badge.svg)](https://github.com/Mykal-Steele/blueWin/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Platform: Linux](https://img.shields.io/badge/platform-Linux-lightgrey)](https://kernel.org/)

Fixes the Bluetooth dual-boot problem. Pair a device in Windows, it stops working in Linux because Windows overwrites the link key on the device. This script reads the new key straight from the Windows registry and updates Linux to match. No re-pairing needed.

---

## How it works

Bluetooth pairing stores a shared link key on both the host and the device. On a dual-boot machine, pairing in Windows writes a new key to the device while Linux still has the old one, so the device won't connect.

blueWin reads the Windows registry offline (Windows doesn't need to be running) and updates the BlueZ pairing record on Linux:

```
Windows: HKLM\SYSTEM\ControlSet001\Services\BTHPORT\Parameters\Keys\<adapter_mac>\<device_mac>
  Linux: /var/lib/bluetooth/<adapter_mac>/<device_mac>/info  ->  [LinkKey] Key=...
```

Registry parsing uses [python-registry](https://github.com/williballenthin/python-registry), which gets installed automatically on first run if you don't have it.

---

## Installation

### Clone and run (simplest)

```bash
git clone https://github.com/Mykal-Steele/blueWin.git
cd blueWin
sudo python3 bt_sync.py
```

### pipx

Install pipx if you don't have it:

```bash
sudo pacman -S python-pipx   # Arch
sudo apt install pipx        # Ubuntu/Debian
sudo dnf install pipx        # Fedora
```

Then:

```bash
pipx install git+https://github.com/Mykal-Steele/blueWin.git
sudo env "PATH=$PATH" bluewin
```

---

## Usage

```bash
sudo python3 bt_sync.py           # clone and run
sudo env "PATH=$PATH" bluewin     # pipx install
```

### First time with a new device

1. **Pair on Linux first** so BlueZ has a record for the device
2. **Pair on Windows** (Settings -> Bluetooth -> Add device)
3. **Run blueWin** from Linux

After that, just re-run blueWin any time you pair on Windows again.

### If auto-detection fails

Mount your Windows partition manually and re-run:

```bash
sudo mount -o ro /dev/sdXY /mnt/windows
sudo python3 bt_sync.py
```

---

## Example output

```
blueWin -- Bluetooth dual-boot key sync
----------------------------------------

[1/4] Checking dependencies
      python-registry ready

[2/4] Finding Windows partition
      Found: /run/media/user/Windows (already mounted)

[3/4] Reading Bluetooth keys from Windows registry
      Using ControlSet001
      2 device key(s) found in Windows registry

[4/4] Syncing keys to Linux

  63:A1:FF:58:4C:6B  EW72               ->  updated
  A0:5A:5F:08:E5:E9  Wireless Controller ->  already up to date

      Bluetooth service restarted

  1 key(s) synced. Turn your devices on -- they should connect.
```

---

## Requirements

| Requirement | Notes |
|---|---|
| Linux with [BlueZ](http://www.bluez.org/) | Standard on all major distros |
| Python 3.9+ | Pre-installed on most distros |
| Root (`sudo`) | Needed to read BlueZ records and mount partitions |
| Windows partition accessible | Script will auto-mount NTFS volumes if needed |

**Disable Windows Fast Startup** or the registry on disk will be stale:

> Control Panel -> Power Options -> "Choose what the power buttons do" -> uncheck **Turn on fast startup**

---

## Distro compatibility

| Distro | Mount path auto-detected |
|---|---|
| Arch / Manjaro | `/run/media/<user>/<label>` |
| Ubuntu / Mint | `/media/<user>/<label>` |
| Fedora | `/run/media/<user>/<label>` |
| Debian | `/media/<user>/<label>` |
| Any (manual mount) | `/mnt/<label>` or `/mnt` |

---

## Troubleshooting

**"Device not paired on Linux yet"**  
Pair the device on Linux first (Bluetooth settings -> Add device), then re-run.

**"Windows partition not found"**  
Open your Windows partition in the file manager to trigger auto-mount, or mount it manually (see above).

**"No Bluetooth keys found in Windows registry"**  
You connected but didn't fully pair. In Windows Bluetooth settings, remove the device and add it again.

**Device still won't connect after sync**  
Fast Startup is probably still on. Disable it in Windows, shut down properly, then re-run.

---

## Development

```bash
git clone https://github.com/Mykal-Steele/blueWin.git
cd blueWin
pip install -e ".[dev]"
make check    # lint + format check
make format   # auto-format
```

---

## Contributing

Issues and PRs are welcome. For bigger changes, open an issue first.

---

## License

MIT - see [LICENSE](LICENSE).
