# -*- mode: python ; coding: utf-8 -*-
import sys
import os

block_cipher = None

a = Analysis(
    ['gui.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('phosphor-icons.ttf', '.'),
        ('phosphor-icons-fill.ttf', '.'),
        ('uxlive-logo.png', '.'),
    ],
    hiddenimports=[
        'scipy.ndimage',
        'scipy.special',
        'numpy',
        'PIL',
        'PIL.Image',
        'PySide6',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Sticker Studio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    target_arch='arm64',
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Sticker Studio',
)

app = BUNDLE(
    coll,
    name='Sticker Studio.app',
    icon='AppIcon.icns',
    bundle_identifier='com.yoggypub.stickerstudio',
    info_plist={
        'CFBundleDisplayName': 'Sticker Studio',
        'CFBundleName': 'Sticker Studio',
        'CFBundleIdentifier': 'com.yoggypub.stickerstudio',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'CFBundlePackageType': 'APPL',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '12.0',
        'NSRequiresAquaSystemAppearance': False,
    },
)
