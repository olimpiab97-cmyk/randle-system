using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using System.Text.RegularExpressions;

namespace RandleAI.TerminalAuthority
{
    internal static class R7VerifierBuildConstants
    {
        internal const string ServiceSha256 = "9ea829416f37c94db2858586fa5e0042652f6caa4637a29fdbefb513577a7526";
        internal const string WorkerSha256 = "b2971b85de73d999bfa801d047b22c2ec6fc3d6bc5cb5923ea4a9ab240ed4401";
        internal const string PolicySha256 = "76eb2900b2000aa0b41e6040335cc323f7443728aad21cd871d5b6b8e17bcd8b";
    }

    internal sealed class R7VerifiedTerminal
    {
        internal string AttemptId;
        internal string Configuration;
        internal string EventRoot;
        internal string Locator;
        internal string Phase;
        internal string ReceiptIdentity;
        internal string RunId;
        internal string RunNonce;
        internal readonly HashSet<string> ProcessIdentities = new HashSet<string>(StringComparer.Ordinal);
        internal IDictionary<string, object> Payload;
    }

    internal static class R7PublicVerifier
    {
        private static X509Certificate2 certificate;
        private static RSA publicKey;

        private static int Main(string[] args)
        {
            try
            {
                InitializeTrust();
                if (args.Length == 1 && String.Equals(args[0], "verify-ledger", StringComparison.Ordinal))
                {
                    R7LedgerState state = R7Support.VerifyLedger(publicKey);
                    Emit("R7_PUBLIC_LEDGER_VERIFIED", state.Sequence, state.RootHash, state.CheckpointIdentity);
                }
                else if (args.Length == 2 && String.Equals(args[0], "verify-terminal", StringComparison.Ordinal))
                {
                    R7VerifiedTerminal terminal = VerifyTerminal(args[1]);
                    R7LedgerState state = R7Support.VerifyLedger(publicKey);
                    Emit("R7_PUBLIC_TERMINAL_VERIFIED", state.Sequence, state.RootHash, terminal.ReceiptIdentity);
                }
                else if (args.Length == 2 && String.Equals(args[0], "verify-reconciliation", StringComparison.Ordinal))
                {
                    string identity = VerifyReconciliation(args[1]);
                    R7LedgerState state = R7Support.VerifyLedger(publicKey);
                    Emit("R7_PUBLIC_RECONCILIATION_VERIFIED", state.Sequence, state.RootHash, identity);
                }
                else if (args.Length == 1 && String.Equals(args[0], "verify-all", StringComparison.Ordinal))
                {
                    R7LedgerState state = R7Support.VerifyLedger(publicKey);
                    foreach (string path in Directory.GetFiles(R7Constants.ReceiptRoot, "*.json", SearchOption.TopDirectoryOnly))
                        VerifyTerminal(R7Support.ContentLocator("terminal", Path.GetFileNameWithoutExtension(path)));
                    foreach (string path in Directory.GetFiles(R7Constants.ReconciliationRoot, "*.json", SearchOption.TopDirectoryOnly))
                        VerifyReconciliation(R7Support.ContentLocator("reconciliation", Path.GetFileNameWithoutExtension(path)));
                    Emit("R7_PUBLIC_ALL_VERIFIED", state.Sequence, state.RootHash, state.CheckpointIdentity);
                }
                else throw new InvalidDataException("public verifier arguments rejected");
                return 0;
            }
            catch (Exception exception)
            {
                Console.Error.WriteLine(exception.GetType().Name + ": " + exception.Message);
                return 2;
            }
            finally
            {
                if (publicKey != null) publicKey.Dispose();
                if (certificate != null) certificate.Dispose();
            }
        }

        private static void InitializeTrust()
        {
            byte[] bytes = File.ReadAllBytes(AuthorityConstants.PublicCertificatePath);
            if (!String.Equals(CryptoUtil.Sha256Hex(bytes), R7Constants.PublicKeyIdentity, StringComparison.Ordinal)) throw new CryptographicException("public trust identity rejected");
            certificate = new X509Certificate2(bytes);
            if (!String.Equals(certificate.Thumbprint, AuthorityConstants.CertificateThumbprint, StringComparison.OrdinalIgnoreCase) || certificate.HasPrivateKey || certificate.GetRSAPublicKey().KeySize != 3072)
                throw new CryptographicException("public trust certificate rejected");
            publicKey = System.Security.Cryptography.X509Certificates.RSACertificateExtensions.GetRSAPublicKey(certificate);
            R7Support.ReadPinnedBytes(R7Constants.CaseDefinitionPath, R7Constants.CaseDefinitionSha256, R7Constants.CaseDefinitionGitBlob, R7Constants.CaseDefinitionSize);
            R7Support.ReadPinnedBytes(R7Constants.ExpectationPath, R7Constants.ExpectationSha256, R7Constants.ExpectationGitBlob, R7Constants.ExpectationSize);
            R7Support.ReadPinnedBytes(R7Constants.CorrectionRequirementsPath, R7Constants.CorrectionRequirementsSha256, R7Constants.CorrectionRequirementsGitBlob, R7Constants.CorrectionRequirementsSize);
        }

        private static R7VerifiedTerminal VerifyTerminal(string locator)
        {
            string identity = R7Support.ParseLocator(locator, "terminal");
            IDictionary<string, object> payload = R7Support.VerifySignedEnvelope(R7Support.ReadContentAddressed(locator, "terminal"), publicKey);
            if (!String.Equals(StrictJson.RequireString(payload, "artifact_type"), "R7_SIGNED_TERMINAL_RECEIPT", StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "terminal_verifier_result"), "SEMANTICALLY_VERIFIED", StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "case_definition_git_blob"), R7Constants.CaseDefinitionGitBlob, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "case_definition_sha256"), R7Constants.CaseDefinitionSha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "expectation_git_blob"), R7Constants.ExpectationGitBlob, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "expectation_sha256"), R7Constants.ExpectationSha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "policy_sha256"), R7VerifierBuildConstants.PolicySha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "service_binary_sha256"), R7VerifierBuildConstants.ServiceSha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "worker_sha256"), R7VerifierBuildConstants.WorkerSha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "subject_commit"), R7Constants.SubjectCommit, StringComparison.Ordinal) ||
                R7Support.RequireLong(payload, "case_count") != R7Constants.RequiredCaseCount)
                throw new InvalidDataException("terminal fixed authority rejected");
            string runId = R7Support.RequireLowerHex(payload, "run_id", 64);
            string runNonce = R7Support.RequireLowerHex(payload, "run_nonce", 64);
            string attemptId = R7Support.RequireLowerHex(payload, "attempt_id", 64);
            string phase = R7Support.RequireEnum(payload, "phase", "CANDIDATE", "FRESH");
            string configuration = StrictJson.RequireString(payload, "configuration");
            SortedDictionary<string, object> claimBase = new SortedDictionary<string, object>(payload, StringComparer.Ordinal);
            string claim = StrictJson.RequireString(claimBase, "terminal_claim_identity");
            claimBase.Remove("ledger_reservation_entry_identity");
            claimBase.Remove("ledger_reservation_prior_root");
            claimBase.Remove("ledger_reservation_sequence");
            claimBase.Remove("terminal_claim_identity");
            if (!String.Equals(claim, CryptoUtil.Sha256Hex(CanonicalJson.SerializeBytes(claimBase)), StringComparison.Ordinal)) throw new InvalidDataException("terminal claim identity rejected");
            R7LedgerState ledger = R7Support.VerifyLedger(publicKey);
            IDictionary<string, object> commit = R7Support.FindLedgerEntry(ledger, "R7_TERMINAL_RECEIPT_COMMITTED", identity);
            if (!String.Equals(StrictJson.RequireString(commit, "subject_id"), runId, StringComparison.Ordinal)) throw new InvalidDataException("terminal ledger subject rejected");
            string reservationIdentity = StrictJson.RequireString(payload, "ledger_reservation_entry_identity");
            IDictionary<string, object> reservation = FindEntryByIdentity(ledger, reservationIdentity);
            if (!String.Equals(StrictJson.RequireString(reservation, "operation"), "R7_TERMINAL_RESERVED", StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(reservation, "subject_id"), runId, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(reservation, "content_address"), claim, StringComparison.Ordinal) ||
                R7Support.RequireLong(reservation, "sequence") != R7Support.RequireLong(payload, "ledger_reservation_sequence")) throw new InvalidDataException("terminal reservation rejected");

            string eventLocator = StrictJson.RequireString(payload, "event_source_locator");
            string observationLocator = StrictJson.RequireString(payload, "observation_locator");
            string traceLocator = StrictJson.RequireString(payload, "traceability_locator");
            string comparisonLocator = StrictJson.RequireString(payload, "comparator_result_locator");
            string processIndexLocator = StrictJson.RequireString(payload, "process_index_locator");
            IDictionary<string, object> eventSource = ReadEvidence(eventLocator);
            IDictionary<string, object> observationSource = ReadEvidence(observationLocator);
            IDictionary<string, object> traceSource = ReadEvidence(traceLocator);
            IDictionary<string, object> comparison = ReadEvidence(comparisonLocator);
            IDictionary<string, object> processIndex = ReadEvidence(processIndexLocator);
            if (!String.Equals(StrictJson.RequireString(eventSource, "run_id"), runId, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(observationSource, "run_id"), runId, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(traceSource, "run_id"), runId, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(comparison, "run_id"), runId, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(processIndex, "run_id"), runId, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(comparison, "conformity"), "CONFORMANT", StringComparison.Ordinal) ||
                R7Support.RequireLong(comparison, "discrepancy_count") != 0) throw new InvalidDataException("terminal child run rejected");
            VerifyEvents(runId, eventSource, observationSource, traceSource, processIndex, ledger);
            if (!String.Equals(StrictJson.RequireString(eventSource, "event_root"), StrictJson.RequireString(payload, "event_root"), StringComparison.Ordinal)) throw new InvalidDataException("terminal event root rejected");

            R7VerifiedTerminal terminal = new R7VerifiedTerminal();
            terminal.AttemptId = attemptId;
            terminal.Configuration = configuration;
            terminal.EventRoot = StrictJson.RequireString(eventSource, "event_root");
            terminal.Locator = locator;
            terminal.Phase = phase;
            terminal.ReceiptIdentity = identity;
            terminal.RunId = runId;
            terminal.RunNonce = runNonce;
            terminal.Payload = payload;
            VerifyProcesses(processIndex, runId, ledger, terminal.ProcessIdentities);
            return terminal;
        }

        private static void VerifyEvents(string runId, IDictionary<string, object> source, IDictionary<string, object> observationSource,
            IDictionary<string, object> traceSource, IDictionary<string, object> processIndex, R7LedgerState ledger)
        {
            object[] events = R7Support.RequireArray(source, "events");
            object[] observations = R7Support.RequireArray(observationSource, "observations");
            object[] traces = R7Support.RequireArray(traceSource, "rows");
            object[] caseRows = R7Support.RequireArray(R7Support.ReadCaseAuthority(), "cases");
            object[] expectationRows = R7Support.RequireArray(R7Support.ReadExpectationAuthority(), "expectations");
            if (events.Length != R7Constants.RequiredCaseCount || observations.Length != events.Length || traces.Length != events.Length || caseRows.Length != events.Length || expectationRows.Length != events.Length)
                throw new InvalidDataException("terminal coverage rejected");
            Dictionary<string, IDictionary<string, object>> expected = Index(expectationRows);
            Dictionary<string, IDictionary<string, object>> definitions = Index(caseRows);
            Dictionary<string, IDictionary<string, object>> observed = Index(observations);
            Dictionary<string, IDictionary<string, object>> trace = Index(traces);
            HashSet<string> governed = new HashSet<string>(caseRows.Cast<IDictionary<string, object>>().Select(delegate(IDictionary<string, object> row) { return StrictJson.RequireString(row, "case_id"); }), StringComparer.Ordinal);
            HashSet<string> seen = new HashSet<string>(StringComparer.Ordinal);
            string suiteLocator = StrictJson.RequireString(processIndex, "suite_process_receipt_locator");
            string suiteIdentity = R7Support.ParseLocator(suiteLocator, "evidence");
            IDictionary<string, object> suiteReceipt = R7Support.VerifySignedEnvelope(R7Support.ReadContentAddressed(suiteLocator, "evidence"), publicKey);
            R7Support.FindLedgerEntry(ledger, "R7_REAL_SUITE_PROCESS_COMPLETED", suiteIdentity);
            string prior = R7Constants.ZeroHash;
            foreach (object raw in events)
            {
                IDictionary<string, object> current = (IDictionary<string, object>)raw;
                string caseId = StrictJson.RequireString(current, "case_id");
                if (!seen.Add(caseId) || !governed.Contains(caseId) || !expected.ContainsKey(caseId) || !observed.ContainsKey(caseId) || !trace.ContainsKey(caseId)) throw new InvalidDataException("terminal case set rejected");
                if (!String.Equals(StrictJson.RequireString(current, "run_id"), runId, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "prior_event_hash"), prior, StringComparison.Ordinal) ||
                    !R7Support.RequireBool(current, "interface_invoked") || !R7Support.RequireBool(current, "forbidden_side_effect_absent") ||
                    R7Support.RequireLong(current, "outer_post_ledger_sequence") != R7Support.RequireLong(current, "outer_pre_ledger_sequence") ||
                    R7Support.RequireLong(current, "subject_event_ledger_delta") < 1 ||
                    !String.Equals(StrictJson.RequireString(current, "case_definition_git_blob"), R7Constants.CaseDefinitionGitBlob, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "expectation_git_blob"), R7Constants.ExpectationGitBlob, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "interface_identity"), R7Constants.SubjectDirectInterfaceSha256, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "interface_operation"), "execute_case", StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "subject_service_sha256"), R7Constants.SubjectServiceSha256, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "target_process_binary_sha256"), R7Constants.SubjectPythonSha256, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "invoking_process_receipt_identity"), suiteIdentity, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "event_constructor_binary_sha256"), R7VerifierBuildConstants.ServiceSha256, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "suite_process_receipt_locator"), suiteLocator, StringComparison.Ordinal))
                    throw new InvalidDataException("terminal current execution rejected");
                IDictionary<string, object> wanted = expected[caseId];
                if (!String.Equals(StrictJson.RequireString(current, "public_interface"), StrictJson.RequireString(wanted, "expected_interface"), StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "actual_outcome"), StrictJson.RequireString(wanted, "expected_outcome"), StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "response_classification"), StrictJson.RequireString(wanted, "expected_response_classification"), StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "enforcing_function"), StrictJson.RequireString(wanted, "expected_enforcing_function"), StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "actual_authority_identity"), StrictJson.RequireString(wanted, "expected_authority_source"), StringComparison.Ordinal))
                    throw new InvalidDataException("terminal independent expectation rejected");
                byte[] requestBytes = R7Support.ReadContentAddressed(StrictJson.RequireString(current, "public_request_locator"), "evidence");
                byte[] responseBytes = R7Support.ReadContentAddressed(StrictJson.RequireString(current, "public_response_locator"), "evidence");
                if (!String.Equals(CryptoUtil.Sha256Hex(requestBytes), StrictJson.RequireString(current, "request_sha256"), StringComparison.Ordinal) ||
                    !String.Equals(CryptoUtil.Sha256Hex(responseBytes), StrictJson.RequireString(current, "response_sha256"), StringComparison.Ordinal)) throw new InvalidDataException("terminal request response identity rejected");
                IDictionary<string, object> request = R7Support.ParseCanonicalObject(requestBytes);
                IDictionary<string, object> response = R7Support.ParseCanonicalObject(responseBytes);
                if (!String.Equals(StrictJson.RequireString(request, "case_id"), caseId, StringComparison.Ordinal) || !String.Equals(StrictJson.RequireString(request, "operation"), "execute_case", StringComparison.Ordinal) || !String.Equals(StrictJson.RequireString(response, "status"), "OK", StringComparison.Ordinal)) throw new InvalidDataException("terminal public interface bytes rejected");
                IDictionary<string, object> result = StrictJson.RequireObject(response, "result");
                IDictionary<string, object> outcome = StrictJson.RequireObject(result, "outcome");
                IDictionary<string, object> innerEvent = StrictJson.RequireObject(result, "event");
                IDictionary<string, object> executionReceipt = StrictJson.RequireObject(result, "execution_receipt");
                if (!String.Equals(StrictJson.RequireString(result, "case_id"), caseId, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(outcome, "status"), StrictJson.RequireString(current, "actual_outcome"), StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(outcome, "code"), StrictJson.RequireString(current, "response_classification"), StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(outcome, "enforcing_function"), StrictJson.RequireString(current, "enforcing_function"), StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(outcome, "authority_identity"), StrictJson.RequireString(current, "actual_authority_identity"), StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(innerEvent, "event_hash"), StrictJson.RequireString(current, "inner_event_hash"), StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(executionReceipt, "receipt_identity"), StrictJson.RequireString(current, "inner_execution_receipt_identity"), StringComparison.Ordinal))
                    throw new InvalidDataException("terminal response derivation rejected");
                if (!String.Equals(StrictJson.RequireString(observed[caseId], "event_hash"), StrictJson.RequireString(current, "event_hash"), StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(observed[caseId], "actual_outcome"), StrictJson.RequireString(current, "actual_outcome"), StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(observed[caseId], "response_classification"), StrictJson.RequireString(current, "response_classification"), StringComparison.Ordinal) ||
                    !R7Support.RequireBool(observed[caseId], "interface_invoked") || !R7Support.RequireBool(observed[caseId], "forbidden_side_effect_absent") ||
                    R7Support.RequireLong(observed[caseId], "outer_ledger_delta") != 0 || R7Support.RequireLong(observed[caseId], "subject_event_ledger_delta") < 1 ||
                    !String.Equals(StrictJson.RequireString(trace[caseId], "event_hash"), StrictJson.RequireString(current, "event_hash"), StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(trace[caseId], "case_definition_git_blob"), R7Constants.CaseDefinitionGitBlob, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(trace[caseId], "expectation_git_blob"), R7Constants.ExpectationGitBlob, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(trace[caseId], "public_interface"), StrictJson.RequireString(current, "public_interface"), StringComparison.Ordinal))
                    throw new InvalidDataException("terminal observation or trace rejected");
                VerifyFixtureProcessEvidence(runId, definitions[caseId], current, observed[caseId], suiteReceipt);
                SortedDictionary<string, object> core = new SortedDictionary<string, object>(current, StringComparer.Ordinal);
                string recorded = StrictJson.RequireString(core, "event_hash");
                core.Remove("event_hash");
                if (!String.Equals(recorded, CryptoUtil.Sha256Hex(CanonicalJson.SerializeBytes(core)), StringComparison.Ordinal)) throw new InvalidDataException("terminal event hash rejected");
                prior = recorded;
            }
            if (seen.Count != R7Constants.RequiredCaseCount || !String.Equals(prior, StrictJson.RequireString(source, "event_root"), StringComparison.Ordinal)) throw new InvalidDataException("terminal event chain rejected");
        }

        private static void VerifyFixtureProcessEvidence(string runId, IDictionary<string, object> definition,
            IDictionary<string, object> current, IDictionary<string, object> observed, IDictionary<string, object> suiteReceipt)
        {
            bool required = StrictJson.RequireString(StrictJson.RequireObject(definition, "source_case"), "mutation").StartsWith("reparse_substitution_", StringComparison.Ordinal);
            bool invoked = R7Support.RequireBool(current, "fixture_helper_invoked");
            if (invoked != R7Support.RequireBool(observed, "fixture_helper_invoked")) throw new InvalidDataException("public fixture observation binding rejected");
            int expectedCount = 0;
            foreach (object raw in R7Support.RequireArray(R7Support.ReadCaseAuthority(), "cases"))
            {
                IDictionary<string, object> row = raw as IDictionary<string, object>;
                if (row != null && StrictJson.RequireString(StrictJson.RequireObject(row, "source_case"), "mutation").StartsWith("reparse_substitution_", StringComparison.Ordinal)) expectedCount++;
            }
            if (!String.Equals(StrictJson.RequireString(suiteReceipt, "fixture_host_sha256"), R7Constants.SubjectFixtureHostSha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(suiteReceipt, "fixture_host_file_identity"), R7FileIdentity.Get(R7Constants.SubjectFixtureHostPath), StringComparison.Ordinal) ||
                !String.Equals(CryptoUtil.Sha256File(R7Constants.SubjectFixtureHostPath), R7Constants.SubjectFixtureHostSha256, StringComparison.Ordinal) ||
                R7Support.RequireLong(suiteReceipt, "fixture_process_receipt_count") != expectedCount)
                throw new InvalidDataException("public fixture suite measurement rejected");
            if (!required)
            {
                if (invoked || !String.Equals(StrictJson.RequireString(current, "fixture_body_identity"), R7Constants.ZeroHash, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "fixture_helper_file_identity"), String.Empty, StringComparison.Ordinal) ||
                    R7Support.RequireLong(current, "fixture_helper_process_id") != 0 ||
                    !String.Equals(StrictJson.RequireString(current, "fixture_process_receipt_identity"), R7Constants.ZeroHash, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "fixture_process_receipt_locator"), String.Empty, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "fixture_reparse_snapshot_identity"), R7Constants.ZeroHash, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "fixture_reparse_snapshot_locator"), String.Empty, StringComparison.Ordinal))
                    throw new InvalidDataException("public unexpected fixture evidence rejected");
                return;
            }
            if (!invoked) throw new InvalidDataException("public required fixture evidence missing");
            string locator = StrictJson.RequireString(current, "fixture_process_receipt_locator");
            string identity = R7Support.ParseLocator(locator, "evidence");
            string snapshotLocator = StrictJson.RequireString(current, "fixture_reparse_snapshot_locator");
            string snapshotIdentity = R7Support.ParseLocator(snapshotLocator, "evidence");
            if (!String.Equals(identity, StrictJson.RequireString(current, "fixture_process_receipt_identity"), StringComparison.Ordinal) ||
                !String.Equals(identity, StrictJson.RequireString(observed, "fixture_process_receipt_identity"), StringComparison.Ordinal) ||
                !String.Equals(locator, StrictJson.RequireString(observed, "fixture_process_receipt_locator"), StringComparison.Ordinal) ||
                !String.Equals(snapshotIdentity, StrictJson.RequireString(current, "fixture_reparse_snapshot_identity"), StringComparison.Ordinal) ||
                !String.Equals(snapshotIdentity, StrictJson.RequireString(observed, "fixture_reparse_snapshot_identity"), StringComparison.Ordinal) ||
                !String.Equals(snapshotLocator, StrictJson.RequireString(observed, "fixture_reparse_snapshot_locator"), StringComparison.Ordinal) ||
                R7Support.RequireArray(current, "raw_evidence_locators").Count(delegate(object value) { return String.Equals(value as string, locator, StringComparison.Ordinal); }) != 1 ||
                R7Support.RequireArray(observed, "evidence_citations").Count(delegate(object value) { return String.Equals(value as string, locator, StringComparison.Ordinal); }) != 1 ||
                R7Support.RequireArray(current, "raw_evidence_locators").Count(delegate(object value) { return String.Equals(value as string, snapshotLocator, StringComparison.Ordinal); }) != 1 ||
                R7Support.RequireArray(observed, "evidence_citations").Count(delegate(object value) { return String.Equals(value as string, snapshotLocator, StringComparison.Ordinal); }) != 1)
                throw new InvalidDataException("public fixture locator binding rejected");
            byte[] bytes = R7Support.ReadContentAddressed(locator, "evidence");
            if (!String.Equals(CryptoUtil.Sha256Hex(bytes), identity, StringComparison.Ordinal)) throw new InvalidDataException("public fixture content address rejected");
            IDictionary<string, object> receipt = R7Support.ParseCanonicalObject(bytes);
            StrictJson.RequireExactKeys(receipt,
                "artifact_type", "authentication_type", "body_identity", "command", "command_sha256", "end_time", "exit_code",
                "fixture_nonce", "group_sids", "helper_binary_file_identity", "helper_binary_sha256", "helper_process_id",
                "is_administrator", "junction_path", "junction_path_sha256", "operation", "outer_run_id",
                "parent_binary_file_identity", "parent_binary_sha256", "parent_process_id", "parent_start_time", "reparse_tag",
                "schema_version", "start_time", "target_path", "target_path_sha256", "token_inheritance", "user_sid");
            if (!String.Equals(StrictJson.RequireString(receipt, "artifact_type"), "R7_MEASURED_JUNCTION_FIXTURE_PROCESS", StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(receipt, "schema_version"), R7Constants.SchemaVersion, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(receipt, "operation"), "CREATE_DIRECTORY_JUNCTION_FIXTURE", StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(receipt, "outer_run_id"), runId, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(receipt, "helper_binary_sha256"), R7Constants.SubjectFixtureHostSha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(receipt, "parent_binary_sha256"), R7Constants.SubjectPythonSha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(receipt, "helper_binary_file_identity"), R7FileIdentity.Get(R7Constants.SubjectFixtureHostPath), StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(receipt, "parent_binary_file_identity"), R7FileIdentity.Get(R7Constants.SubjectPythonPath), StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(receipt, "user_sid"), R7Constants.ServiceSid, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(receipt, "token_inheritance"), "CREATEPROCESS_DEFAULT_CALLER_TOKEN", StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(receipt, "reparse_tag"), "a0000003", StringComparison.Ordinal) ||
                R7Support.RequireBool(receipt, "is_administrator") || R7Support.RequireLong(receipt, "exit_code") != 0 ||
                R7Support.RequireLong(receipt, "parent_process_id") != R7Support.RequireLong(current, "subject_process_id") ||
                R7Support.RequireLong(receipt, "helper_process_id") != R7Support.RequireLong(current, "fixture_helper_process_id") ||
                !String.Equals(StrictJson.RequireString(receipt, "helper_binary_file_identity"), StrictJson.RequireString(current, "fixture_helper_file_identity"), StringComparison.Ordinal))
                throw new InvalidDataException("public fixture process authority rejected");
            IDictionary<string, object> token = StrictJson.RequireObject(suiteReceipt, "subject_token_evidence");
            if (!String.Equals(StrictJson.RequireString(receipt, "authentication_type"), StrictJson.RequireString(token, "authentication_type"), StringComparison.Ordinal) ||
                !String.Equals(CanonicalJson.Serialize(R7Support.RequireArray(receipt, "group_sids")), CanonicalJson.Serialize(R7Support.RequireArray(token, "group_sids")), StringComparison.Ordinal))
                throw new InvalidDataException("public fixture token inheritance rejected");
            SortedDictionary<string, object> body = new SortedDictionary<string, object>(receipt, StringComparer.Ordinal);
            string bodyIdentity = R7Support.RequireLowerHex(body, "body_identity", 64);
            body.Remove("body_identity");
            if (!String.Equals(bodyIdentity, CryptoUtil.Sha256Hex(CanonicalJson.SerializeBytes(body)), StringComparison.Ordinal) ||
                !String.Equals(bodyIdentity, StrictJson.RequireString(current, "fixture_body_identity"), StringComparison.Ordinal) ||
                !String.Equals(bodyIdentity, StrictJson.RequireString(observed, "fixture_body_identity"), StringComparison.Ordinal) ||
                !R7Support.IsLowerHex(StrictJson.RequireString(receipt, "fixture_nonce"), 64))
                throw new InvalidDataException("public fixture body identity rejected");
            string command = StrictJson.RequireString(receipt, "command");
            Match match = Regex.Match(command, @"\ANew-Item -ItemType Junction -Path '(?<junction>[^']+)' -Target '(?<target>[^']+)' \| Out-Null\z", RegexOptions.CultureInvariant);
            string junctionPath = Path.GetFullPath(StrictJson.RequireString(receipt, "junction_path"));
            string targetPath = Path.GetFullPath(StrictJson.RequireString(receipt, "target_path"));
            string root = Path.GetFullPath(R7Constants.SubjectTemporaryRoot).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            if (!match.Success || !String.Equals(junctionPath, Path.GetFullPath(match.Groups["junction"].Value), StringComparison.OrdinalIgnoreCase) ||
                !String.Equals(targetPath, Path.GetFullPath(match.Groups["target"].Value), StringComparison.OrdinalIgnoreCase) ||
                !junctionPath.StartsWith(root, StringComparison.OrdinalIgnoreCase) || !targetPath.StartsWith(root, StringComparison.OrdinalIgnoreCase) ||
                !String.Equals(Path.GetFileName(junctionPath), "reparse-parent", StringComparison.Ordinal) ||
                !String.Equals(Path.GetFileName(targetPath), "reparse-target", StringComparison.Ordinal) ||
                !String.Equals(Path.GetDirectoryName(junctionPath), Path.GetDirectoryName(targetPath), StringComparison.OrdinalIgnoreCase) ||
                !String.Equals(CryptoUtil.Sha256Hex(new UTF8Encoding(false, true).GetBytes(command)), StrictJson.RequireString(receipt, "command_sha256"), StringComparison.Ordinal) ||
                !String.Equals(CryptoUtil.Sha256Hex(new UTF8Encoding(false, true).GetBytes(junctionPath)), StrictJson.RequireString(receipt, "junction_path_sha256"), StringComparison.Ordinal) ||
                !String.Equals(CryptoUtil.Sha256Hex(new UTF8Encoding(false, true).GetBytes(targetPath)), StrictJson.RequireString(receipt, "target_path_sha256"), StringComparison.Ordinal))
                throw new InvalidDataException("public fixture command or path rejected");
            byte[] snapshotBytes = R7Support.ReadContentAddressed(snapshotLocator, "evidence");
            if (!String.Equals(CryptoUtil.Sha256Hex(snapshotBytes), snapshotIdentity, StringComparison.Ordinal))
                throw new InvalidDataException("public fixture snapshot content address rejected");
            IDictionary<string, object> snapshot = R7Support.ParseCanonicalObject(snapshotBytes);
            StrictJson.RequireExactKeys(snapshot, "artifact_type", "body_identity", "capture_model", "capture_time", "case_id",
                "fixture_process_receipt_identity", "junction_attributes", "junction_path", "reparse_data_base64", "reparse_data_sha256",
                "run_id", "schema_version", "service_binary_file_identity", "service_binary_sha256", "service_process_id", "service_sid",
                "target_attributes", "target_path");
            SortedDictionary<string, object> snapshotBody = new SortedDictionary<string, object>(snapshot, StringComparer.Ordinal);
            string snapshotBodyIdentity = R7Support.RequireLowerHex(snapshotBody, "body_identity", 64);
            snapshotBody.Remove("body_identity");
            long junctionAttributes = R7Support.RequireLong(snapshot, "junction_attributes");
            long targetAttributes = R7Support.RequireLong(snapshot, "target_attributes");
            if (!String.Equals(snapshotBodyIdentity, CryptoUtil.Sha256Hex(CanonicalJson.SerializeBytes(snapshotBody)), StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(snapshot, "artifact_type"), "R7_SERVICE_REPARSE_SIDE_EFFECT_EVIDENCE", StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(snapshot, "capture_model"), "FSCTL_GET_REPARSE_POINT", StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(snapshot, "case_id"), StrictJson.RequireString(current, "case_id"), StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(snapshot, "fixture_process_receipt_identity"), identity, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(snapshot, "junction_path"), junctionPath, StringComparison.OrdinalIgnoreCase) ||
                !String.Equals(StrictJson.RequireString(snapshot, "run_id"), runId, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(snapshot, "schema_version"), R7Constants.SchemaVersion, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(snapshot, "service_binary_file_identity"), StrictJson.RequireString(suiteReceipt, "parent_service_binary_file_identity"), StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(snapshot, "service_binary_sha256"), StrictJson.RequireString(suiteReceipt, "parent_service_binary_sha256"), StringComparison.Ordinal) ||
                R7Support.RequireLong(snapshot, "service_process_id") != R7Support.RequireLong(suiteReceipt, "parent_service_process_id") ||
                !String.Equals(StrictJson.RequireString(snapshot, "service_sid"), R7Constants.ServiceSid, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(snapshot, "target_path"), targetPath, StringComparison.OrdinalIgnoreCase) ||
                (junctionAttributes & (long)FileAttributes.ReparsePoint) == 0 || (junctionAttributes & (long)FileAttributes.Directory) == 0 ||
                (targetAttributes & (long)FileAttributes.ReparsePoint) != 0 || (targetAttributes & (long)FileAttributes.Directory) == 0)
                throw new InvalidDataException("public fixture snapshot authority rejected");
            byte[] reparseData;
            try { reparseData = Convert.FromBase64String(StrictJson.RequireString(snapshot, "reparse_data_base64")); }
            catch (FormatException exception) { throw new InvalidDataException("public fixture snapshot base64 rejected", exception); }
            if (!String.Equals(CryptoUtil.Sha256Hex(reparseData), StrictJson.RequireString(snapshot, "reparse_data_sha256"), StringComparison.Ordinal))
                throw new InvalidDataException("public fixture snapshot hash rejected");
            R7ReparseEvidence.ValidateMountPoint(reparseData, targetPath);
            const string format = "yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'";
            DateTimeStyles styles = DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal;
            DateTimeOffset eventStart;
            DateTimeOffset eventEnd;
            DateTimeOffset fixtureStart;
            DateTimeOffset fixtureEnd;
            DateTimeOffset parentStart;
            DateTimeOffset snapshotTime;
            DateTimeOffset suiteCompletionTime;
            if (!DateTimeOffset.TryParseExact(StrictJson.RequireString(current, "public_interface_start_time"), format, CultureInfo.InvariantCulture, styles, out eventStart) ||
                !DateTimeOffset.TryParseExact(StrictJson.RequireString(current, "public_interface_end_time"), format, CultureInfo.InvariantCulture, styles, out eventEnd) ||
                !DateTimeOffset.TryParseExact(StrictJson.RequireString(receipt, "start_time"), format, CultureInfo.InvariantCulture, styles, out fixtureStart) ||
                !DateTimeOffset.TryParseExact(StrictJson.RequireString(receipt, "end_time"), format, CultureInfo.InvariantCulture, styles, out fixtureEnd) ||
                !DateTimeOffset.TryParseExact(StrictJson.RequireString(receipt, "parent_start_time"), format, CultureInfo.InvariantCulture, styles, out parentStart) ||
                !DateTimeOffset.TryParseExact(StrictJson.RequireString(snapshot, "capture_time"), format, CultureInfo.InvariantCulture, styles, out snapshotTime) ||
                !DateTimeOffset.TryParseExact(StrictJson.RequireString(suiteReceipt, "completion_time"), format, CultureInfo.InvariantCulture, styles, out suiteCompletionTime) ||
                parentStart > fixtureStart || fixtureStart < eventStart || fixtureEnd < fixtureStart || fixtureEnd > eventEnd ||
                snapshotTime < eventEnd || snapshotTime > suiteCompletionTime)
                throw new InvalidDataException("public fixture current-event time rejected");
        }

        private static void VerifyProcesses(IDictionary<string, object> index, string runId, R7LedgerState ledger, HashSet<string> identities)
        {
            string[] keys = new string[] { "suite_process_receipt_locator", "observation_process_receipt_locator", "comparator_process_receipt_locator" };
            foreach (string key in keys)
            {
                string locator = StrictJson.RequireString(index, key);
                string identity = R7Support.ParseLocator(locator, "evidence");
                if (!identities.Add(identity)) throw new InvalidDataException("process receipt reuse rejected");
                IDictionary<string, object> receipt = R7Support.VerifySignedEnvelope(R7Support.ReadContentAddressed(locator, "evidence"), publicKey);
                if (!String.Equals(StrictJson.RequireString(receipt, "run_id"), runId, StringComparison.Ordinal)) throw new InvalidDataException("process receipt run rejected");
                string operation = key == "suite_process_receipt_locator" ? "R7_REAL_SUITE_PROCESS_COMPLETED" : "R7_PROCESS_COMPLETED";
                R7Support.FindLedgerEntry(ledger, operation, identity);
                if (key == "suite_process_receipt_locator")
                {
                    if (!String.Equals(StrictJson.RequireString(receipt, "mode"), "execute-real-suite", StringComparison.Ordinal) ||
                        !String.Equals(StrictJson.RequireString(receipt, "launcher_sha256"), R7Constants.SubjectLauncherSha256, StringComparison.Ordinal) ||
                        !String.Equals(StrictJson.RequireString(receipt, "subject_commit"), R7Constants.SubjectCommit, StringComparison.Ordinal) ||
                        !String.Equals(StrictJson.RequireString(receipt, "subject_service_sha256"), R7Constants.SubjectServiceSha256, StringComparison.Ordinal) ||
                        !String.Equals(StrictJson.RequireString(receipt, "python_sha256"), R7Constants.SubjectPythonSha256, StringComparison.Ordinal) ||
                        !String.Equals(StrictJson.RequireString(receipt, "fixture_host_sha256"), R7Constants.SubjectFixtureHostSha256, StringComparison.Ordinal) ||
                        !String.Equals(StrictJson.RequireString(receipt, "fixture_host_file_identity"), R7FileIdentity.Get(R7Constants.SubjectFixtureHostPath), StringComparison.Ordinal) ||
                        R7Support.RequireLong(receipt, "case_count") != R7Constants.RequiredCaseCount) throw new InvalidDataException("suite process measurement rejected");
                    IDictionary<string, object> token = StrictJson.RequireObject(receipt, "subject_token_evidence");
                    byte[] launchBytes = R7Support.ReadContentAddressed(StrictJson.RequireString(receipt, "launch_receipt_locator"), "evidence");
                    IDictionary<string, object> launch = R7Support.ParseCanonicalObject(launchBytes);
                    if (!String.Equals(StrictJson.RequireString(token, "user_sid"), R7Constants.ServiceSid, StringComparison.Ordinal) || R7Support.RequireBool(token, "is_administrator") ||
                        !String.Equals(CanonicalJson.Serialize(token), CanonicalJson.Serialize(launch), StringComparison.Ordinal) ||
                        !String.Equals(CryptoUtil.Sha256Hex(launchBytes), StrictJson.RequireString(receipt, "subject_token_evidence_identity"), StringComparison.Ordinal) ||
                        R7Support.RequireLong(launch, "subject_process_id") != R7Support.RequireLong(receipt, "subject_process_id")) throw new InvalidDataException("suite process principal rejected");
                }
                else if (!String.Equals(StrictJson.RequireString(receipt, "worker_sha256"), R7VerifierBuildConstants.WorkerSha256, StringComparison.Ordinal)) throw new InvalidDataException("worker process measurement rejected");
            }
        }

        private static string VerifyReconciliation(string locator)
        {
            string identity = R7Support.ParseLocator(locator, "reconciliation");
            IDictionary<string, object> payload = R7Support.VerifySignedEnvelope(R7Support.ReadContentAddressed(locator, "reconciliation"), publicKey);
            if (!String.Equals(StrictJson.RequireString(payload, "artifact_type"), "R7_SIGNED_EXTERNAL_RECONCILIATION_RECEIPT", StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "reconciliation_result"), "SEMANTICALLY_EQUIVALENT_REAL_EXECUTIONS", StringComparison.Ordinal) ||
                !R7Support.RequireBool(payload, "provenance_disjoint") || !R7Support.RequireBool(payload, "synthetic_result_class_absent")) throw new InvalidDataException("reconciliation authority rejected");
            R7VerifiedTerminal candidate = VerifyTerminal(StrictJson.RequireString(payload, "candidate_receipt_locator"));
            R7VerifiedTerminal fresh = VerifyTerminal(StrictJson.RequireString(payload, "fresh_receipt_locator"));
            if (!String.Equals(candidate.Phase, "CANDIDATE", StringComparison.Ordinal) || !String.Equals(fresh.Phase, "FRESH", StringComparison.Ordinal) ||
                !String.Equals(candidate.AttemptId, fresh.AttemptId, StringComparison.Ordinal) || !String.Equals(candidate.Configuration, fresh.Configuration, StringComparison.Ordinal) ||
                String.Equals(candidate.RunId, fresh.RunId, StringComparison.Ordinal) || String.Equals(candidate.RunNonce, fresh.RunNonce, StringComparison.Ordinal) ||
                String.Equals(candidate.EventRoot, fresh.EventRoot, StringComparison.Ordinal) || candidate.ProcessIdentities.Overlaps(fresh.ProcessIdentities)) throw new InvalidDataException("reconciliation distinct execution rejected");
            string evaluatorIdentity = VerifyReconciliationEvaluator(
                StrictJson.RequireString(payload, "reconciliation_evaluator_result_locator"),
                StrictJson.RequireString(payload, "reconciliation_process_receipt_locator"),
                R7Support.RequireLowerHex(payload, "reconciliation_process_run_id", 64), candidate, fresh);
            if (candidate.ProcessIdentities.Contains(evaluatorIdentity) || fresh.ProcessIdentities.Contains(evaluatorIdentity))
                throw new InvalidDataException("reconciliation evaluator process reuse rejected");
            SortedDictionary<string, object> claimBase = new SortedDictionary<string, object>(payload, StringComparer.Ordinal);
            string claim = StrictJson.RequireString(claimBase, "reconciliation_claim_identity");
            claimBase.Remove("ledger_reservation_entry_identity");
            claimBase.Remove("ledger_reservation_sequence");
            claimBase.Remove("reconciliation_claim_identity");
            if (!String.Equals(claim, CryptoUtil.Sha256Hex(CanonicalJson.SerializeBytes(claimBase)), StringComparison.Ordinal)) throw new InvalidDataException("reconciliation claim rejected");
            R7Support.FindLedgerEntry(R7Support.VerifyLedger(publicKey), "R7_RECONCILIATION_RECEIPT_COMMITTED", identity);
            return identity;
        }

        private static string VerifyReconciliationEvaluator(string resultLocator, string processReceiptLocator, string reconciliationRunId,
            R7VerifiedTerminal candidate, R7VerifiedTerminal fresh)
        {
            IDictionary<string, object> result = ReadEvidence(resultLocator);
            if (!String.Equals(StrictJson.RequireString(result, "artifact_type"), "R7_INDEPENDENT_EXTERNAL_RECONCILIATION_RESULT", StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(result, "run_id"), reconciliationRunId, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(result, "reconciliation_result"), "RECONCILED_REAL_EXECUTIONS", StringComparison.Ordinal) ||
                R7Support.RequireLong(result, "discrepancy_count") != 0 || R7Support.RequireArray(result, "discrepancies").Length != 0 ||
                R7Support.RequireLong(result, "resolved_terminal_count") != 2 || !R7Support.RequireBool(result, "synthetic_result_class_absent") ||
                !String.Equals(StrictJson.RequireString(result, "candidate_receipt_identity"), candidate.ReceiptIdentity, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(result, "fresh_receipt_identity"), fresh.ReceiptIdentity, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(result, "candidate_run_id"), candidate.RunId, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(result, "fresh_run_id"), fresh.RunId, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(result, "candidate_event_root"), candidate.EventRoot, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(result, "fresh_event_root"), fresh.EventRoot, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(result, "case_definition_git_blob"), R7Constants.CaseDefinitionGitBlob, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(result, "expectation_git_blob"), R7Constants.ExpectationGitBlob, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(result, "policy_sha256"), R7VerifierBuildConstants.PolicySha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(result, "service_binary_sha256"), R7VerifierBuildConstants.ServiceSha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(result, "worker_binary_sha256"), R7VerifierBuildConstants.WorkerSha256, StringComparison.Ordinal))
                throw new InvalidDataException("reconciliation evaluator result rejected");
            string processIdentity = R7Support.ParseLocator(processReceiptLocator, "evidence");
            IDictionary<string, object> receipt = R7Support.VerifySignedEnvelope(R7Support.ReadContentAddressed(processReceiptLocator, "evidence"), publicKey);
            if (!String.Equals(StrictJson.RequireString(receipt, "mode"), "reconcile", StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(receipt, "run_id"), reconciliationRunId, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(receipt, "worker_sha256"), R7VerifierBuildConstants.WorkerSha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(receipt, "process_nonce"), StrictJson.RequireString(result, "reconciliation_process_nonce"), StringComparison.Ordinal))
                throw new InvalidDataException("reconciliation evaluator process rejected");
            IDictionary<string, object> workerOutput = StrictJson.RequireObject(receipt, "result");
            IDictionary<string, object> embeddedResult = StrictJson.RequireObject(workerOutput, "result");
            if (!String.Equals(CanonicalJson.Serialize(embeddedResult), CanonicalJson.Serialize(result), StringComparison.Ordinal))
                throw new InvalidDataException("reconciliation evaluator output binding rejected");
            R7Support.FindLedgerEntry(R7Support.VerifyLedger(publicKey), "R7_PROCESS_COMPLETED", processIdentity);
            return processIdentity;
        }

        private static IDictionary<string, object> FindEntryByIdentity(R7LedgerState ledger, string identity)
        {
            for (int index = 0; index < ledger.EntryIdentities.Count; index++) if (String.Equals(ledger.EntryIdentities[index], identity, StringComparison.Ordinal)) return ledger.Payloads[index];
            throw new InvalidDataException("ledger entry identity unresolved");
        }

        private static IDictionary<string, object> ReadEvidence(string locator)
        {
            return R7Support.ParseCanonicalObject(R7Support.ReadContentAddressed(locator, "evidence"));
        }

        private static Dictionary<string, IDictionary<string, object>> Index(object[] rows)
        {
            Dictionary<string, IDictionary<string, object>> result = new Dictionary<string, IDictionary<string, object>>(StringComparer.Ordinal);
            foreach (object raw in rows)
            {
                IDictionary<string, object> row = raw as IDictionary<string, object>;
                if (row == null) throw new InvalidDataException("indexed row rejected");
                string id = StrictJson.RequireString(row, "case_id");
                if (result.ContainsKey(id)) throw new InvalidDataException("indexed duplicate case rejected");
                result.Add(id, row);
            }
            return result;
        }

        private static void Emit(string resultCode, long sequence, string root, string identity)
        {
            SortedDictionary<string, object> value = new SortedDictionary<string, object>(StringComparer.Ordinal);
            value["identity"] = identity;
            value["ledger_root"] = root;
            value["ledger_sequence"] = sequence;
            value["result_code"] = resultCode;
            value["status"] = "VERIFIED";
            Console.Out.WriteLine(CanonicalJson.Serialize(value));
        }
    }
}
