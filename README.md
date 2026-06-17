# ROM-AI 本地 Demo 1.0.2

这是 ROM-AI 设计平台的本地 Demo 版本，用于验证四板块联动和项目经理核心工作流。

## 板块

- 项目管理中心：项目建档、资料、会议、任务、交付与审核。
- 设计知识库：读取本地 Obsidian/项目资料，支持问答和来源引用。
- AI 设计代理：通过大对话端触发任务拆解、技术重点、会议纪要、PPT 结构等技能卡片。
- 数字网络平台：真实成员与 AI 数字员工的人机组织表。
- `/boss`：隐藏老板驾驶舱，只读查看项目态势、风险、负载和知识沉淀。

## 目录

- `frontend/`：Vite + React 前端。
- `backend/`：FastAPI + SQLite 后端。
- `docs/`：早期方案说明、技术架构和展示资料。

## 本地运行

后端：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

前端：

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5175
```

打开：

```text
http://127.0.0.1:5175/projects
```

## Windows 安装包打包

可在 GitHub Releases 下载 Windows 安装包：

```text
https://github.com/Leslie0Han/ROM-AI-local-demo/releases
```

如需本地重新生成 Windows `.exe` 安装包，请在 Windows 10/11 x64 上运行：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\build-windows-exe.ps1
```

打包结果会输出到：

```text
release/ROM-AI-Setup-1.0.2.exe
```

从 `1.0.1` 开始，桌面应用支持在“系统设置”里检查、下载并重启安装更新。发布新版时需要把 `release/` 中的安装包、`.blockmap` 和 `latest.yml` 一起上传到 GitHub Release。

详细说明见：

```text
scripts/README-Windows-Exe.md
```

## 本地私有数据

以下内容属于每台电脑自己的运行数据、依赖缓存或敏感配置，不应提交到 GitHub，也不会进入发布安装包：

- `.env`
- SQLite 数据库
- 上传资料
- `node_modules`
- `dist`
- 构建缓存、日志、临时文件
