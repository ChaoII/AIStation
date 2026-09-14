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
    OCR_TEXT 场景建议把静态图（如 ocr2.jpg）用 FFmpeg 循环成 mp4 后传入本参数。
    ABSENT 场景必须传入「人先出现、随后离开画面」的视频：Agent 需先由含目标的事件建立
    last_seen 历史，静默期心跳触发的 absence 才会命中（只有空白画面会因无历史而不命中）。

.PARAMETER ModelPath
    算法检测模型文件路径。支持本地绝对路径（同机 Agent 直接读取）或 http(s)/s3 URL（Agent 下载）。
    当 `-Scene PED_ATTR` 且未显式传入本参数时，自动改用 zhgd_det.onnx；
    当 `-Scene LPR` 时自动改用 yolov5plate.onnx；
    当 `-Scene FACE_DET` 时自动改用 -FaceModelPath（scrfd_2.5g_bnkps_shape640x640.onnx）；
    当 `-Scene ABSENT` 时自动改用 -DetModelPath（yolo11n_nms.onnx）。

.PARAMETER ClsModelPath
    PED_ATTR 属性分类（cls）模型路径，写入 preset_params.cls_path；仅 `-Scene PED_ATTR` 使用。
    OCR_TEXT 场景未显式传入时自动改用 ppocrv6_tiny\cls_infer.onnx。

.PARAMETER RecModelPath
    OCR_TEXT 文本识别（rec）模型路径，写入 preset_params.rec_path；仅 `-Scene OCR_TEXT` 使用。

.PARAMETER DictPath
    OCR_TEXT 字符字典路径，写入 preset_params.dict_path；仅 `-Scene OCR_TEXT` 使用。

.PARAMETER PlateRecModelPath
    车牌识别（rec）模型路径，写入 preset_params.rec_path；仅 `-Scene LPR` 使用。
    默认取 plate_recognition_color.onnx（与 yolov5plate.onnx 检测模型配套）。

.PARAMETER FaceModelPath
    人脸检测（face_detection）模型路径，写入 Algorithm.model_path；仅 `-Scene FACE_DET` 使用。
    默认取 seetaface\scrfd_2.5g_bnkps_shape640x640.onnx（SCRFD，输入 640x640、ORT/CPU）。

.PARAMETER DetModelPath
    ABSENT 离岗场景检测模型路径，写入 Algorithm.model_path；仅 `-Scene ABSENT` 使用。
    默认复用各检测场景通用的 yolo11n_nms.onnx（单 det pipeline，ORT/CPU）。

.PARAMETER Scene
    场景模式：
      - INTRUSION（默认）：单 det 模型，断言 algorithm_type=INTRUSION 告警；
      - DET_ZONE：单 det 检测场景（区域入侵），scene_type=DET_ZONE，断言
        algorithm_type=DET_ZONE 告警（可配合 -Tracking 验证跟踪）；
      - PED_ATTR：det+cls 行人属性 pipeline，播种属性规则并断言
        objects[].attributes 已透传到 ai_result.detections[].attributes。
      - OCR_TEXT：det+cls+rec+dict 通用文本 pipeline，播种 text_match 规则并断言
        ai_result.detections[].text 非空（模型/字典默认取 ppocrv6_tiny）。
      - LPR：det+rec 车牌识别 pipeline，播种 text_match 规则并断言
        ai_result.detections[].text 非空（模型默认取 yolov5plate + plate_recognition_color）。
      - FACE_DET：单 face_detection（SCRFD）模型管线，播种 object_present 规则并断言
        algorithm_type=FACE_DET 告警且 ai_result.detections[] 非空（模型默认取 -FaceModelPath）。
      - ABSENT：单 det 模型 + absence 时序规则（label=person、gap_sec=10、interval_seconds=30），
        断言 algorithm_type=ABSENT 告警、ai_result.detections 为空（由 Agent 静默期心跳的空检测
        事件驱动），且 interval_seconds 内不重复告警（容差 1 条）。视频需「人先出现再离开画面」，
        否则 last_seen 无历史，absence 永不命中；检测模型默认取 -DetModelPath。

.PARAMETER DecoderHwAccel
    算法 runtime_config.decoder.hw_accel，默认 none（CPU 解码，匹配 -ModelPath 的 ORT/CPU 后端）。
    Agent 侧可选值：auto/none/cuda/vaapi/qsv/sophgo（见 ModelDeploy config.hpp）。
    若模型走 GPU（backend=cuda）则需改为 cuda，否则 CPU 后端会拒绝 GPU NV12。

.PARAMETER Tracking
    启用算法 runtime_config.tracking={enabled=true, algorithm=bytetrack}，让 Agent 对检测目标
    做 ByteTrack 跟踪，并在事件 objects[].track_id 回填稳定轨迹号（缺省关闭）。
    仅对检测类场景（DET_ZONE/INTRUSION）有意义；启用后脚本追加断言：
    告警 ai_result.detections[].track_id 至少一条出现且 >= 0。

.PARAMETER EdgeCode
    边缘设备编码；必须与 Agent `--edge-code` 一致（心跳按 code upsert）。
    留空（默认）时按 RunId 生成运行时唯一编码 `edge-e2e-<RunId>`，避免软删后同码无法复用。

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
    [string]$ClsModelPath = "E:\CLionProjects\ModelDeploy\test_data\test_models\onnx\zhgd_ml.onnx",
    [string]$RecModelPath = "E:\CLionProjects\ModelDeploy\test_data\test_models\onnx\ocr\ppocrv6_tiny\rec_infer.onnx",
    [string]$DictPath = "E:\CLionProjects\ModelDeploy\test_data\ppocrv6_tiny_dict.txt",
    [string]$PlateRecModelPath = "E:\CLionProjects\ModelDeploy\test_data\test_models\onnx\plate_recognition_color.onnx",
    [string]$FaceModelPath = "E:\CLionProjects\ModelDeploy\test_data\test_models\onnx\seetaface\scrfd_2.5g_bnkps_shape640x640.onnx",
    [string]$DetModelPath = "E:\CLionProjects\ModelDeploy\test_data\test_models\onnx\yolo11n\yolo11n_nms.onnx",
    [ValidateSet("INTRUSION", "DET_ZONE", "PED_ATTR", "OCR_TEXT", "LPR", "FACE_DET", "ABSENT")]
    [string]$Scene = "INTRUSION",
    [string]$DecoderHwAccel = "none",
    [switch]$Tracking,

    [string]$EdgeCode = "",
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
        "--edge-code", $effectiveEdgeCode,
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
    # PED_ATTR/OCR_TEXT/LPR/FACE_DET/ABSENT 场景要求设备声明对应模型族，
    # 否则能力校验会拒绝下发；其余场景保持仅 det。
    $capModelFamilies = @("det")
    if ($Scene -eq "ABSENT") {
        # 场景目录 ABSENT 要求模型族 det（scene/catalog.py），与默认值一致，此处显式声明便于对照
        $capModelFamilies = @("det")
    } elseif ($Scene -eq "PED_ATTR") {
        $capModelFamilies = @("det", "pedestrian_attribute")
    } elseif ($Scene -eq "OCR_TEXT") {
        $capModelFamilies = @("ocr")
    } elseif ($Scene -eq "LPR") {
        # 车牌场景能力校验只要求 lpr 模型族（见 scene/catalog.py 的 LPR 定义）
        $capModelFamilies = @("lpr")
    } elseif ($Scene -eq "FACE_DET") {
        # 场景目录 FACE_DET 要求模型族 face_detection（scene/catalog.py），
        # 而 Agent 心跳上报的人脸族名为 face；两者都播种以兼容（心跳随后覆盖为上报值）。
        $capModelFamilies = @("face_detection", "face")
    }
    $createBody = @{
        name         = "E2E 边缘设备 $effectiveEdgeCode"
        code         = $effectiveEdgeCode
        control_url  = $script:AgentControlUrl
        secret       = $Secret
        capabilities = @{
            model_families = $capModelFamilies
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
        $list = Invoke-Api -Method Get -Path "/api/v1/video/edge/list?code=$effectiveEdgeCode&page_no=1&page_size=50"
        $item = @($list.items) | Where-Object { $_.code -eq $effectiveEdgeCode } | Select-Object -First 1
        if (-not $item) { throw "边缘设备不存在且无法创建: $effectiveEdgeCode" }
        # 复用已有能力清单，但场景要求的模型族必须补齐（PED_ATTR 需 pedestrian_attribute）
        $updateCaps = if ($item.capabilities) { $item.capabilities } else { @{} }
        $updateCaps.model_families = $capModelFamilies
        $updateBody = @{
            name         = $item.name
            code         = $effectiveEdgeCode
            control_url  = $script:AgentControlUrl
            secret       = $Secret
            capabilities = $updateCaps
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
# 显式 -EdgeCode 优先；否则按 RunId 生成运行时唯一编码，避免软删后同码无法复用（对齐 Agent 的 per-edge 身份）
$effectiveEdgeCode = if ($EdgeCode) { $EdgeCode } else { "edge-e2e-$($script:RunId)" }
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

# 场景模式：PED_ATTR 使用 det+cls 双模型（zhgd_det + zhgd_ml）与属性告警规则；
# OCR_TEXT 使用 det+cls+rec+dict 四件套（ppocrv6_tiny）与文本规则；
# LPR 使用 det+rec 双模型（yolov5plate + plate_recognition_color）与文本规则；
# FACE_DET 使用单 face_detection 模型（scrfd）与 object_present 规则；
# ABSENT 使用单 det 模型（yolo11n_nms）与 absence 时序规则（依赖 Agent 空事件心跳）。
# 未显式传入对应模型参数时，按场景切换到各自默认模型。
$effectiveAlgorithmType = switch ($Scene) {
    "DET_ZONE" { "DET_ZONE" }
    "PED_ATTR" { "PED_ATTR" }
    "OCR_TEXT" { "OCR_TEXT" }
    "LPR"      { "LPR" }
    "FACE_DET" { "FACE_DET" }
    "ABSENT"   { "ABSENT" }
    default    { "INTRUSION" }
}
$pedAttrDetDefault = "E:\CLionProjects\ModelDeploy\test_data\test_models\onnx\zhgd_det.onnx"
$ocrDetDefault = "E:\CLionProjects\ModelDeploy\test_data\test_models\onnx\ocr\ppocrv6_tiny\det_infer.onnx"
$ocrClsDefault = "E:\CLionProjects\ModelDeploy\test_data\test_models\onnx\ocr\ppocrv6_tiny\cls_infer.onnx"
$lprDetDefault = "E:\CLionProjects\ModelDeploy\test_data\test_models\onnx\yolov5plate.onnx"
$effectiveModelPath = $ModelPath
if (-not $PSBoundParameters.ContainsKey("ModelPath")) {
    if ($Scene -eq "PED_ATTR") { $effectiveModelPath = $pedAttrDetDefault }
    elseif ($Scene -eq "OCR_TEXT") { $effectiveModelPath = $ocrDetDefault }
    elseif ($Scene -eq "LPR") { $effectiveModelPath = $lprDetDefault }
    elseif ($Scene -eq "FACE_DET") { $effectiveModelPath = $FaceModelPath }
    elseif ($Scene -eq "ABSENT") { $effectiveModelPath = $DetModelPath }
}
$effectiveClsPath = $ClsModelPath
if ($Scene -eq "OCR_TEXT" -and -not $PSBoundParameters.ContainsKey("ClsModelPath")) {
    $effectiveClsPath = $ocrClsDefault
}
# LPR 的识别（rec）模型默认取 plate_recognition_color.onnx（车牌专用）
$effectiveRecPath = $RecModelPath
if ($Scene -eq "LPR") { $effectiveRecPath = $PlateRecModelPath }

# 已创建资源 ID，便于清理
$created = @{ AlgorithmId = $null; CameraId = $null; EdgeId = $null; Task1Id = $null; Task2Id = $null; RuleId = $null }

Write-E2E "==== AIStation 云边 Agent 真机 E2E（transport=$Transport scene=$Scene） ===="
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
    Write-E2E "EdgeDevice id=$($created.EdgeId) code=$effectiveEdgeCode" -Level OK

    Write-E2E "Step 1c: 启动边缘 Agent（先播种设备，避免心跳抢先 upsert 丢失 control_url/secret）" -Level STEP
    Start-Agent
    Write-E2E "Agent 控制面就绪: $($script:AgentControlUrl)" -Level OK

    Write-E2E "Step 2: 播种 Algorithm / Camera / AlgorithmTask（scene=$Scene）" -Level STEP
    $algoCode = New-UniqueCode $effectiveAlgorithmType
    $algoName = switch ($Scene) {
        "DET_ZONE" { "E2E 区域入侵 $($script:RunId)" }
        "PED_ATTR" { "E2E 行人属性 $($script:RunId)" }
        "OCR_TEXT" { "E2E 文本识别 $($script:RunId)" }
        "LPR"      { "E2E 车牌识别 $($script:RunId)" }
        "FACE_DET" { "E2E 人脸检测 $($script:RunId)" }
        "ABSENT"   { "E2E 离岗检测 $($script:RunId)" }
        default    { "E2E 闯入检测 $($script:RunId)" }
    }
    $algoBody = @{
        name            = $algoName
        code            = $algoCode
        algorithm_type  = $effectiveAlgorithmType
        model_path      = $effectiveModelPath
        runtime_config  = @{
            backend  = "ort"
            device   = "cpu"
            decoder  = @{ hw_accel = $DecoderHwAccel; device_only = $false; rtsp_transport = "tcp" }
        }
        preset_params   = @{ confidence_threshold = 0.4; input_size = @(640, 640) }
    }
    if ($Scene -eq "PED_ATTR") {
        # scene_type 触发编排编译 pedestrian_attribute（det+cls）pipeline
        $algoBody.scene_type = "PED_ATTR"
        $algoBody.preset_params = @{
            cls_path             = $effectiveClsPath
            attributes           = @("safety_helmet", "reflective_vest", "safety_rope", "work_uniform")
            confidence_threshold = 0.4
            cls_threshold        = 0.5
        }
    } elseif ($Scene -eq "OCR_TEXT") {
        # scene_type 触发编排编译 ocr（det+cls+rec+dict）pipeline；
        # runtime_config 按 OCR/ORT-CPU 契约显式给定（不做 RTSP transport 覆盖）
        $algoBody.scene_type = "OCR_TEXT"
        $algoBody.runtime_config = @{
            backend  = "ort"
            device   = "cpu"
            decoder  = @{ hw_accel = $DecoderHwAccel; device_only = $false }
        }
        $algoBody.preset_params = @{
            cls_path             = $effectiveClsPath
            rec_path             = $RecModelPath
            dict_path            = $DictPath
            input_size           = @(960, 960)
            confidence_threshold = 0.3
        }
    } elseif ($Scene -eq "LPR") {
        # scene_type 触发编排编译 lpr（det+rec）pipeline；不涉及 cls/dict；
        # runtime_config 按车牌/ORT-CPU 契约显式给定（不做 RTSP transport 覆盖）
        $algoBody.scene_type = "LPR"
        $algoBody.runtime_config = @{
            backend  = "ort"
            device   = "cpu"
            decoder  = @{ hw_accel = $DecoderHwAccel; device_only = $false }
        }
        $algoBody.preset_params = @{
            rec_path             = $effectiveRecPath
            input_size           = @(640, 640)
            confidence_threshold = 0.25
        }
    } elseif ($Scene -eq "FACE_DET") {
        # scene_type 触发编排编译 face_detection（单模型）pipeline；
        # runtime_config 按人脸/ORT-CPU 契约显式给定（不做 RTSP transport 覆盖）
        $algoBody.scene_type = "FACE_DET"
        $algoBody.runtime_config = @{
            backend  = "ort"
            device   = "cpu"
            decoder  = @{ hw_accel = $DecoderHwAccel; device_only = $false }
        }
        $algoBody.preset_params = @{
            input_size           = @(640, 640)
            confidence_threshold = 0.3
        }
    } elseif ($Scene -eq "ABSENT") {
        # scene_type 触发编排编译检测（det）pipeline；
        # runtime_config 按检测/ORT-CPU 契约显式给定（不做 RTSP transport 覆盖）
        $algoBody.scene_type = "ABSENT"
        $algoBody.runtime_config = @{
            backend  = "ort"
            device   = "cpu"
            decoder  = @{ hw_accel = $DecoderHwAccel; device_only = $false }
        }
        $algoBody.preset_params = @{
            confidence_threshold = 0.3
        }
    } elseif ($Scene -eq "DET_ZONE") {
        # 检测场景：显式声明 scene_type，编排按场景目录（model_families=["det"]）解析
        $algoBody.scene_type = "DET_ZONE"
    }
    if ($Tracking) {
        # 跟踪开关：写入算法 runtime_config.tracking，编排透传为 Agent TaskConfig.tracking
        $algoBody.runtime_config["tracking"] = @{ enabled = $true; algorithm = "bytetrack" }
        Write-E2E "跟踪已启用: runtime_config.tracking={enabled=true, algorithm=bytetrack}"
    }
    $algo = Invoke-Api -Method Post -Path "/api/v1/video/algorithm/create" -Body $algoBody
    $created.AlgorithmId = $algo.id
    Write-E2E "Algorithm id=$($created.AlgorithmId) code=$algoCode model=$effectiveModelPath" -Level OK

    $cameraBody = @{
        name        = "E2E 摄像机 $($script:RunId)"
        rtsp_url_sub = $VideoPath
    }
    $camera = Invoke-Api -Method Post -Path "/api/v1/video/camera/create" -Body $cameraBody
    $created.CameraId = $camera.id
    Write-E2E "Camera id=$($created.CameraId) rtsp_url_sub=$VideoPath" -Level OK

    if ($Scene -eq "PED_ATTR") {
        # 链路验证规则：work_uniform 分数存在即 >-1 命中，用于确认属性从 objects 透传到 detections
        $ruleBody = @{
            name       = "E2E 工作服属性规则 $($script:RunId)"
            camera_id  = $created.CameraId
            alarm_type = "PED_ATTR"
            severity   = "WARNING"
            conditions = @{
                op       = "and"
                children = @(
                    @{ subject = "attribute"; field = "work_uniform"; op = "gt"; value = -1.0 }
                )
            }
            status     = $true
        }
        $rule = Invoke-Api -Method Post -Path "/api/v1/video/alarm/rule/create" -Body $ruleBody
        $created.RuleId = $rule.id
        Write-E2E "AlarmRule id=$($created.RuleId) alarm_type=PED_ATTR conditions=work_uniform>-1（属性存在即命中，链路验证）" -Level OK
    } elseif ($Scene -eq "OCR_TEXT") {
        # 链路验证规则：regex=".+" 命中任意非空识别文本，用于确认 text 从检测框透传到 detections
        $ruleBody = @{
            name       = "E2E 文本规则 $($script:RunId)"
            camera_id  = $created.CameraId
            alarm_type = "OCR_TEXT"
            severity   = "WARNING"
            conditions = @{
                op       = "and"
                children = @(
                    @{ subject = "text_match"; regex = ".+" }
                )
            }
            status     = $true
        }
        $rule = Invoke-Api -Method Post -Path "/api/v1/video/alarm/rule/create" -Body $ruleBody
        $created.RuleId = $rule.id
        Write-E2E "AlarmRule id=$($created.RuleId) alarm_type=OCR_TEXT conditions=text_match(.+)（任意文本命中，链路验证）" -Level OK
    } elseif ($Scene -eq "LPR") {
        # 链路验证规则：regex=".+" 命中任意非空车牌文本，用于确认 text 从检测框透传到 detections
        $ruleBody = @{
            name       = "E2E 车牌规则 $($script:RunId)"
            camera_id  = $created.CameraId
            alarm_type = "LPR"
            severity   = "WARNING"
            conditions = @{
                op       = "and"
                children = @(
                    @{ subject = "text_match"; regex = ".+" }
                )
            }
            status     = $true
        }
        $rule = Invoke-Api -Method Post -Path "/api/v1/video/alarm/rule/create" -Body $ruleBody
        $created.RuleId = $rule.id
        Write-E2E "AlarmRule id=$($created.RuleId) alarm_type=LPR conditions=text_match(.+)（任意车牌文本命中，链路验证）" -Level OK
    } elseif ($Scene -eq "FACE_DET") {
        # 链路验证规则：object_present 不限定 label（人脸模型 labels 为空且随模型而异，
        # 限定 "face" 可能漏命中），只要出现任意人脸框即命中，用于验证整条链路。
        $ruleBody = @{
            name       = "E2E 人脸规则 $($script:RunId)"
            camera_id  = $created.CameraId
            alarm_type = "FACE_DET"
            severity   = "WARNING"
            conditions = @{
                op       = "and"
                children = @(
                    @{ subject = "object_present" }
                )
            }
            status     = $true
        }
        $rule = Invoke-Api -Method Post -Path "/api/v1/video/alarm/rule/create" -Body $ruleBody
        $created.RuleId = $rule.id
        Write-E2E "AlarmRule id=$($created.RuleId) alarm_type=FACE_DET conditions=object_present（出现人脸框即命中，链路验证）" -Level OK
    } elseif ($Scene -eq "ABSENT") {
        # absence 时序规则：最近一次 person 出现后静默 >= gap_sec=10s 命中；
        # interval_seconds=30 为告警防抖窗口（心跳每 5s 报一次空检测，靠它避免重复告警）
        $ruleBody = @{
            name             = "E2E 离岗规则 $($script:RunId)"
            camera_id        = $created.CameraId
            alarm_type       = "ABSENT"
            severity         = "WARNING"
            interval_seconds = 30
            conditions       = @{
                op       = "and"
                children = @(
                    @{ subject = "absence"; label = "person"; gap_sec = 10 }
                )
            }
            status           = $true
        }
        $rule = Invoke-Api -Method Post -Path "/api/v1/video/alarm/rule/create" -Body $ruleBody
        $created.RuleId = $rule.id
        Write-E2E "AlarmRule id=$($created.RuleId) alarm_type=ABSENT conditions=absence(person,gap_sec=10) interval_seconds=30（静默超时即命中，链路验证）" -Level OK
    }

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

    $deviceOnline = Wait-Until -TimeoutSec $PollTimeoutSec -IntervalSec 3 -Message "设备 $effectiveEdgeCode online" -Condition {
        $list = Invoke-Api -Method Get -Path "/api/v1/video/edge/list?code=$effectiveEdgeCode&page_no=1&page_size=50"
        $item = @($list.items) | Where-Object { $_.code -eq $effectiveEdgeCode } | Select-Object -First 1
        return ($item -and $item.status -eq "online")
    }
    [void](Assert-That $deviceOnline "断言1: 设备 status=online")

    if ($Scene -eq "LPR") {
        # 断言设备能力清单含 lpr 模型族（下发前能力校验的前提；Agent 心跳会上报含 lpr）
        Write-E2E "Step 3a2: 断言设备能力含 lpr 模型族" -Level STEP
        $edgeList = Invoke-Api -Method Get -Path "/api/v1/video/edge/list?code=$effectiveEdgeCode&page_no=1&page_size=50"
        $edgeItem = @($edgeList.items) | Where-Object { $_.code -eq $effectiveEdgeCode } | Select-Object -First 1
        $families = @()
        if ($edgeItem -and $edgeItem.capabilities -and $edgeItem.capabilities.model_families) {
            $families = @($edgeItem.capabilities.model_families)
        }
        $lprCapOk = ($families -contains "lpr")
        [void](Assert-That $lprCapOk "断言1b: 设备 capabilities.model_families 含 lpr（实际: $($families -join ', ')）")
    }

    if ($Scene -eq "FACE_DET") {
        # 断言设备能力清单含 face 模型族（Agent 心跳上报的人脸族名；
        # 场景目录 FACE_DET 的能力要求为 face_detection）
        Write-E2E "Step 3a2: 断言设备能力含 face 模型族" -Level STEP
        $edgeList = Invoke-Api -Method Get -Path "/api/v1/video/edge/list?code=$effectiveEdgeCode&page_no=1&page_size=50"
        $edgeItem = @($edgeList.items) | Where-Object { $_.code -eq $effectiveEdgeCode } | Select-Object -First 1
        $families = @()
        if ($edgeItem -and $edgeItem.capabilities -and $edgeItem.capabilities.model_families) {
            $families = @($edgeItem.capabilities.model_families)
        }
        $faceCapOk = ($families -contains "face")
        [void](Assert-That $faceCapOk "断言1b: 设备 capabilities.model_families 含 face（实际: $($families -join ', ')）")
    }

    if ($Scene -eq "ABSENT") {
        # 断言设备能力清单含 det 模型族（场景目录 ABSENT 的能力要求为 det）
        Write-E2E "Step 3a2: 断言设备能力含 det 模型族" -Level STEP
        $edgeList = Invoke-Api -Method Get -Path "/api/v1/video/edge/list?code=$effectiveEdgeCode&page_no=1&page_size=50"
        $edgeItem = @($edgeList.items) | Where-Object { $_.code -eq $effectiveEdgeCode } | Select-Object -First 1
        $families = @()
        if ($edgeItem -and $edgeItem.capabilities -and $edgeItem.capabilities.model_families) {
            $families = @($edgeItem.capabilities.model_families)
        }
        $detCapOk = ($families -contains "det")
        [void](Assert-That $detCapOk "断言1b: 设备 capabilities.model_families 含 det（实际: $($families -join ', ')）")
    }

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

    Write-E2E "Step 3c: 等待 $effectiveAlgorithmType 告警落库" -Level STEP
    $sceneAlarm = Wait-Until -TimeoutSec $AlarmWaitSec -IntervalSec 5 -Message "camera=$($created.CameraId) 出现 algorithm_type=$effectiveAlgorithmType 告警" -Condition {
        $alarms = Get-AlarmItems -CameraId $created.CameraId
        $hit = @($alarms) | Where-Object {
            $_.alarm_type -eq $effectiveAlgorithmType -or ($_.ai_result -and $_.ai_result.algorithm_type -eq $effectiveAlgorithmType)
        } | Select-Object -First 1
        if ($hit) { $script:SampleAlarm = $hit; return $true }
        return $false
    }
    [void](Assert-That $sceneAlarm "断言3: 出现 algorithm_type=$effectiveAlgorithmType 告警")
    if ($sceneAlarm -and $script:SampleAlarm) {
        Write-E2E "告警样本: id=$($script:SampleAlarm.id) alarm_type=$($script:SampleAlarm.alarm_type) snapshot_url=$($script:SampleAlarm.snapshot_url)"
    }

    Write-E2E "Step 3d: 断言告警 snapshot_url 非空" -Level STEP
    $snapOk = $false
    if ($script:SampleAlarm) {
        $snapOk = -not [string]::IsNullOrWhiteSpace($script:SampleAlarm.snapshot_url)
    }
    [void](Assert-That $snapOk "断言4: 告警 snapshot_url 非空（内联快照已落 DETECTIONS_DIR）")

    if ($Scene -eq "PED_ATTR") {
        Write-E2E "Step 3d2: 断言 PED_ATTR 属性已透传（objects[].attributes → ai_result.detections[].attributes）" -Level STEP
        $attrDets = @()
        if ($script:SampleAlarm -and $script:SampleAlarm.ai_result) {
            $attrDets = @($script:SampleAlarm.ai_result.detections | Where-Object { $_.attributes })
        }
        $attrOk = ($attrDets.Count -gt 0)
        [void](Assert-That $attrOk "断言3b: 告警 ai_result.detections[].attributes 非空")
        if ($attrOk) {
            $attrNames = @($attrDets[0].attributes.PSObject.Properties.Name)
            Write-E2E "属性样本: $($attrNames -join ', ')"
        }
    }

    if ($Scene -eq "FACE_DET") {
        Write-E2E "Step 3d2: 断言人脸检测框已透传（objects[] → ai_result.detections[]）" -Level STEP
        $faceDets = @()
        if ($script:SampleAlarm -and $script:SampleAlarm.ai_result) {
            $faceDets = @($script:SampleAlarm.ai_result.detections)
        }
        $faceDetOk = ($faceDets.Count -gt 0)
        [void](Assert-That $faceDetOk "断言3b: 告警 ai_result.detections[] 非空（人脸框）")
        if ($faceDetOk) {
            Write-E2E "detections 样本数: $($faceDets.Count)"
        }
    }

    if ($Scene -eq "ABSENT") {
        Write-E2E "Step 3d2: 断言 absence 告警由空检测心跳驱动（ai_result.detections 为空）" -Level STEP
        $absentDets = @()
        if ($script:SampleAlarm -and $script:SampleAlarm.ai_result) {
            $absentDets = @($script:SampleAlarm.ai_result.detections)
        }
        [void](Assert-That ($absentDets.Count -eq 0) "断言3b: absence 告警 ai_result.detections 为空（心跳空检测触发）")

        Write-E2E "Step 3d3: 断言 interval_seconds=30 内 absence 告警不重复（容差 1 条）" -Level STEP
        $firstAbsentId = -1
        if ($script:SampleAlarm) { $firstAbsentId = [int]$script:SampleAlarm.id }
        $absentWindowSec = 15  # < interval_seconds=30，窗口内约 2~3 次心跳
        Write-E2E "等待 ${absentWindowSec}s（< interval_seconds=30）观察心跳是否重复建告警…"
        Start-Sleep -Seconds $absentWindowSec
        $absentAlarms = @(Get-AlarmItems -CameraId $created.CameraId -PageSize 100 | Where-Object {
            $_.alarm_type -eq "ABSENT" -or ($_.ai_result -and $_.ai_result.algorithm_type -eq "ABSENT")
        })
        $absentNew = @($absentAlarms | Where-Object { [int]$_.id -ne $firstAbsentId }).Count
        [void](Assert-That ($absentNew -le 1) "断言3c: interval_seconds=30 内新增 absence 告警 <= 1（实际新增=$absentNew，容差 1 条）")
    }

    if ($Scene -eq "OCR_TEXT" -or $Scene -eq "LPR") {
        $sceneLabel = if ($Scene -eq "LPR") { "LPR 车牌" } else { "OCR" }
        Write-E2E "Step 3d2: 断言 $sceneLabel 文本已透传（objects[].text → ai_result.detections[].text）" -Level STEP
        $textDets = @()
        if ($script:SampleAlarm -and $script:SampleAlarm.ai_result) {
            $textDets = @($script:SampleAlarm.ai_result.detections | Where-Object {
                $_.text -is [string] -and -not [string]::IsNullOrWhiteSpace($_.text)
            })
        }
        $textOk = ($textDets.Count -gt 0)
        [void](Assert-That $textOk "断言3c: 告警 ai_result.detections[].text 非空")
        if ($textOk) {
            $textSample = @($textDets | ForEach-Object { $_.text }) -join " | "
            Write-E2E "文本样本: $textSample"
        }
    }

    if ($Tracking) {
        Write-E2E "Step 3d3: 断言跟踪 track_id 已透传（objects[].track_id → ai_result.detections[].track_id）" -Level STEP
        # 扫描全部场景告警的检测框（首条告警可能尚未形成轨迹，故不只看样本告警）；
        # Agent 仅在 track_id >= 0 时才写该字段（见 SP4 跟踪契约 §3）。
        $trackAlarms = @(Get-AlarmItems -CameraId $created.CameraId -PageSize 100 | Where-Object {
            $_.alarm_type -eq $effectiveAlgorithmType -or ($_.ai_result -and $_.ai_result.algorithm_type -eq $effectiveAlgorithmType)
        })
        $trackDets = @($trackAlarms | ForEach-Object { @($_.ai_result.detections) } | Where-Object {
            $null -ne $_.track_id -and [int]$_.track_id -ge 0
        })
        $trackOk = ($trackDets.Count -gt 0)
        [void](Assert-That $trackOk "断言3d: 告警 ai_result.detections[].track_id 至少一条出现且 >= 0")
        if ($trackOk) {
            $trackSample = @($trackDets | ForEach-Object { $_.track_id } | Select-Object -Unique) -join ", "
            Write-E2E "track_id 样本: $trackSample"
        }
    }

    Write-E2E "Step 3e: 重复 event_id 去重断言" -Level STEP
    $dedupTaskId = 999999  # 哨兵 task_id，用于把去重测试的告警与真实 Agent 告警隔离
    $dedupEventId = "e2e-dedup-$($script:RunId)"
    $dedupCountBefore = @(Get-AlarmItems -CameraId $created.CameraId -PageSize 100 | Where-Object { $_.ai_result -and $_.ai_result.task_id -eq $dedupTaskId }).Count

    $dedupPayload = @{
        event_id       = $dedupEventId
        edge_code      = $effectiveEdgeCode
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
            $topic = "$MqttTopicPrefix/$effectiveEdgeCode/camera/$($created.CameraId)/detect"
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
    if ($Scene -eq "PED_ATTR") {
        Write-E2E "属性证据（DB）: select id, alarm_type, ai_result->'detections' from video_alarm_records where camera_id=$($created.CameraId) order by id desc limit 1;"
    }
    if ($Scene -eq "OCR_TEXT") {
        Write-E2E "文本证据（DB）: select id, alarm_type, ai_result->'detections'->0->>'text' as ocr_text from video_alarm_records where camera_id=$($created.CameraId) order by id desc limit 5;"
    }
    if ($Scene -eq "LPR") {
        Write-E2E "车牌证据（DB）: select id, alarm_type, ai_result->'detections'->0->>'text' as plate_text from video_alarm_records where camera_id=$($created.CameraId) order by id desc limit 5;"
    }
    if ($Scene -eq "FACE_DET") {
        Write-E2E "人脸证据（DB）: select id, alarm_type, jsonb_array_length(ai_result->'detections') as n_dets from video_alarm_records where camera_id=$($created.CameraId) order by id desc limit 5;"
    }
    if ($Scene -eq "ABSENT") {
        Write-E2E "离岗证据（DB）: select id, alarm_type, jsonb_array_length(ai_result->'detections') as n_dets, ai_result->>'task_id' as task_id from video_alarm_records where camera_id=$($created.CameraId) order by id desc limit 5;"
    }
    if ($Tracking) {
        Write-E2E "跟踪证据（DB）: select id, alarm_type, jsonb_path_query_array(ai_result, '$.detections[*].track_id') as track_ids from video_alarm_records where camera_id=$($created.CameraId) order by id desc limit 5;"
    }
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
            if ($created.RuleId) {
                Invoke-Api -Method Delete -Path "/api/v1/video/alarm/rule/delete" -Body (@($created.RuleId) | ConvertTo-Json -AsArray) | Out-Null
                Write-E2E "已清理 AlarmRule id=$($created.RuleId)"
            }
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
