# ROM-AI Windows 桌面打包交付计划

## 当前项目结构分析

ROM-AI 是一个本地优先的混合桌面项目：

- 前端：React + Vite + TypeScript，入口为 `frontend\src\main.tsx`，构建产物为 `frontend\dist\`。
- 后端：Python FastAPI + SQLite + SQLAlchemy，开发入口为 `backend\main.py`，桌面入口为 `backend\desktop_server.py`。
- 桌面壳：Electron，入口为 `desktop\main.js`，预加载脚本为 `desktop\preload.js`。
- 打包链路：`build.bat` 调用 `scripts\build-windows-exe.ps1`，依次构建前端、PyInstaller 后端、Electron Builder 安装包。
- 资源文件：前端静态资源在 `frontend\public\`，桌面图标在 `desktop\build\icon.ico`。
- 用户数据：发布版写入 Electron `userData` 目录下的 `backend-data\` 和 `logs\`，不写入安装目录。
- 配置文件：发布版首次启动生成 AppData 下的 `.env`，不会打包本机 `backend\.env`。

## 推荐 GUI 技术方案

继续使用 Electron + React GUI：

- Electron 负责启动本地后端、加载前端静态页面、隐藏控制台窗口、管理子进程生命周期。
- React 页面作为主 GUI，包含项目中心、文件收件箱、知识库、AI 代理、网络平台、系统设置等模块。
- 系统设置页作为参数配置区，展示 API 配置状态、数据目录、配置文件、日志目录。
- 长时间任务继续由后端异步或后台任务执行，前端展示 busy、进度、日志或错误消息。
- 错误以可读提示展示，并写入 AppData 日志目录。

## 推荐 exe 打包方案

采用：

- 前端：`npm ci` + `npm run build`
- 后端：PyInstaller onedir 输出 `backend_dist\rom-ai-backend\rom-ai-backend.exe`
- 桌面安装包：Electron Builder NSIS 输出 `release\ROM-AI-Setup-1.0.0.exe`

后端 exe 通过 Electron Builder `extraResources` 放入安装包真实资源目录，避免 asar 内部无法执行。

## 块 8 · 打包与分发：便携版优先 + NSIS 缓存预置

本轮新增一条出差优先交付路径：先产出免安装便携版，再把 NSIS 安装包作为缓存就绪后的增强产物。

### 8.1 便携版（默认优先）

当 NSIS 因 `winCodeSign`、`nsis`、`nsis-resources` 下载或权限问题失败时，先使用 Electron Builder 的 directory target：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-portable-win.ps1
```

该脚本复用：

- `frontend\dist\`
- `backend\dist\rmo-ai-backend\rmo-ai-backend.exe`
- `desktop\node_modules\.bin\electron-builder.cmd`

产物：

```text
release\
  win-unpacked\
    Rmo-AI.exe
    resources\
      backend\
  ROM-AI-portable-win-unpacked.zip
```

`win-unpacked` 不走 NSIS，不需要安装器签名，也不依赖 `winCodeSign`。它适合出差、U 盘和内部分发：解压后直接双击 `Rmo-AI.exe`。

### 8.2 缓存预置

在网络可用时，预先喂满以下缓存：

```text
%LOCALAPPDATA%\electron\Cache
%LOCALAPPDATA%\electron-builder\Cache\winCodeSign
%LOCALAPPDATA%\electron-builder\Cache\nsis
```

建议加入杀软/EDR 白名单：

```text
%LOCALAPPDATA%\electron-builder\Cache
%LOCALAPPDATA%\electron\Cache
```

并固定关闭代码签名自动发现：

```bat
set CSC_IDENTITY_AUTO_DISCOVERY=false
```

镜像：

```text
ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/
ELECTRON_BUILDER_BINARIES_MIRROR=https://npmmirror.com/mirrors/electron-builder-binaries/
```

### 8.3 判断 EACCES

- 如果日志路径包含 `electron-builder\Cache\winCodeSign` 或 `electron-builder\Cache\nsis`，优先怀疑杀软隔离或缓存目录权限。
- 如果 `desktop\node_modules\.bin\electron-builder.cmd` 不存在，说明不是 NSIS 阶段失败，而是 desktop 依赖安装不完整，需要先恢复 `desktop\node_modules`。
- 如果便携版成功但 NSIS 失败，优先交付 `release\win-unpacked` 或 `ROM-AI-portable-win-unpacked.zip`。

## 已改动的关键文件

- `desktop\main.js`：启动后端、动态端口、GET 健康检查、日志、进程清理、错误提示。
- `desktop\preload.js`：提供桌面运行时信息和打开目录 IPC。
- `desktop\package.json`：配置图标、安装器、后端 `extraResources`。
- `backend\desktop_server.py`：桌面后端入口，读取 AppData、端口、日志环境变量。
- `backend\app\config.py`：去除个人路径默认值，配置写入 AppData `.env`。
- `backend\app\routes\health.py`、`backend\app\schemas.py`：状态接口返回数据、配置、日志目录。
- `frontend\src\lib\runtime.ts` 和各 API 客户端：支持 Electron 注入的后端地址。
- `frontend\src\pages\SettingsPage.tsx`：展示配置、数据、日志目录。
- `scripts\build-windows-exe.ps1`、`build.bat`：完整构建入口。
- `README_RUN.md`、`known_issues.md`、`test_checklist.md`：交付说明、已知问题、测试步骤。

## 风险点和解决方案

- API Key 泄漏：`backend\.env` 不进入安装包；若该文件被 Git 跟踪，构建脚本直接失败。
- 端口冲突：Electron 优先使用 8000，不可用时尝试 8010-8049，并把实际端口注入前端。
- 后端 exe 路径失效：Electron 同时兼容开发路径和安装包 `extraResources` 路径。
- 安装目录写入失败：数据库、上传、配置、日志全部写入 AppData。
- PyInstaller 隐藏依赖：构建脚本显式 collect FastAPI、Uvicorn、Pydantic、SQLAlchemy、Office/PDF 解析库。
- 控制台黑框：Electron 使用 `windowsHide: true` 启动后端，stdout/stderr 写入日志文件。
- 关闭残留进程：Electron 在窗口关闭和退出前终止后端子进程。
- Electron Builder 下载阻塞：构建脚本默认设置 Electron 和 electron-builder-binaries 镜像。

## 最终交付目录结构

```text
release\
  ROM-AI-Setup-1.0.0.exe
  ROM-AI-Setup-1.0.0.exe.blockmap
  win-unpacked\
    ROM-AI.exe
    resources\
      app.asar
      backend\
        rom-ai-backend\
          rom-ai-backend.exe
          _internal\

backend_dist\
  rom-ai-backend\
    rom-ai-backend.exe
    _internal\

desktop\
  build\
    icon.ico

build.bat
scripts\build-windows-exe.ps1
README_RUN.md
packaging_plan.md
known_issues.md
test_checklist.md
```

安装后用户数据目录：

```text
%APPDATA%\ROM-AI\
  backend-data\
    .env
    rmo_ai.db
    uploads\
    cloud\
  logs\
    backend.log
    backend-error.log
```

## 当前自测结果

- 后端测试：48 passed。
- 前端 lint：通过。
- 前端 build：通过，有 bundle size warning。
- 构建脚本：`scripts\build-windows-exe.ps1 -SkipInstall -SkipTests` 通过。
- 打包产物：`release\ROM-AI-Setup-1.0.0.exe` 已生成。
- 运行验收：`release\win-unpacked\ROM-AI.exe` 可启动，后端健康接口返回正常。
- 关闭验收：关闭窗口后无 ROM-AI 或后端残留进程。
- 安全检查：交付包未包含 `.env`，未发现项目代码中的硬编码密钥。
