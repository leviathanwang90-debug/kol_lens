$ErrorActionPreference = 'SilentlyContinue'
$ProgressPreference = 'SilentlyContinue'

function Write-Section($title) {
    Write-Host ""
    Write-Host "==================== $title ===================="
    Write-Host ""
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

function Try-Invoke($scriptBlock) {
    try { & $scriptBlock } catch { }
}

Write-Section '1. System Overview'
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

Write-Section '2. CPU and Memory'
$cpuList = Get-CimInstance Win32_Processor
$cpuNames = ($cpuList | Select-Object -ExpandProperty Name) -join ' | '
$coreCount = ($cpuList | Measure-Object -Property NumberOfCores -Sum).Sum
$logicalCount = ($cpuList | Measure-Object -Property NumberOfLogicalProcessors -Sum).Sum
$totalMemGB = [math]::Round($cs.TotalPhysicalMemory / 1GB, 2)
$freeMemGB = [math]::Round($os.FreePhysicalMemory * 1KB / 1GB, 2)
$usedMemGB = [math]::Round($totalMemGB - $freeMemGB, 2)
if ($totalMemGB -gt 0) {
    $memUsagePct = [math]::Round(($usedMemGB / $totalMemGB) * 100, 2)
} else {
    $memUsagePct = 'N/A'
}
Write-KV 'CPU Model' $cpuNames
Write-KV 'Physical Cores' $coreCount
Write-KV 'Logical Processors' $logicalCount
Write-KV 'Total Memory (GB)' $totalMemGB
Write-KV 'Free Memory (GB)' $freeMemGB
Write-KV 'Used Memory (GB)' $usedMemGB
Write-KV 'Memory Usage (%)' $memUsagePct

Write-Section '3. Page File'
$pageFiles = Get-CimInstance Win32_PageFileUsage
if ($pageFiles) {
    $pageFiles | ForEach-Object {
        $msg = "Allocated=" + $_.AllocatedBaseSize + "MB, CurrentUsage=" + $_.CurrentUsage + "MB, PeakUsage=" + $_.PeakUsage + "MB"
        Write-KV ("Page File " + $_.Name) $msg
    }
} else {
    Write-KV 'Page File' 'Not detected or no permission'
}

Write-Section '4. Disk Volumes'
$vols = Get-CimInstance Win32_LogicalDisk | Where-Object { $_.DriveType -in 2,3 }
foreach ($v in $vols) {
    if ($v.Size) { $sizeGB = [math]::Round($v.Size / 1GB, 2) } else { $sizeGB = 'N/A' }
    if ($v.FreeSpace -ne $null) { $freeGB = [math]::Round($v.FreeSpace / 1GB, 2) } else { $freeGB = 'N/A' }
    if ($v.Size -and $v.FreeSpace -ne $null) {
        $usedPct = [math]::Round((($v.Size - $v.FreeSpace) / $v.Size) * 100, 2)
    } else {
        $usedPct = 'N/A'
    }
    $msg = "Label=" + $v.VolumeName + "; FS=" + $v.FileSystem + "; Size=" + $sizeGB + "GB; Free=" + $freeGB + "GB; Used=" + $usedPct + "%"
    Write-KV ("Drive " + $v.DeviceID) $msg
}

Write-Section '5. Network and IP'
Try-Invoke {
    $ips = Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' }
    foreach ($ip in $ips) {
        Write-KV ("IPv4 " + $ip.InterfaceAlias) $ip.IPAddress
    }
}
$pub = $null
try { $pub = Invoke-RestMethod -Uri 'https://api.ipify.org?format=text' -TimeoutSec 8 } catch { }
Write-KV 'Public IP' $pub

Write-Section '6. Runtime and Tools'
$tools = @('python','python3','py','node','npm','pnpm','git','docker','nginx','psql','redis-cli','wsl')
foreach ($t in $tools) {
    $path = Test-Cmd $t
    if ($path) { Write-KV $t $path } else { Write-KV $t 'Not Found' }
}

$py311 = $null
try { $py311 = (& py -3.11 --version) 2>$null } catch { }
if ($py311) {
    Write-KV 'Python Version' $py311
} else {
    $pyv = $null
    try { $pyv = (& python --version) 2>$null } catch { }
    Write-KV 'Python Version' $pyv
}

$nodev = $null
try { $nodev = (& node -v) 2>$null } catch { }
Write-KV 'Node Version' $nodev

$npmv = $null
try { $npmv = (& npm -v) 2>$null } catch { }
Write-KV 'npm Version' $npmv

$pnpmv = $null
try { $pnpmv = (& pnpm -v) 2>$null } catch { }
Write-KV 'pnpm Version' $pnpmv

$gitv = $null
try { $gitv = (& git --version) 2>$null } catch { }
Write-KV 'Git Version' $gitv

$dockerv = $null
try { $dockerv = (& docker --version) 2>$null } catch { }
Write-KV 'Docker Version' $dockerv

$composev = $null
try { $composev = (& docker compose version) 2>$null } catch { }
Write-KV 'Docker Compose Version' $composev

$wslv = $null
try { $wslv = (& wsl --version | Select-Object -First 1) 2>$null } catch { }
Write-KV 'WSL Version' $wslv

Write-Section '7. Docker and WSL'
$wslStatus = $null
try { $wslStatus = (& wsl -l -v | Out-String).Trim() } catch { }
Write-KV 'WSL Status' $wslStatus

$dockerInfo = $null
try { $dockerInfo = (& docker info --format '{{.ServerVersion}} | {{.OperatingSystem}}') 2>$null } catch { }
Write-KV 'Docker Info' $dockerInfo

$dockerPs = $null
try { $dockerPs = (& docker ps -a --format 'table {{.Names}}	{{.Image}}	{{.Status}}	{{.Ports}}' | Out-String).Trim() } catch { }
Write-KV 'Docker Containers' $dockerPs

Write-Section '8. Services'
$svcKeywords = @('nginx','postgres','redis','docker')
$svcs = Get-Service | Where-Object {
    $n = $_.Name.ToLower()
    $d = ($_.DisplayName + '').ToLower()
    ($svcKeywords | Where-Object { $n -like ('*' + $_ + '*') -or $d -like ('*' + $_ + '*') }).Count -gt 0
}
if ($svcs) {
    $svcs | Sort-Object Name | ForEach-Object {
        $msg = 'Status=' + $_.Status + '; DisplayName=' + $_.DisplayName
        Write-KV $_.Name $msg
    }
} else {
    Write-KV 'Windows Services' 'No related service detected'
}

Write-Section '9. Port Listening'
$ports = @(80,443,3007,5432,6379,19530,9000,9001,9091)
foreach ($p in $ports) {
    $conns = $null
    try { $conns = Get-NetTCPConnection -LocalPort $p -State Listen } catch { }
    if ($conns) {
        foreach ($c in $conns) {
            $proc = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
            if ($proc) { $pname = $proc.ProcessName } else { $pname = 'Unknown' }
            $msg = 'LISTEN ' + $c.LocalAddress + ':' + $c.LocalPort + ' PID=' + $c.OwningProcess + ' Process=' + $pname
            Write-KV ('Port ' + $p) $msg
        }
    } else {
        Write-KV ('Port ' + $p) 'Free'
    }
}

Write-Section '10. Related Processes'
$procKeywords = @('nginx','postgres','redis','docker','minio','etcd','milvus','python','node')
$procs = Get-Process | Where-Object {
    $name = $_.ProcessName.ToLower()
    ($procKeywords | Where-Object { $name -like ('*' + $_ + '*') }).Count -gt 0
} | Sort-Object ProcessName
if ($procs) {
    $procs | Select-Object ProcessName, Id, CPU, WS, PM | Format-Table -AutoSize | Out-String | Write-Host
} else {
    Write-KV 'Processes' 'No related process detected'
}

Write-Section '11. Firewall'
Try-Invoke {
    Get-NetFirewallProfile | Select-Object Name, Enabled, DefaultInboundAction, DefaultOutboundAction | Format-Table -AutoSize | Out-String | Write-Host
}

Write-Section '12. Suggested Paths'
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
    if (Test-Path $p) { Write-KV $p 'Exists' } else { Write-KV $p 'Missing' }
}

Write-Section '13. Quick Review'
Write-Host 'Please focus on these items:'
Write-Host '1) Memory >= 16GB is preferred for full local deployment with Milvus.'
Write-Host '2) Ports 3007, 5432, 6379, 19530, 9000, 9001, 9091 should preferably be free.'
Write-Host '3) Python 3.11, Node.js, pnpm, Docker Desktop and WSL2 should be available.'
Write-Host '4) Decide whether PostgreSQL, Redis and Milvus will be local, containerized or remote.'
Write-Host '5) Check whether ports 80 and 443 are already occupied by IIS or Nginx.'

Write-Section '14. What to send back'
Write-Host 'Please send back these sections:'
Write-Host 'A. Section 2: CPU and Memory'
Write-Host 'B. Section 4: Disk Volumes'
Write-Host 'C. Sections 6 to 10: Runtime, Services, Ports'
