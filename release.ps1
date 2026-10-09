# Vydá novou verzi: .\release.ps1 1.0.1 "Co je nového"
# Nastaví verzi, sestaví instalátor, commitne, otaguje a nahraje GitHub Release.
# Nainstalovaní agenti si novou verzi do 6 hodin stáhnou sami (nebo hned přes tray menu).
param(
    [Parameter(Mandatory = $true)][string]$Version,
    [string]$Notes = "",
    [string]$Trailer = ""  # volitelný řádek na konec commitu, např. Co-Authored-By
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw "Verze musí být ve tvaru 1.2.3" }
if (git status --porcelain) { throw "Nejdřív commitni rozdělané změny." }

$versionPy = "`"`"`"Verze agenta – mění ji release.ps1 při vydání nové verze.`"`"`"`n__version__ = `"$Version`"`n"
[IO.File]::WriteAllText("$PSScriptRoot\agent\version.py", $versionPy, (New-Object Text.UTF8Encoding $false))

cmd /c "`"$PSScriptRoot\build.bat`""
if ($LASTEXITCODE -ne 0) { throw "Sestavení selhalo" }

$setup = "dist\EanAgent-Setup-$Version.exe"
$hash = (Get-FileHash $setup -Algorithm SHA256).Hash.ToLower()
"$hash  EanAgent-Setup-$Version.exe" | Set-Content -Encoding ascii -NoNewline "$setup.sha256"

git add agent\version.py
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    if ($Trailer) { git commit -m "Verze $Version" -m $Trailer } else { git commit -m "Verze $Version" }
}
git tag "v$Version"
git push origin HEAD "v$Version"

if (-not $Notes) { $Notes = "EAN Agent $Version" }
gh release create "v$Version" $setup "$setup.sha256" --title "EAN Agent $Version" --notes $Notes
Write-Host "Vydáno: v$Version"
