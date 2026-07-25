[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ArtifactTool,
    [switch]$GenerateRegistries,
    [switch]$GeneratePackageManifest
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$packageRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $packageRoot '..\..\..'))
$packageRelativeRoot = 'Architecture/Audits/2026-07-24_R7_Terminal_Authority_Architecture_Remediation_DRAFT'
$artifactToolFull = [IO.Path]::GetFullPath($ArtifactTool)
$measurementRoot = Join-Path $packageRoot ('Build\StaticRegistryMeasurements_' + [DateTime]::UtcNow.ToString('yyyyMMddHHmmss'))

function Get-LowerHash([string]$Path) { return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant() }
function Get-RelativePath([string]$Base, [string]$Path) {
    $baseFull = [IO.Path]::GetFullPath($Base).TrimEnd('\') + '\'
    $pathFull = [IO.Path]::GetFullPath($Path)
    return [Uri]::UnescapeDataString(([Uri]$baseFull).MakeRelativeUri([Uri]$pathFull).ToString()).Replace('\','/')
}
function Get-GitBlobIdentity([string]$Path) {
    $bytes = [IO.File]::ReadAllBytes($Path)
    $header = [Text.Encoding]::ASCII.GetBytes(('blob ' + $bytes.Length + [char]0))
    $all = New-Object byte[] ($header.Length + $bytes.Length)
    [Buffer]::BlockCopy($header,0,$all,0,$header.Length)
    [Buffer]::BlockCopy($bytes,0,$all,$header.Length,$bytes.Length)
    $sha = [Security.Cryptography.SHA1]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($all))).Replace('-','').ToLowerInvariant() }
    finally { $sha.Dispose() }
}
function Write-CanonicalNew([object]$Value, [string]$Path, [string]$Label) {
    $full = [IO.Path]::GetFullPath($Path)
    if (Test-Path -LiteralPath $full) { throw "$Label already exists: $full" }
    if (-not (Test-Path -LiteralPath $measurementRoot)) { New-Item -ItemType Directory -Path $measurementRoot | Out-Null }
    $raw = Join-Path $measurementRoot ($Label + '.raw.json')
    [IO.File]::WriteAllText($raw, ($Value | ConvertTo-Json -Depth 100), [Text.UTF8Encoding]::new($false))
    & $artifactToolFull canonicalize $raw $full | Out-Null
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $full -PathType Leaf)) { throw "Canonical registry write failed: $Label" }
}
function New-ScriptDefinition([string]$Name,[string]$Role,[string[]]$Stages,[string]$ExecutionClass,[string[]]$Dependencies,[string]$AuthorityClass) {
    return [ordered]@{ authority_classification=$AuthorityClass; dependencies=$Dependencies; execution_class=$ExecutionClass; name=$Name; role=$Role; stages=$Stages }
}
function New-SourceDefinition([string]$Name,[string[]]$ArchitectureRoles,[string[]]$Blockers,[string[]]$Surfaces,[string[]]$Verification,[string]$IntendedAuthority,[string[]]$Consumers) {
    return [ordered]@{ architecture_roles=$ArchitectureRoles; blockers=$Blockers; consumers=$Consumers; implementation_surfaces=$Surfaces; intended_authority=$IntendedAuthority; name=$Name; verification=$Verification }
}
function New-UtilityDefinition([string]$Role,[string]$Path,[string[]]$Stages,[string[]]$Scripts,[string]$Restriction,[string]$Classification,[string]$ClosureClass,[string[]]$Commands) {
    return [ordered]@{ authority_classification=$Classification; closure_class=$ClosureClass; commands=$Commands; path=$Path; required_by_scripts=$Scripts; restriction=$Restriction; role=$Role; stages=$Stages }
}

if (-not $GenerateRegistries -and -not $GeneratePackageManifest) { throw 'Select GenerateRegistries or GeneratePackageManifest.' }
if (-not (Test-Path -LiteralPath $artifactToolFull -PathType Leaf)) { throw 'Artifact tool is absent.' }

if ($GenerateRegistries) {
    $scriptDefinitions = @(
        (New-ScriptDefinition 'author_cases.ps1' 'CASE_AUTHORING' @('PRECOMMIT_AUTHORITY_GENERATION') 'BUILD_TIME' @('POWERSHELL_ORCHESTRATOR') 'NONAUTHORITATIVE_GOVERNANCE_DERIVATION'),
        (New-ScriptDefinition 'author_expectations.ps1' 'EXPECTATION_AUTHORING' @('PRECOMMIT_AUTHORITY_GENERATION') 'BUILD_TIME' @('POWERSHELL_ORCHESTRATOR') 'NONAUTHORITATIVE_INDEPENDENT_EXPECTATION_DERIVATION'),
        (New-ScriptDefinition 'build_remediation_package.ps1' 'TERMINAL_TARGET_BUILD' @('UNIT2_TARGET_BUILD','FUTURE_POSTCOMMIT_BUILD') 'BUILD_TIME' @('POWERSHELL_ORCHESTRATOR','CSC_COMPILER','ILDASM_TOOL','GIT_BUILD_AND_VERIFICATION','ARTIFACT_TOOL_BUILD_OUTPUT') 'UNIT2_CONTENT_ADDRESSED_UNINSTALLED_TERMINAL_TARGET_BUILD'),
        (New-ScriptDefinition 'build_static_closure.ps1' 'STATIC_CLOSURE_BUILD' @('PRECOMMIT_STATIC_BUILD','DETACHED_POSTCOMMIT_STATIC_BUILD') 'BUILD_TIME' @('POWERSHELL_ORCHESTRATOR','CSC_COMPILER','ILDASM_TOOL','GIT_BUILD_AND_VERIFICATION','ARTIFACT_TOOL_BUILD_OUTPUT') 'NONAUTHORITATIVE_STATIC_COMPILE_EVIDENCE'),
        (New-ScriptDefinition 'build_unit2_upgrade_authority.ps1' 'UNIT2_UPGRADE_AUTHORITY_BUILD' @('UNIT2_POSTCOMMIT_BUILD') 'BUILD_TIME' @('POWERSHELL_ORCHESTRATOR','CSC_COMPILER','ILDASM_TOOL','GIT_BUILD_AND_VERIFICATION','ARTIFACT_TOOL_BUILD_OUTPUT') 'UNIT2_CONTENT_BOUND_BUILD_ORCHESTRATION'),
        (New-ScriptDefinition 'capture_remediation_host_state.ps1' 'HOST_STATE_CAPTURE' @('READ_ONLY_PREFLIGHT','FUTURE_POSTTRANSITION_CAPTURE') 'VERIFICATION_TIME' @('POWERSHELL_ORCHESTRATOR','GIT_BUILD_AND_VERIFICATION','SC_SERVICE_CONTROL_TOOL','POWERSHELL_MANAGEMENT_ASSEMBLY') 'READ_ONLY_EVIDENCE_CAPTURE_NO_AUTHORITY'),
        (New-ScriptDefinition 'complete_unit2_upgrade_authority.ps1' 'UNIT2_UPGRADE_AUTHORITY_COMPLETION' @('UNIT2_POSTCOMMIT_PROVISIONING') 'INSTALLATION_TIME' @('POWERSHELL_ORCHESTRATOR','SC_SERVICE_CONTROL_TOOL','ICACLS_ACL_TOOL','POWERSHELL_MANAGEMENT_ASSEMBLY') 'UNIT2_LIMITED_HOST_MUTATION'),
        (New-ScriptDefinition 'extract_immutable_authority.ps1' 'IMMUTABLE_AUTHORITY_EXTRACTION' @('PRECOMMIT_AUTHORITY_GENERATION') 'BUILD_TIME' @('POWERSHELL_ORCHESTRATOR','GIT_BUILD_AND_VERIFICATION') 'NONAUTHORITATIVE_BYTE_EXTRACTION'),
        (New-ScriptDefinition 'generate_requirement_registry.ps1' 'REQUIREMENT_REGISTRY_GENERATION' @('PRECOMMIT_AUTHORITY_GENERATION') 'BUILD_TIME' @('POWERSHELL_ORCHESTRATOR') 'NONAUTHORITATIVE_DERIVATION_FROM_GOVERNING_BYTES'),
        (New-ScriptDefinition 'generate_static_closure_registries.ps1' 'STATIC_REGISTRY_GENERATION' @('PRECOMMIT_STATIC_CLOSURE') 'BUILD_TIME' @('POWERSHELL_ORCHESTRATOR','ARTIFACT_TOOL_BUILD_OUTPUT') 'NONAUTHORITATIVE_STATIC_MANIFEST_GENERATOR'),
        (New-ScriptDefinition 'generate_traceability.ps1' 'TRACEABILITY_GENERATION' @('PRECOMMIT_STATIC_VERIFICATION','FUTURE_POSTMATRIX_VERIFICATION') 'VERIFICATION_TIME' @('POWERSHELL_ORCHESTRATOR') 'NONAUTHORITATIVE_TRACE_EVIDENCE'),
        (New-ScriptDefinition 'install_authorized_transition.ps1' 'FUTURE_AUTHORIZED_INSTALLER' @('FUTURE_SEPARATELY_AUTHORIZED_HOST_TRANSITION') 'INSTALLATION_TIME' @('POWERSHELL_ORCHESTRATOR','SC_SERVICE_CONTROL_TOOL','ICACLS_ACL_TOOL','POWERSHELL_MANAGEMENT_ASSEMBLY','ARTIFACT_TOOL_BUILD_OUTPUT') 'FUTURE_HOST_MUTATION_PLAN_NOT_INVOKED_IN_STATIC_UNIT'),
        (New-ScriptDefinition 'provision_upgrade_authority.ps1' 'UNIT2_UPGRADE_BOOTSTRAP' @('UNIT2_POSTCOMMIT_PROVISIONING') 'INSTALLATION_TIME' @('POWERSHELL_ORCHESTRATOR','SC_SERVICE_CONTROL_TOOL','ICACLS_ACL_TOOL','TAKEOWN_CERTIFICATE_ACL_RECOVERY_TOOL','POWERSHELL_MANAGEMENT_ASSEMBLY','PKI_MODULE_MANIFEST') 'UNIT2_EXPLICITLY_AUTHORIZED_KEY_SERVICE_AND_ROOT_BOOTSTRAP'),
        (New-ScriptDefinition 'run_fresh_matrix.ps1' 'FUTURE_MATRIX_ORCHESTRATOR' @('FUTURE_POSTCOMMIT_POSTINSTALL_MATRIX') 'VERIFICATION_TIME' @('POWERSHELL_ORCHESTRATOR','GIT_BUILD_AND_VERIFICATION','ICACLS_ACL_TOOL','FSUTIL_PATH_FIXTURE_TOOL','POWERSHELL_MANAGEMENT_ASSEMBLY','POWERSHELL_JOB_ASSEMBLY','ARTIFACT_TOOL_BUILD_OUTPUT') 'NONAUTHORITATIVE_FUTURE_MATRIX_ORCHESTRATION_NOT_INVOKED_IN_STATIC_UNIT'),
        (New-ScriptDefinition 'scan_secrets_and_contamination.ps1' 'SECRET_AND_CONTAMINATION_SCAN' @('PRECOMMIT_STATIC_VERIFICATION','STAGED_DELTA_VERIFICATION','FUTURE_POSTMATRIX_VERIFICATION') 'VERIFICATION_TIME' @('POWERSHELL_ORCHESTRATOR','GIT_BUILD_AND_VERIFICATION','POWERSHELL_UTILITY_MODULE') 'NONAUTHORITATIVE_FAIL_CLOSED_VERIFICATION'),
        (New-ScriptDefinition 'verify_authority_coverage.ps1' 'AUTHORITY_COVERAGE_VERIFICATION' @('PRECOMMIT_STATIC_VERIFICATION','DETACHED_POSTCOMMIT_STATIC_VERIFICATION') 'VERIFICATION_TIME' @('POWERSHELL_ORCHESTRATOR') 'NONAUTHORITATIVE_FAIL_CLOSED_VERIFICATION'),
        (New-ScriptDefinition 'verify_static_architecture.ps1' 'STATIC_ARCHITECTURE_VERIFICATION' @('PRECOMMIT_STATIC_VERIFICATION','DETACHED_POSTCOMMIT_STATIC_VERIFICATION') 'VERIFICATION_TIME' @('POWERSHELL_ORCHESTRATOR','GIT_BUILD_AND_VERIFICATION','STATIC_VERIFIER_OFFLINE_BUILD_OUTPUT') 'NONAUTHORITATIVE_FAIL_CLOSED_VERIFICATION'),
        (New-ScriptDefinition 'verify_unit2_upgrade_authority.ps1' 'UNIT2_UPGRADE_AUTHORITY_VERIFICATION' @('UNIT2_POSTPROVISION_LIVE_VERIFICATION') 'VERIFICATION_TIME' @('POWERSHELL_ORCHESTRATOR','SC_SERVICE_CONTROL_TOOL','POWERSHELL_MANAGEMENT_ASSEMBLY','UNIT2_UPGRADE_CLIENT_BUILD_OUTPUT','UNIT2_UPGRADE_PUBLIC_VERIFIER_BUILD_OUTPUT','UNIT2_UPGRADE_PROTOCOL_PROBE_BUILD_OUTPUT') 'UNIT2_PUBLIC_AND_LIVE_BOUNDARY_VERIFICATION')
    )
    $actualScripts = @(Get-ChildItem -LiteralPath $packageRoot -Filter '*.ps1' -File | Sort-Object Name)
    $declaredScriptNames = @($scriptDefinitions | ForEach-Object name | Sort-Object)
    $actualScriptNames = @($actualScripts | ForEach-Object Name | Sort-Object)
    if (($declaredScriptNames -join "`n") -cne ($actualScriptNames -join "`n")) { throw 'Governed script definition set does not equal the package script set.' }
    $scriptRows = foreach ($definition in $scriptDefinitions | Sort-Object name) {
        $file = Get-Item -LiteralPath (Join-Path $packageRoot $definition.name)
        [ordered]@{
            allowed_invocation_stages = $definition.stages
            authority_classification = $definition.authority_classification
            dependencies = $definition.dependencies
            execution_class = $definition.execution_class
            git_blob_identity = Get-GitBlobIdentity $file.FullName
            mode = '100644'
            path = ($packageRelativeRoot + '/' + $file.Name)
            raw_sha256 = Get-LowerHash $file.FullName
            role = $definition.role
            size = $file.Length
        }
    }
    $scriptArtifact = [ordered]@{ artifact_type='R7_GOVERNED_SCRIPT_REGISTRY'; authority_classification='NONAUTHORITATIVE_STATIC_PACKAGE_CLOSURE'; generated_from_current_bytes=$true; schema_version='1.0.0'; script_count=@($scriptRows).Count; scripts=@($scriptRows); status='STATIC_CLOSED_POSTCOMMIT_BLOB_VERIFICATION_REQUIRED' }
    Write-CanonicalNew $scriptArtifact (Join-Path $packageRoot 'governed_script_registry.json') 'governed-script-registry'

    $managementAssembly = 'C:\Windows\Microsoft.Net\assembly\GAC_MSIL\Microsoft.PowerShell.Commands.Management\v4.0_3.0.0.0__31bf3856ad364e35\Microsoft.PowerShell.Commands.Management.dll'
    $jobAssembly = 'C:\Windows\Microsoft.Net\assembly\GAC_MSIL\System.Management.Automation\v4.0_3.0.0.0__31bf3856ad364e35\System.Management.Automation.dll'
    $utilityModuleManifest = 'C:\Windows\System32\WindowsPowerShell\v1.0\Modules\Microsoft.PowerShell.Utility\Microsoft.PowerShell.Utility.psd1'
    $utilityModuleScript = 'C:\Windows\System32\WindowsPowerShell\v1.0\Modules\Microsoft.PowerShell.Utility\Microsoft.PowerShell.Utility.psm1'
    $utilityDefinitions = @(
        (New-UtilityDefinition 'GIT_BUILD_AND_VERIFICATION' 'C:\Program Files\Git\cmd\git.exe' @('BUILD_TIME','VERIFICATION_TIME','FUTURE_MATRIX') @('extract_immutable_authority.ps1','build_remediation_package.ps1','build_static_closure.ps1','build_unit2_upgrade_authority.ps1','capture_remediation_host_state.ps1','run_fresh_matrix.ps1','scan_secrets_and_contamination.ps1','verify_static_architecture.ps1') 'ABSOLUTE_PATH_ONLY; ENVIRONMENT_AND_CONFIG_CLOSED; PROHIBITED_FROM_RUNTIME_AUTHORITY' 'NONAUTHORITATIVE_BUILD_AND_VERIFICATION_TOOL' 'RECURSIVE_INSTALLATION_ROOT' @('cat-file','ls-tree','rev-parse','status','diff','clone','checkout')),
        (New-UtilityDefinition 'POWERSHELL_ORCHESTRATOR' 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' @('BUILD_TIME','VERIFICATION_TIME','UNIT2_INSTALLATION','UNIT2_VERIFICATION','FUTURE_INSTALLATION','FUTURE_MATRIX') @($actualScriptNames) 'ABSOLUTE_HOST_PATH; NONAUTHORITATIVE_ORCHESTRATOR; SCRIPT_BYTES_SEPARATELY_GOVERNED' 'NONAUTHORITATIVE_ORCHESTRATOR' 'RECURSIVE_POWERSHELL_ROOT' @('PowerShell-script-host')),
        (New-UtilityDefinition 'CSC_COMPILER' 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe' @('BUILD_TIME') @('build_remediation_package.ps1','build_static_closure.ps1','build_unit2_upgrade_authority.ps1') 'ABSOLUTE_PATH; FIXED OPTIONS; NO RESPONSE FILES; NO PATH SEARCH' 'NONAUTHORITATIVE_COMPILER_INPUT' 'RECURSIVE_FRAMEWORK_ROOT' @('compile-x64-net48')),
        (New-UtilityDefinition 'ILDASM_TOOL' 'C:\Program Files (x86)\Microsoft SDKs\Windows\v10.0A\bin\NETFX 4.8 Tools\x64\ildasm.exe' @('BUILD_TIME') @('build_remediation_package.ps1','build_static_closure.ps1','build_unit2_upgrade_authority.ps1') 'ABSOLUTE_PATH; NORMALIZED_IL_COMPARISON_ONLY' 'NONAUTHORITATIVE_BINARY_SEMANTIC_CHECK_TOOL' 'RECURSIVE_ILDASM_ROOT' @('normalized-il')),
        (New-UtilityDefinition 'SC_SERVICE_CONTROL_TOOL' 'C:\Windows\System32\sc.exe' @('READ_ONLY_PREFLIGHT','UNIT2_INSTALLATION','UNIT2_VERIFICATION','FUTURE_INSTALLATION') @('capture_remediation_host_state.ps1','complete_unit2_upgrade_authority.ps1','install_authorized_transition.ps1','provision_upgrade_authority.ps1','verify_unit2_upgrade_authority.ps1') 'ABSOLUTE PATH; UNIT2 USE LIMITED TO UPGRADE AUTHORITY; TERMINAL SERVICE MUTATION FORBIDDEN' 'UNIT2_GOVERNED_HOST_TRANSITION_UTILITY' 'FILE_MEASUREMENT_OS_TCB' @('qc','qsidtype','qprivs','upgrade-service-start-stop')),
        (New-UtilityDefinition 'ICACLS_ACL_TOOL' 'C:\Windows\System32\icacls.exe' @('UNIT2_INSTALLATION','FUTURE_INSTALLATION','FUTURE_MATRIX_FIXTURE') @('complete_unit2_upgrade_authority.ps1','install_authorized_transition.ps1','provision_upgrade_authority.ps1','run_fresh_matrix.ps1') 'ABSOLUTE PATH; UNIT2 DEDICATED ROOTS ONLY' 'UNIT2_GOVERNED_ACL_UTILITY' 'FILE_MEASUREMENT_OS_TCB' @('dedicated-root-acl-application')),
        (New-UtilityDefinition 'TAKEOWN_CERTIFICATE_ACL_RECOVERY_TOOL' 'C:\Windows\System32\takeown.exe' @('UNIT2_BOOTSTRAP_RECOVERY') @('provision_upgrade_authority.ps1') 'ABSOLUTE PATH; EXACT PRESERVED UPGRADE PUBLIC-CERTIFICATE FILE ONLY; OWNER RECOVERY PRECEDES CLOSED ACL RESTORATION; NO RECURSION' 'UNIT2_GOVERNED_ONE_TIME_CERTIFICATE_ACL_RECOVERY_UTILITY' 'FILE_MEASUREMENT_OS_TCB' @('takeown-upgrade-public-certificate-only')),
        (New-UtilityDefinition 'FSUTIL_PATH_FIXTURE_TOOL' 'C:\Windows\System32\fsutil.exe' @('FUTURE_MATRIX_FIXTURE') @('run_fresh_matrix.ps1') 'ABSOLUTE_PATH; ISOLATED TEST ROOT ONLY; NOT INVOKED IN STATIC UNIT' 'FUTURE_NONAUTHORITY_FIXTURE_UTILITY_NOT_INVOKED' 'FILE_MEASUREMENT_OS_TCB' @('future-setshortname')),
        (New-UtilityDefinition 'RUNTIME_MACHINE_CONFIG' 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\Config\machine.config' @('BUILD_TIME','RUNTIME_INPUT') @('build_remediation_package.ps1','build_static_closure.ps1','build_unit2_upgrade_authority.ps1') 'CONTENT_BOUND_CONFIGURATION; NO ENVIRONMENT OVERRIDE' 'FRAMEWORK_CONFIGURATION_INPUT' 'RECURSIVE_FRAMEWORK_ROOT' @('clr-configuration')),
        (New-UtilityDefinition 'COMPILER_REFERENCE_mscorlib.dll' 'C:\Program Files (x86)\Reference Assemblies\Microsoft\Framework\.NETFramework\v4.8\mscorlib.dll' @('BUILD_TIME') @('build_remediation_package.ps1','build_static_closure.ps1','build_unit2_upgrade_authority.ps1') 'ABSOLUTE_REFERENCE; NOSTDLIB; EXPLICIT REFERENCE' 'COMPILER_REFERENCE_INPUT' 'RECURSIVE_REFERENCE_ROOT' @('compile-reference')),
        (New-UtilityDefinition 'COMPILER_REFERENCE_System.dll' 'C:\Program Files (x86)\Reference Assemblies\Microsoft\Framework\.NETFramework\v4.8\System.dll' @('BUILD_TIME') @('build_remediation_package.ps1','build_static_closure.ps1','build_unit2_upgrade_authority.ps1') 'ABSOLUTE_REFERENCE; NOSTDLIB; EXPLICIT REFERENCE' 'COMPILER_REFERENCE_INPUT' 'RECURSIVE_REFERENCE_ROOT' @('compile-reference')),
        (New-UtilityDefinition 'COMPILER_REFERENCE_System.Core.dll' 'C:\Program Files (x86)\Reference Assemblies\Microsoft\Framework\.NETFramework\v4.8\System.Core.dll' @('BUILD_TIME') @('build_remediation_package.ps1','build_static_closure.ps1','build_unit2_upgrade_authority.ps1') 'ABSOLUTE_REFERENCE; NOSTDLIB; EXPLICIT REFERENCE' 'COMPILER_REFERENCE_INPUT' 'RECURSIVE_REFERENCE_ROOT' @('compile-reference')),
        (New-UtilityDefinition 'COMPILER_REFERENCE_System.Security.dll' 'C:\Program Files (x86)\Reference Assemblies\Microsoft\Framework\.NETFramework\v4.8\System.Security.dll' @('BUILD_TIME') @('build_remediation_package.ps1','build_static_closure.ps1','build_unit2_upgrade_authority.ps1') 'ABSOLUTE_REFERENCE; NOSTDLIB; EXPLICIT REFERENCE' 'COMPILER_REFERENCE_INPUT' 'RECURSIVE_REFERENCE_ROOT' @('compile-reference')),
        (New-UtilityDefinition 'COMPILER_REFERENCE_System.ServiceProcess.dll' 'C:\Program Files (x86)\Reference Assemblies\Microsoft\Framework\.NETFramework\v4.8\System.ServiceProcess.dll' @('BUILD_TIME') @('build_remediation_package.ps1','build_static_closure.ps1','build_unit2_upgrade_authority.ps1') 'ABSOLUTE_REFERENCE; NOSTDLIB; EXPLICIT REFERENCE' 'COMPILER_REFERENCE_INPUT' 'RECURSIVE_REFERENCE_ROOT' @('compile-reference')),
        (New-UtilityDefinition 'POWERSHELL_MANAGEMENT_ASSEMBLY' $managementAssembly @('READ_ONLY_PREFLIGHT','UNIT2_INSTALLATION','UNIT2_VERIFICATION','FUTURE_INSTALLATION','FUTURE_MATRIX') @('capture_remediation_host_state.ps1','complete_unit2_upgrade_authority.ps1','install_authorized_transition.ps1','provision_upgrade_authority.ps1','run_fresh_matrix.ps1','verify_unit2_upgrade_authority.ps1') 'CMDLETS RESOLVE TO THIS MEASURED ASSEMBLY; UNIT2 MUTATION LIMITED TO UPGRADE AUTHORITY' 'POWERSHELL_CMDLET_PROVIDER_INPUT' 'FILE_MEASUREMENT_OS_TCB' @('Get-Service','Start-Service','Stop-Service','New-Item','Get-CimInstance','Start-Process','Move-Item')),
        (New-UtilityDefinition 'POWERSHELL_JOB_ASSEMBLY' $jobAssembly @('FUTURE_MATRIX_FIXTURE') @('run_fresh_matrix.ps1') 'START-JOB PROVIDER MEASURED; CHILD POWERSHELL CLOSURE REQUIRED; NOT INVOKED IN STATIC UNIT' 'FUTURE_NONAUTHORITY_MATRIX_JOB_PROVIDER' 'FILE_MEASUREMENT_OS_TCB' @('Start-Job')),
        (New-UtilityDefinition 'POWERSHELL_UTILITY_MODULE_MANIFEST' $utilityModuleManifest @('BUILD_TIME','VERIFICATION_TIME') @($actualScriptNames) 'MODULE MANIFEST CONTENT BOUND WITH POWERSHELL ROOT' 'POWERSHELL_MODULE_INPUT' 'RECURSIVE_POWERSHELL_ROOT' @('Get-FileHash','ConvertTo-Json')),
        (New-UtilityDefinition 'POWERSHELL_UTILITY_MODULE_SCRIPT' $utilityModuleScript @('BUILD_TIME','VERIFICATION_TIME') @($actualScriptNames) 'MODULE SCRIPT CONTENT BOUND WITH POWERSHELL ROOT' 'POWERSHELL_MODULE_INPUT' 'RECURSIVE_POWERSHELL_ROOT' @('Get-FileHash')),
        (New-UtilityDefinition 'PKI_MODULE_MANIFEST' 'C:\Windows\System32\WindowsPowerShell\v1.0\Modules\PKI\pki.psd1' @('UNIT2_UPGRADE_PROVISIONING') @('provision_upgrade_authority.ps1') 'EXPLICIT IMPORT BY ABSOLUTE MANIFEST; UNIT2 USE LIMITED TO NONEXPORTABLE UPGRADE KEY AND PUBLIC CERTIFICATE' 'UNIT2_KEY_PROVISIONING_MODULE' 'RECURSIVE_POWERSHELL_ROOT' @('New-SelfSignedCertificate','Export-Certificate')),
        (New-UtilityDefinition 'PKI_MODULE_TYPES' 'C:\Windows\System32\WindowsPowerShell\v1.0\Modules\PKI\pki.types.ps1xml' @('UNIT2_UPGRADE_PROVISIONING') @('provision_upgrade_authority.ps1') 'CONTENT BOUND PKI MODULE INPUT' 'UNIT2_KEY_PROVISIONING_MODULE_INPUT' 'RECURSIVE_POWERSHELL_ROOT' @('PKI-types'))
    )
    if (-not (Test-Path -LiteralPath $measurementRoot)) { New-Item -ItemType Directory -Path $measurementRoot | Out-Null }
    $utilityIndex = 0
    $utilityRows = foreach ($definition in $utilityDefinitions | Sort-Object role) {
        $full = [IO.Path]::GetFullPath($definition.path)
        if (-not (Test-Path -LiteralPath $full -PathType Leaf)) { throw "External utility input missing: $full" }
        $measurementPath = Join-Path $measurementRoot ('u' + $utilityIndex.ToString('D2') + '.json')
        $utilityIndex++
        & $artifactToolFull measure $full $measurementPath | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "External utility measurement failed: $($definition.role)" }
        [ordered]@{
            allowed_invocation_stages = $definition.stages
            authority_classification = $definition.authority_classification
            closure_class = $definition.closure_class
            commands = $definition.commands
            measurement = (Get-Content -LiteralPath $measurementPath -Raw | ConvertFrom-Json)
            path = $full
            path_search_allowed = $false
            required_by_scripts = $definition.required_by_scripts
            restriction = $definition.restriction
            role = $definition.role
            runtime_authority = $false
        }
    }
    $utilityArtifact = [ordered]@{ artifact_type='R7_EXTERNAL_UTILITY_REGISTRY'; authority_classification='NONAUTHORITATIVE_STATIC_DEPENDENCY_CLOSURE'; schema_version='1.0.0'; status='STATIC_CONTENT_BOUND_HOST_SPECIFIC_POSTCOMMIT_REVALIDATION_REQUIRED'; utility_count=@($utilityRows).Count; utilities=@($utilityRows) }
    Write-CanonicalNew $utilityArtifact (Join-Path $packageRoot 'external_utility_registry.json') 'external-utility-registry'

    $targets = @(
        [ordered]@{authority_classification='UNIT2_UPGRADE_DISPOSITION_AUTHORITY_AFTER_PROVISIONING';define='UNIT2_SERVICE';file_name='RandleTerminalUpgradeAuthority.exe';installed_role=$true;main='RandleAI.R7Remediation.R7Unit2UpgradeServiceProgram';role='UNIT2_UPGRADE_AUTHORITY'},
        [ordered]@{authority_classification='UNIT2_NONAUTHORITATIVE_MEASURED_CLIENT';define='';file_name='RandleTerminalUpgradeClient.exe';installed_role=$true;main='RandleAI.R7Remediation.R7Unit2UpgradeClientProgram';role='UNIT2_UPGRADE_CLIENT'},
        [ordered]@{authority_classification='UNIT2_PUBLIC_ONLY_UPGRADE_VERIFIER';define='';file_name='RandleTerminalUpgradePublicVerifier.exe';installed_role=$true;main='RandleAI.R7Remediation.R7Unit2UpgradePublicVerifierProgram';role='UNIT2_UPGRADE_PUBLIC_VERIFIER'},
        [ordered]@{authority_classification='UNIT2_NONAUTHORITATIVE_PROTOCOL_ATTACK_DRIVER';define='';file_name='RandleTerminalUpgradeProtocolProbe.exe';installed_role=$true;main='RandleAI.R7Remediation.R7Unit2UpgradeProbeProgram';role='UNIT2_UPGRADE_PROTOCOL_PROBE'},
        [ordered]@{authority_classification='FUTURE_TERMINAL_SIGNER_BINARY';define='';file_name='RandleTerminalAuthority.exe';installed_role=$true;main='RandleAI.R7Remediation.R7TerminalServiceProgram';role='TERMINAL_SIGNER'},
        [ordered]@{authority_classification='NONAUTHORITATIVE_RAW_EXECUTION_PRODUCER';define='EXECUTION_ROLE';file_name='RandleTerminalExecution.exe';installed_role=$true;main='RandleAI.R7Remediation.R7ExecutionServiceProgram';role='EXECUTION'},
        [ordered]@{authority_classification='NONAUTHORITATIVE_RAW_OBSERVATION_PRODUCER';define='OBSERVATION_ROLE';file_name='RandleTerminalObservation.exe';installed_role=$true;main='RandleAI.R7Remediation.R7ObservationServiceProgram';role='OBSERVATION'},
        [ordered]@{authority_classification='NONAUTHORITATIVE_SEMANTIC_COMPARATOR';define='COMPARATOR_ROLE';file_name='RandleTerminalComparator.exe';installed_role=$true;main='RandleAI.R7Remediation.R7ComparatorServiceProgram';role='COMPARATOR'},
        [ordered]@{authority_classification='OFFLINE_PUBLIC_CLASSIFICATION_VERIFIER';define='';file_name='RandleTerminalPublicVerifier.exe';installed_role=$true;main='RandleAI.R7Remediation.R7PublicVerifierProgram';role='PUBLIC_VERIFIER'},
        [ordered]@{authority_classification='NONAUTHORITATIVE_AUTHORITY_PACKAGE_VERIFIER';define='';file_name='RandleTerminalAuthorityVerifier.exe';installed_role=$true;main='RandleAI.R7Remediation.R7AuthorityVerifierProgram';role='AUTHORITY_VERIFIER'},
        [ordered]@{authority_classification='NONAUTHORITATIVE_ADVERSARIAL_ORCHESTRATION_SUPPORT';define='';file_name='RandleTerminalAdversarialHarness.exe';installed_role=$true;main='RandleAI.R7Remediation.R7AdversarialHarnessProgram';role='ADVERSARIAL_HARNESS'},
        [ordered]@{authority_classification='NONAUTHORITATIVE_INSTALLED_STATIC_SUPPORT';define='INSTALLED_STATIC_ROLE';file_name='RandleTerminalStaticVerifier.exe';installed_role=$true;main='RandleAI.R7Remediation.R7StaticVerificationProgram';role='STATIC_VERIFIER_INSTALLED'},
        [ordered]@{authority_classification='NONAUTHORITATIVE_OFFLINE_STATIC_SUPPORT';define='';file_name='RandleTerminalStaticVerifier.Offline.exe';installed_role=$false;main='RandleAI.R7Remediation.R7StaticVerificationProgram';role='STATIC_VERIFIER_OFFLINE'},
        [ordered]@{authority_classification='NONAUTHORITATIVE_BUILD_AND_INSTALL_SUPPORT';define='';file_name='R7ArtifactTool.exe';installed_role=$false;main='RandleAI.R7Remediation.R7ArtifactToolProgram';role='ARTIFACT_TOOL'}
    )
    $allCompiledRoles = @($targets | ForEach-Object role)
    $sourceDefinitions = @(
        (New-SourceDefinition 'R7AdversarialHarness.cs' @('HOSTILE_OUTER_INTERFACE_DRIVER','MATRIX_ORCHESTRATION') @('R7AR-B03','R7AR-B16') @('TERMINAL_PIPE','PUBLIC_VERIFIER','UPGRADE_PIPE','OS_BOUNDARY','SAFE_FILE','DEPENDENCY_VERIFIER','RECOVERY_ENGINE') @('COMPILE','STATIC_TRACE','FUTURE_MATRIX') 'NONAUTHORITATIVE_SUPPORT' @('ADVERSARIAL_HARNESS')),
        (New-SourceDefinition 'R7ArtifactTool.cs' @('MEASUREMENT_TOOL','BUILD_SUPPORT','INSTALL_SUPPORT') @('R7AR-B05','R7AR-B11','R7AR-B12','R7AR-B15') @('SAFE_FILE','DEPENDENCY_VERIFIER','OS_BOUNDARY') @('COMPILE','UTILITY_MEASUREMENT','STATIC_TRACE') 'NONAUTHORITATIVE_SUPPORT' @('ARTIFACT_TOOL')),
        (New-SourceDefinition 'R7AuthorityArtifacts.cs' @('EXACT_AUTHORITY_RESOLUTION') @('R7AR-B01','R7AR-B14') @('AUTHORITY_REGISTRY') @('STATIC_AUTHORITY','STATIC_TRACE') 'DISPOSITION_DETERMINATIVE_WHEN_AUTHORIZED_AND_INSTALLED' @('TERMINAL_SIGNER','PUBLIC_VERIFIER','AUTHORITY_VERIFIER','EXECUTION','OBSERVATION','COMPARATOR')),
        (New-SourceDefinition 'R7AuthorityVerifier.cs' @('AUTHORITY_PACKAGE_VERIFIER') @('R7AR-B01','R7AR-B14') @('AUTHORITY_REGISTRY') @('STATIC_AUTHORITY','STATIC_TRACE') 'NONAUTHORITATIVE_SUPPORT' @('AUTHORITY_VERIFIER')),
        (New-SourceDefinition 'R7BuildClosureVerifier.cs' @('BUILD_AND_BINARY_CLOSURE_VERIFIER') @('R7AR-B07','R7AR-B12','R7AR-B15') @('DEPENDENCY_VERIFIER','SOURCE_AND_RUNTIME') @('STATIC_BUILD_RECEIPT','STATIC_TRACE') 'DISPOSITION_DETERMINATIVE_WHEN_AUTHORIZED_AND_INSTALLED' @('TERMINAL_SIGNER','UNIT2_UPGRADE_AUTHORITY','UNIT2_UPGRADE_PUBLIC_VERIFIER','PUBLIC_VERIFIER')),
        (New-SourceDefinition 'R7CoreJsonProtocol.cs' @('STRICT_FRAMING','CANONICAL_JSON') @('R7AR-B06') @('TERMINAL_PIPE') @('PARSER_22_CASES','COMPILE','STATIC_TRACE') 'DISPOSITION_DETERMINATIVE_WHEN_AUTHORIZED_AND_INSTALLED' @('ALL_EXECUTABLE_ROLES')),
        (New-SourceDefinition 'R7CryptoLedger.cs' @('CRYPTOGRAPHIC_LEDGER','DURABLE_FILE') @('R7AR-B08','R7AR-B09','R7AR-B10') @('TERMINAL_PIPE','RECOVERY_ENGINE','PUBLIC_VERIFIER','UPGRADE_PIPE') @('STATIC_TRANSACTION','STATIC_RECOVERY','STATIC_HISTORY','STATIC_TRACE','UNIT2_LEDGER') 'DISPOSITION_DETERMINATIVE_WHEN_AUTHORIZED_AND_INSTALLED' @('TERMINAL_SIGNER','UNIT2_UPGRADE_AUTHORITY','UNIT2_UPGRADE_PUBLIC_VERIFIER','PUBLIC_VERIFIER')),
        (New-SourceDefinition 'R7DependencyClosure.cs' @('RUNTIME_DEPENDENCY_CLOSURE') @('R7AR-B12','R7AR-B15') @('DEPENDENCY_VERIFIER','SOURCE_AND_RUNTIME') @('STATIC_DEPENDENCY_MANIFEST','COMPILE','STATIC_TRACE','FUTURE_RUNTIME_PROBE') 'DISPOSITION_DETERMINATIVE_WHEN_AUTHORIZED_AND_INSTALLED' @('ALL_INSTALLED_ROLES')),
        (New-SourceDefinition 'R7EvidenceStore.cs' @('RAW_INTERACTION_EVIDENCE_STORE') @('R7AR-B03','R7AR-B04') @('TERMINAL_PIPE') @('COMPILE','STATIC_TRACE','FUTURE_HOSTILE_GRAPH_ATTACKS') 'DISPOSITION_DETERMINATIVE_WHEN_AUTHORIZED_AND_INSTALLED' @('TERMINAL_SIGNER')),
        (New-SourceDefinition 'R7HistoricalClassification.cs' @('VERSIONED_HISTORY_CLASSIFICATION') @('R7AR-B08','R7AR-B13') @('PUBLIC_VERIFIER','RECOVERY_ENGINE') @('STATIC_HISTORY','STATIC_TRACE','FUTURE_APPEND_ONLY_CLASSIFICATION') 'DISPOSITION_DETERMINATIVE_WHEN_AUTHORIZED_AND_INSTALLED' @('TERMINAL_SIGNER','PUBLIC_VERIFIER')),
        (New-SourceDefinition 'R7MeasuredUtility.cs' @('HELD_MEASURED_UTILITY_INVOCATION') @('R7AR-B05','R7AR-B11','R7AR-B12','R7AR-B15') @('OS_BOUNDARY','SAFE_FILE','DEPENDENCY_VERIFIER') @('COMPILE','STATIC_UTILITY_REGISTRY','STATIC_TRACE','FUTURE_INSTALLATION_PROBE') 'NONAUTHORITATIVE_SUPPORT' @('ARTIFACT_TOOL')),
        (New-SourceDefinition 'R7Policy.cs' @('POLICY_AND_VERSION_BINDING') @('R7AR-B07','R7AR-B08','R7AR-B12') @('UPGRADE_PIPE','TERMINAL_PIPE','PUBLIC_VERIFIER') @('COMPILE','STATIC_TRACE','FUTURE_ACTIVATION') 'DISPOSITION_DETERMINATIVE_WHEN_AUTHORIZED_AND_INSTALLED' @('TERMINAL_SIGNER','UNIT2_UPGRADE_AUTHORITY','UNIT2_UPGRADE_PUBLIC_VERIFIER','PUBLIC_VERIFIER')),
        (New-SourceDefinition 'R7PublicVerifier.cs' @('VERSION_AWARE_OFFLINE_PUBLIC_VERIFICATION') @('R7AR-B07','R7AR-B08','R7AR-B13','R7AR-B16') @('PUBLIC_VERIFIER') @('STATIC_HISTORY','COMPILE','STATIC_TRACE','FUTURE_STOPPED_VERIFICATION') 'PUBLIC_CLASSIFICATION_DETERMINATIVE' @('PUBLIC_VERIFIER')),
        (New-SourceDefinition 'R7RecoveryProbeAuditor.cs' @('INDEPENDENT_RECOVERY_PROOF_REDERIVATION') @('R7AR-B04','R7AR-B10') @('RECOVERY_ENGINE','CLAIM_VERIFIER') @('STATIC_RECOVERY','COMPILE','STATIC_TRACE') 'DISPOSITION_DETERMINATIVE_WHEN_AUTHORIZED_AND_INSTALLED' @('TERMINAL_SIGNER')),
        (New-SourceDefinition 'R7RecoveryProbeEngine.cs' @('ISOLATED_RECOVERY_FAULT_ENGINE') @('R7AR-B10') @('RECOVERY_ENGINE') @('STATIC_RECOVERY','COMPILE','STATIC_TRACE','FUTURE_CRASH_MATRIX') 'NONAUTHORITATIVE_ISOLATED_TEST_SUPPORT' @('STATIC_VERIFIER_OFFLINE','EXECUTION')),
        (New-SourceDefinition 'R7RoleServices.cs' @('EXECUTION_PRODUCER','OBSERVATION_PRODUCER','SEMANTIC_COMPARATOR','NESTED_OUTER_SUBMISSION') @('R7AR-B02','R7AR-B03','R7AR-B05','R7AR-B16') @('TERMINAL_PIPE','OS_BOUNDARY','SEMANTIC_VERIFIER') @('COMPILE','STATIC_TRACE','FUTURE_OUTER_INTERFACE_MATRIX') 'NONAUTHORITATIVE_PRODUCERS_AND_COMPARATOR' @('EXECUTION','OBSERVATION','COMPARATOR')),
        (New-SourceDefinition 'R7SafeFile.cs' @('HELD_NO_FOLLOW_FILE_IDENTITY') @('R7AR-B11','R7AR-B12') @('SAFE_FILE','DEPENDENCY_VERIFIER') @('COMPILE','STATIC_TRACE','FUTURE_PHYSICAL_ATTACKS') 'DISPOSITION_DETERMINATIVE_WHEN_AUTHORIZED_AND_INSTALLED' @('ALL_EXECUTABLE_ROLES')),
        (New-SourceDefinition 'R7ServiceBoundary.cs' @('LSA_ACCOUNT_RIGHTS','SCM_SERVICE_BOUNDARY') @('R7AR-B05','R7AR-B07') @('OS_BOUNDARY') @('COMPILE','STATIC_UTILITY_REGISTRY','STATIC_TRACE','FUTURE_SERVICE_BOUNDARY_PROBES') 'NONAUTHORITATIVE_FUTURE_INSTALLATION_SUPPORT' @('ARTIFACT_TOOL')),
        (New-SourceDefinition 'R7ServiceInfrastructure.cs' @('NAMED_PIPE_SERVER','OS_CALLER_CAPTURE') @('R7AR-B05','R7AR-B06') @('TERMINAL_PIPE','OS_BOUNDARY') @('COMPILE','PARSER_22_CASES','STATIC_TRACE','UNIT2_LIVE_IPC','FUTURE_LIVE_IPC') 'DISPOSITION_DETERMINATIVE_WHEN_AUTHORIZED_AND_INSTALLED' @('TERMINAL_SIGNER','UNIT2_UPGRADE_AUTHORITY','EXECUTION','OBSERVATION','COMPARATOR')),
        (New-SourceDefinition 'R7StaticVerification.cs' @('OFFLINE_STATIC_TEST_DRIVER') @('R7AR-B01','R7AR-B06','R7AR-B08','R7AR-B09','R7AR-B10','R7AR-B14') @('AUTHORITY_REGISTRY','RECOVERY_ENGINE','TERMINAL_PIPE') @('PARSER_22_CASES','STATIC_AUTHORITY','STATIC_TRANSACTION','STATIC_RECOVERY','STATIC_HISTORY','STATIC_TRACE') 'NONAUTHORITATIVE_SUPPORT' @('STATIC_VERIFIER_OFFLINE','STATIC_VERIFIER_INSTALLED')),
        (New-SourceDefinition 'R7TerminalSignerService.cs' @('TERMINAL_SEMANTIC_AUTHORITY','NESTED_OUTER_GRAPH_REDERIVATION') @('R7AR-B02','R7AR-B03','R7AR-B04','R7AR-B05','R7AR-B08','R7AR-B09','R7AR-B13','R7AR-B14') @('TERMINAL_PIPE','CLAIM_VERIFIER','SEMANTIC_VERIFIER','TRACE_VERIFIER','PUBLIC_VERIFIER') @('COMPILE','STATIC_TRACE','FUTURE_HOSTILE_GRAPH_ATTACKS','FUTURE_MATRIX') 'DISPOSITION_DETERMINATIVE_WHEN_AUTHORIZED_AND_INSTALLED' @('TERMINAL_SIGNER')),
        (New-SourceDefinition 'R7Transaction.cs' @('APPEND_ONLY_TRANSACTION_STATE_MACHINE') @('R7AR-B09','R7AR-B10') @('TERMINAL_PIPE','RECOVERY_ENGINE') @('STATIC_TRANSACTION','STATIC_RECOVERY','COMPILE','STATIC_TRACE') 'DISPOSITION_DETERMINATIVE_WHEN_AUTHORIZED_AND_INSTALLED' @('TERMINAL_SIGNER','UNIT2_UPGRADE_AUTHORITY')),
        (New-SourceDefinition 'R7UpgradeAuthorityService.cs' @('SUPERSEDED_PRE_UNIT2_UPGRADE_PROPOSAL') @('R7AR-B07') @('UPGRADE_PIPE') @('COMPILE','STATIC_TRACE') 'NONAUTHORITATIVE_SUPERSEDED_SOURCE_NOT_SELECTED_AS_ENTRYPOINT' @('SOURCE_CLOSURE_ONLY')),
        (New-SourceDefinition 'R7UpgradeClient.cs' @('SUPERSEDED_PRE_UNIT2_UPGRADE_CLIENT') @('R7AR-B07') @('UPGRADE_PIPE') @('COMPILE','STATIC_TRACE') 'NONAUTHORITATIVE_SUPERSEDED_SOURCE_NOT_SELECTED_AS_ENTRYPOINT' @('SOURCE_CLOSURE_ONLY')),
        (New-SourceDefinition 'R7Unit2UpgradeAuthority.cs' @('UNIT2_NONCIRCULAR_UPGRADE_AUTHORITY','FIXED_TRANSITION_PAYLOAD','SIGNED_PROVISIONING_ATTESTATION','UPGRADE_LEDGER') @('R7AR-B05','R7AR-B06','R7AR-B07','R7AR-B09','R7AR-B10','R7AR-B11','R7AR-B12','R7AR-B15') @('UPGRADE_PIPE','OS_BOUNDARY','SAFE_FILE','DEPENDENCY_VERIFIER') @('COMPILE','UNIT2_LIVE_IPC','UNIT2_LEDGER','UNIT2_AUTHORIZATION') 'UPGRADE_DISPOSITION_DETERMINATIVE_AFTER_UNIT2_PROVISIONING' @('UNIT2_UPGRADE_AUTHORITY')),
        (New-SourceDefinition 'R7Unit2UpgradeClient.cs' @('UNIT2_NARROW_UPGRADE_CLIENT') @('R7AR-B06','R7AR-B07') @('UPGRADE_PIPE') @('COMPILE','UNIT2_AUTHORIZATION') 'NONAUTHORITATIVE_REQUEST_SUPPORT' @('UNIT2_UPGRADE_CLIENT')),
        (New-SourceDefinition 'R7Unit2UpgradeProbe.cs' @('UNIT2_STRICT_PROTOCOL_PROBE') @('R7AR-B06','R7AR-B07') @('UPGRADE_PIPE') @('COMPILE','UNIT2_LIVE_IPC') 'NONAUTHORITATIVE_ADVERSARIAL_VERIFICATION' @('UNIT2_UPGRADE_PROTOCOL_PROBE')),
        (New-SourceDefinition 'R7Unit2UpgradePublicVerifier.cs' @('UNIT2_PUBLIC_ONLY_VERIFIER','UNIT2_BOUNDARY_ENFORCER','UNIT2_KEY_DENIAL_PROBE') @('R7AR-B05','R7AR-B07','R7AR-B08','R7AR-B10') @('UPGRADE_PIPE','PUBLIC_VERIFIER','OS_BOUNDARY') @('COMPILE','UNIT2_PUBLIC_STOPPED_VERIFICATION','UNIT2_PRINCIPAL_ISOLATION') 'PUBLIC_UPGRADE_CLASSIFICATION_DETERMINATIVE' @('UNIT2_UPGRADE_PUBLIC_VERIFIER'))
    )
    $actualSources = @(Get-ChildItem -LiteralPath (Join-Path $packageRoot 'Source') -Filter '*.cs' -File | Sort-Object Name)
    if ((@($sourceDefinitions | ForEach-Object name | Sort-Object) -join "`n") -cne (@($actualSources | ForEach-Object Name | Sort-Object) -join "`n")) { throw 'Source routing definition set does not equal the current source set.' }
    $requirements = Get-Content -LiteralPath (Join-Path $packageRoot 'governed_requirement_registry.json') -Raw | ConvertFrom-Json
    $knownRequirements = @{}; foreach ($row in @($requirements.requirements)) { $knownRequirements[[string]$row.requirement_id] = $true }
    $sourceRows = foreach ($definition in $sourceDefinitions | Sort-Object name) {
        $file = Get-Item -LiteralPath (Join-Path $packageRoot ('Source\' + $definition.name))
        $requirementIds = @($definition.blockers | ForEach-Object { 'R7RM-AR-' + $_.Substring(5) } | Sort-Object -Unique)
        foreach ($id in $requirementIds) { if (-not $knownRequirements.ContainsKey($id)) { throw "Source routing requirement is absent: $id" } }
        [ordered]@{
            architecture_roles = $definition.architecture_roles
            blocker_ids = $definition.blockers
            compiled_into_roles = $allCompiledRoles
            current_static_unit_authority = 'NONAUTHORITATIVE_UNINSTALLED_SOURCE'
            expected_verification = $definition.verification
            git_blob_identity = Get-GitBlobIdentity $file.FullName
            implementation_surfaces = $definition.implementation_surfaces
            intended_runtime_authority = $definition.intended_authority
            mode = '100644'
            path = ('Source/' + $file.Name)
            primary_architectural_consumers = $definition.consumers
            raw_sha256 = Get-LowerHash $file.FullName
            requirement_ids = $requirementIds
            size = $file.Length
        }
    }
    $sourceArtifact = [ordered]@{ artifact_type='R7_SOURCE_ROLE_REGISTRY'; current_authority='NONAUTHORITATIVE_STATIC_PROPOSAL'; executable_role_count=$targets.Count; executable_roles=$targets; schema_version='1.0.0'; source_count=@($sourceRows).Count; sources=@($sourceRows); status='STATIC_CLOSED_POSTCOMMIT_BLOB_VERIFICATION_REQUIRED' }
    Write-CanonicalNew $sourceArtifact (Join-Path $packageRoot 'source_role_registry.json') 'source-role-registry'
}

if ($GeneratePackageManifest) {
    $manifestPath = Join-Path $packageRoot 'static_package_file_manifest.json'
    $excluded = @('static_package_file_manifest.json')
    $files = @(Get-ChildItem -LiteralPath $packageRoot -Recurse -File -Force | Where-Object { $_.FullName -notlike ((Join-Path $packageRoot 'Build') + '\*') -and $excluded -notcontains $_.Name } | Sort-Object FullName)
    $rows = foreach ($file in $files) {
        [ordered]@{ git_blob_identity=(Get-GitBlobIdentity $file.FullName); mode='100644'; path=(Get-RelativePath $repositoryRoot $file.FullName); raw_sha256=(Get-LowerHash $file.FullName); size=$file.Length }
    }
    $artifact = [ordered]@{ artifact_type='R7_STATIC_PACKAGE_FILE_MANIFEST'; authority_classification='NONAUTHORITATIVE_STATIC_STAGED_DELTA_MANIFEST'; excluded_self_path=($packageRelativeRoot + '/static_package_file_manifest.json'); file_count=@($rows).Count; files=@($rows); schema_version='1.0.0'; status='COMPLETE_EXCEPT_EXPLICIT_SELF_EXCLUSION' }
    Write-CanonicalNew $artifact $manifestPath 'static-package-file-manifest'
}

[ordered]@{ artifact_tool_sha256=(Get-LowerHash $artifactToolFull); generated_package_manifest=[bool]$GeneratePackageManifest; generated_registries=[bool]$GenerateRegistries; measurement_root=$measurementRoot; status='PASS' } | ConvertTo-Json
