# Parte de situación de las ramas que trabajan en paralelo.
#
# Se ejecuta desde integración y no pregunta nada a nadie: lo lee todo del
# repositorio. Sirve para saber por dónde van las otras sesiones sin tener que
# abrirlas, y sobre todo para detectar pronto lo único que puede estropear una
# fusión: que una rama haya escrito fuera de su zona.
#
#   powershell -ExecutionPolicy Bypass -File scripts\estado-capas.ps1

$ErrorActionPreference = "Stop"

# Cada capa: su rama, su carpeta, el prefijo donde SÍ puede escribir, y el
# número de decisión que tiene reservado (ver CLAUDE.md).
$capas = @(
    @{ rama = "capa/tts"; dir = "C:\Users\migue\doombot-tts"; zona = "src/doombot/tts/"; dec = "D-021" }
    @{ rama = "capa/hud"; dir = "C:\Users\migue\doombot-hud"; zona = "ui/";              dec = "D-022" }
)

# Ficheros que solo toca integración. Están aquí y no en un comentario porque
# es la comprobación que de verdad evita conflictos de fusión.
$comunes = @(
    "src/doombot/chat.py", "src/doombot/config.py", "src/doombot/paths.py",
    "src/doombot/profiles.py", "src/doombot/backends/base.py", "pyproject.toml",
    "CLAUDE.md", ".gitignore"
)

Push-Location $PSScriptRoot\..
git fetch origin --quiet --prune

Write-Host ""
Write-Host "  ESTADO DE LAS CAPAS  -  $(Get-Date -Format 'dd/MM/yyyy HH:mm')" -ForegroundColor White
Write-Host "  main = $(git rev-parse --short main)  -  origin/main = $(git rev-parse --short origin/main)"
Write-Host ""

foreach ($c in $capas) {
    $rama = $c.rama
    Write-Host ("  " + "-" * 68)
    Write-Host "  $rama" -ForegroundColor Cyan

    $existe = git rev-parse --verify --quiet "$rama"
    if (-not $existe) { Write-Host "    la rama no existe" -ForegroundColor Red; continue }

    # --- avance ---
    $nuevos = @(git log --oneline "main..$rama")
    $atras  = @(git log --oneline "$rama..main")

    if ($nuevos.Count -eq 0) {
        Write-Host "    sin trabajo nuevo todavia" -ForegroundColor DarkGray
    } else {
        Write-Host "    $($nuevos.Count) commit(s) por delante de main:" -ForegroundColor Green
        $nuevos | Select-Object -First 6 | ForEach-Object { Write-Host "      $_" }
        if ($nuevos.Count -gt 6) { Write-Host "      ... y $($nuevos.Count - 6) mas" }
    }
    if ($atras.Count -gt 0) {
        Write-Host "    $($atras.Count) commit(s) de main sin recoger (conviene que hagan merge)" -ForegroundColor Yellow
    }

    # --- ficheros tocados, y si alguno esta fuera de su zona ---
    if ($nuevos.Count -gt 0) {
        $tocados = @(git diff --name-only "main...$rama")
        $fuera = @($tocados | Where-Object { -not $_.StartsWith($c.zona) -and $_ -notlike "docs/*" -and $_ -notlike "obsidian/*" })
        $invasion = @($fuera | Where-Object { $comunes -contains $_ })

        Write-Host "    ficheros tocados: $($tocados.Count)"
        if ($invasion.Count -gt 0) {
            Write-Host "    AVISO: ha escrito en ficheros de integracion:" -ForegroundColor Red
            $invasion | ForEach-Object { Write-Host "      $_" -ForegroundColor Red }
            Write-Host "    -> revisar a mano antes de fusionar" -ForegroundColor Red
        } elseif ($fuera.Count -gt 0) {
            Write-Host "    fuera de $($c.zona) (no critico):" -ForegroundColor Yellow
            $fuera | Select-Object -First 5 | ForEach-Object { Write-Host "      $_" -ForegroundColor Yellow }
        }
    }

    # --- ha dejado rastro para el resto? ---
    $decUsada = @(git show "${rama}:docs/decisiones.md" 2>$null | Select-String -Pattern "^## $($c.dec)").Count -gt 0
    $notas = @(git diff --name-only "main...$rama" | Where-Object { $_ -like "docs/NOTAS_SESION/*" })
    Write-Host "    decision $($c.dec) escrita: $(if ($decUsada) { 'si' } else { 'todavia no' })"
    Write-Host "    nota de sesion:           $(if ($notas.Count) { $notas[0] } else { 'todavia no' })"

    # --- estado de su copia de trabajo ---
    if (Test-Path $c.dir) {
        $sucio = @(git -C $c.dir status --porcelain)
        $subido = (git rev-parse "$rama") -eq (git rev-parse "origin/$rama" 2>$null)
        Write-Host "    sin commitear en su carpeta: $($sucio.Count) fichero(s)"
        Write-Host "    subido a GitHub:             $(if ($subido) { 'si' } else { 'NO - falta git push' })" `
            -ForegroundColor $(if ($subido) { 'Gray' } else { 'Yellow' })
    } else {
        Write-Host "    su carpeta no existe: $($c.dir)" -ForegroundColor Red
    }
    Write-Host ""
}

Write-Host ("  " + "-" * 68)
Write-Host "  Para fusionar una rama cuando este lista:" -ForegroundColor White
Write-Host "    git merge --no-ff capa/tts"
Write-Host ""
Pop-Location

exit 0
