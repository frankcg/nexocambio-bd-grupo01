# =============================================================================
# NexoCambio · Prepara toda la demo con un solo comando (ejecutar antes de presentar).
#   powershell -ExecutionPolicy Bypass -File demo\preparar_demo.ps1
#
# 1. Abre Docker Desktop si hace falta y levanta Redis.
# 2. Cierra procesadores y tableros de ensayos anteriores (dos procesadores se reparten las
#    particiones de Kafka y un evento podría no verse).
# 3. Ejecuta 0_preparar.py: topics, carga de Redis desde PostgreSQL y modelo.
# 4. Abre el procesador en su propia ventana y el tablero en el navegador.
# =============================================================================
$raiz = Split-Path $PSScriptRoot -Parent
$py = Join-Path $raiz ".venv\Scripts\python.exe"
$env:PYTHONIOENCODING = "utf-8"
Set-Location $raiz

function Paso($texto) { Write-Host "`n== $texto" -ForegroundColor Cyan }

Paso "1/4 · Docker y Redis"
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Abriendo Docker Desktop…"
    Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    $limite = (Get-Date).AddSeconds(150)
    do { Start-Sleep 3; docker info *> $null } while ($LASTEXITCODE -ne 0 -and (Get-Date) -lt $limite)
    if ($LASTEXITCODE -ne 0) { Write-Host "Docker no respondió en 150 s. Ábralo a mano y vuelva a ejecutar." -ForegroundColor Red; exit 1 }
}
docker compose -f demo/docker-compose.yml up -d
if ($LASTEXITCODE -ne 0) { Write-Host "No se pudo levantar Redis." -ForegroundColor Red; exit 1 }

Paso "2/4 · Cerrar procesadores y tableros anteriores"
$viejos = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match '2_procesador\.py|tablero\.py' }
$viejos | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Write-Host "Cerrados: $(@($viejos).Count)"

Paso "3/4 · Topics, Redis y modelo (≈ 1 minuto)"
& $py demo/0_preparar.py
if ($LASTEXITCODE -ne 0) { Write-Host "0_preparar.py falló: revise PostgreSQL (puerto 5433) y el archivo .env." -ForegroundColor Red; exit 1 }

Paso "4/4 · Procesador y tablero"
$procesador = "`$host.UI.RawUI.WindowTitle = 'NexoCambio · procesador'; `$env:PYTHONIOENCODING = 'utf-8'; " +
              "Set-Location '$raiz'; & '$py' demo/2_procesador.py"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $procesador
$tablero = "`$host.UI.RawUI.WindowTitle = 'NexoCambio · tablero'; Set-Location '$raiz\demo'; " +
           "& '$py' -m streamlit run tablero.py --server.port 8501"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $tablero -WindowStyle Minimized

Write-Host "`nListo. Antes de empezar, compruebe:" -ForegroundColor Green
Write-Host "  · La ventana 'procesador' dice: Escuchando … (12 particiones)"
Write-Host "  · El tablero está abierto en http://localhost:8501"
Write-Host "  · En Databricks, el notebook ingesta_kafka_bronze está abierto"
Write-Host "`nDemo:"
Write-Host "  Acto 1: `$env:PGCLIENTENCODING='UTF8'; & 'C:\Program Files\PostgreSQL\18\bin\psql.exe' -h localhost -p 5433 -U postgres -d nexocambio -f demo/acto1_postgresql.sql"
Write-Host "  Acto 2: .venv\Scripts\python demo/acto2.py"
