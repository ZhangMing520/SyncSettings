# Submitting "Sync Settings Reborn" to Package Control

The original `SyncSettings` package is no longer maintained
(https://github.com/mfuentesg/SyncSettings). This fork revives it under a new
name so it can be listed independently on Package Control without colliding
with the dead package.

## How Package Control distribution works

You do **not** upload a zip. You register your **Git repository** in the
official channel repository. Package Control then pulls releases from your tags.

## Step 1 — Make sure your repo is ready

- This repo must be public on GitHub.
- It should have a Git **tag** for the release you want to publish
  (e.g. `v4.0.0`). Package Control reads tags.
- The `details` URL below must point to **your** repository.

If you want to rename the GitHub repo to `SyncSettingsReborn`, do it before
step 2 and update the `details` URL accordingly.

## Step 2 — Submit to `package_control_channel`

Two options:

**Option A — web form (easiest)**
Open https://packagecontrol.io/submit and enter your repository URL:

```
https://github.com/ZhangMing520/SyncSettings
```

**Option B — pull request (recommended, fully controlled)**

1. Fork https://github.com/wbond/package_control_channel
2. Add a file `packages/S/Sync%20Settings%20Reborn.json` (the folder is the
   first letter of the package name) with this content:

```json
{
    "name": "Sync Settings Reborn",
    "details": "https://github.com/ZhangMing520/SyncSettings",
    "releases": [
        {
            "sublime_text": "*",
            "tags": true
        }
    ]
}
```

3. Open a PR against `wbond/package_control_channel`.

## Result

Once merged, users can install it via:
`Command Palette → Package Control: Install Package → Sync Settings Reborn`.

Future updates: just push a new tag (e.g. `v4.0.1`) to your repo; Package
Control picks it up automatically. No need to re-submit.

## Notes

- The package install folder name is taken from the channel `name`
  ("Sync Settings Reborn"), so the installed path is
  `Packages/Sync Settings Reborn/`.
- Runtime dependencies (`requests` and its transitive deps) are declared in
  `dependencies.json` and installed automatically by Package Control.
- The settings file was renamed to `SyncSettingsReborn.sublime-settings` and
  old config is migrated automatically on first run.
