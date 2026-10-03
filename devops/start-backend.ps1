# 稳定启动 AIStation 后端（单进程、无 reload）
#
# 用途：避免 `uv run main.py run` 在 dev 环境强制 --reload 产生的多实例/端口句柄残留。
# 步骤：
#   1. 强杀所有监听 8001 的进程 + uv reload supervisor；
#   2. 用 uvicorn 单进程（--factory, 无 --reload）启动后端。
#
# 用法：
#   powershell -File devops/start-backend.ps1            # 后台启动
#   powershell -File devops/start-backend.ps1 -Foreground # 前台（便于看日志）
#   powershell -File devops/start-backend.ps1 -Port 8001

param(
  [switch]$Foreground,
  [int]$Port = 8001
)

$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $PSScriptRoot   # devops -> 仓库根
$Backend = Join-Path $Root 'backend'

Write-Host "== 清理端口 $Port 上的存活进程 =="
$conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
$killed = 0
foreach ($c in $conns) {
  if ($c.OwningProcess -and $c.OwningProcess -ne 0) {
    $p = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
    if ($p) {
      try { Stop-Process -Id $c.OwningProcess -Force -ErrorAction Stop; $killed++ } catch {}
    }
  }
}
Write-Host "  已停止 $killed 个监听进程"

Write-Host "== 清理 uv reload supervisor (uv.exe) =="
Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'uv.exe' } | ForEach-Object {
  try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop } catch {}
}
Start-Sleep -Seconds 3

Set-Location $Backend
$env:ENVIRONMENT = 'dev'
$env:PYTHONIOENCODING = 'utf-8'

if ($Foreground) {
  Write-Host "== 前台启动后端 (uvicorn 单进程, 无 reload), 端口 $Port =="
  uv run uvicorn main:create_app --factory --host 0.0.0.0 --port $Port
} else {
  Write-Host "== 后台启动后端 (uvicorn 单进程, 无 reload), 端口 $Port =="
  Start-Process -FilePath 'uv' `
    -ArgumentList 'run','uvicorn','main:create_app','--factory','--host','0.0.0.0','--port',"$Port" `
    -WorkingDirectory $Backend -WindowStyle Hidden
  Write-Host "  已在后台启动，日志见控制台/提到的方式。"
}
