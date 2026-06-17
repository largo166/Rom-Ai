# ROM-AI 已知问题清单

## 当前版本已知问题

- Windows 安装包暂未做代码签名，安装或下载时可能出现系统安全提示。
- 未配置 DeepSeek API Key 时，部分 AI 功能会进入 mock 模式或提示需要配置。
- 前端构建存在 bundle size warning，不影响当前功能运行。
- 后端测试存在 FastAPI `on_event` 和 `datetime.utcnow()` 弃用警告，后续版本建议治理。
- 桌面图标为当前版本生成的简版图标，后续可替换为正式品牌图标。
- 如果本机安全软件拦截 PyInstaller 后端 exe，应用可能启动失败；请在安全软件中允许 ROM-AI 后重试。

## 发布注意事项

- 不要提交或打包 `backend\.env`、`backend\data\`、`backend\uploads\`、`backend\C__\`、日志文件。
- 交付客户时优先提供 `release\ROM-AI-Setup-1.0.0.exe` 和 `README_RUN.md`。
- 不要把开发机数据库作为演示数据直接内置到安装包中；如需演示数据，建议单独设计导入流程。
