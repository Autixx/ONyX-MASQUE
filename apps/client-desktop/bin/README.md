Bundled runtime layout for the ONyX LuST Windows client.

Expected files:

- `lust-client.exe` - ONyX managed LuST runtime helper launched by the local daemon
- `tun2socks.exe` - Windows tunnel userspace bridge used to expose LuST as a system adapter
- `wintun.dll` - WireGuard Wintun driver runtime loaded by `tun2socks.exe`

Notes:

- this binary is built from `apps/client-desktop/lust_client.py`
- `build.ps1` and `build-portable.ps1` generate it through `LustClient.spec`
- when `tun2socks.exe` and `wintun.dll` are present, the helper brings up a Windows Wintun adapter and routes traffic into the LuST session
- if the profile is switched to `tunnel.mode=proxy`, the helper can stay in local SOCKS5 mode without the Wintun runtime
