<#
Full refresh of the model open in Power BI Desktop (same as Home > Refresh), through the local
engine. Used before reconciling so the numbers come from a fresh import of data/gold.
#>
$here = Split-Path $MyInvocation.MyCommand.Path
$engine = Get-CimInstance Win32_Process -Filter "Name='msmdsrv.exe'" | Select-Object -First 1
$line = netstat -ano | Select-String "LISTENING\s+$($engine.ProcessId)$" | Select-Object -First 1
$port = [int](($line.ToString().Trim() -split '\s+')[1] -split ':')[-1]
Add-Type -Path (Join-Path (Split-Path $engine.ExecutablePath) "Microsoft.PowerBI.AdomdClient.dll")
$c = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection("Data Source=localhost:$port")
$c.Open()
$cmd0 = $c.CreateCommand(); $cmd0.CommandText = "select [CATALOG_NAME] from `$SYSTEM.DBSCHEMA_CATALOGS"
$r0 = $cmd0.ExecuteReader(); $cats = @(); while ($r0.Read()) { $cats += $r0.GetValue(0) }; $r0.Close()
foreach ($cat in $cats) {
    $c.ChangeDatabase($cat)
    $t = $c.CreateCommand(); $t.CommandText = "select [Name] from `$SYSTEM.TMSCHEMA_TABLES"
    $r = $t.ExecuteReader(); $has = $r.Read(); $r.Close()
    if (-not $has) { continue }
    $cmd = $c.CreateCommand()
    $cmd.CommandText = '{"refresh":{"type":"full","objects":[{"database":"' + $cat + '"}]}}'
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $cmd.ExecuteNonQuery() | Out-Null
    "refreshed $cat in $([int]$sw.Elapsed.TotalSeconds)s"
}
$c.Close()
