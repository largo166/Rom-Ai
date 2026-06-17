# ROM-AI Windows 交付测试清单

## 构建前

- [x] `backend\.env` 未被 Git 跟踪。
- [x] `backend\requirements.txt` 存在。
- [x] `frontend\package-lock.json` 存在。
- [x] `desktop\package-lock.json` 存在。
- [x] `desktop\build\icon.ico` 存在。
- [x] `backend\.venv-win\Scripts\python.exe -m pytest` 通过。
- [x] `npm run lint` 在 `frontend` 通过。
- [x] `npm run build` 在 `frontend` 通过。

## 打包

- [x] `scripts\build-windows-exe.ps1 -SkipInstall -SkipTests` 可完整跑通。
- [x] 生成 `backend_dist\rom-ai-backend\rom-ai-backend.exe`。
- [x] 生成 `release\ROM-AI-Setup-1.0.0.exe`。
- [x] 生成 `release\win-unpacked\ROM-AI.exe`。
- [x] 交付包不包含 `backend\.env`。
- [x] 交付包不包含开发机 `backend\data\rmo_ai.db`。
- [x] 交付包不包含开发机上传文件。

## 运行验收

- [x] 双击 `release\win-unpacked\ROM-AI.exe` 可以启动。
- [x] 启动时没有命令行黑框。
- [x] 后端随桌面应用启动，`GET /api/health` 返回正常。
- [x] 设置接口显示数据目录、配置文件、日志目录位于 AppData。
- [x] 未配置 API Key 时显示未配置状态，不闪退。
- [x] 关闭窗口后无 ROM-AI 或后端异常残留进程。

## 建议人工复测

- [ ] 在一台没有开发环境的 Windows 电脑上安装 `release\ROM-AI-Setup-1.0.0.exe` 并启动。
- [ ] 在系统设置页保存 DeepSeek API Key 后验证 AI 功能。
- [ ] 上传一个文件，确认文件写入 `%APPDATA%\ROM-AI\backend-data\uploads`。
- [ ] 占用 8000 端口后启动，确认应用可切换到备用端口或给出清晰提示。
