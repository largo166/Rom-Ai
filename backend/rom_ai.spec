# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

# 需要显式收集的包：既有后端业务代码，也有依赖的隐藏子模块
hiddenimports = ["app.main"]
for pkg in [
    "app",
    "pydantic",
    "pydantic_core",
    "pydantic_settings",
    "uvicorn",
    "anyio",
    "docx",
    "openpyxl",
    "pptx",
    "pdfplumber",
    "pypdf",
    "sqlalchemy",
    "alembic",
    "httpx",
    "starlette",
    "fastapi",
    "lxml",
]:
    hiddenimports.extend(collect_submodules(pkg))

# 显式收集包含数据文件/二进制文件/隐藏子模块的依赖
datas = []
binaries = []
for pkg in [
    "pydantic",
    "pydantic_settings",
    "fastapi",
    "uvicorn",
    "sqlalchemy",
    "alembic",
    "python_dotenv",
    "pypdf",
    "docx",
    "pptx",
    "openpyxl",
    "lxml",
    "httpx",
]:
    try:
        tmp_ret = collect_all(pkg)
        datas += tmp_ret[0]
        binaries += tmp_ret[1]
        hiddenimports += tmp_ret[2]
    except Exception:
        pass

# 项目数据文件与顶层入口模块：迁移脚本、alembic 配置、内置知识库资产、FastAPI 主模块
datas += [
    ("migrations", "migrations"),
    ("alembic.ini", "."),
    ("knowledge_assets", "knowledge_assets"),
    ("main.py", "."),
]

a = Analysis(
    ["entry.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy", "numpy"],
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
    name="rmo-ai-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # --noconsole
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="rmo-ai-backend",
)
