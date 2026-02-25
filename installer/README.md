# OHE Windows Installer

This folder contains the [Inno Setup 6](https://jrsoftware.org/isinfo.php) script that packages the OHE GUI into a single distributable Windows setup wizard.

## What the installer does

- Installs `ohe-gui.exe` and all dependencies under `Program Files\OHE Measurement System\`
- Creates a **Start Menu** shortcut
- Optionally creates a **Desktop** shortcut
- Optionally associates `.mp4` files with the OHE GUI
- Includes a clean **Uninstaller**
- **Does NOT require Python** on the end-user machine (everything is bundled)

## Prerequisites (developer machine only)

| Tool | Where to get it | Required? |
|---|---|---|
| Python 3.11+ | python.org | ✅ Yes |
| PyInstaller | `pip install pyinstaller` | ✅ Yes (auto-installed by script) |
| Inno Setup 6 | [jrsoftware.org/isinfo.php](https://jrsoftware.org/isinfo.php) | ✅ Yes |

## Build the installer (one command)

```powershell
# From the project root:
.\scripts\build_installer.ps1
```

This single script:
1. Runs all 76 tests (aborts if any fail)
2. Builds the PyInstaller bundle → `dist\ohe-gui\`
3. Compiles the Inno Setup script → `installer\Output\OHE_Setup_1.0.0.exe`

## Manual Inno Setup compilation (alternative)

```powershell
# After building with PyInstaller first:
iscc installer\ohe_setup.iss
```

Or open `ohe_setup.iss` in the **Inno Setup Compiler** IDE and press `Ctrl+F9`.

## Output

```
installer\
└── Output\
    └── OHE_Setup_1.0.0.exe   ← distribute this single file
```

## Customising

Edit `ohe_setup.iss` to change:
- `MyAppVersion` — version number shown in the installer
- `MyAppPublisher` — company/publisher name
- `DefaultDirName` — default install location
- `SetupIconFile` — point to your custom `.ico` file
