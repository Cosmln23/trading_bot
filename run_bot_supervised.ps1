# --- config ---
$Repo = "C:\Users\fred1\Desktop\Bybit-Futures-Bot"
$Py   = "$Repo\.venv\Scripts\python.exe"
$WS   = "$Repo\BybitUSDT\liquidation_ws.py"
$PM   = "$Repo\BybitUSDT\profit.py"
$LOG  = "$Repo\logs"
$BackoffStart = 3
$BackoffMax   = 30

New-Item -ItemType Directory -Force -Path $LOG | Out-Null

function Start-ProcLoop($name, $script) {
  $backoff = $BackoffStart
  while ($true) {
    $ts = Get-Date -Format "yyyyMMdd_HHmmss"
    $out = Join-Path $LOG "$name-$ts.out.log"
    $err = Join-Path $LOG "$name-$ts.err.log"
    Write-Host "[$name] starting... ($ts)"
    $p = Start-Process -FilePath $Py -ArgumentList $script `
         -RedirectStandardOutput $out -RedirectStandardError $err `
         -NoNewWindow -PassThru
    Wait-Process -Id $p.Id
    Write-Host "[$name] exited code=$($p.ExitCode). Restarting in $backoff s..."
    Start-Sleep -Seconds $backoff
    $backoff = [Math]::Min($backoff * 2, $BackoffMax)
  }
}

Start-Job -ScriptBlock ${function:Start-ProcLoop} -Name "liq" -ArgumentList @("liq", $WS) | Out-Null
Start-Job -ScriptBlock ${function:Start-ProcLoop} -Name "pm"  -ArgumentList @("pm",  $PM) | Out-Null

Write-Host "Supervisor running. Use Get-Job / Receive-Job / Stop-Job to manage."
while ($true) { Start-Sleep -Seconds 3600 }
