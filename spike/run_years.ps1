$py = ".\.venv-scratch\Scripts\python.exe"
for ($y = 2001; $y -le 2025; $y++) {
    $out = "spike\data\years\ndvi_$y.csv"
    if (Test-Path $out) { "skip $y" | Out-File -Append "spike\data\run.log"; continue }
    $p = Start-Process -FilePath $py -ArgumentList "-u","spike\modis_ndvi.py","--start",$y,"--end",$y,"--out",$out -NoNewWindow -PassThru `
        -RedirectStandardOutput "spike\data\years\log_$y.txt" -RedirectStandardError "spike\data\years\err_$y.txt"
    if (-not $p.WaitForExit(150000)) { $p.Kill(); "TIMEOUT $y" | Out-File -Append "spike\data\run.log" }
    else { "done $y rc=$($p.ExitCode)" | Out-File -Append "spike\data\run.log" }
}
"ALL DONE" | Out-File -Append "spike\data\run.log"
