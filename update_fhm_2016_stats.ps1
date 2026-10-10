param(
  [int]$SeasonId = 5,
  [int]$TeamYear = 2016,
  [int]$BirthYear = 2016,
  [int]$Limit = 50,
  [int]$DelayMs = 120,
  [string]$OutputJson = "all_2016_players_season5.json",
  [string]$OutputJs = "all_2016_players_season5.js"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Invoke-FhmPost {
  param(
    [string]$Uri,
    [hashtable]$Body,
    [int]$Retries = 3
  )

  for ($attempt = 1; $attempt -le $Retries; $attempt++) {
    try {
      $payload = $Body | ConvertTo-Json -Compress
      return Invoke-RestMethod -Uri $Uri -Method Post -ContentType "application/json" -Body $payload
    }
    catch {
      if ($attempt -ge $Retries) {
        throw
      }
      Start-Sleep -Milliseconds (350 * $attempt)
    }
  }
}

function Invoke-FhmGet {
  param(
    [string]$Uri,
    [int]$Retries = 3
  )

  for ($attempt = 1; $attempt -le $Retries; $attempt++) {
    try {
      return Invoke-RestMethod -Uri $Uri -Method Get
    }
    catch {
      if ($attempt -ge $Retries) {
        throw
      }
      Start-Sleep -Milliseconds (350 * $attempt)
    }
  }
}

if ($Limit -lt 1 -or $Limit -gt 50) {
  throw "Limit must be in range 1..50"
}

$teams = @()
$offset = 0

while ($true) {
  $teamResponse = Invoke-FhmPost -Uri "https://fhmoscow.com/api/team/list" -Body @{
    season = $SeasonId
    year   = $TeamYear
    limit  = $Limit
    offset = $offset
  }

  $items = @($teamResponse.items)
  if ($items.Count -eq 0) {
    break
  }

  $teams += $items
  $offset += $items.Count

  if ($teams.Count -ge [int]$teamResponse.count) {
    break
  }
}

$rows = @()
$yearSuffix = ".{0}$" -f $BirthYear

for ($index = 0; $index -lt $teams.Count; $index++) {
  $team = $teams[$index]
  $teamId = [int]$team.id
  $teamName = [string]$team.shortName
  Write-Host ("[{0}/{1}] {2}" -f ($index + 1), $teams.Count, $teamName)

  $groupName = "-"
  try {
    $filterData = Invoke-FhmPost -Uri "https://fhmoscow.com/api/filter/data" -Body @{
      season = $SeasonId
      team   = $teamId
    }

    $groups = @($filterData.group)
    if ($groups.Count -gt 0) {
      $currentGroup = $groups | Where-Object { $_.current -eq $true } | Select-Object -First 1
      if ($null -eq $currentGroup) {
        $currentGroup = $groups | Select-Object -First 1
      }
      if ($null -ne $currentGroup -and $currentGroup.name) {
        $groupName = [string]$currentGroup.name
      }
    }
  }
  catch {
    $groupName = "-"
  }

  $rosterResponse = Invoke-FhmGet -Uri ("https://fhmoscow.com/api/team/{0}/player?season={1}" -f $teamId, $SeasonId)
  $players = if ($rosterResponse -is [array]) { @($rosterResponse) } else { @($rosterResponse.value) }

  foreach ($player in $players) {
    $dob = [string]$player.dateOfBirth
    if ($dob -notmatch $yearSuffix) {
      continue
    }

    $games = 0
    $goals = 0

    if ($null -ne $player.statistics) {
      if ($player.statistics.PSObject.Properties.Name -contains "gamesCount") {
        $games = [int]$player.statistics.gamesCount
      }
      if ($player.statistics.PSObject.Properties.Name -contains "totalGoals") {
        $goals = [int]$player.statistics.totalGoals
      }
    }

    $rows += [pscustomobject]@{
      player = [string]$player.fullName
      group  = $groupName
      team   = $teamName
      games  = $games
      goals  = $goals
    }
  }

  if ($DelayMs -gt 0) {
    Start-Sleep -Milliseconds $DelayMs
  }
}

$rows = $rows | Sort-Object @{ Expression = "goals"; Descending = $true }, @{ Expression = "games"; Descending = $true }, @{ Expression = "player"; Descending = $false }

$json = $rows | ConvertTo-Json -Depth 4
Set-Content -Path $OutputJson -Value $json -Encoding utf8
Set-Content -Path $OutputJs -Value ("window.playerGoalsData = " + $json + ";") -Encoding utf8

Write-Host ""
Write-Host ("Teams processed: {0}" -f $teams.Count)
Write-Host ("Player rows: {0}" -f $rows.Count)
Write-Host ("JSON: {0}" -f (Resolve-Path $OutputJson))
Write-Host ("JS:   {0}" -f (Resolve-Path $OutputJs))
Write-Host ""
$rows | Select-Object -First 10 | Format-Table -AutoSize | Out-String | Write-Host
