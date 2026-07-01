while ($true) {
    Write-Host "Starting backend..." -ForegroundColor Cyan
    & python -m uvicorn main:app --host 0.0.0.0 --port 8081 --reload
    Write-Host "Backend stopped. Restarting in 2s..." -ForegroundColor Yellow
    Start-Sleep -Seconds 2
}
