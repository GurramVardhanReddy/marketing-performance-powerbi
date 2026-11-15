<#
Run a DAX (or DMV) query against the model open in Power BI Desktop and print the rows as JSON.
Finds the running local Analysis Services engine and the ADOMD client that ships with Desktop.

  .\scripts\query_model.ps1 -Query "EVALUATE ROW(""Impressions"", [Impressions])"
#>
param([Parameter(Mandatory = $true)][string]$Query, [int]$Port = 0, [string]$Catalog = "")

$engine = Get-CimInstance Win32_Process -Filter "Name='msmdsrv.exe'" | Select-Object -First 1
if (-not $engine) { throw "Power BI Desktop is not running with a model open." }
if ($Port -eq 0) {
    $Port = (Get-NetTCPConnection -OwningProcess $engine.ProcessId -State Listen -ErrorAction SilentlyContinue |
             Select-Object -First 1).LocalPort
    if (-not $Port) {
        $line = netstat -ano | Select-String "LISTENING\s+$($engine.ProcessId)$" | Select-Object -First 1
        $Port = [int](($line.ToString().Trim() -split '\s+')[1] -split ':')[-1]
    }
}
$bin = Split-Path $engine.ExecutablePath
Add-Type -Path (Join-Path $bin "Microsoft.PowerBI.AdomdClient.dll")
$conn = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection("Data Source=localhost:$Port")
$conn.Open()
if (-not $Catalog) {
    # Desktop can hold more than one database (one may be empty); use the one with tables
    $cmd0 = $conn.CreateCommand()
    $cmd0.CommandText = "select [CATALOG_NAME] from `$SYSTEM.DBSCHEMA_CATALOGS"
    $r0 = $cmd0.ExecuteReader(); $cats = @()
    while ($r0.Read()) { $cats += $r0.GetValue(0) }
    $r0.Close()
    foreach ($cat in $cats) {
        $conn.ChangeDatabase($cat)
        $cmd1 = $conn.CreateCommand()
        $cmd1.CommandText = "select [Name] from `$SYSTEM.TMSCHEMA_TABLES"
        $r1 = $cmd1.ExecuteReader(); $has = $r1.Read(); $r1.Close()
        if ($has) { $Catalog = $cat; break }
    }
}
$conn.ChangeDatabase($Catalog)
try {
    $cmd = $conn.CreateCommand(); $cmd.CommandText = $Query
    $reader = $cmd.ExecuteReader()
    $rows = @()
    while ($reader.Read()) {
        $row = [ordered]@{}
        for ($i = 0; $i -lt $reader.FieldCount; $i++) { $row[$reader.GetName($i)] = $reader.GetValue($i) }
        $rows += [pscustomobject]$row
    }
    $reader.Close()
    ConvertTo-Json -InputObject @($rows) -Depth 3 -Compress
} finally { $conn.Close() }
