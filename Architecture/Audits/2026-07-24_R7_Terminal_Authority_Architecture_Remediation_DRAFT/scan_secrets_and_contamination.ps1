[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$OutputPath,
    [string]$BuildRoot,
    [string]$MatrixRoot,
    [string[]]$AdditionalRoots = @()
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$packageRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $packageRoot '..\..\..'))
$safeRepository = $repositoryRoot.Replace('\','/')
$gitExecutable = 'C:\Program Files\Git\cmd\git.exe'
$findings = [Collections.Generic.List[object]]::new()
$fixtures = [Collections.Generic.List[object]]::new()
$files = [Collections.Generic.List[object]]::new()

function Get-LowerHash([string]$Path) { return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant() }
function Write-JsonNew([object]$Value, [string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if (Test-Path -LiteralPath $full) { throw "Refusing scan overwrite: $full" }
    $parent = Split-Path -Parent $full
    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent | Out-Null }
    [IO.File]::WriteAllText($full, ($Value | ConvertTo-Json -Depth 100), [Text.UTF8Encoding]::new($false))
}
function Is-TextFile([IO.FileInfo]$File) {
    return $File.Extension.ToLowerInvariant() -in @('.cs','.ps1','.md','.json','.txt','.il','.config','.xml','.csv','.log','.stderr','.stdout') -or $File.Name.EndsWith('.g.cs',[StringComparison]::OrdinalIgnoreCase)
}
function Add-Finding([string]$Category, [string]$Path, [string]$Evidence) { $findings.Add([ordered]@{ category = $Category; evidence = $Evidence; path = $Path }) }
function Scan-File([IO.FileInfo]$File, [string]$RootClass) {
    $extension = $File.Extension.ToLowerInvariant()
    $hash = Get-LowerHash $File.FullName
    $classification = 'NONSECRET_ARTIFACT'
    if ($extension -in @('.cer','.crt','.pub')) { $classification = 'PUBLIC_TRUST_MATERIAL' }
    if ($File.Name -match '(?i)test.*pem|pem.*test|fixture') { $classification = 'TEST_FIXTURE_NONAUTHORITY' }
    if ($extension -in @('.pfx','.p12','.pkcs12','.key') -or $File.Name -match '(?i)private[-_]?key|machine[-_]?key|signing[-_]?seed') { Add-Finding 'PROHIBITED_SECRET_FILE_TYPE_OR_NAME' $File.FullName $File.Name }
    if (Is-TextFile $File) {
        $text = [IO.File]::ReadAllText($File.FullName)
        foreach ($marker in @(('-----BEGIN ' + 'PRIVATE KEY-----'),('-----BEGIN RSA ' + 'PRIVATE KEY-----'),('-----BEGIN EC ' + 'PRIVATE KEY-----'),('-----BEGIN OPENSSH ' + 'PRIVATE KEY-----'))) { if ($text.Contains($marker)) { Add-Finding 'PRIVATE_KEY_MATERIAL' $File.FullName $marker } }
        foreach ($pattern in @(
            '(?im)^\s*(password|passwd|pwd)\s*[:=]\s*["''][^"'']{1,}["'']',
            '(?im)^\s*(access[_-]?token|api[_-]?token|client[_-]?secret|shared[_-]?secret|hmac[_-]?secret|signing[_-]?seed)\s*[:=]\s*["''][^"'']{1,}["'']',
            '(?i)authorization\s*:\s*bearer\s+[A-Za-z0-9._~+/-]{16,}',
            '(?i)AKIA[0-9A-Z]{16}'
        )) { if ([regex]::IsMatch($text,$pattern)) { Add-Finding 'CREDENTIAL_OR_TOKEN_PATTERN' $File.FullName $pattern } }
        if ($text -match '-----BEGIN (PUBLIC KEY|CERTIFICATE)-----' -and $classification -eq 'TEST_FIXTURE_NONAUTHORITY') {
            $fixtures.Add([ordered]@{ authority_path_eligible = $false; classification = $classification; path = $File.FullName; raw_sha256 = $hash })
        }
    }
    $files.Add([ordered]@{ classification = $classification; path = $File.FullName; raw_sha256 = $hash; root_class = $RootClass; size = $File.Length })
}
function Scan-Root([string]$Path, [string]$RootClass) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return }
    $full = [IO.Path]::GetFullPath($Path)
    if (-not (Test-Path -LiteralPath $full -PathType Container)) { throw "Scan root missing: $full" }
    foreach ($file in Get-ChildItem -LiteralPath $full -Recurse -File -Force | Sort-Object FullName) { Scan-File $file $RootClass }
}

Scan-Root $packageRoot 'REMEDIATION_SOURCE_AND_GOVERNANCE'
if (-not [string]::IsNullOrWhiteSpace($BuildRoot)) { Scan-Root $BuildRoot 'BUILD_AND_STAGING' }
if (-not [string]::IsNullOrWhiteSpace($MatrixRoot)) { Scan-Root $MatrixRoot 'MATRIX_EVIDENCE' }
foreach ($root in $AdditionalRoots) { Scan-Root $root 'AUTHORIZED_PUBLIC_HOST_EVIDENCE' }

$caseArtifact = Get-Content -Raw -LiteralPath (Join-Path $packageRoot 'immutable_case_definitions.json') | ConvertFrom-Json
$badAuthorityReferences = @($caseArtifact.cases | ForEach-Object { $case = $_; @($case.authority_refs) | Where-Object governing_commit -eq 'f0cfbce97e913a133530dd66a70326b1e03a0fb6' | ForEach-Object { $case.case_id } })
if ($badAuthorityReferences.Count -ne 0) { Add-Finding 'PROHIBITED_SOURCE_NORMATIVE_AUTHORITY' (Join-Path $packageRoot 'immutable_case_definitions.json') ($badAuthorityReferences -join ',') }
$coverageArtifact = Get-Content -Raw -LiteralPath (Join-Path $packageRoot 'exact_byte_coverage_proof.json') | ConvertFrom-Json
if ([int]$coverageArtifact.prohibited_source_reference_count -ne 0) { Add-Finding 'PROHIBITED_SOURCE_COVERAGE_DEPENDENCY' (Join-Path $packageRoot 'exact_byte_coverage_proof.json') ([string]$coverageArtifact.prohibited_source_reference_count) }
if (-not [string]::IsNullOrWhiteSpace($BuildRoot)) {
    $buildRootFull = [IO.Path]::GetFullPath($BuildRoot)
    $buildSummaryPath = Join-Path $buildRootFull 'static_build_summary.json'
    if (-not (Test-Path -LiteralPath $buildSummaryPath -PathType Leaf)) { $buildSummaryPath = Join-Path $buildRootFull 'build_summary.json' }
    if (-not (Test-Path -LiteralPath $buildSummaryPath -PathType Leaf)) { $buildSummaryPath = Join-Path $buildRootFull 'unit2_build_manifest.json' }
    if (-not (Test-Path -LiteralPath $buildSummaryPath -PathType Leaf)) { throw "Recognized build summary is absent: $buildRootFull" }
    $buildSummary = Get-Content -Raw -LiteralPath $buildSummaryPath | ConvertFrom-Json
    if ($buildSummary.PSObject.Properties.Name -notcontains 'prohibited_source_dependency_count') { throw "Build summary omits prohibited-source closure: $buildSummaryPath" }
    if ([int]$buildSummary.prohibited_source_dependency_count -ne 0) { Add-Finding 'PROHIBITED_SOURCE_BUILD_DEPENDENCY' $buildSummaryPath ([string]$buildSummary.prohibited_source_dependency_count) }
}
if (-not [string]::IsNullOrWhiteSpace($MatrixRoot)) {
    $matrixSummaryPath = Join-Path ([IO.Path]::GetFullPath($MatrixRoot)) 'matrix-summary.json'
    $matrixSummary = Get-Content -Raw -LiteralPath $matrixSummaryPath | ConvertFrom-Json
    if ($matrixSummary.prohibited_source_evidence_reused -ne $false) { Add-Finding 'PROHIBITED_SOURCE_MATRIX_REUSE' $matrixSummaryPath ([string]$matrixSummary.prohibited_source_evidence_reused) }
}

$stagedPaths = @(& $gitExecutable -c "safe.directory=$safeRepository" -C $repositoryRoot diff --cached --name-only --diff-filter=ACMR)
if ($LASTEXITCODE -ne 0) { throw 'Unable to enumerate staged delta.' }
foreach ($relative in $stagedPaths) {
    $full = Join-Path $repositoryRoot $relative
    if (Test-Path -LiteralPath $full -PathType Leaf) {
        $known = @($files | Where-Object path -eq $full)
        if ($known.Count -eq 0) { Scan-File (Get-Item -LiteralPath $full) 'STAGED_DELTA' }
    }
}

$privateKeyPathsRead = @($files | Where-Object { $_.path -match '(?i)\\Microsoft\\Crypto\\|\\MachineKeys\\' })
if ($privateKeyPathsRead.Count -ne 0) { Add-Finding 'PRIVATE_KEY_STORE_READ' $privateKeyPathsRead[0].path 'Private key stores are outside authorized scan roots.' }
$result = [ordered]@{
    artifact_type = 'R7_SECRET_AND_CONTAMINATION_SCAN'
    file_count = $files.Count
    files = $files.ToArray()
    finding_count = $findings.Count
    findings = $findings.ToArray()
    private_key_material_copied = $false
    private_key_store_file_count = $privateKeyPathsRead.Count
    prohibited_source_dependency_count = @($findings | Where-Object category -like 'PROHIBITED_SOURCE*').Count
    schema_version = '1.0.0'
    staged_paths = $stagedPaths
    status = $(if ($findings.Count -eq 0) { 'PASS' } else { 'FAIL' })
    test_fixtures = $fixtures.ToArray()
    test_fixtures_authority_path_eligible = $false
}
Write-JsonNew $result $OutputPath
if ($findings.Count -ne 0) { throw "Secret or contamination scan found $($findings.Count) blocking findings; evidence preserved at $OutputPath" }
Write-Output ([ordered]@{ files = $files.Count; findings = 0; output = [IO.Path]::GetFullPath($OutputPath); raw_sha256 = (Get-LowerHash $OutputPath); status = 'PASS' } | ConvertTo-Json)
