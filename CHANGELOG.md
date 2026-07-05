# Changelog

All notable changes from this point forward will be tracked here.

## Unreleased

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
