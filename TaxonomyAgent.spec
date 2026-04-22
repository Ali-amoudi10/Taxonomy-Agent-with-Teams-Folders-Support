# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

project_root = Path.cwd()

hiddenimports = [
    "tkinter",
    "tkinter.ttk",
    "config_wizard",
    "app.config_manager",
    "jinja2",
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "pythoncom",
    "win32com",
    "win32com.client",
    "chromadb.telemetry.product.posthog",
    # SharePoint / Teams support — all imported lazily inside function bodies
    "app.sharepoint",
    "app.sharepoint.client",
    "app.sharepoint.token_store",
    "app.sharepoint.device_auth",
    "app.rag_kb.teams_indexer",
    "app.source_utils",
    "requests",
    "requests.adapters",
    "requests.auth",
] + collect_submodules("chromadb")

datas = [
    (str(project_root / "app" / "ui" / "templates"), "app/ui/templates"),
    (str(project_root / "app" / "ui" / "static"), "app/ui/static"),
    (str(project_root / ".env.template"), "."),
]

block_cipher = None

a = Analysis(
    ["launcher.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="Taxonomy Agent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
