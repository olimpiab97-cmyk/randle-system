using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Security;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;

namespace RandleAI.R7Remediation
{
    internal sealed class R7ReceiptClassification
    {
        internal string Identity;
        internal string ReceiptType;
        internal string Classification;
        internal string IssueTime;
        internal string SourceFamily;
        internal string SchemaVersion;
        internal string InterfaceVersion;
        internal string PolicySha256;
        internal string ServiceBinarySha256;
        internal string TrustIdentity;
        internal string AuthorityClass;
        internal long LedgerSequence;
        internal string LedgerEntryIdentity;

        internal SortedDictionary<string, object> ToJson()
        {
            return R7Json.Object(
                "authority_class", AuthorityClass,
                "classification", Classification,
                "identity", Identity,
                "interface_version", InterfaceVersion,
                "issue_time", IssueTime,
                "ledger_entry_identity", LedgerEntryIdentity,
                "ledger_sequence", LedgerSequence,
                "policy_sha256", PolicySha256,
                "receipt_type", ReceiptType,
                "schema_version", SchemaVersion,
                "service_binary_sha256", ServiceBinarySha256,
                "source_family", SourceFamily,
                "trust_identity", TrustIdentity);
        }
    }

    internal sealed class R7UpgradeVersionBinding
    {
        internal string AuthorizationIdentity;
        internal string ActivationIdentity;
        internal long ActivationSequence;
        internal string InterfaceVersion;
        internal string PolicySha256;
        internal string ServiceBinarySha256;
        internal string SourceCommit;
        internal string SourceTree;
        internal string TransitionNonce;
        internal Dictionary<string, string> ComponentSha256;
        internal Dictionary<string, string> ComponentPaths;
        internal Dictionary<string, string> DirectoryFileIdentities;
        internal Dictionary<string, string> InstalledFileIdentities;
    }

    internal sealed class R7PublicInteraction
    {
        internal string InteractionIdentity;
        internal SortedDictionary<string, object> Capture;
        internal SortedDictionary<string, object> Request;
        internal SortedDictionary<string, object> Response;
    }

    internal static class R7PublicVerifierProgram
    {
        private static int Main(string[] args)
        {
            try
            {
                R7RuntimeBoundary.Enforce(R7Fixed.TerminalInstallRoot);
                bool probe = args.Length == 6 && args[0] == "probe";
                if (!probe && args.Length > 1) throw new ArgumentException("usage: [output] | probe <case-id> <operation> <canonical-payload-base64> <public-output> <interaction-output>");
                string caseId = probe ? args[1] : String.Empty;
                string targetOperation = probe ? args[2] : String.Empty;
                SortedDictionary<string, object> targetPayload = probe ? DecodeCanonicalObject(args[3]) : null;
                string outputPath = probe ? Path.GetFullPath(args[4]) : args.Length == 0 ? String.Empty : Path.GetFullPath(args[0]);
                string interactionPath = probe ? Path.GetFullPath(args[5]) : String.Empty;
                SortedDictionary<string, object> verification;
                R7ActiveUpgrade activeUpgrade = R7ActiveUpgrade.ResolveAuthorization("PUBLIC_VERIFIER");
                R7TerminalPolicy terminalPolicy = R7TerminalPolicy.Load(activeUpgrade.TerminalPolicySha256);
                if (!String.Equals(terminalPolicy.SourceCommit, R7BuildIdentity.SourceCommit, StringComparison.Ordinal) || !String.Equals(terminalPolicy.SourceTree, R7BuildIdentity.SourceTree, StringComparison.Ordinal) || !R7Hash.FixedTimeEquals(terminalPolicy.DependencyManifestSha256, R7BuildIdentity.DependencyManifestSha256)) throw new InvalidDataException("PUBLIC_VERIFIER_POLICY_BINDING_INVALID");
                R7ComponentIdentity publicVerifierComponent = terminalPolicy.Component("PUBLIC_VERIFIER");
                string executable = Path.GetFullPath(Assembly.GetExecutingAssembly().Location);
                using (R7VerifiedFile binary = R7SafeFile.Open(executable, publicVerifierComponent.Path, R7Fixed.TerminalInstallRoot, publicVerifierComponent.Sha256, R7Fixed.SystemSid, null, terminalPolicy.VolumeIdentity))
                using (R7DependencyClosure dependencies = new R7DependencyClosure(R7Fixed.DependencyManifestPath, terminalPolicy.DependencyManifestSha256, R7Fixed.TerminalInstallRoot))
                {
                    activeUpgrade.RequireActivatedComponent("PUBLIC_VERIFIER", binary.Measurement.FileIdentity);
                    dependencies.VerifyNoNewModules();
                    verification = VerifyAll();
                    dependencies.VerifyNoNewModules();
                }
                SortedDictionary<string, object> result = verification;
                if (probe)
                {
                    SortedDictionary<string, object> targetResult = EvaluatePublicTarget(caseId, targetOperation, targetPayload, verification);
                    result = R7Json.Object(
                        "artifact_type", "R7_PUBLIC_VERIFIER_OUTER_CASE_RESULT",
                        "case_id", caseId,
                        "private_key_required", false,
                        "public_verification", verification,
                        "running_service_required_for_public_verification", false,
                        "schema_version", "1.0.0",
                        "status", "PASS",
                        "target_operation", targetOperation,
                        "target_payload_sha256", R7Hash.Bytes(R7Json.Encode(targetPayload)),
                        "target_result", targetResult);
                }
                byte[] bytes = R7Json.Encode(result);
                if (probe)
                {
                    string outputRoot = Path.GetDirectoryName(outputPath);
                    if (!outputPath.StartsWith(R7Fixed.PublicVerifierProbeRoot + Path.DirectorySeparatorChar, StringComparison.Ordinal) ||
                        !interactionPath.StartsWith(R7Fixed.PublicVerifierProbeRoot + Path.DirectorySeparatorChar, StringComparison.Ordinal) ||
                        !String.Equals(outputRoot, Path.GetDirectoryName(interactionPath), StringComparison.Ordinal) ||
                        String.Equals(outputPath, interactionPath, StringComparison.Ordinal)) throw new SecurityException("PUBLIC_VERIFIER_PROBE_PATH_INVALID");
                    R7SafeFile.MeasureDirectory(R7Fixed.PublicVerifierProbeRoot, R7Fixed.PublicVerifierProbeRoot, null, null, terminalPolicy.VolumeIdentity);
                    R7SafeFile.MeasureDirectory(outputRoot, outputRoot, null, null, null);
                    R7SafeFile.AssertAbsent(outputPath, outputPath, outputRoot);
                    R7SafeFile.AssertAbsent(interactionPath, interactionPath, outputRoot);
                    R7DurableFile.CreateNew(outputPath, bytes);
                    byte[] sent;
                    byte[] received;
                    SortedDictionary<string, object> signerResponse;
                    using (R7VerifiedFile written = R7SafeFile.Open(outputPath, outputPath, R7Fixed.PublicVerifierProbeRoot, R7Hash.Bytes(bytes), null, null, terminalPolicy.VolumeIdentity))
                    {
                        SortedDictionary<string, object> request = R7RoleClient.Request("SUBMIT_PUBLIC_VERIFICATION_EVIDENCE", R7Json.Object(
                            "case_id", caseId,
                            "output_measurement", written.Measurement.ToJson(),
                            "target_operation", targetOperation,
                            "target_payload", targetPayload));
                        signerResponse = R7Framing.Call(R7Fixed.TerminalPipe, request, 120000, out sent, out received);
                    }
                    SortedDictionary<string, object> invocation = R7Json.Object(
                        "artifact_type", "R7_HOSTILE_OUTER_INTERFACE_INVOCATION",
                        "pipe_name", R7Fixed.TerminalPipe,
                        "request_frame", Convert.ToBase64String(sent),
                        "request_frame_sha256", R7Hash.Bytes(sent),
                        "response", signerResponse,
                        "response_frame", Convert.ToBase64String(received),
                        "response_frame_sha256", R7Hash.Bytes(received),
                        "schema_version", "1.0.0");
                    byte[] invocationBytes = R7Json.Encode(invocation);
                    R7DurableFile.CreateNew(interactionPath, invocationBytes);
                    using (R7VerifiedFile interaction = R7SafeFile.Open(interactionPath, interactionPath, R7Fixed.PublicVerifierProbeRoot, R7Hash.Bytes(invocationBytes), null, null, terminalPolicy.VolumeIdentity)) { }
                    Console.WriteLine("PUBLIC_VERIFIER_OUTER_CASE_COMPLETED|" + caseId + "|" + R7Hash.Bytes(bytes));
                }
                else
                {
                    if (!String.IsNullOrEmpty(outputPath))
                    {
                        string outputRoot = Path.GetDirectoryName(outputPath);
                        R7SafeFile.MeasureDirectory(outputRoot, outputRoot, null, null, null);
                        R7SafeFile.AssertAbsent(outputPath, outputPath, outputRoot);
                        R7DurableFile.CreateNew(outputPath, bytes);
                        using (R7VerifiedFile written = R7SafeFile.Open(outputPath, outputPath, outputRoot, R7Hash.Bytes(bytes), null, null, null)) { }
                    }
                    Console.WriteLine(new System.Text.UTF8Encoding(false, true).GetString(bytes));
                }
                return 0;
            }
            catch (Exception exception)
            {
                Console.Error.WriteLine(exception.GetType().FullName + "|" + exception.Message);
                return 1;
            }
        }

        private static SortedDictionary<string, object> DecodeCanonicalObject(string encoded)
        {
            byte[] bytes;
            try { bytes = Convert.FromBase64String(encoded); }
            catch (FormatException) { throw new InvalidDataException("PUBLIC_TARGET_PAYLOAD_ENCODING_INVALID"); }
            SortedDictionary<string, object> value = RequireObject(R7Json.Parse(bytes));
            if (!R7Hash.FixedTimeEquals(R7Hash.Bytes(bytes), R7Hash.Bytes(R7Json.Encode(value)))) throw new InvalidDataException("PUBLIC_TARGET_PAYLOAD_NOT_CANONICAL");
            return value;
        }

        private static SortedDictionary<string, object> EvaluatePublicTarget(string caseId, string operation, SortedDictionary<string, object> payload, SortedDictionary<string, object> verification)
        {
            if (caseId.Length == 0 || operation.Length == 0 || R7Json.String(verification, "status", 1, 64) != "PASS" ||
                R7Json.Boolean(verification, "private_key_required") || R7Json.Boolean(verification, "running_service_required")) throw new InvalidDataException("PUBLIC_TARGET_PREREQUISITE_INVALID");
            if (operation == "VERIFY_ALL")
            {
                R7Json.ExactKeys(payload);
                SortedDictionary<string, object> result = R7PipeWindowsService.Success("ALL_ENTRIES_CLASSIFIED");
                result.Add("ledger_entry_count", R7Json.Integer(verification, "ledger_entry_count", 1, Int64.MaxValue));
                result.Add("ledger_root", R7Json.String(verification, "ledger_root", 64, 64));
                result.Add("receipt_count", R7Json.Integer(verification, "receipt_count", 1, Int64.MaxValue));
                return result;
            }
            if (operation == "GET_VERSION_HISTORY")
            {
                R7Json.ExactKeys(payload);
                SortedDictionary<string, object> result = R7PipeWindowsService.Success("VERSION_HISTORY_RESOLVED");
                result.Add("active_upgrade_authorization_identity", R7Json.String(verification, "active_upgrade_authorization_identity", 64, 64));
                result.Add("upgrade_version_binding_count", R7Json.Integer(verification, "upgrade_version_binding_count", 1, Int64.MaxValue));
                result.Add("version_rules", R7Json.Child(verification, "version_rules"));
                return result;
            }
            if (operation == "CLASSIFY_LEDGER_SEQUENCE")
            {
                R7Json.ExactKeys(payload, "sequence");
                long sequence = R7Json.Integer(payload, "sequence", 1, Int64.MaxValue);
                if (sequence != 332 && sequence != 678) throw new InvalidDataException("PUBLIC_SPECIAL_SEQUENCE_REQUIRED");
                SortedDictionary<string, object> row = R7Json.Child(verification, sequence == 332 ? "sequence_332" : "sequence_678");
                SortedDictionary<string, object> result = R7PipeWindowsService.Success(sequence == 332 ? "SEQUENCE_332_CLASSIFIED" : "SEQUENCE_678_CLASSIFIED");
                result.Add("classification", R7Json.String(row, "classification", 1, 256));
                result.Add("sequence", sequence);
                return result;
            }
            if (operation == "VERIFY_TERMINAL_RECEIPT" || operation == "VERIFY_RECONCILIATION" || operation == "CLASSIFY_RECEIPT")
            {
                bool wrongVersion = caseId == "HIS-001";
                if (wrongVersion) R7Json.ExactKeys(payload, "claimed_schema_version", "receipt_identity");
                else R7Json.ExactKeys(payload, "receipt_identity");
                string identity = R7Json.String(payload, "receipt_identity", 64, 64);
                SortedDictionary<string, object> row = FindPublicReceipt(verification, identity);
                string schemaVersion = R7Json.String(row, "schema_version", 1, 128);
                if (wrongVersion)
                {
                    string claimed = R7Json.String(payload, "claimed_schema_version", 1, 128);
                    if (String.Equals(claimed, schemaVersion, StringComparison.Ordinal)) throw new InvalidDataException("PUBLIC_WRONG_VERSION_ATTACK_NOT_PRESENT");
                    return R7PipeWindowsService.Rejection("VERSION_RULE_MISMATCH");
                }
                string receiptType = R7Json.String(row, "receipt_type", 1, 128);
                if (operation == "VERIFY_TERMINAL_RECEIPT" && receiptType != "TERMINAL_RUN_RECEIPT") throw new InvalidDataException("PUBLIC_RECEIPT_TYPE_MISMATCH");
                if (operation == "VERIFY_RECONCILIATION" && receiptType != "RECONCILIATION_RECEIPT") throw new InvalidDataException("PUBLIC_RECEIPT_TYPE_MISMATCH");
                bool current = R7Json.String(row, "source_family", 1, 128) == "REMEDIATION_V4";
                string code = operation == "VERIFY_TERMINAL_RECEIPT" ? "TERMINAL_RECEIPT_VALID" : operation == "VERIFY_RECONCILIATION" ? "RECONCILIATION_VALID" : current ? "CURRENT_RECEIPT_CLASSIFIED" : "OLDEST_RECEIPT_CLASSIFIED";
                SortedDictionary<string, object> result = R7PipeWindowsService.Success(code);
                result.Add("classification", R7Json.String(row, "classification", 1, 256));
                result.Add("receipt_identity", identity);
                result.Add("receipt_type", receiptType);
                return result;
            }
            throw new InvalidDataException("PUBLIC_TARGET_OPERATION_NOT_ALLOWED");
        }

        private static SortedDictionary<string, object> FindPublicReceipt(SortedDictionary<string, object> verification, string identity)
        {
            SortedDictionary<string, object> found = null;
            foreach (object raw in R7Json.Array(verification, "receipt_classifications"))
            {
                SortedDictionary<string, object> row = RequireObject(raw);
                if (R7Json.String(row, "identity", 64, 64) != identity) continue;
                if (found != null) throw new InvalidDataException("PUBLIC_RECEIPT_IDENTITY_AMBIGUOUS");
                found = row;
            }
            if (found == null) throw new InvalidDataException("PUBLIC_RECEIPT_IDENTITY_UNRESOLVED");
            return found;
        }

        internal static SortedDictionary<string, object> VerifyRetainedLegacyHistory(string ledgerRoot, string certificatePath, string receiptRoot, string reconciliationRoot, string evidenceRoot, string responseRoot, string classificationRegistryPath)
        {
            ledgerRoot = Path.GetFullPath(ledgerRoot);
            certificatePath = Path.GetFullPath(certificatePath);
            receiptRoot = Path.GetFullPath(receiptRoot);
            reconciliationRoot = Path.GetFullPath(reconciliationRoot);
            evidenceRoot = Path.GetFullPath(evidenceRoot);
            responseRoot = Path.GetFullPath(responseRoot);
            classificationRegistryPath = Path.GetFullPath(classificationRegistryPath);
            using (X509Certificate2 certificate = R7Crypto.LoadPublicCertificate(certificatePath, R7Fixed.TerminalPublicKeyIdentity, Path.GetDirectoryName(certificatePath)))
            using (RSA verifier = System.Security.Cryptography.X509Certificates.RSACertificateExtensions.GetRSAPublicKey(certificate))
            {
                R7VersionedLedger ledger = new R7VersionedLedger(ledgerRoot, R7Fixed.LedgerId, R7Fixed.TerminalPublicKeyIdentity, R7Fixed.TerminalSid, null, verifier);
                string volumeIdentity = R7SafeFile.MeasureDirectory(ledgerRoot, ledgerRoot, null, null, null).VolumeIdentity;
                List<R7ReceiptClassification> classifications = new List<R7ReceiptClassification>();
                VerifyLegacyReceiptDirectory(receiptRoot, receiptRoot, "TERMINAL_RECEIPT", false, ledger, verifier, volumeIdentity, classifications);
                VerifyLegacyReceiptDirectory(reconciliationRoot, receiptRoot, "RECONCILIATION_RECEIPT", true, ledger, verifier, volumeIdentity, classifications);
                SortedDictionary<string, object> registry;
                using (R7VerifiedFile file = R7SafeFile.Open(classificationRegistryPath, classificationRegistryPath, Path.GetDirectoryName(classificationRegistryPath), R7BuildIdentity.HistoricalClassificationRegistrySha256, null, null, volumeIdentity)) registry = RequireObject(R7Json.Parse(file.Bytes));
                object[] bindings = R7HistoricalClassification.VerifyRegistry(registry, ledger, verifier, volumeIdentity, evidenceRoot, receiptRoot, responseRoot);
                int terminal = 0;
                int reconciliation = 0;
                HashSet<string> versions = new HashSet<string>(StringComparer.Ordinal);
                foreach (R7ReceiptClassification classification in classifications)
                {
                    if (classification.ReceiptType == "TERMINAL_RECEIPT") terminal++;
                    else if (classification.ReceiptType == "RECONCILIATION_RECEIPT") reconciliation++;
                    else throw new InvalidDataException("LEGACY_RECEIPT_TYPE_UNEXPECTED");
                    if (classification.Classification != "STRUCTURALLY_VALID_REJECTED_NONAUTHORITATIVE_CANDIDATE_EVIDENCE") throw new InvalidDataException("LEGACY_RECEIPT_AUTHORITY_REINTERPRETATION");
                    versions.Add(classification.SchemaVersion + "|" + classification.InterfaceVersion + "|" + classification.PolicySha256 + "|" + classification.ServiceBinarySha256);
                }
                bool pass = ledger.Sequence == 678 && terminal == 64 && reconciliation == 31 && bindings.Length == 10;
                return R7Json.Object(
                    "artifact_type", "R7_RETAINED_LEGACY_HISTORY_VERIFICATION",
                    "classification_binding_count", (long)bindings.Length,
                    "ledger_entry_count", ledger.Sequence,
                    "ledger_root", ledger.RootHash,
                    "private_key_required", false,
                    "reconciliation_receipt_count", (long)reconciliation,
                    "schema_version", "1.0.0",
                    "status", pass ? "PASS" : "FAIL",
                    "terminal_receipt_count", (long)terminal,
                    "version_binding_count", (long)versions.Count);
            }
        }

        internal static SortedDictionary<string, object> VerifyAll()
        {
            using (X509Certificate2 terminalCertificate = R7Crypto.LoadPublicCertificate(R7Fixed.TerminalPublicCertificatePath, R7Fixed.TerminalPublicKeyIdentity, Path.GetDirectoryName(R7Fixed.TerminalPublicCertificatePath)))
            using (RSA terminalVerifier = System.Security.Cryptography.X509Certificates.RSACertificateExtensions.GetRSAPublicKey(terminalCertificate))
            using (X509Certificate2 upgradeCertificate = R7Crypto.LoadPublicCertificate(R7Fixed.UpgradePublicCertificatePath, R7BuildIdentity.UpgradePublicCertificateSha256, Path.GetDirectoryName(R7Fixed.UpgradePublicCertificatePath)))
            using (RSA upgradeVerifier = System.Security.Cryptography.X509Certificates.RSACertificateExtensions.GetRSAPublicKey(upgradeCertificate))
            {
                R7VersionedLedger terminalLedger = new R7VersionedLedger(R7Fixed.LedgerRoot, R7Fixed.LedgerId, R7Fixed.TerminalPublicKeyIdentity, R7Fixed.TerminalSid, null, terminalVerifier);
                UpgradePublicPolicy upgradePolicy = LoadUpgradePolicy();
                R7VersionedLedger upgradeLedger = new R7VersionedLedger(R7Fixed.UpgradeLedgerRoot, upgradePolicy.LedgerId, R7BuildIdentity.UpgradePublicCertificateSha256, R7Fixed.UpgradeSid, null, upgradeVerifier);
                SortedDictionary<string, object> upgradeGenesisVerification = VerifyUpgradeGenesis(upgradeLedger, upgradePolicy);
                R7AuthoritySet authority = new R7AuthoritySet(new R7AuthorityIdentities(R7BuildIdentity.RequirementRegistrySha256, R7BuildIdentity.CaseDefinitionsSha256, R7BuildIdentity.ExpectationsSha256, R7BuildIdentity.CoverageProofSha256, R7BuildIdentity.AuthoritySourceManifestSha256));
                string terminalVolumeIdentity = R7SafeFile.MeasureDirectory(R7Fixed.LedgerRoot, R7Fixed.LedgerRoot, null, null, null).VolumeIdentity;
                R7ObjectStore objects = new R7ObjectStore(R7Fixed.ObjectRoot, R7Fixed.TerminalSid, terminalVolumeIdentity);
                R7ObjectStore upgradeObjects = new R7ObjectStore(R7Fixed.UpgradeObjectRoot, R7Fixed.UpgradeSid, upgradePolicy.VolumeIdentity);
                R7EvidenceStore interactionEvidence = new R7EvidenceStore(R7Fixed.EvidenceRoot, objects, R7Fixed.TerminalSid, terminalVolumeIdentity);
                string activeAuthorizationIdentity;
                using (R7VerifiedFile activeAuthorization = R7SafeFile.Open(R7Fixed.ActiveTransitionPath, R7Fixed.ActiveTransitionPath, Path.GetDirectoryName(R7Fixed.ActiveTransitionPath), null, R7Fixed.SystemSid, null, terminalVolumeIdentity)) activeAuthorizationIdentity = activeAuthorization.Measurement.Sha256;
                Dictionary<string, R7UpgradeVersionBinding> upgradeBindings = LoadUpgradeVersionBindings(upgradeLedger, upgradeObjects, upgradeVerifier, upgradePolicy, terminalVolumeIdentity, activeAuthorizationIdentity);
                R7UpgradeVersionBinding activeVersion = upgradeBindings[activeAuthorizationIdentity];
                R7TerminalPolicy terminalPolicy = R7TerminalPolicy.Load(activeVersion.PolicySha256);
                SortedDictionary<string, object> buildClosureVerification = R7BuildClosureVerifier.VerifyTerminalBuildAndInstalledInventory(terminalPolicy, activeVersion, upgradePolicy.UpgradeClientSha256, upgradePolicy.InstallerScriptSha256, terminalVolumeIdentity);
                SortedDictionary<string, object> upgradeInteractionVerification = VerifyUpgradeInteractions(upgradeLedger, upgradeObjects, upgradePolicy);
                SortedDictionary<string, object> terminalRecoveryVerification = VerifyCheckpointRecoveryHistory(terminalLedger, objects, R7Fixed.RecoveryRoot, "R7R_CHECKPOINT_RECOVERY_INTENT", true, R7Fixed.TerminalSid, terminalVolumeIdentity, terminalVerifier, R7Fixed.TerminalPublicKeyIdentity, R7Fixed.LedgerId);
                SortedDictionary<string, object> upgradeRecoveryVerification = VerifyCheckpointRecoveryHistory(upgradeLedger, upgradeObjects, R7Fixed.UpgradeRecoveryRoot, "UPGRADE_CHECKPOINT_RECOVERY_INTENT", false, R7Fixed.UpgradeSid, upgradePolicy.VolumeIdentity, upgradeVerifier, R7BuildIdentity.UpgradePublicCertificateSha256, upgradePolicy.LedgerId);
                Dictionary<string, R7TransactionSnapshot> receiptTransactions = ResolveTransactionStates(terminalLedger, objects, terminalVolumeIdentity);
                SortedDictionary<string, object> responseArtifactVerification = VerifyResponseArtifacts(receiptTransactions, terminalVolumeIdentity);
                List<R7ReceiptClassification> classifications = new List<R7ReceiptClassification>();
                VerifyLegacyReceiptDirectory(R7Fixed.LegacyReceiptRoot, R7Fixed.LegacyReceiptRoot, "TERMINAL_RECEIPT", false, terminalLedger, terminalVerifier, terminalVolumeIdentity, classifications);
                VerifyLegacyReceiptDirectory(R7Fixed.LegacyReconciliationRoot, R7Fixed.LegacyReceiptRoot, "RECONCILIATION_RECEIPT", true, terminalLedger, terminalVerifier, terminalVolumeIdentity, classifications);
                VerifyV4Receipts(terminalVerifier, receiptTransactions, terminalLedger, objects, interactionEvidence, authority, upgradeBindings, terminalVolumeIdentity, classifications);
                classifications.Sort(delegate(R7ReceiptClassification left, R7ReceiptClassification right)
                {
                    int time = StringComparer.Ordinal.Compare(left.IssueTime, right.IssueTime);
                    return time != 0 ? time : StringComparer.Ordinal.Compare(left.Identity, right.Identity);
                });
                int authoritative = 0;
                int rejectedCandidate = 0;
                int aborted = 0;
                int incomplete = 0;
                int superseded = 0;
                foreach (R7ReceiptClassification item in classifications)
                {
                    if (item.Classification == "VALID_AUTHORITATIVE_RECEIPT" || item.Classification == "VALID_AUTHORITATIVE_RECONCILIATION") authoritative++;
                    else if (item.Classification.IndexOf("REJECTED", StringComparison.Ordinal) >= 0 || item.Classification.IndexOf("CANDIDATE", StringComparison.Ordinal) >= 0) rejectedCandidate++;
                    else if (item.Classification.IndexOf("ABORT", StringComparison.Ordinal) >= 0) aborted++;
                    else if (item.Classification.IndexOf("INCOMPLETE", StringComparison.Ordinal) >= 0) incomplete++;
                    else if (item.Classification.IndexOf("SUPERSEDED", StringComparison.Ordinal) >= 0) superseded++;
                }
                object[] classificationRows = new object[classifications.Count];
                for (int i = 0; i < classifications.Count; i++) classificationRows[i] = classifications[i].ToJson();
                R7LedgerRecord sequence332 = terminalLedger.FindSequence(332);
                R7LedgerRecord sequence678 = terminalLedger.FindSequence(678);
                if (sequence332 == null || sequence678 == null) throw new InvalidDataException("HISTORICAL_SPECIAL_SEQUENCE_MISSING");
                R7LedgerRecord[] historyClassifications = terminalLedger.Find("R7R_HISTORICAL_CLASSIFICATION_COMMITTED", R7BuildIdentity.HistoricalClassificationRegistrySha256);
                if (historyClassifications.Length != 1) throw new InvalidDataException("HISTORICAL_CLASSIFICATION_RECORD_MISSING_OR_DUPLICATE");
                SortedDictionary<string, object> historyProof = objects.Get(historyClassifications[0].ContentAddress);
                R7Json.ExactKeys(historyProof, "classification_time", "governed_registry", "governed_registry_raw_sha256", "infrastructure_range", "rejected_v3_range", "schema_version", "sequence_332_reuse", "sequence_678_reuse", "superseded_policy_sha256", "superseded_service_binary_sha256", "verified_historical_bindings");
                if (R7Json.String(historyProof, "governed_registry_raw_sha256", 64, 64) != R7BuildIdentity.HistoricalClassificationRegistrySha256) throw new InvalidDataException("HISTORICAL_CLASSIFICATION_REGISTRY_MISMATCH");
                SortedDictionary<string, object> historyRegistry;
                using (R7VerifiedFile historyFile = R7SafeFile.Open(R7Fixed.HistoricalClassificationPath, R7Fixed.HistoricalClassificationPath, Path.GetDirectoryName(R7Fixed.HistoricalClassificationPath), R7BuildIdentity.HistoricalClassificationRegistrySha256, R7Fixed.SystemSid, null, terminalVolumeIdentity)) historyRegistry = RequireObject(R7Json.Parse(historyFile.Bytes));
                object[] verifiedHistoricalBindings = R7HistoricalClassification.VerifyRegistry(historyRegistry, terminalLedger, terminalVerifier, terminalVolumeIdentity);
                SortedDictionary<string, object> embeddedRegistry = R7Json.Child(historyProof, "governed_registry");
                if (!R7Hash.FixedTimeEquals(R7Hash.Bytes(R7Json.Encode(historyRegistry)), R7Hash.Bytes(R7Json.Encode(embeddedRegistry)))) throw new InvalidDataException("HISTORICAL_CLASSIFICATION_EMBEDDED_REGISTRY_MISMATCH");
                if (!R7Hash.FixedTimeEquals(R7Hash.Bytes(R7Json.Encode(verifiedHistoricalBindings)), R7Hash.Bytes(R7Json.Encode(R7Json.Array(historyProof, "verified_historical_bindings"))))) throw new InvalidDataException("HISTORICAL_CLASSIFICATION_BINDINGS_MISMATCH");
                string oldest = classifications.Count == 0 ? String.Empty : classifications[0].Identity;
                string newest = classifications.Count == 0 ? String.Empty : classifications[classifications.Count - 1].Identity;
                int recoveryRecords = terminalLedger.Find("R7R_CHECKPOINT_RECOVERY_INTENT", null).Length + terminalLedger.Find("R7R_ABORTED", null).Length + terminalLedger.Find("R7R_SUPERSEDED", null).Length;
                int upgradeAuthorizations = upgradeLedger.Find("UPGRADE_AUTHORIZATION_ISSUED", null).Length;
                int upgradeActivations = upgradeLedger.Find("UPGRADE_ACTIVATED", null).Length;
                if (upgradeAuthorizations < 1 || upgradeActivations < 1) throw new InvalidDataException("UPGRADE_HISTORY_INCOMPLETE");
                return R7Json.Object(
                    "artifact_type", "R7_VERSION_AWARE_PUBLIC_VERIFICATION_RESULT",
                    "build_closure_verification", buildClosureVerification,
                    "checkpoint_recovery_verification", terminalRecoveryVerification,
                    "checkpoint_identity", terminalLedger.CheckpointIdentity,
                    "checkpoint_recovery_required", !String.IsNullOrEmpty(terminalLedger.CheckpointRecoveryReason),
                    "classification_counts", R7Json.Object(
                        "aborted", (long)aborted,
                        "authoritative", (long)authoritative,
                        "incomplete", (long)incomplete,
                        "rejected_candidate", (long)rejectedCandidate,
                        "superseded", (long)superseded),
                    "current_receipt_identity", newest,
                    "ledger_entry_count", terminalLedger.Sequence,
                    "ledger_id", R7Fixed.LedgerId,
                    "ledger_root", terminalLedger.RootHash,
                    "oldest_retained_receipt_identity", oldest,
                    "private_key_required", false,
                    "receipt_classifications", classificationRows,
                    "receipt_count", (long)classifications.Count,
                    "recovery_record_count", (long)recoveryRecords,
                    "response_artifact_verification", responseArtifactVerification,
                    "running_service_required", false,
                    "schema_version", "1.0.0",
                    "sequence_332", R7Json.Object("classification", "INCOMPLETE_ISSUANCE_SUPERSEDED_NONAUTHORITY", "content_address", sequence332.ContentAddress, "entry_hash", sequence332.EntryHash, "entry_identity", sequence332.EntryIdentity, "reuse", "PERMANENTLY_FORBIDDEN", "terminal_receipt", "ABSENT"),
                    "sequence_678", R7Json.Object("classification", "ABORTED_CLIENT_REJECTED_ISSUANCE_NONAUTHORITY", "content_address", sequence678.ContentAddress, "entry_hash", sequence678.EntryHash, "entry_identity", sequence678.EntryIdentity, "reuse", "PERMANENTLY_FORBIDDEN", "terminal_receipt", "ABSENT"),
                    "status", "PASS",
                    "terminal_public_key_identity", R7Fixed.TerminalPublicKeyIdentity,
                    "active_upgrade_authorization_identity", activeAuthorizationIdentity,
                    "upgrade_activation_count", (long)upgradeActivations,
                    "upgrade_authorization_count", (long)upgradeAuthorizations,
                    "upgrade_ledger_id", upgradePolicy.LedgerId,
                    "upgrade_ledger_root", upgradeLedger.RootHash,
                    "upgrade_ledger_sequence", upgradeLedger.Sequence,
                    "upgrade_interaction_verification", upgradeInteractionVerification,
                    "upgrade_checkpoint_recovery_verification", upgradeRecoveryVerification,
                    "upgrade_genesis_verification", upgradeGenesisVerification,
                    "upgrade_public_key_identity", R7BuildIdentity.UpgradePublicCertificateSha256,
                    "upgrade_version_binding_count", (long)upgradeBindings.Count,
                    "verified_historical_binding_count", (long)verifiedHistoricalBindings.Length,
                    "version_rules", R7Json.Object(
                        "sequences_1_5", "VALID_PROVISIONED_INFRASTRUCTURE_AUTHORITY",
                        "sequences_6_678", "STRUCTURALLY_VALID_REJECTED_NONAUTHORITATIVE_CANDIDATE_EVIDENCE",
                        "v4_receipts", "CLASSIFIED_BY_COMMITTED_TRANSACTION_AND_ISSUANCE_POLICY"));
            }
        }

        private static SortedDictionary<string, object> VerifyCheckpointRecoveryHistory(R7VersionedLedger ledger, R7ObjectStore objects, string recoveryRoot, string recoveryOperation, bool terminalFormat, string expectedFileOwnerSid, string expectedVolumeIdentity, RSA verifier, string publicKeyIdentity, string ledgerId)
        {
            if (!String.IsNullOrEmpty(ledger.CheckpointRecoveryReason) || ledger.CheckpointIdentity == R7Fixed.ZeroHash) throw new InvalidDataException("PUBLIC_CHECKPOINT_RECOVERY_STILL_REQUIRED:" + recoveryOperation);
            R7SafeFile.MeasureDirectory(recoveryRoot, recoveryRoot, R7Fixed.SystemSid, null, expectedVolumeIdentity);
            HashSet<string> expectedArtifacts = new HashSet<string>(StringComparer.Ordinal);
            R7LedgerRecord[] records = ledger.Find(recoveryOperation, null);
            foreach (R7LedgerRecord record in records)
            {
                SortedDictionary<string, object> content = objects.Get(record.ContentAddress);
                R7Json.ExactKeys(content, "checkpoint_identity_before", "ledger_root_before", "ledger_sequence_before", "pending_checkpoint_artifacts", "reason", "recovery_subject", "recovery_target_sequence");
                string priorIdentity = R7Json.String(content, "checkpoint_identity_before", 64, 64);
                string reason = R7Json.String(content, "reason", 1, 4096);
                string recoverySubject = R7Json.String(content, "recovery_subject", 64, 64);
                long sequenceBefore = R7Json.Integer(content, "ledger_sequence_before", 0, Int64.MaxValue);
                long targetSequence = R7Json.Integer(content, "recovery_target_sequence", 1, Int64.MaxValue);
                if (!R7Hash.IsLowerSha256(priorIdentity) || !R7Hash.IsLowerSha256(recoverySubject) || !IsGovernedCheckpointReason(reason) ||
                    sequenceBefore != record.Sequence - 1 || targetSequence != record.Sequence || record.SubjectId != recoverySubject ||
                    R7Json.String(content, "ledger_root_before", 64, 64) != R7Json.String(record.Payload, "prior_entry_hash", 64, 64)) throw new InvalidDataException("CHECKPOINT_RECOVERY_INTENT_BINDING_INVALID:" + record.Sequence.ToString(CultureInfo.InvariantCulture));

                object[] pending = R7Json.Array(content, "pending_checkpoint_artifacts");
                List<string> pendingTokens = new List<string>();
                HashSet<string> pendingNames = new HashSet<string>(StringComparer.Ordinal);
                foreach (object rawPending in pending)
                {
                    SortedDictionary<string, object> artifact = RequireObject(rawPending);
                    R7Json.ExactKeys(artifact, "identity", "name");
                    string identity = R7Json.String(artifact, "identity", 64, 64);
                    string name = R7Json.String(artifact, "name", 1, 256);
                    const string prefix = "checkpoint.json.new.";
                    if (!R7Hash.IsLowerSha256(identity) || !name.StartsWith(prefix, StringComparison.Ordinal) || name.Length != prefix.Length + 32 || !IsLowerHex(name.Substring(prefix.Length)) || !pendingNames.Add(name)) throw new InvalidDataException("CHECKPOINT_PENDING_ARTIFACT_INVALID");
                    string preserved = Path.Combine(recoveryRoot, "checkpoint.pending." + identity + "." + name.Substring(prefix.Length) + ".preserved");
                    if (!expectedArtifacts.Add(preserved)) throw new InvalidDataException("CHECKPOINT_PRESERVED_ARTIFACT_DUPLICATE");
                    using (R7VerifiedFile file = R7SafeFile.Open(preserved, preserved, recoveryRoot, identity, expectedFileOwnerSid, null, expectedVolumeIdentity)) { }
                    pendingTokens.Add(name + "|" + identity);
                }
                pendingTokens.Sort(StringComparer.Ordinal);
                string orphanIdentity = R7Hash.Bytes(new UTF8Encoding(false, true).GetBytes(String.Join("\n", pendingTokens.ToArray())));
                string orphanMarker = "ORPHAN_CHECKPOINT_TEMP_" + orphanIdentity;
                if ((pending.Length == 0 && reason.IndexOf("ORPHAN_CHECKPOINT_TEMP_", StringComparison.Ordinal) >= 0) ||
                    (pending.Length != 0 && Array.IndexOf(reason.Split(new string[] { "__AND__" }, StringSplitOptions.None), orphanMarker) < 0)) throw new InvalidDataException("CHECKPOINT_PENDING_REASON_MISMATCH");

                if (priorIdentity == R7Fixed.ZeroHash)
                {
                    if (reason.Split(new string[] { "__AND__" }, StringSplitOptions.None)[0] != "CHECKPOINT_MISSING") throw new InvalidDataException("CHECKPOINT_MISSING_IDENTITY_MISMATCH");
                }
                else
                {
                    string preserved = Path.Combine(recoveryRoot, "checkpoint." + priorIdentity + ".preserved");
                    if (!expectedArtifacts.Add(preserved)) throw new InvalidDataException("CHECKPOINT_PRESERVED_ARTIFACT_DUPLICATE");
                    byte[] preservedBytes;
                    using (R7VerifiedFile file = R7SafeFile.Open(preserved, preserved, recoveryRoot, priorIdentity, expectedFileOwnerSid, null, expectedVolumeIdentity)) preservedBytes = file.Bytes;
                    bool signedPrefix = false;
                    long preservedSequence = 0;
                    try
                    {
                        SortedDictionary<string, object> checkpoint = R7Crypto.VerifyEnvelope(preservedBytes, publicKeyIdentity, verifier);
                        R7Json.ExactKeys(checkpoint, "issue_time", "ledger_id", "public_key_identity", "root_hash", "schema_version", "sequence", "service_sid");
                        preservedSequence = R7Json.Integer(checkpoint, "sequence", 1, sequenceBefore);
                        R7LedgerRecord prefixRecord = ledger.FindSequence(preservedSequence);
                        signedPrefix = prefixRecord != null && R7Json.String(checkpoint, "ledger_id", 64, 64) == ledgerId && R7Json.String(checkpoint, "public_key_identity", 64, 64) == publicKeyIdentity &&
                            R7Json.String(checkpoint, "service_sid", 1, 256) == expectedFileOwnerSid && R7Json.String(checkpoint, "root_hash", 64, 64) == prefixRecord.EntryHash;
                    }
                    catch (Exception) { signedPrefix = false; }
                    string primaryReason = reason.Split(new string[] { "__AND__" }, StringSplitOptions.None)[0];
                    if (primaryReason.StartsWith("STALE_VALID_CHECKPOINT_AT_", StringComparison.Ordinal))
                    {
                        long claimedSequence;
                        if (!Int64.TryParse(primaryReason.Substring("STALE_VALID_CHECKPOINT_AT_".Length), NumberStyles.None, CultureInfo.InvariantCulture, out claimedSequence) || !signedPrefix || claimedSequence != preservedSequence || claimedSequence >= sequenceBefore) throw new InvalidDataException("STALE_CHECKPOINT_RECOVERY_PROOF_INVALID");
                    }
                    else if ((primaryReason == "CHECKPOINT_MISSING" || primaryReason.StartsWith("ORPHAN_CHECKPOINT_TEMP_", StringComparison.Ordinal)) && !signedPrefix) throw new InvalidDataException("CHECKPOINT_RECOVERY_SIGNED_PREFIX_INVALID");
                }

                string computedSubject;
                if (terminalFormat)
                {
                    computedSubject = R7Hash.Bytes(new UTF8Encoding(false, true).GetBytes("R7R_CHECKPOINT_RECOVERY|" + priorIdentity + "|" + reason + "|" + String.Join("\n", pendingTokens.ToArray())));
                }
                else
                {
                    computedSubject = R7Hash.Bytes(R7Json.Encode(R7Json.Object("checkpoint_identity_before", priorIdentity, "pending_checkpoint_artifacts", pending, "reason", reason)));
                }
                if (computedSubject != recoverySubject) throw new InvalidDataException("CHECKPOINT_RECOVERY_SUBJECT_INVALID");
            }

            using (R7VerifiedDirectory held = R7SafeFile.HoldDirectory(recoveryRoot, recoveryRoot, R7Fixed.SystemSid, null, expectedVolumeIdentity))
            {
                if (Directory.GetDirectories(recoveryRoot, "*", SearchOption.TopDirectoryOnly).Length != 0) throw new InvalidDataException("CHECKPOINT_RECOVERY_DIRECTORY_ENTRY_REJECTED");
                string[] files = Directory.GetFiles(recoveryRoot, "*", SearchOption.TopDirectoryOnly);
                Array.Sort(files, StringComparer.Ordinal);
                foreach (string file in files) if (!expectedArtifacts.Contains(Path.GetFullPath(file))) throw new InvalidDataException("UNREFERENCED_CHECKPOINT_RECOVERY_ARTIFACT:" + file);
                if (files.Length != expectedArtifacts.Count) throw new InvalidDataException("CHECKPOINT_RECOVERY_ARTIFACT_MISSING");
            }
            return R7Json.Object(
                "checkpoint_identity", ledger.CheckpointIdentity,
                "checkpoint_recovery_required", false,
                "intent_count", (long)records.Length,
                "preserved_artifact_count", (long)expectedArtifacts.Count,
                "recovery_operation", recoveryOperation,
                "status", "PASS");
        }

        private static bool IsGovernedCheckpointReason(string reason)
        {
            string[] parts = reason.Split(new string[] { "__AND__" }, StringSplitOptions.None);
            HashSet<string> seen = new HashSet<string>(StringComparer.Ordinal);
            foreach (string part in parts)
            {
                if (!seen.Add(part)) return false;
                bool valid = part == "CHECKPOINT_MISSING" || part == "CHECKPOINT_NOT_A_VALID_CHAIN_PREFIX" ||
                    part.StartsWith("STALE_VALID_CHECKPOINT_AT_", StringComparison.Ordinal) || part.StartsWith("CHECKPOINT_INVALID_", StringComparison.Ordinal) ||
                    part.StartsWith("CHECKPOINT_ADVANCEMENT_FAILED_", StringComparison.Ordinal) || part.StartsWith("ORPHAN_CHECKPOINT_TEMP_", StringComparison.Ordinal);
                if (!valid) return false;
                if (part.StartsWith("ORPHAN_CHECKPOINT_TEMP_", StringComparison.Ordinal) && (part.Length != "ORPHAN_CHECKPOINT_TEMP_".Length + 64 || !IsLowerHex(part.Substring("ORPHAN_CHECKPOINT_TEMP_".Length)))) return false;
            }
            return parts.Length != 0;
        }

        private static Dictionary<string, R7TransactionSnapshot> ResolveTransactionStates(R7VersionedLedger ledger, R7ObjectStore objects, string expectedVolumeIdentity)
        {
            Dictionary<string, R7TransactionSnapshot> result = new Dictionary<string, R7TransactionSnapshot>(StringComparer.Ordinal);
            Dictionary<string, string> receiptOwners = new Dictionary<string, string>(StringComparer.Ordinal);
            Dictionary<string, R7TransactionSnapshot> transactions = new Dictionary<string, R7TransactionSnapshot>(StringComparer.Ordinal);
            Dictionary<string, string> terminalClassifications = new Dictionary<string, string>(StringComparer.Ordinal);
            foreach (R7LedgerRecord record in ledger.Records)
            {
                if (!R7TransactionManager.IsTransactionLedgerOperation(record.Operation)) continue;
                if (!R7Hash.IsLowerSha256(record.ContentAddress)) throw new InvalidDataException("PUBLIC_TRANSACTION_CONTENT_IDENTITY_INVALID");
                SortedDictionary<string, object> state = objects.Get(record.ContentAddress);
                R7Json.ExactKeys(state, "classification", "evidence_identity", "operation", "prior_state", "receipt_identity", "request_identity", "request_sha256", "response_identity", "schema_version", "state", "transition_time");
                string requestIdentity = R7Json.String(state, "request_identity", 36, 36);
                Guid parsedRequestIdentity;
                if (!Guid.TryParseExact(requestIdentity, "D", out parsedRequestIdentity) || parsedRequestIdentity.ToString("D") != requestIdentity) throw new InvalidDataException("PUBLIC_TRANSACTION_REQUEST_IDENTITY_INVALID");
                string requestSha = R7Json.String(state, "request_sha256", 64, 64);
                string operation = R7Json.String(state, "operation", 1, 256);
                string next = R7Json.String(state, "state", 1, 128);
                string prior = R7Json.String(state, "prior_state", 0, 128);
                string receipt = R7Json.String(state, "receipt_identity", 0, 64);
                string response = R7Json.String(state, "response_identity", 0, 64);
                string evidence = R7Json.String(state, "evidence_identity", 0, 64);
                string classification = R7Json.String(state, "classification", 1, 4096);
                DateTimeOffset transitionTime;
                if (!DateTimeOffset.TryParseExact(R7Json.String(state, "transition_time", 28, 28), "yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out transitionTime) ||
                    !R7Hash.IsLowerSha256(requestSha) || record.SubjectId != requestIdentity || record.Operation != "R7R_" + next || record.SchemaVersion != R7Fixed.InterfaceVersion || R7Json.String(state, "schema_version", 1, 128) != R7Fixed.InterfaceVersion) throw new InvalidDataException("PUBLIC_TRANSACTION_LEDGER_BINDING_INVALID");
                if ((receipt.Length != 0 && !R7Hash.IsLowerSha256(receipt)) || (response.Length != 0 && !R7Hash.IsLowerSha256(response)) || (evidence.Length != 0 && !R7Hash.IsLowerSha256(evidence))) throw new InvalidDataException("PUBLIC_TRANSACTION_DURABLE_IDENTITY_INVALID");
                if ((next == "REQUEST_RECEIVED" || next == "RESERVED") && (receipt.Length != 0 || response.Length != 0 || evidence.Length != 0)) throw new InvalidDataException("PUBLIC_TRANSACTION_PREVALIDATION_IDENTITY_PRESENT");
                if (next == "EVIDENCE_VALIDATED" && (receipt.Length != 0 || response.Length != 0 || !R7Hash.IsLowerSha256(evidence))) throw new InvalidDataException("PUBLIC_TRANSACTION_VALIDATED_IDENTITY_SET_INVALID");
                if ((next == "RECEIPT_PREPARED" || next == "COMMITTED" || next == "RESPONSE_AVAILABLE") && (!R7Hash.IsLowerSha256(receipt) || !R7Hash.IsLowerSha256(response) || !R7Hash.IsLowerSha256(evidence))) throw new InvalidDataException("PUBLIC_TRANSACTION_COMMIT_IDENTITY_SET_INVALID");
                if (next == "ABORTED")
                {
                    bool validAbortIdentities =
                        ((prior == "REQUEST_RECEIVED" || prior == "RESERVED") && receipt.Length == 0 && response.Length == 0 && evidence.Length == 0) ||
                        (prior == "EVIDENCE_VALIDATED" && receipt.Length == 0 && response.Length == 0 && R7Hash.IsLowerSha256(evidence)) ||
                        (prior == "RECEIPT_PREPARED" && R7Hash.IsLowerSha256(receipt) && R7Hash.IsLowerSha256(response) && R7Hash.IsLowerSha256(evidence));
                    if (!validAbortIdentities) throw new InvalidDataException("PUBLIC_TRANSACTION_ABORT_IDENTITY_SET_INVALID");
                    if (classification != "TRANSACTION_PRECOMMIT_FAILURE" && classification != "RETRY_RECOVERED_INCOMPLETE_RESERVATION" && classification != "STARTUP_RECOVERY_ABORT") throw new InvalidDataException("PUBLIC_TRANSACTION_ABORT_CLASSIFICATION_INVALID");
                }
                if (next == "SUPERSEDED" && classification != "INCOMPLETE_ARTIFACTS_SUPERSEDED") throw new InvalidDataException("PUBLIC_TRANSACTION_SUPERSESSION_CLASSIFICATION_INVALID");
                R7TransactionSnapshot snapshot;
                if (!transactions.TryGetValue(requestIdentity, out snapshot))
                {
                    snapshot = new R7TransactionSnapshot { RequestIdentity = requestIdentity, RequestSha256 = requestSha, Operation = operation, State = "NONE", ReceiptIdentity = String.Empty, ResponseIdentity = String.Empty, EvidenceIdentity = String.Empty, TerminalClassification = String.Empty };
                    transactions.Add(requestIdentity, snapshot);
                }
                R7TransactionManager.ValidateTransition(snapshot.State, next);
                if (snapshot.State != prior || snapshot.RequestSha256 != requestSha || snapshot.Operation != operation ||
                    (snapshot.ReceiptIdentity.Length != 0 && snapshot.ReceiptIdentity != receipt) ||
                    (snapshot.ResponseIdentity.Length != 0 && snapshot.ResponseIdentity != response) ||
                    (snapshot.EvidenceIdentity.Length != 0 && snapshot.EvidenceIdentity != evidence)) throw new InvalidDataException("PUBLIC_TRANSACTION_CHAIN_MISMATCH");
                string terminalClassification;
                if (next == "EVIDENCE_VALIDATED")
                {
                    terminalClassifications[requestIdentity] = classification;
                    snapshot.TerminalClassification = classification;
                }
                else if (next == "RECEIPT_PREPARED" || next == "COMMITTED")
                {
                    if (!terminalClassifications.TryGetValue(requestIdentity, out terminalClassification) || terminalClassification != classification) throw new InvalidDataException("PUBLIC_TRANSACTION_CLASSIFICATION_CHANGED");
                }
                else if (next == "RESPONSE_AVAILABLE")
                {
                    if (!terminalClassifications.TryGetValue(requestIdentity, out terminalClassification) || (classification != terminalClassification && classification != "RECOVERED_RESPONSE")) throw new InvalidDataException("PUBLIC_TRANSACTION_RESPONSE_CLASSIFICATION_INVALID");
                }
                snapshot.State = next;
                snapshot.ReceiptIdentity = receipt;
                snapshot.ResponseIdentity = response;
                snapshot.EvidenceIdentity = evidence;
                snapshot.LastSequence = record.Sequence;
                if (receipt.Length != 0)
                {
                    string owner;
                    if (receiptOwners.TryGetValue(receipt, out owner) && owner != requestIdentity) throw new InvalidDataException("PUBLIC_TRANSACTION_RECEIPT_REUSED");
                    receiptOwners[receipt] = requestIdentity;
                }
            }
            foreach (R7TransactionSnapshot snapshot in transactions.Values)
            {
                if (snapshot.ReceiptIdentity.Length != 0) result.Add(snapshot.ReceiptIdentity, snapshot);
                if (snapshot.State != "COMMITTED" && snapshot.State != "RESPONSE_AVAILABLE") continue;
                ValidateCommittedTransactionArtifacts(snapshot, expectedVolumeIdentity);
            }
            return result;
        }

        private static void ValidateCommittedTransactionArtifacts(R7TransactionSnapshot snapshot, string expectedVolumeIdentity)
        {
            string receiptPath = Path.Combine(R7Fixed.ReceiptRoot, snapshot.ReceiptIdentity + ".receipt.json");
            string responsePath = Path.Combine(R7Fixed.ResponseRoot, snapshot.ResponseIdentity + ".frame");
            using (R7VerifiedFile receipt = R7SafeFile.Open(receiptPath, receiptPath, R7Fixed.ReceiptRoot, snapshot.ReceiptIdentity, R7Fixed.TerminalSid, null, expectedVolumeIdentity)) { }
            using (R7VerifiedFile response = R7SafeFile.Open(responsePath, responsePath, R7Fixed.ResponseRoot, snapshot.ResponseIdentity, R7Fixed.TerminalSid, null, expectedVolumeIdentity))
            {
                SortedDictionary<string, object> message = R7Framing.Decode(response.Bytes);
                if (R7Json.String(message, "status", 1, 64) != "COMPLETE" ||
                    R7Json.String(message, "protocol_version", 1, 64) != R7Fixed.ProtocolVersion ||
                    R7Json.String(message, "interface_version", 1, 128) != R7Fixed.InterfaceVersion ||
                    R7Json.String(message, "receipt_identity", 64, 64) != snapshot.ReceiptIdentity ||
                    R7Json.String(message, "request_identity", 36, 36) != snapshot.RequestIdentity) throw new InvalidDataException("PUBLIC_COMMITTED_RESPONSE_BINDING_INVALID");
                if (snapshot.Operation == "SUBMIT_TERMINAL_PROPOSAL")
                {
                    R7Json.ExactKeys(message, "interface_version", "proposal_identity", "protocol_version", "receipt_identity", "request_identity", "result_code", "status");
                    if (R7Json.String(message, "result_code", 1, 256) != "REQUEST_RECEIVED" || !R7Hash.IsLowerSha256(R7Json.String(message, "proposal_identity", 64, 64))) throw new InvalidDataException("PUBLIC_PROPOSAL_RESPONSE_INVALID");
                }
                else if (snapshot.Operation == "SUBMIT_RUN_GRAPH")
                {
                    R7Json.ExactKeys(message, "case_count", "complete_case_registry", "evidence_identity", "interface_version", "protocol_version", "provenance_identity", "receipt_identity", "request_identity", "result_code", "run_kind", "status");
                    string resultCode = R7Json.String(message, "result_code", 1, 256);
                    if (resultCode != "TERMINAL_RECEIPT_COMMITTED" && resultCode != "CANDIDATE_GRAPH_RECORDED" && resultCode != "FRESH_BOOTSTRAP_RECORDED") throw new InvalidDataException("PUBLIC_RUN_RESPONSE_CODE_INVALID");
                    if (R7Json.String(message, "evidence_identity", 64, 64) != snapshot.EvidenceIdentity || !R7Hash.IsLowerSha256(R7Json.String(message, "provenance_identity", 64, 64))) throw new InvalidDataException("PUBLIC_RUN_RESPONSE_EVIDENCE_INVALID");
                }
                else if (snapshot.Operation == "SUBMIT_RECONCILIATION")
                {
                    R7Json.ExactKeys(message, "candidate_receipt_identity", "fresh_receipt_identity", "full_case_registry", "interface_version", "protocol_version", "receipt_identity", "request_identity", "result_code", "status");
                    if (R7Json.String(message, "result_code", 1, 256) != "RECONCILIATION_COMMITTED" ||
                        !R7Hash.IsLowerSha256(R7Json.String(message, "candidate_receipt_identity", 64, 64)) ||
                        !R7Hash.IsLowerSha256(R7Json.String(message, "fresh_receipt_identity", 64, 64))) throw new InvalidDataException("PUBLIC_RECONCILIATION_RESPONSE_INVALID");
                }
                else throw new InvalidDataException("PUBLIC_COMMITTED_OPERATION_UNKNOWN");
            }
        }

        private static SortedDictionary<string, object> VerifyResponseArtifacts(Dictionary<string, R7TransactionSnapshot> receiptTransactions, string expectedVolumeIdentity)
        {
            R7SafeFile.MeasureDirectory(R7Fixed.ResponseRoot, R7Fixed.ResponseRoot, R7Fixed.SystemSid, null, expectedVolumeIdentity);
            if (Directory.GetDirectories(R7Fixed.ResponseRoot, "*", SearchOption.TopDirectoryOnly).Length != 0) throw new InvalidDataException("V4_RESPONSE_DIRECTORY_ENTRY_REJECTED");
            Dictionary<string, R7TransactionSnapshot> byResponse = new Dictionary<string, R7TransactionSnapshot>(StringComparer.Ordinal);
            foreach (R7TransactionSnapshot snapshot in receiptTransactions.Values)
            {
                if (!R7Hash.IsLowerSha256(snapshot.ResponseIdentity)) continue;
                if (byResponse.ContainsKey(snapshot.ResponseIdentity)) throw new InvalidDataException("V4_RESPONSE_TRANSACTION_IDENTITY_REUSED");
                byResponse.Add(snapshot.ResponseIdentity, snapshot);
            }
            HashSet<string> observed = new HashSet<string>(StringComparer.Ordinal);
            long committed = 0;
            long abortedOrSuperseded = 0;
            long orphan = 0;
            string[] paths = Directory.GetFiles(R7Fixed.ResponseRoot, "*", SearchOption.TopDirectoryOnly);
            Array.Sort(paths, StringComparer.Ordinal);
            foreach (string path in paths)
            {
                string name = Path.GetFileName(path);
                const string suffix = ".frame";
                if (name.Length != 64 + suffix.Length || !name.EndsWith(suffix, StringComparison.Ordinal)) throw new InvalidDataException("V4_RESPONSE_FILENAME_INVALID");
                string identity = name.Substring(0, 64);
                if (!R7Hash.IsLowerSha256(identity) || !observed.Add(identity)) throw new InvalidDataException("V4_RESPONSE_IDENTITY_INVALID");
                SortedDictionary<string, object> message;
                using (R7VerifiedFile file = R7SafeFile.Open(path, path, R7Fixed.ResponseRoot, identity, R7Fixed.TerminalSid, null, expectedVolumeIdentity)) message = R7Framing.Decode(file.Bytes);
                R7TransactionSnapshot snapshot;
                if (!byResponse.TryGetValue(identity, out snapshot)) { orphan++; continue; }
                if (R7Json.String(message, "request_identity", 36, 36) != snapshot.RequestIdentity) throw new InvalidDataException("V4_RESPONSE_REQUEST_BINDING_INVALID");
                if (snapshot.State == "COMMITTED" || snapshot.State == "RESPONSE_AVAILABLE") committed++;
                else if (snapshot.State == "ABORTED" || snapshot.State == "SUPERSEDED") abortedOrSuperseded++;
                else orphan++;
            }
            foreach (KeyValuePair<string, R7TransactionSnapshot> pair in byResponse)
            {
                if ((pair.Value.State == "COMMITTED" || pair.Value.State == "RESPONSE_AVAILABLE") && !observed.Contains(pair.Key)) throw new InvalidDataException("V4_COMMITTED_RESPONSE_ARTIFACT_MISSING");
            }
            return R7Json.Object(
                "aborted_or_superseded_response_count", abortedOrSuperseded,
                "committed_response_count", committed,
                "orphan_nonauthority_response_count", orphan,
                "response_artifact_count", (long)paths.Length,
                "status", "PASS");
        }

        private static SortedDictionary<string, object> VerifyUpgradeInteractions(R7VersionedLedger ledger, R7ObjectStore objects, UpgradePublicPolicy policy)
        {
            long complete = 0;
            long rejected = 0;
            long readOnly = 0;
            long mutationAttempts = 0;
            foreach (R7LedgerRecord record in ledger.Records)
            {
                if (!String.Equals(record.Operation, "UPGRADE_INTERFACE_INTERACTION", StringComparison.Ordinal)) continue;
                SortedDictionary<string, object> interaction = objects.Get(record.ContentAddress);
                R7Json.ExactKeys(interaction,
                    "artifact_type", "authority_ledger_root_after_dispatch", "authority_ledger_root_before", "authority_ledger_sequence_after_dispatch",
                    "authority_ledger_sequence_before", "caller", "operation", "request", "request_frame", "request_frame_sha256", "request_identity",
                    "response", "response_frame", "response_frame_sha256", "schema_version");
                string requestIdentity = R7Json.String(interaction, "request_identity", 36, 36);
                if (!String.Equals(R7Json.String(interaction, "artifact_type", 1, 256), "R7_UPGRADE_AUTHORITY_SERVER_CAPTURED_INTERACTION", StringComparison.Ordinal) ||
                    !String.Equals(record.SubjectId, requestIdentity, StringComparison.Ordinal) || !String.Equals(record.RequestNonce, requestIdentity, StringComparison.Ordinal)) throw new InvalidDataException("UPGRADE_INTERACTION_LEDGER_BINDING_INVALID");
                byte[] requestFrame = Convert.FromBase64String(R7Json.String(interaction, "request_frame", 1, R7Fixed.MaximumEncodedFrameChars));
                byte[] responseFrame = Convert.FromBase64String(R7Json.String(interaction, "response_frame", 1, R7Fixed.MaximumEncodedFrameChars));
                SortedDictionary<string, object> decodedRequest = R7Framing.Decode(requestFrame);
                SortedDictionary<string, object> decodedResponse = R7Framing.Decode(responseFrame);
                if (!R7Hash.FixedTimeEquals(R7Hash.Bytes(requestFrame), R7Json.String(interaction, "request_frame_sha256", 64, 64)) ||
                    !R7Hash.FixedTimeEquals(R7Hash.Bytes(responseFrame), R7Json.String(interaction, "response_frame_sha256", 64, 64)) ||
                    !R7Hash.FixedTimeEquals(R7Hash.Bytes(R7Json.Encode(decodedRequest)), R7Hash.Bytes(R7Json.Encode(R7Json.Child(interaction, "request")))) ||
                    !R7Hash.FixedTimeEquals(R7Hash.Bytes(R7Json.Encode(decodedResponse)), R7Hash.Bytes(R7Json.Encode(R7Json.Child(interaction, "response")))) ||
                    !String.Equals(R7Json.String(decodedRequest, "request_identity", 36, 36), requestIdentity, StringComparison.Ordinal)) throw new InvalidDataException("UPGRADE_INTERACTION_FRAME_BINDING_INVALID");
                string operation = R7Json.String(interaction, "operation", 1, 128);
                if (!String.Equals(operation, R7Json.String(decodedRequest, "operation", 1, 128), StringComparison.Ordinal)) throw new InvalidDataException("UPGRADE_INTERACTION_OPERATION_MISMATCH");
                SortedDictionary<string, object> caller = R7Json.Child(interaction, "caller");
                string callerSid = R7Json.String(caller, "user_sid", 1, 256);
                if (operation == "AUTHORIZE_TERMINAL_UPGRADE")
                {
                    mutationAttempts++;
                    if (callerSid == R7Fixed.OperatorSid || callerSid == R7Fixed.SystemSid)
                    {
                        if (!R7Hash.FixedTimeEquals(R7Json.String(caller, "process_sha256", 64, 64), policy.UpgradeClientSha256)) throw new InvalidDataException("UPGRADE_OPERATOR_CLIENT_SUBSTITUTED");
                    }
                    else if (callerSid != R7Fixed.TerminalSid) throw new InvalidDataException("UPGRADE_AUTHORIZATION_CALLER_CLASS_INVALID");
                }
                long before = R7Json.Integer(interaction, "authority_ledger_sequence_before", 0, Int64.MaxValue);
                long after = R7Json.Integer(interaction, "authority_ledger_sequence_after_dispatch", 0, Int64.MaxValue);
                string status = R7Json.String(decodedResponse, "status", 1, 64);
                if (status == "REJECTED")
                {
                    rejected++;
                    if (before != after || R7Json.String(interaction, "authority_ledger_root_before", 64, 64) != R7Json.String(interaction, "authority_ledger_root_after_dispatch", 64, 64)) throw new InvalidDataException("REJECTED_UPGRADE_INTERACTION_CHANGED_AUTHORITY");
                }
                else
                {
                    complete++;
                    if (operation == "GET_UPGRADE_STATUS") readOnly++;
                }
            }
            return R7Json.Object(
                "complete_interaction_count", complete,
                "interaction_count", complete + rejected,
                "mutation_attempt_count", mutationAttempts,
                "read_only_interaction_count", readOnly,
                "rejected_non_authority_count", rejected,
                "status", "PASS");
        }

        private static void VerifyUpgradeRequestPayload(SortedDictionary<string, object> request, SortedDictionary<string, object> authorization)
        {
            R7Json.ExactKeys(request,
                "build_receipt_sha256", "components", "dependency_manifest_sha256", "host_binding", "installer_identity", "new_interface_version",
                "old_interface_version", "old_policy_sha256", "old_service_binary_sha256", "rollback_constraints", "source_commit", "source_tree",
                "staging_root", "transition_nonce");
            foreach (string field in new string[] { "build_receipt_sha256", "dependency_manifest_sha256", "new_interface_version", "old_interface_version", "old_policy_sha256", "old_service_binary_sha256", "rollback_constraints", "source_commit", "source_tree", "staging_root", "transition_nonce" })
            {
                if (R7Json.String(request, field, 1, 4096) != R7Json.String(authorization, field, 1, 4096)) throw new InvalidDataException("UPGRADE_REQUEST_AUTHORIZATION_FIELD_MISMATCH:" + field);
            }
            if (R7Hash.Bytes(R7Json.Encode(R7Json.Child(request, "host_binding"))) != R7Hash.Bytes(R7Json.Encode(R7Json.Child(authorization, "host_binding"))) ||
                R7Hash.Bytes(R7Json.Encode(R7Json.Child(request, "installer_identity"))) != R7Hash.Bytes(R7Json.Encode(R7Json.Child(authorization, "installer_identity")))) throw new InvalidDataException("UPGRADE_REQUEST_AUTHORIZATION_NESTED_MISMATCH");
            Dictionary<string, SortedDictionary<string, object>> measuredByRole = new Dictionary<string, SortedDictionary<string, object>>(StringComparer.Ordinal);
            foreach (object raw in R7Json.Array(authorization, "components"))
            {
                SortedDictionary<string, object> measured = RequireObject(raw);
                R7Json.ExactKeys(measured, "file_identity", "final_path", "final_path_preinstall_state", "role", "sha256", "size", "staging_relative_path");
                string role = R7Json.String(measured, "role", 1, 256);
                if (R7Json.String(measured, "final_path_preinstall_state", 1, 64) != "ABSENT" || R7Json.Integer(measured, "size", 0, Int64.MaxValue) < 0 || measuredByRole.ContainsKey(role)) throw new InvalidDataException("UPGRADE_MEASURED_COMPONENT_INVALID");
                measuredByRole.Add(role, measured);
            }
            object[] requestedComponents = R7Json.Array(request, "components");
            if (requestedComponents.Length != measuredByRole.Count) throw new InvalidDataException("UPGRADE_REQUEST_COMPONENT_COUNT_INVALID");
            HashSet<string> seen = new HashSet<string>(StringComparer.Ordinal);
            foreach (object raw in requestedComponents)
            {
                SortedDictionary<string, object> requested = RequireObject(raw);
                R7Json.ExactKeys(requested, "final_path", "role", "sha256", "staging_relative_path");
                string role = R7Json.String(requested, "role", 1, 256);
                SortedDictionary<string, object> measured;
                if (!seen.Add(role) || !measuredByRole.TryGetValue(role, out measured) ||
                    R7Json.String(requested, "final_path", 3, 4096) != R7Json.String(measured, "final_path", 3, 4096) ||
                    R7Json.String(requested, "sha256", 64, 64) != R7Json.String(measured, "sha256", 64, 64) ||
                    R7Json.String(requested, "staging_relative_path", 1, 2048) != R7Json.String(measured, "staging_relative_path", 1, 2048)) throw new InvalidDataException("UPGRADE_REQUEST_COMPONENT_MEASUREMENT_MISMATCH");
            }
        }

        private static void VerifyUpgradeMutationInteraction(R7VersionedLedger ledger, R7ObjectStore objects, SortedDictionary<string, object> mutationRecord, string expectedOperation)
        {
            string requestIdentity = R7Json.String(mutationRecord, "request_identity", 36, 36);
            string requestFrameSha256 = R7Json.String(mutationRecord, "request_frame_sha256", 64, 64);
            string requestPayloadIdentity = R7Json.String(mutationRecord, "request_payload_identity", 64, 64);
            R7LedgerRecord[] interactions = ledger.Find("UPGRADE_INTERFACE_INTERACTION", requestIdentity);
            if (interactions.Length != 1) throw new InvalidDataException("UPGRADE_MUTATION_INTERACTION_MISSING_OR_DUPLICATE");
            SortedDictionary<string, object> interaction = objects.Get(interactions[0].ContentAddress);
            if (R7Json.String(interaction, "operation", 1, 128) != expectedOperation || R7Json.String(interaction, "request_identity", 36, 36) != requestIdentity || R7Json.String(interaction, "request_frame_sha256", 64, 64) != requestFrameSha256) throw new InvalidDataException("UPGRADE_MUTATION_INTERACTION_BINDING_INVALID");
            SortedDictionary<string, object> request = R7Json.Child(interaction, "request");
            if (R7Json.String(request, "operation", 1, 128) != expectedOperation || R7Json.String(request, "request_identity", 36, 36) != requestIdentity || R7Hash.Bytes(R7Json.Encode(R7Json.Child(request, "payload"))) != requestPayloadIdentity) throw new InvalidDataException("UPGRADE_MUTATION_INTERACTION_REQUEST_INVALID");
            if (R7Json.String(R7Json.Child(interaction, "response"), "status", 1, 64) != "COMPLETE") throw new InvalidDataException("UPGRADE_MUTATION_INTERACTION_NOT_COMPLETE");
        }

        private static Dictionary<string, R7UpgradeVersionBinding> LoadUpgradeVersionBindings(R7VersionedLedger ledger, R7ObjectStore objects, RSA verifier, UpgradePublicPolicy policy, string expectedVolumeIdentity, string activeAuthorizationIdentity)
        {
            Dictionary<string, R7UpgradeVersionBinding> result = new Dictionary<string, R7UpgradeVersionBinding>(StringComparer.Ordinal);
            HashSet<string> resolvedAuthorizationNonces = new HashSet<string>(StringComparer.Ordinal);
            HashSet<string> activationFileNonces = new HashSet<string>(StringComparer.Ordinal);
            HashSet<string> consumedActivationNonces = new HashSet<string>(StringComparer.Ordinal);
            R7SafeFile.MeasureDirectory(R7Fixed.UpgradeAuthorizationRoot, R7Fixed.UpgradeAuthorizationRoot, R7Fixed.SystemSid, null, expectedVolumeIdentity);
            R7SafeFile.MeasureDirectory(R7Fixed.UpgradeActivationRoot, R7Fixed.UpgradeActivationRoot, R7Fixed.SystemSid, null, expectedVolumeIdentity);
            if (Directory.GetDirectories(R7Fixed.UpgradeAuthorizationRoot, "*", SearchOption.TopDirectoryOnly).Length != 0 || Directory.GetDirectories(R7Fixed.UpgradeActivationRoot, "*", SearchOption.TopDirectoryOnly).Length != 0) throw new InvalidDataException("UPGRADE_RECORD_DIRECTORY_ENTRY_REJECTED");
            foreach (string activationFile in Directory.GetFiles(R7Fixed.UpgradeActivationRoot, "*", SearchOption.TopDirectoryOnly))
            {
                string activationName = Path.GetFileName(activationFile);
                const string activationSuffix = ".activation.json";
                if (activationName.Length != 36 + activationSuffix.Length || !activationName.EndsWith(activationSuffix, StringComparison.Ordinal)) throw new InvalidDataException("UPGRADE_ACTIVATION_FILENAME_INVALID");
                string activationNonce = activationName.Substring(0, 36);
                Guid activationGuid;
                if (!Guid.TryParseExact(activationNonce, "D", out activationGuid) || activationGuid.ToString("D") != activationNonce || !activationFileNonces.Add(activationNonce)) throw new InvalidDataException("UPGRADE_ACTIVATION_NONCE_INVALID");
            }
            string[] paths = Directory.GetFiles(R7Fixed.UpgradeAuthorizationRoot, "*", SearchOption.TopDirectoryOnly);
            Array.Sort(paths, StringComparer.Ordinal);
            foreach (string path in paths)
            {
                string fileName = Path.GetFileName(path);
                string suffix = ".upgrade.json";
                if (fileName.Length != 36 + suffix.Length || !fileName.EndsWith(suffix, StringComparison.Ordinal)) throw new InvalidDataException("UPGRADE_AUTHORIZATION_FILENAME_INVALID");
                string nonce = fileName.Substring(0, fileName.Length - suffix.Length);
                Guid parsedNonce;
                if (!Guid.TryParseExact(nonce, "D", out parsedNonce) || parsedNonce.ToString("D") != nonce) throw new InvalidDataException("UPGRADE_AUTHORIZATION_NONCE_INVALID");
                if (!resolvedAuthorizationNonces.Add(nonce)) throw new InvalidDataException("UPGRADE_AUTHORIZATION_NONCE_DUPLICATE");
                SortedDictionary<string, object> authorization;
                string authorizationIdentity;
                using (R7VerifiedFile file = R7SafeFile.Open(path, path, R7Fixed.UpgradeAuthorizationRoot, null, R7Fixed.UpgradeSid, null, expectedVolumeIdentity))
                {
                    authorizationIdentity = file.Measurement.Sha256;
                    authorization = R7Crypto.VerifyEnvelope(file.Bytes, R7BuildIdentity.UpgradePublicCertificateSha256, verifier);
                }
                R7Json.ExactKeys(authorization, "activation_sequence", "authorization_time", "authority_class", "build_receipt_sha256", "components", "dependency_manifest_sha256", "host_binding", "installer_identity", "new_interface_version", "old_interface_version", "old_policy_sha256", "old_service_binary_sha256", "operation", "request_frame_sha256", "request_identity", "request_payload_identity", "revocation_state", "rollback_constraints", "schema_version", "source_commit", "source_tree", "staging_root", "transition_nonce", "verification_object_identity");
                if (R7Json.String(authorization, "authority_class", 1, 128) != "TERMINAL_UPGRADE_AUTHORIZATION" ||
                    R7Json.String(authorization, "operation", 1, 128) != "AUTHORIZE_TERMINAL_UPGRADE" ||
                    R7Json.String(authorization, "revocation_state", 1, 64) != "ACTIVE" ||
                    R7Json.String(authorization, "transition_nonce", 36, 36) != nonce ||
                    R7Json.String(authorization, "schema_version", 1, 64) != "1.0.0" ||
                    R7Json.String(authorization, "old_service_binary_sha256", 64, 64) != policy.OldBinarySha256 ||
                    R7Json.String(authorization, "old_policy_sha256", 64, 64) != policy.OldPolicySha256 ||
                    R7Json.String(authorization, "old_interface_version", 1, 128) != policy.OldInterfaceVersion ||
                    R7Json.String(authorization, "new_interface_version", 1, 128) != R7Fixed.InterfaceVersion ||
                    R7Json.String(authorization, "dependency_manifest_sha256", 64, 64) != policy.DependencyManifestSha256 ||
                    R7Json.String(authorization, "source_commit", 40, 40) != policy.SourceCommit ||
                    R7Json.String(authorization, "source_tree", 40, 40) != policy.SourceTree ||
                    R7Json.String(authorization, "rollback_constraints", 1, 4096) != "PRESERVE_LEDGER_CONTINUITY;PRESERVE_ALL_HISTORICAL_EVIDENCE;REQUIRE_SIGNED_ROLLBACK_AUTHORIZATION;NO_V1_OR_REJECTED_V3_DOWNGRADE") throw new InvalidDataException("UPGRADE_AUTHORIZATION_SEMANTICS_INVALID");
                SortedDictionary<string, object> authorizationHost = R7Json.Child(authorization, "host_binding");
                R7Json.ExactKeys(authorizationHost, "terminal_ledger_id", "terminal_service_sid", "volume_identity");
                SortedDictionary<string, object> authorizationInstaller = R7Json.Child(authorization, "installer_identity");
                R7Json.ExactKeys(authorizationInstaller, "executable_sha256", "script_sha256");
                DateTimeOffset authorizationIssuedTime;
                Guid authorizationRequestGuid;
                if (R7Json.String(authorizationHost, "terminal_ledger_id", 64, 64) != R7Fixed.LedgerId || R7Json.String(authorizationHost, "terminal_service_sid", 1, 256) != R7Fixed.TerminalSid || R7Json.String(authorizationHost, "volume_identity", 8, 64) != expectedVolumeIdentity ||
                    R7Json.String(authorizationInstaller, "executable_sha256", 64, 64) != policy.UpgradeClientSha256 || R7Json.String(authorizationInstaller, "script_sha256", 64, 64) != policy.InstallerScriptSha256 ||
                    !Guid.TryParseExact(R7Json.String(authorization, "request_identity", 36, 36), "D", out authorizationRequestGuid) || authorizationRequestGuid.ToString("D") != R7Json.String(authorization, "request_identity", 36, 36) ||
                    !DateTimeOffset.TryParseExact(R7Json.String(authorization, "authorization_time", 28, 28), "yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out authorizationIssuedTime)) throw new InvalidDataException("UPGRADE_AUTHORIZATION_HOST_INSTALLER_OR_TIME_INVALID");
                string verificationObjectIdentity = R7Json.String(authorization, "verification_object_identity", 64, 64);
                SortedDictionary<string, object> verificationObject = objects.Get(verificationObjectIdentity);
                R7Json.ExactKeys(verificationObject, "artifact_type", "measured_components", "request_frame", "request_frame_sha256", "request_identity", "request_payload_identity", "schema_version", "transition_nonce");
                byte[] authorizationRequestFrame = Convert.FromBase64String(R7Json.String(verificationObject, "request_frame", 1, R7Fixed.MaximumEncodedFrameChars));
                if (R7Json.String(verificationObject, "artifact_type", 1, 256) != "R7_UPGRADE_AUTHORIZATION_RAW_REQUEST_EVIDENCE" ||
                    R7Json.String(verificationObject, "transition_nonce", 36, 36) != nonce ||
                    R7Json.String(verificationObject, "request_identity", 36, 36) != R7Json.String(authorization, "request_identity", 36, 36) ||
                    R7Json.String(verificationObject, "request_payload_identity", 64, 64) != R7Json.String(authorization, "request_payload_identity", 64, 64) ||
                    R7Json.String(verificationObject, "request_frame_sha256", 64, 64) != R7Json.String(authorization, "request_frame_sha256", 64, 64) ||
                    R7Hash.Bytes(authorizationRequestFrame) != R7Json.String(authorization, "request_frame_sha256", 64, 64)) throw new InvalidDataException("UPGRADE_AUTHORIZATION_RAW_EVIDENCE_INVALID");
                SortedDictionary<string, object> decodedAuthorizationRequest = R7Framing.Decode(authorizationRequestFrame);
                R7Json.ExactKeys(decodedAuthorizationRequest, "interface_version", "operation", "payload", "protocol_version", "request_identity");
                SortedDictionary<string, object> decodedAuthorizationPayload = R7Json.Child(decodedAuthorizationRequest, "payload");
                if (R7Json.String(decodedAuthorizationRequest, "operation", 1, 128) != "AUTHORIZE_TERMINAL_UPGRADE" ||
                    R7Json.String(decodedAuthorizationRequest, "interface_version", 1, 128) != "1.0.0" || R7Json.String(decodedAuthorizationRequest, "protocol_version", 1, 64) != R7Fixed.ProtocolVersion ||
                    R7Json.String(decodedAuthorizationRequest, "request_identity", 36, 36) != R7Json.String(authorization, "request_identity", 36, 36) ||
                    R7Hash.Bytes(R7Json.Encode(decodedAuthorizationPayload)) != R7Json.String(authorization, "request_payload_identity", 64, 64) ||
                    R7Hash.Bytes(R7Json.Encode(R7Json.Array(verificationObject, "measured_components"))) != R7Hash.Bytes(R7Json.Encode(R7Json.Array(authorization, "components")))) throw new InvalidDataException("UPGRADE_AUTHORIZATION_DECODED_REQUEST_INVALID");
                VerifyUpgradeRequestPayload(decodedAuthorizationPayload, authorization);
                R7LedgerRecord[] issued = ledger.Find("UPGRADE_AUTHORIZATION_ISSUED", nonce);
                if (issued.Length != 1 || issued[0].ContentAddress != authorizationIdentity) throw new InvalidDataException("UPGRADE_AUTHORIZATION_LEDGER_MEMBERSHIP_INVALID");
                VerifyUpgradeMutationInteraction(ledger, objects, authorization, "AUTHORIZE_TERMINAL_UPGRADE");
                R7LedgerRecord[] revoked = ledger.Find("UPGRADE_AUTHORIZATION_REVOKED", nonce);
                R7LedgerRecord[] activated = ledger.Find("UPGRADE_ACTIVATED", nonce);
                if (revoked.Length > 1 || activated.Length > 1 || (revoked.Length != 0 && activated.Length != 0)) throw new InvalidDataException("UPGRADE_AUTHORIZATION_TERMINAL_STATE_INVALID");
                if (revoked.Length == 1)
                {
                    SortedDictionary<string, object> revocation = objects.Get(revoked[0].ContentAddress);
                    R7Json.ExactKeys(revocation, "operation", "reason", "request_frame_sha256", "request_identity", "request_payload_identity", "schema_version", "transition_nonce");
                    if (R7Json.String(revocation, "operation", 1, 128) != "REVOKE_AUTHORIZATION" ||
                        R7Json.String(revocation, "transition_nonce", 36, 36) != nonce ||
                        !R7Hash.IsLowerSha256(R7Json.String(revocation, "request_frame_sha256", 64, 64)) ||
                        !R7Hash.IsLowerSha256(R7Json.String(revocation, "request_payload_identity", 64, 64))) throw new InvalidDataException("UPGRADE_REVOCATION_RECORD_INVALID");
                    VerifyUpgradeMutationInteraction(ledger, objects, revocation, "REVOKE_AUTHORIZATION");
                    continue;
                }
                if (activated.Length == 0) continue;
                if (!activationFileNonces.Contains(nonce) || !consumedActivationNonces.Add(nonce)) throw new InvalidDataException("UPGRADE_ACTIVATION_FILE_MISSING_OR_DUPLICATE");

                string activationPath = Path.Combine(R7Fixed.UpgradeActivationRoot, nonce + ".activation.json");
                SortedDictionary<string, object> activation;
                string activationIdentity;
                using (R7VerifiedFile file = R7SafeFile.Open(activationPath, activationPath, R7Fixed.UpgradeActivationRoot, activated[0].ContentAddress, R7Fixed.UpgradeSid, null, expectedVolumeIdentity))
                {
                    activationIdentity = file.Measurement.Sha256;
                    activation = R7Crypto.VerifyEnvelope(file.Bytes, R7BuildIdentity.UpgradePublicCertificateSha256, verifier);
                }
                R7Json.ExactKeys(activation, "activation_sequence", "activation_time", "authority_class", "authority_directories", "authorization_identity", "caller", "installed_components", "new_interface_version", "operation", "request_frame_sha256", "request_identity", "request_payload_identity", "schema_version", "transition_nonce");
                if (R7Json.String(activation, "authority_class", 1, 128) != "TERMINAL_UPGRADE_ACTIVATION" ||
                    R7Json.String(activation, "operation", 1, 128) != "ACTIVATE_TERMINAL_UPGRADE" ||
                    R7Json.String(activation, "authorization_identity", 64, 64) != authorizationIdentity ||
                    R7Json.String(activation, "transition_nonce", 36, 36) != nonce ||
                    R7Json.String(activation, "new_interface_version", 1, 128) != R7Json.String(authorization, "new_interface_version", 1, 128) ||
                    R7Json.Integer(activation, "activation_sequence", 1, Int64.MaxValue) != R7Json.Integer(authorization, "activation_sequence", 1, Int64.MaxValue) ||
                    !R7Hash.IsLowerSha256(R7Json.String(activation, "request_frame_sha256", 64, 64)) ||
                    !R7Hash.IsLowerSha256(R7Json.String(activation, "request_payload_identity", 64, 64))) throw new InvalidDataException("UPGRADE_ACTIVATION_BINDING_INVALID");
                VerifyUpgradeMutationInteraction(ledger, objects, activation, "ACTIVATE_TERMINAL_UPGRADE");
                Guid activationRequestIdentity;
                if (!Guid.TryParseExact(R7Json.String(activation, "request_identity", 36, 36), "D", out activationRequestIdentity)) throw new InvalidDataException("UPGRADE_ACTIVATION_REQUEST_IDENTITY_INVALID");
                DateTimeOffset authorizationTime;
                DateTimeOffset activationTime;
                if (!DateTimeOffset.TryParseExact(R7Json.String(authorization, "authorization_time", 1, 128), "yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out authorizationTime) ||
                    !DateTimeOffset.TryParseExact(R7Json.String(activation, "activation_time", 1, 128), "yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out activationTime) || activationTime < authorizationTime) throw new InvalidDataException("UPGRADE_ACTIVATION_TIME_INVALID");

                string terminalSigner = String.Empty;
                string terminalPolicy = String.Empty;
                HashSet<string> roles = new HashSet<string>(StringComparer.Ordinal);
                Dictionary<string, SortedDictionary<string, object>> authorizedByRole = new Dictionary<string, SortedDictionary<string, object>>(StringComparer.Ordinal);
                Dictionary<string, string> componentSha256 = new Dictionary<string, string>(StringComparer.Ordinal);
                Dictionary<string, string> componentPaths = new Dictionary<string, string>(StringComparer.Ordinal);
                foreach (object raw in R7Json.Array(authorization, "components"))
                {
                    SortedDictionary<string, object> component = RequireObject(raw);
                    R7Json.ExactKeys(component, "file_identity", "final_path", "final_path_preinstall_state", "role", "sha256", "size", "staging_relative_path");
                    string role = R7Json.String(component, "role", 1, 256);
                    if (!roles.Add(role)) throw new InvalidDataException("UPGRADE_AUTHORIZATION_COMPONENT_DUPLICATE");
                    if (R7Json.String(component, "final_path_preinstall_state", 1, 64) != "ABSENT" || R7Json.String(component, "file_identity", 1, 128).Length == 0) throw new InvalidDataException("UPGRADE_AUTHORIZATION_PREINSTALL_MEASUREMENT_INVALID");
                    string sha = R7Json.String(component, "sha256", 64, 64);
                    if (!R7Hash.IsLowerSha256(sha)) throw new InvalidDataException("UPGRADE_AUTHORIZATION_COMPONENT_HASH_INVALID");
                    authorizedByRole.Add(role, component);
                    componentSha256.Add(role, sha);
                    componentPaths.Add(role, R7Json.String(component, "final_path", 3, 4096));
                    if (role == "TERMINAL_SIGNER") terminalSigner = sha;
                    if (role == "TERMINAL_POLICY") terminalPolicy = sha;
                }
                if (!R7Hash.IsLowerSha256(terminalSigner) || !R7Hash.IsLowerSha256(terminalPolicy)) throw new InvalidDataException("UPGRADE_AUTHORIZATION_REQUIRED_COMPONENT_MISSING");
                SortedDictionary<string, object> host = R7Json.Child(authorization, "host_binding");
                string authorizedVolumeIdentity = R7Json.String(host, "volume_identity", 8, 64);
                if (!String.Equals(authorizedVolumeIdentity, expectedVolumeIdentity, StringComparison.Ordinal)) throw new InvalidDataException("UPGRADE_ACTIVATION_VOLUME_BINDING_INVALID");
                Dictionary<string, string> directoryFileIdentities = VerifyActivationDirectories(activation, authorizedVolumeIdentity, authorizationIdentity == activeAuthorizationIdentity);
                Dictionary<string, string> installedFileIdentities = new Dictionary<string, string>(StringComparer.Ordinal);
                foreach (object rawInstalled in R7Json.Array(activation, "installed_components"))
                {
                    SortedDictionary<string, object> installed = RequireObject(rawInstalled);
                    R7Json.ExactKeys(installed, "canonical_path", "creation_time", "file_identity", "final_nt_path", "hard_link_count", "owner_sid", "role", "security_descriptor_sha256", "sha256", "size", "streams", "volume_identity");
                    string role = R7Json.String(installed, "role", 1, 256);
                    SortedDictionary<string, object> authorized;
                    if (!authorizedByRole.TryGetValue(role, out authorized) || installedFileIdentities.ContainsKey(role)) throw new InvalidDataException("UPGRADE_INSTALLED_COMPONENT_SET_INVALID");
                    string finalPath = R7Json.String(installed, "canonical_path", 3, 4096);
                    string fileIdentity = R7Json.String(installed, "file_identity", 1, 128);
                    string securityDescriptor = R7Json.String(installed, "security_descriptor_sha256", 64, 64);
                    object[] streams = R7Json.Array(installed, "streams");
                    DateTimeOffset creationTime;
                    if (!DateTimeOffset.TryParseExact(R7Json.String(installed, "creation_time", 1, 128), "yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out creationTime) || creationTime < authorizationTime || creationTime > activationTime ||
                        !String.Equals(finalPath, R7Json.String(authorized, "final_path", 3, 4096), StringComparison.Ordinal) ||
                        !R7Hash.FixedTimeEquals(R7Json.String(installed, "sha256", 64, 64), R7Json.String(authorized, "sha256", 64, 64)) ||
                        R7Json.Integer(installed, "size", 0, Int64.MaxValue) != R7Json.Integer(authorized, "size", 0, Int64.MaxValue) ||
                        R7Json.Integer(installed, "hard_link_count", 1, 1) != 1 ||
                        R7Json.String(installed, "owner_sid", 1, 256) != R7Fixed.SystemSid ||
                        R7Json.String(installed, "volume_identity", 8, 64) != authorizedVolumeIdentity ||
                        R7Json.String(installed, "final_nt_path", 3, 4096) != @"\\?\" + finalPath ||
                        !R7Hash.IsLowerSha256(securityDescriptor) || streams.Length != 1 || !String.Equals(streams[0] as string, "::$DATA", StringComparison.Ordinal)) throw new InvalidDataException("UPGRADE_INSTALLED_COMPONENT_MEASUREMENT_INVALID:" + role);
                    if (authorizationIdentity == activeAuthorizationIdentity)
                    {
                        string root = finalPath.StartsWith(R7Fixed.TerminalInstallRoot + Path.DirectorySeparatorChar, StringComparison.Ordinal) ? R7Fixed.TerminalInstallRoot : R7Fixed.RemediationRoot;
                        using (R7VerifiedFile current = R7SafeFile.Open(finalPath, finalPath, root, R7Json.String(installed, "sha256", 64, 64), R7Fixed.SystemSid, securityDescriptor, authorizedVolumeIdentity))
                        {
                            if (current.Measurement.FileIdentity != fileIdentity || current.Measurement.Size != R7Json.Integer(installed, "size", 0, Int64.MaxValue) || current.Measurement.CreationTime != R7Json.String(installed, "creation_time", 1, 128)) throw new InvalidDataException("ACTIVE_INSTALLED_COMPONENT_IDENTITY_CHANGED:" + role);
                        }
                    }
                    installedFileIdentities.Add(role, fileIdentity);
                }
                if (installedFileIdentities.Count != authorizedByRole.Count) throw new InvalidDataException("UPGRADE_INSTALLED_COMPONENT_SET_INCOMPLETE");
                SortedDictionary<string, object> activationCaller = R7Json.Child(activation, "caller");
                R7Json.ExactKeys(activationCaller, "authentication_id", "contains_terminal_signer_sid", "elevation_type", "group_sids", "privileges", "process_file_identity", "process_id", "process_path", "process_sha256", "process_start_time", "token_id", "user_sid");
                if (R7Json.String(activationCaller, "user_sid", 1, 256) != R7Fixed.TerminalSid || !R7Json.Boolean(activationCaller, "contains_terminal_signer_sid") ||
                    !R7Hash.FixedTimeEquals(R7Json.String(activationCaller, "process_sha256", 64, 64), terminalSigner) ||
                    R7Json.String(activationCaller, "process_file_identity", 1, 256) != installedFileIdentities["TERMINAL_SIGNER"]) throw new InvalidDataException("UPGRADE_ACTIVATION_CALLER_BINARY_INVALID");
                if (result.ContainsKey(authorizationIdentity)) throw new InvalidDataException("UPGRADE_AUTHORIZATION_IDENTITY_DUPLICATE");
                result.Add(authorizationIdentity, new R7UpgradeVersionBinding
                {
                    ActivationIdentity = activationIdentity,
                    ActivationSequence = R7Json.Integer(activation, "activation_sequence", 1, Int64.MaxValue),
                    AuthorizationIdentity = authorizationIdentity,
                    InterfaceVersion = R7Json.String(authorization, "new_interface_version", 1, 128),
                    PolicySha256 = terminalPolicy,
                    ServiceBinarySha256 = terminalSigner,
                    SourceCommit = R7Json.String(authorization, "source_commit", 40, 40),
                    SourceTree = R7Json.String(authorization, "source_tree", 40, 40),
                    TransitionNonce = nonce,
                    ComponentSha256 = componentSha256,
                    ComponentPaths = componentPaths,
                    DirectoryFileIdentities = directoryFileIdentities,
                    InstalledFileIdentities = installedFileIdentities
                });
            }
            foreach (R7LedgerRecord issuedRecord in ledger.Find("UPGRADE_AUTHORIZATION_ISSUED", null)) if (!resolvedAuthorizationNonces.Contains(issuedRecord.SubjectId)) throw new InvalidDataException("UPGRADE_LEDGER_AUTHORIZATION_FILE_MISSING");
            foreach (R7LedgerRecord activatedRecord in ledger.Find("UPGRADE_ACTIVATED", null)) if (!resolvedAuthorizationNonces.Contains(activatedRecord.SubjectId)) throw new InvalidDataException("UPGRADE_LEDGER_ACTIVATION_AUTHORIZATION_MISSING");
            foreach (R7LedgerRecord revokedRecord in ledger.Find("UPGRADE_AUTHORIZATION_REVOKED", null)) if (!resolvedAuthorizationNonces.Contains(revokedRecord.SubjectId)) throw new InvalidDataException("UPGRADE_LEDGER_REVOCATION_AUTHORIZATION_MISSING");
            foreach (string activationNonce in activationFileNonces) if (!consumedActivationNonces.Contains(activationNonce)) throw new InvalidDataException("UPGRADE_ACTIVATION_FILE_WITHOUT_ACTIVE_LEDGER_STATE");
            if (result.Count == 0 || !result.ContainsKey(activeAuthorizationIdentity)) throw new InvalidDataException("ACTIVE_ACTIVATED_UPGRADE_VERSION_BINDING_MISSING");
            long maximumActivatedSequence = 0;
            HashSet<long> activatedSequences = new HashSet<long>();
            foreach (R7UpgradeVersionBinding binding in result.Values)
            {
                if (!activatedSequences.Add(binding.ActivationSequence)) throw new InvalidDataException("UPGRADE_ACTIVATION_SEQUENCE_DUPLICATE");
                if (binding.ActivationSequence > maximumActivatedSequence) maximumActivatedSequence = binding.ActivationSequence;
            }
            if (result[activeAuthorizationIdentity].ActivationSequence != maximumActivatedSequence) throw new InvalidDataException("ACTIVE_UPGRADE_IS_DOWNGRADE");
            return result;
        }

        private static Dictionary<string, string> VerifyActivationDirectories(SortedDictionary<string, object> activation, string expectedVolumeIdentity, bool verifyCurrent)
        {
            SortedDictionary<string, string> expected = R7Fixed.AuthorityDirectories();
            Dictionary<string, string> identities = new Dictionary<string, string>(StringComparer.Ordinal);
            HashSet<string> distinctIdentities = new HashSet<string>(StringComparer.Ordinal);
            foreach (object rawDirectory in R7Json.Array(activation, "authority_directories"))
            {
                SortedDictionary<string, object> directory = RequireObject(rawDirectory);
                R7Json.ExactKeys(directory, "canonical_path", "creation_time", "file_identity", "final_nt_path", "hard_link_count", "owner_sid", "role", "security_descriptor_sha256", "sha256", "short_path", "size", "streams", "volume_identity");
                string role = R7Json.String(directory, "role", 1, 256);
                string expectedPath;
                if (!expected.TryGetValue(role, out expectedPath) || identities.ContainsKey(role)) throw new InvalidDataException("UPGRADE_AUTHORITY_DIRECTORY_SET_INVALID:" + role);
                string path = R7Json.String(directory, "canonical_path", 3, 4096);
                string fileIdentity = R7Json.String(directory, "file_identity", 25, 25);
                string aclIdentity = R7Json.String(directory, "security_descriptor_sha256", 64, 64);
                string creationTime = R7Json.String(directory, "creation_time", 1, 128);
                string shortPath = R7Json.String(directory, "short_path", 0, 4096);
                long linkCount = R7Json.Integer(directory, "hard_link_count", 1, UInt32.MaxValue);
                object[] streams = R7Json.Array(directory, "streams");
                DateTimeOffset parsedCreationTime;
                if (!String.Equals(path, expectedPath, StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(directory, "final_nt_path", 3, 4096), @"\\?\" + path, StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(directory, "owner_sid", 1, 256), R7Fixed.SystemSid, StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(directory, "volume_identity", 8, 64), expectedVolumeIdentity, StringComparison.Ordinal) ||
                    !fileIdentity.StartsWith(expectedVolumeIdentity + ":", StringComparison.Ordinal) || !IsLowerHex(fileIdentity.Substring(9)) ||
                    !R7Hash.IsLowerSha256(aclIdentity) || R7Json.String(directory, "sha256", 0, 0).Length != 0 || R7Json.Integer(directory, "size", 0, 0) != 0 ||
                    streams.Length != 1 || !String.Equals(streams[0] as string, "::$DATA", StringComparison.Ordinal) ||
                    !DateTimeOffset.TryParseExact(creationTime, "yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out parsedCreationTime) ||
                    !distinctIdentities.Add(fileIdentity)) throw new InvalidDataException("UPGRADE_AUTHORITY_DIRECTORY_MEASUREMENT_INVALID:" + role);
                if (verifyCurrent)
                {
                    R7FileMeasurement current = R7SafeFile.MeasureDirectory(path, path, R7Fixed.SystemSid, aclIdentity, expectedVolumeIdentity);
                    if (!String.Equals(current.FileIdentity, fileIdentity, StringComparison.Ordinal) || !String.Equals(current.CreationTime, creationTime, StringComparison.Ordinal) ||
                        !String.Equals(current.FinalNtPath, R7Json.String(directory, "final_nt_path", 3, 4096), StringComparison.Ordinal) ||
                        !String.Equals(current.ShortPath ?? String.Empty, shortPath, StringComparison.Ordinal) || current.LinkCount != (uint)linkCount ||
                        current.Streams.Length != 1 || !String.Equals(current.Streams[0], "::$DATA", StringComparison.Ordinal)) throw new InvalidDataException("ACTIVE_AUTHORITY_DIRECTORY_IDENTITY_CHANGED:" + role);
                }
                identities.Add(role, fileIdentity);
            }
            if (identities.Count != expected.Count) throw new InvalidDataException("UPGRADE_AUTHORITY_DIRECTORY_SET_INCOMPLETE");
            return identities;
        }

        private static bool IsLowerHex(string value)
        {
            if (String.IsNullOrEmpty(value)) return false;
            foreach (char character in value) if (!((character >= '0' && character <= '9') || (character >= 'a' && character <= 'f'))) return false;
            return true;
        }

        private static void VerifyLegacyReceiptDirectory(string root, string terminalReceiptRoot, string defaultType, bool reconciliation, R7VersionedLedger ledger, RSA verifier, string expectedVolumeIdentity, List<R7ReceiptClassification> output)
        {
            R7SafeFile.MeasureDirectory(root, root, null, null, expectedVolumeIdentity);
            if (Directory.GetDirectories(root, "*", SearchOption.TopDirectoryOnly).Length != 0) throw new InvalidDataException("LEGACY_RECEIPT_DIRECTORY_ENTRY_REJECTED");
            string[] paths = Directory.GetFiles(root, "*", SearchOption.TopDirectoryOnly);
            Array.Sort(paths, StringComparer.Ordinal);
            foreach (string path in paths)
            {
                string fileName = Path.GetFileName(path);
                if (fileName.Length != 69 || !fileName.EndsWith(".json", StringComparison.Ordinal)) throw new InvalidDataException("LEGACY_RECEIPT_FILENAME_INVALID");
                string name = fileName.Substring(0, 64);
                if (!R7Hash.IsLowerSha256(name)) throw new InvalidDataException("LEGACY_RECEIPT_FILENAME_INVALID");
                using (R7VerifiedFile file = R7SafeFile.Open(path, path, root, name, null, null, expectedVolumeIdentity))
                {
                    SortedDictionary<string, object> payload = R7Crypto.VerifyEnvelope(file.Bytes, R7Fixed.TerminalPublicKeyIdentity, verifier);
                    string schema = R7Json.String(payload, "schema_version", 1, 128);
                    string interfaceVersion = R7Json.String(payload, "interface_version", 1, 128);
                    string artifactType = R7Json.String(payload, "artifact_type", 1, 256);
                    ValidateLegacySchema(payload, reconciliation, schema, interfaceVersion, artifactType);
                    string policySha = R7Json.String(payload, "policy_sha256", 64, 64);
                    string serviceSha = R7Json.String(payload, "service_binary_sha256", 64, 64);
                    if (!R7Hash.IsLowerSha256(policySha) || !R7Hash.IsLowerSha256(serviceSha) || !LegacyVersionBindingAllowed(schema, interfaceVersion, policySha, serviceSha)) throw new InvalidDataException("LEGACY_RECEIPT_VERSION_BINDING_UNKNOWN");
                    if (R7Json.String(payload, "public_key_identity", 64, 64) != R7Fixed.TerminalPublicKeyIdentity ||
                        R7Json.String(payload, "ledger_id", 64, 64) != R7Fixed.LedgerId ||
                        R7Json.String(payload, "service_sid", 1, 256) != R7Fixed.TerminalSid) throw new InvalidDataException("LEGACY_RECEIPT_FIXED_IDENTITY_MISMATCH");
                    string issueTime = R7Json.String(payload, "issue_time", 1, 128);
                    DateTimeOffset parsedIssueTime;
                    if (!DateTimeOffset.TryParseExact(issueTime, "yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out parsedIssueTime)) throw new InvalidDataException("LEGACY_RECEIPT_TIME_INVALID");
                    R7LedgerRecord membership = ResolveLegacyMembership(ledger, name, reconciliation);
                    if (membership.SchemaVersion != schema) throw new InvalidDataException("LEGACY_RECEIPT_LEDGER_SCHEMA_MISMATCH");
                    long reservationSequence = R7Json.Integer(payload, "ledger_reservation_sequence", 1, Int64.MaxValue);
                    R7LedgerRecord reservation = ledger.FindSequence(reservationSequence);
                    string reservationOperation = reconciliation ? "R7_RECONCILIATION_RESERVED" : "R7_TERMINAL_RESERVED";
                    string claimField = reconciliation ? "reconciliation_claim_identity" : "terminal_claim_identity";
                    if (reservation == null || reservation.Operation != reservationOperation ||
                        reservation.EntryIdentity != R7Json.String(payload, "ledger_reservation_entry_identity", 64, 64) ||
                        reservation.ContentAddress != R7Json.String(payload, claimField, 64, 64) || membership.Sequence <= reservation.Sequence) throw new InvalidDataException("LEGACY_RECEIPT_RESERVATION_BINDING_INVALID");
                    if (reconciliation)
                    {
                        string candidate = R7Json.String(payload, "candidate_receipt_identity", 64, 64);
                        string fresh = R7Json.String(payload, "fresh_receipt_identity", 64, 64);
                        if (!R7Hash.IsLowerSha256(candidate) || !R7Hash.IsLowerSha256(fresh)) throw new InvalidDataException("LEGACY_RECONCILIATION_RECEIPT_REFERENCE_MISSING");
                        VerifyLegacyReferencedReceipt(terminalReceiptRoot, candidate, verifier, expectedVolumeIdentity);
                        VerifyLegacyReferencedReceipt(terminalReceiptRoot, fresh, verifier, expectedVolumeIdentity);
                    }
                    string type = payload.ContainsKey("receipt_type") ? R7Json.String(payload, "receipt_type", 1, 128) : defaultType;
                    output.Add(new R7ReceiptClassification
                    {
                        AuthorityClass = "REJECTED_IMPLEMENTATION_RECEIPT_NEVER_ACCEPTED",
                        Identity = name,
                        ReceiptType = type,
                        Classification = "STRUCTURALLY_VALID_REJECTED_NONAUTHORITATIVE_CANDIDATE_EVIDENCE",
                        InterfaceVersion = interfaceVersion,
                        IssueTime = issueTime,
                        LedgerEntryIdentity = membership.EntryIdentity,
                        LedgerSequence = membership.Sequence,
                        PolicySha256 = policySha,
                        SchemaVersion = schema,
                        ServiceBinarySha256 = serviceSha,
                        SourceFamily = interfaceVersion == "2.0.0-DRAFT" ? "REJECTED_V2_DRAFT" : "REJECTED_V3_DRAFT",
                        TrustIdentity = R7Fixed.TerminalPublicKeyIdentity
                    });
                }
            }
        }

        private static void VerifyLegacyReferencedReceipt(string root, string identity, RSA verifier, string expectedVolumeIdentity)
        {
            string path = Path.Combine(root, identity + ".json");
            using (R7VerifiedFile file = R7SafeFile.Open(path, path, root, identity, null, null, expectedVolumeIdentity))
            {
                SortedDictionary<string, object> payload = R7Crypto.VerifyEnvelope(file.Bytes, R7Fixed.TerminalPublicKeyIdentity, verifier);
                if (R7Json.String(payload, "public_key_identity", 64, 64) != R7Fixed.TerminalPublicKeyIdentity || R7Json.String(payload, "ledger_id", 64, 64) != R7Fixed.LedgerId) throw new InvalidDataException("LEGACY_RECONCILIATION_REFERENCED_RECEIPT_INVALID");
            }
        }

        private static void ValidateLegacySchema(SortedDictionary<string, object> payload, bool reconciliation, string schema, string interfaceVersion, string artifactType)
        {
            if (!reconciliation && schema == "7.0.0-DRAFT" && interfaceVersion == "2.0.0-DRAFT" && artifactType == "SIGNED_R7_TERMINAL_RECEIPT")
            {
                R7Json.ExactKeys(payload, "artifact_type", "attempt_id", "attempt_receipt_locator", "authorization_state", "case_count", "child_evidence", "cleanup_result", "configuration", "deterministic_identity", "deterministic_semantic_identities", "discrepancy_count", "event_count", "final_terminal_state", "governed_execution_identity", "interface_version", "ipc_identity", "issue_time", "ledger_id", "ledger_reservation_entry_identity", "ledger_reservation_prior_root", "ledger_reservation_sequence", "observation_count", "phase", "policy_sha256", "prior_authoritative_state", "process_counts", "provisioning_commit", "public_key_identity", "r6_commit", "r7_blocked_commit", "r7_incomplete_commit", "requested_transition", "run_id", "run_issuance_ledger_entry_identity", "run_issuance_ledger_sequence", "run_issuance_receipt_locator", "run_nonce", "run_specific_identities", "schema_version", "service_binary_sha256", "service_name", "service_sid", "symbol", "terminal_claim_identity", "terminal_operation", "terminal_status", "trade_or_workflow_identity", "worker_sha256");
                return;
            }
            if (!reconciliation && schema == "7.1.0-DRAFT" && interfaceVersion == "3.0.0-DRAFT" && artifactType == "R7_SIGNED_TERMINAL_RECEIPT")
            {
                R7Json.ExactKeys(payload, "artifact_type", "attempt_id", "attempt_locator", "case_count", "case_definition_git_blob", "case_definition_sha256", "case_definition_size", "comparator_result_locator", "configuration", "event_root", "event_source_locator", "expectation_git_blob", "expectation_sha256", "expectation_size", "interface_version", "ipc_identity", "issue_time", "ledger_genesis_identity", "ledger_id", "ledger_reservation_entry_identity", "ledger_reservation_prior_root", "ledger_reservation_sequence", "observation_locator", "phase", "policy_sha256", "process_index_locator", "public_key_identity", "run_id", "run_issuance_ledger_entry_identity", "run_locator", "run_nonce", "schema_version", "service_binary_sha256", "service_sid", "subject_commit", "subject_process_id", "subject_run_id", "suite_process_receipt_locator", "terminal_claim_identity", "terminal_verifier_result", "traceability_locator", "worker_sha256");
                return;
            }
            if (reconciliation && schema == "7.0.0-DRAFT" && interfaceVersion == "2.0.0-DRAFT" && artifactType == "SIGNED_R7_RECONCILIATION_RECEIPT")
            {
                R7Json.ExactKeys(payload, "artifact_type", "attempt_id", "candidate_locator", "candidate_receipt_identity", "candidate_run_id", "candidate_run_nonce", "configuration", "deterministic_identity", "fresh_locator", "fresh_receipt_identity", "fresh_run_id", "fresh_run_nonce", "interface_version", "ipc_identity", "issue_time", "ledger_id", "ledger_reservation_entry_identity", "ledger_reservation_prior_root", "ledger_reservation_sequence", "normalized_comparison_identity", "normalized_observation_identity", "pair_identity", "policy_sha256", "provisioning_commit", "public_key_identity", "r6_commit", "reconciliation_attempt_nonce", "reconciliation_claim_identity", "schema_version", "service_binary_sha256", "service_sid", "status", "terminal_receipts_verified");
                return;
            }
            if (reconciliation && schema == "7.1.0-DRAFT" && interfaceVersion == "3.0.0-DRAFT" && artifactType == "R7_SIGNED_EXTERNAL_RECONCILIATION_RECEIPT")
            {
                R7Json.ExactKeys(payload, "artifact_type", "attempt_id", "candidate_event_root", "candidate_receipt_identity", "candidate_receipt_locator", "candidate_run_id", "case_definition_git_blob", "configuration", "expectation_git_blob", "fresh_event_root", "fresh_receipt_identity", "fresh_receipt_locator", "fresh_run_id", "interface_version", "issue_time", "ledger_id", "ledger_reservation_entry_identity", "ledger_reservation_sequence", "policy_sha256", "provenance_disjoint", "public_key_identity", "reconciliation_claim_identity", "reconciliation_evaluator_result_locator", "reconciliation_process_nonce", "reconciliation_process_receipt_locator", "reconciliation_process_run_id", "reconciliation_result", "schema_version", "service_binary_sha256", "service_sid", "subject_commit", "synthetic_result_class_absent", "worker_sha256");
                return;
            }
            throw new InvalidDataException("LEGACY_RECEIPT_SCHEMA_OR_ARTIFACT_UNKNOWN");
        }

        private static bool LegacyVersionBindingAllowed(string schema, string interfaceVersion, string policy, string service)
        {
            if (schema == "7.0.0-DRAFT" && interfaceVersion == "2.0.0-DRAFT")
            {
                return (policy == "bde065eb0d484a18fb2edb7d35573af6dd002c7c7a5119d637e278847f6acd91" && service == "6076d4d630721d911517f8a1b92cff32777098fbb714bd417d38b5c6f6904763") ||
                    (policy == "5d81f25c46edeb555e3f158d85627682ad2da946d1fabc7a1f585a621ee6f37e" && (service == "2af03bbeff16adc56c009ffcda87078f3d86bb8ea761bc9e96f9b81831a7b05e" || service == "f885c15a00f82ce850afed27b3a352cb3efb52d0d90fba4ac232c588dfd06eb6"));
            }
            if (schema == "7.1.0-DRAFT" && interfaceVersion == "3.0.0-DRAFT")
            {
                return (policy == "c8c3653d9658d3919bf7c5f4507974f651457b304e6d5216db7ba9b8700f8dda" && service == "8f544d64d8279d3f6984ed0262beb96ec16950090ea34bbe6fba8e895fb3fade") ||
                    (policy == "76eb2900b2000aa0b41e6040335cc323f7443728aad21cd871d5b6b8e17bcd8b" && service == "9ea829416f37c94db2858586fa5e0042652f6caa4637a29fdbefb513577a7526");
            }
            return false;
        }

        private static R7LedgerRecord ResolveLegacyMembership(R7VersionedLedger ledger, string identity, bool reconciliation)
        {
            R7LedgerRecord found = null;
            foreach (R7LedgerRecord record in ledger.Records)
            {
                bool operation = reconciliation ? record.Operation == "R7_RECONCILIATION_COMMITTED" || record.Operation == "R7_RECONCILIATION_RECEIPT_COMMITTED" : record.Operation == "R7_TERMINAL_RECEIPT_COMMITTED";
                if (!operation || record.ContentAddress != identity) continue;
                if (found != null) throw new InvalidDataException("LEGACY_RECEIPT_LEDGER_MEMBERSHIP_DUPLICATE");
                found = record;
            }
            if (found == null) throw new InvalidDataException("LEGACY_RECEIPT_LEDGER_MEMBERSHIP_MISSING");
            return found;
        }

        private static void VerifyV4Receipts(RSA verifier, Dictionary<string, R7TransactionSnapshot> receiptTransactions, R7VersionedLedger ledger, R7ObjectStore objects, R7EvidenceStore interactionEvidence, R7AuthoritySet authority, Dictionary<string, R7UpgradeVersionBinding> upgradeBindings, string expectedVolumeIdentity, List<R7ReceiptClassification> output)
        {
            R7SafeFile.MeasureDirectory(R7Fixed.ReceiptRoot, R7Fixed.ReceiptRoot, R7Fixed.SystemSid, null, expectedVolumeIdentity);
            if (Directory.GetDirectories(R7Fixed.ReceiptRoot, "*", SearchOption.TopDirectoryOnly).Length != 0) throw new InvalidDataException("V4_RECEIPT_DIRECTORY_ENTRY_REJECTED");
            string[] paths = Directory.GetFiles(R7Fixed.ReceiptRoot, "*", SearchOption.TopDirectoryOnly);
            Array.Sort(paths, StringComparer.Ordinal);
            foreach (string path in paths)
            {
                string name = Path.GetFileName(path);
                string suffix = ".receipt.json";
                if (name.Length != 64 + suffix.Length || !name.EndsWith(suffix, StringComparison.Ordinal)) throw new InvalidDataException("V4_RECEIPT_FILENAME_INVALID");
                string identity = name.Substring(0, name.Length - suffix.Length);
                if (!R7Hash.IsLowerSha256(identity)) throw new InvalidDataException("V4_RECEIPT_FILENAME_INVALID");
                using (R7VerifiedFile file = R7SafeFile.Open(path, path, R7Fixed.ReceiptRoot, identity, R7Fixed.TerminalSid, null, expectedVolumeIdentity))
                {
                    SortedDictionary<string, object> payload = R7Crypto.VerifyEnvelope(file.Bytes, R7Fixed.TerminalPublicKeyIdentity, verifier);
                    R7Json.ExactKeys(payload, "activation_identity", "authority_identities", "details", "evidence_identity", "interface_version", "issue_time", "ledger_id", "policy_sha256", "public_key_identity", "receipt_type", "request_identity", "request_sha256", "schema_version", "source_commit", "source_tree", "terminal_classification", "upgrade_authorization_identity");
                    if (R7Json.String(payload, "schema_version", 1, 128) != "4.0.0" || R7Json.String(payload, "ledger_id", 64, 64) != R7Fixed.LedgerId || R7Json.String(payload, "public_key_identity", 64, 64) != R7Fixed.TerminalPublicKeyIdentity) throw new InvalidDataException("V4_RECEIPT_FIXED_IDENTITY_MISMATCH");
                    string requestIdentity = R7Json.String(payload, "request_identity", 36, 36);
                    Guid parsedRequestIdentity;
                    DateTimeOffset issueTime;
                    if (!Guid.TryParseExact(requestIdentity, "D", out parsedRequestIdentity) || parsedRequestIdentity.ToString("D") != requestIdentity ||
                        !DateTimeOffset.TryParseExact(R7Json.String(payload, "issue_time", 28, 28), "yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out issueTime) ||
                        !R7Hash.IsLowerSha256(R7Json.String(payload, "request_sha256", 64, 64)) ||
                        !R7Hash.IsLowerSha256(R7Json.String(payload, "evidence_identity", 64, 64))) throw new InvalidDataException("V4_RECEIPT_REQUEST_OR_TIME_INVALID");
                    SortedDictionary<string, object> authorityIdentities = R7Json.Child(payload, "authority_identities");
                    R7Json.ExactKeys(authorityIdentities, "case_definitions_sha256", "coverage_proof_sha256", "expectations_sha256", "requirement_registry_sha256", "source_manifest_sha256");
                    if (R7Json.String(authorityIdentities, "case_definitions_sha256", 64, 64) != R7BuildIdentity.CaseDefinitionsSha256 ||
                        R7Json.String(authorityIdentities, "coverage_proof_sha256", 64, 64) != R7BuildIdentity.CoverageProofSha256 ||
                        R7Json.String(authorityIdentities, "expectations_sha256", 64, 64) != R7BuildIdentity.ExpectationsSha256 ||
                        R7Json.String(authorityIdentities, "requirement_registry_sha256", 64, 64) != R7BuildIdentity.RequirementRegistrySha256 ||
                        R7Json.String(authorityIdentities, "source_manifest_sha256", 64, 64) != R7BuildIdentity.AuthoritySourceManifestSha256) throw new InvalidDataException("V4_RECEIPT_AUTHORITY_IDENTITY_MISMATCH");
                    string authorizationIdentity = R7Json.String(payload, "upgrade_authorization_identity", 64, 64);
                    R7UpgradeVersionBinding version;
                    if (!upgradeBindings.TryGetValue(authorizationIdentity, out version) ||
                        R7Json.String(payload, "activation_identity", 64, 64) != version.ActivationIdentity ||
                        R7Json.String(payload, "interface_version", 1, 128) != version.InterfaceVersion ||
                        R7Json.String(payload, "policy_sha256", 64, 64) != version.PolicySha256 ||
                        R7Json.String(payload, "source_commit", 40, 40) != version.SourceCommit ||
                        R7Json.String(payload, "source_tree", 40, 40) != version.SourceTree) throw new InvalidDataException("V4_RECEIPT_UPGRADE_VERSION_BINDING_INVALID");
                    R7TransactionSnapshot transaction;
                    bool stateKnown = receiptTransactions.TryGetValue(identity, out transaction);
                    bool committed = stateKnown && (transaction.State == "COMMITTED" || transaction.State == "RESPONSE_AVAILABLE");
                    if (stateKnown && (transaction.RequestIdentity != requestIdentity || transaction.RequestSha256 != R7Json.String(payload, "request_sha256", 64, 64) || transaction.EvidenceIdentity != R7Json.String(payload, "evidence_identity", 64, 64))) throw new InvalidDataException("V4_RECEIPT_TRANSACTION_BINDING_INVALID");
                    string issuedClassification = R7Json.String(payload, "terminal_classification", 1, 256);
                    if (stateKnown && transaction.TerminalClassification.Length != 0 && transaction.TerminalClassification != issuedClassification) throw new InvalidDataException("V4_RECEIPT_TRANSACTION_CLASSIFICATION_MISMATCH");
                    string receiptType = R7Json.String(payload, "receipt_type", 1, 128);
                    if (issuedClassification == "COMMITTED_AUTHORITATIVE_FRESH_RECEIPT")
                    {
                        if (receiptType != "TERMINAL_RUN_RECEIPT") throw new InvalidDataException("V4_FRESH_RECEIPT_TYPE_INVALID");
                        if (stateKnown) RequireTransactionOperation(transaction, "SUBMIT_RUN_GRAPH");
                        string freshRunKind = R7Json.String(R7Json.Child(payload, "details"), "run_kind", 1, 64);
                        if (freshRunKind != "FRESH" && freshRunKind != "CASE_FRESH") throw new InvalidDataException("V4_FRESH_RUN_KIND_INVALID");
                        VerifyRunEvidence(identity, payload, objects, interactionEvidence, authority, version, freshRunKind, freshRunKind == "FRESH" ? "POS-006" : String.Empty, freshRunKind == "FRESH");
                    }
                    else if (issuedClassification == "VALID_NONAUTHORITATIVE_CANDIDATE_EVIDENCE")
                    {
                        if (receiptType != "TERMINAL_RUN_RECEIPT") throw new InvalidDataException("V4_CANDIDATE_RECEIPT_TYPE_INVALID");
                        if (stateKnown) RequireTransactionOperation(transaction, "SUBMIT_RUN_GRAPH");
                        string candidateRunKind = R7Json.String(R7Json.Child(payload, "details"), "run_kind", 1, 64);
                        if (candidateRunKind != "CANDIDATE" && candidateRunKind != "CASE_CANDIDATE") throw new InvalidDataException("V4_CANDIDATE_RUN_KIND_INVALID");
                        VerifyRunEvidence(identity, payload, objects, interactionEvidence, authority, version, candidateRunKind, candidateRunKind == "CANDIDATE" ? "POS-005" : String.Empty, candidateRunKind == "CANDIDATE");
                    }
                    else if (issuedClassification == "VALID_NONAUTHORITATIVE_BOOTSTRAP_EVIDENCE")
                    {
                        if (receiptType != "TERMINAL_RUN_RECEIPT") throw new InvalidDataException("V4_BOOTSTRAP_RECEIPT_TYPE_INVALID");
                        if (stateKnown) RequireTransactionOperation(transaction, "SUBMIT_RUN_GRAPH");
                        string bootstrapRunKind = R7Json.String(R7Json.Child(payload, "details"), "run_kind", 1, 64);
                        if (bootstrapRunKind != "BOOTSTRAP_CANDIDATE" && bootstrapRunKind != "BOOTSTRAP_FRESH") throw new InvalidDataException("V4_BOOTSTRAP_RUN_KIND_INVALID");
                        VerifyRunEvidence(identity, payload, objects, interactionEvidence, authority, version, bootstrapRunKind, String.Empty, false);
                    }
                    else if (issuedClassification == "COMMITTED_RECONCILIATION" || issuedClassification == "VALID_NONAUTHORITATIVE_BOOTSTRAP_RECONCILIATION")
                    {
                        if (receiptType != "RECONCILIATION_RECEIPT") throw new InvalidDataException("V4_RECONCILIATION_RECEIPT_TYPE_INVALID");
                        if (stateKnown) RequireTransactionOperation(transaction, "SUBMIT_RECONCILIATION");
                        VerifyReconciliationEvidence(payload, objects, receiptTransactions, issuedClassification == "COMMITTED_RECONCILIATION", authority.CaseIds.Length - 2);
                    }
                    else if (issuedClassification == "REQUEST_RECEIVED_NONAUTHORITY")
                    {
                        if (receiptType != "TERMINAL_PROPOSAL_RECEIPT") throw new InvalidDataException("V4_PROPOSAL_RECEIPT_TYPE_INVALID");
                        if (stateKnown) RequireTransactionOperation(transaction, "SUBMIT_TERMINAL_PROPOSAL");
                        VerifyProposalEvidence(payload, objects);
                    }
                    else throw new InvalidDataException("V4_RECEIPT_ISSUANCE_CLASSIFICATION_UNKNOWN");
                    string classification;
                    if (!committed)
                    {
                        if (stateKnown && transaction.State == "SUPERSEDED") classification = "SUPERSEDED_INCOMPLETE_ISSUANCE_NONAUTHORITY";
                        else if (stateKnown && transaction.State == "ABORTED") classification = "ABORTED_ISSUANCE";
                        else classification = "INCOMPLETE_ISSUANCE_NONAUTHORITY";
                    }
                    else if (issuedClassification == "COMMITTED_AUTHORITATIVE_FRESH_RECEIPT") classification = "VALID_AUTHORITATIVE_RECEIPT";
                    else if (issuedClassification == "VALID_NONAUTHORITATIVE_CANDIDATE_EVIDENCE") classification = "STRUCTURALLY_VALID_NONAUTHORITATIVE_CANDIDATE_EVIDENCE";
                    else if (issuedClassification == "COMMITTED_RECONCILIATION") classification = "VALID_AUTHORITATIVE_RECONCILIATION";
                    else if (issuedClassification == "VALID_NONAUTHORITATIVE_BOOTSTRAP_RECONCILIATION") classification = "STRUCTURALLY_VALID_NONAUTHORITATIVE_BOOTSTRAP_RECONCILIATION";
                    else if (issuedClassification == "VALID_NONAUTHORITATIVE_BOOTSTRAP_EVIDENCE") classification = "STRUCTURALLY_VALID_NONAUTHORITATIVE_BOOTSTRAP_EVIDENCE";
                    else if (issuedClassification == "REQUEST_RECEIVED_NONAUTHORITY") classification = "VALID_NONAUTHORITATIVE_PROPOSAL_EVIDENCE";
                    else classification = "VERSION_RESOLVED_NONAUTHORITY";
                    R7LedgerRecord membership = ResolveV4Membership(ledger, objects, identity, committed);
                    output.Add(new R7ReceiptClassification
                    {
                        AuthorityClass = classification == "VALID_AUTHORITATIVE_RECEIPT" || classification == "VALID_AUTHORITATIVE_RECONCILIATION" ? "ACTIVATED_REMEDIATION_AUTHORITY" : "ACTIVATED_REMEDIATION_NONAUTHORITY_EVIDENCE",
                        Identity = identity,
                        ReceiptType = receiptType,
                        Classification = classification,
                        InterfaceVersion = version.InterfaceVersion,
                        IssueTime = R7Json.String(payload, "issue_time", 1, 128),
                        LedgerEntryIdentity = membership == null ? String.Empty : membership.EntryIdentity,
                        LedgerSequence = membership == null ? 0 : membership.Sequence,
                        PolicySha256 = version.PolicySha256,
                        SchemaVersion = R7Json.String(payload, "schema_version", 1, 128),
                        ServiceBinarySha256 = version.ServiceBinarySha256,
                        SourceFamily = "REMEDIATION_V4",
                        TrustIdentity = R7Fixed.TerminalPublicKeyIdentity
                    });
                }
            }
        }

        private static void RequireTransactionOperation(R7TransactionSnapshot transaction, string expectedOperation)
        {
            if (transaction == null || transaction.Operation != expectedOperation) throw new InvalidDataException("V4_RECEIPT_TRANSACTION_OPERATION_INVALID");
        }

        private static void VerifyProposalEvidence(SortedDictionary<string, object> receipt, R7ObjectStore objects)
        {
            SortedDictionary<string, object> details = R7Json.Child(receipt, "details");
            R7Json.ExactKeys(details, "checkout_identity", "configuration", "proposal_identity");
            string checkout = R7Json.String(details, "checkout_identity", 64, 64);
            string proposal = R7Json.String(details, "proposal_identity", 64, 64);
            if (!R7Hash.IsLowerSha256(checkout) || !R7Hash.IsLowerSha256(proposal)) throw new InvalidDataException("PROPOSAL_DETAILS_INVALID");
            SortedDictionary<string, object> evidence = objects.Get(R7Json.String(receipt, "evidence_identity", 64, 64));
            R7Json.ExactKeys(evidence, "caller", "checkout_identity", "configuration", "proposal_identity", "request_frame_sha256");
            if (R7Json.String(evidence, "checkout_identity", 64, 64) != checkout ||
                R7Json.String(evidence, "proposal_identity", 64, 64) != proposal ||
                R7Json.String(evidence, "request_frame_sha256", 64, 64) != R7Json.String(receipt, "request_sha256", 64, 64) ||
                R7Hash.Bytes(R7Json.Encode(R7Json.Child(evidence, "configuration"))) != R7Hash.Bytes(R7Json.Encode(R7Json.Child(details, "configuration")))) throw new InvalidDataException("PROPOSAL_EVIDENCE_BINDING_INVALID");
            ValidateCallerShape(R7Json.Child(evidence, "caller"));
        }

        private static void ValidateCallerShape(SortedDictionary<string, object> caller)
        {
            R7Json.ExactKeys(caller, "authentication_id", "contains_terminal_signer_sid", "elevation_type", "group_sids", "privileges", "process_file_identity", "process_id", "process_path", "process_sha256", "process_start_time", "token_id", "user_sid");
            if (!R7Hash.IsLowerSha256(R7Json.String(caller, "process_sha256", 64, 64)) ||
                R7Json.String(caller, "process_file_identity", 1, 256).Length == 0 ||
                R7Json.Integer(caller, "process_id", 1, Int64.MaxValue) < 1 ||
                R7Json.String(caller, "user_sid", 1, 256).Length == 0) throw new InvalidDataException("CALLER_EVIDENCE_INVALID");
        }

        private static R7LedgerRecord ResolveV4Membership(R7VersionedLedger ledger, R7ObjectStore objects, string receiptIdentity, bool required)
        {
            R7LedgerRecord found = null;
            foreach (R7LedgerRecord record in ledger.Records)
            {
                if (record.Operation != "R7R_COMMITTED") continue;
                SortedDictionary<string, object> state = objects.Get(record.ContentAddress);
                R7Json.ExactKeys(state, "classification", "evidence_identity", "operation", "prior_state", "receipt_identity", "request_identity", "request_sha256", "response_identity", "schema_version", "state", "transition_time");
                if (R7Json.String(state, "state", 1, 128) != "COMMITTED" || record.SubjectId != R7Json.String(state, "request_identity", 36, 36)) throw new InvalidDataException("V4_RECEIPT_COMMIT_STATE_INVALID");
                if (!state.ContainsKey("receipt_identity") || R7Json.String(state, "receipt_identity", 0, 64) != receiptIdentity) continue;
                if (found != null) throw new InvalidDataException("V4_RECEIPT_COMMIT_MEMBERSHIP_DUPLICATE");
                found = record;
            }
            if (required && found == null) throw new InvalidDataException("V4_RECEIPT_COMMIT_MEMBERSHIP_MISSING");
            return found;
        }

        private static void VerifyRunEvidence(string receiptIdentity, SortedDictionary<string, object> receipt, R7ObjectStore objects, R7EvidenceStore interactionEvidence, R7AuthoritySet authority, R7UpgradeVersionBinding version, string requiredRunKind, string currentCase, bool requireComplete)
        {
            SortedDictionary<string, object> details = R7Json.Child(receipt, "details");
            R7Json.ExactKeys(details, "case_count", "checkout_identity", "complete_case_registry", "completion_scope", "configuration", "provenance_identity", "run_kind");
            long caseCount = R7Json.Integer(details, "case_count", 1, authority.CaseIds.Length);
            bool completeCaseRegistry = R7Json.Boolean(details, "complete_case_registry");
            bool caseSubmissionProbe = requiredRunKind == "CASE_CANDIDATE" || requiredRunKind == "CASE_FRESH";
            string completionScope = R7Json.String(details, "completion_scope", 1, 128);
            if ((requireComplete && (!completeCaseRegistry || caseCount != authority.CaseIds.Length - 1)) ||
                (caseSubmissionProbe && (completeCaseRegistry || caseCount != authority.CaseIds.Length - 2 || completionScope != "NONRECURSIVE_CASE_SUBMISSION_PROBE")) ||
                (!caseSubmissionProbe && requireComplete && completionScope != "FULL_GOVERNED_CASE_REGISTRY") ||
                (!caseSubmissionProbe && !requireComplete && completionScope != "PARTIAL_BOOTSTRAP_GRAPH") ||
                R7Json.String(details, "run_kind", 1, 64) != requiredRunKind ||
                !R7Hash.IsLowerSha256(R7Json.String(details, "checkout_identity", 64, 64)) ||
                !R7Hash.IsLowerSha256(R7Json.String(details, "provenance_identity", 64, 64))) throw new InvalidDataException("RUN_RECEIPT_DETAILS_INVALID");
            SortedDictionary<string, object> graph = objects.Get(R7Json.String(receipt, "evidence_identity", 64, 64));
            R7Json.ExactKeys(graph, "artifact_type", "case_count", "case_results", "complete_for_run", "passed", "run_kind", "schema_version");
            if (R7Json.String(graph, "artifact_type", 1, 256) != "R7_SIGNER_REDERIVED_SUITE_EVIDENCE" ||
                R7Json.String(graph, "schema_version", 1, 128) != "1.0.0" ||
                R7Json.String(graph, "run_kind", 1, 64) != requiredRunKind ||
                R7Json.Boolean(graph, "complete_for_run") != (completeCaseRegistry || caseSubmissionProbe) || !R7Json.Boolean(graph, "passed") ||
                R7Json.Integer(graph, "case_count", 1, authority.CaseIds.Length) != caseCount || R7Json.Array(graph, "case_results").Length != caseCount) throw new InvalidDataException("RUN_GRAPH_INCOMPLETE");
            HashSet<string> seen = new HashSet<string>(StringComparer.Ordinal);
            bool currentFound = false;
            foreach (object raw in R7Json.Array(graph, "case_results"))
            {
                SortedDictionary<string, object> locator = RequireObject(raw);
                R7Json.ExactKeys(locator, "case_id", "result_identity");
                string caseId = R7Json.String(locator, "case_id", 1, 128);
                if (!seen.Add(caseId)) throw new InvalidDataException("DUPLICATE_CASE_RESULT");
                R7CaseDefinition definition = authority.Case(caseId);
                R7Expectation expectation = authority.Expectation(caseId);
                SortedDictionary<string, object> result = objects.Get(R7Json.String(locator, "result_identity", 64, 64));
                string baseIdentity = R7Json.String(result, "base_interaction_identity", 64, 64);
                if (definition.Driver == "RAW_FRAME")
                {
                    R7Json.ExactKeys(result, "actual_code", "actual_status", "base_capture_identity", "base_interaction_identity", "case_id", "comparator_capture_identity", "effective_base_caller_role", "event_capture_identity", "expectation_definition_sha256", "expected_code", "expected_response_class", "expected_terminal_classification", "observation_capture_identity", "obligation_proof_identity", "obligations_verified", "parser_rejection_offset", "parser_result_rederived", "passed", "raw_evidence_complete", "signer_derived_terminal_classification", "signer_rederived");
                    if (R7Json.String(result, "parser_result_rederived", 1, 256) != R7Json.String(result, "actual_code", 1, 256) || R7Json.Integer(result, "parser_rejection_offset", -1, Int64.MaxValue) < -1) throw new InvalidDataException("CASE_PARSER_REDERIVATION_INVALID");
                }
                else R7Json.ExactKeys(result, "actual_code", "actual_status", "base_capture_identity", "base_interaction_identity", "case_id", "comparator_capture_identity", "effective_base_caller_role", "event_capture_identity", "expectation_definition_sha256", "expected_code", "expected_response_class", "expected_terminal_classification", "observation_capture_identity", "obligation_proof_identity", "obligations_verified", "passed", "raw_evidence_complete", "signer_derived_terminal_classification", "signer_rederived");
                if (!R7Hash.IsLowerSha256(baseIdentity) ||
                    !R7Hash.IsLowerSha256(R7Json.String(result, "base_capture_identity", 64, 64)) ||
                    !R7Hash.IsLowerSha256(R7Json.String(result, "event_capture_identity", 64, 64)) ||
                    !R7Hash.IsLowerSha256(R7Json.String(result, "observation_capture_identity", 64, 64)) ||
                    !R7Hash.IsLowerSha256(R7Json.String(result, "comparator_capture_identity", 64, 64)) ||
                    !R7Json.Boolean(result, "raw_evidence_complete") || !R7Json.Boolean(result, "obligations_verified")) throw new InvalidDataException("CASE_RAW_OR_OBLIGATION_PROOF_MISSING");
                VerifyInteractionGraph(result, objects, interactionEvidence, version, definition);
                ValidateObligationProof(objects.Get(R7Json.String(result, "obligation_proof_identity", 64, 64)), expectation, caseId);
                if (!String.IsNullOrEmpty(currentCase) && caseId == currentCase) currentFound = true;
                if (!R7Json.Boolean(result, "passed") || !R7Json.Boolean(result, "signer_rederived") ||
                    R7Json.String(result, "case_id", 1, 128) != caseId ||
                    R7Json.String(result, "actual_code", 1, 256) != expectation.ResultCode ||
                    R7Json.String(result, "actual_status", 1, 256) != expectation.ResponseClass ||
                    R7Json.String(result, "expected_code", 1, 256) != expectation.ResultCode ||
                    R7Json.String(result, "expected_response_class", 1, 256) != expectation.ResponseClass ||
                    R7Json.String(result, "expected_terminal_classification", 1, 256) != expectation.Classification ||
                    R7Json.String(result, "signer_derived_terminal_classification", 1, 256) != expectation.Classification ||
                    R7Json.String(result, "expectation_definition_sha256", 64, 64) != R7Hash.Bytes(R7Json.Encode(expectation.Raw))) throw new InvalidDataException("CASE_RESULT_SEMANTICS_INVALID");
                if (definition.CaseId != caseId) throw new InvalidDataException("CASE_AUTHORITY_MISMATCH");
            }
            if (requireComplete)
            {
                string excludedCase = requiredRunKind == "CANDIDATE" ? "POS-006" : "POS-005";
                foreach (string governedCaseId in authority.CaseIds)
                {
                    if (governedCaseId == excludedCase)
                    {
                        if (seen.Contains(governedCaseId)) throw new InvalidDataException("RUN_GRAPH_EXCLUDED_META_CASE_PRESENT");
                    }
                    else if (!seen.Contains(governedCaseId)) throw new InvalidDataException("RUN_GRAPH_GOVERNED_CASE_MISSING:" + governedCaseId);
                }
                if (!currentFound || seen.Count != authority.CaseIds.Length - 1) throw new InvalidDataException("OUTER_SUBMISSION_CASE_OR_COUNT_INVALID");
            }
            else if (caseSubmissionProbe)
            {
                if (seen.Contains("POS-005") || seen.Contains("POS-006") || seen.Count != authority.CaseIds.Length - 2) throw new InvalidDataException("CASE_SUBMISSION_PROBE_GRAPH_INVALID");
                foreach (string governedCaseId in authority.CaseIds) if (governedCaseId != "POS-005" && governedCaseId != "POS-006" && !seen.Contains(governedCaseId)) throw new InvalidDataException("CASE_SUBMISSION_PROBE_CASE_MISSING:" + governedCaseId);
            }
            else if (currentFound || seen.Count != caseCount) throw new InvalidDataException("BOOTSTRAP_GRAPH_CASE_COUNT_INVALID");
        }

        private static void VerifyInteractionGraph(SortedDictionary<string, object> result, R7ObjectStore objects, R7EvidenceStore evidenceStore, R7UpgradeVersionBinding version, R7CaseDefinition definition)
        {
            string baseRole = R7Json.String(result, "effective_base_caller_role", 1, 64);
            string expectedBaseRole = definition.Driver == "PUBLIC_VERIFIER" ? "PUBLIC_VERIFIER" :
                definition.CaseId == "EXP-002" || definition.CaseId == "EXP-004" ? "OBSERVATION" :
                definition.CaseId == "PRI-002" || definition.CaseId == "SEM-007" ? "COMPARATOR" :
                definition.CaseId == "EXP-001" || definition.CaseId == "PRI-006" || definition.Driver == "SEMANTIC_PROBE" || definition.CaseId.StartsWith("SEM-", StringComparison.Ordinal) || definition.Driver == "ACL_PROBE" || definition.Driver == "TOKEN_PROBE" || definition.Driver == "SOURCE_PROBE" || definition.Driver == "RECOVERY_HARNESS" ? "EXECUTION" : "ADVERSARIAL_HARNESS";
            if (!String.Equals(baseRole, expectedBaseRole, StringComparison.Ordinal)) throw new InvalidDataException("PUBLIC_BASE_CALLER_ROLE_INVALID");
            bool parserCase = definition.Driver == "RAW_FRAME";
            R7PublicInteraction baseInteraction = ResolveInteraction(objects, evidenceStore, R7Json.String(result, "base_capture_identity", 64, 64), R7Json.String(result, "base_interaction_identity", 64, 64), version, baseRole, parserCase);
            R7PublicInteraction eventInteraction = ResolveInteraction(objects, evidenceStore, R7Json.String(result, "event_capture_identity", 64, 64), null, version, "EXECUTION", false);
            R7PublicInteraction observationInteraction = ResolveInteraction(objects, evidenceStore, R7Json.String(result, "observation_capture_identity", 64, 64), null, version, "OBSERVATION", false);
            R7PublicInteraction comparatorInteraction = ResolveInteraction(objects, evidenceStore, R7Json.String(result, "comparator_capture_identity", 64, 64), null, version, "COMPARATOR", false);

            if (R7Json.String(eventInteraction.Request, "operation", 1, 128) != "SUBMIT_EXECUTION_EVIDENCE" ||
                R7Json.String(observationInteraction.Request, "operation", 1, 128) != "SUBMIT_OBSERVATION_EVIDENCE" ||
                R7Json.String(comparatorInteraction.Request, "operation", 1, 128) != "SUBMIT_COMPARATOR_EVIDENCE") throw new InvalidDataException("PUBLIC_EVIDENCE_STAGE_OPERATION_INVALID");
            SortedDictionary<string, object> eventEnvelope = R7Json.Child(eventInteraction.Request, "payload");
            SortedDictionary<string, object> observationEnvelope = R7Json.Child(observationInteraction.Request, "payload");
            SortedDictionary<string, object> comparatorEnvelope = R7Json.Child(comparatorInteraction.Request, "payload");
            R7Json.ExactKeys(eventEnvelope, "evidence", "evidence_kind");
            R7Json.ExactKeys(observationEnvelope, "evidence", "evidence_kind");
            R7Json.ExactKeys(comparatorEnvelope, "evidence", "evidence_kind");
            if (R7Json.String(eventEnvelope, "evidence_kind", 1, 64) != "EVENT" || R7Json.String(observationEnvelope, "evidence_kind", 1, 64) != "OBSERVATION" || R7Json.String(comparatorEnvelope, "evidence_kind", 1, 64) != "COMPARISON") throw new InvalidDataException("PUBLIC_EVIDENCE_STAGE_KIND_INVALID");
            SortedDictionary<string, object> eventPayload = R7Json.Child(eventEnvelope, "evidence");
            SortedDictionary<string, object> observationPayload = R7Json.Child(observationEnvelope, "evidence");
            SortedDictionary<string, object> comparatorPayload = R7Json.Child(comparatorEnvelope, "evidence");
            if (R7Json.String(eventPayload, "base_interaction_identity", 64, 64) != baseInteraction.InteractionIdentity ||
                R7Json.String(observationPayload, "base_interaction_identity", 64, 64) != baseInteraction.InteractionIdentity ||
                R7Json.String(comparatorPayload, "base_interaction_identity", 64, 64) != baseInteraction.InteractionIdentity ||
                R7Json.String(comparatorPayload, "event_interaction_identity", 64, 64) != eventInteraction.InteractionIdentity ||
                R7Json.String(comparatorPayload, "observation_interaction_identity", 64, 64) != observationInteraction.InteractionIdentity) throw new InvalidDataException("PUBLIC_EVIDENCE_GRAPH_REFERENCE_INVALID");
            string actualStatus = R7Json.String(baseInteraction.Response, "status", 1, 64);
            string actualCode = actualStatus == "COMPLETE" ? R7Json.String(baseInteraction.Response, "result_code", 1, 256) : R7Json.String(baseInteraction.Response, "error_code", 1, 256);
            if (R7Json.String(result, "actual_status", 1, 256) != actualStatus || R7Json.String(result, "actual_code", 1, 256) != actualCode) throw new InvalidDataException("PUBLIC_CASE_RESULT_RAW_RESPONSE_MISMATCH");
            SortedDictionary<string, object> eventValue = R7Json.Child(eventPayload, "event");
            SortedDictionary<string, object> observationValue = R7Json.Child(observationPayload, "observation");
            if (R7Json.String(eventValue, "request_frame_sha256", 64, 64) != R7Json.String(baseInteraction.Capture, "request_frame_sha256", 64, 64) ||
                R7Json.String(eventValue, "response_frame_sha256", 64, 64) != R7Json.String(baseInteraction.Capture, "response_frame_sha256", 64, 64) ||
                R7Json.String(observationValue, "actual_status", 1, 64) != actualStatus ||
                R7Json.String(observationValue, "actual_code", 1, 256) != actualCode ||
                R7Json.Integer(observationValue, "ledger_sequence_before", 0, Int64.MaxValue) != R7Json.Integer(baseInteraction.Capture, "ledger_sequence_before", 0, Int64.MaxValue) ||
                R7Json.Integer(observationValue, "ledger_sequence_after", 0, Int64.MaxValue) != R7Json.Integer(baseInteraction.Capture, "ledger_sequence_after", 0, Int64.MaxValue)) throw new InvalidDataException("PUBLIC_EVENT_OR_OBSERVATION_RAW_MISMATCH");
            byte[] eventRawRequest = Convert.FromBase64String(R7Json.String(eventPayload, "raw_request_frame", 1, R7Fixed.MaximumEncodedCaptureChars));
            byte[] eventRawResponse = Convert.FromBase64String(R7Json.String(eventPayload, "raw_response_frame", 1, R7Fixed.MaximumEncodedFrameChars));
            byte[] observationRawRequest = Convert.FromBase64String(R7Json.String(observationPayload, "raw_request_frame", 1, R7Fixed.MaximumEncodedCaptureChars));
            byte[] observationRawResponse = Convert.FromBase64String(R7Json.String(observationPayload, "raw_response_frame", 1, R7Fixed.MaximumEncodedFrameChars));
            byte[] comparatorRawResponse = Convert.FromBase64String(R7Json.String(comparatorPayload, "raw_response_frame", 1, R7Fixed.MaximumEncodedFrameChars));
            string baseRequestHash = R7Json.String(baseInteraction.Capture, "request_frame_sha256", 64, 64);
            string baseResponseHash = R7Json.String(baseInteraction.Capture, "response_frame_sha256", 64, 64);
            if (R7Hash.Bytes(eventRawRequest) != baseRequestHash || R7Hash.Bytes(observationRawRequest) != baseRequestHash || R7Hash.Bytes(eventRawResponse) != baseResponseHash || R7Hash.Bytes(observationRawResponse) != baseResponseHash || R7Hash.Bytes(comparatorRawResponse) != baseResponseHash) throw new InvalidDataException("PUBLIC_STAGE_RAW_FRAME_INVALID");
            if (R7Json.String(comparatorPayload, "actual_status", 1, 64) != actualStatus || R7Json.String(comparatorPayload, "actual_code", 1, 256) != actualCode || R7Json.String(comparatorPayload, "case_id", 1, 128) != definition.CaseId) throw new InvalidDataException("PUBLIC_COMPARATOR_RAW_INPUT_MISMATCH");
        }

        private static R7PublicInteraction ResolveInteraction(R7ObjectStore objects, R7EvidenceStore evidenceStore, string captureIdentity, string expectedInteractionIdentity, R7UpgradeVersionBinding version, string role, bool allowInvalidRequest)
        {
            SortedDictionary<string, object> capture = objects.Get(captureIdentity);
            R7Json.ExactKeys(capture,
                "artifact_type", "caller", "concurrent_connection_count_at_receive", "connection_identity", "derivation", "interaction_identity",
                "ledger_root_after", "ledger_root_before", "ledger_sequence_after", "ledger_sequence_before", "protected_state_after", "protected_state_before",
                "protocol_error_code", "protocol_error_offset", "receive_time", "request_frame", "request_frame_sha256", "request_payload_sha256",
                "response_frame", "response_frame_sha256", "response_message", "schema_version", "server_derived_evidence");
            string interactionIdentity = R7Json.String(capture, "interaction_identity", 64, 64);
            if (!R7Hash.IsLowerSha256(interactionIdentity) || (expectedInteractionIdentity != null && interactionIdentity != expectedInteractionIdentity) ||
                R7Json.String(capture, "artifact_type", 1, 256) != "R7_SERVER_OBSERVED_OUTER_INTERACTION" ||
                R7Json.String(capture, "schema_version", 1, 128) != "1.0.0") throw new InvalidDataException("PUBLIC_INTERACTION_FIXED_IDENTITY_INVALID");
            R7InteractionEvidence mapping = evidenceStore.Resolve(interactionIdentity);
            if (mapping.CaptureIdentity != captureIdentity) throw new InvalidDataException("PUBLIC_INTERACTION_MAPPING_CAPTURE_INVALID");
            byte[] requestFrame;
            byte[] responseFrame;
            try
            {
                requestFrame = Convert.FromBase64String(R7Json.String(capture, "request_frame", 1, R7Fixed.MaximumEncodedCaptureChars));
                responseFrame = Convert.FromBase64String(R7Json.String(capture, "response_frame", 1, R7Fixed.MaximumEncodedFrameChars));
            }
            catch (FormatException) { throw new InvalidDataException("PUBLIC_INTERACTION_FRAME_ENCODING_INVALID"); }
            if (requestFrame.Length == 0 || requestFrame.Length > R7Fixed.MaximumCapturedFrameBytes || responseFrame.Length == 0 || responseFrame.Length > R7Fixed.MaximumFrameBytes ||
                R7Hash.Bytes(requestFrame) != R7Json.String(capture, "request_frame_sha256", 64, 64) ||
                R7Hash.Bytes(responseFrame) != R7Json.String(capture, "response_frame_sha256", 64, 64) ||
                !R7Hash.IsLowerSha256(R7Json.String(capture, "request_payload_sha256", 64, 64))) throw new InvalidDataException("PUBLIC_INTERACTION_RAW_FRAME_INVALID");
            SortedDictionary<string, object> response = R7Framing.Decode(responseFrame);
            if (R7Hash.Bytes(R7Json.Encode(response)) != R7Hash.Bytes(R7Json.Encode(R7Json.Child(capture, "response_message")))) throw new InvalidDataException("PUBLIC_INTERACTION_RESPONSE_MESSAGE_INVALID");
            SortedDictionary<string, object> request = null;
            if (!allowInvalidRequest) request = R7Framing.Decode(requestFrame);
            else
            {
                try { request = R7Framing.Decode(requestFrame); }
                catch (R7ProtocolException) { }
            }
            Guid connectionIdentity;
            DateTimeOffset receiveTime;
            if (!Guid.TryParseExact(R7Json.String(capture, "connection_identity", 36, 36), "D", out connectionIdentity) ||
                !DateTimeOffset.TryParseExact(R7Json.String(capture, "receive_time", 28, 28), "yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out receiveTime) ||
                !R7Hash.IsLowerSha256(R7Json.String(capture, "ledger_root_before", 64, 64)) || !R7Hash.IsLowerSha256(R7Json.String(capture, "ledger_root_after", 64, 64)) ||
                R7Json.Integer(capture, "ledger_sequence_after", 0, Int64.MaxValue) < R7Json.Integer(capture, "ledger_sequence_before", 0, Int64.MaxValue) ||
                R7Json.Integer(capture, "concurrent_connection_count_at_receive", 1, Int32.MaxValue) < 1) throw new InvalidDataException("PUBLIC_INTERACTION_PROCESS_OR_LEDGER_CONTEXT_INVALID");
            string derivation = R7Json.String(capture, "derivation", 1, 128);
            string protocolError = R7Json.String(capture, "protocol_error_code", 0, 256);
            long protocolOffset = R7Json.Integer(capture, "protocol_error_offset", -1, Int64.MaxValue);
            if (derivation != "SIGNER_SERVER_CAPTURE" && derivation != "STRICT_PARSER_REJECTION_BEFORE_DISPATCH") throw new InvalidDataException("PUBLIC_INTERACTION_DERIVATION_INVALID");
            if ((derivation == "SIGNER_SERVER_CAPTURE" && (protocolError.Length != 0 || protocolOffset != -1)) ||
                (derivation == "STRICT_PARSER_REJECTION_BEFORE_DISPATCH" && (protocolError.Length == 0 || protocolOffset < 0))) throw new InvalidDataException("PUBLIC_INTERACTION_PROTOCOL_CLASSIFICATION_INVALID");
            ValidateCallerForRole(R7Json.Child(capture, "caller"), version, role);
            ValidateProtectedState(R7Json.Child(capture, "protected_state_before"));
            ValidateProtectedState(R7Json.Child(capture, "protected_state_after"));
            R7Json.Child(capture, "server_derived_evidence");
            return new R7PublicInteraction { InteractionIdentity = interactionIdentity, Capture = capture, Request = request, Response = response };
        }

        private static void ValidateCallerForRole(SortedDictionary<string, object> caller, R7UpgradeVersionBinding version, string role)
        {
            ValidateCallerShape(caller);
            string expectedSid = role == "EXECUTION" ? R7Fixed.ExecutionSid : role == "OBSERVATION" ? R7Fixed.ObservationSid : role == "COMPARATOR" ? R7Fixed.ComparatorSid : role == "ADVERSARIAL_HARNESS" || role == "PUBLIC_VERIFIER" ? R7Fixed.OperatorSid : null;
            string componentSha;
            string componentFileIdentity;
            string componentPath;
            if (expectedSid == null || !version.ComponentSha256.TryGetValue(role, out componentSha) || !version.InstalledFileIdentities.TryGetValue(role, out componentFileIdentity) || !version.ComponentPaths.TryGetValue(role, out componentPath)) throw new InvalidDataException("PUBLIC_INTERACTION_ROLE_BINDING_MISSING");
            if (R7Json.String(caller, "user_sid", 1, 256) != expectedSid || R7Json.Boolean(caller, "contains_terminal_signer_sid") ||
                R7Json.String(caller, "process_sha256", 64, 64) != componentSha ||
                R7Json.String(caller, "process_file_identity", 1, 256) != componentFileIdentity ||
                R7Json.String(caller, "process_path", 3, 4096) != componentPath) throw new InvalidDataException("PUBLIC_INTERACTION_CALLER_BINARY_INVALID");
            foreach (object group in R7Json.Array(caller, "group_sids"))
            {
                string value = group as string;
                if (value == null || value == R7Fixed.TerminalSid) throw new InvalidDataException("PUBLIC_INTERACTION_CALLER_GROUP_INVALID");
            }
            foreach (object privilege in R7Json.Array(caller, "privileges")) if (privilege as string == null) throw new InvalidDataException("PUBLIC_INTERACTION_CALLER_PRIVILEGE_INVALID");
        }

        private static void ValidateProtectedState(SortedDictionary<string, object> state)
        {
            R7Json.ExactKeys(state, "authority_identity", "configuration_identity", "receipt_identity", "response_identity", "signer_process_id", "signer_process_instance_identity", "signer_process_start_time", "terminal_trust_identity", "upgrade_authorization_identity", "upgrade_trust_identity");
            foreach (string name in new string[] { "authority_identity", "configuration_identity", "receipt_identity", "response_identity", "signer_process_instance_identity", "terminal_trust_identity", "upgrade_authorization_identity", "upgrade_trust_identity" }) if (!R7Hash.IsLowerSha256(R7Json.String(state, name, 64, 64))) throw new InvalidDataException("PUBLIC_PROTECTED_STATE_IDENTITY_INVALID:" + name);
            DateTimeOffset processStart;
            if (R7Json.Integer(state, "signer_process_id", 1, Int64.MaxValue) < 1 || !DateTimeOffset.TryParseExact(R7Json.String(state, "signer_process_start_time", 28, 28), "yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out processStart)) throw new InvalidDataException("PUBLIC_PROTECTED_STATE_PROCESS_INVALID");
        }

        private static void ValidateObligationProof(SortedDictionary<string, object> proof, R7Expectation expectation, string caseId)
        {
            R7Json.ExactKeys(proof, "case_id", "evidence_obligations", "forbidden_effect_obligations", "required_effect_obligations", "restart_retry_obligation", "restart_retry_verified_by", "schema_version");
            if (R7Json.String(proof, "case_id", 1, 128) != caseId ||
                R7Json.String(proof, "schema_version", 1, 128) != "1.0.0" ||
                R7Json.String(proof, "restart_retry_obligation", 1, 1024) != expectation.RestartRetry ||
                R7Json.String(proof, "restart_retry_verified_by", 1, 1024).Length == 0) throw new InvalidDataException("OBLIGATION_PROOF_BINDING_INVALID");
            ValidateObligationRows(R7Json.Array(proof, "evidence_obligations"), expectation.RequiredEvidence, "EVIDENCE");
            ValidateObligationRows(R7Json.Array(proof, "required_effect_obligations"), expectation.RequiredEffects, "REQUIRED_EFFECT");
            ValidateObligationRows(R7Json.Array(proof, "forbidden_effect_obligations"), expectation.ForbiddenEffects, "FORBIDDEN_EFFECT");
        }

        private static void ValidateObligationRows(object[] rows, string[] expectedTokens, string kind)
        {
            if (rows.Length != expectedTokens.Length) throw new InvalidDataException("OBLIGATION_PROOF_COUNT_INVALID:" + kind);
            HashSet<string> seen = new HashSet<string>(StringComparer.Ordinal);
            foreach (object raw in rows)
            {
                SortedDictionary<string, object> row = RequireObject(raw);
                R7Json.ExactKeys(row, "basis", "satisfied", "token");
                string token = R7Json.String(row, "token", 1, 256);
                if (!R7Json.Boolean(row, "satisfied") || R7Json.String(row, "basis", 1, 1024).Length == 0 || !seen.Add(token)) throw new InvalidDataException("OBLIGATION_PROOF_ROW_INVALID:" + kind);
            }
            foreach (string token in expectedTokens) if (!seen.Contains(token)) throw new InvalidDataException("OBLIGATION_PROOF_TOKEN_MISSING:" + kind + ":" + token);
        }

        private static void VerifyReconciliationEvidence(SortedDictionary<string, object> receipt, R7ObjectStore objects, Dictionary<string, R7TransactionSnapshot> receiptTransactions, bool requireFull, int expectedFullCaseCount)
        {
            SortedDictionary<string, object> details = R7Json.Child(receipt, "details");
            R7Json.ExactKeys(details, "candidate_receipt_identity", "compared_case_count", "fresh_receipt_identity", "full_case_registry", "provenance_identity");
            bool full = R7Json.Boolean(details, "full_case_registry");
            if (expectedFullCaseCount < 1) throw new InvalidDataException("RECONCILIATION_EXPECTED_CASE_COUNT_INVALID");
            long compared = R7Json.Integer(details, "compared_case_count", 1, expectedFullCaseCount);
            if ((requireFull && (!full || compared != expectedFullCaseCount)) || (!requireFull && full) || !R7Hash.IsLowerSha256(R7Json.String(details, "provenance_identity", 64, 64))) throw new InvalidDataException("RECONCILIATION_DETAILS_INVALID");
            SortedDictionary<string, object> proof = objects.Get(R7Json.String(receipt, "evidence_identity", 64, 64));
            R7Json.ExactKeys(proof, "candidate_evidence_identity", "candidate_receipt_identity", "compared_case_count", "fresh_evidence_identity", "fresh_receipt_identity", "matched", "provenance_identity");
            if (!R7Json.Boolean(proof, "matched") || R7Json.Integer(proof, "compared_case_count", 1, expectedFullCaseCount) != compared ||
                R7Json.String(proof, "candidate_receipt_identity", 64, 64) != R7Json.String(details, "candidate_receipt_identity", 64, 64) ||
                R7Json.String(proof, "fresh_receipt_identity", 64, 64) != R7Json.String(details, "fresh_receipt_identity", 64, 64) ||
                R7Json.String(proof, "provenance_identity", 64, 64) != R7Json.String(details, "provenance_identity", 64, 64) ||
                !R7Hash.IsLowerSha256(R7Json.String(proof, "candidate_evidence_identity", 64, 64)) ||
                !R7Hash.IsLowerSha256(R7Json.String(proof, "fresh_evidence_identity", 64, 64))) throw new InvalidDataException("RECONCILIATION_EVIDENCE_INVALID");
            string candidate = R7Json.String(details, "candidate_receipt_identity", 64, 64);
            string fresh = R7Json.String(details, "fresh_receipt_identity", 64, 64);
            R7TransactionSnapshot candidateState;
            R7TransactionSnapshot freshState;
            if (!receiptTransactions.TryGetValue(candidate, out candidateState) || !receiptTransactions.TryGetValue(fresh, out freshState) ||
                (candidateState.State != "COMMITTED" && candidateState.State != "RESPONSE_AVAILABLE") ||
                (freshState.State != "COMMITTED" && freshState.State != "RESPONSE_AVAILABLE") ||
                candidateState.Operation != "SUBMIT_RUN_GRAPH" || freshState.Operation != "SUBMIT_RUN_GRAPH" || candidate == fresh) throw new InvalidDataException("RECONCILIATION_MEMBERSHIP_INVALID");
            if (candidateState.EvidenceIdentity != R7Json.String(proof, "candidate_evidence_identity", 64, 64) || freshState.EvidenceIdentity != R7Json.String(proof, "fresh_evidence_identity", 64, 64)) throw new InvalidDataException("RECONCILIATION_GRAPH_EVIDENCE_BINDING_INVALID");
        }

        private static SortedDictionary<string, object> RequireObject(object value)
        {
            SortedDictionary<string, object> result = value as SortedDictionary<string, object>;
            if (result == null) throw new InvalidDataException("OBJECT_REQUIRED");
            return result;
        }

        private static UpgradePublicPolicy LoadUpgradePolicy()
        {
            using (R7VerifiedFile file = R7SafeFile.Open(R7Fixed.UpgradePolicyPath, R7Fixed.UpgradePolicyPath, Path.GetDirectoryName(R7Fixed.UpgradePolicyPath), null, R7Fixed.SystemSid, null, null))
            {
                SortedDictionary<string, object> policy = R7Json.ParseCanonicalObject(file.Bytes);
                R7Json.ExactKeys(policy, "artifact_type", "bootstrap_authority", "dependency_manifest_sha256", "fixed_roots", "host_binding", "installer_script_sha256", "interface_version", "key_unique_name", "ledger_id", "old_interface_version", "old_policy_sha256", "old_service_binary_sha256", "operation_allowlist", "protocol_version", "public_certificate_sha256", "required_components", "revoked_component_sha256", "schema_version", "service_sid", "source_commit", "source_tree", "threat_model", "upgrade_client_sha256", "volume_identity");
                string ledgerId = R7Json.String(policy, "ledger_id", 64, 64);
                string clientSha = R7Json.String(policy, "upgrade_client_sha256", 64, 64);
                string volumeIdentity = R7Json.String(policy, "volume_identity", 8, 64);
                string dependencyManifest = R7Json.String(policy, "dependency_manifest_sha256", 64, 64);
                string installerScript = R7Json.String(policy, "installer_script_sha256", 64, 64);
                string oldBinary = R7Json.String(policy, "old_service_binary_sha256", 64, 64);
                string oldPolicy = R7Json.String(policy, "old_policy_sha256", 64, 64);
                string sourceCommit = R7Json.String(policy, "source_commit", 40, 40);
                string sourceTree = R7Json.String(policy, "source_tree", 40, 40);
                SortedDictionary<string, object> host = R7Json.Child(policy, "host_binding");
                R7Json.ExactKeys(host, "terminal_ledger_id", "terminal_service_sid");
                HashSet<string> operations = new HashSet<string>(StringComparer.Ordinal);
                foreach (object raw in R7Json.Array(policy, "operation_allowlist")) { string value = raw as string; if (value == null || !operations.Add(value)) throw new InvalidDataException("UPGRADE_PUBLIC_POLICY_OPERATION_INVALID"); }
                foreach (string required in new string[] { "ACTIVATE_TERMINAL_UPGRADE", "AUTHORIZE_TERMINAL_UPGRADE", "GET_ACTIVATION", "GET_AUTHORIZATION", "GET_UPGRADE_INTERACTION", "GET_UPGRADE_STATUS", "REVOKE_AUTHORIZATION" }) if (!operations.Contains(required)) throw new InvalidDataException("UPGRADE_PUBLIC_POLICY_OPERATION_MISSING");
                if (operations.Count != 7 || !R7Hash.IsLowerSha256(ledgerId) || !R7Hash.IsLowerSha256(clientSha) || !R7Hash.IsLowerSha256(dependencyManifest) || !R7Hash.IsLowerSha256(installerScript) || !R7Hash.IsLowerSha256(oldBinary) || !R7Hash.IsLowerSha256(oldPolicy) ||
                    !String.Equals(file.Measurement.VolumeIdentity, volumeIdentity, StringComparison.Ordinal) ||
                    R7Json.String(policy, "artifact_type", 1, 128) != "R7_SEPARATE_UPGRADE_AUTHORITY_POLICY" ||
                    R7Json.String(policy, "bootstrap_authority", 1, 256) != "EXPLICIT_R7_ARCHITECTURE_REMEDIATION_AUTHORIZATION" ||
                    R7Json.String(policy, "interface_version", 1, 64) != "1.0.0" || R7Json.String(policy, "protocol_version", 1, 64) != R7Fixed.ProtocolVersion ||
                    R7Json.String(policy, "schema_version", 1, 64) != "1.0.0" || R7Json.String(policy, "service_sid", 1, 256) != R7Fixed.UpgradeSid ||
                    R7Json.String(host, "terminal_ledger_id", 64, 64) != R7Fixed.LedgerId || R7Json.String(host, "terminal_service_sid", 1, 256) != R7Fixed.TerminalSid ||
                    !String.Equals(R7Json.String(policy, "public_certificate_sha256", 64, 64), R7BuildIdentity.UpgradePublicCertificateSha256, StringComparison.Ordinal)) throw new InvalidDataException("UPGRADE_PUBLIC_POLICY_INVALID");
                return new UpgradePublicPolicy
                {
                    DependencyManifestSha256 = dependencyManifest,
                    InstallerScriptSha256 = installerScript,
                    LedgerId = ledgerId,
                    OldBinarySha256 = oldBinary,
                    OldInterfaceVersion = R7Json.String(policy, "old_interface_version", 1, 128),
                    OldPolicySha256 = oldPolicy,
                    PolicySha256 = file.Measurement.Sha256,
                    SourceCommit = sourceCommit,
                    SourceTree = sourceTree,
                    UpgradeClientSha256 = clientSha,
                    VolumeIdentity = volumeIdentity
                };
            }
        }

        private static SortedDictionary<string, object> VerifyUpgradeGenesis(R7VersionedLedger ledger, UpgradePublicPolicy policy)
        {
            R7LedgerRecord genesis = ledger.FindSequence(1);
            if (genesis == null || !String.Equals(genesis.Operation, "UPGRADE_LEDGER_GENESIS", StringComparison.Ordinal) || !String.Equals(genesis.SubjectId, policy.LedgerId, StringComparison.Ordinal)) throw new InvalidDataException("UPGRADE_GENESIS_RECORD_INVALID");
            string binaryPath = Path.Combine(R7Fixed.UpgradeInstallRoot, "RandleTerminalUpgradeAuthority.exe");
            string binarySha256;
            using (R7VerifiedFile binary = R7SafeFile.Open(binaryPath, binaryPath, R7Fixed.UpgradeInstallRoot, null, R7Fixed.SystemSid, null, policy.VolumeIdentity)) binarySha256 = binary.Measurement.Sha256;
            string buildReceiptIdentity = R7BuildClosureVerifier.VerifyUpgradeAuthorityBuildReceipt(binarySha256, policy.PolicySha256, policy.DependencyManifestSha256, policy.UpgradeClientSha256, policy.InstallerScriptSha256, policy.SourceCommit, policy.SourceTree, policy.VolumeIdentity);
            string expectedContent = R7Hash.Bytes(R7Json.Encode(R7Json.Object(
                "binary_sha256", binarySha256,
                "build_receipt_sha256", buildReceiptIdentity,
                "policy_sha256", policy.PolicySha256,
                "public_key_identity", R7BuildIdentity.UpgradePublicCertificateSha256,
                "service_sid", R7Fixed.UpgradeSid)));
            if (!R7Hash.FixedTimeEquals(genesis.ContentAddress, expectedContent)) throw new InvalidDataException("UPGRADE_GENESIS_COMPONENT_BINDING_INVALID");
            return R7Json.Object(
                "binary_sha256", binarySha256,
                "build_receipt_sha256", buildReceiptIdentity,
                "genesis_entry_identity", genesis.EntryIdentity,
                "policy_sha256", policy.PolicySha256,
                "public_key_identity", R7BuildIdentity.UpgradePublicCertificateSha256,
                "status", "PASS");
        }

        private sealed class UpgradePublicPolicy
        {
            internal string DependencyManifestSha256;
            internal string InstallerScriptSha256;
            internal string LedgerId;
            internal string OldBinarySha256;
            internal string OldInterfaceVersion;
            internal string OldPolicySha256;
            internal string PolicySha256;
            internal string SourceCommit;
            internal string SourceTree;
            internal string UpgradeClientSha256;
            internal string VolumeIdentity;
        }
    }
}
