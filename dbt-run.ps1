Get-Content .env | Where-Object { $_ -match '^\s*[^#=].*=' } | ForEach-Object {
    $k, $v = $_ -split '=', 2
    [System.Environment]::SetEnvironmentVariable($k.Trim(), $v.Trim(), 'Process')
}
Set-Location dbt_protectora
dbt run
Set-Location ..
