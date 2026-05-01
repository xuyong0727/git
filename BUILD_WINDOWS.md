构建 Windows 可执行文件（EXE）说明

目标：在 Windows 10+ 上生成 `scan_control.exe`。

两种方式：本地在 Windows 上构建（推荐）或使用 GitHub Actions 在云上构建。

先决条件
- 请确保仓库根目录包含以下文件：`scan_control.py`（主程序），可选 `p.ico`（程序图标），可选 `config.ini`（运行时配置）。
- 若你的项目使用 `pymssql`，请在 Windows 环境上确保相关二进制依赖可用（通常 Windows runner 可安装二进制 wheel）。

1) 在本地 Windows 上构建（简单）

打开 `cmd.exe`（或 PowerShell），切换到项目目录，执行：

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pyinstaller --clean --onefile --noconsole --icon=p.ico --add-data "config.ini;." scan_control.py
```

生成的 exe 在 `dist\scan_control.exe`。

常见问题：
- 如果程序启动失败但无窗口，请暂时移除 `--noconsole` 以查看错误输出。 
- 若 PyInstaller 在打包时缺少某些模块（找不到 mssql 驱动），可在 workflow 或本地手动安装失败的二进制依赖，或改用 `pyodbc` 并调整代码（替换 `pymssql`）。

2) 使用 GitHub Actions 构建（推荐用于你无法在 Windows 本地构建时）

- 我已添加工作流文件：`.github/workflows/build-windows.yml`。 在仓库推送后，进入 GitHub 上的 `Actions`，找到 `Build Windows exe`，点击 `Run workflow`。
- 构建完成后，工作流会将 `dist/scan_control.exe` 作为 artifact 上传，可在 workflow 运行页面下载。

注意事项
- 请把 `p.ico`（若需要图标）和 `config.ini`（若需要初始配置）加入仓库，否则构建将发出警告，exe 仍可生成但可能没有图标或使用默认配置。
- 若你需要我把构建结果直接生成并发送给你，请授权我访问你的 GitHub 仓库并触发工作流，或将代码推到我可访问的仓库（当前环境无法直接交付 Windows 二进制）。

需要我现在为你把这些文件推送到 GitHub 并触发 Action 吗？
