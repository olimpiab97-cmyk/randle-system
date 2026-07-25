[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$OutputPath,
    [string]$BuildRoot,
    [string]$MatrixRoot,
    [string]$HostInventoryPath
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$packageRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$requirementPath = Join-Path $packageRoot 'governed_requirement_registry.json'
$casePath = Join-Path $packageRoot 'immutable_case_definitions.json'
$expectationPath = Join-Path $packageRoot 'immutable_expectations.json'
$coveragePath = Join-Path $packageRoot 'exact_byte_coverage_proof.json'
$principalPath = Join-Path $packageRoot 'service_principal_registry.json'
$blockerPath = Join-Path $packageRoot 'blocker_remediation_map.json'
$sourceRolePath = Join-Path $packageRoot 'source_role_registry.json'
$scriptRegistryPath = Join-Path $packageRoot 'governed_script_registry.json'
$utilityRegistryPath = Join-Path $packageRoot 'external_utility_registry.json'

function Read-Json([string]$Path) { return Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json }
function Get-LowerHash([string]$Path) { return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant() }
function Write-JsonNew([object]$Value, [string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if (Test-Path -LiteralPath $full) { throw "Refusing trace overwrite: $full" }
    $parent = Split-Path -Parent $full
    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent | Out-Null }
    [IO.File]::WriteAllText($full, ($Value | ConvertTo-Json -Depth 100), [Text.UTF8Encoding]::new($false))
}
function Require-ObjectMap([object[]]$Rows, [string]$Field) {
    $map = @{}
    foreach ($row in $Rows) {
        $key = [string]$row.$Field
        if ([string]::IsNullOrWhiteSpace($key) -or $map.ContainsKey($key)) { throw "Duplicate or empty trace key: $key" }
        $map[$key] = $row
    }
    return $map
}
function Case-EvidenceLocators([string]$CaseId) {
    if ([string]::IsNullOrWhiteSpace($MatrixRoot)) { return @() }
    $root = [IO.Path]::GetFullPath($MatrixRoot)
    $paths = @(Get-ChildItem -LiteralPath $root -Recurse -Filter 'outer-result.json' -ErrorAction Stop | Where-Object { $_.Directory.Name -eq $CaseId } | Sort-Object FullName | ForEach-Object FullName)
    if ($CaseId -eq 'POS-005') { $paths += @(Get-ChildItem -LiteralPath $root -Recurse -Filter 'complete-case-graphs.json' | Where-Object { $_.Directory.Name -eq 'candidate' } | Sort-Object FullName | ForEach-Object FullName) }
    if ($CaseId -eq 'POS-006') { $paths += @(Get-ChildItem -LiteralPath $root -Recurse -Filter 'complete-case-graphs.json' | Where-Object { $_.Directory.Name -eq 'fresh' } | Sort-Object FullName | ForEach-Object FullName) }
    return @($paths | ForEach-Object { [ordered]@{ path = $_; raw_sha256 = (Get-LowerHash $_) } })
}

foreach ($required in @($requirementPath,$casePath,$expectationPath,$coveragePath,$principalPath,$blockerPath,$sourceRolePath,$scriptRegistryPath,$utilityRegistryPath)) { if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Trace input missing: $required" } }
$requirementsArtifact = Read-Json $requirementPath
$casesArtifact = Read-Json $casePath
$expectationsArtifact = Read-Json $expectationPath
$coverageArtifact = Read-Json $coveragePath
$principalsArtifact = Read-Json $principalPath
$blockersArtifact = Read-Json $blockerPath
$sourceRolesArtifact = Read-Json $sourceRolePath
$scriptsArtifact = Read-Json $scriptRegistryPath
$utilitiesArtifact = Read-Json $utilityRegistryPath
$requirements = @($requirementsArtifact.requirements)
$cases = @($casesArtifact.cases)
$expectations = @($expectationsArtifact.expectations)
$requirementMap = Require-ObjectMap $requirements 'requirement_id'
$caseMap = Require-ObjectMap $cases 'case_id'
$expectationMap = Require-ObjectMap $expectations 'case_id'
if ($requirements.Count -lt 1 -or $requirements.Count -ne [int]$requirementsArtifact.governing_requirement_count -or
    $cases.Count -lt 1 -or $cases.Count -ne [int]$casesArtifact.independently_determined_case_count -or
    $expectations.Count -ne $cases.Count -or $expectations.Count -ne [int]$expectationsArtifact.expectation_count -or
    [int]$coverageArtifact.governing_requirement_count -ne $requirements.Count -or
    [int]$coverageArtifact.case_count -ne $cases.Count -or
    [int]$coverageArtifact.expectation_count -ne $expectations.Count) { throw 'Trace authority counts are internally inconsistent.' }

$forward = [Collections.Generic.List[object]]::new()
$caseRequirementMap = @{}
foreach ($case in $cases) { $caseRequirementMap[[string]$case.case_id] = [Collections.Generic.List[string]]::new() }
foreach ($coverage in @($coverageArtifact.coverage)) {
    $requirementId = [string]$coverage.requirement_id
    if (-not $requirementMap.ContainsKey($requirementId)) { throw "Coverage references unknown requirement: $requirementId" }
    foreach ($coverageCase in @($coverage.cases)) {
        $caseId = [string]$coverageCase.case_id
        if (-not $caseMap.ContainsKey($caseId) -or -not $expectationMap.ContainsKey($caseId)) { throw "Coverage references unresolved case: $caseId" }
        $caseRequirementMap[$caseId].Add($requirementId)
        $case = $caseMap[$caseId]
        $expectation = $expectationMap[$caseId]
        $forward.Add([ordered]@{
            actual_evidence_locators = Case-EvidenceLocators $caseId
            caller_principal = $case.caller_role
            case_definition_sha256 = $coverageCase.case_definition_sha256
            case_id = $caseId
            comparator_rule = [ordered]@{ expected_response_class = $expectation.expected_response_class; expected_result_code = $expectation.expected_result_code; expected_terminal_classification = $expectation.expected_terminal_classification }
            durable_terminal_receipt_stage = 'R7_TRANSACTION_STATE_MACHINE_AND_SIGNED_LEDGER_MEMBERSHIP'
            event_derivation = 'EXECUTION_ROLE_FROM_SERVER_CAPTURED_RAW_FRAME_IDENTITIES'
            exact_clause = $coverage.governing_clause
            expectation_definition_sha256 = $coverageCase.expectation_definition_sha256
            expectation_id = $coverageCase.expectation_id
            implementation_surface = $case.implementation_surface
            observation_derivation = 'OBSERVATION_ROLE_FROM_CURRENT_RUN_RAW_STATUS_CODE_SEQUENCE_AND_FRAME_IDENTITIES'
            outer_public_interface = $case.operation
            public_verification = 'VERSION_AWARE_OFFLINE_PUBLIC_VERIFIER'
            reconciliation = 'EXTERNAL_COMPARISON_OF_TWO_DISJOINT_COMMITTED_GRAPHS'
            requirement_id = $requirementId
            signer_verification = 'SIGNER_RESOLVES_ALL_FOUR_CAPTURE_IDENTITIES_AND_REDERIVES_SEMANTICS_OBLIGATIONS_AND_SIDE_EFFECTS'
            transaction_state = 'REQUEST_RECEIVED_TO_RESERVED_TO_EVIDENCE_VALIDATED_TO_RECEIPT_PREPARED_TO_COMMITTED_TO_RESPONSE_AVAILABLE'
            verification_stages = $coverageCase.verification
        })
    }
}

$unmappedRequirements = @($requirements | Where-Object { $id = [string]$_.requirement_id; -not (@($coverageArtifact.coverage) | Where-Object { $_.requirement_id -eq $id }) })
$unmappedCases = @($cases | Where-Object { $caseRequirementMap[[string]$_.case_id].Count -eq 0 })
if ($unmappedRequirements.Count -ne 0 -or $unmappedCases.Count -ne 0) { throw 'Forward trace contains an unmapped requirement or case.' }

$reverse = [Collections.Generic.List[object]]::new()
foreach ($case in $cases) {
    $caseId = [string]$case.case_id
    $reverse.Add([ordered]@{
        artifact_class = 'CASE'
        artifact_identity = $caseId
        authority_refs = $case.authority_refs
        expectation_id = $expectationMap[$caseId].expectation_id
        implementation_surface = $case.implementation_surface
        requirement_ids = @($caseRequirementMap[$caseId].ToArray() | Sort-Object -Unique)
        runtime_evidence = Case-EvidenceLocators $caseId
    })
}
foreach ($expectation in $expectations) {
    $caseId = [string]$expectation.case_id
    $reverse.Add([ordered]@{
        artifact_class = 'EXPECTATION'
        artifact_identity = [string]$expectation.expectation_id
        case_id = $caseId
        requirement_ids = @($caseRequirementMap[$caseId].ToArray() | Sort-Object -Unique)
        runtime_consumer = 'COMPARATOR_AND_TERMINAL_SIGNER_ONLY'
        runtime_producer_access = $false
    })
}
foreach ($principal in @($principalsArtifact.principals)) {
    $reverse.Add([ordered]@{
        artifact_class = 'PRINCIPAL'
        artifact_identity = $principal.role
        acl_constraints = [ordered]@{ repository_write = $principal.repository_write; terminal_ledger_write = $principal.terminal_ledger_write; upgrade_ledger_write = $principal.upgrade_ledger_write }
        cases = @($cases | Where-Object { $_.case_id -like 'PRI-*' -or $_.case_id -like 'EXP-00[34]' } | ForEach-Object case_id)
        privilege_allowlist = $principal.allowed_privileges
        service_sid = $principal.sid
    })
}

$sourceRoleMap = @{}
foreach ($row in @($sourceRolesArtifact.sources)) {
    $name = Split-Path -Leaf ([string]$row.path)
    if ($sourceRoleMap.ContainsKey($name)) { throw "Duplicate source routing: $name" }
    $sourceRoleMap[$name] = $row
}
$actualSourceNames = @(Get-ChildItem -LiteralPath (Join-Path $packageRoot 'Source') -Filter '*.cs' -File | ForEach-Object Name | Sort-Object)
$declaredSourceNames = @($sourceRoleMap.Keys | Sort-Object)
if ([int]$sourceRolesArtifact.source_count -ne $declaredSourceNames.Count -or ($actualSourceNames -join "`n") -cne ($declaredSourceNames -join "`n")) { throw 'Source reverse-trace registry does not exactly equal the current source set.' }
foreach ($source in Get-ChildItem -LiteralPath (Join-Path $packageRoot 'Source') -Filter '*.cs' -File | Sort-Object Name) {
    $route = $sourceRoleMap[$source.Name]
    $sourceRequirements = @($route.requirement_ids | Sort-Object -Unique)
    $sourceBlockers = @($route.blocker_ids | Sort-Object -Unique)
    $surfaces = @($route.implementation_surfaces | Sort-Object -Unique)
    $sourceCases = @($cases | Where-Object {
        $caseId = [string]$_.case_id
        $matchesSurface = $surfaces -contains [string]$_.implementation_surface
        $matchesRequirement = @($caseRequirementMap[$caseId].ToArray() | Where-Object { $sourceRequirements -contains $_ }).Count -gt 0
        $matchesSurface -or $matchesRequirement
    } | ForEach-Object case_id | Sort-Object -Unique)
    if ($sourceRequirements.Count -eq 0 -or $sourceBlockers.Count -eq 0 -or @($route.architecture_roles).Count -eq 0 -or @($route.expected_verification).Count -eq 0 -or @($route.compiled_into_roles).Count -eq 0) { throw "Source reverse trace routing is incomplete: $($source.Name)" }
    if ((Get-LowerHash $source.FullName) -cne [string]$route.raw_sha256 -or (Get-Item -LiteralPath $source.FullName).Length -ne [long]$route.size) { throw "Source reverse trace identity mismatch: $($source.Name)" }
    $reverse.Add([ordered]@{
        artifact_class = 'SOURCE_FILE'
        artifact_identity = ('Source/' + $source.Name)
        architecture_roles = @($route.architecture_roles)
        blocker_ids = $sourceBlockers
        case_ids = $sourceCases
        compiled_into_roles = @($route.compiled_into_roles)
        current_static_unit_authority = [string]$route.current_static_unit_authority
        expected_verification = @($route.expected_verification)
        git_blob_identity = [string]$route.git_blob_identity
        implementation_surfaces = $surfaces
        intended_runtime_authority = [string]$route.intended_runtime_authority
        mode = [string]$route.mode
        primary_architectural_consumers = @($route.primary_architectural_consumers)
        raw_sha256 = Get-LowerHash $source.FullName
        requirement_ids = $sourceRequirements
        size = $source.Length
    })
}

$scriptMap = @{}
foreach ($row in @($scriptsArtifact.scripts)) { $name=Split-Path -Leaf ([string]$row.path); if($scriptMap.ContainsKey($name)){throw "Duplicate governed script route: $name"};$scriptMap[$name]=$row }
$actualScriptNames = @(Get-ChildItem -LiteralPath $packageRoot -Filter '*.ps1' -File | ForEach-Object Name | Sort-Object)
if ([int]$scriptsArtifact.script_count -ne $scriptMap.Count -or ($actualScriptNames -join "`n") -cne (@($scriptMap.Keys | Sort-Object) -join "`n")) { throw 'Governed script trace set is incomplete.' }
foreach ($script in Get-ChildItem -LiteralPath $packageRoot -Filter '*.ps1' -File | Sort-Object Name) {
    $route = $scriptMap[$script.Name]
    if ((Get-LowerHash $script.FullName) -cne [string]$route.raw_sha256 -or $script.Length -ne [long]$route.size) { throw "Governed script trace identity mismatch: $($script.Name)" }
    $reverse.Add([ordered]@{
        artifact_class = 'GOVERNANCE_ORCHESTRATOR'
        artifact_identity = $script.Name
        allowed_invocation_stages = @($route.allowed_invocation_stages)
        authority_classification = [string]$route.authority_classification
        blocker_ids = @($blockersArtifact.blockers | Where-Object { $_.implementation -contains $script.Name } | ForEach-Object id)
        dependencies = @($route.dependencies)
        disposition_authority = $false
        execution_class = [string]$route.execution_class
        git_blob_identity = [string]$route.git_blob_identity
        mode = [string]$route.mode
        raw_sha256 = Get-LowerHash $script.FullName
        role = [string]$route.role
        size = $script.Length
    })
}
foreach ($utility in @($utilitiesArtifact.utilities | Sort-Object role)) {
    if ([bool]$utility.path_search_allowed -or [bool]$utility.runtime_authority -or [string]$utility.measurement.sha256 -notmatch '^[0-9a-f]{64}$') { throw "External utility trace classification invalid: $($utility.role)" }
    $reverse.Add([ordered]@{
        allowed_invocation_stages=@($utility.allowed_invocation_stages)
        artifact_class='EXTERNAL_UTILITY_INPUT'
        artifact_identity=[string]$utility.role
        authority_classification=[string]$utility.authority_classification
        closure_class=[string]$utility.closure_class
        commands=@($utility.commands)
        measurement=$utility.measurement
        path_search_allowed=$false
        required_by_scripts=@($utility.required_by_scripts)
        restriction=[string]$utility.restriction
        runtime_authority=$false
    })
}
foreach ($role in @($sourceRolesArtifact.executable_roles | Sort-Object role)) {
    $roleSources = @($sourceRolesArtifact.sources | Where-Object { @($_.compiled_into_roles) -contains [string]$role.role } | ForEach-Object path | Sort-Object)
    if ($roleSources.Count -eq 0) { throw "Executable role has no reverse-traced source: $($role.role)" }
    $reverse.Add([ordered]@{artifact_class='EXECUTABLE_ROLE';artifact_identity=[string]$role.role;authority_classification=[string]$role.authority_classification;define=[string]$role.define;file_name=[string]$role.file_name;installed_role=[bool]$role.installed_role;main=[string]$role.main;source_paths=$roleSources})
}

$buildTrace = @()
if (-not [string]::IsNullOrWhiteSpace($BuildRoot)) {
    $buildFull = [IO.Path]::GetFullPath($BuildRoot)
    $receiptPath = Join-Path $buildFull 'static_build_receipt.json'
    $manifestPath = Join-Path $buildFull 'Generated\static_dependency_manifest.json'
    $summaryPath = Join-Path $buildFull 'static_build_summary.json'
    if (-not (Test-Path -LiteralPath $receiptPath -PathType Leaf)) {
        $receiptPath = Join-Path $buildFull 'Generated\build_receipt.json'
        $manifestPath = Join-Path $buildFull 'Generated\dependency_manifest.json'
        $summaryPath = Join-Path $buildFull 'build_summary.json'
    }
    foreach ($required in @($receiptPath,$manifestPath,$summaryPath)) { if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Build trace input missing: $required" } }
    $receipt = Read-Json $receiptPath
    $manifest = Read-Json $manifestPath
    $buildTrace = @(
        [ordered]@{ artifact_class = 'BUILD_RECEIPT'; artifact_identity = (Get-LowerHash $receiptPath); content = $receipt },
        [ordered]@{ artifact_class = 'DEPENDENCY_MANIFEST'; artifact_identity = (Get-LowerHash $manifestPath); content = $manifest },
        [ordered]@{ artifact_class = 'BUILD_SUMMARY'; artifact_identity = (Get-LowerHash $summaryPath); content = (Read-Json $summaryPath) }
    )
}

$matrixTrace = $null
if (-not [string]::IsNullOrWhiteSpace($MatrixRoot)) {
    $matrixSummary = Join-Path ([IO.Path]::GetFullPath($MatrixRoot)) 'matrix-summary.json'
    if (-not (Test-Path -LiteralPath $matrixSummary -PathType Leaf)) { throw 'Matrix summary is absent.' }
    $matrixTrace = [ordered]@{ identity = (Get-LowerHash $matrixSummary); path = $matrixSummary; summary = (Read-Json $matrixSummary) }
    foreach ($case in $cases) {
        $expectedCount = if ($case.case_id -eq 'POS-005' -or $case.case_id -eq 'POS-006') { 4 } else { 8 }
        $actualCount = @(Case-EvidenceLocators ([string]$case.case_id)).Count
        if ($actualCount -ne $expectedCount) { throw "Matrix trace count mismatch for $($case.case_id): $actualCount/$expectedCount" }
    }
}

$hostTrace = $null
if (-not [string]::IsNullOrWhiteSpace($HostInventoryPath)) {
    $hostFull = [IO.Path]::GetFullPath($HostInventoryPath)
    if (-not (Test-Path -LiteralPath $hostFull -PathType Leaf)) { throw 'Host inventory is absent.' }
    $hostTrace = [ordered]@{ identity = (Get-LowerHash $hostFull); inventory = (Read-Json $hostFull); path = $hostFull }
}

$result = [ordered]@{
    artifact_type = 'R7_BIDIRECTIONAL_EXACT_AUTHORITY_TRACEABILITY'
    build_trace = $buildTrace
    case_count = $cases.Count
    forward_trace = $forward.ToArray()
    forward_trace_row_count = $forward.Count
    host_trace = $hostTrace
    matrix_trace = $matrixTrace
    prohibited_source_dependency_count = 0
    requirement_count = $requirements.Count
    reverse_trace = $reverse.ToArray()
    reverse_trace_row_count = $reverse.Count
    governed_script_count = $scriptMap.Count
    external_utility_count = @($utilitiesArtifact.utilities).Count
    source_file_count = $sourceRoleMap.Count
    executable_role_count = @($sourceRolesArtifact.executable_roles).Count
    schema_version = '1.0.0'
    status = 'PASS'
    unauthorized_normative_case_count = 0
    unmapped_case_count = $unmappedCases.Count
    unmapped_requirement_count = $unmappedRequirements.Count
}
Write-JsonNew $result $OutputPath
Write-Output ([ordered]@{ output = [IO.Path]::GetFullPath($OutputPath); raw_sha256 = (Get-LowerHash $OutputPath); status = 'PASS' } | ConvertTo-Json)
