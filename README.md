# Resolve Freesound Browser

Resolve Freesound Browser is a small desktop sound browser for DaVinci Resolve
workflows. It searches Freesound and Openverse sources, previews sounds, shows
waveforms and metadata, trims preview ranges, and lets you drag or import the
resulting audio into Resolve.

The app is intentionally standalone. DaVinci Resolve does not expose a public
Linux API for a true docked panel, so this tool runs next to Resolve and uses
normal file drag/drop plus optional Resolve scripting import.

## Features

- Unified Freesound, Jamendo, and Wikimedia Commons search
- Freesound APIv2 search through `https://freesound.org/apiv2/search/`
- Freesound fallback through Openverse when no Freesound API key is configured
- API-key authentication for search, preview access, waveform images, and metadata
- Sort modes: relevance, rating, most downloaded, newest, duration
- Source, license, category, usage, and length filters
- Optional filter to hide language files whose name starts with `LL`
- Infinite scroll / automatic result loading
- Modern dark UI with result waveforms and rating stars
- Preview playback with play/pause, next, volume, click-to-seek, and playhead
- Large waveform with draggable In/Out handles
- Trimmed download, drag, and Resolve import using `ffmpeg`
- Drag from the waveform or result list into Resolve / Media Pool / file manager
- Optional import into the active Resolve Media Pool through Resolve scripting
- Library tab with recently-used sounds and named collections
- Rotating debug log for troubleshooting
- Configurable cache cleanup by age and maximum size

## Linux Install

Recommended install/update command. It downloads the latest GitHub release into
`~/Apps/ResolveFreesoundBrowser`, installs Python dependencies, registers the
desktop launcher, and installs the Resolve script menu entry:

```bash
curl -fsSL https://raw.githubusercontent.com/RayDurlok/soundbrowser/main/install_latest_linux.sh | bash
```

Manual install from an already downloaded project folder:

```bash
cd ~/Apps/ResolveFreesoundBrowser
python3 -m pip install --user -r requirements.txt
./install_linux_user.sh
```

The installer creates:

- `~/.local/bin/resolve-freesound-browser`
- Desktop launcher: `Resolve Freesound Browser`
- Resolve menu launcher: `Workspace -> Scripts -> Edit -> Resolve Freesound Browser`

Run from the terminal:

```bash
resolve-freesound-browser
```

Or directly:

```bash
cd ~/Apps/ResolveFreesoundBrowser
python3 run.py
```

### ffmpeg

`ffmpeg` is required for trimmed In/Out exports, drag files, and imports. The app
will offer a best-effort install if `ffmpeg` is missing.

Manual Fedora install:

```bash
sudo dnf install ffmpeg-free
```

Depending on enabled repositories/codecs, you may prefer your normal full ffmpeg
package source.

## Linux Update

Run the same latest-release installer again:

```bash
curl -fsSL https://raw.githubusercontent.com/RayDurlok/soundbrowser/main/install_latest_linux.sh | bash
```

If this folder is a Git checkout and you prefer manual control:

```bash
cd ~/Apps/ResolveFreesoundBrowser
latest_tag=$(curl -fsSL https://api.github.com/repos/RayDurlok/soundbrowser/releases/latest | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])')
git fetch --tags --prune origin
git checkout --detach "$latest_tag"
python3 -m pip install --user -r requirements.txt
./install_linux_user.sh
```

## macOS Install

Recommended install/update command. It downloads the latest GitHub release into
`~/Apps/ResolveFreesoundBrowser`, creates/updates the local virtual environment,
creates a normal app in `~/Applications`, installs the Resolve menu launcher,
and installs all required Homebrew dependencies. If Homebrew is missing, its
official installer is started first:

```bash
curl -fsSL https://raw.githubusercontent.com/RayDurlok/soundbrowser/main/install_latest_macos.sh | bash
```

The installer creates:

- `~/Applications/Resolve Freesound Browser.app`
- `~/.local/bin/resolve-freesound-browser`
- `~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/Resolve Freesound Browser.py`

Open the app from Finder, Spotlight, or Launchpad. Inside Resolve it appears at:

```text
Workspace -> Scripts -> Edit -> Resolve Freesound Browser
```

If Resolve was open during installation, restart it once so it discovers the
new Scripts menu entry.

Manual install from an already downloaded project folder:

```bash
brew install python ffmpeg
cd ~/Apps/ResolveFreesoundBrowser
"$(brew --prefix python)/bin/python3" -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade -r requirements.txt
./install_macos_user.sh
```

If Homebrew itself is not installed, use its official installation command:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Resolve import on macOS requires Resolve scripting to be enabled:

```text
Preferences -> System -> General -> External scripting using: Local
```

The app uses DaVinci Resolve's standard macOS scripting paths:

```text
/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting
/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so
```

## macOS Update

Run the same installer again. It updates the venv, `.app`, and Resolve launcher.
Local changes inside the app checkout are saved to a named Git stash before the
release is switched, and the installer prints the command to restore them:

```bash
curl -fsSL https://raw.githubusercontent.com/RayDurlok/soundbrowser/main/install_latest_macos.sh | bash
```

If this folder is a Git checkout and you prefer manual control:

```bash
cd ~/Apps/ResolveFreesoundBrowser
latest_tag=$(curl -fsSL https://api.github.com/repos/RayDurlok/soundbrowser/releases/latest | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])')
git stash push --include-untracked -m "before-manual-update"
git fetch --tags --prune origin
git checkout --detach "$latest_tag"
"$(brew --prefix python)/bin/python3" -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade -r requirements.txt
./install_macos_user.sh
```

## macOS Uninstall

Remove the `.app`, command launcher, and Resolve Scripts menu entry:

```bash
cd ~/Apps/ResolveFreesoundBrowser
./uninstall_macos_user.sh
```

The repository checkout, settings, downloads, and cache are intentionally kept.

## Windows Run

Install Python 3 and then, from the project folder:

```powershell
python -m pip install -r requirements.txt
python run.py
```

Or double-click:

```text
run_windows.bat
```

Resolve import on Windows requires Resolve scripting to be enabled and the
standard Resolve scripting module to be installed by DaVinci Resolve.

## Freesound API Key

Create an API credential at:

```text
https://freesound.org/apiv2/apply/
```

Suggested fields:

- `Name`: `Resolve Freesound Browser`
- `URL`: `http://localhost`
- `Callback URL`: `http://freesound.org/home/app_permissions/permission_granted/`
- `Description`: `Desktop tool for searching Freesound previews and using them in DaVinci Resolve.`

After creating the credential, copy the value from:

```text
Client secret / Api key
```

Then open the app and set it via:

```text
Gear button -> API key
```

You can also provide it for one run:

```bash
FREESOUND_API_KEY=your_key python3 run.py
```

## Resolve Workflow

Recommended workflow:

1. Search for a sound.
2. Audition with `Play`.
3. Adjust In/Out handles on the large waveform if needed.
4. Drag from the waveform or result row into Resolve.

Dragging into the Media Pool is usually reliable. Dragging directly to the
timeline depends on the current Resolve page, focused panel, track targeting,
timeline state, and the exact drop position. If timeline drop behaves
inconsistently, drag into the Media Pool first and then place the clip from
there.

The `Import` button uses Resolve scripting and imports the prepared preview/trim
file into the active project's Media Pool.

Enable Resolve scripting:

```text
Preferences -> System -> General -> External scripting using: Local
```

## Data Locations

Linux:

- Config: `~/.config/resolve-freesound-browser/config.json`
- Library/history: `~/.config/resolve-freesound-browser/history.json` and `collections.json`
- Cache: `~/.cache/resolve-freesound-browser/`
- Logs: `~/.cache/resolve-freesound-browser/logs/app.log`

Windows:

- Config: `%APPDATA%\Resolve Freesound Browser\config.json`
- Cache/logs: `%LOCALAPPDATA%\Resolve Freesound Browser\Cache\`

macOS:

- Config: `~/Library/Application Support/Resolve Freesound Browser/config.json`
- Library/history: `~/Library/Application Support/Resolve Freesound Browser/history.json` and `collections.json`
- Cache/logs: `~/Library/Caches/Resolve Freesound Browser/`

Cache cleanup is configured in:

```text
Gear button -> Cache…
```

It applies to cached previews, waveforms, and trimmed drag/import files. The
download folder is not cleaned automatically.

## Logging

The app writes a rotating debug log to:

```text
~/.cache/resolve-freesound-browser/logs/app.log
```

The log includes search requests, Freesound downloads, trim commands, Resolve
import attempts, and tracebacks. API keys are not logged.

For verbose console output:

```bash
FREESOUND_LOG_LEVEL=DEBUG python3 run.py
```

## Current Limitations

- Freesound original-quality downloads require OAuth2 and are not implemented yet.
- The app uses Freesound preview files for drag/download/import.
- Direct timeline drag in Resolve can be inconsistent; Media Pool drag is more reliable.
- A true docked Resolve panel is not available through Resolve's public Linux APIs.
