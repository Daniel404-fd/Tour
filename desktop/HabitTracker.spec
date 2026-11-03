# Сборка: pyinstaller HabitTracker.spec  (см. build_windows.bat)
# -*- mode: python ; coding: utf-8 -*-

# Неиспользуемые модули Qt — исключаем, чтобы .exe был меньше.
EXCLUDES = [
    "tkinter", "unittest", "pydoc", "PySide6.QtQml", "PySide6.QtQuick",
    "PySide6.QtQuickWidgets", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebChannel", "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.Qt3DCore", "PySide6.Qt3DRender",
    "PySide6.QtDataVisualization", "PySide6.QtGraphs", "PySide6.QtSql", "PySide6.QtTest",
    "PySide6.QtSvg", "PySide6.QtSvgWidgets", "PySide6.QtBluetooth", "PySide6.QtPositioning",
    "PySide6.QtLocation", "PySide6.QtSerialPort", "PySide6.QtSensors", "PySide6.QtDesigner",
    "PySide6.QtHelp", "PySide6.QtUiTools", "PySide6.QtXml", "PySide6.QtSpatialAudio",
    "PySide6.QtTextToSpeech", "PySide6.QtRemoteObjects", "PySide6.QtScxml",
    "PySide6.QtStateMachine", "PySide6.QtNfc", "PySide6.QtWebSockets", "PySide6.QtHttpServer",
]

a = Analysis(
    ["run_app.py"],
    pathex=["."],
    datas=[("tracker/resources/icon.png", "tracker/resources")],
    hiddenimports=["PySide6.QtNetwork", "PySide6.QtCharts", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets"],
    excludes=EXCLUDES,
    noarchive=False,
)

# Оставляем только русские и английские переводы Qt.
def _keep(entry):
    name = entry[0].replace("\\", "/")
    if "/translations/" in name:
        base = name.rsplit("/", 1)[-1]
        return base.startswith("qtbase_ru") or base.startswith("qt_ru")
    return True

a.datas = [d for d in a.datas if _keep(d)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="HabitTracker",
    icon="packaging/icon.ico",
    version="packaging/version_info.txt",
    console=False,
    upx=False,
    runtime_tmpdir=None,
)
