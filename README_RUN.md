# ROM-AI Windows 运行说明

## 安装与启动

1. 双击 `release\ROM-AI-Setup-1.0.0.exe` 安装。
2. 安装完成后，从桌面快捷方式或开始菜单启动 `ROM-AI`。
3. 首次启动会自动创建本机用户数据目录，不需要手动启动前端或后端。

## 用户数据位置

发布版不会把数据库、上传文件、日志写入安装目录。默认位置：

```text
%APPDATA%\ROM-AI\backend-data
%APPDATA%\ROM-AI\logs
```

其中：

- `backend-data\.env`：本机配置文件。
- `backend-data\rmo_ai.db`：SQLite 数据库。
- `backend-data\uploads`：上传文件。
- `logs\backend.log`、`logs\backend-error.log`：后端日志。

也可以在应用内打开“系统设置”页面查看这些路径。

## API Key 配置

应用不会内置 API Key、Token、账号或密码。

配置方式：

1. 打开应用的“系统设置”页面。
2. 输入 DeepSeek API Key、Base URL、模型名。
3. 点击“保存配置”。

配置会写入当前 Windows 用户的 AppData `.env`，不会写入安装目录。未配置 API Key 时，部分 AI 功能会使用 mock 模式或给出明确提示。

## 构建安装包

在项目根目录运行：

```bat
build.bat
```

或：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-windows-exe.ps1
```

如已安装依赖，可使用：

```powershell
.\scripts\build-windows-exe.ps1 -SkipInstall
```

构建输出：

```text
release\ROM-AI-Setup-1.0.0.exe
release\win-unpacked\ROM-AI.exe
```

## 故障排查

- 启动失败：查看弹窗中的错误说明，并检查 `%APPDATA%\ROM-AI\logs`。
- 端口占用：应用会自动尝试备用端口；如果仍失败，请关闭占用 8000 或 8010-8049 的程序。
- API 调用失败：确认系统设置里的 API Key、Base URL、模型名是否正确。
- 上传或数据库异常：检查 `%APPDATA%\ROM-AI\backend-data` 是否可写。

## 卸载说明

卸载程序会移除应用文件。用户数据默认保留在 `%APPDATA%\ROM-AI`，避免误删项目资料。如需彻底清理，可手动删除该目录。
