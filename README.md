# DLSSNR Manager for Decky Loader

A Decky sidebar for installing the **ReShade** DLSSNR route into a selected offline
Steam game running through Proton. It finds installed Steam libraries, lets the user
choose the actual Windows executable, copies a model-free runtime into that executable's
directory, and exposes the same basic performance/preprocess controls as NR Lab.

## Safety model

- The game must be closed before installation or removal.
- Every copied file is hashed and recorded in a manifest outside the game directory.
- Existing injection files are refused unless **Back up and replace** is explicitly enabled.
- Removal deletes only files whose hash still matches the install record; changed files are
  left alone. Recorded originals are restored when safe.
- The plugin never includes or fetches `nvngx_dlssnr.dll` or `dlssnr.bin`. The user selects a
  local, legitimately obtained DLL/zip and extraction occurs locally.
- This is for offline games without anti-cheat only.

## Use

1. Install a GitHub release zip through Decky Loader.
2. Open **DLSSNR Manager** in the Decky sidebar and select the installed Steam game and its real
   Windows game EXE (not a launcher/crash reporter).
3. Confirm that the game is offline and has no anti-cheat. Select your own local
   `nvngx_dlssnr.dll` (or a zip containing it), then install. The plugin blocks installation
   without this confirmation and never downloads/provides the file.
4. In Steam's launch options, set `WINEDLLOVERRIDES="dxgi=n,b" %command%`, then restart the game.
5. Change model resolution, passes, preprocess, and exposure in the sidebar. These changes take
   effect on the next launch.

## Comparison

The initial runtime offers its existing full-frame preprocess A/B toggle (`Ctrl+F10`). A true
50/50 before/after wipe needs compositor support in the injected add-on; it is intentionally not
pretended to be a sidebar-only feature. It is tracked as the next runtime enhancement.

The release workflow builds both x86 and x86_64 model-free runtimes from upstream and attaches a
Decky-compatible zip to every version tag.
