using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Security.Principal;
using System.Text;
using System.Text.RegularExpressions;

namespace RandleAI.TerminalAuthority
{
    internal sealed class R7WorkerTerminalView
    {
        internal string AttemptId;
        internal string Configuration;
        internal string EventRoot;
        internal string Locator;
        internal string Phase;
        internal string ReceiptIdentity;
        internal string RunId;
        internal string RunNonce;
        internal IDictionary<string, object> Payload;
        internal readonly HashSet<string> ProcessIdentities = new HashSet<string>(StringComparer.Ordinal);
    }

    internal static class R7MeasuredWorker
    {
        private static int Main(string[] args)
        {
            try
            {
                if (args.Length != 4) throw new InvalidDataException("WORKER_ARGUMENT_COUNT");
                string mode = args[0];
                string runId = args[1];
                string processNonce = args[2];
                string inputPath = ValidateInputPath(args[3]);
                if (!R7Support.IsLowerHex(runId, 64) || !R7Support.IsLowerHex(processNonce, 64))
                    throw new InvalidDataException("WORKER_RUN_OR_PROCESS_IDENTITY");
                byte[] inputBytes = File.ReadAllBytes(inputPath);
                IDictionary<string, object> input = R7Support.ParseCanonicalObject(inputBytes);
                StrictJson.RequireExactKeys(input, "mode", "process_nonce", "run_id", "subject");
                if (!String.Equals(StrictJson.RequireString(input, "mode"), mode, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(input, "run_id"), runId, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(input, "process_nonce"), processNonce, StringComparison.Ordinal))
                    throw new InvalidDataException("WORKER_INPUT_BINDING");
                IDictionary<string, object> subject = StrictJson.RequireObject(input, "subject");
                object result;
                if (String.Equals(mode, "derive-observations", StringComparison.Ordinal)) result = DeriveObservations(runId, processNonce, subject);
                else if (String.Equals(mode, "compare", StringComparison.Ordinal)) result = Compare(runId, processNonce, subject);
                else if (String.Equals(mode, "reconcile", StringComparison.Ordinal)) result = Reconcile(runId, processNonce, subject);
                else throw new InvalidDataException("WORKER_MODE_REJECTED");

                using (WindowsIdentity identity = WindowsIdentity.GetCurrent())
                {
                    WindowsPrincipal principal = new WindowsPrincipal(identity);
                    List<object> groups = new List<object>();
                    if (identity.Groups != null)
                    {
                        foreach (IdentityReference group in identity.Groups)
                        {
                            SecurityIdentifier sid = group.Translate(typeof(SecurityIdentifier)) as SecurityIdentifier;
                            if (sid != null) groups.Add(sid.Value);
                        }
                    }
                    groups.Sort(delegate(object left, object right) { return StringComparer.Ordinal.Compare((string)left, (string)right); });
                    SortedDictionary<string, object> output = new SortedDictionary<string, object>(StringComparer.Ordinal);
                    output["group_sids"] = groups.ToArray();
                    output["input_identity"] = CryptoUtil.Sha256Hex(inputBytes);
                    output["is_administrator"] = principal.IsInRole(WindowsBuiltInRole.Administrator);
                    output["mode"] = mode;
                    output["process_nonce"] = processNonce;
                    output["result"] = result;
                    output["run_id"] = runId;
                    output["status"] = "COMPLETE";
                    output["user_sid"] = identity.User == null ? String.Empty : identity.User.Value;
                    output["worker_binary_sha256"] = CryptoUtil.Sha256File(Assembly.GetExecutingAssembly().Location);
                    output["worker_pid"] = Process.GetCurrentProcess().Id;
                    Console.Out.Write(CanonicalJson.Serialize(output));
                    Console.Out.Write("\n");
                }
                return 0;
            }
            catch (Exception exception)
            {
                Console.Error.WriteLine(exception.GetType().FullName + ": " + exception.Message);
                return 1;
            }
        }

        private static string ValidateInputPath(string value)
        {
            string full = Path.GetFullPath(value);
            string root = Path.GetFullPath(R7Constants.SessionRoot).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            if (!full.StartsWith(root, StringComparison.OrdinalIgnoreCase) || !String.Equals(Path.GetFileName(full), "input.json", StringComparison.Ordinal))
                throw new InvalidDataException("WORKER_INPUT_PATH_REJECTED");
            return full;
        }

        private static IDictionary<string, object> DeriveObservations(string runId, string processNonce, IDictionary<string, object> subject)
        {
            StrictJson.RequireExactKeys(subject, "event_source_locator");
            string eventLocator = StrictJson.RequireString(subject, "event_source_locator");
            IDictionary<string, object> source = ReadEvidence(eventLocator);
            RequireEventSource(source, runId);
            object[] events = R7Support.RequireArray(source, "events");
            List<object> observations = new List<object>();
            HashSet<string> seen = new HashSet<string>(StringComparer.Ordinal);
            foreach (object raw in events)
            {
                IDictionary<string, object> current = raw as IDictionary<string, object>;
                if (current == null) throw new InvalidDataException("OBSERVATION_EVENT_SHAPE");
                string caseId = StrictJson.RequireString(current, "case_id");
                if (!seen.Add(caseId) || !String.Equals(StrictJson.RequireString(current, "run_id"), runId, StringComparison.Ordinal))
                    throw new InvalidDataException("OBSERVATION_EVENT_DUPLICATE_OR_RUN");
                SortedDictionary<string, object> observation = new SortedDictionary<string, object>(StringComparer.Ordinal);
                observation["actual_authority_identity"] = StrictJson.RequireString(current, "actual_authority_identity");
                observation["actual_outcome"] = StrictJson.RequireString(current, "actual_outcome");
                observation["case_id"] = caseId;
                observation["derived_at"] = R7Support.Timestamp();
                observation["enforcing_function"] = StrictJson.RequireString(current, "enforcing_function");
                observation["event_hash"] = StrictJson.RequireString(current, "event_hash");
                observation["event_sequence"] = R7Support.RequireLong(current, "sequence");
                List<object> citations = new List<object> {
                    eventLocator,
                    StrictJson.RequireString(current, "public_request_locator"),
                    StrictJson.RequireString(current, "public_response_locator"),
                    StrictJson.RequireString(current, "suite_process_receipt_locator")
                };
                if (R7Support.RequireBool(current, "fixture_helper_invoked"))
                {
                    citations.Add(StrictJson.RequireString(current, "fixture_process_receipt_locator"));
                    citations.Add(StrictJson.RequireString(current, "fixture_reparse_snapshot_locator"));
                }
                observation["evidence_citations"] = citations.ToArray();
                observation["fixture_body_identity"] = StrictJson.RequireString(current, "fixture_body_identity");
                observation["fixture_helper_file_identity"] = StrictJson.RequireString(current, "fixture_helper_file_identity");
                observation["fixture_helper_invoked"] = R7Support.RequireBool(current, "fixture_helper_invoked");
                observation["fixture_helper_process_id"] = R7Support.RequireLong(current, "fixture_helper_process_id");
                observation["fixture_process_receipt_identity"] = StrictJson.RequireString(current, "fixture_process_receipt_identity");
                observation["fixture_process_receipt_locator"] = StrictJson.RequireString(current, "fixture_process_receipt_locator");
                observation["fixture_reparse_snapshot_identity"] = StrictJson.RequireString(current, "fixture_reparse_snapshot_identity");
                observation["fixture_reparse_snapshot_locator"] = StrictJson.RequireString(current, "fixture_reparse_snapshot_locator");
                observation["forbidden_side_effect_absent"] = R7Support.RequireBool(current, "forbidden_side_effect_absent");
                observation["inner_event_hash"] = StrictJson.RequireString(current, "inner_event_hash");
                observation["inner_execution_receipt_identity"] = StrictJson.RequireString(current, "inner_execution_receipt_identity");
                observation["interface_invoked"] = R7Support.RequireBool(current, "interface_invoked");
                observation["outer_ledger_delta"] = R7Support.RequireLong(current, "outer_post_ledger_sequence") - R7Support.RequireLong(current, "outer_pre_ledger_sequence");
                observation["response_classification"] = StrictJson.RequireString(current, "response_classification");
                observation["subject_case_token_identity"] = StrictJson.RequireString(current, "subject_case_token_identity");
                observation["subject_event_ledger_delta"] = R7Support.RequireLong(current, "subject_event_ledger_delta");
                observation["subject_process_id"] = R7Support.RequireLong(current, "subject_process_id");
                observations.Add(observation);
            }
            SortedDictionary<string, object> value = new SortedDictionary<string, object>(StringComparer.Ordinal);
            value["artifact_type"] = "R7_DERIVED_CURRENT_OBSERVATIONS";
            value["event_source_locator"] = eventLocator;
            value["observation_count"] = observations.Count;
            value["observations"] = observations.ToArray();
            value["observer_binary_sha256"] = CryptoUtil.Sha256File(Assembly.GetExecutingAssembly().Location);
            value["observer_process_nonce"] = processNonce;
            value["observer_process_id"] = Process.GetCurrentProcess().Id;
            value["run_id"] = runId;
            value["schema_version"] = R7Constants.SchemaVersion;
            return value;
        }

        private static IDictionary<string, object> Compare(string runId, string processNonce, IDictionary<string, object> subject)
        {
            StrictJson.RequireExactKeys(subject, "event_source_locator", "observation_locator", "traceability_locator");
            string eventLocator = StrictJson.RequireString(subject, "event_source_locator");
            string observationLocator = StrictJson.RequireString(subject, "observation_locator");
            string traceLocator = StrictJson.RequireString(subject, "traceability_locator");
            IDictionary<string, object> caseAuthority = R7Support.ReadCaseAuthority();
            IDictionary<string, object> expectationAuthority = R7Support.ReadExpectationAuthority();
            IDictionary<string, object> eventSource = ReadEvidence(eventLocator);
            IDictionary<string, object> observationSource = ReadEvidence(observationLocator);
            IDictionary<string, object> traceSource = ReadEvidence(traceLocator);
            RequireEventSource(eventSource, runId);
            object[] cases = R7Support.RequireArray(caseAuthority, "cases");
            object[] expectations = R7Support.RequireArray(expectationAuthority, "expectations");
            object[] events = R7Support.RequireArray(eventSource, "events");
            object[] observations = R7Support.RequireArray(observationSource, "observations");
            object[] traces = R7Support.RequireArray(traceSource, "rows");
            List<object> discrepancies = new List<object>();
            List<object> decisions = new List<object>();
            Count(discrepancies, "CASE_COUNT", cases.Length, R7Constants.RequiredCaseCount);
            Count(discrepancies, "EXPECTATION_COUNT", expectations.Length, R7Constants.RequiredCaseCount);
            Count(discrepancies, "EVENT_COUNT", events.Length, R7Constants.RequiredCaseCount);
            Count(discrepancies, "OBSERVATION_COUNT", observations.Length, R7Constants.RequiredCaseCount);
            Count(discrepancies, "TRACE_COUNT", traces.Length, R7Constants.RequiredCaseCount);
            Dictionary<string, IDictionary<string, object>> expectedById = Index(expectations, "EXPECTATION", discrepancies);
            Dictionary<string, IDictionary<string, object>> eventById = Index(events, "EVENT", discrepancies);
            Dictionary<string, IDictionary<string, object>> observationById = Index(observations, "OBSERVATION", discrepancies);
            Dictionary<string, IDictionary<string, object>> traceById = Index(traces, "TRACE", discrepancies);
            HashSet<string> governedIds = new HashSet<string>(cases.Select(delegate(object item) { return StrictJson.RequireString((IDictionary<string, object>)item, "case_id"); }), StringComparer.Ordinal);
            RejectUnknown(expectedById.Keys, governedIds, "EXPECTATION", discrepancies);
            RejectUnknown(eventById.Keys, governedIds, "EVENT", discrepancies);
            RejectUnknown(observationById.Keys, governedIds, "OBSERVATION", discrepancies);
            RejectUnknown(traceById.Keys, governedIds, "TRACE", discrepancies);

            X509Certificate2 certificate = CryptoUtil.LoadPublicCertificate();
            using (RSA publicKey = System.Security.Cryptography.X509Certificates.RSACertificateExtensions.GetRSAPublicKey(certificate))
            {
                R7LedgerState ledger = R7Support.VerifyLedger(publicKey);
                foreach (object raw in cases)
                {
                    IDictionary<string, object> definition = (IDictionary<string, object>)raw;
                    string caseId = StrictJson.RequireString(definition, "case_id");
                    int before = discrepancies.Count;
                    IDictionary<string, object> expected;
                    IDictionary<string, object> actual;
                    IDictionary<string, object> observed;
                    IDictionary<string, object> trace;
                    if (!expectedById.TryGetValue(caseId, out expected)) Add(discrepancies, caseId, "EXPECTATION_MISSING", "independent expectation is absent");
                    if (!eventById.TryGetValue(caseId, out actual)) Add(discrepancies, caseId, "EVENT_MISSING", "current execution event is absent");
                    if (!observationById.TryGetValue(caseId, out observed)) Add(discrepancies, caseId, "OBSERVATION_MISSING", "derived observation is absent");
                    if (!traceById.TryGetValue(caseId, out trace)) Add(discrepancies, caseId, "TRACE_MISSING", "trace row is absent");
                    if (expected != null && actual != null && observed != null && trace != null)
                        VerifyCase(runId, definition, expected, actual, observed, trace, ledger, publicKey, discrepancies);
                    SortedDictionary<string, object> decision = new SortedDictionary<string, object>(StringComparer.Ordinal);
                    decision["case_id"] = caseId;
                    decision["decision"] = discrepancies.Count == before ? "CONFORMANT" : "DISCREPANT";
                    decision["event_hash"] = actual == null ? String.Empty : StrictJson.RequireString(actual, "event_hash");
                    decisions.Add(decision);
                }
            }
            certificate.Dispose();
            SortedDictionary<string, object> result = new SortedDictionary<string, object>(StringComparer.Ordinal);
            result["artifact_type"] = "R7_INDEPENDENT_COMPARATOR_RESULT";
            result["case_decisions"] = decisions.ToArray();
            result["case_definition_git_blob"] = R7Constants.CaseDefinitionGitBlob;
            result["comparator_binary_sha256"] = CryptoUtil.Sha256File(Assembly.GetExecutingAssembly().Location);
            result["comparator_process_nonce"] = processNonce;
            result["conformity"] = discrepancies.Count == 0 ? "CONFORMANT" : "NONCONFORMANT";
            result["discrepancies"] = discrepancies.ToArray();
            result["discrepancy_count"] = discrepancies.Count;
            result["event_source_locator"] = eventLocator;
            result["expectation_git_blob"] = R7Constants.ExpectationGitBlob;
            result["observation_locator"] = observationLocator;
            result["resolved_case_count"] = decisions.Count;
            result["run_id"] = runId;
            result["schema_version"] = R7Constants.SchemaVersion;
            result["traceability_locator"] = traceLocator;
            return result;
        }

        private static IDictionary<string, object> Reconcile(string runId, string processNonce, IDictionary<string, object> subject)
        {
            StrictJson.RequireExactKeys(subject, "attempt_id", "candidate_locator", "fresh_locator");
            string attemptId = R7Support.RequireLowerHex(subject, "attempt_id", 64);
            string candidateLocator = StrictJson.RequireString(subject, "candidate_locator");
            string freshLocator = StrictJson.RequireString(subject, "fresh_locator");
            List<object> discrepancies = new List<object>();
            R7WorkerTerminalView candidate = null;
            R7WorkerTerminalView fresh = null;
            string serviceSha256 = CryptoUtil.Sha256File(R7Constants.ServiceExecutablePath);
            string policySha256 = CryptoUtil.Sha256File(R7Constants.PolicyPath);
            string workerSha256 = CryptoUtil.Sha256File(Assembly.GetExecutingAssembly().Location);
            if (String.Equals(candidateLocator, freshLocator, StringComparison.Ordinal))
                Add(discrepancies, String.Empty, "RECEIPT_LOCATOR_REUSE", "candidate and fresh locators are identical");

            X509Certificate2 certificate = null;
            RSA publicKey = null;
            try
            {
                certificate = CryptoUtil.LoadPublicCertificate();
                if (certificate.HasPrivateKey || certificate.GetRSAPublicKey().KeySize != 3072)
                    throw new CryptographicException("RECONCILER_PUBLIC_TRUST_REJECTED");
                publicKey = System.Security.Cryptography.X509Certificates.RSACertificateExtensions.GetRSAPublicKey(certificate);
                try { candidate = VerifyWorkerTerminal(candidateLocator, publicKey, serviceSha256, policySha256, workerSha256); }
                catch (Exception exception) { Add(discrepancies, String.Empty, "CANDIDATE_TERMINAL_REJECTED", exception.GetType().Name + ": " + exception.Message); }
                try { fresh = VerifyWorkerTerminal(freshLocator, publicKey, serviceSha256, policySha256, workerSha256); }
                catch (Exception exception) { Add(discrepancies, String.Empty, "FRESH_TERMINAL_REJECTED", exception.GetType().Name + ": " + exception.Message); }
                if (candidate != null && fresh != null)
                {
                    Equal(discrepancies, String.Empty, "CANDIDATE_ATTEMPT", candidate.AttemptId, attemptId);
                    Equal(discrepancies, String.Empty, "FRESH_ATTEMPT", fresh.AttemptId, attemptId);
                    Equal(discrepancies, String.Empty, "CANDIDATE_PHASE", candidate.Phase, "CANDIDATE");
                    Equal(discrepancies, String.Empty, "FRESH_PHASE", fresh.Phase, "FRESH");
                    Equal(discrepancies, String.Empty, "CONFIGURATION", candidate.Configuration, fresh.Configuration);
                    RejectSame(discrepancies, "RUN_ID_REUSE", candidate.RunId, fresh.RunId);
                    RejectSame(discrepancies, "RUN_NONCE_REUSE", candidate.RunNonce, fresh.RunNonce);
                    RejectSame(discrepancies, "EVENT_ROOT_REUSE", candidate.EventRoot, fresh.EventRoot);
                    RejectSame(discrepancies, "RECEIPT_IDENTITY_REUSE", candidate.ReceiptIdentity, fresh.ReceiptIdentity);
                    if (candidate.ProcessIdentities.Overlaps(fresh.ProcessIdentities))
                        Add(discrepancies, String.Empty, "PROCESS_RECEIPT_REUSE", "candidate and fresh executions share a process receipt identity");
                    string[] semanticKeys = new string[] {
                        "case_definition_git_blob", "case_definition_sha256", "expectation_git_blob", "expectation_sha256",
                        "policy_sha256", "service_binary_sha256", "worker_sha256", "subject_commit"
                    };
                    foreach (string key in semanticKeys)
                        Equal(discrepancies, String.Empty, "SEMANTIC_" + key.ToUpperInvariant(), StrictJson.RequireString(candidate.Payload, key), StrictJson.RequireString(fresh.Payload, key));
                }
            }
            finally
            {
                if (publicKey != null) publicKey.Dispose();
                if (certificate != null) certificate.Dispose();
            }

            SortedDictionary<string, object> result = new SortedDictionary<string, object>(StringComparer.Ordinal);
            result["artifact_type"] = "R7_INDEPENDENT_EXTERNAL_RECONCILIATION_RESULT";
            result["attempt_id"] = attemptId;
            result["candidate_event_root"] = candidate == null ? String.Empty : candidate.EventRoot;
            result["candidate_receipt_identity"] = candidate == null ? String.Empty : candidate.ReceiptIdentity;
            result["candidate_receipt_locator"] = candidateLocator;
            result["candidate_run_id"] = candidate == null ? String.Empty : candidate.RunId;
            result["case_definition_git_blob"] = R7Constants.CaseDefinitionGitBlob;
            result["discrepancies"] = discrepancies.ToArray();
            result["discrepancy_count"] = discrepancies.Count;
            result["expectation_git_blob"] = R7Constants.ExpectationGitBlob;
            result["fresh_event_root"] = fresh == null ? String.Empty : fresh.EventRoot;
            result["fresh_receipt_identity"] = fresh == null ? String.Empty : fresh.ReceiptIdentity;
            result["fresh_receipt_locator"] = freshLocator;
            result["fresh_run_id"] = fresh == null ? String.Empty : fresh.RunId;
            result["policy_sha256"] = policySha256;
            result["reconciliation_process_nonce"] = processNonce;
            result["reconciliation_result"] = discrepancies.Count == 0 ? "RECONCILED_REAL_EXECUTIONS" : "REJECTED";
            result["resolved_terminal_count"] = (candidate == null ? 0 : 1) + (fresh == null ? 0 : 1);
            result["run_id"] = runId;
            result["schema_version"] = R7Constants.SchemaVersion;
            result["service_binary_sha256"] = serviceSha256;
            result["synthetic_result_class_absent"] = discrepancies.Count == 0;
            result["worker_binary_sha256"] = workerSha256;
            return result;
        }

        private static R7WorkerTerminalView VerifyWorkerTerminal(string locator, RSA publicKey, string serviceSha256, string policySha256, string workerSha256)
        {
            string identity = R7Support.ParseLocator(locator, "terminal");
            IDictionary<string, object> payload = R7Support.VerifySignedEnvelope(R7Support.ReadContentAddressed(locator, "terminal"), publicKey);
            if (!String.Equals(StrictJson.RequireString(payload, "artifact_type"), "R7_SIGNED_TERMINAL_RECEIPT", StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "interface_version"), R7Constants.InterfaceVersion, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "schema_version"), R7Constants.SchemaVersion, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "terminal_verifier_result"), "SEMANTICALLY_VERIFIED", StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "case_definition_git_blob"), R7Constants.CaseDefinitionGitBlob, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "case_definition_sha256"), R7Constants.CaseDefinitionSha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "expectation_git_blob"), R7Constants.ExpectationGitBlob, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "expectation_sha256"), R7Constants.ExpectationSha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "policy_sha256"), policySha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "service_binary_sha256"), serviceSha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "worker_sha256"), workerSha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "subject_commit"), R7Constants.SubjectCommit, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "service_sid"), R7Constants.ServiceSid, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "public_key_identity"), R7Constants.PublicKeyIdentity, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "ledger_id"), R7Constants.LedgerId, StringComparison.Ordinal) ||
                R7Support.RequireLong(payload, "case_count") != R7Constants.RequiredCaseCount)
                throw new InvalidDataException("RECONCILER_TERMINAL_FIXED_AUTHORITY");
            string runId = R7Support.RequireLowerHex(payload, "run_id", 64);
            string runNonce = R7Support.RequireLowerHex(payload, "run_nonce", 64);
            string attemptId = R7Support.RequireLowerHex(payload, "attempt_id", 64);
            string phase = R7Support.RequireEnum(payload, "phase", "CANDIDATE", "FRESH");
            string configuration = StrictJson.RequireString(payload, "configuration");
            if (!AllowedConfiguration(configuration)) throw new InvalidDataException("RECONCILER_CONFIGURATION_REJECTED");
            SortedDictionary<string, object> claimBase = new SortedDictionary<string, object>(payload, StringComparer.Ordinal);
            string claim = StrictJson.RequireString(claimBase, "terminal_claim_identity");
            claimBase.Remove("ledger_reservation_entry_identity");
            claimBase.Remove("ledger_reservation_prior_root");
            claimBase.Remove("ledger_reservation_sequence");
            claimBase.Remove("terminal_claim_identity");
            if (!String.Equals(claim, CryptoUtil.Sha256Hex(CanonicalJson.SerializeBytes(claimBase)), StringComparison.Ordinal))
                throw new InvalidDataException("RECONCILER_TERMINAL_CLAIM");
            R7LedgerState ledger = R7Support.VerifyLedger(publicKey);
            IDictionary<string, object> commit = R7Support.FindLedgerEntry(ledger, "R7_TERMINAL_RECEIPT_COMMITTED", identity);
            if (!String.Equals(StrictJson.RequireString(commit, "subject_id"), runId, StringComparison.Ordinal))
                throw new InvalidDataException("RECONCILER_TERMINAL_LEDGER_SUBJECT");
            string reservationIdentity = StrictJson.RequireString(payload, "ledger_reservation_entry_identity");
            IDictionary<string, object> reservation = FindWorkerLedgerEntry(ledger, reservationIdentity);
            if (!String.Equals(StrictJson.RequireString(reservation, "operation"), "R7_TERMINAL_RESERVED", StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(reservation, "subject_id"), runId, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(reservation, "content_address"), claim, StringComparison.Ordinal) ||
                R7Support.RequireLong(reservation, "sequence") != R7Support.RequireLong(payload, "ledger_reservation_sequence"))
                throw new InvalidDataException("RECONCILER_TERMINAL_RESERVATION");

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
                R7Support.RequireLong(comparison, "discrepancy_count") != 0 ||
                R7Support.RequireArray(comparison, "discrepancies").Length != 0 ||
                R7Support.RequireLong(comparison, "resolved_case_count") != R7Constants.RequiredCaseCount)
                throw new InvalidDataException("RECONCILER_TERMINAL_CHILD_BINDING");
            VerifyWorkerEvents(runId, eventSource, observationSource, traceSource, ledger, publicKey);
            if (!String.Equals(StrictJson.RequireString(eventSource, "event_root"), StrictJson.RequireString(payload, "event_root"), StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(eventSource, "subject_run_id"), StrictJson.RequireString(payload, "subject_run_id"), StringComparison.Ordinal))
                throw new InvalidDataException("RECONCILER_EVENT_ROOT_BINDING");

            R7WorkerTerminalView terminal = new R7WorkerTerminalView();
            terminal.AttemptId = attemptId;
            terminal.Configuration = configuration;
            terminal.EventRoot = StrictJson.RequireString(eventSource, "event_root");
            terminal.Locator = locator;
            terminal.Phase = phase;
            terminal.ReceiptIdentity = identity;
            terminal.RunId = runId;
            terminal.RunNonce = runNonce;
            terminal.Payload = payload;
            VerifyWorkerProcesses(processIndex, payload, runId, ledger, publicKey, workerSha256, terminal.ProcessIdentities);
            return terminal;
        }

        private static void VerifyWorkerEvents(string runId, IDictionary<string, object> source, IDictionary<string, object> observationSource,
            IDictionary<string, object> traceSource, R7LedgerState ledger, RSA publicKey)
        {
            object[] events = R7Support.RequireArray(source, "events");
            object[] observations = R7Support.RequireArray(observationSource, "observations");
            object[] traces = R7Support.RequireArray(traceSource, "rows");
            object[] caseRows = R7Support.RequireArray(R7Support.ReadCaseAuthority(), "cases");
            object[] expectationRows = R7Support.RequireArray(R7Support.ReadExpectationAuthority(), "expectations");
            if (events.Length != R7Constants.RequiredCaseCount || observations.Length != events.Length || traces.Length != events.Length ||
                caseRows.Length != events.Length || expectationRows.Length != events.Length)
                throw new InvalidDataException("RECONCILER_TERMINAL_COVERAGE");
            Dictionary<string, IDictionary<string, object>> expected = WorkerIndex(expectationRows);
            Dictionary<string, IDictionary<string, object>> definitions = WorkerIndex(caseRows);
            Dictionary<string, IDictionary<string, object>> observed = WorkerIndex(observations);
            Dictionary<string, IDictionary<string, object>> trace = WorkerIndex(traces);
            HashSet<string> governed = new HashSet<string>(caseRows.Cast<IDictionary<string, object>>().Select(delegate(IDictionary<string, object> row) { return StrictJson.RequireString(row, "case_id"); }), StringComparer.Ordinal);
            HashSet<string> seen = new HashSet<string>(StringComparer.Ordinal);
            string prior = R7Constants.ZeroHash;
            foreach (object raw in events)
            {
                IDictionary<string, object> current = raw as IDictionary<string, object>;
                if (current == null) throw new InvalidDataException("RECONCILER_EVENT_SHAPE");
                string caseId = StrictJson.RequireString(current, "case_id");
                if (!seen.Add(caseId) || !governed.Contains(caseId) || !expected.ContainsKey(caseId) || !observed.ContainsKey(caseId) || !trace.ContainsKey(caseId))
                    throw new InvalidDataException("RECONCILER_CASE_SET");
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
                    !String.Equals(StrictJson.RequireString(current, "target_process_binary_sha256"), R7Constants.SubjectPythonSha256, StringComparison.Ordinal))
                    throw new InvalidDataException("RECONCILER_CURRENT_EXECUTION");
                IDictionary<string, object> wanted = expected[caseId];
                if (!String.Equals(StrictJson.RequireString(current, "public_interface"), StrictJson.RequireString(wanted, "expected_interface"), StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "actual_outcome"), StrictJson.RequireString(wanted, "expected_outcome"), StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "response_classification"), StrictJson.RequireString(wanted, "expected_response_classification"), StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "enforcing_function"), StrictJson.RequireString(wanted, "expected_enforcing_function"), StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "actual_authority_identity"), StrictJson.RequireString(wanted, "expected_authority_source"), StringComparison.Ordinal))
                    throw new InvalidDataException("RECONCILER_EXPECTATION_MISMATCH");
                byte[] requestBytes = R7Support.ReadContentAddressed(StrictJson.RequireString(current, "public_request_locator"), "evidence");
                byte[] responseBytes = R7Support.ReadContentAddressed(StrictJson.RequireString(current, "public_response_locator"), "evidence");
                if (!String.Equals(CryptoUtil.Sha256Hex(requestBytes), StrictJson.RequireString(current, "request_sha256"), StringComparison.Ordinal) ||
                    !String.Equals(CryptoUtil.Sha256Hex(responseBytes), StrictJson.RequireString(current, "response_sha256"), StringComparison.Ordinal))
                    throw new InvalidDataException("RECONCILER_REQUEST_RESPONSE_IDENTITY");
                IDictionary<string, object> request = R7Support.ParseCanonicalObject(requestBytes);
                StrictJson.RequireExactKeys(request, "case_id", "operation");
                IDictionary<string, object> response = R7Support.ParseCanonicalObject(responseBytes);
                if (!String.Equals(StrictJson.RequireString(request, "case_id"), caseId, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(request, "operation"), "execute_case", StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(response, "status"), "OK", StringComparison.Ordinal))
                    throw new InvalidDataException("RECONCILER_PUBLIC_INTERFACE_BYTES");
                IDictionary<string, object> result = StrictJson.RequireObject(response, "result");
                IDictionary<string, object> outcome = StrictJson.RequireObject(result, "outcome");
                if (!String.Equals(StrictJson.RequireString(result, "case_id"), caseId, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(outcome, "status"), StrictJson.RequireString(current, "actual_outcome"), StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(outcome, "code"), StrictJson.RequireString(current, "response_classification"), StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(outcome, "enforcing_function"), StrictJson.RequireString(current, "enforcing_function"), StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(outcome, "authority_identity"), StrictJson.RequireString(current, "actual_authority_identity"), StringComparison.Ordinal))
                    throw new InvalidDataException("RECONCILER_RESPONSE_DERIVATION");
                IDictionary<string, object> innerEvent = StrictJson.RequireObject(result, "event");
                IDictionary<string, object> executionReceipt = StrictJson.RequireObject(result, "execution_receipt");
                if (!String.Equals(StrictJson.RequireString(innerEvent, "event_hash"), StrictJson.RequireString(current, "inner_event_hash"), StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(executionReceipt, "receipt_identity"), StrictJson.RequireString(current, "inner_execution_receipt_identity"), StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(observed[caseId], "event_hash"), StrictJson.RequireString(current, "event_hash"), StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(observed[caseId], "actual_outcome"), StrictJson.RequireString(current, "actual_outcome"), StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(observed[caseId], "response_classification"), StrictJson.RequireString(current, "response_classification"), StringComparison.Ordinal) ||
                    !R7Support.RequireBool(observed[caseId], "interface_invoked") || !R7Support.RequireBool(observed[caseId], "forbidden_side_effect_absent") ||
                    R7Support.RequireLong(observed[caseId], "outer_ledger_delta") != 0 || R7Support.RequireLong(observed[caseId], "subject_event_ledger_delta") < 1 ||
                    !String.Equals(StrictJson.RequireString(trace[caseId], "event_hash"), StrictJson.RequireString(current, "event_hash"), StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(trace[caseId], "case_definition_git_blob"), R7Constants.CaseDefinitionGitBlob, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(trace[caseId], "expectation_git_blob"), R7Constants.ExpectationGitBlob, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(trace[caseId], "public_interface"), StrictJson.RequireString(current, "public_interface"), StringComparison.Ordinal))
                    throw new InvalidDataException("RECONCILER_OBSERVATION_OR_TRACE");
                string suiteLocator = StrictJson.RequireString(current, "suite_process_receipt_locator");
                string suiteIdentity = R7Support.ParseLocator(suiteLocator, "evidence");
                IDictionary<string, object> processReceipt = R7Support.VerifySignedEnvelope(R7Support.ReadContentAddressed(suiteLocator, "evidence"), publicKey);
                if (!String.Equals(StrictJson.RequireString(processReceipt, "run_id"), runId, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(processReceipt, "mode"), "execute-real-suite", StringComparison.Ordinal) ||
                    R7Support.RequireLong(processReceipt, "subject_process_id") != R7Support.RequireLong(current, "subject_process_id") ||
                    !String.Equals(StrictJson.RequireString(current, "invoking_process_receipt_identity"), suiteIdentity, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "event_constructor_binary_sha256"), StrictJson.RequireString(processReceipt, "parent_service_binary_sha256"), StringComparison.Ordinal))
                    throw new InvalidDataException("RECONCILER_SUITE_PROCESS");
                VerifyFixtureProcessEvidence(runId, definitions[caseId], current, observed[caseId], processReceipt);
                R7Support.FindLedgerEntry(ledger, "R7_REAL_SUITE_PROCESS_COMPLETED", suiteIdentity);
                SortedDictionary<string, object> core = new SortedDictionary<string, object>(current, StringComparer.Ordinal);
                string recorded = StrictJson.RequireString(core, "event_hash");
                core.Remove("event_hash");
                if (!String.Equals(recorded, CryptoUtil.Sha256Hex(CanonicalJson.SerializeBytes(core)), StringComparison.Ordinal))
                    throw new InvalidDataException("RECONCILER_EVENT_HASH");
                prior = recorded;
            }
            if (seen.Count != R7Constants.RequiredCaseCount || !String.Equals(prior, StrictJson.RequireString(source, "event_root"), StringComparison.Ordinal))
                throw new InvalidDataException("RECONCILER_EVENT_CHAIN");
        }

        private static void VerifyWorkerProcesses(IDictionary<string, object> index, IDictionary<string, object> terminalPayload, string runId,
            R7LedgerState ledger, RSA publicKey, string workerSha256, HashSet<string> identities)
        {
            string[] keys = new string[] { "suite_process_receipt_locator", "observation_process_receipt_locator", "comparator_process_receipt_locator" };
            foreach (string key in keys)
            {
                string locator = StrictJson.RequireString(index, key);
                string identity = R7Support.ParseLocator(locator, "evidence");
                if (!identities.Add(identity)) throw new InvalidDataException("RECONCILER_PROCESS_RECEIPT_REUSE");
                IDictionary<string, object> receipt = R7Support.VerifySignedEnvelope(R7Support.ReadContentAddressed(locator, "evidence"), publicKey);
                if (!String.Equals(StrictJson.RequireString(receipt, "run_id"), runId, StringComparison.Ordinal))
                    throw new InvalidDataException("RECONCILER_PROCESS_RUN");
                if (key == "suite_process_receipt_locator")
                {
                    if (!String.Equals(locator, StrictJson.RequireString(terminalPayload, "suite_process_receipt_locator"), StringComparison.Ordinal) ||
                        !String.Equals(StrictJson.RequireString(receipt, "mode"), "execute-real-suite", StringComparison.Ordinal) ||
                        !String.Equals(StrictJson.RequireString(receipt, "launcher_sha256"), R7Constants.SubjectLauncherSha256, StringComparison.Ordinal) ||
                        !String.Equals(StrictJson.RequireString(receipt, "subject_commit"), R7Constants.SubjectCommit, StringComparison.Ordinal) ||
                        !String.Equals(StrictJson.RequireString(receipt, "subject_service_sha256"), R7Constants.SubjectServiceSha256, StringComparison.Ordinal) ||
                        !String.Equals(StrictJson.RequireString(receipt, "python_sha256"), R7Constants.SubjectPythonSha256, StringComparison.Ordinal) ||
                        R7Support.RequireLong(receipt, "case_count") != R7Constants.RequiredCaseCount)
                        throw new InvalidDataException("RECONCILER_SUITE_MEASUREMENT");
                    IDictionary<string, object> token = StrictJson.RequireObject(receipt, "subject_token_evidence");
                    byte[] launchBytes = R7Support.ReadContentAddressed(StrictJson.RequireString(receipt, "launch_receipt_locator"), "evidence");
                    IDictionary<string, object> launch = R7Support.ParseCanonicalObject(launchBytes);
                    if (!String.Equals(StrictJson.RequireString(token, "user_sid"), R7Constants.ServiceSid, StringComparison.Ordinal) || R7Support.RequireBool(token, "is_administrator") ||
                        !String.Equals(CanonicalJson.Serialize(token), CanonicalJson.Serialize(launch), StringComparison.Ordinal) ||
                        !String.Equals(CryptoUtil.Sha256Hex(launchBytes), StrictJson.RequireString(receipt, "subject_token_evidence_identity"), StringComparison.Ordinal))
                        throw new InvalidDataException("RECONCILER_SUITE_PRINCIPAL");
                    R7Support.FindLedgerEntry(ledger, "R7_REAL_SUITE_PROCESS_COMPLETED", identity);
                }
                else
                {
                    string mode = key == "observation_process_receipt_locator" ? "derive-observations" : "compare";
                    string resultLocator = key == "observation_process_receipt_locator" ? StrictJson.RequireString(terminalPayload, "observation_locator") : StrictJson.RequireString(terminalPayload, "comparator_result_locator");
                    if (!String.Equals(StrictJson.RequireString(receipt, "mode"), mode, StringComparison.Ordinal) ||
                        !String.Equals(StrictJson.RequireString(receipt, "worker_sha256"), workerSha256, StringComparison.Ordinal))
                        throw new InvalidDataException("RECONCILER_WORKER_MEASUREMENT");
                    IDictionary<string, object> workerOutput = StrictJson.RequireObject(receipt, "result");
                    IDictionary<string, object> workerResult = StrictJson.RequireObject(workerOutput, "result");
                    IDictionary<string, object> storedResult = ReadEvidence(resultLocator);
                    if (!String.Equals(CanonicalJson.Serialize(workerResult), CanonicalJson.Serialize(storedResult), StringComparison.Ordinal))
                        throw new InvalidDataException("RECONCILER_WORKER_RESULT_BINDING");
                    R7Support.FindLedgerEntry(ledger, "R7_PROCESS_COMPLETED", identity);
                }
            }
        }

        private static IDictionary<string, object> FindWorkerLedgerEntry(R7LedgerState ledger, string identity)
        {
            for (int index = 0; index < ledger.EntryIdentities.Count; index++)
                if (String.Equals(ledger.EntryIdentities[index], identity, StringComparison.Ordinal)) return ledger.Payloads[index];
            throw new InvalidDataException("RECONCILER_LEDGER_ENTRY_UNRESOLVED");
        }

        private static Dictionary<string, IDictionary<string, object>> WorkerIndex(object[] rows)
        {
            Dictionary<string, IDictionary<string, object>> result = new Dictionary<string, IDictionary<string, object>>(StringComparer.Ordinal);
            foreach (object raw in rows)
            {
                IDictionary<string, object> row = raw as IDictionary<string, object>;
                if (row == null) throw new InvalidDataException("RECONCILER_INDEX_SHAPE");
                string caseId = StrictJson.RequireString(row, "case_id");
                if (result.ContainsKey(caseId)) throw new InvalidDataException("RECONCILER_INDEX_DUPLICATE");
                result.Add(caseId, row);
            }
            return result;
        }

        private static bool AllowedConfiguration(string configuration)
        {
            return String.Equals(configuration, "SHORT_AUTOCRLF_TRUE", StringComparison.Ordinal) ||
                String.Equals(configuration, "SHORT_AUTOCRLF_FALSE", StringComparison.Ordinal) ||
                String.Equals(configuration, "LONG_AUTOCRLF_TRUE", StringComparison.Ordinal) ||
                String.Equals(configuration, "LONG_AUTOCRLF_FALSE", StringComparison.Ordinal);
        }

        private static void RejectSame(List<object> discrepancies, string code, string left, string right)
        {
            if (String.Equals(left, right, StringComparison.Ordinal)) Add(discrepancies, String.Empty, code, "candidate and fresh identities are equal");
        }

        private static void VerifyCase(string runId, IDictionary<string, object> definition, IDictionary<string, object> expected,
            IDictionary<string, object> actual, IDictionary<string, object> observed, IDictionary<string, object> trace,
            R7LedgerState ledger, RSA publicKey, List<object> discrepancies)
        {
            string caseId = StrictJson.RequireString(definition, "case_id");
            Equal(discrepancies, caseId, "EVENT_RUN", StrictJson.RequireString(actual, "run_id"), runId);
            Equal(discrepancies, caseId, "CASE_BLOB", StrictJson.RequireString(actual, "case_definition_git_blob"), R7Constants.CaseDefinitionGitBlob);
            Equal(discrepancies, caseId, "EXPECTATION_BLOB", StrictJson.RequireString(actual, "expectation_git_blob"), R7Constants.ExpectationGitBlob);
            Equal(discrepancies, caseId, "INTERFACE", StrictJson.RequireString(actual, "public_interface"), StrictJson.RequireString(expected, "expected_interface"));
            Equal(discrepancies, caseId, "OUTCOME", StrictJson.RequireString(actual, "actual_outcome"), StrictJson.RequireString(expected, "expected_outcome"));
            Equal(discrepancies, caseId, "CLASSIFICATION", StrictJson.RequireString(actual, "response_classification"), StrictJson.RequireString(expected, "expected_response_classification"));
            Equal(discrepancies, caseId, "ENFORCING_FUNCTION", StrictJson.RequireString(actual, "enforcing_function"), StrictJson.RequireString(expected, "expected_enforcing_function"));
            Equal(discrepancies, caseId, "AUTHORITY_IDENTITY", StrictJson.RequireString(actual, "actual_authority_identity"), StrictJson.RequireString(expected, "expected_authority_source"));
            Equal(discrepancies, caseId, "INTERFACE_IDENTITY", StrictJson.RequireString(actual, "interface_identity"), R7Constants.SubjectDirectInterfaceSha256);
            Equal(discrepancies, caseId, "INTERFACE_OPERATION", StrictJson.RequireString(actual, "interface_operation"), "execute_case");
            Equal(discrepancies, caseId, "SUBJECT_SERVICE_BINARY", StrictJson.RequireString(actual, "subject_service_sha256"), R7Constants.SubjectServiceSha256);
            Equal(discrepancies, caseId, "TARGET_PROCESS_BINARY", StrictJson.RequireString(actual, "target_process_binary_sha256"), R7Constants.SubjectPythonSha256);
            if (!R7Support.RequireBool(actual, "interface_invoked") || !R7Support.RequireBool(observed, "interface_invoked")) Add(discrepancies, caseId, "INTERFACE_NOT_INVOKED", "measured invocation evidence is absent");
            if (!R7Support.RequireBool(actual, "forbidden_side_effect_absent") || !R7Support.RequireBool(observed, "forbidden_side_effect_absent")) Add(discrepancies, caseId, "FORBIDDEN_SIDE_EFFECT", "forbidden outer authority effect is present or unresolved");
            long outerDelta = R7Support.RequireLong(actual, "outer_post_ledger_sequence") - R7Support.RequireLong(actual, "outer_pre_ledger_sequence");
            if (outerDelta != 0 || R7Support.RequireLong(observed, "outer_ledger_delta") != 0) Add(discrepancies, caseId, "OUTER_LEDGER_DELTA", "case changed the outer ledger");
            if (R7Support.RequireLong(actual, "subject_event_ledger_delta") < 1 || R7Support.RequireLong(observed, "subject_event_ledger_delta") < 1) Add(discrepancies, caseId, "SUBJECT_LEDGER_DELTA", "subject event append is absent");

            byte[] requestBytes = R7Support.ReadContentAddressed(StrictJson.RequireString(actual, "public_request_locator"), "evidence");
            byte[] responseBytes = R7Support.ReadContentAddressed(StrictJson.RequireString(actual, "public_response_locator"), "evidence");
            Equal(discrepancies, caseId, "REQUEST_HASH", CryptoUtil.Sha256Hex(requestBytes), StrictJson.RequireString(actual, "request_sha256"));
            Equal(discrepancies, caseId, "RESPONSE_HASH", CryptoUtil.Sha256Hex(responseBytes), StrictJson.RequireString(actual, "response_sha256"));
            IDictionary<string, object> request = R7Support.ParseCanonicalObject(requestBytes);
            StrictJson.RequireExactKeys(request, "case_id", "operation");
            Equal(discrepancies, caseId, "REQUEST_CASE", StrictJson.RequireString(request, "case_id"), caseId);
            Equal(discrepancies, caseId, "REQUEST_OPERATION", StrictJson.RequireString(request, "operation"), "execute_case");
            IDictionary<string, object> response = R7Support.ParseCanonicalObject(responseBytes);
            Equal(discrepancies, caseId, "RESPONSE_PROTOCOL", StrictJson.RequireString(response, "status"), "OK");
            IDictionary<string, object> result = StrictJson.RequireObject(response, "result");
            Equal(discrepancies, caseId, "RESULT_CASE", StrictJson.RequireString(result, "case_id"), caseId);
            IDictionary<string, object> outcome = StrictJson.RequireObject(result, "outcome");
            Equal(discrepancies, caseId, "RAW_OUTCOME", StrictJson.RequireString(outcome, "status"), StrictJson.RequireString(actual, "actual_outcome"));
            Equal(discrepancies, caseId, "RAW_CODE", StrictJson.RequireString(outcome, "code"), StrictJson.RequireString(actual, "response_classification"));
            Equal(discrepancies, caseId, "RAW_FUNCTION", StrictJson.RequireString(outcome, "enforcing_function"), StrictJson.RequireString(actual, "enforcing_function"));
            Equal(discrepancies, caseId, "RAW_AUTHORITY", StrictJson.RequireString(outcome, "authority_identity"), StrictJson.RequireString(actual, "actual_authority_identity"));
            IDictionary<string, object> innerEvent = StrictJson.RequireObject(result, "event");
            Equal(discrepancies, caseId, "INNER_EVENT", StrictJson.RequireString(innerEvent, "event_hash"), StrictJson.RequireString(actual, "inner_event_hash"));
            IDictionary<string, object> executionReceipt = StrictJson.RequireObject(result, "execution_receipt");
            Equal(discrepancies, caseId, "INNER_EXECUTION_RECEIPT", StrictJson.RequireString(executionReceipt, "receipt_identity"), StrictJson.RequireString(actual, "inner_execution_receipt_identity"));

            string suiteLocator = StrictJson.RequireString(actual, "suite_process_receipt_locator");
            string suiteIdentity = R7Support.ParseLocator(suiteLocator, "evidence");
            IDictionary<string, object> processReceipt = R7Support.VerifySignedEnvelope(R7Support.ReadContentAddressed(suiteLocator, "evidence"), publicKey);
            Equal(discrepancies, caseId, "INVOKING_PROCESS_RECEIPT", StrictJson.RequireString(actual, "invoking_process_receipt_identity"), suiteIdentity);
            Equal(discrepancies, caseId, "EVENT_CONSTRUCTOR_BINARY", StrictJson.RequireString(actual, "event_constructor_binary_sha256"), StrictJson.RequireString(processReceipt, "parent_service_binary_sha256"));
            Equal(discrepancies, caseId, "PROCESS_RUN", StrictJson.RequireString(processReceipt, "run_id"), runId);
            Equal(discrepancies, caseId, "PROCESS_MODE", StrictJson.RequireString(processReceipt, "mode"), "execute-real-suite");
            Equal(discrepancies, caseId, "PROCESS_LAUNCHER", StrictJson.RequireString(processReceipt, "launcher_sha256"), R7Constants.SubjectLauncherSha256);
            if (R7Support.RequireLong(processReceipt, "subject_process_id") != R7Support.RequireLong(actual, "subject_process_id")) Add(discrepancies, caseId, "SUBJECT_PROCESS", "suite process receipt PID mismatch");
            byte[] launchBytes = R7Support.ReadContentAddressed(StrictJson.RequireString(processReceipt, "launch_receipt_locator"), "evidence");
            IDictionary<string, object> launch = R7Support.ParseCanonicalObject(launchBytes);
            if (!String.Equals(StrictJson.RequireString(launch, "launcher_binary_sha256"), R7Constants.SubjectLauncherSha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(launch, "python_binary_sha256"), R7Constants.SubjectPythonSha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(launch, "user_sid"), R7Constants.ServiceSid, StringComparison.Ordinal) ||
                R7Support.RequireBool(launch, "is_administrator") ||
                R7Support.RequireLong(launch, "subject_process_id") != R7Support.RequireLong(actual, "subject_process_id") ||
                !String.Equals(CanonicalJson.Serialize(launch), CanonicalJson.Serialize(StrictJson.RequireObject(processReceipt, "subject_token_evidence")), StringComparison.Ordinal) ||
                !String.Equals(CryptoUtil.Sha256Hex(launchBytes), StrictJson.RequireString(processReceipt, "subject_token_evidence_identity"), StringComparison.Ordinal))
                Add(discrepancies, caseId, "SUBJECT_LAUNCH_EVIDENCE", "measured launcher, inherited token, or Python process binding mismatch");
            try { VerifyFixtureProcessEvidence(runId, definition, actual, observed, processReceipt); }
            catch (Exception exception) { Add(discrepancies, caseId, "FIXTURE_PROCESS_EVIDENCE", exception.Message); }
            try { R7Support.FindLedgerEntry(ledger, "R7_REAL_SUITE_PROCESS_COMPLETED", suiteIdentity); }
            catch (Exception exception) { Add(discrepancies, caseId, "PROCESS_LEDGER_MEMBERSHIP", exception.Message); }
            Equal(discrepancies, caseId, "OBSERVED_EVENT", StrictJson.RequireString(observed, "event_hash"), StrictJson.RequireString(actual, "event_hash"));
            Equal(discrepancies, caseId, "OBSERVED_OUTCOME", StrictJson.RequireString(observed, "actual_outcome"), StrictJson.RequireString(actual, "actual_outcome"));
            Equal(discrepancies, caseId, "OBSERVED_CODE", StrictJson.RequireString(observed, "response_classification"), StrictJson.RequireString(actual, "response_classification"));
            Equal(discrepancies, caseId, "OBSERVED_FIXTURE_RECEIPT", StrictJson.RequireString(observed, "fixture_process_receipt_identity"), StrictJson.RequireString(actual, "fixture_process_receipt_identity"));
            Equal(discrepancies, caseId, "OBSERVED_REPARSE_SNAPSHOT", StrictJson.RequireString(observed, "fixture_reparse_snapshot_identity"), StrictJson.RequireString(actual, "fixture_reparse_snapshot_identity"));
            Equal(discrepancies, caseId, "TRACE_EVENT", StrictJson.RequireString(trace, "event_hash"), StrictJson.RequireString(actual, "event_hash"));
            Equal(discrepancies, caseId, "TRACE_CASE_BLOB", StrictJson.RequireString(trace, "case_definition_git_blob"), R7Constants.CaseDefinitionGitBlob);
            Equal(discrepancies, caseId, "TRACE_EXPECTATION_BLOB", StrictJson.RequireString(trace, "expectation_git_blob"), R7Constants.ExpectationGitBlob);
            Equal(discrepancies, caseId, "TRACE_INTERFACE", StrictJson.RequireString(trace, "public_interface"), StrictJson.RequireString(actual, "public_interface"));
        }

        private static void VerifyFixtureProcessEvidence(string runId, IDictionary<string, object> definition,
            IDictionary<string, object> actual, IDictionary<string, object> observed, IDictionary<string, object> suiteReceipt)
        {
            IDictionary<string, object> sourceCase = StrictJson.RequireObject(definition, "source_case");
            string caseId = StrictJson.RequireString(definition, "case_id");
            bool required = StrictJson.RequireString(sourceCase, "mutation").StartsWith("reparse_substitution_", StringComparison.Ordinal);
            bool invoked = R7Support.RequireBool(actual, "fixture_helper_invoked");
            if (invoked != R7Support.RequireBool(observed, "fixture_helper_invoked")) throw new InvalidDataException("FIXTURE_OBSERVATION_INVOCATION");
            int expectedFixtureCount = 0;
            foreach (object raw in R7Support.RequireArray(R7Support.ReadCaseAuthority(), "cases"))
            {
                IDictionary<string, object> row = raw as IDictionary<string, object>;
                if (row != null && StrictJson.RequireString(StrictJson.RequireObject(row, "source_case"), "mutation").StartsWith("reparse_substitution_", StringComparison.Ordinal)) expectedFixtureCount++;
            }
            if (!String.Equals(StrictJson.RequireString(suiteReceipt, "fixture_host_sha256"), R7Constants.SubjectFixtureHostSha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(suiteReceipt, "fixture_host_file_identity"), R7FileIdentity.Get(R7Constants.SubjectFixtureHostPath), StringComparison.Ordinal) ||
                R7Support.RequireLong(suiteReceipt, "fixture_process_receipt_count") != expectedFixtureCount ||
                !String.Equals(CryptoUtil.Sha256File(R7Constants.SubjectFixtureHostPath), R7Constants.SubjectFixtureHostSha256, StringComparison.Ordinal))
                throw new InvalidDataException("FIXTURE_SUITE_MEASUREMENT");
            if (!required)
            {
                if (invoked || !String.Equals(StrictJson.RequireString(actual, "fixture_body_identity"), R7Constants.ZeroHash, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(actual, "fixture_helper_file_identity"), String.Empty, StringComparison.Ordinal) ||
                    R7Support.RequireLong(actual, "fixture_helper_process_id") != 0 ||
                    !String.Equals(StrictJson.RequireString(actual, "fixture_process_receipt_identity"), R7Constants.ZeroHash, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(actual, "fixture_process_receipt_locator"), String.Empty, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(actual, "fixture_reparse_snapshot_identity"), R7Constants.ZeroHash, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(actual, "fixture_reparse_snapshot_locator"), String.Empty, StringComparison.Ordinal))
                    throw new InvalidDataException("UNEXPECTED_FIXTURE_EVIDENCE");
                return;
            }
            if (!invoked) throw new InvalidDataException("REQUIRED_FIXTURE_INVOCATION_MISSING");
            string locator = StrictJson.RequireString(actual, "fixture_process_receipt_locator");
            string identity = R7Support.ParseLocator(locator, "evidence");
            string snapshotLocator = StrictJson.RequireString(actual, "fixture_reparse_snapshot_locator");
            string snapshotIdentity = R7Support.ParseLocator(snapshotLocator, "evidence");
            if (!String.Equals(identity, StrictJson.RequireString(actual, "fixture_process_receipt_identity"), StringComparison.Ordinal) ||
                !String.Equals(identity, StrictJson.RequireString(observed, "fixture_process_receipt_identity"), StringComparison.Ordinal) ||
                !String.Equals(locator, StrictJson.RequireString(observed, "fixture_process_receipt_locator"), StringComparison.Ordinal) ||
                !String.Equals(snapshotIdentity, StrictJson.RequireString(actual, "fixture_reparse_snapshot_identity"), StringComparison.Ordinal) ||
                !String.Equals(snapshotIdentity, StrictJson.RequireString(observed, "fixture_reparse_snapshot_identity"), StringComparison.Ordinal) ||
                !String.Equals(snapshotLocator, StrictJson.RequireString(observed, "fixture_reparse_snapshot_locator"), StringComparison.Ordinal))
                throw new InvalidDataException("FIXTURE_EVENT_OBSERVATION_BINDING");
            if (R7Support.RequireArray(actual, "raw_evidence_locators").Count(delegate(object value) { return String.Equals(value as string, locator, StringComparison.Ordinal); }) != 1 ||
                R7Support.RequireArray(observed, "evidence_citations").Count(delegate(object value) { return String.Equals(value as string, locator, StringComparison.Ordinal); }) != 1 ||
                R7Support.RequireArray(actual, "raw_evidence_locators").Count(delegate(object value) { return String.Equals(value as string, snapshotLocator, StringComparison.Ordinal); }) != 1 ||
                R7Support.RequireArray(observed, "evidence_citations").Count(delegate(object value) { return String.Equals(value as string, snapshotLocator, StringComparison.Ordinal); }) != 1)
                throw new InvalidDataException("FIXTURE_EVIDENCE_CITATION");
            byte[] bytes = R7Support.ReadContentAddressed(locator, "evidence");
            if (!String.Equals(CryptoUtil.Sha256Hex(bytes), identity, StringComparison.Ordinal)) throw new InvalidDataException("FIXTURE_CONTENT_ADDRESS");
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
                R7Support.RequireLong(receipt, "parent_process_id") != R7Support.RequireLong(actual, "subject_process_id") ||
                R7Support.RequireLong(receipt, "helper_process_id") != R7Support.RequireLong(actual, "fixture_helper_process_id") ||
                !String.Equals(StrictJson.RequireString(receipt, "helper_binary_file_identity"), StrictJson.RequireString(actual, "fixture_helper_file_identity"), StringComparison.Ordinal))
                throw new InvalidDataException("FIXTURE_PROCESS_RECEIPT_AUTHORITY");
            IDictionary<string, object> token = StrictJson.RequireObject(suiteReceipt, "subject_token_evidence");
            if (!String.Equals(StrictJson.RequireString(receipt, "authentication_type"), StrictJson.RequireString(token, "authentication_type"), StringComparison.Ordinal) ||
                !String.Equals(CanonicalJson.Serialize(R7Support.RequireArray(receipt, "group_sids")), CanonicalJson.Serialize(R7Support.RequireArray(token, "group_sids")), StringComparison.Ordinal))
                throw new InvalidDataException("FIXTURE_TOKEN_INHERITANCE");
            SortedDictionary<string, object> body = new SortedDictionary<string, object>(receipt, StringComparer.Ordinal);
            string bodyIdentity = R7Support.RequireLowerHex(body, "body_identity", 64);
            body.Remove("body_identity");
            if (!String.Equals(bodyIdentity, CryptoUtil.Sha256Hex(CanonicalJson.SerializeBytes(body)), StringComparison.Ordinal) ||
                !String.Equals(bodyIdentity, StrictJson.RequireString(actual, "fixture_body_identity"), StringComparison.Ordinal) ||
                !String.Equals(bodyIdentity, StrictJson.RequireString(observed, "fixture_body_identity"), StringComparison.Ordinal) ||
                !R7Support.IsLowerHex(StrictJson.RequireString(receipt, "fixture_nonce"), 64))
                throw new InvalidDataException("FIXTURE_BODY_IDENTITY");

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
                throw new InvalidDataException("FIXTURE_COMMAND_OR_PATH_EVIDENCE");
            byte[] snapshotBytes = R7Support.ReadContentAddressed(snapshotLocator, "evidence");
            if (!String.Equals(CryptoUtil.Sha256Hex(snapshotBytes), snapshotIdentity, StringComparison.Ordinal))
                throw new InvalidDataException("FIXTURE_REPARSE_SNAPSHOT_CONTENT_ADDRESS");
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
                !String.Equals(StrictJson.RequireString(snapshot, "case_id"), caseId, StringComparison.Ordinal) ||
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
                throw new InvalidDataException("FIXTURE_REPARSE_SNAPSHOT_AUTHORITY");
            byte[] reparseData;
            try { reparseData = Convert.FromBase64String(StrictJson.RequireString(snapshot, "reparse_data_base64")); }
            catch (FormatException exception) { throw new InvalidDataException("FIXTURE_REPARSE_SNAPSHOT_BASE64", exception); }
            if (!String.Equals(CryptoUtil.Sha256Hex(reparseData), StrictJson.RequireString(snapshot, "reparse_data_sha256"), StringComparison.Ordinal))
                throw new InvalidDataException("FIXTURE_REPARSE_SNAPSHOT_HASH");
            R7ReparseEvidence.ValidateMountPoint(reparseData, targetPath);
            const string timeFormat = "yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'";
            DateTimeOffset eventStart;
            DateTimeOffset eventEnd;
            DateTimeOffset fixtureStart;
            DateTimeOffset fixtureEnd;
            DateTimeOffset parentStart;
            DateTimeOffset snapshotTime;
            DateTimeOffset suiteCompletionTime;
            DateTimeStyles styles = DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal;
            if (!DateTimeOffset.TryParseExact(StrictJson.RequireString(actual, "public_interface_start_time"), timeFormat, CultureInfo.InvariantCulture, styles, out eventStart) ||
                !DateTimeOffset.TryParseExact(StrictJson.RequireString(actual, "public_interface_end_time"), timeFormat, CultureInfo.InvariantCulture, styles, out eventEnd) ||
                !DateTimeOffset.TryParseExact(StrictJson.RequireString(receipt, "start_time"), timeFormat, CultureInfo.InvariantCulture, styles, out fixtureStart) ||
                !DateTimeOffset.TryParseExact(StrictJson.RequireString(receipt, "end_time"), timeFormat, CultureInfo.InvariantCulture, styles, out fixtureEnd) ||
                !DateTimeOffset.TryParseExact(StrictJson.RequireString(receipt, "parent_start_time"), timeFormat, CultureInfo.InvariantCulture, styles, out parentStart) ||
                !DateTimeOffset.TryParseExact(StrictJson.RequireString(snapshot, "capture_time"), timeFormat, CultureInfo.InvariantCulture, styles, out snapshotTime) ||
                !DateTimeOffset.TryParseExact(StrictJson.RequireString(suiteReceipt, "completion_time"), timeFormat, CultureInfo.InvariantCulture, styles, out suiteCompletionTime) ||
                parentStart > fixtureStart || fixtureStart < eventStart || fixtureEnd < fixtureStart || fixtureEnd > eventEnd ||
                snapshotTime < eventEnd || snapshotTime > suiteCompletionTime)
                throw new InvalidDataException("FIXTURE_CURRENT_EVENT_TIME");
        }

        private static IDictionary<string, object> ReadEvidence(string locator)
        {
            return R7Support.ParseCanonicalObject(R7Support.ReadContentAddressed(locator, "evidence"));
        }

        private static void RequireEventSource(IDictionary<string, object> value, string runId)
        {
            StrictJson.RequireExactKeys(value, "artifact_type", "case_definition_git_blob", "event_count", "event_root", "events", "expectation_git_blob", "run_id", "schema_version", "subject_run_id", "suite_process_receipt_locator");
            if (!String.Equals(StrictJson.RequireString(value, "artifact_type"), "R7_CURRENT_EXECUTION_EVENTS", StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(value, "run_id"), runId, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(value, "case_definition_git_blob"), R7Constants.CaseDefinitionGitBlob, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(value, "expectation_git_blob"), R7Constants.ExpectationGitBlob, StringComparison.Ordinal) ||
                R7Support.RequireLong(value, "event_count") != R7Constants.RequiredCaseCount ||
                R7Support.RequireArray(value, "events").Length != R7Constants.RequiredCaseCount)
                throw new InvalidDataException("EVENT_SOURCE_BINDING");
        }

        private static Dictionary<string, IDictionary<string, object>> Index(object[] rows, string role, List<object> discrepancies)
        {
            Dictionary<string, IDictionary<string, object>> result = new Dictionary<string, IDictionary<string, object>>(StringComparer.Ordinal);
            foreach (object raw in rows)
            {
                IDictionary<string, object> row = raw as IDictionary<string, object>;
                if (row == null) { Add(discrepancies, String.Empty, role + "_SHAPE", "row is not an object"); continue; }
                string caseId = StrictJson.RequireString(row, "case_id");
                if (result.ContainsKey(caseId)) Add(discrepancies, caseId, role + "_DUPLICATE", "case appears more than once");
                else result.Add(caseId, row);
            }
            return result;
        }

        private static void RejectUnknown(IEnumerable<string> actual, HashSet<string> governed, string role, List<object> discrepancies)
        {
            foreach (string caseId in actual) if (!governed.Contains(caseId)) Add(discrepancies, caseId, role + "_UNKNOWN", "unknown extra case");
        }

        private static void Count(List<object> discrepancies, string code, int actual, int expected)
        {
            if (actual != expected) Add(discrepancies, String.Empty, code, actual.ToString(CultureInfo.InvariantCulture) + " != " + expected.ToString(CultureInfo.InvariantCulture));
        }

        private static void Equal(List<object> discrepancies, string caseId, string code, string actual, string expected)
        {
            if (!String.Equals(actual, expected, StringComparison.Ordinal)) Add(discrepancies, caseId, code, actual + " != " + expected);
        }

        private static void Add(List<object> values, string caseId, string code, string detail)
        {
            SortedDictionary<string, object> value = new SortedDictionary<string, object>(StringComparer.Ordinal);
            value["case_id"] = caseId;
            value["code"] = code;
            value["detail"] = detail;
            values.Add(value);
        }
    }
}
