# blueWin

Sync Bluetooth pairing keys from Windows to Linux on dual-boot machines.

When you pair a Bluetooth device in Windows, Windows writes a new key to the device.
Linux still has the old key and the connection fails. This script reads the key Windows
wrote and updates Linux to match — no re-pairing needed.

---

## How it works

Bluetooth pairing creates a shared secret (link key) stored on both the host and the
device. On a dual-boot machine, pairing in Windows overwrites the key on the device.
Linux's copy becomes stale and the device refuses to connect.

`bt-sync` reads the key directly out of the Windows registry (offline — Windows does
not need to be running) and writes it into BlueZ's pairing record on Linux.

---

## Requirements

- Linux with [BlueZ](http://www.bluez.org/) (standard on all major distros)
- Python 3.6+
- Root access (`sudo`)
- Windows partition accessible (the script will auto-mount it if needed)

> **Disable Windows Fast Startup** or the registry on disk may be stale:
> Control Panel → Power Options → "Choose what the power buttons do"
> → uncheck **Turn on fast startup**

---

## Usage

```bash
sudo python3 bt-sync.py
```

That's it. The script auto-detects your Windows partition and your paired devices.

### First time with a new device

You need to pair the device on **Linux first** (once only). This creates BlueZ's
pairing record which the script updates. After that:

1. Re-pair on Windows whenever you like
2. Boot into Linux and run `sudo python3 bt-sync.py`
3. The device connects — no re-pairing on Linux needed

---

## Example output

```
bt-sync — Bluetooth dual-boot key sync
────────────────────────────────────────

[1/4] Checking dependencies
      python-registry ready

[2/4] Finding Windows partition
      Found: /run/media/user/Windows (already mounted)

[3/4] Reading Bluetooth keys from Windows registry
      Using ControlSet001
      2 device(s) found in Windows registry

[4/4] Syncing keys to Linux

  63:A1:FF:58:4C:6B  EW72               →  updated
  A0:5A:5F:08:E5:E9  Wireless Controller →  already up to date

      Bluetooth service restarted

  1 key(s) synced. Turn your devices on — they should connect.
```

---

## Supported distros

| Distro | Mount path detected | Tested |
|---|---|---|
| Arch / Manjaro | `/run/media/<user>/<label>` | Yes |
| Ubuntu / Mint | `/media/<user>/<label>` | Yes |
| Fedora | `/run/media/<user>/<label>` | Yes |
| Debian | `/media/<user>/<label>` | Yes |
| Any (manual mount) | `/mnt/<label>` or `/mnt` | Yes |

If your Windows partition is not auto-detected, mount it manually first:

```bash
sudo mount -o ro /dev/sdXY /mnt/windows
sudo python3 bt-sync.py
```

---

## Troubleshooting

**Device shows "not paired on Linux yet"**
Pair the device on Linux first (Settings → Bluetooth → Add device), then re-run.

**"Windows partition not found"**
Open your Windows partition in the file manager to trigger auto-mount, then re-run.
Or mount it manually (see above).

**"No Bluetooth keys found in Windows registry"**
You connected but didn't pair. Open Windows Bluetooth settings, remove the device,
and add it again (full pairing, not just connect).

**Device still won't connect after sync**
Make sure Fast Startup is disabled in Windows — see Requirements above.

---

## How the key sync works (technical)

Windows stores Bluetooth link keys in the registry at:

```
HKLM\SYSTEM\ControlSet001\Services\BTHPORT\Parameters\Keys\<adapter_mac>\<device_mac>
```

Linux (BlueZ) stores them in:

```
/var/lib/bluetooth/<adapter_mac>/<device_mac>/info  →  [LinkKey] Key=...
```

The script reads the Windows hive offline using
[python-registry](https://github.com/williballenthin/python-registry),
finds the matching BlueZ record by MAC address, and replaces the `Key=` value.
python-registry is installed automatically into a temporary venv on first run.

---

## License

MIT
