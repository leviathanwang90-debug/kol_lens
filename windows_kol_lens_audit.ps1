$ErrorActionPreference = 'SilentlyContinue'
$ProgressPreference = 'SilentlyContinue'

function Write-Section($title) {
    Write-Host "`n==================== $title ====================`n"
}

function Write-KV($key, $value) {
    if ($null -eq $value -or $value -eq '') { $value = 'N/A' }
    Write-Host ("{0,-32}: {1}" -f $key, $value)
}

function Test-Cmd($name) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

function Safe-Run($scriptBlock) {
    try { & $scriptBlock } catch { }
}

Write-Section '1. 主机与系统概览'
$os = Get-CimInstance Win32_OperatingSystem
$cs = Get-CimInstance Win32_ComputerSystem
$bios = Get-CimInstance Win32_BIOS
Write-KV 'Computer Name' $env:COMPUTERNAME
Write-KV 'OS Caption' $os.Caption
Write-KV 'OS Version' $os.Version
Write-KV 'OS Build' $os.BuildNumber
Write-KV 'Install Date' $os.InstallDate
Write-KV 'Last Boot Time' $os.LastBootUpTime
Write-KV 'Manufacturer' $cs.Manufacturer
Write-KV 'Model' $cs.Model
Write-KV 'Serial Number' $bios.SerialNumber
Write-KV 'Current User' $env:USERNAME

Write-Section '2. CPU 与内存'
$cpuList = Get-CimInstance Win32_Processor
$cpuNames = ($cpuList | Select-Object -ExpandProperty Name) -join ' | '
$coreCount = ($cpuList | Measure-Object -Property NumberOfCores -Sum).Sum
$logicalCount = ($cpuList | Measure-Object -Property NumberOfLogicalProcessors -Sum).Sum
$totalMemGB = [math]::Round($cs.TotalPhysicalMemory / 1GB, 2)
$freeMemGB = [math]::Round($os.FreePhysicalMemory * 1KB / 1GB, 2)
$usedMemGB = [math]::Round($totalMemGB - $freeMemGB, 2)
$memUsagePct = if ($totalMemGB -gt 0) { [math]::Round(($usedMemGB / $totalMemGB) * 100, 2) } else { 'N/A' }
Write-KV 'CPU Model' $cpuNames
Write-KV 'Physical Cores' $coreCount
Write-KV 'Logical Processors' $logicalCount
Write-KV 'Total Memory (GB)' $totalMemGB
Write-KV 'Free Memory (GB)' $freeMemGB
Write-KV 'Used Memory (GB)' $usedMemGB
Write-KV 'Memory Usage (%)' $memUsagePct

Write-Section '3. 页面文件 / 虚拟内存'
$pageFiles = Get-CimInstance Win32_PageFileUsage
if ($pageFiles) {
    $pageFiles | ForEach-Object {
        Write-KV ('Page File ' + $_.Name) (("Allocated={0}MB, CurrentUsage={1}MB, PeakUsage={2}MB" -f $_.AllocatedBaseSize, $_.CurrentUsage, $_.PeakUsage))
    }
} else {
    Write-KV 'Page File' '未检测到或无权限读取'
}

Write-Section '4. 磁盘与卷'
$vols = Get-CimInstance Win32_LogicalDisk | Where-Object { $_.DriveType -in 2,3 }
foreach ($v in $vols) {
    $sizeGB = if ($v.Size) { [math]::Round($v.Size / 1GB, 2) } else { 'N/A' }
    $freeGB = if ($v.FreeSpace) { [math]::Round($v.FreeSpace / 1GB, 2) } else { 'N/A' }
    $usedPct = if ($v.Size -and $v.FreeSpace -ne $null) { [math]::Round((($v.Size - $v.FreeSpace) / $v.Size) * 100, 2) } else { 'N/A' }
    Write-KV ("Drive $($v.DeviceID)") (("Label={0}; FS={1}; Size={2}GB; Free={3}GB; Used={4}%" -f $v.VolumeName, $v.FileSystem, $sizeGB, $freeGB, $usedPct))
}

Write-Section '5. 网络与 IP'
Safe-Run {
    $ips = Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -ne '169.254.0.0' }
    foreach ($ip in $ips) {
        Write-KV ("IPv4 $($ip.InterfaceAlias)") $ip.IPAddress
    }
}
$pub = $null
try { $pub = (Invoke-RestMethod -Uri 'https://api.ipify.org?format=text' -TimeoutSec 8) } catch { }
Write-KV 'Public IP' $pub

Write-Section '6. 常用运行时与工具'
$tools = @('python','python3','py','node','npm','pnpm','git','docker','docker-compose','nginx','psql','redis-cli','milvus','wsl')
foreach ($t in $tools) {
    $path = Test-Cmd $t
    Write-KV $t $(if ($path) { $path } else { '未找到' })
}

Safe-Run { Write-KV 'Python Version' (& py -3.11 --version 2>$null) }
if (-not $?) { Safe-Run { Write-KV 'Python Version' (& python --version 2>$null) } }
Safe-Run { Write-KV 'Node Version' (& node -v 2>$null) }
Safe-Run { Write-KV 'npm Version' (& npm -v 2>$null) }
Safe-Run { Write-KV 'pnpm Version' (& pnpm -v 2>$null) }
Safe-Run { Write-KV 'Git Version' (& git --version 2>$null) }
Safe-Run { Write-KV 'Docker Version' (& docker --version 2>$null) }
Safe-Run { Write-KV 'Docker Compose Version' (& docker compose version 2>$null) }
Safe-Run { Write-KV 'WSL Version' (& wsl --version 2>$null | Select-Object -First 1) }

Write-Section '7. Docker / WSL / 虚拟化能力'
Safe-Run { Write-KV 'WSL Status' (& wsl -l -v 2>$null | Out-String).Trim() }
Safe-Run { Write-KV 'Docker Info' (& docker info --format '{{.ServerVersion}} | {{.OperatingSystem}}' 2>$null) }
Safe-Run { Write-KV 'Docker Containers' (& docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' 2>$null | Out-String).Trim() }
Safe-Run { Write-KV 'Docker Images' (& docker images --format 'table {{.Repository}}\t{{.Tag}}\t{{.Size}}' 2>$null | Select-Object -First 15 | Out-String).Trim() }

Write-Section '8. 服务检测（Nginx / PostgreSQL / Redis / Docker）'
$svcKeywords = 'nginx','postgres','redis','docker','com.docker.service'
$svcs = Get-Service | Where-Object {
    $n = $_.Name.ToLower(); $d = ($_.DisplayName + '').ToLower();
    ($svcKeywords | Where-Object { $n -like "*$_*" -or $d -like "*$_*" }).Count -gt 0
}
if ($svcs) {
    $svcs | Sort-Object Name | ForEach-Object {
        Write-KV $_.Name (("Status={0}; DisplayName={1}" -f $_.Status, $_.DisplayName))
    }
} else {
    Write-KV 'Windows Services' '未检测到相关服务'
}

Write-Section '9. 端口占用'
$ports = 80,443,3007,5432,6379,19530,9000,9001,9091
foreach ($p in $ports) {
    $conns = Get-NetTCPConnection -LocalPort $p -State Listen
    if ($conns) {
        foreach ($c in $conns) {
            $proc = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
            $pname = if ($proc) { $proc.ProcessName } else { 'Unknown' }
            Write-KV ("Port $p") (("LISTEN {0}:{1} PID={2} Process={3}" -f $c.LocalAddress, $c.LocalPort, $c.OwningProcess, $pname))
        }
    } else {
        Write-KV ("Port $p") '空闲'
    }
}

Write-Section '10. PostgreSQL / Redis / Nginx / Milvus 进程'
$procKeywords = 'nginx','postgres','redis','docker','minio','etcd','milvus','python','node'
$procs = Get-Process | Where-Object {
    $name = $_.ProcessName.ToLower()
    ($procKeywords | Where-Object { $name -like "*$_*" }).Count -gt 0
} | Sort-Object ProcessName
if ($procs) {
    $procs | Select-Object ProcessName, Id, CPU, WS, PM | Format-Table -AutoSize | Out-String | Write-Host
} else {
    Write-KV 'Processes' '未检测到相关进程'
}

Write-Section '11. 防火墙状态'
Safe-Run {
    Get-NetFirewallProfile | Select-Object Name, Enabled, DefaultInboundAction, DefaultOutboundAction | Format-Table -AutoSize | Out-String | Write-Host
}

Write-Section '12. 项目路径建议检查'
$paths = @(
    'C:\kol_lens',
    'D:\kol_lens',
    'C:\nginx',
    'C:\Program Files\Docker',
    'C:\Program Files\PostgreSQL',
    'C:\Redis',
    'C:\tools'
)
foreach ($p in $paths) {
    Write-KV $p $(if (Test-Path $p) { '存在' } else { '不存在' })
}

Write-Section '13. 结论提示（供人工判断）'
Write-Host '请重点看以下几项：'
Write-Host '1) 内存是否 >= 16GB；如果只有 8GB，本地完整跑 Milvus 风险较高。'
Write-Host '2) 3007 / 5432 / 6379 / 19530 / 9000 / 9001 / 9091 是否空闲。'
Write-Host '3) Python 3.11、Node、pnpm、Docker Desktop / WSL2 是否已具备。'
Write-Host '4) PostgreSQL、Redis、Milvus 是否准备用本机、容器还是远端。'
Write-Host '5) 80 / 443 是否已被其他站点占用，避免和现有 Nginx / IIS 冲突。'

Write-Section '14. 建议回传给我的内容'
Write-Host '请把以下三段结果贴回来：'
Write-Host 'A. 2. CPU 与内存'
Write-Host 'B. 4. 磁盘与卷'
Write-Host 'C. 6~10. 运行时、服务和端口占用'
