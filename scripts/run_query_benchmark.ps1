# 一键跑智能问数基准（含精度门槛）
# 用法：
#   .\scripts\run_query_benchmark.ps1                          # 全量 113 题 + 精度门槛(默认 0.90)
#   .\scripts\run_query_benchmark.ps1 -Tag '本体黑话' -Threshold 0.95   # 快速只跑本体黑话 + 95% 门槛
param(
  [string]$Tag = "",
  [double]$Threshold = 0.90
)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\backend")

$args = @("run", "python", "-m", "app.plugin.module_ai.query.benchmark", "--check", "--threshold=$Threshold")
if ($Tag) { $args += "--tag=$Tag" }

Write-Host "==> 智能问数基准回归（Tag=$Tag  Threshold=$Threshold）" -ForegroundColor Cyan
uv @args
if ($LASTEXITCODE -ne 0) { Write-Host "==> 基准未达标，回归失败" -ForegroundColor Red; exit 1 }
Write-Host "==> 基准回归通过 ✅" -ForegroundColor Green
