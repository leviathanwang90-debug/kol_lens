$ErrorActionPreference = 'SilentlyContinue'
$ProgressPreference = 'SilentlyContinue'

function W($title) {
    Write-Host ""
    Write-Host "==================== $title ===================="
    Write-Host ""
}

function KV($k, $v) {
    if ($null -eq $v -or $v -eq '') { $v = 'N/A' }
    Write-Host ("{0,-28}: {1}" -f $k, $v)
}

function CmdPath($name) {
    $c = Get-Command $name -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    return $null
}

W '1. System Overview'
$os = Get-CimInstance Win32_OperatingSystem
$cs = Get-CimInstance Win32_ComputerSystem
KV 'Computer Name' $env:COMPUTERNAME
KV 'OS Caption' $os.Caption
KV 'OS Version' $os.Version
KV 'Last Boot Time' $os.LastBootUpTime
KV 'Current User' $env:USERNAME

W '2. CPU and Memory'
$cpuList = Get-CimInstance Win32_Processor
$cpuNames = ($cpuList | Select-Object -ExpandProperty Name) -join ' | '
$coreCount = ($cpuList | Measure-Object -Property NumberOfCores -Sum).Sum
$logicalCount = ($cpuList | Measure-Object -Property NumberOfLogicalProcessors -Sum).Sum
$totalMemGB = [math]::Round($cs.TotalPhysicalMemory / 1GB, 2)
$freeMemGB = [math]::Round($os.FreePhysicalMemory * 1KB / 1GB, 2)
$usedMemGB = [math]::Round($totalMemGB - $freeMemGB, 2)
$memUsagePct = [math]::Round(($usedMemGB / $totalMemGB) * 100, 2)
KV 'CPU Model' $cpuNames
KV 'Physical Cores' $coreCount
KV 'Logical Processors' $logicalCount
KV 'Total Memory (GB)' $totalMemGB
KV 'Free Memory (GB)' $freeMemGB
KV 'Used Memory (GB)' $usedMemGB
KV 'Memory Usage (%)' $memUsagePct

W '3. Disk Volumes'
$vols = Get-CimInstance Win32_LogicalDisk | Where-Object { $_.DriveType -in 2,3 }
foreach ($v in $vols) {
    $sizeGB = if ($v.Size) { [math]::Round($v.Size / 1GB, 2) } else { 'N/A' }
    $freeGB = if ($v.FreeSpace -ne $null) { [math]::Round($v.FreeSpace / 1GB, 2) } else { 'N/A' }
    $usedPct = if ($v.Size -and $v.FreeSpace -ne $null) { [math]::Round((($v.Size - $v.FreeSpace) / $v.Size) * 100, 2) } else { 'N/A' }
    KV ('Drive ' + $v.DeviceID) ('Size=' + $sizeGB + 'GB; Free=' + $freeGB + 'GB; Used=' + $usedPct + '%; FS=' + $v.FileSystem)
}

W '4. Runtime and Tools'
$tools = @('python','py','node','npm','pnpm','git','docker','wsl','nginx','psql','redis-cli')
foreach ($t in $tools) {
    $path = CmdPath $t
    if ($path) { KV $t $path } else { KV $t 'Not Found' }
}

$pyv = $null
try { $pyv = (& python --version) 2>$null } catch { }
KV 'Python Version' $pyv

$nodev = $null
try { $nodev = (& node -v) 2>$null } catch { }
KV 'Node Version' $nodev

$npmv = $null
try { $npmv = (cmd /c npm -v) 2>$null } catch { }
KV 'npm Version' $npmv

$pnpmv = $null
try { $pnpmv = (cmd /c pnpm -v) 2>$null } catch { }
KV 'pnpm Version' $pnpmv

$gitv = $null
try { $gitv = (& git --version) 2>$null } catch { }
KV 'Git Version' $gitv

W '5. Services'
$svcKeywords = @('nginx','postgres','redis','docker')
$svcs = Get-Service | Where-Object {
    $n = $_.Name.ToLower()
    $d = ($_.DisplayName + '').ToLower()
    ($svcKeywords | Where-Object { $n -like ('*' + $_ + '*') -or $d -like ('*' + $_ + '*') }).Count -gt 0
}
if ($svcs) {
    $svcs | Sort-Object Name | ForEach-Object {
        KV $_.Name ('Status=' + $_.Status + '; DisplayName=' + $_.DisplayName)
    }
} else {
    KV 'Windows Services' 'No related service detected'
}

W '6. Port Listening'
$ports = @(80,443,3007,5432,6379,19530,9000,9001,9091)
foreach ($p in $ports) {
    $conns = $null
    try { $conns = Get-NetTCPConnection -LocalPort $p -State Listen } catch { }
    if ($conns) {
        foreach ($c in $conns) {
            $proc = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
            $pname = if ($proc) { $proc.ProcessName } else { 'Unknown' }
            KV ('Port ' + $p) ('LISTEN ' + $c.LocalAddress + ':' + $c.LocalPort + ' PID=' + $c.OwningProcess + ' Process=' + $pname)
        }
    } else {
        KV ('Port ' + $p) 'Free'
    }
}

W '7. Related Processes'
$procKeywords = @('nginx','postgres','redis','docker','minio','etcd','milvus','python','node')
$procs = Get-Process | Where-Object {
    $name = $_.ProcessName.ToLower()
    ($procKeywords | Where-Object { $name -like ('*' + $_ + '*') }).Count -gt 0
} | Sort-Object ProcessName
if ($procs) {
    $procs | Select-Object ProcessName, Id, CPU, WS, PM | Format-Table -AutoSize | Out-String | Write-Host
} else {
    KV 'Processes' 'No related process detected'
}

W '8. Quick Review'
Write-Host 'Please send back Sections 2, 3, 4, 5, 6, and 7.'
Write-Host 'If memory is below 16GB, local Milvus remains risky.'
Write-Host 'If Docker is Not Found, full local Milvus setup is not ready yet.'
Write-Host 'If ports 80 or 443 are occupied, check IIS or other web services first.'
