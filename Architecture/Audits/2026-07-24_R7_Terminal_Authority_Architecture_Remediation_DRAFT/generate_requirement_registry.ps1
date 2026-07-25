param()

$ErrorActionPreference = 'Stop'
$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$SourceRoot = Join-Path $PackageRoot 'AuthoritySources'
$Utf8 = New-Object System.Text.UTF8Encoding($false, $true)

function Get-LowerSha256 {
    param([byte[]]$Bytes)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        return ([System.BitConverter]::ToString($sha.ComputeHash($Bytes))).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $sha.Dispose()
    }
}

function Read-AuthoritySource {
    param([string]$FileName)
    $path = Join-Path $SourceRoot $FileName
    $bytes = [System.IO.File]::ReadAllBytes($path)
    $text = $Utf8.GetString($bytes)
    $lines = $text.Split(@("`n"), [System.StringSplitOptions]::None)
    for ($index = 0; $index -lt $lines.Length; $index++) {
        if ($lines[$index].EndsWith("`r")) {
            $lines[$index] = $lines[$index].Substring(0, $lines[$index].Length - 1)
        }
    }
    return [pscustomobject]@{ Path = $path; Bytes = $bytes; Text = $text; Lines = $lines }
}

function Get-LineRange {
    param(
        [object]$Source,
        [int]$StartLine,
        [int]$EndLine
    )
    if ($StartLine -lt 1 -or $EndLine -lt $StartLine -or $EndLine -gt $Source.Lines.Length) {
        throw "invalid line range $StartLine-$EndLine for $($Source.Path)"
    }
    $quote = [String]::Join("`n", $Source.Lines[($StartLine - 1)..($EndLine - 1)])
    $prefix = if ($StartLine -eq 1) { '' } else { [String]::Join("`n", $Source.Lines[0..($StartLine - 2)]) + "`n" }
    $startByte = $Utf8.GetByteCount($prefix)
    $quoteBytes = $Utf8.GetBytes($quote)
    return [pscustomobject]@{
        StartLine = $StartLine
        EndLine = $EndLine
        StartByte = $startByte
        EndByteExclusive = $startByte + $quoteBytes.Length
        Quote = $quote
        QuoteSha256 = Get-LowerSha256 -Bytes $quoteBytes
    }
}

$categoryControls = @{
    PATH = @{
        interpretation = 'Authority is accepted only from an exact physical file and directory identity held through governed use.'
        positive = 'Open the fixed object without following reparse points; verify final NT path, volume, file ID, owner, ACL, link count, streams, size and bytes from the held handle.'
        rejection = 'Reject aliases, reparse traversal, unexpected links or streams, path-case collisions, alternate volumes, stale copies and identity changes between measurement and use.'
        evidence = 'Held-handle identity, final path, volume serial, file ID, owner/ACL, link/stream inventory, size, SHA-256 and before/use/after identity evidence.'
        side_effects = 'Only the explicitly authorized read or immutable install action may occur.'
        forbidden = 'No authority-store mutation, alternate-root selection, path reopening after validation or production-root write.'
        durability = 'Installed authority identities and root ACLs remain fixed and publicly inventory-verifiable.'
        restart = 'Restart reopens and revalidates the same fixed physical identities; substitution, rollback and stale copies fail closed.'
        reconciliation = 'Candidate and fresh evidence must bind distinct run files while resolving the same governed installed identities.'
    }
    SEPARATION = @{
        interpretation = 'Independent roles and evidence classes must be separated by both semantics and OS-enforced capabilities.'
        positive = 'Use distinct restricted principals and disjoint readable/writable roots for execution, observation, comparison, signing and upgrade authority.'
        rejection = 'Reject self-review, signer-token inheritance, expectation access by actual producers, shared signing capability and caller-controlled authority substitution.'
        evidence = 'Service SIDs, token groups, privilege sets, ACLs, access-denied probes, process parentage and per-role file-access evidence.'
        side_effects = 'Each role writes only its narrow append-only spool or authority store.'
        forbidden = 'No child key use, ledger/trust/receipt write, signer impersonation, repository write or interactive logon.'
        durability = 'Principal, privilege and ACL registries are content-bound and rechecked at service start and terminal issuance.'
        restart = 'Restart preserves distinct principals and denies inherited signer capabilities.'
        reconciliation = 'Reconciliation resolves independently produced graphs and rejects shared or synthetic provenance.'
    }
    CANONICAL = @{
        interpretation = 'Every authority and IPC object has one strict byte representation and one closed typed meaning.'
        positive = 'Validate complete framing, strict UTF-8/NFC, duplicate-free recursive JSON, exact types, closed key sets, schema and semantic rules before dispatch.'
        rejection = 'Reject duplicate keys, coercion, floats, null/absent confusion, unknown fields, noncanonical bytes, trailing data, partial or multiple objects and normalization collisions.'
        evidence = 'Raw frame bytes, parse-stage classification, canonical round-trip identity, schema identity and semantic-validation trace.'
        side_effects = 'A valid request may reach only its allowlisted operation.'
        forbidden = 'Malformed or ambiguous input causes no authority, ledger, receipt, trust or checkpoint effect.'
        durability = 'Canonical bytes and their hashes are stored with every durable transaction.'
        restart = 'Retry compares exact canonical request bytes; a reused identity with different bytes conflicts.'
        reconciliation = 'Only canonical, schema-valid, semantically valid evidence locators enter comparison or reconciliation.'
    }
    STATE = @{
        interpretation = 'Authority state is explicit, append-only, transactionally durable and deterministic across failure.'
        positive = 'Advance only through governed request, reservation, validation, preparation, commit and response-availability states with reconstructable responses.'
        rejection = 'Reject illegal transitions, reuse of incomplete state, conflicting retries, authority without commit and reconciliation against uncommitted or superseded receipts.'
        evidence = 'Signed state entries, request-byte identity, receipt/response content addresses, checkpoint before/after, flush and directory-durability evidence.'
        side_effects = 'Committed authority appends exactly once and exposes a deterministic response.'
        forbidden = 'No deletion, rewrite, truncation, ambiguous rejection-after-commit or mutable-cache authority.'
        durability = 'Ledger entry, receipt and response reconstruction survive crash, restart and client disconnect.'
        restart = 'Replay advances stale checkpoints, aborts incomplete reservations append-only and returns identical committed responses.'
        reconciliation = 'Only committed, nonrevoked current receipts may be reconciled; later classification is explicit and signed.'
    }
    HISTORY = @{
        interpretation = 'Historical evidence retains its original bytes and is classified under the version and authority that governed issuance.'
        positive = 'Verify every ledger entry and receipt with public material, resolve version/trust/policy/service class, and append explicit classifications where needed.'
        rejection = 'Reject reinterpretation of rejected candidates, unknown-version promotion, history rewrite and use of incomplete, aborted, superseded or revoked evidence.'
        evidence = 'Complete signature/hash/link replay, version registry, upgrade/revocation records and per-receipt deterministic classification.'
        side_effects = 'Only append-only classification, supersession, revocation, abort or recovery records may change current authority status.'
        forbidden = 'No old entry or receipt byte is edited, deleted, reordered, replaced or concealed.'
        durability = 'Public verification works without a running service or private key for the complete retained history.'
        restart = 'Restart reproduces the same classifications and prevents reuse of terminally invalid history.'
        reconciliation = 'Historical inputs are accepted only when their deterministic class permits reconciliation under the resolved version.'
    }
    OBSERVATION = @{
        interpretation = 'Events and observations are derived from current raw OS and interface evidence without expectation authority.'
        positive = 'Derive event and observation fields from signer-captured request/response/process/side-effect bytes and a finalized current-run chain.'
        rejection = 'Reject caller labels, expected values, prior events, fabricated process or effect claims, missing evidence and observation copying.'
        evidence = 'Raw process/token/image identity, exact request/response bytes, side-effect snapshots, event chain and independently derived observation trace.'
        side_effects = 'The event source and observation spool are append-only and role-scoped.'
        forbidden = 'Execution and observation principals cannot read expectations or write terminal authority stores.'
        durability = 'Finalized source and observation identities remain content-addressed and publicly resolvable.'
        restart = 'Prior-run evidence remains historical and cannot satisfy current-run freshness.'
        reconciliation = 'Candidate and fresh observations must be independently derived, complete and provenance-disjoint.'
    }
    COMPARATOR = @{
        interpretation = 'Comparison is isolated and semantic, while the signer independently repeats every disposition-determinative derivation.'
        positive = 'Compare immutable expectations to observations only after raw-evidence closure and produce a complete rule-by-rule result.'
        rejection = 'Reject matching summaries, missing raw evidence, shared actual-generation logic, fabricated comparator receipts and two invalid graphs.'
        evidence = 'Comparator principal/process identity, exact expectation/observation locators, rule trace, discrepancies and signer recomputation result.'
        side_effects = 'Comparator writes only its restricted result spool.'
        forbidden = 'Comparator has no signing key, ledger/trust/receipt write or execution-producer capability.'
        durability = 'Comparator results are immutable inputs, never terminal authority by themselves.'
        restart = 'Replayed comparator output is rejected unless it resolves to the current finalized run evidence.'
        reconciliation = 'Reconciliation repeats semantic comparison for each graph before comparing candidate and fresh results.'
    }
    TRACE = @{
        interpretation = 'Traceability resolves bidirectionally from exact clause bytes to every runtime and host artifact without circular proof.'
        positive = 'Bind clause, requirement, case, expectation, interface, principal, raw evidence, event, observation, comparator, signer, transaction, receipt, ledger, verifier and reconciliation.'
        rejection = 'Reject orphan requirements/tests/artifacts, invented clauses, summary-to-summary proof, source without execution, events without raw evidence and dependencies without requirements.'
        evidence = 'Machine-verifiable forward and reverse maps with exact content identities and zero unmapped nodes.'
        side_effects = 'Trace generation is read-only over immutable authority and current evidence.'
        forbidden = 'No trace row may create authority or substitute for missing behavior evidence.'
        durability = 'Trace identities are content-addressed with the terminal receipt and retained for public review.'
        restart = 'Reverse resolution remains complete after restart and version transition.'
        reconciliation = 'Both candidate and fresh graphs independently resolve the complete trace and disjoint provenance.'
    }
    TRUST = @{
        interpretation = 'Signing and review authority derives from separately governed public trust, role, capability, validity, rotation and revocation state.'
        positive = 'Resolve exact public trust and issuance bytes and prove the private capability is restricted to its dedicated principal and operation class.'
        rejection = 'Reject self-claims, caller keys, generic signing, expired/revoked trust, role confusion, unresolved issuers and receipt-defined authority.'
        evidence = 'Public certificate, key metadata, ACL, service SID, operation allowlist, trust issuance, validity and revocation records.'
        side_effects = 'Only the dedicated signer or upgrade authority may create its allowlisted signed records.'
        forbidden = 'No private key export, shared secret, child key use, arbitrary signing or trading/runtime authority.'
        durability = 'Public verification and revocation history persist independently of running services.'
        restart = 'Service activation revalidates trust, role, version and revocation state before accepting requests.'
        reconciliation = 'Every receipt and transition must chain to the correct trust role and version.'
    }
    UPGRADE = @{
        interpretation = 'A separately isolated authority must authorize the exact terminal component transition before installation.'
        positive = 'Issue a one-time operation-specific pre-install record binding old/new binary, policy, interface, source, build, dependencies, host, ledger, activation and rollback rules.'
        rejection = 'Reject self-authorization, post-install authorization, downgrade, policy/interface rollback, component omission/substitution, replay and another host or ledger.'
        evidence = 'Separate SID/key/trust, signed upgrade receipt, append-only upgrade ledger, installed component identities and activation verification.'
        side_effects = 'Only an authorized exact component set may become active at its governed sequence.'
        forbidden = 'Upgrade authority cannot issue terminal receipts, generic signatures or runtime/trading authority.'
        durability = 'Upgrade, rollback and revocation history is append-only and publicly verifiable.'
        restart = 'Terminal service refuses start when active files do not resolve to the current pre-install authorization and anti-downgrade state.'
        reconciliation = 'Receipt verification resolves the exact service/policy/interface version active at issuance.'
    }
    DEPENDENCY = @{
        interpretation = 'Every executable behavior input is closed by exact source, build, runtime and file identity or removed from authority.'
        positive = 'Bind compiler, references, runtime assemblies, source, options, architecture, configuration, DLL load set and every installed/executed role.'
        rejection = 'Reject Python user/current-directory imports, mutable global Git, unmanifested modules, DLL side-loading, framework or compiler-reference substitution and omitted roles.'
        evidence = 'Dependency and binary manifests, deterministic rebuild hashes, source blobs, compiler/reference hashes, process module sets and search-path evidence.'
        side_effects = 'Only measured binaries and dependencies execute from immutable ACL-protected roots.'
        forbidden = 'No Python or Git runtime authority, unbound framework input, environment import/search influence or reference-only role.'
        durability = 'Installed and running identities remain content-bound and publicly reproducible.'
        restart = 'Every service revalidates its binary, policy and runtime dependency closure at activation.'
        reconciliation = 'Candidate and fresh builds resolve the same source/dependency identities and separately measured processes.'
    }
    OUTER = @{
        interpretation = 'Tests and terminal decisions exercise the actual hostile outer authority interfaces and independently verify their effects.'
        positive = 'Invoke public submit, execute, retrieve, verify, ledger, trust, reconciliation, replay, recovery and version operations with real caller principals.'
        rejection = 'Reject fixture substitution, inner execute_case results, fabricated PASS/effects/receipt membership and requests carrying expected outcomes.'
        evidence = 'Signer-captured raw frames, caller PID/SID/image, response frames, durable/forbidden side effects and ledger/store snapshots.'
        side_effects = 'Positive operations create only their governed transactional effects; negative operations create no authority effect.'
        forbidden = 'No fixture result or child summary may substitute for actual public-interface behavior.'
        durability = 'Outer results, committed responses and receipt locators survive retry and restart.'
        restart = 'Unavailable services fail closed and committed requests reconstruct identically after restart.'
        reconciliation = 'External reconciliation consumes only publicly verifiable terminal locators and complete graphs.'
    }
    DOCUMENT = @{
        interpretation = 'Architecture and authorization claims use a closed proof grammar and preserve every withheld boundary.'
        positive = 'Accept only explicitly supported proof/classification vocabulary backed by the complete evidence chain.'
        rejection = 'Reject unknown approval verbs/euphemisms, ambiguity, unsupported completion, acceptance, merge, deployment or trading claims.'
        evidence = 'Closed grammar result plus linked clause, implementation, positive/mutation, expectation, event, observation, comparison and trace evidence.'
        side_effects = 'Documents remain proposal-only and do not change canonical or operational authority.'
        forbidden = 'No self-approval, acceptance, merge, canonical incorporation, deployment, trading or later-phase authorization.'
        durability = 'Withheld classifications remain explicit in every retained report and receipt.'
        restart = 'Documentation authority is independent of runtime state.'
        reconciliation = 'Candidate/fresh proof claims are permitted only after both complete graphs and external reconciliation verify.'
    }
}

$sourceManifest = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $SourceRoot 'authority_source_manifest.json') | ConvertFrom-Json
$sourceMetadata = @{}
foreach ($row in $sourceManifest.sources) { $sourceMetadata[$row.name] = $row }

$specCategory = [ordered]@{
    'CPB-R4-01'='PATH'; 'CPB-R4-02'='SEPARATION'; 'CPB-R4-03'='CANONICAL'; 'CPB-R4-04'='STATE'; 'CPB-R4-05'='HISTORY'; 'CPB-R4-06'='OBSERVATION'; 'CPB-R4-07'='COMPARATOR'; 'CPB-R4-08'='DOCUMENT'; 'CPB-R4-09'='TRACE'; 'CPB-R4-10'='TRUST'; 'CPB-R4-11'='DOCUMENT';
    'CPB-R5-01'='PATH'; 'CPB-R5-02'='HISTORY'; 'CPB-R5-03'='COMPARATOR'; 'CPB-R5-04'='OBSERVATION'; 'CPB-R5-05'='OBSERVATION'; 'CPB-R5-06'='CANONICAL'; 'CPB-R5-07'='TRACE'; 'CPB-R5-08'='TRUST'; 'CPB-R5-09'='TRUST'; 'CPB-R5-10'='DOCUMENT';
    'CPB-R6-01'='PATH'; 'CPB-R6-02'='SEPARATION'; 'CPB-R6-03'='STATE'; 'CPB-R6-04'='OBSERVATION'; 'CPB-R6-05'='OBSERVATION'; 'CPB-R6-06'='OBSERVATION'; 'CPB-R6-07'='CANONICAL'; 'CPB-R6-08'='TRACE'; 'CPB-R6-09'='TRUST'; 'CPB-R6-10'='TRUST'; 'CPB-R6-11'='DEPENDENCY'; 'CPB-R6-12'='OUTER'; 'CPB-R6-13'='STATE'; 'CPB-R6-14'='DOCUMENT'; 'CPB-R6-15'='DOCUMENT'
}

$records = New-Object System.Collections.Generic.List[object]

function Add-Requirement {
    param(
        [string]$Id,
        [string]$SourceName,
        [string]$SectionHeading,
        [int]$StartLine,
        [int]$EndLine,
        [string]$Category,
        [string]$InterpretationSuffix
    )
    $source = Read-AuthoritySource -FileName ([System.IO.Path]::GetFileName($sourceMetadata[$SourceName].package_path))
    $range = Get-LineRange -Source $source -StartLine $StartLine -EndLine $EndLine
    $control = $categoryControls[$Category]
    if ($null -eq $control) { throw "unknown category $Category" }
    $records.Add([pscustomobject][ordered]@{
        requirement_id = $Id
        governing_commit = $sourceMetadata[$SourceName].governing_commit
        governing_blob = $sourceMetadata[$SourceName].governing_blob
        governing_path = $sourceMetadata[$SourceName].governing_path
        section_heading = $SectionHeading
        line_range = "$StartLine-$EndLine"
        byte_range = "$($range.StartByte)-$($range.EndByteExclusive)"
        quoted_clause_text = $range.Quote
        clause_raw_sha256 = $range.QuoteSha256
        requirement_interpretation = $control.interpretation + ' ' + $InterpretationSuffix
        required_positive_behavior = $control.positive
        required_rejection_behavior = $control.rejection
        required_evidence = $control.evidence
        required_side_effects = $control.side_effects
        forbidden_side_effects = $control.forbidden
        durability_obligation = $control.durability
        restart_retry_replay_obligation = $control.restart
        reconciliation_obligation = $control.reconciliation
        acceptance_significance = 'BLOCKING'
        control_category = $Category
        primary_authority = $true
    })
}

$spec = Read-AuthoritySource -FileName 'R6_SPECIFICATION.md'
for ($index = 0; $index -lt $spec.Lines.Length; $index++) {
    $line = $spec.Lines[$index]
    $clauseId = $null
    $heading = $null
    if ($line -match '^## R4-(\d{2})$') {
        $clauseId = 'CPB-R4-' + $Matches[1]
        $heading = $line.Substring(3)
    }
    elseif ($line -match '^### \[(CPB-R[56]-\d{2})\] (.+)$') {
        $clauseId = $Matches[1]
        $heading = $Matches[2]
    }
    if ($null -ne $clauseId) {
        $clauseLine = $index + 2
        while ($clauseLine -le $spec.Lines.Length -and [String]::IsNullOrWhiteSpace($spec.Lines[$clauseLine - 1])) { $clauseLine++ }
        if ($clauseLine -gt $spec.Lines.Length) { throw "missing clause body for $clauseId" }
        $clauseEndLine = if ($clauseId.StartsWith('CPB-R4-', [StringComparison]::Ordinal)) { $clauseLine + 2 } else { $clauseLine }
        if ($clauseEndLine -gt $spec.Lines.Length) { throw "incomplete clause body for $clauseId" }
        $id = 'R7RM-' + $clauseId.Substring(4)
        Add-Requirement -Id $id -SourceName 'R6_SPECIFICATION' -SectionHeading $heading -StartLine $clauseLine -EndLine $clauseEndLine -Category $specCategory[$clauseId] -InterpretationSuffix "Exact retained clause $clauseId."
    }
}

$r6bCategories = @('PATH','SEPARATION','STATE','OBSERVATION','TRACE','TRUST','PATH','DOCUMENT','OUTER','OUTER')
for ($item = 1; $item -le 10; $item++) {
    $id = if ($item -le 9) { 'R7RM-R6B-{0:D2}' -f $item } else { 'R7RM-R6-MATRIX' }
    Add-Requirement -Id $id -SourceName 'R6_INDEPENDENT_REJECTION' -SectionHeading 'Exact remediation required for each rejected item' -StartLine (244 + $item) -EndLine (244 + $item) -Category $r6bCategories[$item - 1] -InterpretationSuffix "R6 rejection correction item $item is retained as external remediation authority."
}

Add-Requirement -Id 'R7RM-R7B-01' -SourceName 'R7_INCOMPLETE_RECORD' -SectionHeading 'Blocking finding R7-B01 — replaceable authority client permits complete replay' -StartLine 70 -EndLine 70 -Category 'OUTER' -InterpretationSuffix 'Complete prior-result replay with zero current processes or events must never obtain terminal authority.'
Add-Requirement -Id 'R7RM-R7B-02' -SourceName 'R7_INCOMPLETE_RECORD' -SectionHeading 'Blocking finding R7-B02 — reconciliation trusts caller dictionaries' -StartLine 88 -EndLine 88 -Category 'COMPARATOR' -InterpretationSuffix 'Reconciliation must resolve immutable signed graphs and reject caller dictionaries or summaries.'
$r7tCategories = @('SEPARATION','OUTER','TRUST','TRUST','COMPARATOR','STATE','OUTER','OUTER','DOCUMENT')
for ($item = 1; $item -le 9; $item++) {
    Add-Requirement -Id ('R7RM-R7T-{0:D2}' -f $item) -SourceName 'R7_INCOMPLETE_RECORD' -SectionHeading 'Exact remediation required' -StartLine (97 + $item) -EndLine (97 + $item) -Category $r7tCategories[$item - 1] -InterpretationSuffix "R7 terminal correction item $item."
}

$r7hCategories = @('TRUST','TRUST','SEPARATION','STATE','OUTER','OUTER')
for ($item = 1; $item -le 6; $item++) {
    Add-Requirement -Id ('R7RM-R7H-{0:D2}' -f $item) -SourceName 'R7_BLOCKED_RECORD' -SectionHeading 'Exact authority required to unblock' -StartLine (97 + $item) -EndLine (97 + $item) -Category $r7hCategories[$item - 1] -InterpretationSuffix "Provisioned host authority prerequisite $item."
}

$review = Read-AuthoritySource -FileName 'R7_INDEPENDENT_FINDINGS_LEDGER.json'
$reviewCategories = @('TRACE','SEPARATION','OUTER','COMPARATOR','SEPARATION','CANONICAL','UPGRADE','HISTORY','STATE','STATE','PATH','DEPENDENCY','HISTORY','TRACE','DEPENDENCY','OUTER')
for ($item = 1; $item -le 16; $item++) {
    $findingId = 'R7AR-B{0:D2}' -f $item
    $idLineIndex = -1
    for ($index = 0; $index -lt $review.Lines.Length; $index++) {
        if ($review.Lines[$index] -match ('"id":\s*"' + [regex]::Escape($findingId) + '"')) { $idLineIndex = $index; break }
    }
    if ($idLineIndex -lt 0) { throw "review blocker not found: $findingId" }
    $startIndex = $idLineIndex
    while ($startIndex -ge 0 -and $review.Lines[$startIndex].Trim() -ne '{') { $startIndex-- }
    $endIndex = $idLineIndex
    while ($endIndex -lt $review.Lines.Length -and $review.Lines[$endIndex].Trim() -notmatch '^\},?$') { $endIndex++ }
    Add-Requirement -Id ('R7RM-AR-B{0:D2}' -f $item) -SourceName 'R7_INDEPENDENT_FINDINGS_LEDGER' -SectionHeading 'blocking_findings' -StartLine ($startIndex + 1) -EndLine ($endIndex + 1) -Category $reviewCategories[$item - 1] -InterpretationSuffix "Independent rejection blocker $findingId must be directly closed."
}

$ids = @($records | ForEach-Object requirement_id)
if (@($ids | Sort-Object -Unique).Count -ne $ids.Count) { throw 'duplicate requirement ID' }
if ($records.Count -ne 79) { throw "unexpected independently reconstructed requirement count: $($records.Count)" }

$registry = [pscustomobject][ordered]@{
    artifact_type = 'R7_REMEDIATION_GOVERNED_REQUIREMENT_REGISTRY'
    schema_version = '1.0.0'
    authority_source_manifest = 'AuthoritySources/authority_source_manifest.json'
    governing_requirement_count = $records.Count
    independently_reconstructed = $true
    prohibited_source_commit = 'f0cfbce97e913a133530dd66a70326b1e03a0fb6'
    prohibited_source_reference_count = 0
    requirements = $records.ToArray()
}
$json = $registry | ConvertTo-Json -Depth 12
$output = Join-Path $PackageRoot 'governed_requirement_registry.json'
[System.IO.File]::WriteAllText($output, $json + "`n", $Utf8)
[pscustomobject]@{
    requirement_count = $records.Count
    unique_clause_hash_count = @($records | Select-Object -ExpandProperty clause_raw_sha256 -Unique).Count
    output_sha256 = Get-LowerSha256 -Bytes ([System.IO.File]::ReadAllBytes($output))
    prohibited_source_reference_count = 0
} | ConvertTo-Json
