# Changelog

All notable changes from this point forward will be tracked here.

## Unreleased

## 0.3.2 - 2026-07-20

- Added keyboard shortcuts for the selected sound: Space toggles play/pause, I sets the In point, and O sets the Out point at the current cursor position.
- Added an `Exclude LL` result toggle to hide language files whose name starts with `LL`.
- Preview playback now starts immediately from the remote stream while the local cached drag/import file continues downloading in the background.
- Fixed the Python 3.9 startup crash caused by a runtime-only Python 3.10 union type.
- Added a complete macOS installer with Homebrew dependencies, a user `.app`, a command launcher, and the Resolve Scripts menu entry.
- macOS updates now preserve local checkout changes in a named Git stash before switching releases.
- Added a macOS integration uninstaller and Python 3.9/3.13 compatibility checks.

## 0.3.1 - 2026-07-06

- Added a Cache settings dialog with age retention and maximum cache size limits.
- Added automatic cleanup for cached previews, waveform images, and trimmed drag/import files.

## 0.3.0 - 2026-07-06

- Merged Freesound and Openverse into one search. The "Quelle" selector (Freesound / Jamendo / Wikimedia Commons) now drives a single mixed result list instead of a top-level source toggle.
- Freesound results come from the native Freesound API again; when no Freesound API key is set, Freesound falls back to Openverse.
- Unified the license filter (Public Domain Mark / CC0 / CC BY) across all sources (mapped to Freesound's license filter); removed the separate CC0 checkbox. Kategorie/Nutzung apply to the Openverse sources and grey out when only Freesound is selected.
- Sorting is applied client-side across the merged results (Openverse has no server-side sort); rating/downloads only exist on Freesound, so those items fall to the end of those orders.
- Added a "Länge" filter with min/max seconds (server-side for Freesound, client-side for the merged list so it applies to Openverse too).

## 0.2.1 - 2026-07-06

- Added Linux and macOS latest-release installer/update scripts.
- Updated install and update documentation so both platforms automatically fetch the newest GitHub release.

## 0.2.0 - 2026-07-06

- Added Openverse as a second search source (Jamendo, Wikimedia Commons), selectable via a Source switcher; Freesound is excluded by default to avoid duplicates.
- Added Openverse filters matching the site: Quelle (sources), Audio-Kategorie, Nutzung (commercial enforced), and Lizenzen (Public Domain Mark, CC0, CC BY); all optional and persisted.
- Capped anonymous Openverse requests at page_size 20 (their limit) and added optional Openverse client ID/secret in settings for a bearer token that lifts the cap and rate limits.
- Rendered Openverse waveform peaks into Freesound-style waveform images so both sources look consistent.
- Showed the provider (Jamendo / Wikimedia / Freesound) as a tag on Openverse results and in the detail panel; added an explicit "Ohne Kategorie (alle)" option to the category filter.
- Replaced the app icon with the transparent logo (`resources/icon.png`).
- Made the settings button smaller and renamed its menu entry to "API key".
- Added a modern standalone PySide6 sound-browser interface.
- Added Freesound search with CC0 filtering, sort modes, infinite scroll, waveforms, and ratings.
- Added preview playback with volume, play/pause, next, waveform seeking, and playhead display.
- Added waveform In/Out handles with trimmed drag, download, and Resolve import via `ffmpeg`.
- Added drag support from result rows and the large waveform.
- Added optional Resolve Media Pool import through Resolve scripting.
- Added Library tab with recently-used history and named collections.
- Added rotating debug logging and crash logging.
- Added Linux user installer for command, desktop launcher, and Resolve menu launcher.

## 0.1.0 - 2026-07-05

- Initial local prototype of Resolve Freesound Browser.
