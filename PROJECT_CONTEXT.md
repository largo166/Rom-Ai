# ROM-AI 项目上下文

更新时间：2026-06-17

## 项目定位

ROM-AI-local-demo 是一个本地优先的 Windows 桌面应用项目。当前交付目标是把原有前后端项目整理为可双击运行、可安装分发的 Windows 桌面软件。

项目采用混合技术栈：

- 前端：React + Vite + TypeScript，目录为 `frontend\`。
- 后端：Python FastAPI + SQLite + SQLAlchemy，目录为 `backend\`。
- 桌面壳：Electron，目录为 `desktop\`。
- 打包：PyInstaller 打包后端，Electron Builder 打包 Windows NSIS 安装器。

## 当前项目根目录

实际 Git 项目根目录：

```text
D:\leslie\60_claude项目库\ROM-AI-local-demo
```

项目已从解压后的内层重复目录上移到当前 Git 根目录；`__MACOSX` 解压残留目录已删除。

## 当前交付物位置

Windows 安装包：

```text
D:\leslie\60_claude项目库\ROM-AI-local-demo\release\ROM-AI-Setup-1.0.0.exe
```

免安装运行版：

```text
D:\leslie\60_claude项目库\ROM-AI-local-demo\release\win-unpacked\ROM-AI.exe
```

后端独立 exe：

```text
D:\leslie\60_claude项目库\ROM-AI-local-demo\backend_dist\rom-ai-backend\rom-ai-backend.exe
```

交付说明：

```text
README_RUN.md
packaging_plan.md
known_issues.md
test_checklist.md
```

## 关键构建脚本

一键构建入口：

```text
build.bat
```

PowerShell 构建脚本：

```text
scripts\build-windows-exe.ps1
```

常用构建命令：

```powershell
.\scripts\build-windows-exe.ps1
```

如果依赖已安装，可跳过依赖安装：

```powershell
.\scripts\build-windows-exe.ps1 -SkipInstall
```

如果只想快速重打包，可使用：

```powershell
.\scripts\build-windows-exe.ps1 -SkipInstall -SkipTests
```

构建脚本默认设置 Electron 和 electron-builder-binaries 镜像，避免 GitHub 下载不稳定导致打包失败。

## 桌面运行机制

Electron 主进程位于：

```text
desktop\main.js
```

它负责：

- 启动打包后的 `rom-ai-backend.exe`。
- 隐藏后端控制台窗口。
- 自动选择后端端口，优先 `8000`，冲突时尝试 `8010-8049`。
- 用 `GET /api/health` 轮询后端健康状态。
- 将真实后端地址注入前端。
- 将后端日志写入 AppData。
- 应用关闭时终止后端子进程。

预加载脚本：

```text
desktop\preload.js
```

它向前端暴露有限的桌面能力，例如获取运行时路径、打开日志目录或数据目录。

## 用户数据和配置

发布版不会写入安装目录。默认用户数据目录：

```text
%APPDATA%\ROM-AI\backend-data
```

默认日志目录：

```text
%APPDATA%\ROM-AI\logs
```

首次启动会生成：

```text
%APPDATA%\ROM-AI\backend-data\.env
```

本地开发用的 `backend\.env` 不会进入安装包，也不应提交到 Git。

## 安全约束

- 不要把 API Key、Token、账号、密码写死进代码或 exe。
- 不要提交 `backend\.env`。
- 不要把开发机数据库、上传文件、日志打进安装包。
- 用户数据、数据库、上传文件、日志必须写入 AppData 或用户选择目录。
- 交付包内已检查未包含 `.env`。

## 已完成的重要改造

- 新增 Electron 桌面壳打包配置。
- 新增 PyInstaller 后端桌面入口。
- 修复后端在打包后相对路径、工作目录、模块导入失效的问题。
- 修复 Electron 健康检查默认使用 HEAD 导致误判后端启动失败的问题。
- 前端 API 客户端支持 Electron 注入的动态后端地址。
- 设置页展示数据目录、配置文件、日志目录，并支持打开目录。
- 构建脚本处理依赖安装、测试、前端构建、后端 exe、安装器输出。
- 文档补齐：运行说明、打包计划、已知问题、测试清单。

## 已验证结果

最近一次验证结果：

- 后端测试：`48 passed`。
- 前端 lint：通过。
- 前端 build：通过。
- Electron Builder：已生成 NSIS 安装包。
- `release\win-unpacked\ROM-AI.exe` 可启动。
- 后端健康接口返回：

```json
{"status":"ok","service":"rmo-ai-backend","database":"sqlite"}
```

- 设置接口显示数据目录、配置文件、日志目录均在 `%APPDATA%\ROM-AI` 下。
- 关闭窗口后无 ROM-AI 或后端残留进程。

## 已知问题

- 安装包暂未做代码签名，Windows 可能出现安全提示。
- 前端构建有 bundle size warning，不影响当前运行。
- 后端测试有 FastAPI `on_event` 和 `datetime.utcnow()` 弃用警告。
- 桌面图标是临时生成的简版图标，可替换为正式品牌图标。
- 如果杀毒软件拦截 PyInstaller 后端 exe，应用可能启动失败，需要放行。

## 后续接手建议

1. 如需交付给他人，优先发送 `release\ROM-AI-Setup-1.0.0.exe` 和 `README_RUN.md`。
2. 如用户找不到文件，先检查 `release\` 目录是否存在；不存在则重新运行 Electron Builder 或构建脚本。
3. 如果要正式发布，建议增加代码签名证书。
4. 如果要减少安装包体积，优先治理前端 bundle 拆包和 PyInstaller collect 范围。
5. 如需清理仓库，请谨慎处理当前已有的用户改动；不要随意 revert 未确认来源的修改。
