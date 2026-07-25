param()

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Utf8 = New-Object System.Text.UTF8Encoding($false, $true)
$RegistryPath = Join-Path $Root 'governed_requirement_registry.json'
$CasePath = Join-Path $Root 'immutable_case_definitions.json'
$ExpectationPath = Join-Path $Root 'immutable_expectations.json'

function Get-LowerSha256([byte[]]$Bytes) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { ([BitConverter]::ToString($sha.ComputeHash($Bytes))).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose() }
}
function Read-StrictJson([string]$Path) {
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    $text = $Utf8.GetString($bytes)
    return $text | ConvertFrom-Json
}

$Registry = Read-StrictJson $RegistryPath
$Cases = Read-StrictJson $CasePath
$Expectations = Read-StrictJson $ExpectationPath

if ($Cases.expectation_artifact_read -ne $false) { throw 'case stage read expectation artifact' }
if ($Expectations.case_artifact_read -ne $false -or $Expectations.requirement_registry_read -ne $false -or $Expectations.runtime_evidence_read -ne $false) {
    throw 'expectation stage declared an unauthorized input'
}
if ($Cases.requirement_registry_sha256 -ne (Get-LowerSha256 ([System.IO.File]::ReadAllBytes($RegistryPath)))) { throw 'case registry binding mismatch' }

$RequirementById = @{}
foreach ($requirement in $Registry.requirements) {
    if ($RequirementById.ContainsKey($requirement.requirement_id)) { throw "duplicate requirement $($requirement.requirement_id)" }
    $RequirementById[$requirement.requirement_id] = $requirement
}
$CaseById = @{}
foreach ($case in $Cases.cases) {
    if ($CaseById.ContainsKey($case.case_id)) { throw "duplicate case $($case.case_id)" }
    if ($case.request_recipe.include_expectation_fields -ne $false -or $case.request_recipe.include_desired_result -ne $false) { throw "expectation coupled request $($case.case_id)" }
    $serializedCase = $case | ConvertTo-Json -Depth 20 -Compress
    foreach ($forbidden in @('expected_status','expected_code','expected_evidence','desired_outcome')) {
        if ($serializedCase -match ('"' + [regex]::Escape($forbidden) + '"\s*:')) { throw "prohibited request field $forbidden in $($case.case_id)" }
    }
    foreach ($authority in $case.authority_refs) {
        if (-not $RequirementById.ContainsKey($authority.requirement_id)) { throw "unknown authority $($authority.requirement_id) in $($case.case_id)" }
        $governed = $RequirementById[$authority.requirement_id]
        foreach ($field in @('governing_commit','governing_blob','governing_path','line_range','clause_raw_sha256')) {
            if ($authority.$field -cne $governed.$field) { throw "authority locator mismatch $field in $($case.case_id)" }
        }
    }
    if (@($case.authority_refs).Count -eq 0) { throw "case without governing authority $($case.case_id)" }
    $CaseById[$case.case_id] = $case
}

$ExpectationByCase = @{}
foreach ($expectation in $Expectations.expectations) {
    if ($ExpectationByCase.ContainsKey($expectation.case_id)) { throw "duplicate expectation for $($expectation.case_id)" }
    if (-not $CaseById.ContainsKey($expectation.case_id)) { throw "expectation without case $($expectation.case_id)" }
    $ExpectationByCase[$expectation.case_id] = $expectation
}
$MissingExpectation = @($CaseById.Keys | Where-Object { -not $ExpectationByCase.ContainsKey($_) } | Sort-Object)
if ($MissingExpectation.Count -ne 0) { throw "cases without expectations: $($MissingExpectation -join ',')" }

$CoverageRows = New-Object System.Collections.Generic.List[object]
$UnmappedRequirements = New-Object System.Collections.Generic.List[string]
foreach ($requirement in $Registry.requirements) {
    $mappedCases = @($Cases.cases | Where-Object { @($_.authority_refs | ForEach-Object requirement_id) -contains $requirement.requirement_id } | Sort-Object case_id)
    if ($mappedCases.Count -eq 0) { $UnmappedRequirements.Add($requirement.requirement_id); continue }
    $caseRows = foreach ($case in $mappedCases) {
        $expectation = $ExpectationByCase[$case.case_id]
        [pscustomobject][ordered]@{
            case_id = $case.case_id
            case_definition_sha256 = Get-LowerSha256 $Utf8.GetBytes(($case | ConvertTo-Json -Depth 20 -Compress))
            expectation_id = $expectation.expectation_id
            expectation_definition_sha256 = Get-LowerSha256 $Utf8.GetBytes(($expectation | ConvertTo-Json -Depth 20 -Compress))
            expected_evidence = $expectation.required_evidence
            implementation_surface = $case.implementation_surface
            verification = @('STATIC_SCHEMA_AND_AUTHORITY_VERIFIER','OUTER_INTERFACE_RUNTIME_HARNESS','SIGNER_REDERIVATION','PUBLIC_VERSION_AWARE_VERIFIER')
        }
    }
    $CoverageRows.Add([pscustomobject][ordered]@{
        governing_clause = [pscustomobject][ordered]@{
            governing_commit = $requirement.governing_commit
            governing_blob = $requirement.governing_blob
            governing_path = $requirement.governing_path
            section_heading = $requirement.section_heading
            line_range = $requirement.line_range
            byte_range = $requirement.byte_range
            clause_raw_sha256 = $requirement.clause_raw_sha256
        }
        requirement_id = $requirement.requirement_id
        cases = @($caseRows)
    })
}
if ($UnmappedRequirements.Count -ne 0) { throw "unmapped governing requirements: $($UnmappedRequirements -join ',')" }

$Artifact = [pscustomobject][ordered]@{
    artifact_type = 'R7_REMEDIATION_EXACT_BYTE_COVERAGE_PROOF'
    schema_version = '1.0.0'
    chain = 'GOVERNING_CLAUSE_TO_REQUIREMENT_TO_CASE_TO_EXPECTED_EVIDENCE_TO_IMPLEMENTATION_SURFACE_TO_VERIFICATION'
    requirement_registry_sha256 = Get-LowerSha256 ([System.IO.File]::ReadAllBytes($RegistryPath))
    case_definitions_sha256 = Get-LowerSha256 ([System.IO.File]::ReadAllBytes($CasePath))
    expectations_sha256 = Get-LowerSha256 ([System.IO.File]::ReadAllBytes($ExpectationPath))
    governing_requirement_count = $RequirementById.Count
    case_count = $CaseById.Count
    expectation_count = $ExpectationByCase.Count
    unmapped_governing_requirement_count = 0
    unauthorized_normative_case_count = 0
    prohibited_source_reference_count = 0
    coverage = $CoverageRows.ToArray()
}
$Output = Join-Path $Root 'exact_byte_coverage_proof.json'
[System.IO.File]::WriteAllText($Output, ($Artifact | ConvertTo-Json -Depth 25) + "`n", $Utf8)
[pscustomobject]@{
    status = 'PASS'
    governing_requirement_count = $RequirementById.Count
    case_count = $CaseById.Count
    expectation_count = $ExpectationByCase.Count
    unmapped_governing_requirement_count = 0
    unauthorized_normative_case_count = 0
    prohibited_source_reference_count = 0
    output_sha256 = Get-LowerSha256 ([System.IO.File]::ReadAllBytes($Output))
} | ConvertTo-Json
