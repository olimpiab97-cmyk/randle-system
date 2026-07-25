using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;

namespace RandleAI.R7Remediation
{
    internal static class R7StaticVerificationProgram
    {
#if INSTALLED_STATIC_ROLE
        private const string ExecutionAuthorityClass = "INSTALLED_VERIFICATION_SUPPORT_NONAUTHORITY";
#else
        private const string ExecutionAuthorityClass = "BUILD_TIME_VERIFICATION_NONAUTHORITY";
#endif

        private static int Main(string[] args)
        {
            try
            {
#if INSTALLED_STATIC_ROLE
                R7RuntimeBoundary.Enforce(R7Fixed.TerminalInstallRoot);
                R7ActiveUpgrade activeUpgrade = R7ActiveUpgrade.ResolveAuthorization("STATIC_VERIFIER");
                R7TerminalPolicy terminalPolicy = R7TerminalPolicy.Load(activeUpgrade.TerminalPolicySha256);
                R7ComponentIdentity component = terminalPolicy.Component("STATIC_VERIFIER");
                string executable = Path.GetFullPath(Assembly.GetExecutingAssembly().Location);
                using (R7VerifiedFile binary = R7SafeFile.Open(executable, component.Path, R7Fixed.TerminalInstallRoot, component.Sha256, R7Fixed.SystemSid, null, terminalPolicy.VolumeIdentity))
                using (R7DependencyClosure dependencies = new R7DependencyClosure(R7Fixed.DependencyManifestPath, terminalPolicy.DependencyManifestSha256, R7Fixed.TerminalInstallRoot))
                {
                    activeUpgrade.RequireActivatedComponent("STATIC_VERIFIER", binary.Measurement.FileIdentity);
                    dependencies.VerifyNoNewModules();
                    int result = Dispatch(args);
                    dependencies.VerifyNoNewModules();
                    return result;
                }
#else
                R7RuntimeBoundary.EnforceUninstalledTool();
                return Dispatch(args);
#endif
            }
            catch (Exception exception)
            {
                Console.Error.WriteLine(exception.GetType().FullName + "|" + exception.Message);
                return 1;
            }
        }

        private static int Dispatch(string[] args)
        {
            if (args.Length == 1 && args[0] == "parser") return Emit(ParserVerification());
            if (args.Length == 7 && args[0] == "authority") return Emit(AuthorityVerification(args));
            if (args.Length == 4 && args[0] == "legacy") return Emit(LegacyVerification(args[1], args[2], Int64.Parse(args[3], CultureInfo.InvariantCulture)));
            if (args.Length == 8 && args[0] == "legacy-history") return Emit(R7PublicVerifierProgram.VerifyRetainedLegacyHistory(args[1], args[2], args[3], args[4], args[5], args[6], args[7]));
            if (args.Length == 2 && args[0] == "transaction") return Emit(TransactionVerification(args[1]));
            if (args.Length == 2 && args[0] == "recovery") return Emit(RecoveryVerification(args[1]));
            throw new ArgumentException("usage: parser | authority <package-root> <requirement-sha> <case-sha> <expectation-sha> <coverage-sha> <source-manifest-sha> | legacy <ledger-root> <certificate> <expected-sequence> | legacy-history <ledger-root> <certificate> <receipt-root> <reconciliation-root> <evidence-root> <response-root> <classification-registry> | transaction <isolated-output-root> | recovery <temporary-isolated-output-root>");
        }

        private static int Emit(SortedDictionary<string, object> result)
        {
            result.Add("execution_authority_class", ExecutionAuthorityClass);
            Console.WriteLine(R7Json.Text(result));
            return String.Equals(R7Json.String(result, "status", 1, 32), "PASS", StringComparison.Ordinal) ? 0 : 1;
        }

        private static SortedDictionary<string, object> AuthorityVerification(string[] args)
        {
            string root = Path.GetFullPath(args[1]);
            R7AuthorityLocation location = new R7AuthorityLocation
            {
                RequirementPath = Path.Combine(root, "governed_requirement_registry.json"),
                CasePath = Path.Combine(root, "immutable_case_definitions.json"),
                ExpectationPath = Path.Combine(root, "immutable_expectations.json"),
                CoveragePath = Path.Combine(root, "exact_byte_coverage_proof.json"),
                SourceRoot = Path.Combine(root, "AuthoritySources"),
                SourceManifestPath = Path.Combine(root, "AuthoritySources", "authority_source_manifest.json")
            };
            R7AuthoritySet authority = new R7AuthoritySet(new R7AuthorityIdentities(args[2], args[3], args[4], args[5], args[6]), location);
            return R7Json.Object(
                "artifact_type", "R7_STATIC_COMPLETE_AUTHORITY_PACKAGE_VERIFICATION",
                "case_count", (long)authority.CaseIds.Length,
                "independent_review_package_file_count", 30L,
                "normative_source_count", 5L,
                "schema_version", "1.0.0",
                "status", authority.CaseIds.Length > 0 ? "PASS" : "FAIL");
        }

        private static SortedDictionary<string, object> ParserVerification()
        {
            List<object> results = new List<object>();
            int passed = 0;
            string[] duplicatePayloads = new string[]
            {
                "{\"operation\":\"UNKNOWN\",\"operation\":\"GET_HEALTH\"}",
                "{\"nonce\":\"a\",\"nonce\":\"b\"}",
                "{\"version\":\"4.0\",\"version\":\"3.0\"}",
                "{\"payload\":{},\"payload\":{}}",
                "{\"evidence\":{\"raw\":1,\"raw\":2}}",
                "{\"receipt_locator\":\"a\",\"receipt_locator\":\"b\"}",
                "{\"ledger_identity\":\"a\",\"ledger_identity\":\"b\"}",
                "{\"trust_identity\":\"a\",\"trust_identity\":\"b\"}",
                "{\"case_identity\":\"a\",\"case_identity\":\"b\"}",
                "{\"expectation_identity\":\"a\",\"expectation_identity\":\"b\"}"
            };
            string[] duplicateNames = new string[] { "operation", "nonce", "version", "payload", "nested_evidence", "receipt_locator", "ledger_identity", "trust_identity", "case_identity", "expectation_identity" };
            for (int i = 0; i < duplicatePayloads.Length; i++) if (Reject(Encoding.UTF8.GetBytes(duplicatePayloads[i]), "DUPLICATE_KEY", duplicateNames[i], results)) passed++;
            if (Reject(Encoding.UTF8.GetBytes("{}{}"), "TRAILING_JSON", "two_objects", results)) passed++;
            if (Reject(Encoding.UTF8.GetBytes("{}x"), "TRAILING_JSON", "trailing_json", results)) passed++;
            if (Reject(new byte[] { 0x7b, 0x22, 0x78, 0x22, 0x3a, 0x22, 0xc3, 0x28, 0x22, 0x7d }, "INVALID_UTF8", "invalid_utf8", results)) passed++;
            if (Reject(Encoding.UTF8.GetBytes("{\"x\":\"e\\u0301\"}"), "NON_CANONICAL_UNICODE", "unicode_normalization", results)) passed++;
            if (Reject(Encoding.UTF8.GetBytes("{\"n\":1.0}"), "NON_INTEGER_NUMBER", "strict_number", results)) passed++;
            if (RejectSchema("{\"sequence\":\"1\"}", delegate(SortedDictionary<string, object> value) { R7Json.Integer(value, "sequence", 0, 10); }, "TYPE_MISMATCH", "numeric_string", results)) passed++;
            if (RejectSchema("{\"identity\":null}", delegate(SortedDictionary<string, object> value) { R7Json.String(value, "identity", 1, 10); }, "NULL_NOT_ALLOWED", "null_not_absent", results)) passed++;
            if (RejectSchema("{\"a\":1,\"b\":2}", delegate(SortedDictionary<string, object> value) { R7Json.ExactKeys(value, "a"); }, "SCHEMA_KEY_COUNT", "unknown_field", results)) passed++;

            SortedDictionary<string, object> exact = R7Json.Object("x", new string('A', R7Fixed.MaximumPayloadBytes - 8));
            byte[] exactPayload = R7Json.Encode(exact);
            byte[] exactFrame = R7Framing.Encode(exact);
            bool exactPass = exactPayload.Length == R7Fixed.MaximumPayloadBytes && R7Framing.Decode(exactFrame).Count == 1;
            results.Add(Result("exact_65536", exactPass, exactPayload.Length.ToString(CultureInfo.InvariantCulture)));
            if (exactPass) passed++;
            bool overPass = false;
            try { R7Framing.Encode(R7Json.Object("x", new string('A', R7Fixed.MaximumPayloadBytes - 7))); }
            catch (R7ProtocolException exception) { overPass = exception.Code == "FRAME_TOO_LARGE"; }
            results.Add(Result("one_byte_over", overPass, "FRAME_TOO_LARGE"));
            if (overPass) passed++;
            bool partialPass = false;
            try { R7Framing.Decode(new byte[11]); } catch (R7ProtocolException exception) { partialPass = exception.Code == "PARTIAL_FRAME"; }
            results.Add(Result("partial_frame", partialPass, "PARTIAL_FRAME"));
            if (partialPass) passed++;
            byte[] valid = R7Framing.Encode(R7Json.Object("a", 1L));
            byte[] multiple = new byte[valid.Length * 2];
            Buffer.BlockCopy(valid, 0, multiple, 0, valid.Length);
            Buffer.BlockCopy(valid, 0, multiple, valid.Length, valid.Length);
            bool multiplePass = false;
            try { R7Framing.Decode(multiple); } catch (R7ProtocolException exception) { multiplePass = exception.Code == "FRAME_LENGTH_MISMATCH"; }
            results.Add(Result("multiple_frames", multiplePass, "FRAME_LENGTH_MISMATCH"));
            if (multiplePass) passed++;

            int total = results.Count;
            return R7Json.Object(
                "artifact_type", "R7_STATIC_STRICT_PROTOCOL_VERIFICATION",
                "failed", (long)(total - passed),
                "passed", (long)passed,
                "results", results.ToArray(),
                "schema_version", "1.0.0",
                "status", passed == total ? "PASS" : "FAIL",
                "total", (long)total);
        }

        private static SortedDictionary<string, object> LegacyVerification(string ledgerRoot, string certificatePath, long expectedSequence)
        {
            string certificateHash;
            X509Certificate2 certificate;
            using (R7VerifiedFile file = R7SafeFile.Open(Path.GetFullPath(certificatePath), Path.GetFullPath(certificatePath), Path.GetDirectoryName(Path.GetFullPath(certificatePath)), null, null, null, null))
            {
                certificateHash = file.Measurement.Sha256;
                certificate = new X509Certificate2(file.Bytes);
            }
            using (certificate)
            using (RSA verifier = RSACertificateExtensions.GetRSAPublicKey(certificate))
            {
                R7VersionedLedger ledger = new R7VersionedLedger(Path.GetFullPath(ledgerRoot), R7Fixed.LedgerId, certificateHash, R7Fixed.TerminalSid, null, verifier);
                bool pass = ledger.Sequence == expectedSequence;
                return R7Json.Object(
                    "artifact_type", "R7_REMEDIATION_LEGACY_LEDGER_VERIFICATION",
                    "checkpoint_recovery_reason", ledger.CheckpointRecoveryReason,
                    "ledger_root", ledger.RootHash,
                    "ledger_sequence", ledger.Sequence,
                    "public_key_identity", certificateHash,
                    "schema_version", "1.0.0",
                    "status", pass ? "PASS" : "FAIL");
            }
        }

        private static SortedDictionary<string, object> TransactionVerification(string outputRoot)
        {
            string root = Path.GetFullPath(outputRoot);
            if (Directory.Exists(root) && Directory.GetFileSystemEntries(root).Length != 0) throw new IOException("isolated output root must be absent or empty");
            Directory.CreateDirectory(root);
            string ledgerRoot = Make(root, "Ledger");
            string objectRoot = Make(root, "Objects");
            string receiptRoot = Make(root, "Receipts");
            string responseRoot = Make(root, "Responses");
            using (RSACng key = new RSACng(3072))
            {
                RSAParameters publicParameters = key.ExportParameters(false);
                string publicIdentity = R7Hash.Bytes(Join(publicParameters.Modulus, publicParameters.Exponent));
                string ledgerIdentity = R7Hash.Bytes(Encoding.UTF8.GetBytes("STATIC_TRANSACTION_TEST|" + root));
                string genesis = R7Hash.Bytes(Encoding.UTF8.GetBytes("GENESIS|" + ledgerIdentity + "|" + publicIdentity));
                R7VersionedLedger ledger = new R7VersionedLedger(ledgerRoot, ledgerIdentity, publicIdentity, R7Fixed.TerminalSid, key, key, true, genesis);
                R7ObjectStore objects = new R7ObjectStore(objectRoot);
                R7TransactionManager manager = new R7TransactionManager(ledger, objects, key, publicIdentity, receiptRoot, responseRoot, "TEST-1.0.0", String.Empty);
                string requestIdentity = Guid.NewGuid().ToString("D");
                string requestHash = R7Hash.Bytes(Encoding.UTF8.GetBytes("STATIC_REQUEST"));
                SortedDictionary<string, object> first = manager.Execute(requestIdentity, requestHash, "STATIC_TEST", delegate()
                {
                    string evidenceIdentity = objects.Put(R7Json.Object("raw", "STATIC_CURRENT_RUN"));
                    return new R7PreparedTransaction(
                        R7Json.Object("evidence_identity", evidenceIdentity, "receipt_type", "STATIC_TEST_RECEIPT", "request_identity", requestIdentity, "terminal_classification", "ISOLATED_NONAUTHORITY_TEST"),
                        R7PipeWindowsService.Success("STATIC_COMMITTED"),
                        evidenceIdentity,
                        "ISOLATED_NONAUTHORITY_TEST");
                });
                byte[] firstFrame = R7Framing.Encode(first);
                SortedDictionary<string, object> retry = manager.Execute(requestIdentity, requestHash, "STATIC_TEST", delegate() { throw new InvalidOperationException("prepare called on idempotent retry"); });
                byte[] retryFrame = R7Framing.Encode(retry);
                bool conflict = false;
                try { manager.Execute(requestIdentity, new string('0', 64), "STATIC_TEST", delegate() { return null; }); }
                catch (R7ProtocolException exception) { conflict = exception.Code == "REQUEST_IDENTITY_CONFLICT"; }
                string faultedRequestIdentity = Guid.NewGuid().ToString("D");
                string faultedRequestHash = R7Hash.Bytes(Encoding.UTF8.GetBytes("STATIC_POST_COMMIT_FAULT"));
                R7TransactionManager postCommitFault = new R7TransactionManager(ledger, objects, key, publicIdentity, receiptRoot, responseRoot, "TEST-1.0.0", "AFTER_COMMIT_APPEND");
                SortedDictionary<string, object> postCommitResponse = postCommitFault.Execute(faultedRequestIdentity, faultedRequestHash, "STATIC_POST_COMMIT_FAULT", delegate()
                {
                    string evidenceIdentity = objects.Put(R7Json.Object("raw", "STATIC_POST_COMMIT_CURRENT_RUN"));
                    return new R7PreparedTransaction(
                        R7Json.Object("evidence_identity", evidenceIdentity, "receipt_type", "STATIC_POST_COMMIT_RECEIPT", "request_identity", faultedRequestIdentity, "terminal_classification", "ISOLATED_NONAUTHORITY_TEST"),
                        R7PipeWindowsService.Success("STATIC_POST_COMMIT_RECONSTRUCTED"),
                        evidenceIdentity,
                        "ISOLATED_NONAUTHORITY_TEST");
                });
                bool postCommitFaultNotRejected = R7Json.String(postCommitResponse, "status", 1, 64) == "COMPLETE" && postCommitFault.Find(faultedRequestIdentity).State == "RESPONSE_AVAILABLE";
                R7VersionedLedger restartedLedger = new R7VersionedLedger(ledgerRoot, ledgerIdentity, publicIdentity, R7Fixed.TerminalSid, key, key);
                R7TransactionManager restarted = new R7TransactionManager(restartedLedger, new R7ObjectStore(objectRoot), key, publicIdentity, receiptRoot, responseRoot, "TEST-1.0.0", String.Empty);
                byte[] restartedFrame = R7Framing.Encode(restarted.Reconstruct(requestIdentity));
                bool stable = R7Hash.FixedTimeEquals(R7Hash.Bytes(firstFrame), R7Hash.Bytes(retryFrame)) && R7Hash.FixedTimeEquals(R7Hash.Bytes(firstFrame), R7Hash.Bytes(restartedFrame));
                R7TransactionSnapshot snapshot = restarted.Find(requestIdentity);
                bool pass = stable && conflict && postCommitFaultNotRejected && snapshot != null && snapshot.State == "RESPONSE_AVAILABLE";
                return R7Json.Object(
                    "artifact_type", "R7_STATIC_TRANSACTION_VERIFICATION",
                    "conflicting_retry_rejected", conflict,
                    "final_ledger_root", restartedLedger.RootHash,
                    "final_ledger_sequence", restartedLedger.Sequence,
                    "final_state", snapshot == null ? "MISSING" : snapshot.State,
                    "post_commit_fault_not_reported_as_rejection", postCommitFaultNotRejected,
                    "request_identity", requestIdentity,
                    "response_frame_sha256", R7Hash.Bytes(firstFrame),
                    "response_reconstruction_byte_identical", stable,
                    "schema_version", "1.0.0",
                    "status", pass ? "PASS" : "FAIL");
            }
        }

        private static SortedDictionary<string, object> RecoveryVerification(string outputRoot)
        {
            string root = Path.GetFullPath(outputRoot);
            string temporaryRoot = Path.GetFullPath(Path.GetTempPath()).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            if (!root.StartsWith(temporaryRoot, StringComparison.OrdinalIgnoreCase) || root.IndexOf(Path.DirectorySeparatorChar + "R7StaticIsolatedTests", StringComparison.OrdinalIgnoreCase) < 0) throw new IOException("offline recovery root must be a marked temporary path");
            if (Directory.Exists(root) && Directory.GetFileSystemEntries(root).Length != 0) throw new IOException("offline recovery root must be absent or empty");
            Directory.CreateDirectory(root);
            string[] faultPoints = new string[]
            {
                "BEFORE_RESERVATION", "AFTER_RESERVATION", "AFTER_EVIDENCE_VALIDATION", "AFTER_RECEIPT_PREPARATION", "AFTER_RECEIPT_STORAGE", "AFTER_COMMIT_APPEND",
                "BEFORE_CHECKPOINT_UPDATE", "DURING_CHECKPOINT_UPDATE", "AFTER_CHECKPOINT_BEFORE_RESPONSE", "DURING_RECONCILIATION", "DURING_ABORT_OR_SUPERSESSION",
                "DURING_RESTART_RECOVERY", "DISK_FULL", "ACCESS_DENIED", "PARTIAL_WRITE", "PARENT_DIRECTORY_PERSISTENCE_FAILURE", "CLIENT_DISCONNECT_AFTER_COMMIT",
                "STALE_CHECKPOINT", "PARTIAL_CHECKPOINT", "RESPONSE_NO_COMMIT", "RECONCILIATION_UNCOMMITTED", "INCOMPLETE_RESERVATION", "DUPLICATE_COMPLETION", "CONFLICTING_SUPERSESSION"
            };
            List<object> results = new List<object>();
            for (int index = 0; index < faultPoints.Length; index++)
            {
                string faultPoint = faultPoints[index];
                string probeRoot = Path.Combine(root, index.ToString("D2", CultureInfo.InvariantCulture) + "_" + faultPoint);
                SortedDictionary<string, object> producerResult = R7RecoveryProbeEngine.ExecuteOffline(probeRoot, faultPoint);
                string resultIdentity = R7Hash.Bytes(R7Json.Encode(producerResult));
                SortedDictionary<string, object> audit = R7RecoveryProbeAuditor.VerifyOffline(probeRoot, faultPoint, resultIdentity);
                if (R7Json.String(audit, "status", 1, 32) != "PASS") throw new InvalidDataException("OFFLINE_RECOVERY_AUDIT_FAILED:" + faultPoint);
                results.Add(R7Json.Object(
                    "derived_result_code", R7Json.String(audit, "derived_result_code", 1, 256),
                    "fault_point", faultPoint,
                    "result_identity", resultIdentity,
                    "status", "PASS"));
            }
            return R7Json.Object(
                "artifact_type", "R7_STATIC_ISOLATED_RECOVERY_ALGORITHM_VERIFICATION",
                "authority_classification", "DISPOSABLE_TEMPORARY_NONAUTHORITY_TEST",
                "fault_point_count", (long)faultPoints.Length,
                "results", results.ToArray(),
                "schema_version", "1.0.0",
                "status", results.Count == faultPoints.Length ? "PASS" : "FAIL");
        }

        private static bool Reject(byte[] json, string expected, string name, List<object> results)
        {
            string actual = "ACCEPTED";
            try { R7Json.Parse(json); }
            catch (R7ProtocolException exception) { actual = exception.Code; }
            bool pass = actual == expected;
            results.Add(Result(name, pass, actual));
            return pass;
        }

        private static bool RejectSchema(string json, Action<SortedDictionary<string, object>> action, string expected, string name, List<object> results)
        {
            string actual = "ACCEPTED";
            try { action((SortedDictionary<string, object>)R7Json.Parse(Encoding.UTF8.GetBytes(json))); }
            catch (R7ProtocolException exception) { actual = exception.Code; }
            bool pass = actual == expected;
            results.Add(Result(name, pass, actual));
            return pass;
        }

        private static SortedDictionary<string, object> Result(string name, bool pass, string actual)
        {
            return R7Json.Object("actual", actual, "name", name, "status", pass ? "PASS" : "FAIL");
        }

        private static string Make(string root, string name) { string path = Path.Combine(root, name); Directory.CreateDirectory(path); return path; }
        private static byte[] Join(byte[] left, byte[] right) { byte[] value = new byte[left.Length + right.Length]; Buffer.BlockCopy(left, 0, value, 0, left.Length); Buffer.BlockCopy(right, 0, value, left.Length, right.Length); return value; }
    }
}
