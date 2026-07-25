using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;

namespace RandleAI.R7Remediation
{
    internal sealed class R7AuthorityIdentities
    {
        internal string RequirementSha256;
        internal string CaseSha256;
        internal string ExpectationSha256;
        internal string CoverageSha256;
        internal string SourceManifestSha256;

        internal R7AuthorityIdentities(string requirement, string cases, string expectations, string coverage, string sourceManifest)
        {
            RequirementSha256 = requirement;
            CaseSha256 = cases;
            ExpectationSha256 = expectations;
            CoverageSha256 = coverage;
            SourceManifestSha256 = sourceManifest;
        }
    }

    internal sealed class R7CaseDefinition
    {
        internal string CaseId;
        internal string Title;
        internal string Driver;
        internal string Operation;
        internal string CallerRole;
        internal string Mutation;
        internal string Surface;
        internal string[] RequirementIds;
        internal string[] EvidenceRequirements;
        internal SortedDictionary<string, object> Raw;
    }

    internal sealed class R7AuthorityLocation
    {
        internal string RequirementPath;
        internal string CasePath;
        internal string ExpectationPath;
        internal string CoveragePath;
        internal string SourceRoot;
        internal string SourceManifestPath;

        internal static R7AuthorityLocation Fixed()
        {
            return new R7AuthorityLocation
            {
                RequirementPath = R7Fixed.RequirementPath,
                CasePath = R7Fixed.CasePath,
                ExpectationPath = R7Fixed.ExpectationPath,
                CoveragePath = R7Fixed.CoveragePath,
                SourceRoot = R7Fixed.AuthoritySourceRoot,
                SourceManifestPath = R7Fixed.AuthoritySourceManifestPath
            };
        }
    }

    internal sealed class R7Expectation
    {
        internal string ExpectationId;
        internal string CaseId;
        internal string Classification;
        internal string ResponseClass;
        internal string ResultCode;
        internal string PublicClassification;
        internal string[] RequiredEvidence;
        internal string[] RequiredEffects;
        internal string[] ForbiddenEffects;
        internal string RestartRetry;
        internal SortedDictionary<string, object> Raw;
    }

    internal sealed class R7AuthoritySet
    {
        private const string ProhibitedCommit = "f0cfbce97e913a133530dd66a70326b1e03a0fb6";
        private readonly Dictionary<string, SortedDictionary<string, object>> requirements = new Dictionary<string, SortedDictionary<string, object>>(StringComparer.Ordinal);
        private readonly Dictionary<string, R7CaseDefinition> cases = new Dictionary<string, R7CaseDefinition>(StringComparer.Ordinal);
        private readonly Dictionary<string, R7Expectation> expectations = new Dictionary<string, R7Expectation>(StringComparer.Ordinal);
        internal readonly R7AuthorityIdentities Identities;

        internal R7AuthoritySet(R7AuthorityIdentities expected)
            : this(expected, R7AuthorityLocation.Fixed())
        {
        }

        internal R7AuthoritySet(R7AuthorityIdentities expected, R7AuthorityLocation location)
        {
            Identities = expected;
            SortedDictionary<string, object> sourceManifest = ReadArtifact(location.SourceManifestPath, location.SourceRoot, expected.SourceManifestSha256);
            Dictionary<string, SourceRecord> sources = VerifySourceManifest(sourceManifest, location.SourceRoot);
            SortedDictionary<string, object> registry = ReadArtifact(location.RequirementPath, Path.GetDirectoryName(location.RequirementPath), expected.RequirementSha256);
            VerifyRequirements(registry, sources);
            SortedDictionary<string, object> caseArtifact = ReadArtifact(location.CasePath, Path.GetDirectoryName(location.CasePath), expected.CaseSha256);
            VerifyCases(caseArtifact);
            SortedDictionary<string, object> expectationArtifact = ReadArtifact(location.ExpectationPath, Path.GetDirectoryName(location.ExpectationPath), expected.ExpectationSha256);
            VerifyExpectations(expectationArtifact);
            SortedDictionary<string, object> coverage = ReadArtifact(location.CoveragePath, Path.GetDirectoryName(location.CoveragePath), expected.CoverageSha256);
            VerifyCoverage(coverage);
        }

        internal R7CaseDefinition Case(string caseId)
        {
            R7CaseDefinition value;
            if (!cases.TryGetValue(caseId, out value)) throw new R7ProtocolException("CASE_IDENTITY_UNRESOLVED");
            return value;
        }

        internal R7Expectation Expectation(string caseId)
        {
            R7Expectation value;
            if (!expectations.TryGetValue(caseId, out value)) throw new R7ProtocolException("EXPECTATION_IDENTITY_UNRESOLVED");
            return value;
        }

        internal string[] CaseIds
        {
            get { List<string> ids = new List<string>(cases.Keys); ids.Sort(StringComparer.Ordinal); return ids.ToArray(); }
        }

        internal SortedDictionary<string, object> Requirement(string requirementId)
        {
            SortedDictionary<string, object> value;
            if (!requirements.TryGetValue(requirementId, out value)) throw new R7ProtocolException("REQUIREMENT_IDENTITY_UNRESOLVED");
            return value;
        }

        internal string[] RequirementIds
        {
            get { List<string> ids = new List<string>(requirements.Keys); ids.Sort(StringComparer.Ordinal); return ids.ToArray(); }
        }

        private static SortedDictionary<string, object> ReadArtifact(string path, string root, string expectedSha256)
        {
            using (R7VerifiedFile file = R7SafeFile.Open(path, path, root, expectedSha256, null, null, null))
            {
                object parsed = R7Json.Parse(file.Bytes);
                SortedDictionary<string, object> value = parsed as SortedDictionary<string, object>;
                if (value == null) throw new R7ProtocolException("AUTHORITY_ARTIFACT_ROOT_NOT_OBJECT");
                return value;
            }
        }

        private static Dictionary<string, SourceRecord> VerifySourceManifest(SortedDictionary<string, object> manifest, string sourceRoot)
        {
            R7Json.ExactKeys(manifest, "artifact_type", "independent_review_normative_source", "independent_review_package_commit", "independent_review_package_file_count", "independent_review_package_files", "independent_review_package_tree", "independent_review_supporting_files_normative", "prohibited_source_commit", "prohibited_source_dependency_count", "schema_version", "source_count", "sources");
            if (!String.Equals(R7Json.String(manifest, "artifact_type", 1, 256), "R7_REMEDIATION_IMMUTABLE_AUTHORITY_SOURCE_MANIFEST", StringComparison.Ordinal)) throw new R7ProtocolException("SOURCE_MANIFEST_TYPE");
            if (!String.Equals(R7Json.String(manifest, "prohibited_source_commit", 40, 40), ProhibitedCommit, StringComparison.Ordinal)) throw new R7ProtocolException("PROHIBITED_SOURCE_MARKER_MISMATCH");
            if (R7Json.Integer(manifest, "prohibited_source_dependency_count", 0, 0) != 0) throw new R7ProtocolException("PROHIBITED_SOURCE_DEPENDENCY");
            if (R7Json.Integer(manifest, "source_count", 5, 5) != 5) throw new R7ProtocolException("SOURCE_COUNT");
            object[] rows = R7Json.Array(manifest, "sources");
            if (rows.Length != 5) throw new R7ProtocolException("SOURCE_COUNT");
            Dictionary<string, SourceRecord> result = new Dictionary<string, SourceRecord>(StringComparer.Ordinal);
            foreach (object rawRow in rows)
            {
                SortedDictionary<string, object> row = RequireObject(rawRow, "source manifest row");
                R7Json.ExactKeys(row, "governing_blob", "governing_commit", "governing_path", "mode", "name", "package_path", "raw_sha256", "size");
                string relative = R7Json.String(row, "package_path", 1, 1024);
                const string prefix = "AuthoritySources/";
                if (!relative.StartsWith(prefix, StringComparison.Ordinal) || relative.IndexOf("..", StringComparison.Ordinal) >= 0) throw new R7ProtocolException("SOURCE_PACKAGE_PATH");
                string full = Path.Combine(sourceRoot, relative.Substring(prefix.Length).Replace('/', Path.DirectorySeparatorChar));
                string sha = R7Json.String(row, "raw_sha256", 64, 64);
                long expectedSize = R7Json.Integer(row, "size", 1, Int32.MaxValue);
                byte[] bytes;
                using (R7VerifiedFile file = R7SafeFile.Open(full, full, sourceRoot, sha, null, null, null))
                {
                    if (file.Measurement.Size != expectedSize) throw new R7ProtocolException("SOURCE_SIZE_MISMATCH");
                    bytes = file.Bytes;
                }
                SourceRecord record = new SourceRecord
                {
                    Commit = R7Json.String(row, "governing_commit", 40, 40),
                    Blob = R7Json.String(row, "governing_blob", 40, 40),
                    GoverningPath = R7Json.String(row, "governing_path", 1, 4096),
                    Bytes = bytes,
                    Text = StrictText(bytes)
                };
                string key = SourceKey(record.Commit, record.Blob, record.GoverningPath);
                if (result.ContainsKey(key)) throw new R7ProtocolException("DUPLICATE_SOURCE_AUTHORITY");
                result.Add(key, record);
            }
            VerifyIndependentReviewPackage(manifest, sourceRoot);
            return result;
        }

        private static void VerifyIndependentReviewPackage(SortedDictionary<string, object> sourceManifest, string sourceRoot)
        {
            const string reviewCommit = "9d813a4bad29ec04f022f54ffcae73a5d542eb44";
            const string reviewTree = "85abba68282fee48223fa5ee5197c2535bc965bc";
            const string reviewPrefix = "Architecture/Audits/2026-07-23_R7_Independent_Terminal_Authority_Acceptance_Review/";
            const string packagePrefix = "AuthoritySources/IndependentReview/";
            if (!String.Equals(R7Json.String(sourceManifest, "independent_review_package_commit", 40, 40), reviewCommit, StringComparison.Ordinal) ||
                !String.Equals(R7Json.String(sourceManifest, "independent_review_package_tree", 40, 40), reviewTree, StringComparison.Ordinal) ||
                !String.Equals(R7Json.String(sourceManifest, "independent_review_normative_source", 1, 256), "INDEPENDENT_FINDINGS_LEDGER.json", StringComparison.Ordinal) ||
                R7Json.Boolean(sourceManifest, "independent_review_supporting_files_normative") ||
                R7Json.Integer(sourceManifest, "independent_review_package_file_count", 30, 30) != 30) throw new R7ProtocolException("INDEPENDENT_REVIEW_PACKAGE_IDENTITY_INVALID");
            object[] packageRows = R7Json.Array(sourceManifest, "independent_review_package_files");
            if (packageRows.Length != 30) throw new R7ProtocolException("INDEPENDENT_REVIEW_PACKAGE_COUNT");
            Dictionary<string, SortedDictionary<string, object>> byReviewPath = new Dictionary<string, SortedDictionary<string, object>>(StringComparer.Ordinal);
            SortedDictionary<string, object> retainedManifest = null;
            foreach (object raw in packageRows)
            {
                SortedDictionary<string, object> row = RequireObject(raw, "independent review package row");
                R7Json.ExactKeys(row, "git_blob", "mode", "package_path", "path", "raw_sha256", "size");
                string reviewPath = R7Json.String(row, "path", 1, 4096);
                string packagePath = R7Json.String(row, "package_path", 1, 4096);
                string blob = R7Json.String(row, "git_blob", 40, 40);
                string sha = R7Json.String(row, "raw_sha256", 64, 64);
                long size = R7Json.Integer(row, "size", 1, Int32.MaxValue);
                if (!reviewPath.StartsWith(reviewPrefix, StringComparison.Ordinal) || reviewPath.IndexOf("..", StringComparison.Ordinal) >= 0 ||
                    !packagePath.StartsWith(packagePrefix, StringComparison.Ordinal) || packagePath.IndexOf("..", StringComparison.Ordinal) >= 0 ||
                    !String.Equals(reviewPath.Substring(reviewPrefix.Length), packagePath.Substring(packagePrefix.Length), StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(row, "mode", 6, 6), "100644", StringComparison.Ordinal) ||
                    !IsLowerHex(blob, 40) || !R7Hash.IsLowerSha256(sha) || byReviewPath.ContainsKey(reviewPath)) throw new R7ProtocolException("INDEPENDENT_REVIEW_PACKAGE_ROW_INVALID");
                string full = Path.Combine(sourceRoot, packagePath.Substring("AuthoritySources/".Length).Replace('/', Path.DirectorySeparatorChar));
                byte[] bytes;
                using (R7VerifiedFile file = R7SafeFile.Open(full, full, sourceRoot, sha, null, null, null))
                {
                    if (file.Measurement.Size != size) throw new R7ProtocolException("INDEPENDENT_REVIEW_PACKAGE_SIZE_MISMATCH");
                    bytes = file.Bytes;
                }
                byReviewPath.Add(reviewPath, row);
                if (reviewPath == reviewPrefix + "review_manifest.json") retainedManifest = RequireObject(R7Json.Parse(bytes), "independent review manifest");
            }
            if (retainedManifest == null) throw new R7ProtocolException("INDEPENDENT_REVIEW_MANIFEST_MISSING");
            R7Json.ExactKeys(retainedManifest, "artifact_type", "base_candidate_commit", "disposition", "file_count_excluding_manifest", "files", "manifest_self_exclusion", "prohibited_r7_ancestors", "review_branch", "schema_version");
            if (!String.Equals(R7Json.String(retainedManifest, "artifact_type", 1, 256), "R7_INDEPENDENT_ACCEPTANCE_REVIEW_MANIFEST", StringComparison.Ordinal) ||
                !String.Equals(R7Json.String(retainedManifest, "base_candidate_commit", 40, 40), "35add65e8900ce9a48c3a7175e5e61e5e0868a84", StringComparison.Ordinal) ||
                !R7Json.String(retainedManifest, "disposition", 1, 256).StartsWith("REJECT", StringComparison.Ordinal) ||
                !R7Json.String(retainedManifest, "disposition", 1, 256).EndsWith("R7 REMEDIATION REQUIRED", StringComparison.Ordinal) ||
                R7Json.Integer(retainedManifest, "file_count_excluding_manifest", 29, 29) != 29) throw new R7ProtocolException("INDEPENDENT_REVIEW_MANIFEST_SEMANTICS_INVALID");
            object[] declaredFiles = R7Json.Array(retainedManifest, "files");
            if (declaredFiles.Length != 29) throw new R7ProtocolException("INDEPENDENT_REVIEW_MANIFEST_COUNT");
            foreach (object raw in declaredFiles)
            {
                SortedDictionary<string, object> declared = RequireObject(raw, "independent review manifest file");
                R7Json.ExactKeys(declared, "git_blob", "mode", "path", "raw_sha256", "size");
                string path = R7Json.String(declared, "path", 1, 4096);
                SortedDictionary<string, object> retained;
                if (!byReviewPath.TryGetValue(path, out retained) ||
                    !String.Equals(R7Json.String(declared, "git_blob", 40, 40), R7Json.String(retained, "git_blob", 40, 40), StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(declared, "mode", 6, 6), R7Json.String(retained, "mode", 6, 6), StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(declared, "raw_sha256", 64, 64), R7Json.String(retained, "raw_sha256", 64, 64), StringComparison.Ordinal) ||
                    R7Json.Integer(declared, "size", 1, Int32.MaxValue) != R7Json.Integer(retained, "size", 1, Int32.MaxValue)) throw new R7ProtocolException("INDEPENDENT_REVIEW_MANIFEST_FILE_MISMATCH");
            }
            string findingsPath = reviewPrefix + "INDEPENDENT_FINDINGS_LEDGER.json";
            if (!byReviewPath.ContainsKey(findingsPath)) throw new R7ProtocolException("INDEPENDENT_REVIEW_NORMATIVE_LEDGER_MISSING");
        }

        private static bool IsLowerHex(string value, int length)
        {
            if (value == null || value.Length != length) return false;
            for (int i = 0; i < value.Length; i++) if (!((value[i] >= '0' && value[i] <= '9') || (value[i] >= 'a' && value[i] <= 'f'))) return false;
            return true;
        }

        private void VerifyRequirements(SortedDictionary<string, object> artifact, Dictionary<string, SourceRecord> sources)
        {
            R7Json.ExactKeys(artifact, "artifact_type", "authority_source_manifest", "governing_requirement_count", "independently_reconstructed", "prohibited_source_commit", "prohibited_source_reference_count", "requirements", "schema_version");
            if (R7Json.Integer(artifact, "prohibited_source_reference_count", 0, 0) != 0) throw new R7ProtocolException("PROHIBITED_SOURCE_REFERENCE");
            if (R7Json.Integer(artifact, "governing_requirement_count", 79, 79) != 79 || !R7Json.Boolean(artifact, "independently_reconstructed")) throw new R7ProtocolException("REQUIREMENT_COUNT");
            object[] rows = R7Json.Array(artifact, "requirements");
            if (rows.Length != 79) throw new R7ProtocolException("REQUIREMENT_COUNT");
            foreach (object rawRow in rows)
            {
                SortedDictionary<string, object> row = RequireObject(rawRow, "requirement");
                R7Json.ExactKeys(row,
                    "acceptance_significance", "byte_range", "clause_raw_sha256", "control_category", "durability_obligation",
                    "forbidden_side_effects", "governing_blob", "governing_commit", "governing_path", "line_range", "primary_authority",
                    "quoted_clause_text", "reconciliation_obligation", "requirement_id", "requirement_interpretation", "required_evidence",
                    "required_positive_behavior", "required_rejection_behavior", "required_side_effects", "restart_retry_replay_obligation", "section_heading");
                string id = R7Json.String(row, "requirement_id", 1, 128);
                if (requirements.ContainsKey(id)) throw new R7ProtocolException("DUPLICATE_REQUIREMENT_ID");
                string commit = R7Json.String(row, "governing_commit", 40, 40);
                if (String.Equals(commit, ProhibitedCommit, StringComparison.Ordinal)) throw new R7ProtocolException("PROHIBITED_SOURCE_REFERENCE");
                string blob = R7Json.String(row, "governing_blob", 40, 40);
                string path = R7Json.String(row, "governing_path", 1, 4096);
                SourceRecord source;
                if (!sources.TryGetValue(SourceKey(commit, blob, path), out source)) throw new R7ProtocolException("GOVERNING_SOURCE_UNRESOLVED", id);
                VerifyClause(row, source, id);
                if (!String.Equals(R7Json.String(row, "acceptance_significance", 1, 64), "BLOCKING", StringComparison.Ordinal)) throw new R7ProtocolException("REQUIREMENT_SIGNIFICANCE");
                if (!R7Json.Boolean(row, "primary_authority")) throw new R7ProtocolException("REQUIREMENT_NOT_PRIMARY");
                requirements.Add(id, row);
            }
        }

        private static void VerifyClause(SortedDictionary<string, object> row, SourceRecord source, string id)
        {
            int startLine;
            int endLine;
            ParseRange(R7Json.String(row, "line_range", 3, 64), out startLine, out endLine);
            string[] lines = source.Text.Split(new string[] { "\n" }, StringSplitOptions.None);
            if (startLine < 1 || endLine < startLine || endLine > lines.Length) throw new R7ProtocolException("CLAUSE_LINE_RANGE", id);
            StringBuilder quoteBuilder = new StringBuilder();
            for (int i = startLine - 1; i < endLine; i++)
            {
                if (i > startLine - 1) quoteBuilder.Append('\n');
                string line = lines[i];
                if (line.EndsWith("\r", StringComparison.Ordinal)) line = line.Substring(0, line.Length - 1);
                quoteBuilder.Append(line);
            }
            string quote = quoteBuilder.ToString();
            if (!String.Equals(quote, R7Json.String(row, "quoted_clause_text", 1, 65536), StringComparison.Ordinal)) throw new R7ProtocolException("CLAUSE_TEXT_MISMATCH", id);
            string hash = R7Hash.Bytes(new UTF8Encoding(false, true).GetBytes(quote));
            if (!R7Hash.FixedTimeEquals(hash, R7Json.String(row, "clause_raw_sha256", 64, 64))) throw new R7ProtocolException("CLAUSE_HASH_MISMATCH", id);
            int startByte;
            int endByte;
            ParseRange(R7Json.String(row, "byte_range", 3, 64), out startByte, out endByte);
            string prefix = String.Join("\n", Subarray(lines, 0, startLine - 1));
            if (startLine > 1) prefix += "\n";
            int computedStart = new UTF8Encoding(false, true).GetByteCount(prefix);
            int computedEnd = computedStart + new UTF8Encoding(false, true).GetByteCount(quote);
            if (startByte != computedStart || endByte != computedEnd) throw new R7ProtocolException("CLAUSE_BYTE_RANGE_MISMATCH", id);
        }

        private void VerifyCases(SortedDictionary<string, object> artifact)
        {
            R7Json.ExactKeys(artifact, "artifact_type", "authored_stage", "cases", "expectation_artifact_read", "independently_determined_case_count", "prohibited_source_commit", "prohibited_source_reference_count", "requirement_registry_sha256", "schema_version");
            if (R7Json.Boolean(artifact, "expectation_artifact_read")) throw new R7ProtocolException("CASE_EXPECTATION_COUPLING");
            if (R7Json.Integer(artifact, "prohibited_source_reference_count", 0, 0) != 0) throw new R7ProtocolException("PROHIBITED_SOURCE_REFERENCE");
            object[] rows = R7Json.Array(artifact, "cases");
            long declaredCaseCount = R7Json.Integer(artifact, "independently_determined_case_count", 1, 100000);
            if (rows.Length != declaredCaseCount) throw new R7ProtocolException("CASE_COUNT");
            HashSet<string> mappedRequirements = new HashSet<string>(StringComparer.Ordinal);
            foreach (object rawRow in rows)
            {
                SortedDictionary<string, object> row = RequireObject(rawRow, "case");
                R7Json.ExactKeys(row, "actual_derivation_source", "authority_refs", "caller_role", "case_id", "driver", "evidence_requirements", "implementation_surface", "operation", "request_recipe", "title");
                string id = R7Json.String(row, "case_id", 1, 128);
                if (cases.ContainsKey(id)) throw new R7ProtocolException("DUPLICATE_CASE_ID");
                SortedDictionary<string, object> recipe = R7Json.Child(row, "request_recipe");
                R7Json.ExactKeys(recipe, "dynamic_fields", "include_desired_result", "include_expectation_fields", "mutation");
                if (R7Json.Boolean(recipe, "include_desired_result") || R7Json.Boolean(recipe, "include_expectation_fields")) throw new R7ProtocolException("CASE_EXPECTATION_COUPLING", id);
                object[] authorityRows = R7Json.Array(row, "authority_refs");
                if (authorityRows.Length == 0) throw new R7ProtocolException("CASE_WITHOUT_AUTHORITY", id);
                List<string> requirementIds = new List<string>();
                foreach (object rawAuthority in authorityRows)
                {
                    SortedDictionary<string, object> authority = RequireObject(rawAuthority, "authority reference");
                    R7Json.ExactKeys(authority, "clause_raw_sha256", "governing_blob", "governing_commit", "governing_path", "line_range", "requirement_id", "section_heading");
                    string requirementId = R7Json.String(authority, "requirement_id", 1, 128);
                    SortedDictionary<string, object> requirement;
                    if (!requirements.TryGetValue(requirementId, out requirement)) throw new R7ProtocolException("CASE_AUTHORITY_UNRESOLVED", id);
                    foreach (string field in new string[] { "clause_raw_sha256", "governing_blob", "governing_commit", "governing_path", "line_range", "section_heading" })
                    {
                        if (!String.Equals(R7Json.String(authority, field, 1, 4096), R7Json.String(requirement, field, 1, 4096), StringComparison.Ordinal)) throw new R7ProtocolException("CASE_AUTHORITY_LOCATOR_MISMATCH", id);
                    }
                    requirementIds.Add(requirementId);
                    mappedRequirements.Add(requirementId);
                }
                R7CaseDefinition value = new R7CaseDefinition
                {
                    CaseId = id,
                    Title = R7Json.String(row, "title", 1, 1024),
                    Driver = R7Json.String(row, "driver", 1, 128),
                    Operation = R7Json.String(row, "operation", 1, 128),
                    CallerRole = R7Json.String(row, "caller_role", 1, 128),
                    Mutation = R7Json.String(recipe, "mutation", 1, 256),
                    Surface = R7Json.String(row, "implementation_surface", 1, 256),
                    RequirementIds = requirementIds.ToArray(),
                    EvidenceRequirements = StringArray(R7Json.Array(row, "evidence_requirements"), "case evidence"),
                    Raw = row
                };
                cases.Add(id, value);
            }
            if (mappedRequirements.Count != requirements.Count) throw new R7ProtocolException("REQUIREMENT_COVERAGE_GAP");
        }

        private void VerifyExpectations(SortedDictionary<string, object> artifact)
        {
            R7Json.ExactKeys(artifact, "artifact_type", "authored_before_execution", "authored_stage", "case_artifact_read", "expectation_count", "expectations", "prohibited_source_commit", "prohibited_source_reference_count", "requirement_registry_read", "runtime_evidence_read", "schema_version");
            if (R7Json.Boolean(artifact, "case_artifact_read") || R7Json.Boolean(artifact, "requirement_registry_read") || R7Json.Boolean(artifact, "runtime_evidence_read")) throw new R7ProtocolException("EXPECTATION_AUTHORING_COUPLING");
            if (!R7Json.Boolean(artifact, "authored_before_execution")) throw new R7ProtocolException("EXPECTATION_NOT_PREAUTHORED");
            object[] rows = R7Json.Array(artifact, "expectations");
            long declaredExpectationCount = R7Json.Integer(artifact, "expectation_count", 1, 100000);
            if (rows.Length != declaredExpectationCount) throw new R7ProtocolException("EXPECTATION_COUNT");
            foreach (object rawRow in rows)
            {
                SortedDictionary<string, object> row = RequireObject(rawRow, "expectation");
                R7Json.ExactKeys(row, "case_id", "expectation_id", "expected_public_classification", "expected_response_class", "expected_result_code", "expected_terminal_classification", "forbidden_durable_side_effects", "required_durable_side_effects", "required_evidence", "restart_retry_obligation", "semantic_rationale");
                string caseId = R7Json.String(row, "case_id", 1, 128);
                if (!cases.ContainsKey(caseId)) throw new R7ProtocolException("EXPECTATION_WITHOUT_CASE", caseId);
                if (expectations.ContainsKey(caseId)) throw new R7ProtocolException("DUPLICATE_EXPECTATION", caseId);
                RejectRuntimeFields(row);
                expectations.Add(caseId, new R7Expectation
                {
                    ExpectationId = R7Json.String(row, "expectation_id", 1, 256),
                    CaseId = caseId,
                    Classification = R7Json.String(row, "expected_terminal_classification", 1, 256),
                    ResponseClass = R7Json.String(row, "expected_response_class", 1, 256),
                    ResultCode = R7Json.String(row, "expected_result_code", 1, 256),
                    PublicClassification = R7Json.String(row, "expected_public_classification", 1, 256),
                    RequiredEvidence = StringArray(R7Json.Array(row, "required_evidence"), "required evidence"),
                    RequiredEffects = StringArray(R7Json.Array(row, "required_durable_side_effects"), "required effects"),
                    ForbiddenEffects = StringArray(R7Json.Array(row, "forbidden_durable_side_effects"), "forbidden effects"),
                    RestartRetry = R7Json.String(row, "restart_retry_obligation", 1, 1024),
                    Raw = row
                });
            }
            if (expectations.Count != cases.Count) throw new R7ProtocolException("CASE_EXPECTATION_BIJECTION");
        }

        private void VerifyCoverage(SortedDictionary<string, object> artifact)
        {
            R7Json.ExactKeys(artifact, "artifact_type", "case_count", "case_definitions_sha256", "chain", "coverage", "expectation_count", "expectations_sha256", "governing_requirement_count", "prohibited_source_reference_count", "requirement_registry_sha256", "schema_version", "unauthorized_normative_case_count", "unmapped_governing_requirement_count");
            if (R7Json.Integer(artifact, "governing_requirement_count", 1, 100000) != requirements.Count ||
                R7Json.Integer(artifact, "case_count", 1, 100000) != cases.Count ||
                R7Json.Integer(artifact, "expectation_count", 1, 100000) != expectations.Count ||
                R7Json.Integer(artifact, "unauthorized_normative_case_count", 0, 0) != 0 ||
                R7Json.Integer(artifact, "unmapped_governing_requirement_count", 0, 0) != 0 ||
                R7Json.Integer(artifact, "prohibited_source_reference_count", 0, 0) != 0) throw new R7ProtocolException("COVERAGE_PROOF_INVALID");
            object[] rows = R7Json.Array(artifact, "coverage");
            if (rows.Length != requirements.Count) throw new R7ProtocolException("COVERAGE_ROW_COUNT");
        }

        private static void RejectRuntimeFields(object value)
        {
            SortedDictionary<string, object> dictionary = value as SortedDictionary<string, object>;
            if (dictionary != null)
            {
                foreach (KeyValuePair<string, object> item in dictionary)
                {
                    if (item.Key == "actual_status" || item.Key == "actual_code" || item.Key == "observed_value" || item.Key == "run_identity" || item.Key == "process_id" || item.Key == "session_identity") throw new R7ProtocolException("EXPECTATION_RUNTIME_FIELD", item.Key);
                    RejectRuntimeFields(item.Value);
                }
                return;
            }
            object[] array = value as object[];
            if (array != null) foreach (object item in array) RejectRuntimeFields(item);
        }

        private static SortedDictionary<string, object> RequireObject(object value, string name)
        {
            SortedDictionary<string, object> result = value as SortedDictionary<string, object>;
            if (result == null) throw new R7ProtocolException("OBJECT_REQUIRED", name);
            return result;
        }

        private static string[] StringArray(object[] values, string name)
        {
            string[] result = new string[values.Length];
            for (int i = 0; i < values.Length; i++)
            {
                result[i] = values[i] as string;
                if (result[i] == null || !result[i].IsNormalized(NormalizationForm.FormC)) throw new R7ProtocolException("STRING_ARRAY_REQUIRED", name);
            }
            return result;
        }

        private static string StrictText(byte[] bytes)
        {
            try { return new UTF8Encoding(false, true).GetString(bytes); }
            catch (DecoderFallbackException) { throw new R7ProtocolException("AUTHORITY_SOURCE_UTF8_INVALID"); }
        }

        private static void ParseRange(string value, out int start, out int end)
        {
            string[] parts = value.Split('-');
            if (parts.Length != 2 || !Int32.TryParse(parts[0], NumberStyles.None, CultureInfo.InvariantCulture, out start) || !Int32.TryParse(parts[1], NumberStyles.None, CultureInfo.InvariantCulture, out end)) throw new R7ProtocolException("RANGE_FORMAT");
        }

        private static string[] Subarray(string[] source, int start, int count)
        {
            if (count <= 0) return new string[0];
            string[] result = new string[count];
            Array.Copy(source, start, result, 0, count);
            for (int i = 0; i < result.Length; i++) if (result[i].EndsWith("\r", StringComparison.Ordinal)) result[i] = result[i].Substring(0, result[i].Length - 1);
            return result;
        }

        private static string SourceKey(string commit, string blob, string path) { return commit + "|" + blob + "|" + path; }

        private sealed class SourceRecord
        {
            internal string Commit;
            internal string Blob;
            internal string GoverningPath;
            internal byte[] Bytes;
            internal string Text;
        }
    }
}
