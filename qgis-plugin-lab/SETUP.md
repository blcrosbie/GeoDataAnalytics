# Setup

Do this once per machine. It gets you a QGIS install that can browse the
Earth Engine catalog, authenticate against your own Earth Engine account, and
load `ee_s5p_plugin` from the sibling repo checkout so edits there are live.

## 1. Install QGIS

Any 3.22+ build works; the plugin is tested on 3.22, 3.40, 3.44 LTR and 4.2
across both Qt 5 and Qt 6. If you don't already have a preference, install
the **LTR** release from [qgis.org](https://qgis.org/download/) — it's what
most production QGIS shops run, so it's the most representative environment
to learn in.

## 2. Install the Google Earth Engine plugin

`ee_s5p_plugin` only browses the catalog on its own. Extracting data needs
the separate **Google Earth Engine** plugin, which supplies the `ee` Python
API and authentication:

*Plugins → Manage and Install Plugins… → search "Google Earth Engine" → Install.*

You'll need a Google account [registered for Earth Engine][register] and a
Cloud project — the plugin's sign-in flow walks you through both the first
time it runs.

[register]: https://code.earthengine.google.com/register

If sign-in fails outright (the EE plugin fails inside its own load step, so
its own sign-in command becomes unreachable), authenticate from the QGIS
Python Console instead:

```python
import ee
ee.Authenticate()
```

then restart QGIS. See the plugin README's "If Earth Engine will not sign
in" section for the full failure mode — `ee.Authenticate()` rewrites your
credentials file from scratch, so expect to be asked for your Cloud project
again afterward.

## 3. Symlink `ee_s5p_plugin` for development

This lab assumes `ee_s5p_plugin` is checked out as a sibling of this repo:

```
dev/blcrosbie/
├── GeoDataAnalytics/      (this repo)
└── ee_s5p_plugin/
    └── ee_s5p_plugin/     (the actual plugin package — symlink THIS folder)
```

Find your QGIS profile folder from inside QGIS:
*Settings → User Profiles → Open Active Profile Folder*, then its
`python/plugins` subfolder. Symlink the plugin package into it:

```powershell
# Windows, in an elevated PowerShell
New-Item -ItemType SymbolicLink `
  -Path "$env:APPDATA\QGIS\QGIS3\profiles\default\python\plugins\ee_s5p_plugin" `
  -Target "$PWD\..\ee_s5p_plugin\ee_s5p_plugin"
```

```bash
# Linux
PROFILE=~/.local/share/QGIS/QGIS3/profiles/default
ln -s "$(pwd)/../ee_s5p_plugin/ee_s5p_plugin" "$PROFILE/python/plugins/ee_s5p_plugin"

# macOS
PROFILE=~/"Library/Application Support/QGIS/QGIS3/profiles/default"
ln -s "$(pwd)/../ee_s5p_plugin/ee_s5p_plugin" "$PROFILE/python/plugins/ee_s5p_plugin"
```

Adjust the relative path if your checkout isn't laid out as above — what
matters is that the target is the *inner* `ee_s5p_plugin/` (the one holding
`metadata.txt`), not the repo root.

Then enable it: *Plugins → Manage and Install Plugins… → Installed → tick
"Earth Engine Catalog Query."*

When the plugin repo changes, reload it in place with
[Plugin Reloader][reloader] instead of restarting QGIS.

[reloader]: https://plugins.qgis.org/plugins/plugin_reloader/

## 4. Optional: install `h3` for real hex indexes

Without it, large-area extracts still auto-tile, but with a lat/lon grid
instead of true H3 cells. On OSGeo4W (Windows):

```
C:\OSGeo4W\bin\python-qgis-ltr.bat -m pip install h3
```

On Linux/macOS, use whatever Python QGIS itself runs on (check
*Plugins → Python Console* → `import sys; sys.executable`).

## 5. Verify the install

1. Click the toolbar icon (or *Plugins → Earth Engine Catalog*) to open the
   dock.
2. Collection dropdown → **Sentinel-5P / TROPOMI**. The result list should
   populate without needing Earth Engine sign-in — catalog browsing works
   offline.
3. Double-click any dataset → **Details…** should show bands, units and a
   suggested colour palette.
4. Draw a small AOI, pick a native resolution, and press **Extract…**. If it
   complains about Earth Engine specifically (not about the AOI or
   resolution), that's step 2's authentication, not this plugin — go back
   and fix sign-in before starting a scenario.

## Where lab work lives

Keep QGIS project files, exported layers and write-ups for a scenario under
`results/<scenario-slug>/` in **this** repo, not in your QGIS profile or the
plugin repo. See the top-level [`README.md`](README.md) for why that
directory is gitignored.
