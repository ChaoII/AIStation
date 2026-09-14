#Requires -Version 7.0
<#
.SYNOPSIS
    AIStation 云边协同真机端到端联调脚本（ModelDeploy aistation_agent + AIStation 后端）。

.DESCRIPTION
    编排一次完整的「云端播种 → 边缘 Agent 执行 → 告警落库」链路，并在关键节点做断言：

      1) 可选启动 Docker `eclipse-mosquitto` Broker（-Transport mqtt 时）；
      2) 登录 AIStation（admin），播种 EdgeDevice / Algorithm / Camera / AlgorithmTask；
      3) 启动 `aistation_agent.exe`（控制面 HTTP + 心跳 + 事件发布）；
      4) 启动算法任务，轮询并断言：设备 online、Agent 任务 running、告警落库且
         `algorithm_type=INTRUSION`、`snapshot_url` 非空、重复 event_id 不重复建告警；
      5) 时段（schedule）与生命周期：窗口外任务不产生告警、stop 同步 Agent、delete 同步 Agent；
      6) 打印证据（告警样本、DB 查询语句）与失败/警告汇总。

    本脚本只负责「代码工件」层面的编排，不保证被测环境一定满足前置条件。运行前请阅读：
      docs/superpowers/runbooks/edge-agent-e2e.md

.PARAMETER Transport
    事件通道：mqtt（云边，需 Broker + 后端 VIDEO_ANALYSIS_MODE=cloud_edge）或
    http（纯云，后端 VIDEO_ANALYSIS_MODE=cloud_only，Agent 直连 detection/callback）。

.PARAMETER AgentExe
    aistation_agent.exe 绝对路径。

.PARAMETER VideoPath
    摄像机子码流地址；本脚本用本地 mp4 文件冒充 RTSP（FFmpeg 可直接读文件）。

.PARAMETER ModelPath
    算法模型文件路径。支持本地绝对路径（同机 Agent 直接读取）或 http(s)/s3 URL（Agent 下载）。

.PARAMETER DecoderHwAccel
    算法 runtime_config.decoder.hw_accel，默认 none（CPU 解码，匹配 -ModelPath 的 ORT/CPU 后端）。
    Agent 侧可选值：auto/none/cuda/vaapi/qsv/sophgo（见 ModelDeploy config.hpp）。
    若模型走 GPU（backend=cuda）则需改为 cuda，否则 CPU 后端会拒绝 GPU NV12。

.PARAMETER EdgeCode
    边缘设备编码；必须与 Agent `--edge-code` 一致（心跳按 code upsert）。

.PARAMETER Secret
    边缘控制面/心跳共享密钥；同时用作 Agent 的 `--api-key` 与 `--secret`，并写入 EdgeDevice.secret
    与后端 EDGE_CONTROL_TOKEN（后端侧需保持一致）。

.PARAMETER ApiBase
    AIStation 后端基址，默认 http://127.0.0.1:8001 。

.PARAMETER BackendDir
    后端目录（用于打印 DB 证据命令，不修改后端）。

.PARAMETER AgentControlUrl
    Agent 控制面基址，默认 http://<AgentHost>:<AgentPort> 。

.PARAMETER CaptchaReferer
    登录请求携带的 Referer；以 "docs"/"redoc" 结尾可绕过验证码（后端 login 的 docs 免验证码逻辑）。

.PARAMETER InferenceCallbackToken
    HTTP 通道下 Agent 回调 detection/callback 的 Bearer 令牌（需与后端 INFERENCE_CALLBACK_TOKEN 一致）。

.PARAMETER BrokerName
    Docker Broker 容器名，默认 aistation-mqtt-e2e 。

.PARAMETER SkipBroker
    跳过 Docker Broker 启动；使用已有 Broker 或 Transport=http 时可用。

.PARAMETER KeepResources
    保留 Agent 进程与 Broker 容器（默认结束时停止并删除）。

.PARAMETER KeepData
    保留播种的 Algorithm/Camera/EdgeDevice（默认任务结束即删除任务，并清理本次创建的算法/相机/设备）。

.PARAMETER ScheduleSettleSec
    时段断言前等待秒数；给 Agent schedule_loop 足够时间停掉窗口外任务（该循环约 30s 一轮）。

.PARAMETER AlarmWaitSec
    等待告警出现的超时秒数。

.PARAMETER PollTimeoutSec
    通用轮询超时秒数（设备 online / Agent 任务 running / 生命周期同步）。

.EXAMPLE
    pwsh -NoProfile -File scripts/e2e/edge_agent_e2e.ps1 -Transport mqtt -Secret e2e-secret

.EXAMPLE
    pwsh -NoProfile -File scripts/e2e/edge_agent_e2e.ps1 -Transport http -SkipBroker -KeepData
#>
[CmdletBinding()]
param(
    [ValidateSet("mqtt", "http")]
    [string]$Transport = "mqtt",

    [string]$AgentExe = "E:\CLionProjects\ModelDeploy\build\bin\aistation_agent.exe",
    [string]$VideoPath = "E:\CLionProjects\ModelDeploy\test_data\test_video60.mp4",
    [string]$ModelPath = "E:\CLionProjects\ModelDeploy\test_data\test_models\onnx\yolo11n\yolo11n_nms.onnx",
    [string]$DecoderHwAccel = "none",

    [string]$EdgeCode = "edge-01",
    [string]$Secret = "e2e-shared-secret",
    [string]$ApiBase = "http://127.0.0.1:8001",
    [string]$BackendDir = "D:\AIStation\backend",

    [string]$AgentHost = "127.0.0.1",
    [int]$AgentPort = 19090,
    [string]$AgentControlUrl = "",

    [string]$Username = "admin",
    [string]$Password = "123456",
    [string]$CaptchaReferer = "",
    [string]$InferenceCallbackToken = "infer_callback_shared_secret",

    [string]$BrokerName = "aistation-mqtt-e2e",
    [string]$BrokerImage = "eclipse-mosquitto:2",
    [int]$BrokerPort = 1883,
    [string]$MqttTopicPrefix = "aistation/default/edge",

    [switch]$SkipBroker,
    [switch]$KeepResources,
    [switch]$KeepData,

    [int]$ScheduleSettleSec = 40,
    [int]$AlarmWaitSec = 180,
    [int]$PollTimeoutSec = 180
)

$ErrorActionPreference = "Stop"
$script:Failures = [System.Collections.Generic.List[string]]::new()
$script:Warnings = [System.Collections.Generic.List[string]]::new()

# ─────────────────────────── 日志辅助 ───────────────────────────

function Write-E2E {
    param(
        [Parameter(Mandatory)][string]$Message,
        [ValidateSet("INFO", "OK", "WARN", "FAIL", "STEP")][string]$Level = "INFO"
    )
    $ts = (Get-Date).ToString("HH:mm:ss")
    $prefix = switch ($Level) {
        "OK"   { "[ OK ]" }
        "WARN" { "[WARN]" }
        "FAIL" { "[FAIL]" }
        "STEP" { "────" }
        default { "[INFO]" }
    }
    $color = switch ($Level) {
        "OK"   { "Green" }
        "WARN" { "Yellow" }
        "FAIL" { "Red" }
        "STEP" { "Cyan" }
        default { "Gray" }
    }
    Write-Host "$ts $prefix $Message" -ForegroundColor $color
}

function Add-Failure {
    param([Parameter(Mandatory)][string]$Message)
    $script:Failures.Add($Message)
    Write-E2E $Message -Level FAIL
}

function Add-Warning {
    param([Parameter(Mandatory)][string]$Message)
    $script:Warnings.Add($Message)
    Write-E2E $Message -Level WARN
}

function Assert-That {
    param(
        [Parameter(Mandatory)][bool]$Condition,
        [Parameter(Mandatory)][string]$Message
    )
    if ($Condition) {
        Write-E2E $Message -Level OK
    } else {
        Add-Failure $Message
    }
    return $Condition
}

# ─────────────────────────── HTTP 辅助 ───────────────────────────

function Get-AdminToken {
    param(
        [Parameter(Mandatory)][string]$Base,
        [Parameter(Mandatory)][string]$User,
        [Parameter(Mandatory)][string]$Pass,
        [Parameter(Mandatory)][string]$Referer
    )
    $uri = "$Base/api/v1/system/auth/login"
    $headers = @{ Referer = $Referer; "X-Forwarded-For" = "127.0.0.1" }
    $body = @{ username = $User; password = $Pass; grant_type = "password" }
    try {
        $resp = Invoke-RestMethod -Method Post -Uri $uri -Headers $headers -Body $body `
            -ContentType "application/x-www-form-urlencoded"
    } catch {
        $detail = $_.ErrorDetails.Message
        if (-not $detail) { $detail = $_.Exception.Message }
        throw "登录失败: $detail`n提示：若后端开启验证码，请设置 CAPTCHA_ENABLE=false 重启后端，或把 -CaptchaReferer 指向以 docs/redoc 结尾的地址。"
    }
    # docs referer 下后端返回扁平 token（login 控制器对 DOCS_URL referer 直接返回 model_dump），
    # 其余情况返回 { data: { access_token } }；此处兼容两种形状。
    $token = $resp.access_token
    if (-not $token) { $token = $resp.data.access_token }
    if (-not $token) { throw "登录响应缺少 access_token: $($resp | ConvertTo-Json -Depth 5 -Compress)" }
    return $token
}

# 调用 AIStation 业务 API（自动带 Bearer 与 X-Forwarded-For）；返回后端 JSON 的 data 字段。
function Invoke-Api {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Method,
        [Parameter(Mandatory)][string]$Path,
        [AllowNull()][object]$Body = $null,
        [switch]$Full
    )
    $uri = "$($script:ApiBase)$Path"
    $headers = @{
        Authorization     = "Bearer $($script:Token)"
        "X-Forwarded-For" = "127.0.0.1"
    }
    $params = @{ Method = $Method; Uri = $uri; Headers = $headers }
    if ($null -ne $Body) {
        $params.ContentType = "application/json; charset=utf-8"
        $params.Body = if ($Body -is [string]) { $Body } else { $Body | ConvertTo-Json -Depth 20 -Compress }
    }
    try {
        $resp = Invoke-RestMethod @params
    } catch {
        $detail = $_.ErrorDetails.Message
        if (-not $detail) { $detail = $_.Exception.Message }
        throw "API $Method $Path 失败: $detail"
    }
    if ($Full) { return $resp }
    return $resp.data
}

# 调用 Agent 控制面 API；AllowNotFound 时 404 返回 $null。
function Invoke-AgentApi {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Method,
        [Parameter(Mandatory)][string]$Path,
        [AllowNull()][object]$Body = $null,
        [switch]$AllowNotFound
    )
    $uri = "$($script:AgentControlUrl)$Path"
    $headers = @{ Authorization = "Bearer $($script:Secret)" }
    $params = @{
        Method               = $Method
        Uri                  = $uri
        Headers              = $headers
        SkipHttpErrorCheck   = $true
    }
    if ($null -ne $Body) {
        $params.ContentType = "application/json; charset=utf-8"
        $params.Body = if ($Body -is [string]) { $Body } else { $Body | ConvertTo-Json -Depth 20 -Compress }
    }
    $resp = Invoke-WebRequest @params
    if ($AllowNotFound -and $resp.StatusCode -eq 404) { return $null }
    if ($resp.StatusCode -ge 400) {
        throw "Agent API $Method $Path -> $($resp.StatusCode): $($resp.Content)"
    }
    if (-not $resp.Content) { return $null }
    return ($resp.Content | ConvertFrom-Json)
}

function Wait-Until {
    param(
        [Parameter(Mandatory)][scriptblock]$Condition,
        [Parameter(Mandatory)][string]$Message,
        [int]$TimeoutSec = 180,
        [int]$IntervalSec = 3
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            if (& $Condition) { return $true }
        } catch {
            Write-Verbose "轮询异常（继续重试）: $_"
        }
        Start-Sleep -Seconds $IntervalSec
    }
    Add-Warning "轮询超时（${TimeoutSec}s）: $Message"
    return $false
}

function Get-AlarmItems {
    param([Parameter(Mandatory)][int]$CameraId, [int]$PageSize = 100)
    $data = Invoke-Api -Method Get -Path "/api/v1/video/alarm/record/list?camera_id=$CameraId&page_no=1&page_size=$PageSize"
    if ($data -and $data.items) { return @($data.items) }
    return @()
}

# ─────────────────────────── Broker / Agent 生命周期 ───────────────────────────

function Remove-Broker {
    $exists = docker ps -a --format "{{.Names}}" 2>$null | Where-Object { $_ -eq $BrokerName }
    if ($exists) {
        Write-E2E "移除已存在的 Broker 容器: $BrokerName"
        docker rm -f $BrokerName | Out-Null
    }
}

function Start-Broker {
    $imageExists = docker images --format "{{.Repository}}:{{.Tag}}" 2>$null | Where-Object { $_ -like "$($BrokerImage)*" }
    if (-not $imageExists) {
        throw "本地缺少 Docker 镜像 $BrokerImage，请先执行: docker pull $BrokerImage"
    }
    Remove-Broker

    # eclipse-mosquitto 2.x 默认不允许匿名且仅监听容器内 localhost，
    # 必须挂载显式配置，否则宿主/后端无法匿名连接。
    $confPath = Join-Path $script:TmpDir "mosquitto.conf"
    @(
        "listener 1883 0.0.0.0",
        "allow_anonymous true",
        "persistence false",
        "log_dest stdout"
    ) | Set-Content -Path $confPath -Encoding ascii

    Write-E2E "启动 Broker: docker run -d --name $BrokerName -p ${BrokerPort}:1883 -v <conf> $BrokerImage"
    docker run -d --name $BrokerName -p "${BrokerPort}:1883" `
        -v "${confPath}:/mosquitto/config/mosquitto.conf" `
        $BrokerImage | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Broker 容器启动失败（docker run 退出码 $LASTEXITCODE）" }
    $script:BrokerStarted = $true
}

function Stop-Broker {
    if ($script:BrokerStarted -and -not $KeepResources) {
        Write-E2E "停止并删除 Broker 容器: $BrokerName"
        docker rm -f $BrokerName | Out-Null
    } elseif ($script:BrokerStarted) {
        Write-E2E "按 -KeepResources 保留 Broker 容器: $BrokerName"
    }
}

function Start-Agent {
    if (-not (Test-Path -LiteralPath $AgentExe)) {
        throw "找不到 Agent 可执行文件: $AgentExe"
    }
    $dataDir = Join-Path $script:TmpDir "agent-data"
    $modelCache = Join-Path $script:TmpDir "model-cache"
    New-Item -ItemType Directory -Force -Path $dataDir, $modelCache | Out-Null
    $script:AgentDataDir = $dataDir

    $agentArgs = @(
        "--host", $AgentHost,
        "--port", "$AgentPort",
        "--data-dir", $dataDir,
        "--model-cache-dir", $modelCache,
        "--api-key", $Secret,
        "--secret", $Secret,
        "--cloud-url", $ApiBase,
        "--edge-code", $EdgeCode,
        "--heartbeat-interval", "10"
    )
    $script:AgentStdout = Join-Path $script:TmpDir "agent.stdout.log"
    $script:AgentStderr = Join-Path $script:TmpDir "agent.stderr.log"
    # 含空格的参数加引号，避免 Start-Process 拼接参数时被拆分
    $quotedArgs = $agentArgs | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }
    Write-E2E "启动 Agent: $AgentExe $($agentArgs -join ' ')"
    $script:AgentProc = Start-Process -FilePath $AgentExe -ArgumentList $quotedArgs -PassThru `
        -NoNewWindow -RedirectStandardOutput $script:AgentStdout -RedirectStandardError $script:AgentStderr

    $ok = Wait-Until -TimeoutSec 30 -IntervalSec 1 -Message "Agent /health 就绪" -Condition {
        try {
            $r = Invoke-RestMethod -Method Get -Uri "$($script:AgentControlUrl)/health" -TimeoutSec 3
            return ($r.status -eq "ok")
        } catch { return $false }
    }
    if (-not $ok) { throw "Agent 控制面 /health 未就绪，见日志: $($script:AgentStdout) / $($script:AgentStderr)" }
}

function Stop-Agent {
    if ($script:AgentProc -and -not $script:AgentProc.HasExited) {
        if ($KeepResources) {
            Write-E2E "按 -KeepResources 保留 Agent 进程（PID=$($script:AgentProc.Id)）"
        } else {
            Write-E2E "停止 Agent 进程（PID=$($script:AgentProc.Id)）"
            Stop-Process -Id $script:AgentProc.Id -Force -ErrorAction SilentlyContinue
        }
    }
}

# ─────────────────────────── 播种辅助 ───────────────────────────

# 边缘设备播种：优先 create；若 code 已存在（可能已被 Agent 心跳自动 upsert），则改为 update。
function Seed-EdgeDevice {
    $createBody = @{
        name         = "E2E 边缘设备 $EdgeCode"
        code         = $EdgeCode
        control_url  = $script:AgentControlUrl
        secret       = $Secret
        capabilities = @{
            model_families = @("det")
            backends       = @("ort")
            max_channels   = 8
        }
    }
    try {
        $data = Invoke-Api -Method Post -Path "/api/v1/video/edge/create" -Body $createBody
        $script:CreatedEdge = $true
        return $data.id
    } catch {
        Write-E2E "edge/create 未成功（可能已存在），尝试按 code 查询并更新: $_"
        $list = Invoke-Api -Method Get -Path "/api/v1/video/edge/list?code=$EdgeCode&page_no=1&page_size=50"
        $item = @($list.items) | Where-Object { $_.code -eq $EdgeCode } | Select-Object -First 1
        if (-not $item) { throw "边缘设备不存在且无法创建: $EdgeCode" }
        $updateBody = @{
            name         = $item.name
            code         = $EdgeCode
            control_url  = $script:AgentControlUrl
            secret       = $Secret
            capabilities = $item.capabilities
        }
        Invoke-Api -Method Put -Path "/api/v1/video/edge/update/$($item.id)" -Body $updateBody | Out-Null
        $script:CreatedEdge = $false
        return $item.id
    }
}

function New-UniqueCode {
    param([string]$Base)
    return "$Base-e2e-$($script:RunId)"
}

# ─────────────────────────── 主流程 ───────────────────────────

$script:RunId = (Get-Date).ToString("MMddHHmmss")
$script:BrokerStarted = $false
$script:CreatedEdge = $false
$script:AgentProc = $null
$script:AgentDataDir = $null
$script:AgentStdout = $null
$script:AgentStderr = $null
$script:Token = $null
$script:SampleAlarm = $null
$script:Secret = $Secret
$script:AgentControlUrl = if ($AgentControlUrl) { $AgentControlUrl.TrimEnd("/") } else { "http://${AgentHost}:${AgentPort}" }
$script:ApiBase = $ApiBase.TrimEnd("/")
# 默认以 docs referer 绕过登录验证码（后端仅对 docs/redoc 结尾的 referer 跳过校验）
if ([string]::IsNullOrWhiteSpace($CaptchaReferer)) { $CaptchaReferer = "$($script:ApiBase)/docs" }
$script:TmpDir = Join-Path $env:TEMP "aistation-edge-e2e-$($script:RunId)"
New-Item -ItemType Directory -Force -Path $script:TmpDir | Out-Null

# 已创建资源 ID，便于清理
$created = @{ AlgorithmId = $null; CameraId = $null; EdgeId = $null; Task1Id = $null; Task2Id = $null }

Write-E2E "==== AIStation 云边 Agent 真机 E2E（transport=$Transport） ===="
Write-E2E "RunId=$($script:RunId)  TmpDir=$($script:TmpDir)  AgentControl=$($script:AgentControlUrl)"

try {
    if ($Transport -eq "mqtt" -and -not $SkipBroker) {
        Write-E2E "Step 1a: 启动 MQTT Broker" -Level STEP
        Start-Broker
    } elseif ($Transport -eq "mqtt") {
        Write-E2E "Step 1a: 跳过 Broker（-SkipBroker），假定已有 Broker 监听 $BrokerPort" -Level STEP
    } else {
        Write-E2E "Step 1a: Transport=http，跳过 Broker" -Level STEP
    }

    Write-E2E "Step 1b: 登录 AIStation 并播种 EdgeDevice" -Level STEP
    $script:Token = Get-AdminToken -Base $script:ApiBase -User $Username -Pass $Password -Referer $CaptchaReferer
    Write-E2E "登录成功，已获取 Bearer token" -Level OK
    $created.EdgeId = Seed-EdgeDevice
    Write-E2E "EdgeDevice id=$($created.EdgeId) code=$EdgeCode" -Level OK

    Write-E2E "Step 1c: 启动边缘 Agent（先播种设备，避免心跳抢先 upsert 丢失 control_url/secret）" -Level STEP
    Start-Agent
    Write-E2E "Agent 控制面就绪: $($script:AgentControlUrl)" -Level OK

    Write-E2E "Step 2: 播种 Algorithm / Camera / AlgorithmTask" -Level STEP
    $algoCode = New-UniqueCode "INTRUSION"
    $algoBody = @{
        name            = "E2E 闯入检测 $($script:RunId)"
        code            = $algoCode
        algorithm_type  = "INTRUSION"
        model_path      = $ModelPath
        runtime_config  = @{
            backend  = "ort"
            device   = "cpu"
            decoder  = @{ hw_accel = $DecoderHwAccel; device_only = $false; rtsp_transport = "tcp" }
        }
        preset_params   = @{ confidence_threshold = 0.4; input_size = @(640, 640) }
    }
    $algo = Invoke-Api -Method Post -Path "/api/v1/video/algorithm/create" -Body $algoBody
    $created.AlgorithmId = $algo.id
    Write-E2E "Algorithm id=$($created.AlgorithmId) code=$algoCode" -Level OK

    $cameraBody = @{
        name        = "E2E 摄像机 $($script:RunId)"
        rtsp_url_sub = $VideoPath
    }
    $camera = Invoke-Api -Method Post -Path "/api/v1/video/camera/create" -Body $cameraBody
    $created.CameraId = $camera.id
    Write-E2E "Camera id=$($created.CameraId) rtsp_url_sub=$VideoPath" -Level OK

    # 今天 ISO 星期（0=周一 .. 6=周日），与 Agent schedule 语义一致
    $todayIso = ((Get-Date).DayOfWeek.value__ + 6) % 7
    $otherIso = ($todayIso + 1) % 7

    $taskBody = @{
        camera_id      = $created.CameraId
        algorithm_id   = $created.AlgorithmId
        edge_device_id = $created.EdgeId
        stream_type    = "SUB"
        sensitivity    = 50
        detect_region  = @{ points = @(@(0.2, 0.2), @(0.8, 0.2), @(0.8, 0.8), @(0.2, 0.8)) }
        schedule_json  = @{ slots = @(@{ day = $todayIso; start = 0; end = 24 }) }
    }
    $task1 = Invoke-Api -Method Post -Path "/api/v1/video/algorithm/task/create" -Body $taskBody
    $created.Task1Id = $task1.id
    Write-E2E "AlgorithmTask#1 id=$($created.Task1Id) schedule=今天($todayIso) 全天" -Level OK

    if ($Transport -eq "mqtt") {
        Write-E2E "前置检查: MQTT 事件通道配置（后端需 VIDEO_ANALYSIS_MODE=cloud_edge / MQTT_ENABLED=true / MQTT_BROKER_URL=tcp://127.0.0.1:$BrokerPort）" -Level STEP
        $modeHint = "本脚本无法读取后端运行环境；若告警长时间不出现，请核对 runbook 的『环境变量』章节。"
        Write-E2E $modeHint -Level INFO
    }

    Write-E2E "Step 3a: 启动任务#1 并等待设备 online" -Level STEP
    Invoke-Api -Method Post -Path "/api/v1/video/algorithm/task/$($created.Task1Id)/start" | Out-Null

    $deviceOnline = Wait-Until -TimeoutSec $PollTimeoutSec -IntervalSec 3 -Message "设备 $EdgeCode online" -Condition {
        $list = Invoke-Api -Method Get -Path "/api/v1/video/edge/list?code=$EdgeCode&page_no=1&page_size=50"
        $item = @($list.items) | Where-Object { $_.code -eq $EdgeCode } | Select-Object -First 1
        return ($item -and $item.status -eq "online")
    }
    [void](Assert-That $deviceOnline "断言1: 设备 status=online")

    Write-E2E "Step 3b: 等待 Agent 任务 running 并核对云端任务 RUNNING" -Level STEP
    $agentRunning = Wait-Until -TimeoutSec $PollTimeoutSec -IntervalSec 3 -Message "Agent 任务 $($created.Task1Id) running=true" -Condition {
        $tasks = Invoke-AgentApi -Method Get -Path "/api/v1/tasks"
        $t = @($tasks.items) | Where-Object { $_.task_id -eq "$($created.Task1Id)" } | Select-Object -First 1
        return ($t -and $t.running -eq $true)
    }
    [void](Assert-That $agentRunning "断言2: Agent 任务 running=true")

    $cloudRunning = Wait-Until -TimeoutSec 30 -IntervalSec 3 -Message "云端任务#1 status=RUNNING" -Condition {
        $list = Invoke-Api -Method Get -Path "/api/v1/video/algorithm/task/list?page_no=1&page_size=100"
        $t = @($list.items) | Where-Object { $_.id -eq $created.Task1Id } | Select-Object -First 1
        return ($t -and $t.status -eq "RUNNING")
    }
    [void](Assert-That $cloudRunning "断言2b: 云端任务#1 status=RUNNING")

    Write-E2E "Step 3c: 等待 INTRUSION 告警落库" -Level STEP
    $intrusionAlarm = Wait-Until -TimeoutSec $AlarmWaitSec -IntervalSec 5 -Message "camera=$($created.CameraId) 出现 algorithm_type=INTRUSION 告警" -Condition {
        $alarms = Get-AlarmItems -CameraId $created.CameraId
        $hit = @($alarms) | Where-Object {
            $_.alarm_type -eq "INTRUSION" -or ($_.ai_result -and $_.ai_result.algorithm_type -eq "INTRUSION")
        } | Select-Object -First 1
        if ($hit) { $script:SampleAlarm = $hit; return $true }
        return $false
    }
    [void](Assert-That $intrusionAlarm "断言3: 出现 algorithm_type=INTRUSION 告警")
    if ($intrusionAlarm -and $script:SampleAlarm) {
        Write-E2E "告警样本: id=$($script:SampleAlarm.id) alarm_type=$($script:SampleAlarm.alarm_type) snapshot_url=$($script:SampleAlarm.snapshot_url)"
    }

    Write-E2E "Step 3d: 断言告警 snapshot_url 非空" -Level STEP
    $snapOk = $false
    if ($script:SampleAlarm) {
        $snapOk = -not [string]::IsNullOrWhiteSpace($script:SampleAlarm.snapshot_url)
    }
    [void](Assert-That $snapOk "断言4: 告警 snapshot_url 非空（内联快照已落 DETECTIONS_DIR）")

    Write-E2E "Step 3e: 重复 event_id 去重断言" -Level STEP
    $dedupTaskId = 999999  # 哨兵 task_id，用于把去重测试的告警与真实 Agent 告警隔离
    $dedupEventId = "e2e-dedup-$($script:RunId)"
    $dedupCountBefore = @(Get-AlarmItems -CameraId $created.CameraId -PageSize 100 | Where-Object { $_.ai_result -and $_.ai_result.task_id -eq $dedupTaskId }).Count

    $dedupPayload = @{
        event_id       = $dedupEventId
        edge_code      = $EdgeCode
        camera_id      = $created.CameraId
        task_id        = $dedupTaskId
        algorithm_type = "INTRUSION"
        ts             = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss.fffZ")
        detections     = @(
            @{ label = "person"; label_id = 0; confidence = 0.9; bbox = @{ x = 0.4; y = 0.4; width = 0.2; height = 0.2 } }
        )
    }

    if ($Transport -eq "mqtt") {
        if ($SkipBroker) {
            Add-Warning "断言5: 未启动 Broker（-SkipBroker），跳过 MQTT 重复 event_id 去重断言"
        } else {
            $topic = "$MqttTopicPrefix/$EdgeCode/camera/$($created.CameraId)/detect"
            $payloadJson = $dedupPayload | ConvertTo-Json -Depth 20 -Compress
            # 通过 Broker 容器内 mosquitto_pub 连续投递两条相同 event_id 的消息
            foreach ($i in 1..2) {
                docker exec $BrokerName mosquitto_pub -h 127.0.0.1 -p 1883 -t $topic -m $payloadJson | Out-Null
            }
            Start-Sleep -Seconds 8
            $dedupCountAfter = @(Get-AlarmItems -CameraId $created.CameraId -PageSize 100 | Where-Object { $_.ai_result -and $_.ai_result.task_id -eq $dedupTaskId }).Count
            $delta = $dedupCountAfter - $dedupCountBefore
            [void](Assert-That ($delta -eq 1) "断言5: 重复 event_id 只新建 1 条告警（新增=$delta）")
        }
    } else {
        # HTTP 通道：后端 detection/callback 已按 event_id 模块级去重（algorithm/controller.py 的 _CALLBACK_DEDUP）。
        # 仅统计哨兵 task_id 的告警，避免 Task#1 的真实 Agent 告警污染增量。
        $before = @(Get-AlarmItems -CameraId $created.CameraId -PageSize 100 | Where-Object { $_.ai_result -and $_.ai_result.task_id -eq $dedupTaskId }).Count
        $callbackFailed = $false
        foreach ($i in 1..2) {
            try {
                Invoke-RestMethod -Method Post `
                    -Uri "$($script:ApiBase)/api/v1/video/algorithm/detection/callback" `
                    -Headers @{ Authorization = "Bearer $InferenceCallbackToken"; "X-Forwarded-For" = "127.0.0.1" } `
                    -ContentType "application/json" -Body ($dedupPayload | ConvertTo-Json -Depth 20 -Compress) | Out-Null
            } catch {
                Add-Warning "断言5(HTTP): 重复事件投递失败（检查 -InferenceCallbackToken 是否与后端 INFERENCE_CALLBACK_TOKEN 一致）: $_"
                $callbackFailed = $true
                break
            }
        }
        if (-not $callbackFailed) {
            Start-Sleep -Seconds 5
            $after = @(Get-AlarmItems -CameraId $created.CameraId -PageSize 100 | Where-Object { $_.ai_result -and $_.ai_result.task_id -eq $dedupTaskId }).Count
            $delta = $after - $before
            [void](Assert-That ($delta -eq 1) "断言5(HTTP): 重复 event_id 只新建 1 条告警（新增=$delta）")
        }
    }

    Write-E2E "Step 4a: 时段（schedule）断言 —— 窗口外任务不产生告警" -Level STEP
    $task2Body = @{
        camera_id      = $created.CameraId
        algorithm_id   = $created.AlgorithmId
        edge_device_id = $created.EdgeId
        stream_type    = "SUB"
        sensitivity    = 50
        detect_region  = @{ points = @(@(0.2, 0.2), @(0.8, 0.2), @(0.8, 0.8), @(0.2, 0.8)) }
        schedule_json  = @{ slots = @(@{ day = $otherIso; start = 0; end = 24 }) }
    }
    $task2 = Invoke-Api -Method Post -Path "/api/v1/video/algorithm/task/create" -Body $task2Body
    $created.Task2Id = $task2.id
    Write-E2E "AlgorithmTask#2 id=$($created.Task2Id) schedule=明天($otherIso) 全天（当前窗口外）"
    Invoke-Api -Method Post -Path "/api/v1/video/algorithm/task/$($created.Task2Id)/start" | Out-Null

    Write-E2E "等待 $ScheduleSettleSec s 让 Agent schedule_loop 停掉窗口外任务…"
    Start-Sleep -Seconds $ScheduleSettleSec

    $task2NotRunning = $false
    try {
        $tasks = Invoke-AgentApi -Method Get -Path "/api/v1/tasks"
        $t2 = @($tasks.items) | Where-Object { $_.task_id -eq "$($created.Task2Id)" } | Select-Object -First 1
        $task2NotRunning = ($t2 -and $t2.running -eq $false)
        if (-not $t2) { Add-Warning "Agent 上找不到任务#2（可能已被 schedule 直接清理）" }
    } catch {
        Add-Warning "查询 Agent 任务#2 状态失败: $_"
    }
    [void](Assert-That $task2NotRunning "断言6: 窗口外任务在 Agent 侧停止（running=false）")

    $task2Alarms = @(Get-AlarmItems -CameraId $created.CameraId -PageSize 100 | Where-Object { $_.ai_result -and $_.ai_result.task_id -eq $created.Task2Id }).Count
    [void](Assert-That ($task2Alarms -eq 0) "断言6b: 窗口外任务未产生告警（task#2 告警数=$task2Alarms）")

    Write-E2E "Step 4b: 停止任务#1 并断言 Agent 同步" -Level STEP
    Invoke-Api -Method Post -Path "/api/v1/video/algorithm/task/$($created.Task1Id)/stop" | Out-Null
    $agentStopped = Wait-Until -TimeoutSec 30 -IntervalSec 2 -Message "Agent 任务#1 running=false" -Condition {
        $tasks = Invoke-AgentApi -Method Get -Path "/api/v1/tasks"
        $t = @($tasks.items) | Where-Object { $_.task_id -eq "$($created.Task1Id)" } | Select-Object -First 1
        return ($t -and $t.running -eq $false)
    }
    [void](Assert-That $agentStopped "断言7: stop 后 Agent 任务#1 running=false")

    $cloudStopped = Wait-Until -TimeoutSec 30 -IntervalSec 2 -Message "云端任务#1 status=STOPPED" -Condition {
        $list = Invoke-Api -Method Get -Path "/api/v1/video/algorithm/task/list?page_no=1&page_size=100"
        $t = @($list.items) | Where-Object { $_.id -eq $created.Task1Id } | Select-Object -First 1
        return ($t -and $t.status -eq "STOPPED")
    }
    [void](Assert-That $cloudStopped "断言7b: stop 后云端任务#1 status=STOPPED")

    Write-E2E "Step 4c: 删除任务并断言 Agent 同步删除" -Level STEP
    $deleteIds = @($created.Task1Id, $created.Task2Id)
    Invoke-Api -Method Delete -Path "/api/v1/video/algorithm/task/delete" -Body ($deleteIds | ConvertTo-Json -AsArray) | Out-Null

    $agentDeleted = Wait-Until -TimeoutSec 30 -IntervalSec 2 -Message "Agent 任务#1 已删除（GET 404）" -Condition {
        $r = Invoke-AgentApi -Method Get -Path "/api/v1/tasks/$($created.Task1Id)" -AllowNotFound
        return ($null -eq $r)
    }
    [void](Assert-That $agentDeleted "断言8: delete 后 Agent 任务#1 已移除（GET 404）")

    $cloudDeleted = $false
    try {
        $list = Invoke-Api -Method Get -Path "/api/v1/video/algorithm/task/list?page_no=1&page_size=100"
        $still = @($list.items) | Where-Object { $_.id -eq $created.Task1Id }
        $cloudDeleted = ($still.Count -eq 0)
    } catch { $cloudDeleted = $false }
    [void](Assert-That $cloudDeleted "断言8b: delete 后云端任务列表不再包含任务#1")
    $created.Task1Id = $null
    $created.Task2Id = $null

    Write-E2E "Step 6: 证据与 DB 查询" -Level STEP
    Write-E2E "告警列表 API: GET $($script:ApiBase)/api/v1/video/alarm/record/list?camera_id=$($created.CameraId)"
    Write-E2E "DB 查询示例:"
    Write-E2E ('  psql ... -c "select id,camera_id,alarm_type,status,snapshot_path,' +
        "ai_result->>'task_id' as task_id, alarm_time from alarm_record " +
        'where camera_id=' + $created.CameraId + ' order by id desc limit 20;"')
    Write-E2E "Agent 日志: $($script:AgentStdout) / $($script:AgentStderr)"
    if ($script:AgentDataDir) { Write-E2E "Agent 事件落盘目录: $($script:AgentDataDir)" }
}
catch {
    Add-Failure "执行中断: $($_.Exception.Message)"
    if ($_.ScriptStackTrace) { Write-E2E $_.ScriptStackTrace -Level INFO }
}
finally {
    Write-E2E "Step 7: 清理" -Level STEP
    Stop-Agent
    Stop-Broker

    if (-not $KeepData -and $script:Token) {
        try {
            if ($created.AlgorithmId) {
                Invoke-Api -Method Delete -Path "/api/v1/video/algorithm/delete" -Body (@($created.AlgorithmId) | ConvertTo-Json -AsArray) | Out-Null
                Write-E2E "已清理 Algorithm id=$($created.AlgorithmId)"
            }
            if ($created.CameraId) {
                Invoke-Api -Method Delete -Path "/api/v1/video/camera/delete" -Body (@($created.CameraId) | ConvertTo-Json -AsArray) | Out-Null
                Write-E2E "已清理 Camera id=$($created.CameraId)"
            }
            if ($script:CreatedEdge -and $created.EdgeId) {
                Invoke-Api -Method Delete -Path "/api/v1/video/edge/delete" -Body (@($created.EdgeId) | ConvertTo-Json -AsArray) | Out-Null
                Write-E2E "已清理 EdgeDevice id=$($created.EdgeId)"
            }
        } catch {
            Add-Warning "清理播种数据失败（可手动清理）: $_"
        }
    } elseif ($KeepData) {
        Write-E2E "按 -KeepData 保留播种数据（Algorithm/Camera/Edge=$($created.EdgeId)）"
    }

    Write-E2E "==================== 结果汇总 ====================" -Level STEP
    if ($script:Failures.Count -eq 0) {
        Write-E2E "全部断言通过（$($script:Warnings.Count) 条警告）" -Level OK
    } else {
        Write-E2E "断言失败 $($script:Failures.Count) 条:" -Level FAIL
        foreach ($f in $script:Failures) { Write-E2E "  - $f" -Level FAIL }
    }
    if ($script:Warnings.Count -gt 0) {
        Write-E2E "警告 $($script:Warnings.Count) 条:" -Level WARN
        foreach ($w in $script:Warnings) { Write-E2E "  - $w" -Level WARN }
    }
    Write-E2E "证据目录: $($script:TmpDir)"

    if ($script:Failures.Count -gt 0) { exit 1 } else { exit 0 }
}
