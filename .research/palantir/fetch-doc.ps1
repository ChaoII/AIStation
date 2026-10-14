param(
  [Parameter(Mandatory=$true)][string]$Path,   # e.g. foundry/ontology/core-concepts
  [string]$OutDir = "D:\AIStation\.research\palantir\raw"
)
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$url = "https://www.palantir.com/docs/$Path/"
$name = ($Path -replace '[\\/]', '__') + ".md"
$out = Join-Path $OutDir $name

$r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 90
$c = $r.Content
$start = $c.IndexOf('id="__NEXT_DATA__"')
if ($start -lt 0) { Write-Output "NO_NEXT_DATA $url"; exit 1 }
$s = $c.IndexOf('>', $start) + 1
$e = $c.IndexOf('</script>', $s)
$obj = $c.Substring($s, $e - $s) | ConvertFrom-Json
$md = $obj.props.pageProps.markdown
$title = $obj.props.pageProps.metadata.title
if (-not $md) { Write-Output "NO_MARKDOWN $url"; exit 1 }
"<!-- SOURCE: $url -->`n<!-- TITLE: $title -->`n`n" + $md | Out-File $out -Encoding utf8
Write-Output "OK $out ($($md.Length) chars) title=$title"
