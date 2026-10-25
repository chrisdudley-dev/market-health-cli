# Build on each target OS; PyInstaller does not cross-compile.
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, copy_metadata
root = Path(SPECPATH).parent
app_data = collect_data_files('market_health') + copy_metadata('market-health-cli') + [(str(root / 'config'), 'config')]
a = Analysis([str(root / 'packaging/desktop_entry.py')], pathex=[str(root)],
             datas=app_data, hiddenimports=[],
             excludes=['PySide6.QtWebEngineCore','PySide6.QtWebEngineWidgets','PySide6.QtQml',
                       'PySide6.QtQuick','PySide6.QtPdf','matplotlib','scipy','tkinter','pytest','IPython'])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='MarketHealth',
          console=False, icon=str(root / 'packaging/market-health.ico'))
coll = COLLECT(exe, a.binaries, a.datas, name='MarketHealth')
