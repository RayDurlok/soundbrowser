# Resolve Freesound Browser

Resolve Freesound Browser is a small desktop sound browser for DaVinci Resolve
workflows. It searches Freesound, previews sounds, shows waveforms and metadata,
trims preview ranges, and lets you drag or import the resulting audio into
Resolve.

The app is intentionally standalone. DaVinci Resolve does not expose a public
Linux API for a true docked panel, so this tool runs next to Resolve and uses
normal file drag/drop plus optional Resolve scripting import.

## Features

- Freesound APIv2 search through `https://freesound.org/apiv2/search/`
- API-key authentication for search, preview access, waveform images, and metadata
- Sort modes: relevance, rating, most downloaded, newest, duration
- CC0-only filter
- Infinite scroll / automatic result loading
- Modern dark UI with result waveforms and rating stars
- Preview playback with play/pause, next, volume, click-to-seek, and playhead
- Large waveform with draggable In/Out handles
- Trimmed download, drag, and Resolve import using `ffmpeg`
- Drag from the waveform or result list into Resolve / Media Pool / file manager
- Optional import into the active Resolve Media Pool through Resolve scripting
- Library tab with recently-used sounds and named collections
- Rotating debug log for troubleshooting

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
File -> Settings -> API key
```

You can also provide it for one run:

```bash
FREESOUND_API_KEY=your_key python3 run.py
```

## Linux Install

From this folder:

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

If this folder is a Git checkout:

```bash
cd ~/Apps/ResolveFreesoundBrowser
git pull --ff-only
python3 -m pip install --user -r requirements.txt
./install_linux_user.sh
```

If you update by replacing the folder manually, run:

```bash
cd ~/Apps/ResolveFreesoundBrowser
python3 -m pip install --user -r requirements.txt
./install_linux_user.sh
```

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
