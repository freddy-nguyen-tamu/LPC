# pyinstaller lpc.spec

block_cipher = None

added_files = [
    ('templates', 'templates'),
    ('static', 'static'),
    ('data', 'data'),
    ('uploads', 'uploads'),
    ('outgoing', 'outgoing'),
    ('partials', 'partials'),
]


a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=added_files,
    hiddenimports=['eventlet.hubs.epolls', 'eventlet.hubs.kqueue', 'eventlet.hubs.selects'],
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
    name='TransferProServer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)