$envFile = Join-Path $PSScriptRoot "..\\.env"
Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
        [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
    }
}

Set-Location (Join-Path $PSScriptRoot "..\dbt_protectora")
dbt run --target prod
