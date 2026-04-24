$ErrorActionPreference = 'SilentlyContinue'

function W($title) {
    Write-Host ""
    Write-Host "==================== $title ===================="
    Write-Host ""
}

function KV($k, $v) {
    if ($null -eq $v -or $v -eq '') { $v = 'N/A' }
    Write-Host (("{0,-28}: {1}") -f $k, $v)
}

function CmdPath($name) {
    $c = Get-Command $name -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    return $null
}

W '1. Fast Readiness Check'
$tools = @('python','py','node','npm','pnpm','git','docker','wsl','nginx','psql','redis-cli')
foreach ($t in $tools) {
    $path = CmdPath $t
    if ($path) { KV $t $path } else { KV $t 'Not Found' }
}

W '2. Service Check'
$svcKeywords = @('nginx','postgres','redis','docker','iis')
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

W '3. Port Check'
$ports = @(80,443,3007,5432,6379,19530,9000,9001,9091)
foreach ($p in $ports) {
    $rows = @()
    try {
        $rows = Get-NetTCPConnection -LocalPort $p -State Listen
    } catch { }
    if ($rows -and $rows.Count -gt 0) {
        foreach ($r in $rows) {
            $proc = Get-Process -Id $r.OwningProcess -ErrorAction SilentlyContinue
            $pname = if ($proc) { $proc.ProcessName } else { 'Unknown' }
            KV ('Port ' + $p) ('LISTEN ' + $r.LocalAddress + ':' + $r.LocalPort + ' PID=' + $r.OwningProcess + ' Process=' + $pname)
        }
    } else {
        KV ('Port ' + $p) 'Free'
    }
}

W '4. Key Conclusion'
Write-Host 'Please send back all output of Sections 1, 2, and 3.'
Write-Host 'This script does not run npm or pnpm version commands, so it should not hang there.'
