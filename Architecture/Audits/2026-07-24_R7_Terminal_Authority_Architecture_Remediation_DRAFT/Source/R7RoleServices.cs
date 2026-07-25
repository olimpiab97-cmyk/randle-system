using Microsoft.Win32.SafeHandles;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.IO.Pipes;
using System.Runtime.InteropServices;
using System.Security;
using System.Security.Cryptography;
using System.Security.Principal;
using System.ServiceProcess;
using System.Text;
using System.Threading;

namespace RandleAI.R7Remediation
{
    internal static class R7RoleClient
    {
        internal static SortedDictionary<string, object> Request(string operation, SortedDictionary<string, object> payload)
        {
            return R7Json.Object("interface_version", R7Fixed.InterfaceVersion, "operation", operation, "payload", payload, "protocol_version", R7Fixed.ProtocolVersion, "request_identity", Guid.NewGuid().ToString("D"));
        }

        internal static SortedDictionary<string, object> RoleRequest(string operation, SortedDictionary<string, object> payload)
        {
            return R7Json.Object("interface_version", "1.0.0", "operation", operation, "payload", payload, "protocol_version", R7Fixed.ProtocolVersion, "request_identity", Guid.NewGuid().ToString("D"));
        }

    }

#if EXECUTION_ROLE
    internal sealed class R7CaseOnlyDefinition
    {
        internal string CaseId;
        internal string Driver;
        internal string Operation;
        internal string Mutation;
        internal SortedDictionary<string, object> AuthorityRef;
        internal object[] AuthorityRefs;
    }

    internal sealed class R7CaseOnlyCatalog
    {
        private readonly Dictionary<string, R7CaseOnlyDefinition> cases = new Dictionary<string, R7CaseOnlyDefinition>(StringComparer.Ordinal);

        internal R7CaseOnlyCatalog()
        {
            using (R7VerifiedFile file = R7SafeFile.Open(R7Fixed.CasePath, R7Fixed.CasePath, Path.GetDirectoryName(R7Fixed.CasePath), R7BuildIdentity.CaseDefinitionsSha256, R7Fixed.SystemSid, null, null))
            {
                SortedDictionary<string, object> artifact = RequireObject(R7Json.Parse(file.Bytes));
                object[] caseRows = R7Json.Array(artifact, "cases");
                if (R7Json.Boolean(artifact, "expectation_artifact_read") || R7Json.Integer(artifact, "independently_determined_case_count", 1, 100000) != caseRows.Length) throw new SecurityException("CASE_ARTIFACT_SEPARATION_INVALID");
                foreach (object raw in caseRows)
                {
                    SortedDictionary<string, object> row = RequireObject(raw);
                    SortedDictionary<string, object> recipe = R7Json.Child(row, "request_recipe");
                    object[] authorityRows = R7Json.Array(row, "authority_refs");
                    if (authorityRows.Length == 0) throw new SecurityException("CASE_AUTHORITY_MISSING");
                    SortedDictionary<string, object> primaryAuthority = RequireObject(authorityRows[0]);
                    if (R7Json.Boolean(recipe, "include_expectation_fields") || R7Json.Boolean(recipe, "include_desired_result")) throw new SecurityException("CASE_REQUEST_EXPECTATION_COUPLING");
                    R7CaseOnlyDefinition value = new R7CaseOnlyDefinition
                    {
                        CaseId = R7Json.String(row, "case_id", 1, 128),
                        Driver = R7Json.String(row, "driver", 1, 128),
                        Operation = R7Json.String(row, "operation", 1, 128),
                        Mutation = R7Json.String(recipe, "mutation", 1, 256),
                        AuthorityRef = primaryAuthority,
                        AuthorityRefs = authorityRows
                    };
                    if (cases.ContainsKey(value.CaseId)) throw new SecurityException("DUPLICATE_CASE_ID");
                    cases.Add(value.CaseId, value);
                }
            }
        }

        internal R7CaseOnlyDefinition Get(string caseId)
        {
            R7CaseOnlyDefinition value;
            if (!cases.TryGetValue(caseId, out value)) throw new R7ProtocolException("CASE_IDENTITY_UNRESOLVED");
            return value;
        }

        internal string[] CaseIds
        {
            get { List<string> values = new List<string>(cases.Keys); values.Sort(StringComparer.Ordinal); return values.ToArray(); }
        }

        internal string[] RequirementIds
        {
            get
            {
                HashSet<string> unique = new HashSet<string>(StringComparer.Ordinal);
                foreach (R7CaseOnlyDefinition value in cases.Values)
                {
                    foreach (object raw in value.AuthorityRefs) unique.Add(R7Json.String(RequireObject(raw), "requirement_id", 1, 128));
                }
                List<string> result = new List<string>(unique);
                result.Sort(StringComparer.Ordinal);
                return result.ToArray();
            }
        }

        private static SortedDictionary<string, object> RequireObject(object value)
        {
            SortedDictionary<string, object> result = value as SortedDictionary<string, object>;
            if (result == null) throw new R7ProtocolException("OBJECT_REQUIRED");
            return result;
        }
    }

    internal sealed class R7ExecutionProcessor : R7PipeProcessor
    {
        private readonly R7ActiveUpgrade activeUpgrade;
        private readonly R7CaseOnlyCatalog catalog;
        private readonly string binarySha256;
        private readonly R7VerifiedFile binaryFile;
        private readonly R7DependencyClosure dependencies;

        internal R7ExecutionProcessor()
        {
            if (WindowsIdentity.GetCurrent().User.Value != R7Fixed.ExecutionSid) throw new SecurityException("EXECUTION_SERVICE_SID_MISMATCH");
            string executable = Path.GetFullPath(System.Reflection.Assembly.GetExecutingAssembly().Location);
            if (!String.Equals(executable, R7BuildIdentity.ExecutionBinaryPath, StringComparison.Ordinal)) throw new SecurityException("EXECUTION_BINARY_PATH_MISMATCH");
            activeUpgrade = R7ActiveUpgrade.ResolveAuthorization("EXECUTION");
            R7TerminalPolicy terminalPolicy = R7TerminalPolicy.Load(activeUpgrade.TerminalPolicySha256);
            VerifyRolePolicy(terminalPolicy, activeUpgrade);
            R7ComponentIdentity component = terminalPolicy.Component("EXECUTION");
            binaryFile = R7SafeFile.Open(executable, component.Path, R7Fixed.TerminalInstallRoot, component.Sha256, R7Fixed.SystemSid, null, terminalPolicy.VolumeIdentity);
            binarySha256 = binaryFile.Measurement.Sha256;
            dependencies = new R7DependencyClosure(R7Fixed.DependencyManifestPath, terminalPolicy.DependencyManifestSha256, R7Fixed.TerminalInstallRoot);
            catalog = new R7CaseOnlyCatalog();
        }

        internal override SortedDictionary<string, object> Process(R7RequestContext context, SortedDictionary<string, object> request)
        {
            dependencies.VerifyNoNewModules();
            try
            {
                string operation;
                SortedDictionary<string, object> payload;
                R7RoleProtocol.Require(request, out operation, out payload);
                if (context.Caller.UserSid != R7Fixed.OperatorSid && context.Caller.UserSid != R7Fixed.SystemSid) throw new SecurityException("CALLER_NOT_AUTHORIZED");
                if (operation == "GET_ROLE_HEALTH") { R7Json.ExactKeys(payload); return Health(); }
                activeUpgrade.RequireActivatedComponent("EXECUTION", binaryFile.Measurement.FileIdentity);
                if (operation == "BUILD_CASE_INVOCATION") return BuildCaseInvocation(payload);
                if (operation == "BUILD_EXTERNAL_INTERACTION") return BuildExternalInteraction(payload);
                if (operation == "PRODUCE_EVENT_EVIDENCE") return ProduceEventEvidence(payload);
                if (operation == "RUN_PRINCIPAL_PROBE") return RunPrincipalProbe(payload);
                if (operation == "RUN_RECOVERY_PROBE") return RunRecoveryProbe(payload);
                if (operation == "RUN_EVENT_INJECTION_PROBE") return RunEventInjectionProbe(payload);
                if (operation == "RUN_SEMANTIC_PROBE") return RunSemanticProbe(payload);
                if (operation == "RUN_SIGNER_ONLY_PROBE") return RunSignerOnlyProbe(payload);
                throw new R7ProtocolException("OPERATION_NOT_ALLOWED");
            }
            finally { dependencies.VerifyNoNewModules(); }
        }

        public override void Dispose() { dependencies.Dispose(); binaryFile.Dispose(); }

        private static void VerifyRolePolicy(R7TerminalPolicy terminalPolicy, R7ActiveUpgrade activeUpgrade)
        {
            if (!String.Equals(terminalPolicy.SourceCommit, R7BuildIdentity.SourceCommit, StringComparison.Ordinal) ||
                !String.Equals(terminalPolicy.SourceTree, R7BuildIdentity.SourceTree, StringComparison.Ordinal) ||
                !String.Equals(terminalPolicy.UpgradePublicCertificateSha256, R7BuildIdentity.UpgradePublicCertificateSha256, StringComparison.Ordinal) ||
                !R7Hash.FixedTimeEquals(terminalPolicy.DependencyManifestSha256, R7BuildIdentity.DependencyManifestSha256) ||
                !R7Hash.FixedTimeEquals(terminalPolicy.BuildReceiptSha256, R7Json.String(activeUpgrade.AuthorizationPayload, "build_receipt_sha256", 64, 64))) throw new SecurityException("ROLE_POLICY_SOURCE_MISMATCH");
        }

        private SortedDictionary<string, object> Health()
        {
            SortedDictionary<string, object> result = R7PipeWindowsService.Success("EXECUTION_ROLE_HEALTHY");
            result.Add("binary_sha256", binarySha256);
            result.Add("binary_file_identity", binaryFile.Measurement.FileIdentity);
            result.Add("expectation_artifact_read", false);
            result.Add("service_sid", R7Fixed.ExecutionSid);
            result.Add("terminal_signer_sid_present", false);
            return result;
        }

        private SortedDictionary<string, object> BuildCaseInvocation(SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "case_id", "fixture");
            string caseId = R7Json.String(payload, "case_id", 1, 128);
            R7CaseOnlyDefinition definition = catalog.Get(caseId);
            SortedDictionary<string, object> fixture = R7Json.Child(payload, "fixture");
            SortedDictionary<string, object> plan = BuildInvocationPlan(definition, fixture);
            plan.Add("case_id", caseId);
            plan.Add("expectation_artifact_read", false);
            plan.Add("request_builder_sid", R7Fixed.ExecutionSid);
            plan.Add("result_code", "CASE_OUTER_INVOCATION_PLAN_BUILT");
            plan.Add("status", "COMPLETE");
            return plan;
        }

        private SortedDictionary<string, object> BuildInvocationPlan(R7CaseOnlyDefinition definition, SortedDictionary<string, object> fixture)
        {
            if (definition.Driver == "RAW_FRAME")
            {
                bool expectResponse;
                byte[] raw = BuildRawParserFrame(definition, out expectResponse);
                return DirectPlan("DIRECT_RAW", R7Fixed.TerminalPipe, raw, expectResponse);
            }
            if (definition.Driver == "RECOVERY_HARNESS")
            {
                R7Json.ExactKeys(fixture, "isolated_root");
                return RolePlan("RECOVERY_PROBE", R7Fixed.ExecutionPipe, "RUN_RECOVERY_PROBE", R7Json.Object(
                    "case_id", definition.CaseId,
                    "fault_point", RecoveryFault(definition),
                    "isolated_root", R7Json.String(fixture, "isolated_root", 3, 4096),
                    "mutation", definition.Mutation));
            }
            if (definition.Driver == "CONCURRENCY_PROBE") return BuildConcurrencyPlan(definition, fixture);
            if (definition.Driver == "UPGRADE_PIPE" || definition.Driver == "UPGRADE_VERIFIER") return BuildUpgradePlan(definition, fixture);
            if (definition.Driver == "PUBLIC_VERIFIER") return BuildPublicVerifierPlan(definition, fixture);
            if (definition.CaseId == "EXP-001")
            {
                return RolePlan("ROLE_PROBE", R7Fixed.ExecutionPipe, "RUN_EVENT_INJECTION_PROBE", R7Json.Object(
                    "case_id", definition.CaseId,
                    "mutation", definition.Mutation));
            }
            if (definition.CaseId == "EXP-002" || definition.CaseId == "EXP-004")
            {
                string operation = definition.CaseId == "EXP-002" ? "PROBE_EXPECTATION_INJECTION" : "PROBE_EXPECTATION_ACCESS";
                string target = fixture.ContainsKey("target_identity") ? R7Json.String(fixture, "target_identity", 1, 256) : definition.Operation;
                return RolePlan("ROLE_PROBE", R7Fixed.ObservationPipe, operation, R7Json.Object("case_id", definition.CaseId, "mutation", definition.Mutation, "target_identity", target));
            }
            if (definition.CaseId == "PRI-002" || definition.CaseId == "SEM-007")
            {
                string operation = definition.CaseId == "PRI-002" ? "PROBE_TERMINAL_KEY_ACCESS" : "PROBE_SUMMARY_ONLY";
                string target = fixture.ContainsKey("target_identity") ? R7Json.String(fixture, "target_identity", 1, 256) : definition.Operation;
                return RolePlan("ROLE_PROBE", R7Fixed.ComparatorPipe, operation, R7Json.Object("case_id", definition.CaseId, "mutation", definition.Mutation, "target_identity", target));
            }
            if (definition.CaseId == "PRI-006") return RolePlan("ROLE_PROBE", R7Fixed.ExecutionPipe, "RUN_SIGNER_ONLY_PROBE", R7Json.Object("case_id", definition.CaseId, "mutation", definition.Mutation));
            if (definition.Driver == "SEMANTIC_PROBE" || definition.CaseId.StartsWith("SEM-", StringComparison.Ordinal)) return RolePlan("ROLE_PROBE", R7Fixed.ExecutionPipe, "RUN_SEMANTIC_PROBE", R7Json.Object("case_id", definition.CaseId, "mutation", definition.Mutation));
            if (definition.Driver == "ACL_PROBE" || definition.Driver == "TOKEN_PROBE" || definition.Driver == "SOURCE_PROBE")
            {
                return RolePlan("PRINCIPAL_PROBE", R7Fixed.ExecutionPipe, "RUN_PRINCIPAL_PROBE", R7Json.Object(
                    "case_id", definition.CaseId,
                    "mutation", definition.Mutation,
                    "target_identity", R7Json.String(fixture, "target_identity", 1, 256)));
            }

            string terminalOperation = definition.Operation;
            SortedDictionary<string, object> terminalPayload;
            if (definition.Driver == "AUTHORITY_VERIFIER")
            {
                if (definition.Operation == "VERIFY_COVERAGE")
                {
                    List<object> requirementIds = new List<object>(catalog.RequirementIds);
                    List<object> caseIds = new List<object>(catalog.CaseIds);
                    if (definition.Mutation == "OMIT_REQUIREMENT") requirementIds.RemoveAt(requirementIds.Count - 1);
                    else if (definition.Mutation == "EXTRA_UNAUTHORIZED_CASE") caseIds.Add("UNAUTHORIZED-NORMATIVE-CASE");
                    terminalPayload = R7Json.Object(
                        "case_id", definition.CaseId,
                        "claimed_case_ids", caseIds.ToArray(),
                        "claimed_requirement_ids", requirementIds.ToArray(),
                        "mutation", definition.Mutation,
                        "registry_identity", R7BuildIdentity.CoverageProofSha256);
                }
                else
                {
                    SortedDictionary<string, object> locator = definition.AuthorityRef;
                    string requirementId = definition.Mutation == "NONEXISTENT_CLAUSE" ? "R7REQ-NONEXISTENT" : R7Json.String(locator, "requirement_id", 1, 128);
                    terminalPayload = R7Json.Object(
                        "case_id", definition.CaseId,
                        "claim", R7Json.Object(
                            "clause_hash", definition.Mutation == "CLAUSE_TEXT_MUTATION" || definition.Mutation == "NONEXISTENT_CLAUSE" ? R7Fixed.ZeroHash : R7Json.String(locator, "clause_raw_sha256", 64, 64),
                            "governing_blob", R7Json.String(locator, "governing_blob", 40, 40),
                            "governing_commit", definition.Mutation == "PROHIBITED_F0_CITATION" ? "f0cfbce97e913a133530dd66a70326b1e03a0fb6" : R7Json.String(locator, "governing_commit", 40, 40),
                            "governing_path", R7Json.String(locator, "governing_path", 1, 4096),
                            "line_range", R7Json.String(locator, "line_range", 1, 64),
                            "requirement_id", requirementId,
                            "section_heading", definition.Mutation == "WRONG_SECTION" || definition.Mutation == "NONEXISTENT_CLAUSE" ? "INTENTIONALLY WRONG SECTION" : R7Json.String(locator, "section_heading", 1, 4096)),
                        "mutation", definition.Mutation);
                }
            }
            else if (definition.Driver == "PATH_PROBE")
            {
                terminalOperation = "RUN_PATH_PROBE";
                terminalPayload = R7Json.Object("attack_path", R7Json.String(fixture, "attack_path", 3, 4096), "case_id", definition.CaseId, "mutation", definition.Mutation, "reference_path", R7Json.String(fixture, "reference_path", 3, 4096));
            }
            else if (definition.Driver == "DEPENDENCY_PROBE")
            {
                string role = fixture.ContainsKey("role") ? R7Json.String(fixture, "role", 1, 128) : "TERMINAL_SIGNER";
                string hash = fixture.ContainsKey("claimed_component_sha256") ? R7Json.String(fixture, "claimed_component_sha256", 64, 64) : R7Fixed.ZeroHash;
                terminalOperation = "RUN_DEPENDENCY_PROBE";
                terminalPayload = R7Json.Object(
                    "attack_path", fixture.ContainsKey("attack_path") ? R7Json.String(fixture, "attack_path", 0, 4096) : String.Empty,
                    "case_id", definition.CaseId,
                    "claimed_component_sha256", hash,
                    "mutation", definition.Mutation,
                    "reference_path", fixture.ContainsKey("reference_path") ? R7Json.String(fixture, "reference_path", 0, 4096) : String.Empty,
                    "role", role);
            }
            else if (definition.Driver == "TRACE_VERIFIER") terminalPayload = R7Json.Object("case_id", definition.CaseId, "mutation", definition.Mutation, "trace", BuildTraceAttack(definition));
            else if (definition.Driver == "CLAIM_VERIFIER") terminalPayload = R7Json.Object(
                "case_id", definition.CaseId,
                "claim", definition.Mutation == "UNKNOWN_APPROVAL_VERB" ? "This proposal is greenlit for R7 authority." : "This proposal is canonically incorporated into governing authority.",
                "mutation", definition.Mutation);
            else if (definition.Mutation == "WRONG_VERSION_RULE" || definition.Mutation == "REUSE_SEQUENCE_332" || definition.Mutation == "REUSE_SEQUENCE_678" || definition.Mutation == "CONFLICTING_SUPERSESSION")
            {
                terminalOperation = "VERIFY_HISTORY";
                terminalPayload = R7Json.Object(
                    "case_id", definition.CaseId,
                    "claimed_classification", definition.Mutation == "REUSE_SEQUENCE_332" || definition.Mutation == "REUSE_SEQUENCE_678" ? "REQUEST_NEW_SEQUENCE" : definition.Mutation == "CONFLICTING_SUPERSESSION" ? "VALID_AUTHORITATIVE_RECEIPT" : "VERSION_RESOLVED_HISTORICAL_EVIDENCE",
                    "claimed_schema_version", definition.Mutation == "WRONG_VERSION_RULE" ? "4.0.0" : String.Empty,
                    "mutation", definition.Mutation,
                    "sequence", definition.Mutation == "REUSE_SEQUENCE_332" ? 332L : definition.Mutation == "REUSE_SEQUENCE_678" ? 678L : definition.Mutation == "CONFLICTING_SUPERSESSION" ? 332L : 1L);
            }
            else if (definition.Mutation == "UNCOMMITTED_RECEIPT")
            {
                terminalOperation = "SUBMIT_RECONCILIATION";
                terminalPayload = R7Json.Object("candidate_receipt_identity", new string('d', 64), "fresh_receipt_identity", new string('e', 64), "reconciliation_provenance_identity", new string('f', 64));
            }
            else if (definition.Driver == "PUBLIC_PIPE" || definition.Driver == "SERVICE_CONTROL" || definition.Driver == "PUBLIC_VERIFIER")
            {
                if (definition.CaseId == "POS-018")
                {
                    terminalOperation = "SUBMIT_SERVICE_STOP_EVIDENCE";
                    terminalPayload = R7Json.Object(
                        "client_error_code", R7Json.String(fixture, "client_error_code", 1, 32),
                        "observation_time", R7Json.String(fixture, "observation_time", 1, 128),
                        "request_frame", R7Json.String(fixture, "request_frame", 1, R7Fixed.MaximumEncodedFrameChars),
                        "request_frame_sha256", R7Json.String(fixture, "request_frame_sha256", 64, 64),
                        "service_name", R7Fixed.TerminalService);
                }
                else terminalPayload = PositivePayload(definition, fixture);
            }
            else terminalPayload = fixture;
            return DirectPlan("DIRECT_OUTER_INTERFACE", R7Fixed.TerminalPipe, R7Framing.Encode(R7RoleClient.Request(terminalOperation, terminalPayload)), true);
        }

        private SortedDictionary<string, object> BuildExternalInteraction(SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "case_id", "external_request_frame", "external_response_frame", "upgrade_request_identity");
            string caseId = R7Json.String(payload, "case_id", 1, 128);
            R7CaseOnlyDefinition definition = catalog.Get(caseId);
            if (definition.Driver != "UPGRADE_PIPE" && definition.Driver != "UPGRADE_VERIFIER") throw new R7ProtocolException("EXTERNAL_INTERACTION_CASE_INVALID");
            SortedDictionary<string, object> request = R7RoleClient.Request("SUBMIT_EXTERNAL_INTERACTION", R7Json.Object(
                "case_id", caseId,
                "external_interface", "UPGRADE_PIPE",
                "external_request_frame", R7Json.String(payload, "external_request_frame", 1, R7Fixed.MaximumEncodedFrameChars),
                "external_response_frame", R7Json.String(payload, "external_response_frame", 1, R7Fixed.MaximumEncodedFrameChars),
                "upgrade_request_identity", R7Json.String(payload, "upgrade_request_identity", 36, 36)));
            SortedDictionary<string, object> result = DirectPlan("DIRECT_OUTER_INTERFACE", R7Fixed.TerminalPipe, R7Framing.Encode(request), true);
            result.Add("case_id", caseId);
            result.Add("expectation_artifact_read", false);
            result.Add("request_builder_sid", R7Fixed.ExecutionSid);
            result.Add("result_code", "EXTERNAL_INTERACTION_PLAN_BUILT");
            result.Add("status", "COMPLETE");
            return result;
        }

        private SortedDictionary<string, object> ProduceEventEvidence(SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "base_interaction_identity", "case_id", "request_frame", "response_frame");
            string caseId = R7Json.String(payload, "case_id", 1, 128);
            R7CaseOnlyDefinition definition = catalog.Get(caseId);
            string baseIdentity = R7Json.String(payload, "base_interaction_identity", 64, 64);
            byte[] requestFrame = DecodeFrameField(payload, "request_frame");
            byte[] responseFrame = DecodeFrameField(payload, "response_frame");
            string operation = definition.Operation;
            try { operation = R7Json.String(R7Framing.Decode(requestFrame), "operation", 1, 128); }
            catch (R7ProtocolException) { if (definition.Driver != "RAW_FRAME") throw; }
            SortedDictionary<string, object> eventValue = R7Json.Object(
                "operation", operation,
                "request_frame_sha256", R7Hash.Bytes(requestFrame),
                "response_frame_sha256", R7Hash.Bytes(responseFrame));
            SortedDictionary<string, object> evidenceValue = R7Json.Object(
                "base_interaction_identity", baseIdentity,
                "case_id", caseId,
                "event", eventValue,
                "raw_request_frame", Convert.ToBase64String(requestFrame),
                "raw_response_frame", Convert.ToBase64String(responseFrame));
            return SubmitExecutionEvidence("EVENT", evidenceValue, "EVENT_EVIDENCE_SUBMITTED");
        }

        private SortedDictionary<string, object> RunPrincipalProbe(SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "case_id", "mutation", "target_identity");
            string caseId = R7Json.String(payload, "case_id", 1, 128);
            R7CaseOnlyDefinition definition = catalog.Get(caseId);
            string mutation = R7Json.String(payload, "mutation", 1, 256);
            if (definition.Mutation != mutation || (definition.Driver != "ACL_PROBE" && definition.Driver != "TOKEN_PROBE" && definition.Driver != "SOURCE_PROBE")) throw new R7ProtocolException("PRINCIPAL_CASE_AUTHORITY_MISMATCH");
            System.Diagnostics.Process descendant = null;
            try
            {
                SortedDictionary<string, object> evidenceValue = R7Json.Object(
                    "case_id", caseId,
                    "mutation", mutation,
                    "probe_result", ProbeTarget(mutation, payload),
                    "target_identity", R7Json.String(payload, "target_identity", 1, 256));
                if (mutation == "DESCENDANT_CAPABILITY")
                {
                    ProcessStartInfo start = new ProcessStartInfo();
                    start.FileName = R7BuildIdentity.ExecutionBinaryPath;
                    start.Arguments = "--r7-restricted-descendant-probe";
                    start.CreateNoWindow = true;
                    start.UseShellExecute = false;
                    descendant = System.Diagnostics.Process.Start(start);
                    if (descendant == null) throw new SecurityException("RESTRICTED_DESCENDANT_NOT_CREATED");
                    Thread.Sleep(100);
                    if (descendant.HasExited) throw new SecurityException("RESTRICTED_DESCENDANT_EXITED_EARLY");
                    evidenceValue.Add("spawned_process_id", (long)descendant.Id);
                }
                return SubmitExecutionEvidence("PRINCIPAL_PROBE", evidenceValue, "PRINCIPAL_PROBE_SUBMITTED");
            }
            finally
            {
                if (descendant != null)
                {
                    try { if (!descendant.HasExited) descendant.Kill(); }
                    catch { }
                    try { descendant.WaitForExit(5000); }
                    catch { }
                    descendant.Dispose();
                }
            }
        }

        private SortedDictionary<string, object> RunRecoveryProbe(SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "case_id", "fault_point", "isolated_root", "mutation");
            string caseId = R7Json.String(payload, "case_id", 1, 128);
            R7CaseOnlyDefinition definition = catalog.Get(caseId);
            string mutation = R7Json.String(payload, "mutation", 1, 256);
            string faultPoint = R7Json.String(payload, "fault_point", 1, 256);
            if (definition.Driver != "RECOVERY_HARNESS" || definition.Mutation != mutation || RecoveryFault(definition) != faultPoint) throw new R7ProtocolException("RECOVERY_CASE_AUTHORITY_MISMATCH");
            string root = Path.GetFullPath(R7Json.String(payload, "isolated_root", 3, 4096));
            SortedDictionary<string, object> rawResult = R7RecoveryProbeEngine.Execute(root, faultPoint);
            string resultIdentity = R7Hash.Bytes(R7Json.Encode(rawResult));
            string resultPath = Path.Combine(root, "ProbeEvidence", resultIdentity + ".json");
            using (R7VerifiedFile resultFile = R7SafeFile.Open(resultPath, resultPath, Path.Combine(root, "ProbeEvidence"), resultIdentity, null, null, null)) { }
            return SubmitExecutionEvidence("RECOVERY", R7Json.Object(
                "case_id", caseId,
                "fault_point", faultPoint,
                "isolated_root", root,
                "mutation", mutation,
                "result_identity", resultIdentity), "RECOVERY_EVIDENCE_SUBMITTED");
        }

        private SortedDictionary<string, object> RunEventInjectionProbe(SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "case_id", "mutation");
            string caseId = R7Json.String(payload, "case_id", 1, 128);
            R7CaseOnlyDefinition definition = catalog.Get(caseId);
            if (caseId != "EXP-001" || definition.Mutation != R7Json.String(payload, "mutation", 1, 256)) throw new R7ProtocolException("EVENT_INJECTION_CASE_INVALID");
            SortedDictionary<string, object> hostile = R7Json.Object(
                "base_interaction_identity", R7Fixed.ZeroHash,
                "event", R7Json.Object("operation", "ATTACK", "request_frame_sha256", R7Fixed.ZeroHash, "response_frame_sha256", R7Fixed.ZeroHash),
                "expected_status", "INJECTED");
            return SubmitExecutionEvidence("EVENT", hostile, "HOSTILE_EVENT_PROBE_SUBMITTED");
        }

        private SortedDictionary<string, object> RunSemanticProbe(SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "case_id", "mutation");
            string caseId = R7Json.String(payload, "case_id", 1, 128);
            R7CaseOnlyDefinition definition = catalog.Get(caseId);
            if ((definition.Driver != "SEMANTIC_PROBE" && !definition.CaseId.StartsWith("SEM-", StringComparison.Ordinal)) || definition.Mutation != R7Json.String(payload, "mutation", 1, 256)) throw new R7ProtocolException("SEMANTIC_CASE_AUTHORITY_MISMATCH");
            return SubmitExecutionEvidence("HOSTILE_GRAPH", R7Json.Object("case_id", caseId, "graph", BuildSemanticAttack(definition), "mutation", definition.Mutation), "HOSTILE_GRAPH_SUBMITTED");
        }

        private SortedDictionary<string, object> RunSignerOnlyProbe(SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "case_id", "mutation");
            string caseId = R7Json.String(payload, "case_id", 1, 128);
            R7CaseOnlyDefinition definition = catalog.Get(caseId);
            if (caseId != "PRI-006" || definition.Mutation != R7Json.String(payload, "mutation", 1, 256)) throw new R7ProtocolException("SIGNER_ONLY_CASE_INVALID");
            SortedDictionary<string, object> request = R7RoleClient.Request("SIGNER_ONLY_OPERATION", R7Json.Object());
            byte[] sent;
            byte[] received;
            SortedDictionary<string, object> signerResponse = R7Framing.Call(R7Fixed.TerminalPipe, request, 30000, out sent, out received);
            SortedDictionary<string, object> result = R7PipeWindowsService.Success("UNAUTHORIZED_SIGNER_OPERATION_PROBED");
            result.Add("signer_response", signerResponse);
            result.Add("submission_request_frame", Convert.ToBase64String(sent));
            result.Add("submission_request_frame_sha256", R7Hash.Bytes(sent));
            return result;
        }

        private static SortedDictionary<string, object> BuildSemanticAttack(R7CaseOnlyDefinition definition)
        {
            return R7Json.Object(
                "claimed_invocation_count", definition.Mutation == "WORKER_PASS_ZERO_INVOCATION" || definition.Mutation == "INNER_PASS_OUTER_NOT_INVOKED" || definition.Mutation == "SUPERVISOR_REPLAY_ZERO_EVENTS" ? 0L : 1L,
                "claimed_process_id", definition.Mutation == "FABRICATED_PROCESS_IDENTITY" ? 1L : 0L,
                "claimed_receipt_identity", definition.Mutation == "FABRICATED_RECEIPT_MEMBERSHIP" ? new string('f', 64) : R7Fixed.ZeroHash,
                "claimed_request_frame_sha256", definition.Mutation == "FABRICATED_REQUEST_RESPONSE" ? new string('f', 64) : R7Fixed.ZeroHash,
                "claimed_response_frame_sha256", definition.Mutation == "FABRICATED_REQUEST_RESPONSE" ? new string('e', 64) : R7Fixed.ZeroHash,
                "claimed_side_effect_identity", definition.Mutation == "FABRICATED_SIDE_EFFECTS" ? new string('d', 64) : R7Fixed.ZeroHash,
                "raw_evidence_present", false,
                "summary_only", definition.Mutation == "SUMMARY_ONLY_COMPARISON");
        }

        private static SortedDictionary<string, object> SubmitExecutionEvidence(string kind, SortedDictionary<string, object> value, string code)
        {
            SortedDictionary<string, object> request = R7RoleClient.Request("SUBMIT_EXECUTION_EVIDENCE", R7Json.Object("evidence", value, "evidence_kind", kind));
            byte[] sent;
            byte[] received;
            SortedDictionary<string, object> response = R7Framing.Call(R7Fixed.TerminalPipe, request, 30000, out sent, out received);
            SortedDictionary<string, object> result = R7PipeWindowsService.Success(code);
            result.Add("signer_response", response);
            result.Add("signer_response_frame", Convert.ToBase64String(received));
            result.Add("submission_request_frame", Convert.ToBase64String(sent));
            result.Add("submission_request_frame_sha256", R7Hash.Bytes(sent));
            return result;
        }

        private static SortedDictionary<string, object> DirectPlan(string kind, string pipe, byte[] frame, bool expectResponse)
        {
            return R7Json.Object(
                "expect_response", expectResponse,
                "plan_kind", kind,
                "request_frame", Convert.ToBase64String(frame),
                "request_frame_sha256", R7Hash.Bytes(frame),
                "target_pipe", pipe);
        }

        private static SortedDictionary<string, object> RolePlan(string kind, string pipe, string operation, SortedDictionary<string, object> payload)
        {
            return DirectPlan(kind, pipe, R7Framing.Encode(R7RoleClient.RoleRequest(operation, payload)), true);
        }

        private static SortedDictionary<string, object> BuildPublicVerifierPlan(R7CaseOnlyDefinition definition, SortedDictionary<string, object> fixture)
        {
            SortedDictionary<string, object> targetPayload;
            if (definition.Operation == "VERIFY_ALL" || definition.Operation == "GET_VERSION_HISTORY")
            {
                R7Json.ExactKeys(fixture);
                targetPayload = R7Json.Object();
            }
            else if (definition.Operation == "CLASSIFY_LEDGER_SEQUENCE")
            {
                R7Json.ExactKeys(fixture, "sequence");
                targetPayload = R7Json.Object("sequence", R7Json.Integer(fixture, "sequence", 1, Int64.MaxValue));
            }
            else if (definition.Operation == "VERIFY_TERMINAL_RECEIPT" || definition.Operation == "VERIFY_RECONCILIATION" || definition.Operation == "CLASSIFY_RECEIPT")
            {
                R7Json.ExactKeys(fixture, "receipt_identity");
                string receiptIdentity = R7Json.String(fixture, "receipt_identity", 64, 64);
                targetPayload = definition.CaseId == "HIS-001"
                    ? R7Json.Object("claimed_schema_version", "4.0.0", "receipt_identity", receiptIdentity)
                    : R7Json.Object("receipt_identity", receiptIdentity);
            }
            else throw new R7ProtocolException("PUBLIC_VERIFIER_OPERATION_NOT_ALLOWED");
            return R7Json.Object(
                "expect_response", true,
                "plan_kind", "PUBLIC_VERIFIER_PROCESS",
                "public_verifier_operation", definition.Operation,
                "public_verifier_payload", targetPayload,
                "target_surface", "INSTALLED_PUBLIC_VERIFIER_EXECUTABLE");
        }

        private SortedDictionary<string, object> BuildUpgradePlan(R7CaseOnlyDefinition definition, SortedDictionary<string, object> fixture)
        {
            if (definition.Mutation == "NONE")
            {
                SortedDictionary<string, object> request = R7Json.Object("interface_version", "1.0.0", "operation", "GET_UPGRADE_STATUS", "payload", R7Json.Object(), "protocol_version", R7Fixed.ProtocolVersion, "request_identity", Guid.NewGuid().ToString("D"));
                return DirectPlan("UPGRADE_NEEDS_EXTERNAL_WRAPPER", R7Fixed.UpgradePipe, R7Framing.Encode(request), true);
            }
            if (definition.Mutation == "SELF_AUTHORIZATION")
            {
                return DirectPlan("SELF_UPGRADE_NEEDS_EXTERNAL_WRAPPER", R7Fixed.TerminalPipe, R7Framing.Encode(R7RoleClient.Request("RUN_SELF_UPGRADE_PROBE", R7Json.Object("case_id", definition.CaseId))), true);
            }
            R7Json.ExactKeys(fixture, "external_request_frame", "external_response_frame", "upgrade_request_identity");
            return DirectPlan("DIRECT_OUTER_INTERFACE", R7Fixed.TerminalPipe, R7Framing.Encode(R7RoleClient.Request("SUBMIT_EXTERNAL_INTERACTION", R7Json.Object(
                "case_id", definition.CaseId,
                "external_interface", "UPGRADE_PIPE",
                "external_request_frame", R7Json.String(fixture, "external_request_frame", 1, R7Fixed.MaximumEncodedFrameChars),
                "external_response_frame", R7Json.String(fixture, "external_response_frame", 1, R7Fixed.MaximumEncodedFrameChars),
                "upgrade_request_identity", R7Json.String(fixture, "upgrade_request_identity", 36, 36)))), true);
        }

        private SortedDictionary<string, object> BuildConcurrencyPlan(R7CaseOnlyDefinition definition, SortedDictionary<string, object> fixture)
        {
            R7Json.ExactKeys(fixture, "checkout_identity", "configuration", "proposal_identity");
            string shared = Guid.NewGuid().ToString("D");
            string checkout = R7Json.String(fixture, "checkout_identity", 64, 64);
            string proposal = R7Json.String(fixture, "proposal_identity", 64, 64);
            SortedDictionary<string, object> configuration = R7Json.Child(fixture, "configuration");
            SortedDictionary<string, object> first = R7RoleClient.Request("SUBMIT_TERMINAL_PROPOSAL", R7Json.Object("checkout_identity", checkout, "configuration", configuration, "proposal_identity", proposal));
            SortedDictionary<string, object> second = R7RoleClient.Request("SUBMIT_TERMINAL_PROPOSAL", R7Json.Object("checkout_identity", checkout, "configuration", configuration, "proposal_identity", proposal));
            first["request_identity"] = shared;
            second["request_identity"] = shared;
            if (definition.Mutation == "CONCURRENT_CONFLICTING_BYTES") R7Json.Child(second, "payload")["proposal_identity"] = R7Hash.Bytes(new UTF8Encoding(false, true).GetBytes("CONFLICT|" + proposal));
            else if (definition.Mutation != "CONCURRENT_IDENTICAL_RETRY") throw new R7ProtocolException("CONCURRENCY_MUTATION_INVALID");
            byte[] firstFrame = R7Framing.Encode(first);
            byte[] secondFrame = R7Framing.Encode(second);
            byte[] verificationFrame = R7Framing.Encode(R7RoleClient.Request("VERIFY_CONCURRENT_INTERACTIONS", R7Json.Object(
                "case_id", definition.CaseId,
                "first_request_frame_sha256", R7Hash.Bytes(firstFrame),
                "mutation", definition.Mutation,
                "request_identity", shared,
                "second_request_frame_sha256", R7Hash.Bytes(secondFrame))));
            return R7Json.Object(
                "expect_response", true,
                "first_request_frame", Convert.ToBase64String(firstFrame),
                "first_request_frame_sha256", R7Hash.Bytes(firstFrame),
                "plan_kind", "CONCURRENT_OUTER_INTERFACE",
                "request_frame", Convert.ToBase64String(verificationFrame),
                "request_frame_sha256", R7Hash.Bytes(verificationFrame),
                "second_request_frame", Convert.ToBase64String(secondFrame),
                "second_request_frame_sha256", R7Hash.Bytes(secondFrame),
                "target_pipe", R7Fixed.TerminalPipe);
        }

        private static byte[] DecodeFrameField(SortedDictionary<string, object> value, string key)
        {
            try { return Convert.FromBase64String(R7Json.String(value, key, 1, R7Fixed.MaximumEncodedCaptureChars)); }
            catch (FormatException) { throw new R7ProtocolException("FRAME_ENCODING_INVALID", key); }
        }

        private static SortedDictionary<string, object> BuildTraceAttack(R7CaseOnlyDefinition definition)
        {
            string requirement = R7Json.String(definition.AuthorityRef, "requirement_id", 1, 128);
            string evidence = new string('a', 64);
            string provenance = new string('b', 64);
            List<object> nodes = new List<object>();
            nodes.Add(R7Json.Object("authority_requirement_id", requirement, "evidence_identity", evidence, "id", "SOURCE", "kind", "SOURCE", "provenance_identity", provenance));
            if (definition.Mutation != "SOURCE_WITHOUT_EXECUTION") nodes.Add(R7Json.Object("authority_requirement_id", requirement, "evidence_identity", evidence, "id", "EXECUTION", "kind", "EXECUTION", "provenance_identity", provenance));
            nodes.Add(R7Json.Object("authority_requirement_id", requirement, "evidence_identity", definition.Mutation == "EVENT_WITHOUT_RAW" ? R7Fixed.ZeroHash : evidence, "id", "EVENT", "kind", "EVENT", "provenance_identity", provenance));
            nodes.Add(R7Json.Object("authority_requirement_id", requirement, "evidence_identity", evidence, "id", "HOST", "kind", "HOST_ARTIFACT", "provenance_identity", definition.Mutation == "HOST_ARTIFACT_ORPHAN" ? R7Fixed.ZeroHash : provenance));
            nodes.Add(R7Json.Object("authority_requirement_id", definition.Mutation == "DEPENDENCY_ORPHAN" ? "R7REQ-NONEXISTENT" : requirement, "evidence_identity", evidence, "id", "DEPENDENCY", "kind", "DEPENDENCY", "provenance_identity", provenance));
            List<object> edges = new List<object>();
            if (definition.Mutation == "SOURCE_WITHOUT_EXECUTION")
            {
                edges.Add(R7Json.Object("from", "SOURCE", "to", "EVENT"));
                edges.Add(R7Json.Object("from", "SOURCE", "to", "HOST"));
            }
            else
            {
                edges.Add(R7Json.Object("from", "SOURCE", "to", "EXECUTION"));
                edges.Add(R7Json.Object("from", "EXECUTION", "to", "EVENT"));
                edges.Add(R7Json.Object("from", "EXECUTION", "to", "HOST"));
            }
            edges.Add(R7Json.Object("from", "SOURCE", "to", "DEPENDENCY"));
            if (definition.Mutation == "CIRCULAR_TRACE") edges.Add(R7Json.Object("from", "EVENT", "to", "SOURCE"));
            return R7Json.Object("edges", edges.ToArray(), "nodes", nodes.ToArray());
        }

        private static byte[] BuildRawParserFrame(R7CaseOnlyDefinition definition, out bool expectResponse)
        {
            expectResponse = true;
            string nonce = Guid.NewGuid().ToString("D");
            string prefix = "{\"interface_version\":\"" + R7Fixed.InterfaceVersion + "\",\"operation\":\"GET_HEALTH\",\"payload\":{},\"protocol_version\":\"" + R7Fixed.ProtocolVersion + "\",\"request_identity\":\"" + nonce + "\"}";
            if (definition.Mutation == "DUPLICATE_OPERATION") prefix = "{\"interface_version\":\"" + R7Fixed.InterfaceVersion + "\",\"operation\":\"UNKNOWN\",\"operation\":\"GET_HEALTH\",\"payload\":{},\"protocol_version\":\"" + R7Fixed.ProtocolVersion + "\",\"request_identity\":\"" + nonce + "\"}";
            else if (definition.Mutation == "DUPLICATE_NONCE") prefix = "{\"interface_version\":\"" + R7Fixed.InterfaceVersion + "\",\"operation\":\"GET_HEALTH\",\"payload\":{},\"protocol_version\":\"" + R7Fixed.ProtocolVersion + "\",\"request_identity\":\"" + nonce + "\",\"request_identity\":\"" + Guid.NewGuid().ToString("D") + "\"}";
            else if (definition.Mutation == "DUPLICATE_NESTED_EVIDENCE") prefix = "{\"interface_version\":\"" + R7Fixed.InterfaceVersion + "\",\"operation\":\"SUBMIT_RUN_GRAPH\",\"payload\":{\"evidence\":{\"identity\":\"" + R7Fixed.ZeroHash + "\",\"identity\":\"" + new string('1', 64) + "\"}},\"protocol_version\":\"" + R7Fixed.ProtocolVersion + "\",\"request_identity\":\"" + nonce + "\"}";
            else if (definition.Mutation == "DUPLICATE_VERSION") prefix = "{\"interface_version\":\"" + R7Fixed.InterfaceVersion + "\",\"operation\":\"GET_HEALTH\",\"payload\":{},\"protocol_version\":\"0.0\",\"protocol_version\":\"" + R7Fixed.ProtocolVersion + "\",\"request_identity\":\"" + nonce + "\"}";
            else if (definition.Mutation == "DUPLICATE_PAYLOAD") prefix = "{\"interface_version\":\"" + R7Fixed.InterfaceVersion + "\",\"operation\":\"GET_HEALTH\",\"payload\":{\"attack\":true},\"payload\":{},\"protocol_version\":\"" + R7Fixed.ProtocolVersion + "\",\"request_identity\":\"" + nonce + "\"}";
            else if (definition.Mutation == "DUPLICATE_RECEIPT_LOCATOR") prefix = "{\"interface_version\":\"" + R7Fixed.InterfaceVersion + "\",\"operation\":\"GET_TERMINAL_RECEIPT\",\"payload\":{\"receipt_identity\":\"" + R7Fixed.ZeroHash + "\",\"receipt_identity\":\"" + new string('1', 64) + "\"},\"protocol_version\":\"" + R7Fixed.ProtocolVersion + "\",\"request_identity\":\"" + nonce + "\"}";
            else if (definition.Mutation == "DUPLICATE_LEDGER_IDENTITY") prefix = "{\"interface_version\":\"" + R7Fixed.InterfaceVersion + "\",\"operation\":\"VERIFY_PUBLIC_IDENTITY\",\"payload\":{\"ledger_identity\":\"" + R7Fixed.ZeroHash + "\",\"ledger_identity\":\"" + R7Fixed.LedgerId + "\",\"trust_identity\":\"" + R7Fixed.TerminalPublicKeyIdentity + "\"},\"protocol_version\":\"" + R7Fixed.ProtocolVersion + "\",\"request_identity\":\"" + nonce + "\"}";
            else if (definition.Mutation == "DUPLICATE_TRUST_IDENTITY") prefix = "{\"interface_version\":\"" + R7Fixed.InterfaceVersion + "\",\"operation\":\"VERIFY_PUBLIC_IDENTITY\",\"payload\":{\"ledger_identity\":\"" + R7Fixed.LedgerId + "\",\"trust_identity\":\"" + R7Fixed.ZeroHash + "\",\"trust_identity\":\"" + R7Fixed.TerminalPublicKeyIdentity + "\"},\"protocol_version\":\"" + R7Fixed.ProtocolVersion + "\",\"request_identity\":\"" + nonce + "\"}";
            else if (definition.Mutation == "DUPLICATE_CASE_IDENTITY") prefix = "{\"interface_version\":\"" + R7Fixed.InterfaceVersion + "\",\"operation\":\"VERIFY_CASE_AUTHORITY\",\"payload\":{\"case_id\":\"AUT-001\",\"case_id\":\"AUT-002\"},\"protocol_version\":\"" + R7Fixed.ProtocolVersion + "\",\"request_identity\":\"" + nonce + "\"}";
            else if (definition.Mutation == "DUPLICATE_EXPECTATION_IDENTITY") prefix = "{\"interface_version\":\"" + R7Fixed.InterfaceVersion + "\",\"operation\":\"SUBMIT_RUN_GRAPH\",\"payload\":{\"evidence\":{\"expectation_identity\":\"" + R7Fixed.ZeroHash + "\",\"expectation_identity\":\"" + new string('1', 64) + "\"}},\"protocol_version\":\"" + R7Fixed.ProtocolVersion + "\",\"request_identity\":\"" + nonce + "\"}";
            else if (definition.Mutation == "TWO_JSON_OBJECTS" || definition.Mutation == "TRAILING_JSON") prefix += "{}";
            else if (definition.Mutation == "NUMERIC_STRING") prefix = "{\"interface_version\":\"" + R7Fixed.InterfaceVersion + "\",\"operation\":\"GET_LEDGER_ENTRY\",\"payload\":{\"sequence\":\"1\"},\"protocol_version\":\"" + R7Fixed.ProtocolVersion + "\",\"request_identity\":\"" + nonce + "\"}";
            else if (definition.Mutation == "NULL_INSTEAD_OF_ABSENT") prefix = "{\"interface_version\":\"" + R7Fixed.InterfaceVersion + "\",\"operation\":\"GET_TERMINAL_RECEIPT\",\"payload\":{\"receipt_identity\":null},\"protocol_version\":\"" + R7Fixed.ProtocolVersion + "\",\"request_identity\":\"" + nonce + "\"}";
            else if (definition.Mutation == "NON_NFC_IDENTIFIER") prefix = "{\"interface_version\":\"" + R7Fixed.InterfaceVersion + "\",\"operation\":\"GET_TERMINAL_RECEIPT\",\"payload\":{\"receipt_identity\":\"e\u0301\"},\"protocol_version\":\"" + R7Fixed.ProtocolVersion + "\",\"request_identity\":\"" + nonce + "\"}";
            if (definition.Mutation == "INVALID_UTF8") return Frame(new byte[] { 0x7b, 0x22, 0x78, 0x22, 0x3a, 0x22, 0xc3, 0x28, 0x22, 0x7d });
            if (definition.Mutation == "FRAME_65536")
            {
                SortedDictionary<string, object> request = R7RoleClient.Request("FRAME_BOUNDARY", R7Json.Object("padding", String.Empty));
                byte[] encoded = R7Json.Encode(request);
                request["payload"] = R7Json.Object("padding", new string('A', R7Fixed.MaximumPayloadBytes - encoded.Length));
                encoded = R7Json.Encode(request);
                if (encoded.Length != R7Fixed.MaximumPayloadBytes) throw new InvalidDataException("FRAME_BOUNDARY_CONSTRUCTION_FAILED");
                return Frame(encoded);
            }
            if (definition.Mutation == "FRAME_65537")
            {
                byte[] oversized = new byte[R7Fixed.MaximumPayloadBytes + 1];
                for (int index = 0; index < oversized.Length; index++) oversized[index] = 0x20;
                return Frame(oversized);
            }
            if (definition.Mutation == "PARTIAL_FRAME")
            {
                byte[] complete = Frame(new UTF8Encoding(false, true).GetBytes(prefix));
                byte[] partial = new byte[7];
                Buffer.BlockCopy(complete, 0, partial, 0, partial.Length);
                expectResponse = false;
                return partial;
            }
            if (definition.Mutation == "MULTIPLE_FRAMES")
            {
                byte[] first = Frame(new UTF8Encoding(false, true).GetBytes(prefix));
                byte[] second = Frame(new UTF8Encoding(false, true).GetBytes(prefix));
                byte[] combined = new byte[first.Length + second.Length];
                Buffer.BlockCopy(first, 0, combined, 0, first.Length);
                Buffer.BlockCopy(second, 0, combined, first.Length, second.Length);
                return combined;
            }
            return Frame(new UTF8Encoding(false, true).GetBytes(prefix));
        }

        private static SortedDictionary<string, object> PositivePayload(R7CaseOnlyDefinition definition, SortedDictionary<string, object> fixture)
        {
            if (definition.Operation == "GET_HEALTH" || definition.Operation == "GET_PUBLIC_TRUST" || definition.Operation == "GET_LEDGER_STATUS" || definition.Operation == "GET_VERSION_HISTORY") return R7Json.Object();
            if (definition.Operation == "GET_LEDGER_ENTRY" || definition.Operation == "CLASSIFY_LEDGER_SEQUENCE") return R7Json.Object("sequence", R7Json.Integer(fixture, "sequence", 1, Int64.MaxValue));
            if (definition.Operation == "GET_TERMINAL_RECEIPT" || definition.Operation == "GET_RECONCILIATION" || definition.Operation == "VERIFY_TERMINAL_RECEIPT" || definition.Operation == "VERIFY_RECONCILIATION" || definition.Operation == "CLASSIFY_RECEIPT") return R7Json.Object("receipt_identity", R7Json.String(fixture, "receipt_identity", 64, 64));
            if (definition.Operation == "GET_RECOVERY_STATE") return R7Json.Object("request_identity", R7Json.String(fixture, "request_identity", 36, 36));
            if (definition.Operation == "RETRY_REQUEST") return R7Json.Object("original_request_identity", R7Json.String(fixture, "original_request_identity", 36, 36));
            if (definition.Operation == "SUBMIT_TERMINAL_PROPOSAL") return R7Json.Object("checkout_identity", R7Json.String(fixture, "checkout_identity", 64, 64), "configuration", R7Json.Child(fixture, "configuration"), "proposal_identity", R7Json.String(fixture, "proposal_identity", 64, 64));
            if (definition.Operation == "SUBMIT_RUN_GRAPH")
            {
                R7Json.ExactKeys(fixture, "case_graph_path", "case_graph_sha256", "checkout_identity", "configuration", "provenance_identity", "run_kind");
                string graphPath = Path.GetFullPath(R7Json.String(fixture, "case_graph_path", 3, 4096));
                if (!graphPath.StartsWith(R7Fixed.ExecutionTestRoot + Path.DirectorySeparatorChar, StringComparison.Ordinal)) throw new SecurityException("CASE_GRAPH_INPUT_ROOT_INVALID");
                object[] caseGraphs;
                using (R7VerifiedFile graphFile = R7SafeFile.Open(graphPath, graphPath, R7Fixed.ExecutionTestRoot, R7Json.String(fixture, "case_graph_sha256", 64, 64), null, null, null))
                {
                    caseGraphs = R7Json.ParseCanonical(graphFile.Bytes) as object[];
                    if (caseGraphs == null || caseGraphs.Length < 1) throw new InvalidDataException("CASE_GRAPH_INPUT_INVALID");
                }
                return R7Json.Object(
                    "case_graphs", caseGraphs,
                    "checkout_identity", R7Json.String(fixture, "checkout_identity", 64, 64),
                    "configuration", R7Json.Child(fixture, "configuration"),
                    "provenance_identity", R7Json.String(fixture, "provenance_identity", 64, 64),
                    "run_kind", R7Json.String(fixture, "run_kind", 1, 64));
            }
            if (definition.Operation == "SUBMIT_RECONCILIATION") return R7Json.Object("candidate_receipt_identity", R7Json.String(fixture, "candidate_receipt_identity", 64, 64), "fresh_receipt_identity", R7Json.String(fixture, "fresh_receipt_identity", 64, 64), "reconciliation_provenance_identity", R7Json.String(fixture, "reconciliation_provenance_identity", 64, 64));
            if (definition.Operation == "VERIFY_PUBLIC_IDENTITY") return R7Json.Object("ledger_identity", R7Json.String(fixture, "ledger_identity", 64, 64), "trust_identity", R7Json.String(fixture, "trust_identity", 64, 64));
            return fixture;
        }

        private static SortedDictionary<string, object> ProbeTarget(string mutation, SortedDictionary<string, object> fixture)
        {
            bool granted = false;
            int error = 0;
            string stable = R7Hash.Bytes(new UTF8Encoding(false, true).GetBytes("TARGET|" + mutation + "|" + (fixture.ContainsKey("target_identity") ? R7Json.String(fixture, "target_identity", 1, 256) : "FIXED")));
            try
            {
                if (mutation == "DIRECT_KEY_OPEN" || mutation == "EVENT_PRODUCER_READ_EXPECTATION")
                {
                    string path = mutation == "DIRECT_KEY_OPEN" ? R7BuildIdentity.TerminalKeyFilePath : R7Fixed.ExpectationPath;
                    using (FileStream stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read)) { granted = true; }
                }
                else if (mutation == "DIRECT_LEDGER_APPEND") granted = CanOpenDirectoryForAdd(R7Fixed.LedgerRoot);
                else if (mutation == "DIRECT_TRUST_WRITE") granted = CanOpenDirectoryForAdd(Path.GetDirectoryName(R7Fixed.TerminalPublicCertificatePath));
                else if (mutation == "DIRECT_RECEIPT_WRITE") granted = CanOpenDirectoryForAdd(R7Fixed.ReceiptRoot);
                else if (mutation == "SIGNER_SID_MEMBERSHIP" || mutation == "DESCENDANT_CAPABILITY" || mutation == "SIGNER_PROCESS_CREATION") granted = WindowsIdentity.GetCurrent().Groups.Contains(new SecurityIdentifier(R7Fixed.TerminalSid));
                else granted = false;
            }
            catch (UnauthorizedAccessException exception) { error = exception.HResult; }
            catch (CryptographicException exception) { error = exception.HResult; }
            catch (IOException exception) { error = exception.HResult; }
            return R7Json.Object("access_granted", granted, "error_code", error.ToString("x8", CultureInfo.InvariantCulture), "target_sha256_after", stable, "target_sha256_before", stable);
        }

        private static string RecoveryFault(R7CaseOnlyDefinition definition)
        {
            if (definition.Driver == "RECOVERY_HARNESS")
            {
                if (definition.Mutation == "FAULT_INJECTION") return definition.CaseId;
                return definition.Mutation;
            }
            return definition.Mutation;
        }

        private static byte[] Frame(byte[] payload)
        {
            byte[] header = Header(payload.Length);
            byte[] frame = new byte[header.Length + payload.Length];
            Buffer.BlockCopy(header, 0, frame, 0, header.Length);
            Buffer.BlockCopy(payload, 0, frame, header.Length, payload.Length);
            return frame;
        }

        private static byte[] Header(int length)
        {
            return new byte[] { 0x52, 0x37, 0x54, 0x41, 4, 0, 0, 0, (byte)(length >> 24), (byte)(length >> 16), (byte)(length >> 8), (byte)length };
        }

        private const uint FileAddFile = 0x00000002;
        private const uint FileShareRead = 0x00000001;
        private const uint OpenExisting = 3;
        private const uint FileFlagBackupSemantics = 0x02000000;
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)] private static extern SafeFileHandle CreateFileW(string name, uint access, uint share, IntPtr security, uint creation, uint flags, IntPtr templateFile);
        private static bool CanOpenDirectoryForAdd(string path)
        {
            using (SafeFileHandle handle = CreateFileW(path, FileAddFile, FileShareRead, IntPtr.Zero, OpenExisting, FileFlagBackupSemantics, IntPtr.Zero)) return !handle.IsInvalid;
        }
    }
#endif

#if OBSERVATION_ROLE
    internal sealed class R7ObservationProcessor : R7PipeProcessor
    {
        private readonly R7ActiveUpgrade activeUpgrade;
        private readonly string binarySha256;
        private readonly R7VerifiedFile binaryFile;
        private readonly R7DependencyClosure dependencies;

        internal R7ObservationProcessor()
        {
            if (WindowsIdentity.GetCurrent().User.Value != R7Fixed.ObservationSid) throw new SecurityException("OBSERVATION_SERVICE_SID_MISMATCH");
            string executable = Path.GetFullPath(System.Reflection.Assembly.GetExecutingAssembly().Location);
            if (!String.Equals(executable, R7BuildIdentity.ObservationBinaryPath, StringComparison.Ordinal)) throw new SecurityException("OBSERVATION_BINARY_PATH_MISMATCH");
            activeUpgrade = R7ActiveUpgrade.ResolveAuthorization("OBSERVATION");
            R7TerminalPolicy terminalPolicy = R7TerminalPolicy.Load(activeUpgrade.TerminalPolicySha256);
            VerifyRolePolicy(terminalPolicy, activeUpgrade);
            R7ComponentIdentity component = terminalPolicy.Component("OBSERVATION");
            binaryFile = R7SafeFile.Open(executable, component.Path, R7Fixed.TerminalInstallRoot, component.Sha256, R7Fixed.SystemSid, null, terminalPolicy.VolumeIdentity);
            binarySha256 = binaryFile.Measurement.Sha256;
            dependencies = new R7DependencyClosure(R7Fixed.DependencyManifestPath, terminalPolicy.DependencyManifestSha256, R7Fixed.TerminalInstallRoot);
        }

        internal override SortedDictionary<string, object> Process(R7RequestContext context, SortedDictionary<string, object> request)
        {
            dependencies.VerifyNoNewModules();
            try
            {
            string operation;
            SortedDictionary<string, object> payload;
            R7RoleProtocol.Require(request, out operation, out payload);
            if (context.Caller.UserSid != R7Fixed.OperatorSid && context.Caller.UserSid != R7Fixed.SystemSid) throw new SecurityException("CALLER_NOT_AUTHORIZED");
            if (operation == "GET_ROLE_HEALTH")
            {
                R7Json.ExactKeys(payload);
                SortedDictionary<string, object> health = R7PipeWindowsService.Success("OBSERVATION_ROLE_HEALTHY");
                health.Add("binary_sha256", binarySha256);
                health.Add("binary_file_identity", binaryFile.Measurement.FileIdentity);
                health.Add("expectation_artifact_read", false);
                health.Add("service_sid", R7Fixed.ObservationSid);
                health.Add("terminal_signer_sid_present", false);
                return health;
            }
            activeUpgrade.RequireActivatedComponent("OBSERVATION", binaryFile.Measurement.FileIdentity);
            if (operation == "PROBE_EXPECTATION_ACCESS")
            {
                R7Json.ExactKeys(payload, "case_id", "mutation", "target_identity");
                bool granted = false;
                int error = 0;
                try { using (FileStream stream = new FileStream(R7Fixed.ExpectationPath, FileMode.Open, FileAccess.Read, FileShare.Read)) { granted = true; } }
                catch (UnauthorizedAccessException exception) { error = exception.HResult; }
                catch (IOException exception) { error = exception.HResult; }
                string stable = R7Hash.Bytes(new UTF8Encoding(false, true).GetBytes("EXPECTATION|" + R7Json.String(payload, "target_identity", 1, 256)));
                SortedDictionary<string, object> terminal = R7RoleClient.Request("SUBMIT_OBSERVATION_EVIDENCE", R7Json.Object(
                    "evidence", R7Json.Object(
                        "case_id", R7Json.String(payload, "case_id", 1, 128),
                        "mutation", R7Json.String(payload, "mutation", 1, 256),
                        "probe_result", R7Json.Object("access_granted", granted, "error_code", error.ToString("x8", CultureInfo.InvariantCulture), "target_sha256_after", stable, "target_sha256_before", stable),
                        "target_identity", R7Json.String(payload, "target_identity", 1, 256)),
                    "evidence_kind", "PRINCIPAL_PROBE"));
                return SubmitProbe(terminal);
            }
            if (operation == "PROBE_EXPECTATION_INJECTION")
            {
                R7Json.ExactKeys(payload, "case_id", "mutation", "target_identity");
                SortedDictionary<string, object> terminal = R7RoleClient.Request("SUBMIT_OBSERVATION_EVIDENCE", R7Json.Object(
                    "evidence", R7Json.Object(
                        "base_interaction_identity", R7Fixed.ZeroHash,
                        "expected_code", "INJECTED",
                        "observation", R7Json.Object("actual_code", "MISSING", "actual_status", "MISSING", "ledger_sequence_after", 0L, "ledger_sequence_before", 0L, "side_effect_identity", R7Fixed.ZeroHash)),
                    "evidence_kind", "OBSERVATION"));
                return SubmitProbe(terminal);
            }
            if (operation != "OBSERVE_RAW") throw new R7ProtocolException("OPERATION_NOT_ALLOWED");
            R7Json.ExactKeys(payload, "base_interaction_identity", "case_id", "ledger_sequence_after", "ledger_sequence_before", "request_frame", "response_frame");
            string baseIdentity = R7Json.String(payload, "base_interaction_identity", 64, 64);
            string caseId = R7Json.String(payload, "case_id", 1, 128);
            byte[] requestFrame;
            byte[] responseFrame;
            try
            {
                requestFrame = Convert.FromBase64String(R7Json.String(payload, "request_frame", 1, R7Fixed.MaximumEncodedCaptureChars));
                responseFrame = Convert.FromBase64String(R7Json.String(payload, "response_frame", 1, R7Fixed.MaximumEncodedFrameChars));
            }
            catch (FormatException) { throw new R7ProtocolException("RAW_FRAME_ENCODING_INVALID"); }
            SortedDictionary<string, object> responseMessage = R7Framing.Decode(responseFrame);
            string actualStatus = R7Json.String(responseMessage, "status", 1, 64);
            string actualCode = actualStatus == "COMPLETE" ? R7Json.String(responseMessage, "result_code", 1, 256) : R7Json.String(responseMessage, "error_code", 1, 256);
            string requestHash = R7Hash.Bytes(requestFrame);
            string responseHash = R7Hash.Bytes(responseFrame);
            string sideEffectIdentity = R7Hash.Bytes(R7Json.Encode(R7Json.Object(
                "ledger_sequence_after", R7Json.Integer(payload, "ledger_sequence_after", 0, Int64.MaxValue),
                "ledger_sequence_before", R7Json.Integer(payload, "ledger_sequence_before", 0, Int64.MaxValue),
                "request_frame_sha256", requestHash,
                "response_frame_sha256", responseHash)));
            SortedDictionary<string, object> terminalRequest = R7RoleClient.Request("SUBMIT_OBSERVATION_EVIDENCE", R7Json.Object(
                "evidence", R7Json.Object(
                    "base_interaction_identity", baseIdentity,
                    "case_id", caseId,
                    "observation", R7Json.Object(
                        "actual_code", actualCode,
                        "actual_status", actualStatus,
                        "ledger_sequence_after", R7Json.Integer(payload, "ledger_sequence_after", 0, Int64.MaxValue),
                        "ledger_sequence_before", R7Json.Integer(payload, "ledger_sequence_before", 0, Int64.MaxValue),
                        "side_effect_identity", sideEffectIdentity),
                    "raw_request_frame", Convert.ToBase64String(requestFrame),
                    "raw_response_frame", Convert.ToBase64String(responseFrame)),
                "evidence_kind", "OBSERVATION"));
            byte[] sent;
            byte[] received;
            R7Framing.Call(R7Fixed.TerminalPipe, terminalRequest, 30000, out sent, out received);
            SortedDictionary<string, object> result = R7PipeWindowsService.Success("OBSERVATION_PRODUCED_FROM_RAW_CURRENT_RUN_EVIDENCE");
            result.Add("expectation_artifact_read", false);
            result.Add("side_effect_identity", sideEffectIdentity);
            result.Add("submission_request_frame", Convert.ToBase64String(sent));
            result.Add("submission_request_frame_sha256", R7Hash.Bytes(sent));
            return result;
            }
            finally { dependencies.VerifyNoNewModules(); }
        }

        private static SortedDictionary<string, object> SubmitProbe(SortedDictionary<string, object> terminal)
        {
            byte[] sent;
            byte[] received;
            SortedDictionary<string, object> signerResponse = R7Framing.Call(R7Fixed.TerminalPipe, terminal, 30000, out sent, out received);
            SortedDictionary<string, object> result = R7PipeWindowsService.Success("ROLE_PROBE_SUBMITTED");
            result.Add("signer_response", signerResponse);
            result.Add("submission_request_frame", Convert.ToBase64String(sent));
            result.Add("submission_request_frame_sha256", R7Hash.Bytes(sent));
            return result;
        }

        public override void Dispose() { dependencies.Dispose(); binaryFile.Dispose(); }

        private static void VerifyRolePolicy(R7TerminalPolicy terminalPolicy, R7ActiveUpgrade activeUpgrade)
        {
            if (!String.Equals(terminalPolicy.SourceCommit, R7BuildIdentity.SourceCommit, StringComparison.Ordinal) ||
                !String.Equals(terminalPolicy.SourceTree, R7BuildIdentity.SourceTree, StringComparison.Ordinal) ||
                !String.Equals(terminalPolicy.UpgradePublicCertificateSha256, R7BuildIdentity.UpgradePublicCertificateSha256, StringComparison.Ordinal) ||
                !R7Hash.FixedTimeEquals(terminalPolicy.DependencyManifestSha256, R7BuildIdentity.DependencyManifestSha256) ||
                !R7Hash.FixedTimeEquals(terminalPolicy.BuildReceiptSha256, R7Json.String(activeUpgrade.AuthorizationPayload, "build_receipt_sha256", 64, 64))) throw new SecurityException("ROLE_POLICY_SOURCE_MISMATCH");
        }
    }
#endif

#if COMPARATOR_ROLE
    internal sealed class R7ComparatorExpectation
    {
        internal string ResponseClass;
        internal string ResultCode;
    }

    internal sealed class R7ComparatorProcessor : R7PipeProcessor
    {
        private readonly R7ActiveUpgrade activeUpgrade;
        private readonly Dictionary<string, R7ComparatorExpectation> expectations = new Dictionary<string, R7ComparatorExpectation>(StringComparer.Ordinal);
        private readonly string binarySha256;
        private readonly R7VerifiedFile binaryFile;
        private readonly R7DependencyClosure dependencies;

        internal R7ComparatorProcessor()
        {
            if (WindowsIdentity.GetCurrent().User.Value != R7Fixed.ComparatorSid) throw new SecurityException("COMPARATOR_SERVICE_SID_MISMATCH");
            string executable = Path.GetFullPath(System.Reflection.Assembly.GetExecutingAssembly().Location);
            if (!String.Equals(executable, R7BuildIdentity.ComparatorBinaryPath, StringComparison.Ordinal)) throw new SecurityException("COMPARATOR_BINARY_PATH_MISMATCH");
            activeUpgrade = R7ActiveUpgrade.ResolveAuthorization("COMPARATOR");
            R7TerminalPolicy terminalPolicy = R7TerminalPolicy.Load(activeUpgrade.TerminalPolicySha256);
            VerifyRolePolicy(terminalPolicy, activeUpgrade);
            R7ComponentIdentity component = terminalPolicy.Component("COMPARATOR");
            binaryFile = R7SafeFile.Open(executable, component.Path, R7Fixed.TerminalInstallRoot, component.Sha256, R7Fixed.SystemSid, null, terminalPolicy.VolumeIdentity);
            binarySha256 = binaryFile.Measurement.Sha256;
            dependencies = new R7DependencyClosure(R7Fixed.DependencyManifestPath, terminalPolicy.DependencyManifestSha256, R7Fixed.TerminalInstallRoot);
            using (R7VerifiedFile file = R7SafeFile.Open(R7Fixed.ExpectationPath, R7Fixed.ExpectationPath, Path.GetDirectoryName(R7Fixed.ExpectationPath), R7BuildIdentity.ExpectationsSha256, R7Fixed.SystemSid, null, null))
            {
                SortedDictionary<string, object> artifact = RequireObject(R7Json.Parse(file.Bytes));
                object[] expectationRows = R7Json.Array(artifact, "expectations");
                if (R7Json.Boolean(artifact, "case_artifact_read") || R7Json.Boolean(artifact, "runtime_evidence_read") || R7Json.Integer(artifact, "expectation_count", 1, 100000) != expectationRows.Length) throw new SecurityException("EXPECTATION_ARTIFACT_INDEPENDENCE_INVALID");
                foreach (object raw in expectationRows)
                {
                    SortedDictionary<string, object> row = RequireObject(raw);
                    string caseId = R7Json.String(row, "case_id", 1, 128);
                    if (expectations.ContainsKey(caseId)) throw new SecurityException("DUPLICATE_EXPECTATION");
                    expectations.Add(caseId, new R7ComparatorExpectation
                    {
                        ResponseClass = R7Json.String(row, "expected_response_class", 1, 256),
                        ResultCode = R7Json.String(row, "expected_result_code", 1, 256)
                    });
                }
            }
        }

        internal override SortedDictionary<string, object> Process(R7RequestContext context, SortedDictionary<string, object> request)
        {
            dependencies.VerifyNoNewModules();
            try
            {
            string operation;
            SortedDictionary<string, object> payload;
            R7RoleProtocol.Require(request, out operation, out payload);
            if (context.Caller.UserSid != R7Fixed.OperatorSid && context.Caller.UserSid != R7Fixed.SystemSid) throw new SecurityException("CALLER_NOT_AUTHORIZED");
            if (operation == "GET_ROLE_HEALTH")
            {
                R7Json.ExactKeys(payload);
                SortedDictionary<string, object> health = R7PipeWindowsService.Success("COMPARATOR_ROLE_HEALTHY");
                health.Add("binary_sha256", binarySha256);
                health.Add("binary_file_identity", binaryFile.Measurement.FileIdentity);
                health.Add("expectation_count", (long)expectations.Count);
                health.Add("service_sid", R7Fixed.ComparatorSid);
                health.Add("terminal_signer_sid_present", false);
                return health;
            }
            activeUpgrade.RequireActivatedComponent("COMPARATOR", binaryFile.Measurement.FileIdentity);
            if (operation == "PROBE_TERMINAL_KEY_ACCESS")
            {
                R7Json.ExactKeys(payload, "case_id", "mutation", "target_identity");
                bool granted = false;
                int error = 0;
                try { using (FileStream stream = new FileStream(R7BuildIdentity.TerminalKeyFilePath, FileMode.Open, FileAccess.Read, FileShare.Read)) { granted = true; } }
                catch (UnauthorizedAccessException exception) { error = exception.HResult; }
                catch (CryptographicException exception) { error = exception.HResult; }
                catch (IOException exception) { error = exception.HResult; }
                string stable = R7Hash.Bytes(new UTF8Encoding(false, true).GetBytes("TERMINAL_KEY|" + R7Json.String(payload, "target_identity", 1, 256)));
                SortedDictionary<string, object> terminal = R7RoleClient.Request("SUBMIT_COMPARATOR_EVIDENCE", R7Json.Object(
                    "evidence", R7Json.Object(
                        "case_id", R7Json.String(payload, "case_id", 1, 128),
                        "mutation", R7Json.String(payload, "mutation", 1, 256),
                        "probe_result", R7Json.Object("access_granted", granted, "error_code", error.ToString("x8", CultureInfo.InvariantCulture), "target_sha256_after", stable, "target_sha256_before", stable),
                        "target_identity", R7Json.String(payload, "target_identity", 1, 256)),
                    "evidence_kind", "PRINCIPAL_PROBE"));
                return SubmitProbe(terminal);
            }
            if (operation == "PROBE_SUMMARY_ONLY")
            {
                R7Json.ExactKeys(payload, "case_id", "mutation", "target_identity");
                SortedDictionary<string, object> terminal = R7RoleClient.Request("SUBMIT_COMPARATOR_EVIDENCE", R7Json.Object(
                    "evidence", R7Json.Object(
                        "case_id", R7Json.String(payload, "case_id", 1, 128),
                        "mutation", R7Json.String(payload, "mutation", 1, 256),
                        "summary", R7Json.Object("actual_code", "MATCH", "actual_status", "COMPLETE", "raw_evidence_present", false)),
                    "evidence_kind", "HOSTILE_SUMMARY"));
                return SubmitProbe(terminal);
            }
            if (operation != "COMPARE_RAW") throw new R7ProtocolException("OPERATION_NOT_ALLOWED");
            R7Json.ExactKeys(payload, "base_interaction_identity", "case_id", "event_interaction_identity", "observation_interaction_identity", "response_frame");
            string caseId = R7Json.String(payload, "case_id", 1, 128);
            R7ComparatorExpectation expectation;
            if (!expectations.TryGetValue(caseId, out expectation)) throw new R7ProtocolException("EXPECTATION_IDENTITY_UNRESOLVED");
            byte[] rawResponse;
            try { rawResponse = Convert.FromBase64String(R7Json.String(payload, "response_frame", 1, R7Fixed.MaximumEncodedFrameChars)); }
            catch (FormatException) { throw new R7ProtocolException("RAW_FRAME_ENCODING_INVALID"); }
            SortedDictionary<string, object> responseMessage = R7Framing.Decode(rawResponse);
            string actualStatus = R7Json.String(responseMessage, "status", 1, 64);
            string actualCode = actualStatus == "COMPLETE" ? R7Json.String(responseMessage, "result_code", 1, 256) : R7Json.String(responseMessage, "error_code", 1, 256);
            bool match = ((expectation.ResponseClass == "COMPLETE" && actualStatus == "COMPLETE") || (expectation.ResponseClass == "REJECTED" && actualStatus == "REJECTED") || (expectation.ResponseClass == "UNAVAILABLE" && actualStatus == "UNAVAILABLE")) && actualCode == expectation.ResultCode;
            SortedDictionary<string, object> terminalRequest = R7RoleClient.Request("SUBMIT_COMPARATOR_EVIDENCE", R7Json.Object(
                "evidence", R7Json.Object(
                    "actual_code", actualCode,
                    "actual_status", actualStatus,
                    "base_interaction_identity", R7Json.String(payload, "base_interaction_identity", 64, 64),
                    "case_id", caseId,
                    "comparison", R7Json.Object("comparison_code", match ? "MATCH" : "MISMATCH", "raw_graph_complete", true),
                    "event_interaction_identity", R7Json.String(payload, "event_interaction_identity", 64, 64),
                    "observation_interaction_identity", R7Json.String(payload, "observation_interaction_identity", 64, 64),
                    "raw_response_frame", Convert.ToBase64String(rawResponse)),
                "evidence_kind", "COMPARISON"));
            byte[] sent;
            byte[] received;
            R7Framing.Call(R7Fixed.TerminalPipe, terminalRequest, 30000, out sent, out received);
            SortedDictionary<string, object> result = R7PipeWindowsService.Success("COMPARISON_PRODUCED_FROM_INDEPENDENT_EXPECTATION_AND_RAW_EVIDENCE");
            result.Add("comparison_code", match ? "MATCH" : "MISMATCH");
            result.Add("submission_request_frame", Convert.ToBase64String(sent));
            result.Add("submission_request_frame_sha256", R7Hash.Bytes(sent));
            return result;
            }
            finally { dependencies.VerifyNoNewModules(); }
        }

        private static SortedDictionary<string, object> SubmitProbe(SortedDictionary<string, object> terminal)
        {
            byte[] sent;
            byte[] received;
            SortedDictionary<string, object> signerResponse = R7Framing.Call(R7Fixed.TerminalPipe, terminal, 30000, out sent, out received);
            SortedDictionary<string, object> result = R7PipeWindowsService.Success("ROLE_PROBE_SUBMITTED");
            result.Add("signer_response", signerResponse);
            result.Add("submission_request_frame", Convert.ToBase64String(sent));
            result.Add("submission_request_frame_sha256", R7Hash.Bytes(sent));
            return result;
        }

        public override void Dispose() { dependencies.Dispose(); binaryFile.Dispose(); }

        private static void VerifyRolePolicy(R7TerminalPolicy terminalPolicy, R7ActiveUpgrade activeUpgrade)
        {
            if (!String.Equals(terminalPolicy.SourceCommit, R7BuildIdentity.SourceCommit, StringComparison.Ordinal) ||
                !String.Equals(terminalPolicy.SourceTree, R7BuildIdentity.SourceTree, StringComparison.Ordinal) ||
                !String.Equals(terminalPolicy.UpgradePublicCertificateSha256, R7BuildIdentity.UpgradePublicCertificateSha256, StringComparison.Ordinal) ||
                !R7Hash.FixedTimeEquals(terminalPolicy.DependencyManifestSha256, R7BuildIdentity.DependencyManifestSha256) ||
                !R7Hash.FixedTimeEquals(terminalPolicy.BuildReceiptSha256, R7Json.String(activeUpgrade.AuthorizationPayload, "build_receipt_sha256", 64, 64))) throw new SecurityException("ROLE_POLICY_SOURCE_MISMATCH");
        }

        private static SortedDictionary<string, object> RequireObject(object value)
        {
            SortedDictionary<string, object> result = value as SortedDictionary<string, object>;
            if (result == null) throw new R7ProtocolException("OBJECT_REQUIRED");
            return result;
        }
    }
#endif

    internal static class R7RoleProtocol
    {
        internal static void Require(SortedDictionary<string, object> request, out string operation, out SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(request, "interface_version", "operation", "payload", "protocol_version", "request_identity");
            if (!String.Equals(R7Json.String(request, "interface_version", 1, 128), "1.0.0", StringComparison.Ordinal) || !String.Equals(R7Json.String(request, "protocol_version", 1, 64), R7Fixed.ProtocolVersion, StringComparison.Ordinal)) throw new R7ProtocolException("INTERFACE_VERSION_REJECTED");
            string requestIdentity = R7Json.String(request, "request_identity", 36, 36);
            Guid parsed;
            if (!Guid.TryParseExact(requestIdentity, "D", out parsed) || parsed.ToString("D") != requestIdentity) throw new R7ProtocolException("REQUEST_IDENTITY_INVALID");
            operation = R7Json.String(request, "operation", 1, 128);
            payload = R7Json.Child(request, "payload");
        }
    }

#if EXECUTION_ROLE
    internal static class R7ExecutionServiceProgram
    {
        private static void Main(string[] args)
        {
            R7RuntimeBoundary.Enforce(R7Fixed.TerminalInstallRoot);
            if (args != null && args.Length == 1 && String.Equals(args[0], "--r7-restricted-descendant-probe", StringComparison.Ordinal))
            {
                using (WindowsIdentity identity = WindowsIdentity.GetCurrent())
                {
                    if (identity.User == null || !String.Equals(identity.User.Value, R7Fixed.ExecutionSid, StringComparison.Ordinal)) throw new SecurityException("DESCENDANT_EXECUTION_SID_MISMATCH");
                    if (identity.Groups != null && identity.Groups.Contains(new SecurityIdentifier(R7Fixed.TerminalSid))) throw new SecurityException("DESCENDANT_CONTAINS_TERMINAL_SIGNER_SID");
                }
                Thread.Sleep(60000);
                return;
            }
            if (args != null && args.Length != 0) throw new SecurityException("EXECUTION_ARGUMENT_NOT_ALLOWED");
            ServiceBase.Run(new R7PipeWindowsService(
                R7Fixed.ExecutionService,
                R7Fixed.ExecutionPipe,
                new string[] { R7Fixed.OperatorSid, R7Fixed.SystemSid, R7Fixed.ExecutionSid },
                delegate() { return new R7ExecutionProcessor(); }));
        }
    }
#endif

#if OBSERVATION_ROLE
    internal static class R7ObservationServiceProgram
    {
        private static void Main()
        {
            R7RuntimeBoundary.Enforce(R7Fixed.TerminalInstallRoot);
            ServiceBase.Run(new R7PipeWindowsService(
                R7Fixed.ObservationService,
                R7Fixed.ObservationPipe,
                new string[] { R7Fixed.OperatorSid, R7Fixed.SystemSid, R7Fixed.ObservationSid },
                delegate() { return new R7ObservationProcessor(); }));
        }
    }
#endif

#if COMPARATOR_ROLE
    internal static class R7ComparatorServiceProgram
    {
        private static void Main()
        {
            R7RuntimeBoundary.Enforce(R7Fixed.TerminalInstallRoot);
            ServiceBase.Run(new R7PipeWindowsService(
                R7Fixed.ComparatorService,
                R7Fixed.ComparatorPipe,
                new string[] { R7Fixed.OperatorSid, R7Fixed.SystemSid, R7Fixed.ComparatorSid },
                delegate() { return new R7ComparatorProcessor(); }));
        }
    }
#endif
}
