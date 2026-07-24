using Microsoft.Win32;
using Microsoft.Win32.SafeHandles;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.IO.Pipes;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security;
using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Security.Principal;
using System.ServiceProcess;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;

namespace RandleAI.TerminalAuthority
{
    internal static class R7BuildConstants
    {
        internal const string PolicySha256 = "76eb2900b2000aa0b41e6040335cc323f7443728aad21cd871d5b6b8e17bcd8b";
        internal const string WorkerSha256 = "b2971b85de73d999bfa801d047b22c2ec6fc3d6bc5cb5923ea4a9ab240ed4401";
    }

    internal sealed class R7AppendResult
    {
        internal long Sequence;
        internal string EntryHash;
        internal string EntryIdentity;
        internal string CheckpointIdentity;
    }

    internal sealed class R7DurableLedger
    {
        private readonly object sync = new object();
        private readonly RSA signer;
        private readonly RSA verifier;
        private readonly List<IDictionary<string, object>> payloads = new List<IDictionary<string, object>>();
        private readonly List<string> identities = new List<string>();
        private long sequence;
        private string rootHash;
        private string genesisIdentity;
        private bool faulted;

        internal R7DurableLedger(RSA signer, RSA verifier)
        {
            this.signer = signer;
            this.verifier = verifier;
            Reload();
        }

        internal long Sequence { get { lock (sync) { return sequence; } } }
        internal string RootHash { get { lock (sync) { return rootHash; } } }
        internal string GenesisIdentity { get { lock (sync) { return genesisIdentity; } } }
        internal string CheckpointIdentity
        {
            get
            {
                lock (sync)
                {
                    return CryptoUtil.Sha256File(Path.Combine(R7Constants.LedgerRoot, "checkpoint.json"));
                }
            }
        }

        internal bool ContainsRequestNonce(string requestNonce)
        {
            lock (sync)
            {
                foreach (IDictionary<string, object> payload in payloads)
                {
                    object value;
                    if (payload.TryGetValue("request_nonce", out value) &&
                        String.Equals(value as string, requestNonce, StringComparison.Ordinal)) return true;
                }
                return false;
            }
        }

        internal bool ContainsSubject(string operation, string subjectId)
        {
            return FindBySubject(operation, subjectId) != null;
        }

        internal IDictionary<string, object> FindBySubject(string operation, string subjectId)
        {
            lock (sync)
            {
                IDictionary<string, object> found = null;
                foreach (IDictionary<string, object> payload in payloads)
                {
                    if (String.Equals(StrictJson.RequireString(payload, "operation"), operation, StringComparison.Ordinal) &&
                        String.Equals(StrictJson.RequireString(payload, "subject_id"), subjectId, StringComparison.Ordinal))
                    {
                        if (found != null) throw new InvalidDataException("duplicate ledger subject");
                        found = payload;
                    }
                }
                return found;
            }
        }

        internal IDictionary<string, object> FindByContent(string operation, string contentAddress)
        {
            lock (sync)
            {
                IDictionary<string, object> found = null;
                foreach (IDictionary<string, object> payload in payloads)
                {
                    if (String.Equals(StrictJson.RequireString(payload, "operation"), operation, StringComparison.Ordinal) &&
                        String.Equals(StrictJson.RequireString(payload, "content_address"), contentAddress, StringComparison.Ordinal))
                    {
                        if (found != null) throw new InvalidDataException("duplicate ledger content address");
                        found = payload;
                    }
                }
                return found;
            }
        }

        internal R7AppendResult Append(string operation, string requestNonce, string subjectId, string contentAddress)
        {
            lock (sync)
            {
                if (faulted) throw new InvalidOperationException("LEDGER_FAULTED_RESTART_AND_GOVERNED_RECOVERY_REQUIRED");
                if (!String.IsNullOrEmpty(requestNonce) && ContainsRequestNonce(requestNonce))
                    throw new InvalidOperationException("REQUEST_NONCE_REPLAY");
                long next = checked(sequence + 1);
                SortedDictionary<string, object> core = new SortedDictionary<string, object>(StringComparer.Ordinal);
                core["content_address"] = contentAddress;
                core["issue_time"] = R7Support.Timestamp();
                core["ledger_id"] = R7Constants.LedgerId;
                core["operation"] = operation;
                core["prior_entry_hash"] = rootHash;
                core["public_key_identity"] = R7Constants.PublicKeyIdentity;
                core["request_nonce"] = requestNonce ?? String.Empty;
                core["schema_version"] = R7Constants.SchemaVersion;
                core["sequence"] = next;
                core["service_sid"] = R7Constants.ServiceSid;
                core["subject_id"] = subjectId ?? String.Empty;
                string entryHash = CryptoUtil.Sha256Hex(CanonicalJson.SerializeBytes(core));
                SortedDictionary<string, object> payload = new SortedDictionary<string, object>(core, StringComparer.Ordinal);
                payload["entry_hash"] = entryHash;
                byte[] envelopeBytes = R7Support.CreateSignedEnvelope(payload, signer);
                string path = Path.Combine(R7Constants.LedgerRoot, next.ToString("D20", CultureInfo.InvariantCulture) + ".entry.json");
                R7Support.DurableCreate(path, envelopeBytes);
                sequence = next;
                rootHash = entryHash;
                payloads.Add(payload);
                identities.Add(CryptoUtil.Sha256Hex(envelopeBytes));
                string checkpoint;
                try { checkpoint = WriteCheckpoint(); }
                catch
                {
                    faulted = true;
                    throw;
                }
                return new R7AppendResult
                {
                    Sequence = next,
                    EntryHash = entryHash,
                    EntryIdentity = identities[identities.Count - 1],
                    CheckpointIdentity = checkpoint
                };
            }
        }

        private void Reload()
        {
            lock (sync)
            {
                R7LedgerState state = R7Support.VerifyLedger(verifier);
                sequence = state.Sequence;
                rootHash = state.RootHash;
                genesisIdentity = state.GenesisIdentity;
                faulted = false;
                payloads.Clear();
                identities.Clear();
                payloads.AddRange(state.Payloads);
                identities.AddRange(state.EntryIdentities);
            }
        }

        private string WriteCheckpoint()
        {
            SortedDictionary<string, object> payload = new SortedDictionary<string, object>(StringComparer.Ordinal);
            payload["issue_time"] = R7Support.Timestamp();
            payload["ledger_id"] = R7Constants.LedgerId;
            payload["public_key_identity"] = R7Constants.PublicKeyIdentity;
            payload["root_hash"] = rootHash;
            payload["schema_version"] = R7Constants.SchemaVersion;
            payload["sequence"] = sequence;
            payload["service_sid"] = R7Constants.ServiceSid;
            byte[] bytes = R7Support.CreateSignedEnvelope(payload, signer);
            R7Support.DurableReplace(Path.Combine(R7Constants.LedgerRoot, "checkpoint.json"), bytes);
            return CryptoUtil.Sha256Hex(bytes);
        }
    }

    internal sealed class R7ProcessResult
    {
        internal string Mode;
        internal string ProcessNonce;
        internal int ProcessId;
        internal string ReceiptLocator;
        internal string ReceiptIdentity;
        internal IDictionary<string, object> Result;
        internal string InputLocator;
        internal string StdoutLocator;
        internal string StderrLocator;
    }

    internal sealed class R7SubjectExchange
    {
        internal DateTimeOffset EndedAt;
        internal IDictionary<string, object> Response;
        internal string RequestLocator;
        internal string RequestIdentity;
        internal string ResponseLocator;
        internal string ResponseIdentity;
        internal DateTimeOffset StartedAt;
    }

    internal sealed class R7FixtureEvidence
    {
        internal string BodyIdentity;
        internal string HelperFileIdentity;
        internal int HelperProcessId;
        internal bool Invoked;
        internal string Locator;
        internal string ReparseSnapshotIdentity;
        internal string ReparseSnapshotLocator;
        internal string ReceiptIdentity;
    }

    internal sealed class R7SuiteResult
    {
        internal int SubjectLauncherProcessId;
        internal string SubjectLaunchLocator;
        internal int SubjectProcessId;
        internal string SubjectRunId;
        internal string SubjectReadyLocator;
        internal string SubjectStderrLocator;
        internal string SubjectTokenEvidenceIdentity;
        internal IDictionary<string, object> SubjectTokenEvidence;
        internal string RawCaseIndexLocator;
        internal string RawCaseIndexIdentity;
        internal string ProcessReceiptLocator;
        internal string ProcessReceiptIdentity;
        internal int FixtureProcessReceiptCount;
        internal readonly List<IDictionary<string, object>> Cases = new List<IDictionary<string, object>>();
    }

    internal sealed class R7TerminalView
    {
        internal string Locator;
        internal string ReceiptIdentity;
        internal string AttemptId;
        internal string Phase;
        internal string Configuration;
        internal string RunId;
        internal string RunNonce;
        internal string EventIdentity;
        internal string EventRoot;
        internal readonly HashSet<string> ProcessNonces = new HashSet<string>(StringComparer.Ordinal);
        internal IDictionary<string, object> Payload;
    }

    internal static class R7AuthorityCore
    {
        private static readonly object sync = new object();
        private static X509Certificate2 publicCertificate;
        private static RSA verifier;
        private static RSA signer;
        private static R7DurableLedger ledger;
        private static IDictionary<string, object> policy;
        private static string binarySha256;
        private static string binaryFileIdentity;
        private static string pipeAclIdentity;
        private static string ipcIdentity;

        internal static void Initialize(PipeSecurity pipeSecurity)
        {
            lock (sync)
            {
                string currentSid = WindowsIdentity.GetCurrent().User.Value;
                if (!String.Equals(currentSid, R7Constants.ServiceSid, StringComparison.Ordinal)) throw new SecurityException("service SID mismatch");
                string executable = Path.GetFullPath(Assembly.GetExecutingAssembly().Location);
                if (!String.Equals(executable, R7Constants.ServiceExecutablePath, StringComparison.OrdinalIgnoreCase)) throw new SecurityException("service executable path mismatch");
                byte[] policyBytes = File.ReadAllBytes(R7Constants.PolicyPath);
                if (!String.Equals(CryptoUtil.Sha256Hex(policyBytes), R7BuildConstants.PolicySha256, StringComparison.Ordinal))
                    throw new SecurityException("R7 policy identity mismatch");
                policy = R7Support.ParseCanonicalObject(policyBytes);
                ValidatePolicy(policy);
                ValidatePythonRuntime();
                if (!String.Equals(CryptoUtil.Sha256File(R7Constants.WorkerExecutablePath), R7BuildConstants.WorkerSha256, StringComparison.Ordinal))
                    throw new SecurityException("R7 worker identity mismatch");
                publicCertificate = CryptoUtil.LoadPublicCertificate();
                verifier = System.Security.Cryptography.X509Certificates.RSACertificateExtensions.GetRSAPublicKey(publicCertificate);
                CngKey privateKey = CngKey.Open(
                    AuthorityConstants.KeyUniqueName,
                    CngProvider.MicrosoftSoftwareKeyStorageProvider,
                    CngKeyOpenOptions.MachineKey);
                signer = new RSACng(privateKey);
                RSACng cng = signer as RSACng;
                if (cng == null || cng.KeySize != 3072 || cng.Key.ExportPolicy != CngExportPolicies.None)
                    throw new CryptographicException("R7 signing key isolation rejected");
                if (!String.Equals(cng.Key.UniqueName, AuthorityConstants.KeyUniqueName, StringComparison.Ordinal))
                    throw new CryptographicException("R7 key container rejected");
                binarySha256 = CryptoUtil.Sha256File(executable);
                binaryFileIdentity = R7NativeIdentity.GetFileIdentity(executable);
                pipeAclIdentity = CryptoUtil.Sha256Hex(Encoding.UTF8.GetBytes(pipeSecurity.GetSecurityDescriptorSddlForm(AccessControlSections.All)));
                ipcIdentity = CryptoUtil.Sha256Hex(Encoding.UTF8.GetBytes(R7Constants.PipeName + "|" + pipeAclIdentity + "|" + R7Constants.InterfaceVersion));
                Directory.CreateDirectory(R7Constants.EvidenceRoot);
                Directory.CreateDirectory(R7Constants.ReceiptRoot);
                Directory.CreateDirectory(R7Constants.ReconciliationRoot);
                Directory.CreateDirectory(R7Constants.ResponseRoot);
                Directory.CreateDirectory(R7Constants.SessionRoot);
                Directory.CreateDirectory(R7Constants.FixtureReceiptRoot);
                ledger = new R7DurableLedger(signer, verifier);
                string upgradeSubject = CryptoUtil.Sha256Hex(Encoding.UTF8.GetBytes(binarySha256 + "|" + R7BuildConstants.PolicySha256 + "|" + R7BuildConstants.WorkerSha256 + "|" + R7Constants.SubjectFixtureHostSha256));
                if (!ledger.ContainsSubject("R7_SERVICE_UPGRADE_ACTIVATED", upgradeSubject))
                {
                    SortedDictionary<string, object> upgrade = new SortedDictionary<string, object>(StringComparer.Ordinal);
                    upgrade["binary_sha256"] = binarySha256;
                    upgrade["interface_version"] = R7Constants.InterfaceVersion;
                    upgrade["junction_fixture_host_sha256"] = R7Constants.SubjectFixtureHostSha256;
                    upgrade["policy_sha256"] = R7BuildConstants.PolicySha256;
                    upgrade["provisioning_commit"] = R7Constants.ProvisioningCommit;
                    upgrade["service_sid"] = R7Constants.ServiceSid;
                    upgrade["worker_sha256"] = R7BuildConstants.WorkerSha256;
                    string content = CryptoUtil.Sha256Hex(CanonicalJson.SerializeBytes(upgrade));
                    ledger.Append("R7_SERVICE_UPGRADE_ACTIVATED", String.Empty, upgradeSubject, content);
                }
            }
        }

        private static void ValidatePolicy(IDictionary<string, object> value)
        {
            StrictJson.RequireExactKeys(value,
                "adversarial_probe_authority", "allowed_configurations", "allowed_operations", "artifact_type",
                "case_authority", "correction_requirements", "expectation_authority", "fixed_roots",
                "interface_version", "ledger_id", "provisioning_commit", "public_key_identity",
                "python_runtime_manifest", "r6_commit", "r7_records", "schema_version", "service_sid",
                "subject", "synthetic_authority_prohibitions", "threat_model", "worker_sha256");
            if (!String.Equals(StrictJson.RequireString(value, "artifact_type"), "R7_REAL_EXECUTION_TERMINAL_AUTHORITY_POLICY", StringComparison.Ordinal)) throw new InvalidDataException("policy artifact rejected");
            if (!String.Equals(StrictJson.RequireString(value, "interface_version"), R7Constants.InterfaceVersion, StringComparison.Ordinal)) throw new InvalidDataException("policy interface rejected");
            if (!String.Equals(StrictJson.RequireString(value, "schema_version"), R7Constants.SchemaVersion, StringComparison.Ordinal)) throw new InvalidDataException("policy schema rejected");
            if (!String.Equals(StrictJson.RequireString(value, "r6_commit"), R7Constants.R6Commit, StringComparison.Ordinal)) throw new InvalidDataException("policy R6 rejected");
            if (!String.Equals(StrictJson.RequireString(value, "provisioning_commit"), R7Constants.ProvisioningCommit, StringComparison.Ordinal)) throw new InvalidDataException("policy provisioning rejected");
            if (!String.Equals(StrictJson.RequireString(value, "threat_model"), R7Constants.ThreatModel, StringComparison.Ordinal)) throw new InvalidDataException("policy threat model rejected");
            if (!String.Equals(StrictJson.RequireString(value, "ledger_id"), R7Constants.LedgerId, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(value, "public_key_identity"), R7Constants.PublicKeyIdentity, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(value, "service_sid"), R7Constants.ServiceSid, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(value, "worker_sha256"), R7BuildConstants.WorkerSha256, StringComparison.Ordinal)) throw new InvalidDataException("policy fixed identity rejected");
            ValidatePolicyAuthority(StrictJson.RequireObject(value, "case_authority"), R7Constants.CaseDefinitionGitBlob, R7Constants.CaseDefinitionSha256, R7Constants.CaseDefinitionSize, R7Constants.RequiredCaseCount);
            ValidatePolicyAuthority(StrictJson.RequireObject(value, "expectation_authority"), R7Constants.ExpectationGitBlob, R7Constants.ExpectationSha256, R7Constants.ExpectationSize, R7Constants.RequiredCaseCount);
            ValidatePolicyAuthority(StrictJson.RequireObject(value, "adversarial_probe_authority"), R7Constants.AdversarialProbeGitBlob, R7Constants.AdversarialProbeSha256, R7Constants.AdversarialProbeSize, 25);
            IDictionary<string, object> requirements = StrictJson.RequireObject(value, "correction_requirements");
            if (!String.Equals(StrictJson.RequireString(requirements, "git_blob"), R7Constants.CorrectionRequirementsGitBlob, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(requirements, "raw_sha256"), R7Constants.CorrectionRequirementsSha256, StringComparison.Ordinal) ||
                R7Support.RequireLong(requirements, "size") != R7Constants.CorrectionRequirementsSize) throw new InvalidDataException("policy correction requirements rejected");
            IDictionary<string, object> runtime = StrictJson.RequireObject(value, "python_runtime_manifest");
            if (!String.Equals(StrictJson.RequireString(runtime, "git_blob"), R7Constants.PythonRuntimeManifestGitBlob, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(runtime, "raw_sha256"), R7Constants.PythonRuntimeManifestSha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(runtime, "runtime_root_identity"), R7Constants.PythonRuntimeRootIdentity, StringComparison.Ordinal)) throw new InvalidDataException("policy runtime rejected");
            IDictionary<string, object> roots = StrictJson.RequireObject(value, "fixed_roots");
            StrictJson.RequireExactKeys(roots, "evidence", "fixture_process_receipts", "ledger", "receipts", "reconciliations", "responses", "sessions");
            if (!String.Equals(StrictJson.RequireString(roots, "evidence"), R7Constants.EvidenceRoot.Replace('\\', '/'), StringComparison.OrdinalIgnoreCase) ||
                !String.Equals(StrictJson.RequireString(roots, "fixture_process_receipts"), R7Constants.FixtureReceiptRoot.Replace('\\', '/'), StringComparison.OrdinalIgnoreCase) ||
                !String.Equals(StrictJson.RequireString(roots, "ledger"), R7Constants.LedgerRoot.Replace('\\', '/'), StringComparison.OrdinalIgnoreCase) ||
                !String.Equals(StrictJson.RequireString(roots, "receipts"), R7Constants.ReceiptRoot.Replace('\\', '/'), StringComparison.OrdinalIgnoreCase) ||
                !String.Equals(StrictJson.RequireString(roots, "reconciliations"), R7Constants.ReconciliationRoot.Replace('\\', '/'), StringComparison.OrdinalIgnoreCase) ||
                !String.Equals(StrictJson.RequireString(roots, "responses"), R7Constants.ResponseRoot.Replace('\\', '/'), StringComparison.OrdinalIgnoreCase) ||
                !String.Equals(StrictJson.RequireString(roots, "sessions"), R7Constants.SessionRoot.Replace('\\', '/'), StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("policy fixed roots rejected");
            IDictionary<string, object> subject = StrictJson.RequireObject(value, "subject");
            StrictJson.RequireExactKeys(subject, "commit", "direct_interface_sha256", "fixture_host_sha256", "governed_access_sha256", "launcher_sha256", "ledger_sha256", "python_sha256", "repository", "service_sha256", "tree", "verifier_sha256");
            if (!String.Equals(StrictJson.RequireString(subject, "commit"), R7Constants.SubjectCommit, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(subject, "tree"), R7Constants.SubjectTree, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(subject, "service_sha256"), R7Constants.SubjectServiceSha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(subject, "direct_interface_sha256"), R7Constants.SubjectDirectInterfaceSha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(subject, "fixture_host_sha256"), R7Constants.SubjectFixtureHostSha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(subject, "governed_access_sha256"), R7Constants.SubjectGovernedAccessSha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(subject, "launcher_sha256"), R7Constants.SubjectLauncherSha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(subject, "ledger_sha256"), R7Constants.SubjectLedgerSha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(subject, "python_sha256"), R7Constants.SubjectPythonSha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(subject, "repository"), R7Constants.SubjectRepositoryPath.Replace('\\', '/'), StringComparison.OrdinalIgnoreCase) ||
                !String.Equals(StrictJson.RequireString(subject, "verifier_sha256"), R7Constants.SubjectVerifierSha256, StringComparison.Ordinal)) throw new InvalidDataException("policy subject rejected");
            HashSet<string> operations = new HashSet<string>(R7Support.RequireArray(value, "allowed_operations").Select(delegate(object item) { return item as string; }), StringComparer.Ordinal);
            string[] exact = new string[] { "EXECUTE_R7_RUN", "GET_HEALTH", "GET_LEDGER_STATUS", "GET_PUBLIC_TRUST", "GET_R7_RECEIPT", "GET_R7_RECONCILIATION", "ISSUE_R7_ATTEMPT", "RECONCILE_R7_TERMINAL_RECEIPTS" };
            if (!operations.SetEquals(exact)) throw new InvalidDataException("policy operation allowlist rejected");
        }

        private static void ValidatePolicyAuthority(IDictionary<string, object> value, string gitBlob, string rawSha256, long size, long count)
        {
            StrictJson.RequireExactKeys(value, "count", "git_blob", "path", "raw_sha256", "size");
            if (!String.Equals(StrictJson.RequireString(value, "git_blob"), gitBlob, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(value, "raw_sha256"), rawSha256, StringComparison.Ordinal) ||
                R7Support.RequireLong(value, "size") != size || R7Support.RequireLong(value, "count") != count)
                throw new InvalidDataException("policy immutable authority rejected");
        }

        internal static string Process(string requestText, string callerSid)
        {
            try
            {
                if (requestText == null || Encoding.UTF8.GetByteCount(requestText) > R7Constants.MaximumMessageBytes) return Failure("MESSAGE_TOO_LARGE");
                IDictionary<string, object> request = StrictJson.ParseObject(requestText);
                string operation = StrictJson.RequireString(request, "operation");
                ValidateRequestShape(request, operation);
                if (!String.Equals(StrictJson.RequireString(request, "interface_version"), R7Constants.InterfaceVersion, StringComparison.Ordinal)) return Failure("INTERFACE_VERSION_REJECTED");
                string requestNonce = StrictJson.RequireString(request, "request_nonce");
                Guid nonce;
                if (!Guid.TryParseExact(requestNonce, "D", out nonce) || !String.Equals(nonce.ToString("D"), requestNonce, StringComparison.Ordinal)) return Failure("REQUEST_NONCE_INVALID");
                if (!IsAuthorizedCaller(callerSid)) return Failure("CALLER_NOT_AUTHORIZED");
                if (operation == "GET_HEALTH") return Health();
                if (operation == "GET_PUBLIC_TRUST") return PublicTrust();
                if (operation == "GET_LEDGER_STATUS") return LedgerStatus();
                string replay = LoadIdempotentResponse(requestNonce, requestText);
                if (replay != null) return replay;
                string response;
                if (operation == "ISSUE_R7_ATTEMPT") response = IssueAttempt(requestNonce, request);
                else if (operation == "EXECUTE_R7_RUN") response = ExecuteRun(requestNonce, request);
                else if (operation == "GET_R7_RECEIPT") response = Retrieve(request, "terminal");
                else if (operation == "GET_R7_RECONCILIATION") response = Retrieve(request, "reconciliation");
                else if (operation == "RECONCILE_R7_TERMINAL_RECEIPTS") response = Reconcile(requestNonce, request);
                else return Failure("OPERATION_NOT_ALLOWED");
                if (!response.Contains("\"status\":\"REJECTED\"")) StoreIdempotentResponse(requestNonce, requestText, response);
                return response;
            }
            catch (InvalidOperationException exception)
            {
                return Failure(exception.Message);
            }
            catch (Exception exception)
            {
                RecordFault(exception);
                return Failure("REQUEST_REJECTED");
            }
        }

        private static void ValidateRequestShape(IDictionary<string, object> request, string operation)
        {
            if (operation == "ISSUE_R7_ATTEMPT")
                StrictJson.RequireExactKeys(request, "configuration", "interface_version", "operation", "request_nonce");
            else if (operation == "EXECUTE_R7_RUN")
                StrictJson.RequireExactKeys(request, "attempt_id", "interface_version", "operation", "phase", "request_nonce");
            else if (operation == "RECONCILE_R7_TERMINAL_RECEIPTS")
                StrictJson.RequireExactKeys(request, "attempt_id", "candidate_locator", "fresh_locator", "interface_version", "operation", "request_nonce");
            else if (operation == "GET_R7_RECEIPT" || operation == "GET_R7_RECONCILIATION")
                StrictJson.RequireExactKeys(request, "interface_version", "locator", "operation", "request_nonce");
            else
                StrictJson.RequireExactKeys(request, "interface_version", "operation", "request_nonce");
        }

        private static string IssueAttempt(string requestNonce, IDictionary<string, object> request)
        {
            string configuration = R7Support.RequireEnum(
                request, "configuration",
                "SHORT_AUTOCRLF_TRUE", "SHORT_AUTOCRLF_FALSE", "LONG_AUTOCRLF_TRUE", "LONG_AUTOCRLF_FALSE");
            if (!AllowedConfiguration(configuration)) return Failure("CONFIGURATION_NOT_ALLOWED");
            string attemptId = R7Support.RandomHex(32);
            SortedDictionary<string, object> payload = new SortedDictionary<string, object>(StringComparer.Ordinal);
            payload["artifact_type"] = "R7_ATTEMPT_AUTHORITY";
            payload["attempt_id"] = attemptId;
            payload["configuration"] = configuration;
            payload["interface_version"] = R7Constants.InterfaceVersion;
            payload["issue_time"] = R7Support.Timestamp();
            payload["ledger_id"] = R7Constants.LedgerId;
            payload["policy_sha256"] = R7BuildConstants.PolicySha256;
            payload["provisioning_commit"] = R7Constants.ProvisioningCommit;
            payload["public_key_identity"] = R7Constants.PublicKeyIdentity;
            payload["r6_commit"] = R7Constants.R6Commit;
            payload["schema_version"] = R7Constants.SchemaVersion;
            payload["service_binary_sha256"] = binarySha256;
            payload["service_sid"] = R7Constants.ServiceSid;
            payload["state"] = "ISSUED";
            string locator = StoreSigned(payload, "evidence");
            string identity = R7Support.ParseLocator(locator, "evidence");
            R7AppendResult append = ledger.Append("R7_ATTEMPT_ISSUED", requestNonce, attemptId, identity);
            SortedDictionary<string, object> response = BaseSuccess("R7_ATTEMPT_ISSUED");
            response["attempt_id"] = attemptId;
            response["attempt_locator"] = locator;
            response["checkpoint_identity"] = append.CheckpointIdentity;
            response["configuration"] = configuration;
            response["ledger_entry_identity"] = append.EntryIdentity;
            response["ledger_sequence"] = append.Sequence;
            return CanonicalJson.Serialize(response);
        }

        private static string ExecuteRun(string requestNonce, IDictionary<string, object> request)
        {
            string attemptId = R7Support.RequireLowerHex(request, "attempt_id", 64);
            string phase = R7Support.RequireEnum(request, "phase", "CANDIDATE", "FRESH");
            IDictionary<string, object> attempt = ResolveAttempt(attemptId);
            string configuration = StrictJson.RequireString(attempt, "configuration");
            string phaseSubject = CryptoUtil.Sha256Hex(Encoding.UTF8.GetBytes(attemptId + "|" + phase));
            if (ledger.ContainsSubject("R7_RUN_ISSUED", phaseSubject)) return Failure("RUN_PHASE_ALREADY_ISSUED");

            // Resolve every immutable authority before the first subject process starts.
            IDictionary<string, object> caseAuthority = R7Support.ReadCaseAuthority();
            IDictionary<string, object> expectationAuthority = R7Support.ReadExpectationAuthority();
            ValidateAuthoritySets(caseAuthority, expectationAuthority);
            R7Support.ReadPinnedBytes(R7Constants.CorrectionRequirementsPath, R7Constants.CorrectionRequirementsSha256, R7Constants.CorrectionRequirementsGitBlob, R7Constants.CorrectionRequirementsSize);
            R7Support.ReadPinnedBytes(R7Constants.AdversarialProbePath, R7Constants.AdversarialProbeSha256, R7Constants.AdversarialProbeGitBlob, R7Constants.AdversarialProbeSize);

            string runId = R7Support.RandomHex(32);
            string runNonce = R7Support.RandomHex(32);
            SortedDictionary<string, object> runPayload = new SortedDictionary<string, object>(StringComparer.Ordinal);
            runPayload["artifact_type"] = "R7_REAL_EXECUTION_RUN_ISSUANCE";
            runPayload["attempt_id"] = attemptId;
            runPayload["case_count"] = R7Constants.RequiredCaseCount;
            runPayload["case_definition_git_blob"] = R7Constants.CaseDefinitionGitBlob;
            runPayload["configuration"] = configuration;
            runPayload["expectation_git_blob"] = R7Constants.ExpectationGitBlob;
            runPayload["interface_version"] = R7Constants.InterfaceVersion;
            runPayload["issue_time"] = R7Support.Timestamp();
            runPayload["phase"] = phase;
            runPayload["policy_sha256"] = R7BuildConstants.PolicySha256;
            runPayload["run_id"] = runId;
            runPayload["run_nonce"] = runNonce;
            runPayload["schema_version"] = R7Constants.SchemaVersion;
            runPayload["service_binary_sha256"] = binarySha256;
            runPayload["state"] = "ISSUED_ONCE";
            string runLocator = StoreSigned(runPayload, "evidence");
            string runIdentity = R7Support.ParseLocator(runLocator, "evidence");
            R7AppendResult runAppend = ledger.Append("R7_RUN_ISSUED", requestNonce, phaseSubject, runIdentity);

            object[] caseRows = R7Support.RequireArray(caseAuthority, "cases");
            R7SuiteResult suite = ExecuteRealSuite(runId, phase, caseRows);
            IssueSuiteProcessReceipt(runId, suite);
            object[] events;
            string eventRoot;
            BuildCurrentEvents(runId, suite, out events, out eventRoot);
            SortedDictionary<string, object> eventSource = new SortedDictionary<string, object>(StringComparer.Ordinal);
            eventSource["artifact_type"] = "R7_CURRENT_EXECUTION_EVENTS";
            eventSource["case_definition_git_blob"] = R7Constants.CaseDefinitionGitBlob;
            eventSource["event_count"] = events.Length;
            eventSource["event_root"] = eventRoot;
            eventSource["events"] = events;
            eventSource["expectation_git_blob"] = R7Constants.ExpectationGitBlob;
            eventSource["run_id"] = runId;
            eventSource["schema_version"] = R7Constants.SchemaVersion;
            eventSource["subject_run_id"] = suite.SubjectRunId;
            eventSource["suite_process_receipt_locator"] = suite.ProcessReceiptLocator;
            string eventLocator = StorePlain(eventSource, "evidence");
            string eventIdentity = R7Support.ParseLocator(eventLocator, "evidence");

            string traceLocator = BuildTraceability(runId, caseRows, events, eventLocator);
            R7ProcessResult observer = LaunchWorker("derive-observations", runId, SingleLocatorSubject("event_source_locator", eventLocator));
            string observationLocator = StorePlain(observer.Result, "evidence");
            SortedDictionary<string, object> comparisonSubject = new SortedDictionary<string, object>(StringComparer.Ordinal);
            comparisonSubject["event_source_locator"] = eventLocator;
            comparisonSubject["observation_locator"] = observationLocator;
            comparisonSubject["traceability_locator"] = traceLocator;
            R7ProcessResult comparator = LaunchWorker("compare", runId, comparisonSubject);
            string comparisonLocator = StorePlain(comparator.Result, "evidence");
            if (!String.Equals(StrictJson.RequireString(comparator.Result, "conformity"), "CONFORMANT", StringComparison.Ordinal) ||
                R7Support.RequireLong(comparator.Result, "discrepancy_count") != 0 ||
                R7Support.RequireLong(comparator.Result, "resolved_case_count") != R7Constants.RequiredCaseCount)
                throw new InvalidDataException("INDEPENDENT_COMPARATOR_REJECTED");

            string processIndexLocator = BuildProcessIndex(runId, suite, observer, comparator);
            VerifyCurrentRunSemantics(runId, eventLocator, observationLocator, traceLocator, comparisonLocator, processIndexLocator);
            string attemptLocator = R7Support.ContentLocator("evidence", StrictJson.RequireString(ledger.FindBySubject("R7_ATTEMPT_ISSUED", attemptId), "content_address"));
            SortedDictionary<string, object> terminalBase = new SortedDictionary<string, object>(StringComparer.Ordinal);
            terminalBase["artifact_type"] = "R7_SIGNED_TERMINAL_RECEIPT";
            terminalBase["attempt_id"] = attemptId;
            terminalBase["attempt_locator"] = attemptLocator;
            terminalBase["case_count"] = R7Constants.RequiredCaseCount;
            terminalBase["case_definition_git_blob"] = R7Constants.CaseDefinitionGitBlob;
            terminalBase["case_definition_sha256"] = R7Constants.CaseDefinitionSha256;
            terminalBase["case_definition_size"] = R7Constants.CaseDefinitionSize;
            terminalBase["comparator_result_locator"] = comparisonLocator;
            terminalBase["configuration"] = configuration;
            terminalBase["event_root"] = eventRoot;
            terminalBase["event_source_locator"] = eventLocator;
            terminalBase["expectation_git_blob"] = R7Constants.ExpectationGitBlob;
            terminalBase["expectation_sha256"] = R7Constants.ExpectationSha256;
            terminalBase["expectation_size"] = R7Constants.ExpectationSize;
            terminalBase["interface_version"] = R7Constants.InterfaceVersion;
            terminalBase["ipc_identity"] = ipcIdentity;
            terminalBase["issue_time"] = R7Support.Timestamp();
            terminalBase["ledger_genesis_identity"] = ledger.GenesisIdentity;
            terminalBase["ledger_id"] = R7Constants.LedgerId;
            terminalBase["observation_locator"] = observationLocator;
            terminalBase["phase"] = phase;
            terminalBase["policy_sha256"] = R7BuildConstants.PolicySha256;
            terminalBase["process_index_locator"] = processIndexLocator;
            terminalBase["public_key_identity"] = R7Constants.PublicKeyIdentity;
            terminalBase["run_id"] = runId;
            terminalBase["run_issuance_ledger_entry_identity"] = runAppend.EntryIdentity;
            terminalBase["run_locator"] = runLocator;
            terminalBase["run_nonce"] = runNonce;
            terminalBase["schema_version"] = R7Constants.SchemaVersion;
            terminalBase["service_binary_sha256"] = binarySha256;
            terminalBase["service_sid"] = R7Constants.ServiceSid;
            terminalBase["subject_commit"] = R7Constants.SubjectCommit;
            terminalBase["subject_process_id"] = suite.SubjectProcessId;
            terminalBase["subject_run_id"] = suite.SubjectRunId;
            terminalBase["suite_process_receipt_locator"] = suite.ProcessReceiptLocator;
            terminalBase["terminal_verifier_result"] = "SEMANTICALLY_VERIFIED";
            terminalBase["traceability_locator"] = traceLocator;
            terminalBase["worker_sha256"] = R7BuildConstants.WorkerSha256;
            string claimIdentity = CryptoUtil.Sha256Hex(CanonicalJson.SerializeBytes(terminalBase));
            string rootBeforeReservation = ledger.RootHash;
            R7AppendResult reservation = ledger.Append("R7_TERMINAL_RESERVED", Guid.NewGuid().ToString("D"), runId, claimIdentity);
            SortedDictionary<string, object> terminalPayload = new SortedDictionary<string, object>(terminalBase, StringComparer.Ordinal);
            terminalPayload["ledger_reservation_entry_identity"] = reservation.EntryIdentity;
            terminalPayload["ledger_reservation_prior_root"] = rootBeforeReservation;
            terminalPayload["ledger_reservation_sequence"] = reservation.Sequence;
            terminalPayload["terminal_claim_identity"] = claimIdentity;
            string terminalLocator = StoreSigned(terminalPayload, "terminal");
            string terminalIdentity = R7Support.ParseLocator(terminalLocator, "terminal");
            R7AppendResult commit = ledger.Append("R7_TERMINAL_RECEIPT_COMMITTED", Guid.NewGuid().ToString("D"), runId, terminalIdentity);
            // Append completed before exposing terminal success.
            VerifyTerminal(terminalLocator);
            SortedDictionary<string, object> response = BaseSuccess("R7_TERMINAL_RECEIPT_ISSUED");
            response["checkpoint_identity"] = commit.CheckpointIdentity;
            response["ledger_commit_entry_identity"] = commit.EntryIdentity;
            response["ledger_commit_sequence"] = commit.Sequence;
            response["phase"] = phase;
            response["receipt_identity"] = terminalIdentity;
            response["receipt_locator"] = terminalLocator;
            response["run_id"] = runId;
            return CanonicalJson.Serialize(response);
        }

        private static void ValidateAuthoritySets(IDictionary<string, object> cases, IDictionary<string, object> expectations)
        {
            StrictJson.RequireExactKeys(cases, "artifact_type", "authority_model", "case_count", "cases", "governing_sources", "schema_version");
            StrictJson.RequireExactKeys(expectations, "artifact_type", "authoring_authority", "case_count", "expectations", "provenance_policy", "schema_version", "source_authorities");
            if (!String.Equals(StrictJson.RequireString(cases, "artifact_type"), "R7_REAL_PUBLIC_INTERFACE_CASE_DEFINITIONS", StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(expectations, "artifact_type"), "R7_INDEPENDENT_EXPECTATIONS", StringComparison.Ordinal) ||
                R7Support.RequireLong(cases, "case_count") != R7Constants.RequiredCaseCount ||
                R7Support.RequireLong(expectations, "case_count") != R7Constants.RequiredCaseCount)
                throw new InvalidDataException("IMMUTABLE_AUTHORITY_CARDINALITY");
            object[] caseRows = R7Support.RequireArray(cases, "cases");
            object[] expectationRows = R7Support.RequireArray(expectations, "expectations");
            HashSet<string> caseIds = new HashSet<string>(StringComparer.Ordinal);
            HashSet<string> expectationIds = new HashSet<string>(StringComparer.Ordinal);
            foreach (object raw in caseRows)
            {
                IDictionary<string, object> row = raw as IDictionary<string, object>;
                if (row == null || !caseIds.Add(StrictJson.RequireString(row, "case_id"))) throw new InvalidDataException("CASE_AUTHORITY_DUPLICATE");
            }
            foreach (object raw in expectationRows)
            {
                IDictionary<string, object> row = raw as IDictionary<string, object>;
                if (row == null || !expectationIds.Add(StrictJson.RequireString(row, "case_id"))) throw new InvalidDataException("EXPECTATION_AUTHORITY_DUPLICATE");
            }
            if (!caseIds.SetEquals(expectationIds)) throw new InvalidDataException("CASE_EXPECTATION_SET_MISMATCH");
        }

        private static R7SuiteResult ExecuteRealSuite(string runId, string phase, object[] caseRows)
        {
            ValidateSubjectInstallation();
            Directory.CreateDirectory(R7Constants.SubjectTemporaryRoot);
            Directory.CreateDirectory(R7Constants.FixtureReceiptRoot);
            string fixtureRunRoot = Path.Combine(R7Constants.FixtureReceiptRoot, runId);
            if (Directory.Exists(fixtureRunRoot) || File.Exists(fixtureRunRoot)) throw new SecurityException("FIXTURE_RUN_ROOT_REUSE");
            Directory.CreateDirectory(fixtureRunRoot);
            if (Directory.GetFileSystemEntries(fixtureRunRoot).Length != 0) throw new SecurityException("FIXTURE_RUN_ROOT_NOT_EMPTY");
            ProcessStartInfo start = new ProcessStartInfo();
            start.FileName = R7Constants.SubjectLauncherPath;
            start.Arguments = String.Empty;
            start.WorkingDirectory = R7Constants.InstallRoot;
            start.UseShellExecute = false;
            start.CreateNoWindow = true;
            start.RedirectStandardInput = true;
            start.RedirectStandardOutput = true;
            start.RedirectStandardError = true;
            start.EnvironmentVariables.Remove("PYTHONPATH");
            start.EnvironmentVariables.Remove("PYTHONHOME");
            start.EnvironmentVariables["PYTHONNOUSERSITE"] = "1";
            start.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1";
            start.EnvironmentVariables["RANDLE_R7_FIXTURE_RECEIPT_ROOT"] = R7Constants.FixtureReceiptRoot;
            start.EnvironmentVariables["RANDLE_R7_OUTER_RUN_ID"] = runId;
            start.EnvironmentVariables["TEMP"] = R7Constants.SubjectTemporaryRoot;
            start.EnvironmentVariables["TMP"] = R7Constants.SubjectTemporaryRoot;
            start.EnvironmentVariables["PATH"] = @"C:\Program Files\Git\cmd;C:\Windows\System32;C:\Windows";
            DateTimeOffset launched = DateTimeOffset.UtcNow;
            Process process = new Process();
            process.StartInfo = start;
            if (!process.Start()) throw new InvalidOperationException("REAL_SUBJECT_PROCESS_START_FAILED");
            int launcherPid = process.Id;
            int subjectPid = 0;
            Task<string> stderrTask = process.StandardError.ReadToEndAsync();
            List<object> setupLocators = new List<object>();
            R7SuiteResult suite = new R7SuiteResult();
            try
            {
                string launchLine = ReadSubjectLine(process, 30000);
                byte[] launchBytes = ExactLineBytes(launchLine);
                IDictionary<string, object> launch = R7Support.ParseCanonicalObject(launchBytes);
                StrictJson.RequireExactKeys(launch, "artifact_type", "authentication_type", "group_sids", "is_administrator", "launch_time", "launcher_binary_sha256", "launcher_process_id", "python_binary_sha256", "subject_process_id", "subject_source_sha256", "token_inheritance", "user_sid");
                if (!String.Equals(StrictJson.RequireString(launch, "artifact_type"), "R7_MEASURED_SUBJECT_LAUNCH", StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(launch, "launcher_binary_sha256"), R7Constants.SubjectLauncherSha256, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(launch, "python_binary_sha256"), R7Constants.SubjectPythonSha256, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(launch, "subject_source_sha256"), R7Constants.SubjectServiceSha256, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(launch, "token_inheritance"), "CREATEPROCESS_DEFAULT_CALLER_TOKEN", StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(launch, "user_sid"), R7Constants.ServiceSid, StringComparison.Ordinal) ||
                    R7Support.RequireBool(launch, "is_administrator") || R7Support.RequireLong(launch, "launcher_process_id") != launcherPid)
                    throw new SecurityException("REAL_SUBJECT_LAUNCH_AUTHORITY");
                long rawSubjectPid = R7Support.RequireLong(launch, "subject_process_id");
                if (rawSubjectPid <= 0 || rawSubjectPid > Int32.MaxValue) throw new SecurityException("REAL_SUBJECT_PID");
                subjectPid = (int)rawSubjectPid;
                suite.SubjectLauncherProcessId = launcherPid;
                suite.SubjectProcessId = subjectPid;
                suite.SubjectTokenEvidence = launch;
                suite.SubjectTokenEvidenceIdentity = CryptoUtil.Sha256Hex(launchBytes);
                suite.SubjectLaunchLocator = StoreRawEvidence(launchBytes, ".json");
                setupLocators.Add(suite.SubjectLaunchLocator);
                string readyLine = ReadSubjectLine(process, 120000);
                byte[] readyBytes = ExactLineBytes(readyLine);
                IDictionary<string, object> ready = R7Support.ParseCanonicalObject(readyBytes);
                if (!String.Equals(StrictJson.RequireString(ready, "status"), "READY", StringComparison.Ordinal)) throw new InvalidDataException("REAL_SUBJECT_NOT_READY");
                suite.SubjectReadyLocator = StoreRawEvidence(readyBytes, ".json");

                R7SubjectExchange issuance = SendSubject(process, new SortedDictionary<string, object>(StringComparer.Ordinal) {
                    { "operation", "issue_run" }, { "purpose", phase.ToLowerInvariant() }
                });
                setupLocators.Add(issuance.RequestLocator); setupLocators.Add(issuance.ResponseLocator);
                IDictionary<string, object> issuanceResult = RequireSubjectSuccess(issuance.Response, "issue_run");
                IDictionary<string, object> issuanceReceipt = StrictJson.RequireObject(issuanceResult, "receipt");
                IDictionary<string, object> issuanceBody = StrictJson.RequireObject(issuanceReceipt, "body");
                suite.SubjectRunId = R7Support.RequireLowerHex(issuanceBody, "run_id", 64);
                R7SubjectExchange consumed = SendSubject(process, new SortedDictionary<string, object>(StringComparer.Ordinal) {
                    { "operation", "consume_run" }, { "receipt", issuanceReceipt }
                });
                setupLocators.Add(consumed.RequestLocator); setupLocators.Add(consumed.ResponseLocator);
                RequireSubjectSuccess(consumed.Response, "consume_run");
                R7SubjectExchange parser = SendSubject(process, new SortedDictionary<string, object>(StringComparer.Ordinal) { { "operation", "run_parser" } });
                setupLocators.Add(parser.RequestLocator); setupLocators.Add(parser.ResponseLocator);
                RequireSubjectSuccess(parser.Response, "run_parser");
                R7SubjectExchange recorder = SendSubject(process, new SortedDictionary<string, object>(StringComparer.Ordinal) { { "operation", "start_recorder" } });
                setupLocators.Add(recorder.RequestLocator); setupLocators.Add(recorder.ResponseLocator);
                RequireSubjectSuccess(recorder.Response, "start_recorder");

                HashSet<string> seen = new HashSet<string>(StringComparer.Ordinal);
                foreach (object raw in caseRows)
                {
                    IDictionary<string, object> definition = raw as IDictionary<string, object>;
                    if (definition == null) throw new InvalidDataException("REAL_CASE_SHAPE");
                    string caseId = StrictJson.RequireString(definition, "case_id");
                    if (!seen.Add(caseId)) throw new InvalidDataException("REAL_CASE_DUPLICATE");
                    IDictionary<string, object> source = StrictJson.RequireObject(definition, "source_case");
                    string mutation = StrictJson.RequireString(source, "mutation");
                    bool fixtureRequired = mutation.StartsWith("reparse_substitution_", StringComparison.Ordinal);
                    HashSet<string> fixtureFilesBefore = SnapshotFixtureReceipts(fixtureRunRoot);
                    long preSequence = ledger.Sequence;
                    string preRoot = ledger.RootHash;
                    SortedDictionary<string, object> request = new SortedDictionary<string, object>(StringComparer.Ordinal);
                    request["case_id"] = caseId;
                    request["operation"] = "execute_case";
                    R7SubjectExchange exchange = SendSubject(process, request);
                    long postSequence = ledger.Sequence;
                    string postRoot = ledger.RootHash;
                    R7FixtureEvidence fixture = ResolveFixtureEvidence(fixtureRunRoot, fixtureFilesBefore, fixtureRequired, runId, caseId, subjectPid, exchange, suite.SubjectTokenEvidence);
                    if (fixture.Invoked) suite.FixtureProcessReceiptCount++;
                    IDictionary<string, object> result = RequireSubjectSuccess(exchange.Response, "execute_case");
                    if (!String.Equals(StrictJson.RequireString(result, "case_id"), caseId, StringComparison.Ordinal)) throw new InvalidDataException("REAL_CASE_RESPONSE_BINDING");
                    IDictionary<string, object> outcome = StrictJson.RequireObject(result, "outcome");
                    IDictionary<string, object> innerEvent = StrictJson.RequireObject(result, "event");
                    IDictionary<string, object> executionReceipt = StrictJson.RequireObject(result, "execution_receipt");
                    IDictionary<string, object> executionBody = StrictJson.RequireObject(executionReceipt, "body");
                    SortedDictionary<string, object> item = new SortedDictionary<string, object>(StringComparer.Ordinal);
                    item["actual_authority_identity"] = StrictJson.RequireString(outcome, "authority_identity");
                    item["actual_outcome"] = StrictJson.RequireString(outcome, "status");
                    item["case_id"] = caseId;
                    item["enforcing_function"] = StrictJson.RequireString(outcome, "enforcing_function");
                    item["fixture_body_identity"] = fixture.BodyIdentity;
                    item["fixture_helper_file_identity"] = fixture.HelperFileIdentity;
                    item["fixture_helper_invoked"] = fixture.Invoked;
                    item["fixture_helper_process_id"] = fixture.HelperProcessId;
                    item["fixture_process_receipt_identity"] = fixture.ReceiptIdentity;
                    item["fixture_process_receipt_locator"] = fixture.Locator;
                    item["fixture_reparse_snapshot_identity"] = fixture.ReparseSnapshotIdentity;
                    item["fixture_reparse_snapshot_locator"] = fixture.ReparseSnapshotLocator;
                    item["inner_event_hash"] = R7Support.RequireLowerHex(innerEvent, "event_hash", 64);
                    item["inner_execution_receipt_identity"] = R7Support.RequireLowerHex(executionReceipt, "receipt_identity", 64);
                    item["outer_post_ledger_root"] = postRoot;
                    item["outer_post_ledger_sequence"] = postSequence;
                    item["outer_pre_ledger_root"] = preRoot;
                    item["outer_pre_ledger_sequence"] = preSequence;
                    item["public_interface"] = StrictJson.RequireString(source, "public_interface");
                    item["public_interface_end_time"] = exchange.EndedAt.ToString("yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture);
                    item["public_interface_start_time"] = exchange.StartedAt.ToString("yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture);
                    item["public_request_locator"] = exchange.RequestLocator;
                    item["public_response_locator"] = exchange.ResponseLocator;
                    item["request_sha256"] = exchange.RequestIdentity;
                    item["response_classification"] = StrictJson.RequireString(outcome, "code");
                    item["response_sha256"] = exchange.ResponseIdentity;
                    item["subject_case_token_identity"] = R7Support.RequireLowerHex(executionBody, "case_token_identity", 64);
                    item["subject_event_ledger_delta"] = 1;
                    item["subject_process_id"] = subjectPid;
                    item["subject_launcher_process_id"] = launcherPid;
                    suite.Cases.Add(item);
                }
                if (suite.Cases.Count != R7Constants.RequiredCaseCount) throw new InvalidDataException("REAL_SUITE_CASE_COUNT");
                R7SubjectExchange finalized = SendSubject(process, new SortedDictionary<string, object>(StringComparer.Ordinal) { { "operation", "finalize" } });
                setupLocators.Add(finalized.RequestLocator); setupLocators.Add(finalized.ResponseLocator);
                IDictionary<string, object> finalSource = RequireSubjectSuccess(finalized.Response, "finalize");
                if (R7Support.RequireArray(finalSource, "events").Length != R7Constants.RequiredCaseCount) throw new InvalidDataException("REAL_SUBJECT_FINAL_EVENT_COUNT");
                R7SubjectExchange ledgerSnapshot = SendSubject(process, new SortedDictionary<string, object>(StringComparer.Ordinal) { { "operation", "ledger_snapshot" } });
                setupLocators.Add(ledgerSnapshot.RequestLocator); setupLocators.Add(ledgerSnapshot.ResponseLocator);
                RequireSubjectSuccess(ledgerSnapshot.Response, "ledger_snapshot");
                R7SubjectExchange shutdown = SendSubject(process, new SortedDictionary<string, object>(StringComparer.Ordinal) { { "operation", "shutdown" } });
                setupLocators.Add(shutdown.RequestLocator); setupLocators.Add(shutdown.ResponseLocator);
                RequireSubjectSuccess(shutdown.Response, "shutdown");
                if (!process.WaitForExit(30000)) { try { process.Kill(); } catch { } throw new InvalidOperationException("REAL_SUBJECT_PROCESS_TIMEOUT"); }
                if (process.ExitCode != 0) throw new InvalidOperationException("REAL_SUBJECT_PROCESS_EXIT");
                string stderr = stderrTask.Result;
                suite.SubjectStderrLocator = StoreRawEvidence(new UTF8Encoding(false, true).GetBytes(stderr), ".bin");
                SortedDictionary<string, object> rawIndex = new SortedDictionary<string, object>(StringComparer.Ordinal);
                rawIndex["artifact_type"] = "R7_REAL_SUITE_RAW_CASE_INDEX";
                rawIndex["case_count"] = suite.Cases.Count;
                rawIndex["cases"] = suite.Cases.ToArray();
                rawIndex["final_source_locator"] = finalized.ResponseLocator;
                rawIndex["outer_run_id"] = runId;
                rawIndex["schema_version"] = R7Constants.SchemaVersion;
                rawIndex["setup_and_shutdown_locators"] = setupLocators.ToArray();
                rawIndex["subject_ledger_snapshot_locator"] = ledgerSnapshot.ResponseLocator;
                rawIndex["subject_run_id"] = suite.SubjectRunId;
                suite.RawCaseIndexLocator = StorePlain(rawIndex, "evidence");
                suite.RawCaseIndexIdentity = R7Support.ParseLocator(suite.RawCaseIndexLocator, "evidence");
                return suite;
            }
            catch
            {
                try
                {
                    if (subjectPid > 0)
                    {
                        using (System.Diagnostics.Process subjectProcess = System.Diagnostics.Process.GetProcessById(subjectPid)) if (!subjectProcess.HasExited) subjectProcess.Kill();
                    }
                }
                catch { }
                try { if (!process.HasExited) process.Kill(); } catch { }
                try { process.WaitForExit(5000); } catch { }
                throw;
            }
            finally
            {
                process.Dispose();
            }
        }

        private static HashSet<string> SnapshotFixtureReceipts(string runRoot)
        {
            string[] all = Directory.GetFileSystemEntries(runRoot);
            string[] json = Directory.GetFiles(runRoot, "*.json", SearchOption.TopDirectoryOnly);
            if (all.Length != json.Length) throw new SecurityException("FIXTURE_RECEIPT_ROOT_CONTAMINATED");
            HashSet<string> names = new HashSet<string>(StringComparer.Ordinal);
            foreach (string path in json)
            {
                string name = Path.GetFileName(path);
                if (!Regex.IsMatch(name, @"\A[0-9a-f]{64}\.json\z", RegexOptions.CultureInvariant) || !names.Add(name))
                    throw new SecurityException("FIXTURE_RECEIPT_NAME_REJECTED");
            }
            return names;
        }

        private static R7FixtureEvidence ResolveFixtureEvidence(string runRoot, HashSet<string> before, bool required,
            string runId, string caseId, int subjectPid, R7SubjectExchange exchange, IDictionary<string, object> subjectTokenEvidence)
        {
            HashSet<string> after = SnapshotFixtureReceipts(runRoot);
            List<string> added = after.Where(delegate(string name) { return !before.Contains(name); }).ToList();
            if (!required)
            {
                if (added.Count != 0) throw new SecurityException("UNEXPECTED_FIXTURE_PROCESS_RECEIPT");
                return new R7FixtureEvidence {
                    BodyIdentity = R7Constants.ZeroHash,
                    HelperFileIdentity = String.Empty,
                    HelperProcessId = 0,
                    Invoked = false,
                    Locator = String.Empty,
                    ReparseSnapshotIdentity = R7Constants.ZeroHash,
                    ReparseSnapshotLocator = String.Empty,
                    ReceiptIdentity = R7Constants.ZeroHash
                };
            }
            if (added.Count != 1) throw new SecurityException("REQUIRED_FIXTURE_PROCESS_RECEIPT_COUNT");
            string receiptPath = Path.Combine(runRoot, added[0]);
            byte[] bytes = File.ReadAllBytes(receiptPath);
            string receiptIdentity = CryptoUtil.Sha256Hex(bytes);
            if (!String.Equals(Path.GetFileNameWithoutExtension(receiptPath), receiptIdentity, StringComparison.Ordinal))
                throw new SecurityException("FIXTURE_RECEIPT_CONTENT_ADDRESS");
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
                !String.Equals(StrictJson.RequireString(receipt, "user_sid"), R7Constants.ServiceSid, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(receipt, "token_inheritance"), "CREATEPROCESS_DEFAULT_CALLER_TOKEN", StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(receipt, "reparse_tag"), "a0000003", StringComparison.Ordinal) ||
                R7Support.RequireBool(receipt, "is_administrator") || R7Support.RequireLong(receipt, "exit_code") != 0 ||
                R7Support.RequireLong(receipt, "parent_process_id") != subjectPid)
                throw new SecurityException("FIXTURE_PROCESS_RECEIPT_AUTHORITY");
            if (!String.Equals(StrictJson.RequireString(receipt, "authentication_type"), StrictJson.RequireString(subjectTokenEvidence, "authentication_type"), StringComparison.Ordinal) ||
                !String.Equals(CanonicalJson.Serialize(R7Support.RequireArray(receipt, "group_sids")), CanonicalJson.Serialize(R7Support.RequireArray(subjectTokenEvidence, "group_sids")), StringComparison.Ordinal))
                throw new SecurityException("FIXTURE_INHERITED_TOKEN_EVIDENCE_REJECTED");
            int helperPid = checked((int)R7Support.RequireLong(receipt, "helper_process_id"));
            if (helperPid <= 0 || helperPid == subjectPid || !R7Support.IsLowerHex(StrictJson.RequireString(receipt, "fixture_nonce"), 64))
                throw new SecurityException("FIXTURE_PROCESS_IDENTITY_REJECTED");
            string helperFileIdentity = R7NativeIdentity.GetFileIdentity(R7Constants.SubjectFixtureHostPath);
            if (!String.Equals(StrictJson.RequireString(receipt, "helper_binary_file_identity"), helperFileIdentity, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(receipt, "parent_binary_file_identity"), R7NativeIdentity.GetFileIdentity(R7Constants.SubjectPythonPath), StringComparison.Ordinal))
                throw new SecurityException("FIXTURE_FILE_IDENTITY_REJECTED");

            string command = StrictJson.RequireString(receipt, "command");
            Match match = Regex.Match(command, @"\ANew-Item -ItemType Junction -Path '(?<junction>[^']+)' -Target '(?<target>[^']+)' \| Out-Null\z", RegexOptions.CultureInvariant);
            if (!match.Success || !String.Equals(CryptoUtil.Sha256Hex(new UTF8Encoding(false, true).GetBytes(command)), StrictJson.RequireString(receipt, "command_sha256"), StringComparison.Ordinal))
                throw new SecurityException("FIXTURE_COMMAND_EVIDENCE_REJECTED");
            string junctionPath = Path.GetFullPath(StrictJson.RequireString(receipt, "junction_path"));
            string targetPath = Path.GetFullPath(StrictJson.RequireString(receipt, "target_path"));
            string temporaryRoot = Path.GetFullPath(R7Constants.SubjectTemporaryRoot).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            if (!String.Equals(junctionPath, Path.GetFullPath(match.Groups["junction"].Value), StringComparison.OrdinalIgnoreCase) ||
                !String.Equals(targetPath, Path.GetFullPath(match.Groups["target"].Value), StringComparison.OrdinalIgnoreCase) ||
                !junctionPath.StartsWith(temporaryRoot, StringComparison.OrdinalIgnoreCase) || !targetPath.StartsWith(temporaryRoot, StringComparison.OrdinalIgnoreCase) ||
                !String.Equals(Path.GetFileName(junctionPath), "reparse-parent", StringComparison.Ordinal) ||
                !String.Equals(Path.GetFileName(targetPath), "reparse-target", StringComparison.Ordinal) ||
                !String.Equals(Path.GetDirectoryName(junctionPath), Path.GetDirectoryName(targetPath), StringComparison.OrdinalIgnoreCase) ||
                !String.Equals(CryptoUtil.Sha256Hex(new UTF8Encoding(false, true).GetBytes(junctionPath)), StrictJson.RequireString(receipt, "junction_path_sha256"), StringComparison.Ordinal) ||
                !String.Equals(CryptoUtil.Sha256Hex(new UTF8Encoding(false, true).GetBytes(targetPath)), StrictJson.RequireString(receipt, "target_path_sha256"), StringComparison.Ordinal))
                throw new SecurityException("FIXTURE_PATH_EVIDENCE_REJECTED");
            FileAttributes attributes = File.GetAttributes(junctionPath);
            FileAttributes targetAttributes = File.GetAttributes(targetPath);
            if ((attributes & FileAttributes.ReparsePoint) == 0 || (attributes & FileAttributes.Directory) == 0 ||
                (targetAttributes & FileAttributes.ReparsePoint) != 0 || (targetAttributes & FileAttributes.Directory) == 0)
                throw new SecurityException("FIXTURE_REPARSE_SIDE_EFFECT_UNRESOLVED");
            byte[] reparseData = R7NativeIdentity.GetReparsePointData(junctionPath);
            R7ReparseEvidence.ValidateMountPoint(reparseData, targetPath);
            SortedDictionary<string, object> snapshot = new SortedDictionary<string, object>(StringComparer.Ordinal);
            snapshot["artifact_type"] = "R7_SERVICE_REPARSE_SIDE_EFFECT_EVIDENCE";
            snapshot["capture_model"] = "FSCTL_GET_REPARSE_POINT";
            snapshot["capture_time"] = R7Support.Timestamp();
            snapshot["case_id"] = caseId;
            snapshot["fixture_process_receipt_identity"] = receiptIdentity;
            snapshot["junction_attributes"] = (long)attributes;
            snapshot["junction_path"] = junctionPath;
            snapshot["reparse_data_base64"] = Convert.ToBase64String(reparseData);
            snapshot["reparse_data_sha256"] = CryptoUtil.Sha256Hex(reparseData);
            snapshot["run_id"] = runId;
            snapshot["schema_version"] = R7Constants.SchemaVersion;
            snapshot["service_binary_file_identity"] = binaryFileIdentity;
            snapshot["service_binary_sha256"] = binarySha256;
            snapshot["service_process_id"] = System.Diagnostics.Process.GetCurrentProcess().Id;
            snapshot["service_sid"] = R7Constants.ServiceSid;
            snapshot["target_attributes"] = (long)targetAttributes;
            snapshot["target_path"] = targetPath;
            string snapshotBodyIdentity = CryptoUtil.Sha256Hex(CanonicalJson.SerializeBytes(snapshot));
            snapshot["body_identity"] = snapshotBodyIdentity;
            string snapshotLocator = StorePlain(snapshot, "evidence");
            string snapshotIdentity = R7Support.ParseLocator(snapshotLocator, "evidence");

            DateTimeOffset fixtureStart;
            DateTimeOffset fixtureEnd;
            DateTimeOffset parentStart;
            const string timeFormat = "yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'";
            if (!DateTimeOffset.TryParseExact(StrictJson.RequireString(receipt, "start_time"), timeFormat, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out fixtureStart) ||
                !DateTimeOffset.TryParseExact(StrictJson.RequireString(receipt, "end_time"), timeFormat, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out fixtureEnd) ||
                !DateTimeOffset.TryParseExact(StrictJson.RequireString(receipt, "parent_start_time"), timeFormat, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out parentStart) ||
                parentStart > fixtureStart || fixtureStart < exchange.StartedAt || fixtureEnd < fixtureStart || fixtureEnd > exchange.EndedAt)
                throw new SecurityException("FIXTURE_CURRENT_EXCHANGE_TIME_REJECTED");
            SortedDictionary<string, object> body = new SortedDictionary<string, object>(receipt, StringComparer.Ordinal);
            string bodyIdentity = R7Support.RequireLowerHex(body, "body_identity", 64);
            body.Remove("body_identity");
            if (!String.Equals(bodyIdentity, CryptoUtil.Sha256Hex(CanonicalJson.SerializeBytes(body)), StringComparison.Ordinal))
                throw new SecurityException("FIXTURE_BODY_IDENTITY_REJECTED");
            string locator = StoreRawEvidence(bytes, ".json");
            if (!String.Equals(R7Support.ParseLocator(locator, "evidence"), receiptIdentity, StringComparison.Ordinal))
                throw new SecurityException("FIXTURE_EVIDENCE_COPY_REJECTED");
            return new R7FixtureEvidence {
                BodyIdentity = bodyIdentity,
                HelperFileIdentity = helperFileIdentity,
                HelperProcessId = helperPid,
                Invoked = true,
                Locator = locator,
                ReparseSnapshotIdentity = snapshotIdentity,
                ReparseSnapshotLocator = snapshotLocator,
                ReceiptIdentity = receiptIdentity
            };
        }

        private static void ValidateSubjectInstallation()
        {
            if (!String.Equals(CryptoUtil.Sha256File(R7Constants.SubjectLauncherPath), R7Constants.SubjectLauncherSha256, StringComparison.Ordinal))
                throw new SecurityException("SUBJECT_LAUNCHER_IDENTITY");
            if (!String.Equals(CryptoUtil.Sha256File(R7Constants.SubjectPythonPath), R7Constants.SubjectPythonSha256, StringComparison.Ordinal))
                throw new SecurityException("SUBJECT_PYTHON_IDENTITY");
            if (!String.Equals(CryptoUtil.Sha256File(R7Constants.SubjectFixtureHostPath), R7Constants.SubjectFixtureHostSha256, StringComparison.Ordinal))
                throw new SecurityException("SUBJECT_FIXTURE_HOST_IDENTITY");
            if (!String.Equals(CryptoUtil.Sha256File(R7Constants.SubjectServicePath), R7Constants.SubjectServiceSha256, StringComparison.Ordinal))
                throw new SecurityException("SUBJECT_SERVICE_SOURCE_IDENTITY");
            if (!String.Equals(CryptoUtil.Sha256File(R7Constants.SubjectDirectInterfacePath), R7Constants.SubjectDirectInterfaceSha256, StringComparison.Ordinal) ||
                !String.Equals(CryptoUtil.Sha256File(R7Constants.SubjectVerifierPath), R7Constants.SubjectVerifierSha256, StringComparison.Ordinal) ||
                !String.Equals(CryptoUtil.Sha256File(R7Constants.SubjectLedgerPath), R7Constants.SubjectLedgerSha256, StringComparison.Ordinal) ||
                !String.Equals(CryptoUtil.Sha256File(R7Constants.SubjectGovernedAccessPath), R7Constants.SubjectGovernedAccessSha256, StringComparison.Ordinal))
                throw new SecurityException("SUBJECT_SUPPORT_SOURCE_IDENTITY");
            string commit = RunGitSubject("rev-parse", R7Constants.SubjectCommit + "^{commit}");
            string tree = RunGitSubject("show", "-s", "--format=%T", R7Constants.SubjectCommit);
            if (!String.Equals(commit, R7Constants.SubjectCommit, StringComparison.Ordinal) || !String.Equals(tree, R7Constants.SubjectTree, StringComparison.Ordinal))
                throw new SecurityException("SUBJECT_REPOSITORY_IDENTITY");
        }

        private static void ValidatePythonRuntime()
        {
            byte[] manifestBytes = R7Support.ReadPinnedBytes(R7Constants.PythonRuntimeManifestPath, R7Constants.PythonRuntimeManifestSha256, R7Constants.PythonRuntimeManifestGitBlob, R7Constants.PythonRuntimeManifestSize);
            IDictionary<string, object> manifest = R7Support.ParseCanonicalObject(manifestBytes);
            StrictJson.RequireExactKeys(manifest, "artifact_type", "file_count", "files", "installed_root", "python_executable_sha256", "python_version", "runtime_root_identity", "schema_version", "source_model");
            if (!String.Equals(StrictJson.RequireString(manifest, "artifact_type"), "R7_DEDICATED_PYTHON_RUNTIME_MANIFEST", StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(manifest, "python_executable_sha256"), R7Constants.SubjectPythonSha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(manifest, "runtime_root_identity"), R7Constants.PythonRuntimeRootIdentity, StringComparison.Ordinal))
                throw new SecurityException("PYTHON_RUNTIME_MANIFEST_AUTHORITY");
            string root = Path.GetFullPath(Path.GetDirectoryName(R7Constants.SubjectPythonPath));
            Dictionary<string, IDictionary<string, object>> expected = new Dictionary<string, IDictionary<string, object>>(StringComparer.Ordinal);
            foreach (object raw in R7Support.RequireArray(manifest, "files"))
            {
                IDictionary<string, object> row = raw as IDictionary<string, object>;
                if (row == null) throw new InvalidDataException("PYTHON_RUNTIME_MANIFEST_ROW");
                StrictJson.RequireExactKeys(row, "path", "sha256", "size");
                string relative = StrictJson.RequireString(row, "path");
                if (relative.Contains("\\") || relative.StartsWith("/", StringComparison.Ordinal) || relative.Contains("../") || expected.ContainsKey(relative))
                    throw new InvalidDataException("PYTHON_RUNTIME_MANIFEST_PATH");
                expected.Add(relative, row);
            }
            string[] actualPaths = Directory.GetFiles(root, "*", SearchOption.AllDirectories);
            if (actualPaths.Length != expected.Count || R7Support.RequireLong(manifest, "file_count") != expected.Count) throw new SecurityException("PYTHON_RUNTIME_FILE_COUNT");
            foreach (string path in actualPaths)
            {
                string relative = path.Substring(root.TrimEnd(Path.DirectorySeparatorChar).Length + 1).Replace('\\', '/');
                IDictionary<string, object> row;
                if (!expected.TryGetValue(relative, out row) || new FileInfo(path).Length != R7Support.RequireLong(row, "size") ||
                    !String.Equals(CryptoUtil.Sha256File(path), StrictJson.RequireString(row, "sha256"), StringComparison.Ordinal))
                    throw new SecurityException("PYTHON_RUNTIME_FILE_IDENTITY:" + relative);
            }
        }

        private static string RunGitSubject(params string[] arguments)
        {
            ProcessStartInfo start = new ProcessStartInfo();
            start.FileName = @"C:\Program Files\Git\cmd\git.exe";
            start.Arguments = "-c core.longpaths=true -c " + QuoteArgument("safe.directory=" + R7Constants.SubjectRepositoryPath) +
                " -C " + QuoteArgument(R7Constants.SubjectRepositoryPath) + " " + String.Join(" ", arguments.Select(QuoteArgument).ToArray());
            start.UseShellExecute = false;
            start.CreateNoWindow = true;
            start.RedirectStandardOutput = true;
            start.RedirectStandardError = true;
            using (System.Diagnostics.Process process = System.Diagnostics.Process.Start(start))
            {
                string stdout = process.StandardOutput.ReadToEnd();
                string stderr = process.StandardError.ReadToEnd();
                if (!process.WaitForExit(30000) || process.ExitCode != 0) throw new InvalidDataException("SUBJECT_GIT_OBJECT_RESOLUTION:" + stderr);
                return stdout.Trim();
            }
        }

        private static R7SubjectExchange SendSubject(Process process, IDictionary<string, object> request)
        {
            DateTimeOffset startedAt = DateTimeOffset.UtcNow;
            byte[] core = CanonicalJson.SerializeBytes(request);
            byte[] requestBytes = new byte[core.Length + 1];
            Buffer.BlockCopy(core, 0, requestBytes, 0, core.Length);
            requestBytes[requestBytes.Length - 1] = (byte)'\n';
            string requestLocator = StoreRawEvidence(requestBytes, ".json");
            process.StandardInput.Write(new UTF8Encoding(false, true).GetString(requestBytes));
            process.StandardInput.Flush();
            string responseLine = ReadSubjectLine(process, 120000);
            byte[] responseBytes = ExactLineBytes(responseLine);
            IDictionary<string, object> response = R7Support.ParseCanonicalObject(responseBytes);
            string responseLocator = StoreRawEvidence(responseBytes, ".json");
            DateTimeOffset endedAt = DateTimeOffset.UtcNow;
            return new R7SubjectExchange {
                EndedAt = endedAt,
                Response = response,
                RequestLocator = requestLocator,
                RequestIdentity = R7Support.ParseLocator(requestLocator, "evidence"),
                ResponseLocator = responseLocator,
                ResponseIdentity = R7Support.ParseLocator(responseLocator, "evidence"),
                StartedAt = startedAt
            };
        }

        private static string ReadSubjectLine(Process process, int timeoutMilliseconds)
        {
            Task<string> task = process.StandardOutput.ReadLineAsync();
            if (!task.Wait(timeoutMilliseconds)) { try { process.Kill(); } catch { } throw new System.TimeoutException("REAL_SUBJECT_RESPONSE_TIMEOUT"); }
            string line = task.Result;
            if (line == null) throw new EndOfStreamException("REAL_SUBJECT_RESPONSE_EOF");
            return line;
        }

        private static byte[] ExactLineBytes(string line)
        {
            return new UTF8Encoding(false, true).GetBytes(line + "\n");
        }

        private static IDictionary<string, object> RequireSubjectSuccess(IDictionary<string, object> response, string operation)
        {
            if (!String.Equals(StrictJson.RequireString(response, "status"), "OK", StringComparison.Ordinal))
                throw new InvalidDataException("REAL_SUBJECT_" + operation.ToUpperInvariant() + "_REJECTED:" + StrictJson.RequireString(response, "code"));
            return StrictJson.RequireObject(response, "result");
        }

        private static void IssueSuiteProcessReceipt(string runId, R7SuiteResult suite)
        {
            SortedDictionary<string, object> receipt = new SortedDictionary<string, object>(StringComparer.Ordinal);
            receipt["artifact_type"] = "R7_REAL_SUITE_PROCESS_RECEIPT";
            receipt["case_count"] = suite.Cases.Count;
            receipt["command_identity"] = CryptoUtil.Sha256Hex(Encoding.UTF8.GetBytes(R7Constants.SubjectLauncherPath + "|" + R7Constants.SubjectPythonPath + "|" + R7Constants.SubjectServicePath + "|" + R7Constants.SubjectFixtureHostPath + "|" + R7Constants.SubjectCommit));
            receipt["completion_state"] = "COMPLETE";
            receipt["completion_time"] = R7Support.Timestamp();
            receipt["interface_version"] = R7Constants.InterfaceVersion;
            receipt["fixture_host_file_identity"] = R7NativeIdentity.GetFileIdentity(R7Constants.SubjectFixtureHostPath);
            receipt["fixture_host_sha256"] = R7Constants.SubjectFixtureHostSha256;
            receipt["fixture_process_receipt_count"] = suite.FixtureProcessReceiptCount;
            receipt["launch_receipt_locator"] = suite.SubjectLaunchLocator;
            receipt["launcher_file_identity"] = R7NativeIdentity.GetFileIdentity(R7Constants.SubjectLauncherPath);
            receipt["launcher_process_id"] = suite.SubjectLauncherProcessId;
            receipt["launcher_sha256"] = R7Constants.SubjectLauncherSha256;
            receipt["mode"] = "execute-real-suite";
            receipt["parent_service_process_id"] = System.Diagnostics.Process.GetCurrentProcess().Id;
            receipt["parent_service_binary_sha256"] = binarySha256;
            receipt["parent_service_binary_file_identity"] = binaryFileIdentity;
            receipt["python_file_identity"] = R7NativeIdentity.GetFileIdentity(R7Constants.SubjectPythonPath);
            receipt["python_sha256"] = CryptoUtil.Sha256File(R7Constants.SubjectPythonPath);
            receipt["raw_case_index_locator"] = suite.RawCaseIndexLocator;
            receipt["run_id"] = runId;
            receipt["schema_version"] = R7Constants.SchemaVersion;
            receipt["stderr_locator"] = suite.SubjectStderrLocator;
            receipt["subject_commit"] = R7Constants.SubjectCommit;
            receipt["subject_process_id"] = suite.SubjectProcessId;
            receipt["subject_ready_locator"] = suite.SubjectReadyLocator;
            receipt["subject_run_id"] = suite.SubjectRunId;
            receipt["subject_service_file_identity"] = R7NativeIdentity.GetFileIdentity(R7Constants.SubjectServicePath);
            receipt["subject_service_git_blob"] = R7Constants.SubjectServiceGitBlob;
            receipt["subject_service_sha256"] = R7Constants.SubjectServiceSha256;
            receipt["subject_token_evidence"] = suite.SubjectTokenEvidence;
            receipt["subject_token_evidence_identity"] = suite.SubjectTokenEvidenceIdentity;
            string locator = StoreSigned(receipt, "evidence");
            string identity = R7Support.ParseLocator(locator, "evidence");
            ledger.Append("R7_REAL_SUITE_PROCESS_COMPLETED", Guid.NewGuid().ToString("D"), runId, identity);
            suite.ProcessReceiptLocator = locator;
            suite.ProcessReceiptIdentity = identity;
        }

        private static void BuildCurrentEvents(string runId, R7SuiteResult suite, out object[] events, out string eventRoot)
        {
            List<object> values = new List<object>();
            string prior = R7Constants.ZeroHash;
            int sequence = 0;
            foreach (IDictionary<string, object> raw in suite.Cases)
            {
                sequence++;
                SortedDictionary<string, object> item = new SortedDictionary<string, object>(raw, StringComparer.Ordinal);
                item["case_definition_git_blob"] = R7Constants.CaseDefinitionGitBlob;
                item["event_constructor_binary_sha256"] = binarySha256;
                item["event_schema_version"] = R7Constants.SchemaVersion;
                item["event_time"] = R7Support.Timestamp();
                item["expectation_git_blob"] = R7Constants.ExpectationGitBlob;
                item["forbidden_side_effect_absent"] = R7Support.RequireLong(raw, "outer_post_ledger_sequence") == R7Support.RequireLong(raw, "outer_pre_ledger_sequence") &&
                    String.Equals(StrictJson.RequireString(raw, "outer_post_ledger_root"), StrictJson.RequireString(raw, "outer_pre_ledger_root"), StringComparison.Ordinal);
                item["interface_identity"] = R7Constants.SubjectDirectInterfaceSha256;
                item["interface_invoked"] = true;
                item["interface_operation"] = "execute_case";
                item["invoking_process_receipt_identity"] = suite.ProcessReceiptIdentity;
                item["prior_event_hash"] = prior;
                List<object> rawLocators = new List<object> { StrictJson.RequireString(raw, "public_request_locator"), StrictJson.RequireString(raw, "public_response_locator"), suite.RawCaseIndexLocator, suite.SubjectLaunchLocator, suite.SubjectReadyLocator, suite.SubjectStderrLocator };
                if (R7Support.RequireBool(raw, "fixture_helper_invoked"))
                {
                    rawLocators.Add(StrictJson.RequireString(raw, "fixture_process_receipt_locator"));
                    rawLocators.Add(StrictJson.RequireString(raw, "fixture_reparse_snapshot_locator"));
                }
                item["raw_evidence_locators"] = rawLocators.ToArray();
                item["run_id"] = runId;
                item["sequence"] = sequence;
                item["suite_process_receipt_locator"] = suite.ProcessReceiptLocator;
                item["subject_service_sha256"] = R7Constants.SubjectServiceSha256;
                item["target_process_binary_sha256"] = R7Constants.SubjectPythonSha256;
                string hash = CryptoUtil.Sha256Hex(CanonicalJson.SerializeBytes(item));
                item["event_hash"] = hash;
                prior = hash;
                values.Add(item);
            }
            events = values.ToArray();
            eventRoot = prior;
        }

        private static string BuildTraceability(string runId, object[] cases, object[] events, string eventLocator)
        {
            List<object> rows = new List<object>();
            for (int index = 0; index < cases.Length; index++)
            {
                IDictionary<string, object> definition = (IDictionary<string, object>)cases[index];
                IDictionary<string, object> current = (IDictionary<string, object>)events[index];
                SortedDictionary<string, object> row = new SortedDictionary<string, object>(StringComparer.Ordinal);
                row["case_definition_git_blob"] = R7Constants.CaseDefinitionGitBlob;
                row["case_id"] = StrictJson.RequireString(definition, "case_id");
                row["comparator_stage"] = "R7MeasuredWorker.compare";
                row["event_hash"] = StrictJson.RequireString(current, "event_hash");
                row["event_source_locator"] = eventLocator;
                row["expectation_git_blob"] = R7Constants.ExpectationGitBlob;
                row["governing_requirement_id"] = StrictJson.RequireString(definition, "governing_requirement_id");
                row["observation_stage"] = "R7MeasuredWorker.derive-observations";
                row["process_receipt_locator"] = StrictJson.RequireString(current, "suite_process_receipt_locator");
                row["public_interface"] = StrictJson.RequireString(current, "public_interface");
                row["request_locator"] = StrictJson.RequireString(current, "public_request_locator");
                row["response_locator"] = StrictJson.RequireString(current, "public_response_locator");
                row["reverse_mapping_required"] = true;
                row["run_id"] = runId;
                rows.Add(row);
            }
            SortedDictionary<string, object> trace = new SortedDictionary<string, object>(StringComparer.Ordinal);
            trace["artifact_type"] = "R7_BIDIRECTIONAL_CURRENT_EXECUTION_TRACE";
            trace["case_definition_git_blob"] = R7Constants.CaseDefinitionGitBlob;
            trace["expectation_git_blob"] = R7Constants.ExpectationGitBlob;
            trace["row_count"] = rows.Count;
            trace["rows"] = rows.ToArray();
            trace["run_id"] = runId;
            trace["schema_version"] = R7Constants.SchemaVersion;
            return StorePlain(trace, "evidence");
        }

        private static string BuildProcessIndex(string runId, R7SuiteResult suite, R7ProcessResult observer, R7ProcessResult comparator)
        {
            SortedDictionary<string, object> value = new SortedDictionary<string, object>(StringComparer.Ordinal);
            value["artifact_type"] = "R7_CURRENT_PROCESS_RECEIPT_INDEX";
            value["comparator_process_receipt_locator"] = comparator.ReceiptLocator;
            value["observation_process_receipt_locator"] = observer.ReceiptLocator;
            value["process_count"] = 3;
            value["run_id"] = runId;
            value["schema_version"] = R7Constants.SchemaVersion;
            value["suite_process_receipt_locator"] = suite.ProcessReceiptLocator;
            return StorePlain(value, "evidence");
        }

        private static void VerifyStoredFixtureEvidence(string runId, IDictionary<string, object> definition,
            IDictionary<string, object> current, IDictionary<string, object> observed, IDictionary<string, object> suiteReceipt)
        {
            bool required = StrictJson.RequireString(StrictJson.RequireObject(definition, "source_case"), "mutation").StartsWith("reparse_substitution_", StringComparison.Ordinal);
            bool invoked = R7Support.RequireBool(current, "fixture_helper_invoked");
            if (invoked != R7Support.RequireBool(observed, "fixture_helper_invoked")) throw new InvalidDataException("TERMINAL_FIXTURE_OBSERVATION_BINDING");
            int expectedCount = R7Support.RequireArray(R7Support.ReadCaseAuthority(), "cases").Count(delegate(object raw)
            {
                IDictionary<string, object> row = raw as IDictionary<string, object>;
                return row != null && StrictJson.RequireString(StrictJson.RequireObject(row, "source_case"), "mutation").StartsWith("reparse_substitution_", StringComparison.Ordinal);
            });
            if (!String.Equals(StrictJson.RequireString(suiteReceipt, "fixture_host_sha256"), R7Constants.SubjectFixtureHostSha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(suiteReceipt, "fixture_host_file_identity"), R7FileIdentity.Get(R7Constants.SubjectFixtureHostPath), StringComparison.Ordinal) ||
                !String.Equals(CryptoUtil.Sha256File(R7Constants.SubjectFixtureHostPath), R7Constants.SubjectFixtureHostSha256, StringComparison.Ordinal) ||
                R7Support.RequireLong(suiteReceipt, "fixture_process_receipt_count") != expectedCount)
                throw new InvalidDataException("TERMINAL_FIXTURE_SUITE_MEASUREMENT");
            if (!required)
            {
                if (invoked || !String.Equals(StrictJson.RequireString(current, "fixture_body_identity"), R7Constants.ZeroHash, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "fixture_helper_file_identity"), String.Empty, StringComparison.Ordinal) ||
                    R7Support.RequireLong(current, "fixture_helper_process_id") != 0 ||
                    !String.Equals(StrictJson.RequireString(current, "fixture_process_receipt_identity"), R7Constants.ZeroHash, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "fixture_process_receipt_locator"), String.Empty, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "fixture_reparse_snapshot_identity"), R7Constants.ZeroHash, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "fixture_reparse_snapshot_locator"), String.Empty, StringComparison.Ordinal))
                    throw new InvalidDataException("TERMINAL_UNEXPECTED_FIXTURE_EVIDENCE");
                return;
            }
            if (!invoked) throw new InvalidDataException("TERMINAL_REQUIRED_FIXTURE_MISSING");
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
                throw new InvalidDataException("TERMINAL_FIXTURE_LOCATOR_BINDING");
            byte[] bytes = R7Support.ReadContentAddressed(locator, "evidence");
            if (!String.Equals(CryptoUtil.Sha256Hex(bytes), identity, StringComparison.Ordinal)) throw new InvalidDataException("TERMINAL_FIXTURE_CONTENT_ADDRESS");
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
                throw new InvalidDataException("TERMINAL_FIXTURE_PROCESS_AUTHORITY");
            IDictionary<string, object> token = StrictJson.RequireObject(suiteReceipt, "subject_token_evidence");
            if (!String.Equals(StrictJson.RequireString(receipt, "authentication_type"), StrictJson.RequireString(token, "authentication_type"), StringComparison.Ordinal) ||
                !String.Equals(CanonicalJson.Serialize(R7Support.RequireArray(receipt, "group_sids")), CanonicalJson.Serialize(R7Support.RequireArray(token, "group_sids")), StringComparison.Ordinal))
                throw new InvalidDataException("TERMINAL_FIXTURE_TOKEN_INHERITANCE");
            SortedDictionary<string, object> body = new SortedDictionary<string, object>(receipt, StringComparer.Ordinal);
            string bodyIdentity = R7Support.RequireLowerHex(body, "body_identity", 64);
            body.Remove("body_identity");
            if (!String.Equals(bodyIdentity, CryptoUtil.Sha256Hex(CanonicalJson.SerializeBytes(body)), StringComparison.Ordinal) ||
                !String.Equals(bodyIdentity, StrictJson.RequireString(current, "fixture_body_identity"), StringComparison.Ordinal) ||
                !String.Equals(bodyIdentity, StrictJson.RequireString(observed, "fixture_body_identity"), StringComparison.Ordinal) ||
                !R7Support.IsLowerHex(StrictJson.RequireString(receipt, "fixture_nonce"), 64))
                throw new InvalidDataException("TERMINAL_FIXTURE_BODY_IDENTITY");
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
                throw new InvalidDataException("TERMINAL_FIXTURE_COMMAND_OR_PATH");
            byte[] snapshotBytes = R7Support.ReadContentAddressed(snapshotLocator, "evidence");
            if (!String.Equals(CryptoUtil.Sha256Hex(snapshotBytes), snapshotIdentity, StringComparison.Ordinal))
                throw new InvalidDataException("TERMINAL_FIXTURE_SNAPSHOT_CONTENT_ADDRESS");
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
                throw new InvalidDataException("TERMINAL_FIXTURE_SNAPSHOT_AUTHORITY");
            byte[] reparseData;
            try { reparseData = Convert.FromBase64String(StrictJson.RequireString(snapshot, "reparse_data_base64")); }
            catch (FormatException exception) { throw new InvalidDataException("TERMINAL_FIXTURE_SNAPSHOT_BASE64", exception); }
            if (!String.Equals(CryptoUtil.Sha256Hex(reparseData), StrictJson.RequireString(snapshot, "reparse_data_sha256"), StringComparison.Ordinal))
                throw new InvalidDataException("TERMINAL_FIXTURE_SNAPSHOT_HASH");
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
                throw new InvalidDataException("TERMINAL_FIXTURE_CURRENT_EVENT_TIME");
        }

        private static void VerifyCurrentRunSemantics(string runId, string eventLocator, string observationLocator, string traceLocator, string comparisonLocator, string processIndexLocator)
        {
            IDictionary<string, object> cases = R7Support.ReadCaseAuthority();
            IDictionary<string, object> expectations = R7Support.ReadExpectationAuthority();
            ValidateAuthoritySets(cases, expectations);
            IDictionary<string, object> source = R7Support.ParseCanonicalObject(R7Support.ReadContentAddressed(eventLocator, "evidence"));
            IDictionary<string, object> observations = R7Support.ParseCanonicalObject(R7Support.ReadContentAddressed(observationLocator, "evidence"));
            IDictionary<string, object> traces = R7Support.ParseCanonicalObject(R7Support.ReadContentAddressed(traceLocator, "evidence"));
            IDictionary<string, object> comparison = R7Support.ParseCanonicalObject(R7Support.ReadContentAddressed(comparisonLocator, "evidence"));
            IDictionary<string, object> processIndex = R7Support.ParseCanonicalObject(R7Support.ReadContentAddressed(processIndexLocator, "evidence"));
            if (!String.Equals(StrictJson.RequireString(source, "run_id"), runId, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(observations, "run_id"), runId, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(traces, "run_id"), runId, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(comparison, "run_id"), runId, StringComparison.Ordinal) ||
                R7Support.RequireArray(source, "events").Length != R7Constants.RequiredCaseCount ||
                R7Support.RequireArray(observations, "observations").Length != R7Constants.RequiredCaseCount ||
                R7Support.RequireArray(traces, "rows").Length != R7Constants.RequiredCaseCount ||
                R7Support.RequireLong(comparison, "discrepancy_count") != 0 ||
                !String.Equals(StrictJson.RequireString(comparison, "conformity"), "CONFORMANT", StringComparison.Ordinal))
                throw new InvalidDataException("TERMINAL_SEMANTIC_INPUT_REJECTED");
            Dictionary<string, IDictionary<string, object>> expectedById = R7Support.RequireArray(expectations, "expectations")
                .Cast<IDictionary<string, object>>().ToDictionary(delegate(IDictionary<string, object> row) { return StrictJson.RequireString(row, "case_id"); }, StringComparer.Ordinal);
            Dictionary<string, IDictionary<string, object>> definitionById = R7Support.RequireArray(cases, "cases")
                .Cast<IDictionary<string, object>>().ToDictionary(delegate(IDictionary<string, object> row) { return StrictJson.RequireString(row, "case_id"); }, StringComparer.Ordinal);
            Dictionary<string, IDictionary<string, object>> observationById = R7Support.RequireArray(observations, "observations")
                .Cast<IDictionary<string, object>>().ToDictionary(delegate(IDictionary<string, object> row) { return StrictJson.RequireString(row, "case_id"); }, StringComparer.Ordinal);
            Dictionary<string, IDictionary<string, object>> traceById = R7Support.RequireArray(traces, "rows")
                .Cast<IDictionary<string, object>>().ToDictionary(delegate(IDictionary<string, object> row) { return StrictJson.RequireString(row, "case_id"); }, StringComparer.Ordinal);
            string suiteLocator = StrictJson.RequireString(source, "suite_process_receipt_locator");
            string suiteIdentity = R7Support.ParseLocator(suiteLocator, "evidence");
            IDictionary<string, object> suiteReceipt = R7Support.VerifySignedEnvelope(R7Support.ReadContentAddressed(suiteLocator, "evidence"), verifier);
            if (!String.Equals(suiteLocator, StrictJson.RequireString(processIndex, "suite_process_receipt_locator"), StringComparison.Ordinal))
                throw new InvalidDataException("TERMINAL_SUITE_PROCESS_INDEX_REJECTED");
            HashSet<string> seen = new HashSet<string>(StringComparer.Ordinal);
            string prior = R7Constants.ZeroHash;
            foreach (object raw in R7Support.RequireArray(source, "events"))
            {
                IDictionary<string, object> current = (IDictionary<string, object>)raw;
                string caseId = StrictJson.RequireString(current, "case_id");
                if (!seen.Add(caseId) || !expectedById.ContainsKey(caseId) || !observationById.ContainsKey(caseId) || !traceById.ContainsKey(caseId) ||
                    !String.Equals(StrictJson.RequireString(current, "run_id"), runId, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "prior_event_hash"), prior, StringComparison.Ordinal) || !R7Support.RequireBool(current, "interface_invoked") ||
                    !R7Support.RequireBool(current, "forbidden_side_effect_absent") ||
                    !String.Equals(StrictJson.RequireString(current, "case_definition_git_blob"), R7Constants.CaseDefinitionGitBlob, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "expectation_git_blob"), R7Constants.ExpectationGitBlob, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "interface_identity"), R7Constants.SubjectDirectInterfaceSha256, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "interface_operation"), "execute_case", StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "subject_service_sha256"), R7Constants.SubjectServiceSha256, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "target_process_binary_sha256"), R7Constants.SubjectPythonSha256, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "invoking_process_receipt_identity"), suiteIdentity, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "event_constructor_binary_sha256"), binarySha256, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "suite_process_receipt_locator"), suiteLocator, StringComparison.Ordinal) ||
                    R7Support.RequireLong(current, "outer_post_ledger_sequence") != R7Support.RequireLong(current, "outer_pre_ledger_sequence") ||
                    R7Support.RequireLong(current, "subject_event_ledger_delta") < 1) throw new InvalidDataException("TERMINAL_EVENT_PROVENANCE_REJECTED");
                byte[] requestBytes = R7Support.ReadContentAddressed(StrictJson.RequireString(current, "public_request_locator"), "evidence");
                byte[] responseBytes = R7Support.ReadContentAddressed(StrictJson.RequireString(current, "public_response_locator"), "evidence");
                if (!String.Equals(CryptoUtil.Sha256Hex(requestBytes), StrictJson.RequireString(current, "request_sha256"), StringComparison.Ordinal) ||
                    !String.Equals(CryptoUtil.Sha256Hex(responseBytes), StrictJson.RequireString(current, "response_sha256"), StringComparison.Ordinal)) throw new InvalidDataException("TERMINAL_RAW_EVIDENCE_REJECTED");
                IDictionary<string, object> request = R7Support.ParseCanonicalObject(requestBytes);
                StrictJson.RequireExactKeys(request, "case_id", "operation");
                IDictionary<string, object> response = R7Support.ParseCanonicalObject(responseBytes);
                if (!String.Equals(StrictJson.RequireString(request, "case_id"), caseId, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(request, "operation"), "execute_case", StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(response, "status"), "OK", StringComparison.Ordinal))
                    throw new InvalidDataException("TERMINAL_PUBLIC_INTERFACE_BYTES_REJECTED");
                IDictionary<string, object> responseResult = StrictJson.RequireObject(response, "result");
                IDictionary<string, object> responseOutcome = StrictJson.RequireObject(responseResult, "outcome");
                IDictionary<string, object> responseInnerEvent = StrictJson.RequireObject(responseResult, "event");
                IDictionary<string, object> responseExecutionReceipt = StrictJson.RequireObject(responseResult, "execution_receipt");
                if (!String.Equals(StrictJson.RequireString(responseResult, "case_id"), caseId, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(responseOutcome, "status"), StrictJson.RequireString(current, "actual_outcome"), StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(responseOutcome, "code"), StrictJson.RequireString(current, "response_classification"), StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(responseOutcome, "enforcing_function"), StrictJson.RequireString(current, "enforcing_function"), StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(responseOutcome, "authority_identity"), StrictJson.RequireString(current, "actual_authority_identity"), StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(responseInnerEvent, "event_hash"), StrictJson.RequireString(current, "inner_event_hash"), StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(responseExecutionReceipt, "receipt_identity"), StrictJson.RequireString(current, "inner_execution_receipt_identity"), StringComparison.Ordinal))
                    throw new InvalidDataException("TERMINAL_RESPONSE_DERIVATION_REJECTED");
                IDictionary<string, object> expected = expectedById[caseId];
                if (!String.Equals(StrictJson.RequireString(current, "public_interface"), StrictJson.RequireString(expected, "expected_interface"), StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "actual_outcome"), StrictJson.RequireString(expected, "expected_outcome"), StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "response_classification"), StrictJson.RequireString(expected, "expected_response_classification"), StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "enforcing_function"), StrictJson.RequireString(expected, "expected_enforcing_function"), StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(current, "actual_authority_identity"), StrictJson.RequireString(expected, "expected_authority_source"), StringComparison.Ordinal)) throw new InvalidDataException("TERMINAL_EXPECTATION_COMPARISON_REJECTED");
                IDictionary<string, object> observed = observationById[caseId];
                if (!String.Equals(StrictJson.RequireString(observed, "event_hash"), StrictJson.RequireString(current, "event_hash"), StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(observed, "actual_outcome"), StrictJson.RequireString(current, "actual_outcome"), StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(observed, "response_classification"), StrictJson.RequireString(current, "response_classification"), StringComparison.Ordinal) ||
                    !R7Support.RequireBool(observed, "interface_invoked") || !R7Support.RequireBool(observed, "forbidden_side_effect_absent") ||
                    R7Support.RequireLong(observed, "outer_ledger_delta") != 0 || R7Support.RequireLong(observed, "subject_event_ledger_delta") < 1)
                    throw new InvalidDataException("TERMINAL_OBSERVATION_DERIVATION_REJECTED");
                IDictionary<string, object> trace = traceById[caseId];
                if (!String.Equals(StrictJson.RequireString(trace, "event_hash"), StrictJson.RequireString(current, "event_hash"), StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(trace, "case_definition_git_blob"), R7Constants.CaseDefinitionGitBlob, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(trace, "expectation_git_blob"), R7Constants.ExpectationGitBlob, StringComparison.Ordinal) ||
                    !String.Equals(StrictJson.RequireString(trace, "public_interface"), StrictJson.RequireString(current, "public_interface"), StringComparison.Ordinal))
                    throw new InvalidDataException("TERMINAL_TRACEABILITY_REJECTED");
                VerifyStoredFixtureEvidence(runId, definitionById[caseId], current, observationById[caseId], suiteReceipt);
                SortedDictionary<string, object> core = new SortedDictionary<string, object>(current, StringComparer.Ordinal);
                string recorded = StrictJson.RequireString(core, "event_hash");
                core.Remove("event_hash");
                if (!String.Equals(recorded, CryptoUtil.Sha256Hex(CanonicalJson.SerializeBytes(core)), StringComparison.Ordinal)) throw new InvalidDataException("TERMINAL_EVENT_HASH_REJECTED");
                prior = recorded;
            }
            if (seen.Count != R7Constants.RequiredCaseCount || !String.Equals(prior, StrictJson.RequireString(source, "event_root"), StringComparison.Ordinal))
                throw new InvalidDataException("TERMINAL_COVERAGE_OR_ROOT_REJECTED");
            if (!String.Equals(StrictJson.RequireString(suiteReceipt, "run_id"), runId, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(suiteReceipt, "launcher_sha256"), R7Constants.SubjectLauncherSha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(suiteReceipt, "python_sha256"), R7Constants.SubjectPythonSha256, StringComparison.Ordinal) ||
                R7Support.RequireLong(suiteReceipt, "case_count") != R7Constants.RequiredCaseCount)
                throw new InvalidDataException("TERMINAL_SUITE_PROCESS_RECEIPT_REJECTED");
            byte[] launchBytes = R7Support.ReadContentAddressed(StrictJson.RequireString(suiteReceipt, "launch_receipt_locator"), "evidence");
            IDictionary<string, object> launch = R7Support.ParseCanonicalObject(launchBytes);
            if (!String.Equals(StrictJson.RequireString(launch, "user_sid"), R7Constants.ServiceSid, StringComparison.Ordinal) || R7Support.RequireBool(launch, "is_administrator") ||
                !String.Equals(CanonicalJson.Serialize(launch), CanonicalJson.Serialize(StrictJson.RequireObject(suiteReceipt, "subject_token_evidence")), StringComparison.Ordinal) ||
                !String.Equals(CryptoUtil.Sha256Hex(launchBytes), StrictJson.RequireString(suiteReceipt, "subject_token_evidence_identity"), StringComparison.Ordinal))
                throw new InvalidDataException("TERMINAL_SUITE_LAUNCH_EVIDENCE_REJECTED");
            if (ledger.FindByContent("R7_REAL_SUITE_PROCESS_COMPLETED", suiteIdentity) == null) throw new InvalidDataException("TERMINAL_SUITE_LEDGER_MEMBERSHIP_REJECTED");
        }

        private static IDictionary<string, object> SingleLocatorSubject(string key, string locator)
        {
            SortedDictionary<string, object> value = new SortedDictionary<string, object>(StringComparer.Ordinal);
            value[key] = locator;
            return value;
        }

        private static string StorePlain(IDictionary<string, object> value, string kind)
        {
            if (kind != "evidence") throw new InvalidDataException("PLAIN_STORAGE_KIND");
            byte[] bytes = CanonicalJson.SerializeBytes(value);
            return R7Support.ContentLocator(kind, R7Support.StoreContentAddressed(R7Constants.EvidenceRoot, bytes, ".json"));
        }

        private static string StoreRawEvidence(byte[] bytes, string extension)
        {
            return R7Support.ContentLocator("evidence", R7Support.StoreContentAddressed(R7Constants.EvidenceRoot, bytes, extension));
        }

        private static R7ProcessResult LaunchWorker(string mode, string runId, IDictionary<string, object> subject)
        {
            string processNonce = R7Support.RandomHex(32);
            string sessionId = R7Support.RandomHex(16);
            string sessionDirectory = Path.Combine(R7Constants.SessionRoot, sessionId);
            Directory.CreateDirectory(sessionDirectory);
            string inputPath = Path.Combine(sessionDirectory, "input.json");
            SortedDictionary<string, object> input = new SortedDictionary<string, object>(StringComparer.Ordinal);
            input["mode"] = mode;
            input["process_nonce"] = processNonce;
            input["run_id"] = runId;
            input["subject"] = subject;
            byte[] inputBytes = CanonicalJson.SerializeBytes(input);
            R7Support.DurableCreate(inputPath, inputBytes);
            string arguments = mode + " " + runId + " " + processNonce + " " + QuoteArgument(inputPath);
            ProcessStartInfo start = new ProcessStartInfo();
            start.FileName = R7Constants.WorkerExecutablePath;
            start.Arguments = arguments;
            start.UseShellExecute = false;
            start.CreateNoWindow = true;
            start.RedirectStandardOutput = true;
            start.RedirectStandardError = true;
            start.WorkingDirectory = R7Constants.InstallRoot;
            start.EnvironmentVariables.Remove("PYTHONPATH");
            start.EnvironmentVariables.Remove("PYTHONHOME");
            DateTimeOffset launched = DateTimeOffset.UtcNow;
            System.Diagnostics.Process process = new System.Diagnostics.Process();
            process.StartInfo = start;
            if (!process.Start()) throw new InvalidOperationException("PROCESS_START_FAILED");
            int pid = process.Id;
            string stdout = process.StandardOutput.ReadToEnd();
            string stderr = process.StandardError.ReadToEnd();
            if (!process.WaitForExit(300000))
            {
                try { process.Kill(); } catch { }
                throw new InvalidOperationException("PROCESS_TIMEOUT");
            }
            DateTimeOffset completed = DateTimeOffset.UtcNow;
            int exitCode = process.ExitCode;
            process.Dispose();
            if (exitCode != 0 || String.IsNullOrEmpty(stdout)) throw new InvalidOperationException("PROCESS_INCOMPLETE");
            byte[] stdoutBytes = new UTF8Encoding(false, true).GetBytes(stdout);
            byte[] stderrBytes = new UTF8Encoding(false, true).GetBytes(stderr);
            string inputLocator = StoreRawEvidence(inputBytes, ".json");
            string stdoutLocator = StoreRawEvidence(stdoutBytes, ".bin");
            string stderrLocator = StoreRawEvidence(stderrBytes, ".bin");
            try { Directory.Delete(sessionDirectory, true); } catch { throw new IOException("SESSION_CLEANUP_FAILED"); }
            IDictionary<string, object> result = R7Support.ParseCanonicalObject(stdoutBytes);
            if (!String.Equals(StrictJson.RequireString(result, "status"), "COMPLETE", StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(result, "mode"), mode, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(result, "run_id"), runId, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(result, "process_nonce"), processNonce, StringComparison.Ordinal) ||
                R7Support.RequireLong(result, "worker_pid") != pid ||
                !String.Equals(StrictJson.RequireString(result, "input_identity"), CryptoUtil.Sha256Hex(inputBytes), StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(result, "worker_binary_sha256"), R7BuildConstants.WorkerSha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(result, "user_sid"), R7Constants.ServiceSid, StringComparison.Ordinal) ||
                R7Support.RequireBool(result, "is_administrator"))
                throw new InvalidDataException("PROCESS_RESULT_BINDING");

            SortedDictionary<string, object> receipt = new SortedDictionary<string, object>(StringComparer.Ordinal);
            receipt["artifact_type"] = "R7_PROCESS_EXECUTION_RECEIPT";
            receipt["command_identity"] = CryptoUtil.Sha256Hex(Encoding.UTF8.GetBytes(R7Constants.WorkerExecutablePath + "|" + arguments));
            receipt["completion_state"] = "COMPLETE";
            receipt["completion_time"] = completed.ToString("yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture);
            receipt["environment_identity"] = CryptoUtil.Sha256Hex(Encoding.UTF8.GetBytes("SERVICE_ACCOUNT_SANITIZED_NO_PYTHONPATH_NO_PYTHONHOME"));
            receipt["exit_code"] = exitCode;
            receipt["input_identity"] = CryptoUtil.Sha256Hex(inputBytes);
            receipt["input_locator"] = inputLocator;
            receipt["interface_version"] = R7Constants.InterfaceVersion;
            receipt["launcher_authority_identity"] = R7BuildConstants.PolicySha256;
            receipt["launcher_pid"] = System.Diagnostics.Process.GetCurrentProcess().Id;
            receipt["mode"] = mode;
            receipt["parent_service_binary_sha256"] = binarySha256;
            receipt["process_id"] = pid;
            receipt["process_nonce"] = processNonce;
            receipt["result"] = result;
            receipt["run_id"] = runId;
            receipt["schema_version"] = R7Constants.SchemaVersion;
            receipt["start_time"] = launched.ToString("yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture);
            receipt["stderr_identity"] = CryptoUtil.Sha256Hex(Encoding.UTF8.GetBytes(stderr));
            receipt["stderr_length"] = Encoding.UTF8.GetByteCount(stderr);
            receipt["stderr_locator"] = stderrLocator;
            receipt["stdout_identity"] = CryptoUtil.Sha256Hex(stdoutBytes);
            receipt["stdout_length"] = stdoutBytes.Length;
            receipt["stdout_locator"] = stdoutLocator;
            receipt["worker_file_identity"] = R7NativeIdentity.GetFileIdentity(R7Constants.WorkerExecutablePath);
            receipt["worker_sha256"] = R7BuildConstants.WorkerSha256;
            string locator = StoreSigned(receipt, "evidence");
            string identity = R7Support.ParseLocator(locator, "evidence");
            ledger.Append("R7_PROCESS_COMPLETED", Guid.NewGuid().ToString("D"), runId + "|" + mode + "|" + processNonce, identity);
            return new R7ProcessResult
            {
                Mode = mode,
                ProcessNonce = processNonce,
                ProcessId = pid,
                ReceiptLocator = locator,
                ReceiptIdentity = identity,
                Result = StrictJson.RequireObject(result, "result"),
                InputLocator = inputLocator,
                StdoutLocator = stdoutLocator,
                StderrLocator = stderrLocator
            };
        }

        private static string QuoteArgument(string value)
        {
            if (value.IndexOf('"') >= 0) throw new InvalidDataException("argument contains quote");
            return "\"" + value + "\"";
        }

        private static string Reconcile(string requestNonce, IDictionary<string, object> request)
        {
            string attemptId = R7Support.RequireLowerHex(request, "attempt_id", 64);
            string candidateLocator = StrictJson.RequireString(request, "candidate_locator");
            string freshLocator = StrictJson.RequireString(request, "fresh_locator");
            if (String.Equals(candidateLocator, freshLocator, StringComparison.Ordinal)) return Failure("RECONCILIATION_RECEIPTS_NOT_DISTINCT");
            R7TerminalView candidate = VerifyTerminal(candidateLocator);
            R7TerminalView fresh = VerifyTerminal(freshLocator);
            if (!String.Equals(candidate.AttemptId, attemptId, StringComparison.Ordinal) || !String.Equals(fresh.AttemptId, attemptId, StringComparison.Ordinal)) return Failure("RECONCILIATION_ATTEMPT_MISMATCH");
            if (!String.Equals(candidate.Phase, "CANDIDATE", StringComparison.Ordinal) || !String.Equals(fresh.Phase, "FRESH", StringComparison.Ordinal)) return Failure("RECONCILIATION_PHASE_MISMATCH");
            if (!String.Equals(candidate.Configuration, fresh.Configuration, StringComparison.Ordinal)) return Failure("RECONCILIATION_CONFIGURATION_MISMATCH");
            if (String.Equals(candidate.RunId, fresh.RunId, StringComparison.Ordinal) || String.Equals(candidate.RunNonce, fresh.RunNonce, StringComparison.Ordinal) ||
                String.Equals(candidate.EventRoot, fresh.EventRoot, StringComparison.Ordinal) || String.Equals(candidate.ReceiptIdentity, fresh.ReceiptIdentity, StringComparison.Ordinal) ||
                candidate.ProcessNonces.Overlaps(fresh.ProcessNonces)) return Failure("RECONCILIATION_PROVENANCE_NOT_DISTINCT");
            string[] semanticKeys = new string[] { "case_definition_git_blob", "case_definition_sha256", "expectation_git_blob", "expectation_sha256", "policy_sha256", "service_binary_sha256", "worker_sha256", "subject_commit" };
            foreach (string key in semanticKeys)
                if (!String.Equals(StrictJson.RequireString(candidate.Payload, key), StrictJson.RequireString(fresh.Payload, key), StringComparison.Ordinal)) return Failure("RECONCILIATION_SEMANTIC_MISMATCH");
            string reconciliationRunId = CryptoUtil.Sha256Hex(Encoding.UTF8.GetBytes(attemptId + "|" + candidate.ReceiptIdentity + "|" + fresh.ReceiptIdentity + "|" + requestNonce + "|" + Guid.NewGuid().ToString("D")));
            SortedDictionary<string, object> evaluatorSubject = new SortedDictionary<string, object>(StringComparer.Ordinal);
            evaluatorSubject["attempt_id"] = attemptId;
            evaluatorSubject["candidate_locator"] = candidateLocator;
            evaluatorSubject["fresh_locator"] = freshLocator;
            R7ProcessResult evaluator = LaunchWorker("reconcile", reconciliationRunId, evaluatorSubject);
            string evaluatorResultLocator = StorePlain(evaluator.Result, "evidence");
            ValidateReconciliationEvaluator(evaluatorResultLocator, evaluator.ReceiptLocator, reconciliationRunId, candidate, fresh);
            SortedDictionary<string, object> payload = new SortedDictionary<string, object>(StringComparer.Ordinal);
            payload["artifact_type"] = "R7_SIGNED_EXTERNAL_RECONCILIATION_RECEIPT";
            payload["attempt_id"] = attemptId;
            payload["candidate_event_root"] = candidate.EventRoot;
            payload["candidate_receipt_identity"] = candidate.ReceiptIdentity;
            payload["candidate_receipt_locator"] = candidateLocator;
            payload["candidate_run_id"] = candidate.RunId;
            payload["case_definition_git_blob"] = R7Constants.CaseDefinitionGitBlob;
            payload["configuration"] = candidate.Configuration;
            payload["expectation_git_blob"] = R7Constants.ExpectationGitBlob;
            payload["fresh_event_root"] = fresh.EventRoot;
            payload["fresh_receipt_identity"] = fresh.ReceiptIdentity;
            payload["fresh_receipt_locator"] = freshLocator;
            payload["fresh_run_id"] = fresh.RunId;
            payload["interface_version"] = R7Constants.InterfaceVersion;
            payload["issue_time"] = R7Support.Timestamp();
            payload["ledger_id"] = R7Constants.LedgerId;
            payload["policy_sha256"] = R7BuildConstants.PolicySha256;
            payload["provenance_disjoint"] = true;
            payload["public_key_identity"] = R7Constants.PublicKeyIdentity;
            payload["reconciliation_evaluator_result_locator"] = evaluatorResultLocator;
            payload["reconciliation_process_nonce"] = evaluator.ProcessNonce;
            payload["reconciliation_process_receipt_locator"] = evaluator.ReceiptLocator;
            payload["reconciliation_process_run_id"] = reconciliationRunId;
            payload["reconciliation_result"] = "SEMANTICALLY_EQUIVALENT_REAL_EXECUTIONS";
            payload["schema_version"] = R7Constants.SchemaVersion;
            payload["service_binary_sha256"] = binarySha256;
            payload["service_sid"] = R7Constants.ServiceSid;
            payload["subject_commit"] = R7Constants.SubjectCommit;
            payload["synthetic_result_class_absent"] = true;
            payload["worker_sha256"] = R7BuildConstants.WorkerSha256;
            string claim = CryptoUtil.Sha256Hex(CanonicalJson.SerializeBytes(payload));
            string subject = CryptoUtil.Sha256Hex(Encoding.UTF8.GetBytes(candidate.ReceiptIdentity + "|" + fresh.ReceiptIdentity));
            if (ledger.ContainsSubject("R7_RECONCILIATION_RECEIPT_COMMITTED", subject)) return Failure("RECONCILIATION_ALREADY_ISSUED");
            R7AppendResult reservation = ledger.Append("R7_RECONCILIATION_RESERVED", requestNonce, subject, claim);
            payload["ledger_reservation_entry_identity"] = reservation.EntryIdentity;
            payload["ledger_reservation_sequence"] = reservation.Sequence;
            payload["reconciliation_claim_identity"] = claim;
            string locator = StoreSigned(payload, "reconciliation");
            string identity = R7Support.ParseLocator(locator, "reconciliation");
            R7AppendResult commit = ledger.Append("R7_RECONCILIATION_RECEIPT_COMMITTED", Guid.NewGuid().ToString("D"), subject, identity);
            VerifyReconciliation(locator);
            SortedDictionary<string, object> response = BaseSuccess("R7_RECONCILIATION_RECEIPT_ISSUED");
            response["checkpoint_identity"] = commit.CheckpointIdentity;
            response["ledger_entry_identity"] = commit.EntryIdentity;
            response["ledger_sequence"] = commit.Sequence;
            response["reconciliation_identity"] = identity;
            response["reconciliation_locator"] = locator;
            return CanonicalJson.Serialize(response);
        }

        private static R7TerminalView VerifyTerminal(string locator)
        {
            string identity = R7Support.ParseLocator(locator, "terminal");
            IDictionary<string, object> payload = R7Support.VerifySignedEnvelope(R7Support.ReadContentAddressed(locator, "terminal"), verifier);
            if (!String.Equals(StrictJson.RequireString(payload, "artifact_type"), "R7_SIGNED_TERMINAL_RECEIPT", StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "interface_version"), R7Constants.InterfaceVersion, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "schema_version"), R7Constants.SchemaVersion, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "case_definition_git_blob"), R7Constants.CaseDefinitionGitBlob, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "case_definition_sha256"), R7Constants.CaseDefinitionSha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "expectation_git_blob"), R7Constants.ExpectationGitBlob, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "expectation_sha256"), R7Constants.ExpectationSha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "terminal_verifier_result"), "SEMANTICALLY_VERIFIED", StringComparison.Ordinal) ||
                R7Support.RequireLong(payload, "case_count") != R7Constants.RequiredCaseCount)
                throw new InvalidDataException("TERMINAL_RECEIPT_AUTHORITY");
            string runId = R7Support.RequireLowerHex(payload, "run_id", 64);
            string runNonce = R7Support.RequireLowerHex(payload, "run_nonce", 64);
            string attemptId = R7Support.RequireLowerHex(payload, "attempt_id", 64);
            string phase = R7Support.RequireEnum(payload, "phase", "CANDIDATE", "FRESH");
            string configuration = StrictJson.RequireString(payload, "configuration");
            if (!AllowedConfiguration(configuration)) throw new InvalidDataException("TERMINAL_CONFIGURATION");
            if (!String.Equals(StrictJson.RequireString(payload, "service_binary_sha256"), binarySha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "worker_sha256"), R7BuildConstants.WorkerSha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "policy_sha256"), R7BuildConstants.PolicySha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "subject_commit"), R7Constants.SubjectCommit, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "service_sid"), R7Constants.ServiceSid, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "public_key_identity"), R7Constants.PublicKeyIdentity, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "ledger_id"), R7Constants.LedgerId, StringComparison.Ordinal))
                throw new InvalidDataException("TERMINAL_FIXED_IDENTITY");
            SortedDictionary<string, object> claimBase = new SortedDictionary<string, object>(payload, StringComparer.Ordinal);
            string claim = StrictJson.RequireString(claimBase, "terminal_claim_identity");
            claimBase.Remove("ledger_reservation_entry_identity");
            claimBase.Remove("ledger_reservation_prior_root");
            claimBase.Remove("ledger_reservation_sequence");
            claimBase.Remove("terminal_claim_identity");
            if (!String.Equals(claim, CryptoUtil.Sha256Hex(CanonicalJson.SerializeBytes(claimBase)), StringComparison.Ordinal)) throw new InvalidDataException("TERMINAL_CLAIM_IDENTITY");
            R7LedgerState state = R7Support.VerifyLedger(verifier);
            IDictionary<string, object> commit = R7Support.FindLedgerEntry(state, "R7_TERMINAL_RECEIPT_COMMITTED", identity);
            if (!String.Equals(StrictJson.RequireString(commit, "subject_id"), runId, StringComparison.Ordinal)) throw new InvalidDataException("TERMINAL_LEDGER_SUBJECT");
            string reservationIdentity = StrictJson.RequireString(payload, "ledger_reservation_entry_identity");
            IDictionary<string, object> reservation = null;
            for (int index = 0; index < state.EntryIdentities.Count; index++) if (String.Equals(state.EntryIdentities[index], reservationIdentity, StringComparison.Ordinal)) reservation = state.Payloads[index];
            if (reservation == null || !String.Equals(StrictJson.RequireString(reservation, "operation"), "R7_TERMINAL_RESERVED", StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(reservation, "subject_id"), runId, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(reservation, "content_address"), claim, StringComparison.Ordinal) ||
                R7Support.RequireLong(reservation, "sequence") != R7Support.RequireLong(payload, "ledger_reservation_sequence"))
                throw new InvalidDataException("TERMINAL_RESERVATION");
            string eventLocator = StrictJson.RequireString(payload, "event_source_locator");
            string observationLocator = StrictJson.RequireString(payload, "observation_locator");
            string traceLocator = StrictJson.RequireString(payload, "traceability_locator");
            string comparisonLocator = StrictJson.RequireString(payload, "comparator_result_locator");
            string processIndexLocator = StrictJson.RequireString(payload, "process_index_locator");
            VerifyCurrentRunSemantics(runId, eventLocator, observationLocator, traceLocator, comparisonLocator, processIndexLocator);
            IDictionary<string, object> source = R7Support.ParseCanonicalObject(R7Support.ReadContentAddressed(eventLocator, "evidence"));
            if (!String.Equals(StrictJson.RequireString(source, "event_root"), StrictJson.RequireString(payload, "event_root"), StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(source, "subject_run_id"), StrictJson.RequireString(payload, "subject_run_id"), StringComparison.Ordinal))
                throw new InvalidDataException("TERMINAL_EVENT_SOURCE_BINDING");
            IDictionary<string, object> processIndex = R7Support.ParseCanonicalObject(R7Support.ReadContentAddressed(processIndexLocator, "evidence"));
            R7TerminalView view = new R7TerminalView();
            view.Locator = locator;
            view.ReceiptIdentity = identity;
            view.AttemptId = attemptId;
            view.Phase = phase;
            view.Configuration = configuration;
            view.RunId = runId;
            view.RunNonce = runNonce;
            view.EventIdentity = R7Support.ParseLocator(eventLocator, "evidence");
            view.EventRoot = StrictJson.RequireString(source, "event_root");
            view.Payload = payload;
            string[] processKeys = new string[] { "suite_process_receipt_locator", "observation_process_receipt_locator", "comparator_process_receipt_locator" };
            foreach (string key in processKeys)
            {
                string processLocator = StrictJson.RequireString(processIndex, key);
                IDictionary<string, object> processReceipt = R7Support.VerifySignedEnvelope(R7Support.ReadContentAddressed(processLocator, "evidence"), verifier);
                string nonce;
                object rawNonce;
                if (processReceipt.TryGetValue("process_nonce", out rawNonce)) nonce = rawNonce as string;
                else nonce = CryptoUtil.Sha256Hex(Encoding.UTF8.GetBytes(processLocator + "|" + StrictJson.RequireString(processReceipt, "run_id")));
                if (!R7Support.IsLowerHex(nonce, 64) || !view.ProcessNonces.Add(nonce)) throw new InvalidDataException("TERMINAL_PROCESS_NONCE");
            }
            return view;
        }

        private static void VerifyReconciliation(string locator)
        {
            string identity = R7Support.ParseLocator(locator, "reconciliation");
            IDictionary<string, object> payload = R7Support.VerifySignedEnvelope(R7Support.ReadContentAddressed(locator, "reconciliation"), verifier);
            if (!String.Equals(StrictJson.RequireString(payload, "artifact_type"), "R7_SIGNED_EXTERNAL_RECONCILIATION_RECEIPT", StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "reconciliation_result"), "SEMANTICALLY_EQUIVALENT_REAL_EXECUTIONS", StringComparison.Ordinal) ||
                !R7Support.RequireBool(payload, "provenance_disjoint") || !R7Support.RequireBool(payload, "synthetic_result_class_absent"))
                throw new InvalidDataException("RECONCILIATION_RECEIPT_AUTHORITY");
            R7TerminalView candidate = VerifyTerminal(StrictJson.RequireString(payload, "candidate_receipt_locator"));
            R7TerminalView fresh = VerifyTerminal(StrictJson.RequireString(payload, "fresh_receipt_locator"));
            if (String.Equals(candidate.RunId, fresh.RunId, StringComparison.Ordinal) || String.Equals(candidate.EventRoot, fresh.EventRoot, StringComparison.Ordinal) || candidate.ProcessNonces.Overlaps(fresh.ProcessNonces))
                throw new InvalidDataException("RECONCILIATION_PROVENANCE_REUSE");
            ValidateReconciliationEvaluator(
                StrictJson.RequireString(payload, "reconciliation_evaluator_result_locator"),
                StrictJson.RequireString(payload, "reconciliation_process_receipt_locator"),
                R7Support.RequireLowerHex(payload, "reconciliation_process_run_id", 64), candidate, fresh);
            R7LedgerState state = R7Support.VerifyLedger(verifier);
            R7Support.FindLedgerEntry(state, "R7_RECONCILIATION_RECEIPT_COMMITTED", identity);
            SortedDictionary<string, object> claimBase = new SortedDictionary<string, object>(payload, StringComparer.Ordinal);
            string claim = StrictJson.RequireString(claimBase, "reconciliation_claim_identity");
            claimBase.Remove("ledger_reservation_entry_identity");
            claimBase.Remove("ledger_reservation_sequence");
            claimBase.Remove("reconciliation_claim_identity");
            if (!String.Equals(claim, CryptoUtil.Sha256Hex(CanonicalJson.SerializeBytes(claimBase)), StringComparison.Ordinal)) throw new InvalidDataException("RECONCILIATION_CLAIM_IDENTITY");
        }

        private static void ValidateReconciliationEvaluator(string resultLocator, string processReceiptLocator, string reconciliationRunId,
            R7TerminalView candidate, R7TerminalView fresh)
        {
            IDictionary<string, object> result = R7Support.ParseCanonicalObject(R7Support.ReadContentAddressed(resultLocator, "evidence"));
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
                !String.Equals(StrictJson.RequireString(result, "policy_sha256"), R7BuildConstants.PolicySha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(result, "service_binary_sha256"), binarySha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(result, "worker_binary_sha256"), R7BuildConstants.WorkerSha256, StringComparison.Ordinal))
                throw new InvalidDataException("RECONCILIATION_EVALUATOR_RESULT_REJECTED");
            string processIdentity = R7Support.ParseLocator(processReceiptLocator, "evidence");
            IDictionary<string, object> receipt = R7Support.VerifySignedEnvelope(R7Support.ReadContentAddressed(processReceiptLocator, "evidence"), verifier);
            if (!String.Equals(StrictJson.RequireString(receipt, "mode"), "reconcile", StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(receipt, "run_id"), reconciliationRunId, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(receipt, "worker_sha256"), R7BuildConstants.WorkerSha256, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(receipt, "process_nonce"), StrictJson.RequireString(result, "reconciliation_process_nonce"), StringComparison.Ordinal))
                throw new InvalidDataException("RECONCILIATION_EVALUATOR_PROCESS_REJECTED");
            IDictionary<string, object> workerOutput = StrictJson.RequireObject(receipt, "result");
            IDictionary<string, object> embeddedResult = StrictJson.RequireObject(workerOutput, "result");
            if (!String.Equals(CanonicalJson.Serialize(embeddedResult), CanonicalJson.Serialize(result), StringComparison.Ordinal))
                throw new InvalidDataException("RECONCILIATION_EVALUATOR_OUTPUT_BINDING");
            R7Support.FindLedgerEntry(R7Support.VerifyLedger(verifier), "R7_PROCESS_COMPLETED", processIdentity);
        }

        private static bool AllowedConfiguration(string configuration)
        {
            foreach (object raw in R7Support.RequireArray(policy, "allowed_configurations"))
            {
                string item = raw as string;
                if (item == null) throw new InvalidDataException("CONFIGURATION_POLICY_SHAPE");
                if (String.Equals(item, configuration, StringComparison.Ordinal)) return true;
            }
            return false;
        }

        private static IDictionary<string, object> ResolveAttempt(string attemptId)
        {
            IDictionary<string, object> entry = ledger.FindBySubject("R7_ATTEMPT_ISSUED", attemptId);
            if (entry == null) throw new InvalidOperationException("ATTEMPT_NOT_FOUND");
            string identity = StrictJson.RequireString(entry, "content_address");
            byte[] bytes = R7Support.ReadContentAddressed(R7Support.ContentLocator("evidence", identity), "evidence");
            IDictionary<string, object> payload = R7Support.VerifySignedEnvelope(bytes, verifier);
            if (!String.Equals(StrictJson.RequireString(payload, "artifact_type"), "R7_ATTEMPT_AUTHORITY", StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(payload, "attempt_id"), attemptId, StringComparison.Ordinal))
                throw new InvalidDataException("ATTEMPT_EVIDENCE_REJECTED");
            return payload;
        }

        private static string StoreSigned(IDictionary<string, object> payload, string kind)
        {
            byte[] bytes = R7Support.CreateSignedEnvelope(payload, signer);
            string root = kind == "terminal" ? R7Constants.ReceiptRoot :
                          kind == "reconciliation" ? R7Constants.ReconciliationRoot : R7Constants.EvidenceRoot;
            string identity = R7Support.StoreContentAddressed(root, bytes, ".json");
            return R7Support.ContentLocator(kind, identity);
        }

        private static string Retrieve(IDictionary<string, object> request, string kind)
        {
            string locator = StrictJson.RequireString(request, "locator");
            byte[] bytes = R7Support.ReadContentAddressed(locator, kind);
            R7Support.VerifySignedEnvelope(bytes, verifier);
            if (kind == "terminal") VerifyTerminal(locator);
            else VerifyReconciliation(locator);
            SortedDictionary<string, object> response = BaseSuccess(kind == "terminal" ? "R7_TERMINAL_RECEIPT_RETRIEVED" : "R7_RECONCILIATION_RETRIEVED");
            response["content_base64"] = Convert.ToBase64String(bytes);
            response["content_length"] = bytes.Length;
            response["locator"] = locator;
            response["sha256"] = CryptoUtil.Sha256Hex(bytes);
            return CanonicalJson.Serialize(response);
        }

        private static string LoadIdempotentResponse(string requestNonce, string requestText)
        {
            string path = Path.Combine(R7Constants.ResponseRoot, requestNonce + ".json");
            if (!File.Exists(path)) return null;
            IDictionary<string, object> record = R7Support.ParseCanonicalObject(File.ReadAllBytes(path));
            StrictJson.RequireExactKeys(record, "request_identity", "request_nonce", "response");
            if (!String.Equals(StrictJson.RequireString(record, "request_nonce"), requestNonce, StringComparison.Ordinal) ||
                !String.Equals(StrictJson.RequireString(record, "request_identity"), R7Support.Sha256Utf8(requestText), StringComparison.Ordinal))
                throw new InvalidOperationException("REQUEST_NONCE_REPLAY_CONFLICT");
            return StrictJson.RequireString(record, "response");
        }

        private static void StoreIdempotentResponse(string requestNonce, string requestText, string response)
        {
            SortedDictionary<string, object> record = new SortedDictionary<string, object>(StringComparer.Ordinal);
            record["request_identity"] = R7Support.Sha256Utf8(requestText);
            record["request_nonce"] = requestNonce;
            record["response"] = response;
            string path = Path.Combine(R7Constants.ResponseRoot, requestNonce + ".json");
            byte[] bytes = CanonicalJson.SerializeBytes(record);
            if (!File.Exists(path)) R7Support.DurableCreate(path, bytes);
            else if (!File.ReadAllBytes(path).SequenceEqual(bytes)) throw new InvalidOperationException("IDEMPOTENCY_RECORD_CONFLICT");
        }

        private static SortedDictionary<string, object> BaseSuccess(string resultCode)
        {
            SortedDictionary<string, object> response = new SortedDictionary<string, object>(StringComparer.Ordinal);
            response["interface_version"] = R7Constants.InterfaceVersion;
            response["result_code"] = resultCode;
            response["status"] = "COMPLETE";
            return response;
        }

        private static string Failure(string code)
        {
            SortedDictionary<string, object> response = new SortedDictionary<string, object>(StringComparer.Ordinal);
            response["error_code"] = String.IsNullOrEmpty(code) ? "REQUEST_REJECTED" : code;
            response["interface_version"] = R7Constants.InterfaceVersion;
            response["status"] = "REJECTED";
            return CanonicalJson.Serialize(response);
        }

        private static string Health()
        {
            R7LedgerState state = R7Support.VerifyLedger(verifier);
            SortedDictionary<string, object> response = BaseSuccess("R7_AUTHORITY_HEALTHY");
            response["binary_file_identity"] = binaryFileIdentity;
            response["binary_sha256"] = binarySha256;
            response["healthy"] = true;
            response["ipc_identity"] = ipcIdentity;
            response["ledger_root"] = state.RootHash;
            response["ledger_sequence"] = state.Sequence;
            response["policy_sha256"] = R7BuildConstants.PolicySha256;
            response["public_key_identity"] = R7Constants.PublicKeyIdentity;
            response["repository_write_access"] = R7NativeIdentity.CanAddFile(@"C:\Webhook\RandleSystem");
            response["service_sid"] = R7Constants.ServiceSid;
            response["worker_sha256"] = R7BuildConstants.WorkerSha256;
            return CanonicalJson.Serialize(response);
        }

        private static string PublicTrust()
        {
            byte[] bytes = publicCertificate.Export(X509ContentType.Cert);
            SortedDictionary<string, object> response = BaseSuccess("R7_PUBLIC_TRUST_RETURNED");
            response["certificate_base64"] = Convert.ToBase64String(bytes);
            response["certificate_sha256"] = CryptoUtil.Sha256Hex(bytes);
            response["signature_algorithm"] = R7Constants.SignatureAlgorithm;
            return CanonicalJson.Serialize(response);
        }

        private static string LedgerStatus()
        {
            R7LedgerState state = R7Support.VerifyLedger(verifier);
            SortedDictionary<string, object> response = BaseSuccess("R7_LEDGER_VERIFIED");
            response["checkpoint_identity"] = state.CheckpointIdentity;
            response["genesis_identity"] = state.GenesisIdentity;
            response["ledger_id"] = R7Constants.LedgerId;
            response["root_hash"] = state.RootHash;
            response["sequence"] = state.Sequence;
            return CanonicalJson.Serialize(response);
        }

        private static bool IsAuthorizedCaller(string callerSid)
        {
            return String.Equals(callerSid, R7Constants.OperatorSid, StringComparison.Ordinal) ||
                   String.Equals(callerSid, R7Constants.SystemSid, StringComparison.Ordinal) ||
                   String.Equals(callerSid, R7Constants.ServiceSid, StringComparison.Ordinal);
        }

        internal static void RecordFault(Exception exception)
        {
            try
            {
                string value = exception.GetType().FullName + "|" + exception.HResult.ToString("x8", CultureInfo.InvariantCulture) + "|" + exception.Message;
                string path = Path.Combine(R7Constants.TrustRoot, "r7_service_initialization_fault.txt");
                R7Support.DurableReplace(path, new UTF8Encoding(false, true).GetBytes(value));
            }
            catch { }
        }
    }

    internal static class R7NativeIdentity
    {
        private const uint GenericRead = 0x80000000;
        private const uint FileAddFile = 0x00000002;
        private const uint FileShareRead = 0x00000001;
        private const uint FileShareWrite = 0x00000002;
        private const uint FileShareDelete = 0x00000004;
        private const uint OpenExisting = 3;
        private const uint FileFlagBackupSemantics = 0x02000000;
        private const uint FileFlagOpenReparsePoint = 0x00200000;
        private const uint FsctlGetReparsePoint = 0x000900A8;
        private const uint ProcessQueryLimitedInformation = 0x1000;
        private const uint TokenQuery = 0x0008;

        [StructLayout(LayoutKind.Sequential)]
        private struct ByHandleFileInformation
        {
            public uint FileAttributes;
            public System.Runtime.InteropServices.ComTypes.FILETIME CreationTime;
            public System.Runtime.InteropServices.ComTypes.FILETIME LastAccessTime;
            public System.Runtime.InteropServices.ComTypes.FILETIME LastWriteTime;
            public uint VolumeSerialNumber;
            public uint FileSizeHigh;
            public uint FileSizeLow;
            public uint NumberOfLinks;
            public uint FileIndexHigh;
            public uint FileIndexLow;
        }

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern SafeFileHandle CreateFile(string fileName, uint desiredAccess, uint shareMode, IntPtr securityAttributes, uint creationDisposition, uint flagsAndAttributes, IntPtr templateFile);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool GetFileInformationByHandle(SafeFileHandle handle, out ByHandleFileInformation information);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool DeviceIoControl(SafeFileHandle handle, uint controlCode, IntPtr inputBuffer, uint inputSize,
            [Out] byte[] outputBuffer, uint outputSize, out uint bytesReturned, IntPtr overlapped);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern IntPtr OpenProcess(uint desiredAccess, bool inheritHandle, int processId);

        [DllImport("advapi32.dll", SetLastError = true)]
        private static extern bool OpenProcessToken(IntPtr processHandle, uint desiredAccess, out IntPtr tokenHandle);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool CloseHandle(IntPtr handle);

        internal static string GetFileIdentity(string path)
        {
            using (SafeFileHandle handle = CreateFile(path, GenericRead, FileShareRead | FileShareWrite | FileShareDelete, IntPtr.Zero, OpenExisting, 0, IntPtr.Zero))
            {
                if (handle.IsInvalid) throw new IOException("unable to open file identity", Marshal.GetLastWin32Error());
                ByHandleFileInformation information;
                if (!GetFileInformationByHandle(handle, out information)) throw new IOException("unable to read file identity", Marshal.GetLastWin32Error());
                return information.VolumeSerialNumber.ToString("x8", CultureInfo.InvariantCulture) + ":" +
                       information.FileIndexHigh.ToString("x8", CultureInfo.InvariantCulture) + ":" +
                       information.FileIndexLow.ToString("x8", CultureInfo.InvariantCulture);
            }
        }

        internal static byte[] GetReparsePointData(string path)
        {
            using (SafeFileHandle handle = CreateFile(path, GenericRead, FileShareRead | FileShareWrite | FileShareDelete,
                IntPtr.Zero, OpenExisting, FileFlagOpenReparsePoint | FileFlagBackupSemantics, IntPtr.Zero))
            {
                if (handle.IsInvalid) throw new IOException("unable to open reparse point evidence", Marshal.GetLastWin32Error());
                byte[] buffer = new byte[16384];
                uint returned;
                if (!DeviceIoControl(handle, FsctlGetReparsePoint, IntPtr.Zero, 0, buffer, (uint)buffer.Length, out returned, IntPtr.Zero) || returned < 8 || returned > buffer.Length)
                    throw new IOException("unable to read reparse point evidence", Marshal.GetLastWin32Error());
                byte[] result = new byte[checked((int)returned)];
                Buffer.BlockCopy(buffer, 0, result, 0, checked((int)returned));
                return result;
            }
        }

        internal static bool CanAddFile(string directory)
        {
            using (SafeFileHandle handle = CreateFile(directory, FileAddFile, FileShareRead | FileShareWrite | FileShareDelete, IntPtr.Zero, OpenExisting, FileFlagBackupSemantics, IntPtr.Zero))
            {
                return !handle.IsInvalid;
            }
        }

        internal static IDictionary<string, object> GetProcessTokenEvidence(int processId)
        {
            IntPtr process = OpenProcess(ProcessQueryLimitedInformation, false, processId);
            if (process == IntPtr.Zero) throw new SecurityException("unable to open child process token authority", new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error()));
            IntPtr token = IntPtr.Zero;
            try
            {
                if (!OpenProcessToken(process, TokenQuery, out token)) throw new SecurityException("unable to query child process token", new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error()));
                using (WindowsIdentity identity = new WindowsIdentity(token))
                {
                    WindowsPrincipal principal = new WindowsPrincipal(identity);
                    List<object> groups = new List<object>();
                    if (identity.Groups != null)
                    {
                        foreach (IdentityReference reference in identity.Groups)
                        {
                            SecurityIdentifier sid = reference.Translate(typeof(SecurityIdentifier)) as SecurityIdentifier;
                            if (sid != null) groups.Add(sid.Value);
                        }
                    }
                    groups.Sort(delegate(object left, object right) { return StringComparer.Ordinal.Compare((string)left, (string)right); });
                    SortedDictionary<string, object> result = new SortedDictionary<string, object>(StringComparer.Ordinal);
                    result["authentication_type"] = identity.AuthenticationType ?? String.Empty;
                    result["group_sids"] = groups.ToArray();
                    result["impersonation_level"] = identity.ImpersonationLevel.ToString();
                    result["is_administrator"] = principal.IsInRole(WindowsBuiltInRole.Administrator);
                    result["process_id"] = processId;
                    result["user_sid"] = identity.User == null ? String.Empty : identity.User.Value;
                    if (!String.Equals(StrictJson.RequireString(result, "user_sid"), R7Constants.ServiceSid, StringComparison.Ordinal) || R7Support.RequireBool(result, "is_administrator"))
                        throw new SecurityException("child process token is outside restricted service authority");
                    return result;
                }
            }
            finally
            {
                if (token != IntPtr.Zero) CloseHandle(token);
                CloseHandle(process);
            }
        }
    }

    internal sealed class R7AuthorityWindowsService : ServiceBase
    {
        private volatile bool stopping;
        private Thread serverThread;

        internal R7AuthorityWindowsService()
        {
            ServiceName = R7Constants.ServiceName;
            CanStop = true;
            CanShutdown = true;
            AutoLog = true;
        }

        protected override void OnStart(string[] args)
        {
            try
            {
                RequestAdditionalTime(120000);
                PipeSecurity security = CreatePipeSecurity();
                R7AuthorityCore.Initialize(security);
                stopping = false;
            serverThread = new Thread(delegate()
            {
                try { ServerLoop(security); }
                catch (Exception exception) { R7AuthorityCore.RecordFault(exception); }
            });
                serverThread.IsBackground = true;
                serverThread.Name = "RandleTerminalAuthorityR7Pipe";
                serverThread.Start();
            }
            catch (Exception exception)
            {
                R7AuthorityCore.RecordFault(exception);
                throw;
            }
        }

        protected override void OnStop()
        {
            stopping = true;
            try
            {
                using (NamedPipeClientStream wake = new NamedPipeClientStream(".", R7Constants.PipeName, PipeDirection.Out))
                {
                    wake.Connect(1000);
                    wake.WriteByte((byte)'\n');
                }
            }
            catch { }
            if (serverThread != null) serverThread.Join(5000);
        }

        protected override void OnShutdown()
        {
            OnStop();
            base.OnShutdown();
        }

        private void ServerLoop(PipeSecurity security)
        {
            while (!stopping)
            {
                using (NamedPipeServerStream pipe = new NamedPipeServerStream(
                    R7Constants.PipeName, PipeDirection.InOut, 8, PipeTransmissionMode.Message,
                    PipeOptions.WriteThrough, R7Constants.MaximumMessageBytes, R7Constants.MaximumMessageBytes, security))
                {
                    try
                    {
                        pipe.WaitForConnection();
                        if (stopping) return;
                        string callerSid = String.Empty;
                        try
                        {
                            pipe.RunAsClient(delegate()
                            {
                                using (WindowsIdentity identity = WindowsIdentity.GetCurrent(true)) callerSid = identity.User.Value;
                            });
                        }
                        catch
                        {
                            WriteResponse(pipe, "{\"error_code\":\"CALLER_IDENTITY_UNAVAILABLE\",\"interface_version\":\"3.0.0-DRAFT\",\"status\":\"REJECTED\"}");
                            continue;
                        }
                        string request = ReadRequest(pipe);
                        string response = request == null ? "{\"error_code\":\"MESSAGE_TOO_LARGE\",\"interface_version\":\"3.0.0-DRAFT\",\"status\":\"REJECTED\"}" : R7AuthorityCore.Process(request, callerSid);
                        WriteResponse(pipe, response);
                    }
                    catch (IOException exception)
                    {
                        R7AuthorityCore.RecordFault(exception);
                    }
                }
            }
        }

        private static PipeSecurity CreatePipeSecurity()
        {
            PipeSecurity security = new PipeSecurity();
            security.SetAccessRuleProtection(true, false);
            security.AddAccessRule(new PipeAccessRule(new SecurityIdentifier(R7Constants.OperatorSid), PipeAccessRights.ReadWrite, AccessControlType.Allow));
            security.AddAccessRule(new PipeAccessRule(new SecurityIdentifier(R7Constants.SystemSid), PipeAccessRights.FullControl, AccessControlType.Allow));
            security.AddAccessRule(new PipeAccessRule(new SecurityIdentifier(R7Constants.ServiceSid), PipeAccessRights.FullControl, AccessControlType.Allow));
            return security;
        }

        private static string ReadRequest(Stream pipe)
        {
            MemoryStream buffer = new MemoryStream();
            while (true)
            {
                int value = pipe.ReadByte();
                if (value < 0 || value == '\n') break;
                if (buffer.Length >= R7Constants.MaximumMessageBytes) return null;
                buffer.WriteByte((byte)value);
            }
            try { return new UTF8Encoding(false, true).GetString(buffer.ToArray()); }
            catch { return String.Empty; }
        }

        private static void WriteResponse(Stream pipe, string response)
        {
            byte[] bytes = new UTF8Encoding(false, true).GetBytes(response + "\n");
            pipe.Write(bytes, 0, bytes.Length);
            pipe.Flush();
        }
    }

    internal static class Program
    {
        private static void Main()
        {
            ServiceBase.Run(new R7AuthorityWindowsService());
        }
    }
}
