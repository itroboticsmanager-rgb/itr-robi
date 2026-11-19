# Build and publish a kiosk release for self-update (robi-update.ps1).
# Run on the developer PC from the repository root:
#
#   powershell -File scripts\kiosk\publish-release.ps1            # build into artifacts\robi-release
#   powershell -File scripts\kiosk\publish-release.ps1 -Upload    # ...and put it on the VPS
#
# Layout on the VPS (Caddy serves /srv/itrcrm-guide-files as /guide-files/):
#   robi/<version>/release.zip
#   robi/latest.json            { version, url, sha256, builtAt, commit }
# The version folder goes up first and latest.json last, so a tablet never
# sees a manifest that points at a file that is not there yet.
#
# Plain ASCII (Windows PowerShell 5.1).

param(
    [string]$Version = '',
    [switch]$Upload,
    [string]$BaseUrl = 'https://vps.itrobotics.com.ua/guide-files/robi',
    [string]$Vps = 'deploy@itrcrm-prod-01',
    [string]$VpsRoot = '/srv/itrcrm-guide-files'
)

$ErrorActionPreference = 'Stop'
$repo = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $repo

$dirty = (& git status --porcelain -- app/src prototypes/robi-room/src scripts/kiosk) -join "`n"
if ($dirty) { throw "uncommitted changes in the release paths - commit first:`n$dirty" }
$commit = (& git rev-parse --short HEAD).Trim()
if (-not $Version) { $Version = (Get-Date -Format 'yyyy-MM-dd_HHmm') + '-' + $commit }
if ($Version -notmatch '^[A-Za-z0-9._-]{1,64}$') { throw "bad version: $Version" }

Write-Host "[publish] building web"
Push-Location prototypes\robi-room
# Through cmd: vite writes warnings to stderr, and PowerShell 5.1 with
# ErrorActionPreference=Stop would treat them as a failure.
& cmd /c "npm run build >nul 2>&1"
if ($LASTEXITCODE -ne 0) { Pop-Location; throw 'web build failed (run npm run build in prototypes/robi-room to see why)' }
Pop-Location

$out = Join-Path $repo 'artifacts\robi-release'
$stage = Join-Path $out "stage\$Version"
$verDir = Join-Path $out "robi\$Version"
foreach ($d in $stage, $verDir) { if (Test-Path $d) { Remove-Item $d -Recurse -Force }; New-Item -ItemType Directory -Path $d -Force | Out-Null }

New-Item -ItemType Directory -Path (Join-Path $stage 'app'), (Join-Path $stage 'scripts') -Force | Out-Null
Copy-Item -Recurse app\src (Join-Path $stage 'app\src')
Copy-Item -Recurse scripts\kiosk (Join-Path $stage 'scripts\kiosk')
Copy-Item -Recurse prototypes\robi-room\dist (Join-Path $stage 'web')
Get-ChildItem -Path $stage -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force

$zip = Join-Path $verDir 'release.zip'
Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zip -CompressionLevel Optimal
$sha = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash
$manifest = [ordered]@{
    version = $Version
    url = "$BaseUrl/$Version/release.zip"
    sha256 = $sha
    builtAt = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    commit = $commit
}
$latest = Join-Path $out 'robi\latest.json'
[IO.File]::WriteAllText($latest, ($manifest | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
Write-Host ("[publish] {0}  {1:N1} MB  sha256 {2}" -f $Version, ((Get-Item $zip).Length / 1MB), $sha)

if ($Upload) {
    # tar | tailscale ssh, the same way the guide images go up.
    Write-Host "[publish] uploading robi/$Version"
    & tar -cf - -C (Join-Path $out '') "robi/$Version" | & tailscale ssh $Vps "mkdir -p $VpsRoot/robi && tar -xf - -C $VpsRoot"
    if ($LASTEXITCODE -ne 0) { throw 'upload of the release failed' }
    Write-Host "[publish] uploading robi/latest.json"
    & tar -cf - -C (Join-Path $out '') 'robi/latest.json' | & tailscale ssh $Vps "tar -xf - -C $VpsRoot"
    if ($LASTEXITCODE -ne 0) { throw 'upload of latest.json failed' }
    $check = Invoke-WebRequest -Uri "$BaseUrl/latest.json?t=$([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())" -UseBasicParsing
    if (($check.Content | ConvertFrom-Json).version -ne $Version) { throw 'latest.json on the VPS does not show the new version' }
    Write-Host "[publish] live: $BaseUrl/latest.json -> $Version (tablets pick it up within 15 min, on the home screen)"
}
