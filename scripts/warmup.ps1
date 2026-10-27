# RISKS N10: wake the deployed backend before a demo. Usage: powershell -File scripts/warmup.ps1 https://your-backend
param([Parameter(Mandatory = $true)][string]$BackendUrl, [int]$Tries = 12)
$url = $BackendUrl.TrimEnd('/') + '/api/health'
for ($i = 1; $i -le $Tries; $i++) {
    try {
        $r = Invoke-RestMethod -Uri $url -TimeoutSec 15
        Write-Host "OK ($i): $($r | ConvertTo-Json -Compress)"
        exit 0
    } catch {
        Write-Host "attempt $i failed, retrying in 10 s"
        Start-Sleep -Seconds 10
    }
}
Write-Error "backend did not answer at $url"
exit 1
