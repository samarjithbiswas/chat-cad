Chat CAD - Windows installer
============================

Quick start
-----------
1. Double-click  "Install Chat CAD.bat"
   Wait ~5 min while Miniforge and cadquery download (~1.5 GB total).
   This is one-time. You can close the window when it says "installed".

2. Double-click the "Chat CAD" shortcut on your Desktop
   (or "Run Chat CAD.bat" in this folder).
   Your default browser opens to the app at http://127.0.0.1:5000/.

3. To use the natural-language interface, paste an Anthropic API key
   into the settings panel. Without a key, the typed-command parser
   still works for everything.

What gets installed where
-------------------------
%USERPROFILE%\miniforge-chatcad\        the private Python environment
                                        (no effect on your system Python)
Desktop\Chat CAD.lnk                    launcher shortcut
Start Menu\Chat CAD.lnk                 launcher shortcut

Removing it
-----------
Double-click "Uninstall Chat CAD.bat". The env and shortcuts are removed;
the source folder is left alone so you can keep your STEP / STL exports.

Troubleshooting
---------------
"Chat CAD is not installed yet"
    You ran Run Chat CAD before Install Chat CAD. Run the installer first.

PowerShell ExecutionPolicy error
    The .bat file already uses -ExecutionPolicy Bypass. If it still fails,
    open PowerShell as your user and run the install.ps1 directly:
        powershell -ExecutionPolicy Bypass -File install.ps1

Browser does not open
    Visit http://127.0.0.1:5000/ manually.

cadquery import error in the verify step
    Re-run "Install Chat CAD.bat" - the first conda install sometimes
    races on slow networks. The second run is usually clean.
