param()

$ErrorActionPreference = 'Stop'
$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = (Resolve-Path (Join-Path $PackageRoot '..\..\..')).Path
$OutputRoot = Join-Path $PackageRoot 'AuthoritySources'
$GitExecutable = 'C:\Program Files\Git\cmd\git.exe'

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

function Read-GitBlob {
    param([string]$ObjectId)
    $safe = $RepositoryRoot.Replace('\', '/')
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $GitExecutable
    $psi.Arguments = "-c safe.directory=$safe cat-file blob $ObjectId"
    $psi.WorkingDirectory = $RepositoryRoot
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $process = [System.Diagnostics.Process]::Start($psi)
    $memory = New-Object System.IO.MemoryStream
    $copy = $process.StandardOutput.BaseStream.CopyToAsync($memory)
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()
    $copy.Wait()
    if ($process.ExitCode -ne 0) {
        throw "git cat-file failed for $ObjectId`: $stderr"
    }
    return $memory.ToArray()
}

$sources = @(
    [pscustomobject][ordered]@{
        name = 'R6_SPECIFICATION'
        commit = '87d066eb16d7fe0b6a1677ea7739c5c2ead4ad94'
        blob = '343622743668d7ddc524513307e726f20d1db9fc'
        path = 'Architecture/15_Randle_AI_Current_Production_Baseline_Capture_Boundary_Specification_DRAFT.md'
        mode = '100644'
        size = 11248
        raw_sha256 = '7c5fc26a75dff3fe3d23167424d6d4c12ac04e9fda21fc20cce63e04000399b6'
        output = 'R6_SPECIFICATION.md'
    },
    [pscustomobject][ordered]@{
        name = 'R6_INDEPENDENT_REJECTION'
        commit = 'c286a89d3d858afdfcf677f087c723a460c1e396'
        blob = '851a2aadef9e121e11b5b43837dd37c0a7c2dc96'
        path = 'Architecture/Audits/2026-07-22_Current_Production_Baseline_Boundary_R6_Independent_Review_87d066e_REJECTED.md'
        mode = '100644'
        size = 41590
        raw_sha256 = '27925c8b8ab0e59f4f0fe70585129ccc3d72e8301c95a35a6e42321a66ebb8c5'
        output = 'R6_INDEPENDENT_REJECTION.md'
    },
    [pscustomobject][ordered]@{
        name = 'R7_INCOMPLETE_RECORD'
        commit = '06c6805ed52a0d539a73088c097c60dec335462a'
        blob = '1be3b0b5f15ac8e68b88202e0e9d3787b69d1856'
        path = 'Architecture/Audits/2026-07-22_Current_Production_Baseline_Boundary_R7_Remediation_87d066e_INCOMPLETE.md'
        mode = '100644'
        size = 9817
        raw_sha256 = '344c29dc3594d702cf6f959347f579b5a17aa04c722b02ad264b8f866a64e5bf'
        output = 'R7_INCOMPLETE_RECORD.md'
    },
    [pscustomobject][ordered]@{
        name = 'R7_BLOCKED_RECORD'
        commit = '8ec5697b3c6fd9d93b972113b7e79d033b4cb1f6'
        blob = 'dfa98a89049b9596387143c002252d91d608fbfc'
        path = 'Architecture/Audits/2026-07-23_Current_Production_Baseline_Boundary_R7_Continuation_87d066e_TASK_BLOCKED.md'
        mode = '100644'
        size = 8927
        raw_sha256 = 'f5b03f5820f29bdbe60595b1ec89696ca4aac75eddf76dad6cd0e58da5b74412'
        output = 'R7_BLOCKED_RECORD.md'
    },
    [pscustomobject][ordered]@{
        name = 'R7_INDEPENDENT_FINDINGS_LEDGER'
        commit = '9d813a4bad29ec04f022f54ffcae73a5d542eb44'
        blob = '1a14d1b53e3f77876c9753513b817498f180fd38'
        path = 'Architecture/Audits/2026-07-23_R7_Independent_Terminal_Authority_Acceptance_Review/INDEPENDENT_FINDINGS_LEDGER.json'
        mode = '100644'
        size = 8550
        raw_sha256 = 'f52edac4af1bfbfdb2017eff761eaaa873fcabc31ab7c98e43f1a217731db88c'
        output = 'R7_INDEPENDENT_FINDINGS_LEDGER.json'
    }
)

if (-not (Test-Path -LiteralPath $OutputRoot)) {
    New-Item -ItemType Directory -Path $OutputRoot | Out-Null
}

$manifestRows = foreach ($source in $sources) {
    $bytes = Read-GitBlob -ObjectId $source.blob
    $actualHash = Get-LowerSha256 -Bytes $bytes
    if ($bytes.Length -ne $source.size) {
        throw "size mismatch for $($source.name)"
    }
    if ($actualHash -ne $source.raw_sha256) {
        throw "SHA-256 mismatch for $($source.name)"
    }
    $destination = Join-Path $OutputRoot $source.output
    [System.IO.File]::WriteAllBytes($destination, $bytes)
    [pscustomobject][ordered]@{
        name = $source.name
        governing_commit = $source.commit
        governing_blob = $source.blob
        governing_path = $source.path
        mode = $source.mode
        size = $source.size
        raw_sha256 = $source.raw_sha256
        package_path = ('AuthoritySources/' + $source.output)
    }
}

# The independent findings ledger above is the normative blocker enumeration.
# The other review files are supporting evidence and review tooling, not case or
# expectation authority.  Retain and verify the complete 30-file package so a
# later verifier can prove that no detailed review evidence was omitted while
# still keeping the normative-source boundary explicit.
$reviewCommit = '9d813a4bad29ec04f022f54ffcae73a5d542eb44'
$reviewTree = '85abba68282fee48223fa5ee5197c2535bc965bc'
$reviewPrefix = 'Architecture/Audits/2026-07-23_R7_Independent_Terminal_Authority_Acceptance_Review/'
$reviewManifestBlob = '3fafae50fb49eee7a457eafad8ec5e60165c3468'
$reviewManifestSha256 = '9048534df7f933d8a388ef5e2fea0133e24349229f0662592b6964c9c58ccec3'
$reviewManifestSize = 10721
$reviewManifestBytes = Read-GitBlob -ObjectId $reviewManifestBlob
if ($reviewManifestBytes.Length -ne $reviewManifestSize -or (Get-LowerSha256 -Bytes $reviewManifestBytes) -ne $reviewManifestSha256) {
    throw 'independent review manifest identity mismatch'
}
$strictUtf8 = New-Object System.Text.UTF8Encoding($false, $true)
$reviewManifest = $strictUtf8.GetString($reviewManifestBytes) | ConvertFrom-Json
if ($reviewManifest.artifact_type -cne 'R7_INDEPENDENT_ACCEPTANCE_REVIEW_MANIFEST' -or
    $reviewManifest.base_candidate_commit -cne '35add65e8900ce9a48c3a7175e5e61e5e0868a84' -or
    -not ([string]$reviewManifest.disposition).StartsWith('REJECT', [StringComparison]::Ordinal) -or
    -not ([string]$reviewManifest.disposition).EndsWith('R7 REMEDIATION REQUIRED', [StringComparison]::Ordinal) -or
    [int]$reviewManifest.file_count_excluding_manifest -ne 29 -or
    @($reviewManifest.files).Count -ne 29) {
    throw 'independent review manifest semantics mismatch'
}
$reviewOutputRoot = Join-Path $OutputRoot 'IndependentReview'
if (-not (Test-Path -LiteralPath $reviewOutputRoot)) { New-Item -ItemType Directory -Path $reviewOutputRoot | Out-Null }
$reviewManifestDestination = Join-Path $reviewOutputRoot 'review_manifest.json'
[System.IO.File]::WriteAllBytes($reviewManifestDestination, $reviewManifestBytes)
$reviewPackageRows = New-Object System.Collections.Generic.List[object]
$reviewPackageRows.Add([pscustomobject][ordered]@{
    git_blob = $reviewManifestBlob
    mode = '100644'
    path = $reviewPrefix + 'review_manifest.json'
    package_path = 'AuthoritySources/IndependentReview/review_manifest.json'
    raw_sha256 = $reviewManifestSha256
    size = $reviewManifestSize
})
$seenReviewPaths = @{}
foreach ($row in @($reviewManifest.files | Sort-Object path)) {
    $path = [string]$row.path
    if (-not $path.StartsWith($reviewPrefix, [StringComparison]::Ordinal) -or $path.Substring($reviewPrefix.Length).Contains('/') -or $seenReviewPaths.ContainsKey($path)) {
        throw "invalid or duplicate independent review path: $path"
    }
    if ([string]$row.mode -cne '100644' -or [string]$row.git_blob -notmatch '^[0-9a-f]{40}$' -or [string]$row.raw_sha256 -notmatch '^[0-9a-f]{64}$' -or [long]$row.size -lt 1) {
        throw "invalid independent review manifest row: $path"
    }
    $seenReviewPaths[$path] = $true
    $bytes = Read-GitBlob -ObjectId ([string]$row.git_blob)
    if ($bytes.Length -ne [long]$row.size -or (Get-LowerSha256 -Bytes $bytes) -cne [string]$row.raw_sha256) {
        throw "independent review file identity mismatch: $path"
    }
    $leaf = $path.Substring($reviewPrefix.Length)
    [System.IO.File]::WriteAllBytes((Join-Path $reviewOutputRoot $leaf), $bytes)
    $reviewPackageRows.Add([pscustomobject][ordered]@{
        git_blob = [string]$row.git_blob
        mode = [string]$row.mode
        path = $path
        package_path = 'AuthoritySources/IndependentReview/' + $leaf
        raw_sha256 = [string]$row.raw_sha256
        size = [long]$row.size
    })
}
if ($reviewPackageRows.Count -ne 30) { throw 'complete independent review package must contain 30 files' }

$manifest = [pscustomobject][ordered]@{
    artifact_type = 'R7_REMEDIATION_IMMUTABLE_AUTHORITY_SOURCE_MANIFEST'
    schema_version = '1.0.0'
    prohibited_source_commit = 'f0cfbce97e913a133530dd66a70326b1e03a0fb6'
    prohibited_source_dependency_count = 0
    source_count = $manifestRows.Count
    sources = @($manifestRows)
    independent_review_package_commit = $reviewCommit
    independent_review_package_tree = $reviewTree
    independent_review_package_file_count = $reviewPackageRows.Count
    independent_review_package_files = $reviewPackageRows.ToArray()
    independent_review_normative_source = 'INDEPENDENT_FINDINGS_LEDGER.json'
    independent_review_supporting_files_normative = $false
}
$json = $manifest | ConvertTo-Json -Depth 8
[System.IO.File]::WriteAllText((Join-Path $OutputRoot 'authority_source_manifest.json'), $json + "`n", [System.Text.UTF8Encoding]::new($false))
$json
