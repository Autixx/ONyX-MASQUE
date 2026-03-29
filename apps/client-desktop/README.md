# ONyX Desktop Client

PyQt6 desktop client for ONyX with a daemon-backed `LuST` runtime.

## Current Scope

- login / logout
- registration request submit
- local session persistence
- local X25519 device key generation
- device registration
- device challenge / verify
- encrypted bundle issue + local decrypt
- daemon-backed LuST runtime connect / disconnect using bundled `lust-client.exe`
- Windows system tunnel via `Wintun + tun2socks` over the LuST transport
- first-run splash screen
- system tray lifecycle
- interactive background startup task for Windows user sessions
- Windows runtime-service skeleton for future privileged daemon split

## Not Implemented Yet

- host DNS enforcement hardening
- hardened secret vault
- production support-ticket submit flow

## Files

- `onyx_client.py` - main PyQt6 client
- `onyx_splash.py` - first-run splash screen
- `onyx_daemon_service.py` - Windows privileged daemon skeleton
- `onyx_runtime_selftest.py` - runtime readiness self-test
- `runtime/` - named-pipe, service, and transport adapter layer
- `lust_client.py` - bundled LuST helper process built into `lust-client.exe`
- `bin/` - bundled LuST runtime layout
- `assets/icons/onyx.ico` - Windows application icon
- `assets/icons/onyx_*.png` - multi-resolution icon set

## Install Dependencies

```bash
python -m pip install -r requirements.txt
```

For the Windows daemon skeleton you will also need:

```bash
python -m pip install pywin32
```

## Run

Normal launch:

```bash
python onyx_client.py
```

Start hidden in the tray:

```bash
python onyx_client.py --background
```

Run runtime self-test:

```bash
python onyx_runtime_selftest.py
```

Skip daemon spawn and only validate files / dependencies:

```bash
python onyx_runtime_selftest.py --skip-daemon
```

Build the standalone LuST helper manually:

```bash
python -m PyInstaller --noconfirm LustClient.spec
```

## Runtime Notes

- the client chooses the first usable issued LuST runtime profile from the bundle
- the helper validates the JSON profile, performs an HTTP/2 + TLS probe, opens a LuST session, and then either exposes an internal SOCKS5 uplink or drives `Wintun + tun2socks`
- if the bundle contains no usable LuST profile, connect fails with a runtime error instead of faking success
- `Settings` shows runtime readiness, resolved tool paths, bundle profile summary, and DNS runtime state

## LuST Profile Contract

The desktop daemon expects `lust` runtime profiles to carry JSON like this:

```json
{
  "type": "lust",
  "protocol": "lust-h2",
  "version": 1,
  "endpoint": {
    "scheme": "https",
    "host": "edge.example.com",
    "port": 443,
    "server_name": "edge.example.com",
    "path": "/lust",
    "http_version": "2"
  },
  "session": {
    "protocol": "lust-h2",
    "stream_path": "/lust/stream",
    "heartbeat_seconds": 15,
    "connect_timeout_seconds": 10
  },
  "authentication": {
    "scheme": "bearer",
    "token": "example"
  },
  "client": {
    "peer_id": "peer-id",
    "username": "alice"
  },
  "dns": {
    "resolver": "1.1.1.1"
  },
  "tunnel": {
    "mode": "wintun",
    "interface_name": "wintun",
    "address_v4": "198.18.0.1",
    "netmask_v4": "255.255.0.0",
    "gateway_v4": "198.18.0.1",
    "mtu": 1380,
    "dns_servers": [
      "1.1.1.1"
    ]
  }
}
```

Notes:

- the daemon writes the issued config to `~/.onyx-client/runtime/<tunnel>.json`
- `lust-client.exe` reads that file, validates it, probes the base endpoint, and then opens the LuST frame session on the configured edge node
- the helper writes state to `~/.onyx-client/runtime/lust-client-status.json`
- the panel does not carry user traffic; the runtime connects to a separate LuST edge node on `/lust*`
- `apps/client-desktop/bin/tun2socks.exe` and `apps/client-desktop/bin/wintun.dll` must be present for Windows Wintun mode
- without those binaries the helper can still run in `proxy` mode, but the default issued profile now targets `wintun`

## Windows Background Startup

This client is intentionally installed as an interactive startup task, not as a true Windows service.

Reason:

- a real Windows service is the wrong model for a GUI tray application
- tray icons and interactive windows must run in the user session

Install startup task for the current user:

```bash
python onyx_client.py --install-startup
```

Alias kept for operator convenience:

```bash
python onyx_client.py --install-service
```

Remove startup task:

```bash
python onyx_client.py --uninstall-startup
```

Alias:

```bash
python onyx_client.py --uninstall-service
```

## Windows Runtime Daemon Skeleton

Run the privileged daemon skeleton in console mode:

```bash
python onyx_daemon_service.py --console
```

Install / remove the Windows service skeleton:

```bash
python onyx_daemon_service.py install
python onyx_daemon_service.py remove
```
