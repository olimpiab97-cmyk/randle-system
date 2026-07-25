using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Security;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Security.Principal;
using System.ServiceProcess;

namespace RandleAI.R7Remediation
{
    internal sealed class R7UpgradeComponentRule
    {
        internal string Role;
        internal string RelativePath;
        internal string FinalPath;
        internal string ExpectedSha256;
    }

    internal sealed class R7UpgradePolicy
    {
        internal string Sha256;
        internal string PublicCertificateSha256;
        internal string DependencyManifestSha256;
        internal string KeyUniqueName;
        internal string LedgerId;
        internal string VolumeIdentity;
        internal string OldBinarySha256;
        internal string OldPolicySha256;
        internal string OldInterface;
        internal string SourceCommit;
        internal string SourceTree;
        internal string InstallerScriptSha256;
        internal string UpgradeClientSha256;
        internal string[] RevokedHashes;
        internal Dictionary<string, R7UpgradeComponentRule> Components;

        internal static R7UpgradePolicy Load(string expectedPolicySha256, string expectedCertificateSha256)
        {
            using (R7VerifiedFile file = R7SafeFile.Open(R7Fixed.UpgradePolicyPath, R7Fixed.UpgradePolicyPath, Path.GetDirectoryName(R7Fixed.UpgradePolicyPath), expectedPolicySha256, R7Fixed.SystemSid, null, null))
            {
                SortedDictionary<string, object> raw = RequireObject(R7Json.Parse(file.Bytes));
                R7Json.ExactKeys(raw,
                    "artifact_type", "bootstrap_authority", "dependency_manifest_sha256", "fixed_roots", "host_binding", "installer_script_sha256", "interface_version", "key_unique_name", "ledger_id",
                    "old_interface_version", "old_policy_sha256", "old_service_binary_sha256", "operation_allowlist", "protocol_version",
                    "public_certificate_sha256", "required_components", "revoked_component_sha256", "schema_version", "service_sid", "source_commit", "source_tree", "threat_model", "upgrade_client_sha256", "volume_identity");
                if (!String.Equals(R7Json.String(raw, "artifact_type", 1, 256), "R7_SEPARATE_UPGRADE_AUTHORITY_POLICY", StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(raw, "service_sid", 1, 256), R7Fixed.UpgradeSid, StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(raw, "interface_version", 1, 128), "1.0.0", StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(raw, "protocol_version", 1, 64), R7Fixed.ProtocolVersion, StringComparison.Ordinal)) throw new R7ProtocolException("UPGRADE_POLICY_IDENTITY");
                string cert = Sha(raw, "public_certificate_sha256");
                if (!R7Hash.FixedTimeEquals(cert, expectedCertificateSha256)) throw new R7ProtocolException("UPGRADE_TRUST_BOOTSTRAP_MISMATCH");
                SortedDictionary<string, object> host = R7Json.Child(raw, "host_binding");
                R7Json.ExactKeys(host, "terminal_ledger_id", "terminal_service_sid");
                if (!String.Equals(R7Json.String(host, "terminal_ledger_id", 64, 64), R7Fixed.LedgerId, StringComparison.Ordinal) || !String.Equals(R7Json.String(host, "terminal_service_sid", 1, 256), R7Fixed.TerminalSid, StringComparison.Ordinal)) throw new R7ProtocolException("UPGRADE_HOST_BINDING");
                string[] operations = Strings(R7Json.Array(raw, "operation_allowlist"));
                foreach (string required in new string[] { "AUTHORIZE_TERMINAL_UPGRADE", "ACTIVATE_TERMINAL_UPGRADE", "GET_AUTHORIZATION", "GET_ACTIVATION", "GET_UPGRADE_INTERACTION", "GET_UPGRADE_STATUS", "REVOKE_AUTHORIZATION" }) if (Array.IndexOf(operations, required) < 0) throw new R7ProtocolException("UPGRADE_OPERATION_MISSING", required);
                string[] roots = Strings(R7Json.Array(raw, "fixed_roots"));
                foreach (string required in new string[] { R7Fixed.UpgradeInstallRoot, R7Fixed.UpgradeStateRoot, R7Fixed.TerminalInstallRoot, R7Fixed.TerminalStateRoot }) if (Array.IndexOf(roots, required) < 0) throw new R7ProtocolException("UPGRADE_ROOT_MISSING", required);
                Dictionary<string, R7UpgradeComponentRule> components = new Dictionary<string, R7UpgradeComponentRule>(StringComparer.Ordinal);
                foreach (object rawItem in R7Json.Array(raw, "required_components"))
                {
                    SortedDictionary<string, object> item = RequireObject(rawItem);
                    R7Json.ExactKeys(item, "final_path", "role", "sha256", "staging_relative_path");
                    R7UpgradeComponentRule rule = new R7UpgradeComponentRule
                    {
                        Role = R7Json.String(item, "role", 1, 256),
                        RelativePath = R7Json.String(item, "staging_relative_path", 1, 2048),
                        FinalPath = R7Json.String(item, "final_path", 3, 4096),
                        ExpectedSha256 = Sha(item, "sha256")
                    };
                    if (rule.RelativePath.IndexOf("..", StringComparison.Ordinal) >= 0 || Path.IsPathRooted(rule.RelativePath)) throw new R7ProtocolException("UPGRADE_RELATIVE_PATH");
                    if (components.ContainsKey(rule.Role)) throw new R7ProtocolException("DUPLICATE_UPGRADE_COMPONENT_ROLE");
                    components.Add(rule.Role, rule);
                }
                foreach (string role in new string[] { "TERMINAL_SIGNER", "EXECUTION", "OBSERVATION", "COMPARATOR", "PUBLIC_VERIFIER", "AUTHORITY_VERIFIER", "ADVERSARIAL_HARNESS", "STATIC_VERIFIER", "TERMINAL_POLICY", "DEPENDENCY_MANIFEST", "BUILD_RECEIPT", "INSTALLER_TOOL", "AUTHORITY_PACKAGE_MANIFEST" }) if (!components.ContainsKey(role)) throw new R7ProtocolException("UPGRADE_COMPONENT_MISSING", role);
                string[] revoked = Strings(R7Json.Array(raw, "revoked_component_sha256"));
                foreach (string hash in revoked) if (!R7Hash.IsLowerSha256(hash)) throw new R7ProtocolException("REVOKED_HASH_INVALID");
                return new R7UpgradePolicy
                {
                    Sha256 = file.Measurement.Sha256,
                    PublicCertificateSha256 = cert,
                    DependencyManifestSha256 = Sha(raw, "dependency_manifest_sha256"),
                    KeyUniqueName = R7Json.String(raw, "key_unique_name", 1, 512),
                    LedgerId = Sha(raw, "ledger_id"),
                    VolumeIdentity = R7Json.String(raw, "volume_identity", 8, 64),
                    OldBinarySha256 = Sha(raw, "old_service_binary_sha256"),
                    OldPolicySha256 = Sha(raw, "old_policy_sha256"),
                    OldInterface = R7Json.String(raw, "old_interface_version", 1, 128),
                    SourceCommit = R7Json.String(raw, "source_commit", 40, 40),
                    SourceTree = R7Json.String(raw, "source_tree", 40, 40),
                    InstallerScriptSha256 = Sha(raw, "installer_script_sha256"),
                    UpgradeClientSha256 = Sha(raw, "upgrade_client_sha256"),
                    RevokedHashes = revoked,
                    Components = components
                };
            }
        }

        private static string Sha(IDictionary<string, object> row, string name)
        {
            string value = R7Json.String(row, name, 64, 64);
            if (!R7Hash.IsLowerSha256(value)) throw new R7ProtocolException("SHA256_FORMAT", name);
            return value;
        }

        private static string[] Strings(object[] values)
        {
            string[] result = new string[values.Length];
            for (int i = 0; i < values.Length; i++) { result[i] = values[i] as string; if (result[i] == null) throw new R7ProtocolException("STRING_ARRAY_REQUIRED"); }
            return result;
        }

        private static SortedDictionary<string, object> RequireObject(object value)
        {
            SortedDictionary<string, object> result = value as SortedDictionary<string, object>;
            if (result == null) throw new R7ProtocolException("OBJECT_REQUIRED");
            return result;
        }
    }

    internal sealed class R7UpgradeProcessor : R7PipeProcessor
    {
        private readonly object sync = new object();
        private readonly R7UpgradePolicy policy;
        private readonly X509Certificate2 publicCertificate;
        private readonly RSA verifier;
        private readonly RSA signer;
        private readonly R7VerifiedMetadataFile signingKeyFile;
        private readonly R7VerifiedFile serviceBinaryFile;
        private readonly R7VersionedLedger ledger;
        private readonly R7ObjectStore objects;
        private readonly string binarySha256;
        private readonly string binaryFileIdentity;
        private readonly R7DependencyClosure dependencies;

        internal R7UpgradeProcessor()
        {
            string currentSid = WindowsIdentity.GetCurrent().User.Value;
            if (!String.Equals(currentSid, R7Fixed.UpgradeSid, StringComparison.Ordinal)) throw new SecurityException("UPGRADE_SERVICE_SID_MISMATCH");
            policy = R7UpgradePolicy.Load(R7BuildIdentity.UpgradePolicySha256, R7BuildIdentity.UpgradePublicCertificateSha256);
            if (!R7Hash.FixedTimeEquals(policy.DependencyManifestSha256, R7BuildIdentity.DependencyManifestSha256)) throw new SecurityException("UPGRADE_DEPENDENCY_MANIFEST_IDENTITY_MISMATCH");
            if (!String.Equals(policy.SourceCommit, R7BuildIdentity.SourceCommit, StringComparison.Ordinal) || !String.Equals(policy.SourceTree, R7BuildIdentity.SourceTree, StringComparison.Ordinal)) throw new SecurityException("UPGRADE_SOURCE_IDENTITY_MISMATCH");
            dependencies = new R7DependencyClosure(R7Fixed.UpgradeDependencyManifestPath, R7BuildIdentity.DependencyManifestSha256, R7Fixed.UpgradeInstallRoot);
            publicCertificate = R7Crypto.LoadPublicCertificate(R7Fixed.UpgradePublicCertificatePath, policy.PublicCertificateSha256, Path.GetDirectoryName(R7Fixed.UpgradePublicCertificatePath));
            verifier = System.Security.Cryptography.X509Certificates.RSACertificateExtensions.GetRSAPublicKey(publicCertificate);
            signingKeyFile = R7SafeFile.HoldMetadataFile(R7BuildIdentity.UpgradeKeyFilePath, R7BuildIdentity.UpgradeKeyFilePath, Path.GetDirectoryName(R7BuildIdentity.UpgradeKeyFilePath), R7BuildIdentity.UpgradeKeyFileOwnerSid, R7BuildIdentity.UpgradeKeyFileSecurityDescriptorSha256, R7BuildIdentity.UpgradeKeyFileVolumeIdentity, R7BuildIdentity.UpgradeKeyFileIdentity, R7BuildIdentity.UpgradeKeyFileLinkCount);
            signer = R7Crypto.LoadMachineSigner(policy.KeyUniqueName, 3072);
            string executable = Path.GetFullPath(Assembly.GetExecutingAssembly().Location);
            if (!String.Equals(executable, R7BuildIdentity.UpgradeBinaryPath, StringComparison.Ordinal)) throw new SecurityException("UPGRADE_BINARY_PATH_MISMATCH");
            serviceBinaryFile = R7SafeFile.Open(executable, executable, R7Fixed.UpgradeInstallRoot, null, R7Fixed.SystemSid, null, policy.VolumeIdentity);
            binarySha256 = serviceBinaryFile.Measurement.Sha256;
            binaryFileIdentity = serviceBinaryFile.Measurement.FileIdentity;
            string buildReceiptIdentity = R7BuildClosureVerifier.VerifyUpgradeAuthorityBuildReceipt(binarySha256, policy.Sha256, policy.DependencyManifestSha256, policy.UpgradeClientSha256, policy.InstallerScriptSha256, policy.SourceCommit, policy.SourceTree, policy.VolumeIdentity);
            objects = new R7ObjectStore(R7Fixed.UpgradeObjectRoot, R7Fixed.UpgradeSid, policy.VolumeIdentity);
            string genesis = R7Hash.Bytes(R7Json.Encode(R7Json.Object("binary_sha256", binarySha256, "build_receipt_sha256", buildReceiptIdentity, "policy_sha256", policy.Sha256, "public_key_identity", policy.PublicCertificateSha256, "service_sid", R7Fixed.UpgradeSid)));
            ledger = new R7VersionedLedger(R7Fixed.UpgradeLedgerRoot, policy.LedgerId, policy.PublicCertificateSha256, R7Fixed.UpgradeSid, signer, verifier, true, genesis);
            RecoverCheckpointIfRequired();
            dependencies.VerifyNoNewModules();
        }

        private void RecoverCheckpointIfRequired()
        {
            string reason = ledger.CheckpointRecoveryReason;
            if (String.IsNullOrEmpty(reason)) return;
            string checkpointPath = Path.Combine(R7Fixed.UpgradeLedgerRoot, "checkpoint.json");
            string priorIdentity = R7Fixed.ZeroHash;
            R7VerifiedFile checkpoint;
            if (R7SafeFile.TryOpen(checkpointPath, checkpointPath, R7Fixed.UpgradeLedgerRoot, null, null, null, policy.VolumeIdentity, out checkpoint))
            {
                using (checkpoint)
                {
                    priorIdentity = checkpoint.Measurement.Sha256;
                    string preservedPath = Path.Combine(R7Fixed.UpgradeRecoveryRoot, "checkpoint." + priorIdentity + ".preserved");
                    R7VerifiedFile existing;
                    if (R7SafeFile.TryOpen(preservedPath, preservedPath, R7Fixed.UpgradeRecoveryRoot, priorIdentity, R7Fixed.UpgradeSid, null, policy.VolumeIdentity, out existing)) existing.Dispose();
                    else R7DurableFile.CreateNew(preservedPath, checkpoint.Bytes);
                }
            }
            R7CheckpointArtifact[] pending = ledger.PendingCheckpointArtifacts;
            object[] pendingValues = new object[pending.Length];
            for (int index = 0; index < pending.Length; index++) pendingValues[index] = R7Json.Object("identity", pending[index].Identity, "name", pending[index].Name);
            string recoverySubject = R7Hash.Bytes(R7Json.Encode(R7Json.Object(
                "checkpoint_identity_before", priorIdentity,
                "pending_checkpoint_artifacts", pendingValues,
                "reason", reason)));
            R7LedgerRecord[] existingRecords = ledger.Find("UPGRADE_CHECKPOINT_RECOVERY_INTENT", recoverySubject);
            if (existingRecords.Length > 1) throw new InvalidDataException("UPGRADE_CHECKPOINT_RECOVERY_DUPLICATE");
            if (existingRecords.Length == 0)
            {
                long sequenceBefore = ledger.Sequence;
                string content = objects.Put(R7Json.Object(
                    "checkpoint_identity_before", priorIdentity,
                    "ledger_root_before", ledger.RootHash,
                    "ledger_sequence_before", sequenceBefore,
                    "pending_checkpoint_artifacts", pendingValues,
                    "reason", reason,
                    "recovery_subject", recoverySubject,
                    "recovery_target_sequence", checked(sequenceBefore + 1)));
                ledger.Append("UPGRADE_CHECKPOINT_RECOVERY_INTENT", Guid.NewGuid().ToString("D"), recoverySubject, content, "1.0.0");
            }
            if (pending.Length != 0) ledger.PreservePendingCheckpoints(R7Fixed.UpgradeRecoveryRoot);
            if (!String.IsNullOrEmpty(ledger.CheckpointRecoveryReason)) ledger.RecoverCheckpoint("1.0.0");
            if (!String.IsNullOrEmpty(ledger.CheckpointRecoveryReason) || ledger.CheckpointIdentity == R7Fixed.ZeroHash) throw new R7DurabilityUncertainException("UPGRADE_CHECKPOINT_RECOVERY_NOT_DURABLE", null);
        }

        internal override SortedDictionary<string, object> Process(R7RequestContext context, SortedDictionary<string, object> request)
        {
            dependencies.VerifyNoNewModules();
            try
            {
                R7Json.ExactKeys(request, "interface_version", "operation", "payload", "protocol_version", "request_identity");
            if (!String.Equals(R7Json.String(request, "interface_version", 1, 128), "1.0.0", StringComparison.Ordinal) || !String.Equals(R7Json.String(request, "protocol_version", 1, 64), R7Fixed.ProtocolVersion, StringComparison.Ordinal)) throw new R7ProtocolException("INTERFACE_VERSION_REJECTED");
            string operation = R7Json.String(request, "operation", 1, 128);
            string requestIdentity = CanonicalGuid(R7Json.String(request, "request_identity", 36, 36));
            SortedDictionary<string, object> payload = R7Json.Child(request, "payload");
            if (operation == "GET_UPGRADE_INTERACTION") { RequirePublic(context.Caller); return GetInteraction(payload); }
            if (operation == "GET_AUTHORIZATION" || operation == "GET_ACTIVATION") return DispatchReadOnly(context, operation, payload);
            lock (sync)
            {
                R7LedgerRecord[] priorRecords = ledger.Find("UPGRADE_INTERFACE_INTERACTION", requestIdentity);
                if (priorRecords.Length > 1) throw new R7ProtocolException("UPGRADE_INTERACTION_DUPLICATE");
                if (priorRecords.Length == 1)
                {
                    SortedDictionary<string, object> prior = objects.Get(priorRecords[0].ContentAddress);
                    if (!R7Hash.FixedTimeEquals(R7Json.String(prior, "request_frame_sha256", 64, 64), context.RequestFrameSha256)) throw new R7ProtocolException("REQUEST_IDENTITY_CONFLICT");
                    return R7Json.Child(prior, "response");
                }
                long sequenceBefore = ledger.Sequence;
                string rootBefore = ledger.RootHash;
                SortedDictionary<string, object> response;
                try { response = DispatchMutation(context, operation, requestIdentity, payload); }
                catch (R7ProtocolException exception) { response = R7PipeWindowsService.Rejection(exception.Code); }
                catch (SecurityException exception) { response = R7PipeWindowsService.Rejection(String.IsNullOrEmpty(exception.Message) ? "UPGRADE_CALLER_NOT_AUTHORIZED" : exception.Message); }
                byte[] responseFrame = R7Framing.Encode(response);
                string interactionIdentity = objects.Put(R7Json.Object(
                    "artifact_type", "R7_UPGRADE_AUTHORITY_SERVER_CAPTURED_INTERACTION",
                    "authority_ledger_root_after_dispatch", ledger.RootHash,
                    "authority_ledger_root_before", rootBefore,
                    "authority_ledger_sequence_after_dispatch", ledger.Sequence,
                    "authority_ledger_sequence_before", sequenceBefore,
                    "caller", context.Caller.ToJson(),
                    "operation", operation,
                    "request", request,
                    "request_frame", Convert.ToBase64String(context.RequestFrame),
                    "request_frame_sha256", context.RequestFrameSha256,
                    "request_identity", requestIdentity,
                    "response", response,
                    "response_frame", Convert.ToBase64String(responseFrame),
                    "response_frame_sha256", R7Hash.Bytes(responseFrame),
                    "schema_version", "1.0.0"));
                ledger.Append("UPGRADE_INTERFACE_INTERACTION", requestIdentity, requestIdentity, interactionIdentity, "1.0.0");
                    return response;
                }
            }
            finally { dependencies.VerifyNoNewModules(); }
        }

        private SortedDictionary<string, object> DispatchReadOnly(R7RequestContext context, string operation, SortedDictionary<string, object> payload)
        {
            if (operation == "GET_AUTHORIZATION") { RequirePublic(context.Caller); return GetRecord(payload, false); }
            if (operation == "GET_ACTIVATION") { RequirePublic(context.Caller); return GetRecord(payload, true); }
            throw new R7ProtocolException("OPERATION_NOT_ALLOWED");
        }

        private SortedDictionary<string, object> DispatchMutation(R7RequestContext context, string operation, string requestIdentity, SortedDictionary<string, object> payload)
        {
            if (operation == "GET_UPGRADE_STATUS") { RequirePublic(context.Caller); R7Json.ExactKeys(payload); return Status(); }
            if (operation == "AUTHORIZE_TERMINAL_UPGRADE") { RequireOperator(context.Caller); return Authorize(context, requestIdentity, payload); }
            if (operation == "ACTIVATE_TERMINAL_UPGRADE") { RequireTerminal(context.Caller); return Activate(context, requestIdentity, payload); }
            if (operation == "REVOKE_AUTHORIZATION") { RequireOperator(context.Caller); return Revoke(context, requestIdentity, payload); }
            throw new R7ProtocolException("OPERATION_NOT_ALLOWED");
        }

        public override void Dispose()
        {
            dependencies.Dispose();
            signer.Dispose();
            signingKeyFile.Dispose();
            serviceBinaryFile.Dispose();
            verifier.Dispose();
            publicCertificate.Dispose();
        }

        private SortedDictionary<string, object> Status()
        {
            SortedDictionary<string, object> value = R7PipeWindowsService.Success("UPGRADE_AUTHORITY_STATUS_RESOLVED");
            value.Add("binary_file_identity", binaryFileIdentity);
            value.Add("binary_sha256", binarySha256);
            value.Add("ledger_id", policy.LedgerId);
            value.Add("ledger_root", ledger.RootHash);
            value.Add("ledger_sequence", ledger.Sequence);
            value.Add("policy_sha256", policy.Sha256);
            value.Add("public_key_identity", policy.PublicCertificateSha256);
            value.Add("service_sid", R7Fixed.UpgradeSid);
            return value;
        }

        private SortedDictionary<string, object> Authorize(R7RequestContext context, string requestIdentity, SortedDictionary<string, object> payload)
        {
            lock (sync)
            {
                R7Json.ExactKeys(payload,
                    "build_receipt_sha256", "components", "dependency_manifest_sha256", "host_binding", "installer_identity", "new_interface_version",
                    "old_interface_version", "old_policy_sha256", "old_service_binary_sha256", "rollback_constraints", "source_commit",
                    "source_tree", "staging_root", "transition_nonce");
                string nonce = CanonicalGuid(R7Json.String(payload, "transition_nonce", 36, 36));
                string authorizationPath = Path.Combine(R7Fixed.UpgradeAuthorizationRoot, nonce + ".upgrade.json");
                string requestPayloadIdentity = R7Hash.Bytes(R7Json.Encode(payload));
                R7VerifiedFile priorAuthorization;
                if (R7SafeFile.TryOpen(authorizationPath, authorizationPath, R7Fixed.UpgradeAuthorizationRoot, null, R7Fixed.UpgradeSid, null, policy.VolumeIdentity, out priorAuthorization))
                {
                    priorAuthorization.Dispose();
                    return RecoverAuthorization(context, requestIdentity, requestPayloadIdentity, nonce, authorizationPath);
                }
                if (ledger.Find("UPGRADE_AUTHORIZATION_ISSUED", nonce).Length != 0) throw new R7ProtocolException("TRANSITION_NONCE_REPLAY");
                if (!String.Equals(R7Json.String(payload, "old_service_binary_sha256", 64, 64), policy.OldBinarySha256, StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(payload, "old_policy_sha256", 64, 64), policy.OldPolicySha256, StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(payload, "old_interface_version", 1, 128), policy.OldInterface, StringComparison.Ordinal)) throw new R7ProtocolException("OLD_COMPONENT_SET_MISMATCH");
                if (!String.Equals(R7Json.String(payload, "new_interface_version", 1, 128), R7Fixed.InterfaceVersion, StringComparison.Ordinal)) throw new R7ProtocolException("DOWNGRADE_NOT_AUTHORIZED");
                SortedDictionary<string, object> requestedHost = R7Json.Child(payload, "host_binding");
                R7Json.ExactKeys(requestedHost, "terminal_ledger_id", "terminal_service_sid", "volume_identity");
                if (!String.Equals(R7Json.String(requestedHost, "terminal_ledger_id", 64, 64), R7Fixed.LedgerId, StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(requestedHost, "terminal_service_sid", 1, 256), R7Fixed.TerminalSid, StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(requestedHost, "volume_identity", 8, 64), policy.VolumeIdentity, StringComparison.Ordinal)) throw new R7ProtocolException("HOST_BINDING_MISMATCH");
                string stagingRoot = Path.GetFullPath(R7Json.String(payload, "staging_root", 3, 4096));
                string expectedStagingRoot = Path.Combine(R7Fixed.UpgradeStagingRoot, nonce);
                if (!String.Equals(stagingRoot, expectedStagingRoot, StringComparison.Ordinal)) throw new R7ProtocolException("STAGING_ROOT_MISMATCH");
                R7SafeFile.MeasureDirectory(stagingRoot, expectedStagingRoot, R7Fixed.SystemSid, null, policy.VolumeIdentity);
                VerifyOldLiveSet();

                object[] componentRows = R7Json.Array(payload, "components");
                if (componentRows.Length != policy.Components.Count) throw new R7ProtocolException("INCOMPLETE_COMPONENT_SET");
                HashSet<string> seen = new HashSet<string>(StringComparer.Ordinal);
                List<object> measured = new List<object>();
                foreach (object rawItem in componentRows)
                {
                    SortedDictionary<string, object> item = RequireObject(rawItem);
                    R7Json.ExactKeys(item, "final_path", "role", "sha256", "staging_relative_path");
                    string role = R7Json.String(item, "role", 1, 256);
                    R7UpgradeComponentRule rule;
                    if (!policy.Components.TryGetValue(role, out rule) || !seen.Add(role)) throw new R7ProtocolException("UNAUTHORIZED_COMPONENT_SET");
                    string relative = R7Json.String(item, "staging_relative_path", 1, 2048);
                    string finalPath = R7Json.String(item, "final_path", 3, 4096);
                    if (!String.Equals(relative, rule.RelativePath, StringComparison.Ordinal) || !String.Equals(finalPath, rule.FinalPath, StringComparison.Ordinal)) throw new R7ProtocolException("COMPONENT_PATH_MISMATCH");
                    string claimedSha = R7Json.String(item, "sha256", 64, 64);
                    if (role == "TERMINAL_POLICY" && R7Hash.FixedTimeEquals(claimedSha, policy.OldPolicySha256)) throw new R7ProtocolException("POLICY_ROLLBACK");
                    if (Array.IndexOf(policy.RevokedHashes, claimedSha) >= 0) throw new R7ProtocolException("REVOKED_COMPONENT");
                    if (!R7Hash.FixedTimeEquals(claimedSha, rule.ExpectedSha256)) throw new R7ProtocolException("COMPONENT_SET_MISMATCH", role);
                    string absenceBoundary = finalPath.StartsWith(R7Fixed.TerminalInstallRoot + Path.DirectorySeparatorChar, StringComparison.Ordinal) ? Path.GetDirectoryName(R7Fixed.TerminalInstallRoot) : R7Fixed.TerminalStateRoot;
                    try { R7SafeFile.AssertAbsent(finalPath, finalPath, absenceBoundary); }
                    catch (R7ProtocolException exception) { throw new R7ProtocolException("AUTHORIZATION_NOT_PREINSTALL", role + "|" + exception.Code); }
                    string stagePath = Path.Combine(stagingRoot, relative.Replace('/', Path.DirectorySeparatorChar));
                    using (R7VerifiedFile file = R7SafeFile.Open(stagePath, stagePath, stagingRoot, claimedSha, R7Fixed.SystemSid, null, policy.VolumeIdentity))
                    {
                        measured.Add(R7Json.Object("file_identity", file.Measurement.FileIdentity, "final_path", finalPath, "final_path_preinstall_state", "ABSENT", "role", role, "sha256", file.Measurement.Sha256, "size", file.Measurement.Size, "staging_relative_path", relative));
                    }
                }
                if (seen.Count != policy.Components.Count) throw new R7ProtocolException("INCOMPLETE_COMPONENT_SET");
                string buildReceipt = R7Json.String(payload, "build_receipt_sha256", 64, 64);
                string dependencies = R7Json.String(payload, "dependency_manifest_sha256", 64, 64);
                if (!R7Hash.IsLowerSha256(buildReceipt) || !R7Hash.IsLowerSha256(dependencies)) throw new R7ProtocolException("BUILD_IDENTITY_INVALID");
                if (!R7Hash.FixedTimeEquals(dependencies, policy.DependencyManifestSha256)) throw new R7ProtocolException("DEPENDENCY_MANIFEST_SUBSTITUTION");
                VerifyComponentHash(measured, "BUILD_RECEIPT", buildReceipt);
                VerifyComponentHash(measured, "DEPENDENCY_MANIFEST", dependencies);
                SortedDictionary<string, object> installer = R7Json.Child(payload, "installer_identity");
                R7Json.ExactKeys(installer, "executable_sha256", "script_sha256");
                string installerExecutable = R7Json.String(installer, "executable_sha256", 64, 64);
                string installerScript = R7Json.String(installer, "script_sha256", 64, 64);
                if (!R7Hash.IsLowerSha256(installerExecutable) || !R7Hash.IsLowerSha256(installerScript)) throw new R7ProtocolException("INSTALLER_IDENTITY_INVALID");
                if (!R7Hash.FixedTimeEquals(installerExecutable, policy.UpgradeClientSha256) || !R7Hash.FixedTimeEquals(installerScript, policy.InstallerScriptSha256)) throw new R7ProtocolException("INSTALLER_NOT_GOVERNED");
                if (!R7Hash.FixedTimeEquals(context.Caller.ProcessSha256, installerExecutable)) throw new R7ProtocolException("INSTALLER_EXECUTABLE_IDENTITY_MISMATCH");
                if (R7Json.String(payload, "rollback_constraints", 1, 4096) != "PRESERVE_LEDGER_CONTINUITY;PRESERVE_ALL_HISTORICAL_EVIDENCE;REQUIRE_SIGNED_ROLLBACK_AUTHORIZATION;NO_V1_OR_REJECTED_V3_DOWNGRADE") throw new R7ProtocolException("ROLLBACK_CONSTRAINTS_INVALID");
                string installerStagePath = Path.Combine(stagingRoot, "installer", "install_authorized_transition.ps1");
                using (R7VerifiedFile installerFile = R7SafeFile.Open(installerStagePath, installerStagePath, stagingRoot, installerScript, R7Fixed.SystemSid, null, policy.VolumeIdentity)) { }
                string sourceCommit = R7Json.String(payload, "source_commit", 40, 40);
                string sourceTree = R7Json.String(payload, "source_tree", 40, 40);
                if (!String.Equals(sourceCommit, policy.SourceCommit, StringComparison.Ordinal) || !String.Equals(sourceTree, policy.SourceTree, StringComparison.Ordinal)) throw new R7ProtocolException("SOURCE_IDENTITY_MISMATCH");
                string verificationObjectIdentity = objects.Put(R7Json.Object(
                    "artifact_type", "R7_UPGRADE_AUTHORIZATION_RAW_REQUEST_EVIDENCE",
                    "measured_components", measured.ToArray(),
                    "request_frame", Convert.ToBase64String(context.RequestFrame),
                    "request_frame_sha256", context.RequestFrameSha256,
                    "request_identity", requestIdentity,
                    "request_payload_identity", requestPayloadIdentity,
                    "schema_version", "1.0.0",
                    "transition_nonce", nonce));
                long activationSequence = NextActivationSequence();
                SortedDictionary<string, object> authorizationPayload = R7Json.Object(
                    "activation_sequence", activationSequence,
                    "authorization_time", DateTimeOffset.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture),
                    "authority_class", "TERMINAL_UPGRADE_AUTHORIZATION",
                    "build_receipt_sha256", buildReceipt,
                    "components", measured.ToArray(),
                    "dependency_manifest_sha256", dependencies,
                    "host_binding", R7Json.Object("terminal_ledger_id", R7Fixed.LedgerId, "terminal_service_sid", R7Fixed.TerminalSid, "volume_identity", policy.VolumeIdentity),
                    "installer_identity", installer,
                    "new_interface_version", R7Fixed.InterfaceVersion,
                    "old_interface_version", policy.OldInterface,
                    "old_policy_sha256", policy.OldPolicySha256,
                    "old_service_binary_sha256", policy.OldBinarySha256,
                    "operation", "AUTHORIZE_TERMINAL_UPGRADE",
                    "request_frame_sha256", context.RequestFrameSha256,
                    "request_identity", requestIdentity,
                    "request_payload_identity", requestPayloadIdentity,
                    "revocation_state", "ACTIVE",
                    "rollback_constraints", R7Json.String(payload, "rollback_constraints", 1, 4096),
                    "schema_version", "1.0.0",
                    "source_commit", sourceCommit,
                    "source_tree", sourceTree,
                    "staging_root", stagingRoot,
                    "transition_nonce", nonce,
                    "verification_object_identity", verificationObjectIdentity);
                byte[] bytes = R7Json.Encode(R7Crypto.Envelope(authorizationPayload, policy.PublicCertificateSha256, signer));
                string identity = R7Hash.Bytes(bytes);
                R7DurableFile.CreateNew(authorizationPath, bytes);
                R7LedgerAppend append = ledger.Append("UPGRADE_AUTHORIZATION_ISSUED", Guid.NewGuid().ToString("D"), nonce, identity, "1.0.0");
                return AuthorizationResponse(authorizationPayload, identity, authorizationPath, append.Record);
            }
        }

        private SortedDictionary<string, object> Activate(R7RequestContext context, string requestIdentity, SortedDictionary<string, object> payload)
        {
            lock (sync)
            {
                R7Json.ExactKeys(payload, "authorization_identity", "transition_nonce");
                string nonce = CanonicalGuid(R7Json.String(payload, "transition_nonce", 36, 36));
                string claimedIdentity = R7Json.String(payload, "authorization_identity", 64, 64);
                string activationPath = Path.Combine(R7Fixed.UpgradeActivationRoot, nonce + ".activation.json");
                string requestPayloadIdentity = R7Hash.Bytes(R7Json.Encode(payload));
                R7VerifiedFile priorActivation;
                if (R7SafeFile.TryOpen(activationPath, activationPath, R7Fixed.UpgradeActivationRoot, null, R7Fixed.UpgradeSid, null, policy.VolumeIdentity, out priorActivation))
                {
                    priorActivation.Dispose();
                    return RecoverActivation(context, requestIdentity, requestPayloadIdentity, nonce, claimedIdentity, activationPath);
                }
                string authorizationPath = Path.Combine(R7Fixed.UpgradeAuthorizationRoot, nonce + ".upgrade.json");
                SortedDictionary<string, object> authorization;
                string authorizationIdentity;
                using (R7VerifiedFile file = R7SafeFile.Open(authorizationPath, authorizationPath, R7Fixed.UpgradeAuthorizationRoot, claimedIdentity, R7Fixed.UpgradeSid, null, policy.VolumeIdentity))
                {
                    authorizationIdentity = file.Measurement.Sha256;
                    authorization = R7Crypto.VerifyEnvelope(file.Bytes, policy.PublicCertificateSha256, verifier);
                }
                R7LedgerRecord[] issued = ledger.Find("UPGRADE_AUTHORIZATION_ISSUED", nonce);
                if (issued.Length != 1 || !String.Equals(issued[0].ContentAddress, authorizationIdentity, StringComparison.Ordinal) || ledger.Find("UPGRADE_ACTIVATED", nonce).Length != 0 || ledger.Find("UPGRADE_AUTHORIZATION_REVOKED", nonce).Length != 0) throw new R7ProtocolException("UPGRADE_AUTHORIZATION_STATE_INVALID");
                R7Json.ExactKeys(authorization, "activation_sequence", "authorization_time", "authority_class", "build_receipt_sha256", "components", "dependency_manifest_sha256", "host_binding", "installer_identity", "new_interface_version", "old_interface_version", "old_policy_sha256", "old_service_binary_sha256", "operation", "request_frame_sha256", "request_identity", "request_payload_identity", "revocation_state", "rollback_constraints", "schema_version", "source_commit", "source_tree", "staging_root", "transition_nonce", "verification_object_identity");
                if (!String.Equals(R7Json.String(authorization, "authority_class", 1, 128), "TERMINAL_UPGRADE_AUTHORIZATION", StringComparison.Ordinal) || !String.Equals(R7Json.String(authorization, "operation", 1, 128), "AUTHORIZE_TERMINAL_UPGRADE", StringComparison.Ordinal) || !String.Equals(R7Json.String(authorization, "transition_nonce", 36, 36), nonce, StringComparison.Ordinal) || !String.Equals(R7Json.String(authorization, "revocation_state", 1, 64), "ACTIVE", StringComparison.Ordinal)) throw new R7ProtocolException("UPGRADE_AUTHORIZATION_INVALID");
                List<object> installedComponents = new List<object>();
                HashSet<string> installedRoles = new HashSet<string>(StringComparer.Ordinal);
                string terminalSignerInstalledFileIdentity = String.Empty;
                string terminalSignerInstalledSha256 = String.Empty;
                string terminalSignerInstalledPath = String.Empty;
                foreach (object rawComponent in R7Json.Array(authorization, "components"))
                {
                    SortedDictionary<string, object> component = RequireObject(rawComponent);
                    R7Json.ExactKeys(component, "file_identity", "final_path", "final_path_preinstall_state", "role", "sha256", "size", "staging_relative_path");
                    string role = R7Json.String(component, "role", 1, 256);
                    if (!installedRoles.Add(role) || !String.Equals(R7Json.String(component, "final_path_preinstall_state", 1, 64), "ABSENT", StringComparison.Ordinal)) throw new R7ProtocolException("UPGRADE_AUTHORIZATION_COMPONENT_INVALID");
                    string finalPath = R7Json.String(component, "final_path", 3, 4096);
                    string expectedSha = R7Json.String(component, "sha256", 64, 64);
                    string root = finalPath.StartsWith(R7Fixed.TerminalInstallRoot + Path.DirectorySeparatorChar, StringComparison.Ordinal) ? R7Fixed.TerminalInstallRoot : R7Fixed.RemediationRoot;
                    using (R7VerifiedFile installed = R7SafeFile.Open(finalPath, finalPath, root, expectedSha, R7Fixed.SystemSid, null, policy.VolumeIdentity))
                    {
                        if (role == "TERMINAL_SIGNER")
                        {
                            terminalSignerInstalledFileIdentity = installed.Measurement.FileIdentity;
                            terminalSignerInstalledSha256 = installed.Measurement.Sha256;
                            terminalSignerInstalledPath = installed.Measurement.CanonicalPath;
                        }
                        installedComponents.Add(R7Json.Object(
                            "canonical_path", installed.Measurement.CanonicalPath,
                            "creation_time", installed.Measurement.CreationTime,
                            "file_identity", installed.Measurement.FileIdentity,
                            "final_nt_path", installed.Measurement.FinalNtPath,
                            "hard_link_count", (long)installed.Measurement.LinkCount,
                            "owner_sid", installed.Measurement.OwnerSid,
                            "role", role,
                            "security_descriptor_sha256", installed.Measurement.SecurityDescriptorSha256,
                            "sha256", installed.Measurement.Sha256,
                            "size", installed.Measurement.Size,
                            "streams", installed.Measurement.Streams,
                            "volume_identity", installed.Measurement.VolumeIdentity));
                    }
                }
                if (installedRoles.Count != R7Json.Array(authorization, "components").Length) throw new R7ProtocolException("UPGRADE_INSTALLED_COMPONENT_SET_INCOMPLETE");
                if (String.IsNullOrEmpty(terminalSignerInstalledFileIdentity) ||
                    !String.Equals(context.Caller.ProcessPath, terminalSignerInstalledPath, StringComparison.Ordinal) ||
                    !R7Hash.FixedTimeEquals(context.Caller.ProcessSha256, terminalSignerInstalledSha256) ||
                    !String.Equals(context.Caller.ProcessFileIdentity, terminalSignerInstalledFileIdentity, StringComparison.Ordinal)) throw new R7ProtocolException("UPGRADE_ACTIVATION_CALLER_COMPONENT_MISMATCH");
                List<object> authorityDirectories = new List<object>();
                foreach (KeyValuePair<string, string> expectedDirectory in R7Fixed.AuthorityDirectories())
                {
                    SortedDictionary<string, object> measuredDirectory = R7SafeFile.MeasureDirectory(expectedDirectory.Value, expectedDirectory.Value, R7Fixed.SystemSid, null, policy.VolumeIdentity).ToJson();
                    measuredDirectory.Add("role", expectedDirectory.Key);
                    authorityDirectories.Add(measuredDirectory);
                }
                SortedDictionary<string, object> activationPayload = R7Json.Object(
                    "activation_sequence", R7Json.Integer(authorization, "activation_sequence", 1, Int64.MaxValue),
                    "activation_time", DateTimeOffset.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture),
                    "authority_directories", authorityDirectories.ToArray(),
                    "authority_class", "TERMINAL_UPGRADE_ACTIVATION",
                    "authorization_identity", authorizationIdentity,
                    "caller", context.Caller.ToJson(),
                    "installed_components", installedComponents.ToArray(),
                    "new_interface_version", R7Fixed.InterfaceVersion,
                    "operation", "ACTIVATE_TERMINAL_UPGRADE",
                    "request_frame_sha256", context.RequestFrameSha256,
                    "request_identity", requestIdentity,
                    "request_payload_identity", requestPayloadIdentity,
                    "schema_version", "1.0.0",
                    "transition_nonce", nonce);
                byte[] activationBytes = R7Json.Encode(R7Crypto.Envelope(activationPayload, policy.PublicCertificateSha256, signer));
                string activationIdentity = R7Hash.Bytes(activationBytes);
                R7DurableFile.CreateNew(activationPath, activationBytes);
                R7LedgerAppend append = ledger.Append("UPGRADE_ACTIVATED", Guid.NewGuid().ToString("D"), nonce, activationIdentity, "1.0.0");
                return ActivationResponse(activationPayload, activationIdentity, append.Record);
            }
        }

        private SortedDictionary<string, object> Revoke(R7RequestContext context, string requestIdentity, SortedDictionary<string, object> payload)
        {
            lock (sync)
            {
                R7Json.ExactKeys(payload, "reason", "transition_nonce");
                string nonce = CanonicalGuid(R7Json.String(payload, "transition_nonce", 36, 36));
                string requestPayloadIdentity = R7Hash.Bytes(R7Json.Encode(payload));
                R7LedgerRecord[] existing = ledger.Find("UPGRADE_AUTHORIZATION_REVOKED", nonce);
                if (existing.Length > 1) throw new R7ProtocolException("UPGRADE_REVOCATION_DUPLICATE");
                if (existing.Length == 1)
                {
                    SortedDictionary<string, object> prior = objects.Get(existing[0].ContentAddress);
                    R7Json.ExactKeys(prior, "operation", "reason", "request_frame_sha256", "request_identity", "request_payload_identity", "schema_version", "transition_nonce");
                    if (R7Json.String(prior, "request_identity", 36, 36) != requestIdentity ||
                        R7Json.String(prior, "request_frame_sha256", 64, 64) != context.RequestFrameSha256 ||
                        R7Json.String(prior, "request_payload_identity", 64, 64) != requestPayloadIdentity) throw new R7ProtocolException("CONFLICTING_UPGRADE_REVOCATION_RETRY");
                    return RevocationResponse(prior, existing[0].ContentAddress, existing[0]);
                }
                if (ledger.Find("UPGRADE_AUTHORIZATION_ISSUED", nonce).Length != 1 || ledger.Find("UPGRADE_ACTIVATED", nonce).Length != 0) throw new R7ProtocolException("UPGRADE_AUTHORIZATION_STATE_INVALID");
                SortedDictionary<string, object> revocation = R7Json.Object(
                    "operation", "REVOKE_AUTHORIZATION",
                    "reason", R7Json.String(payload, "reason", 1, 2048),
                    "request_frame_sha256", context.RequestFrameSha256,
                    "request_identity", requestIdentity,
                    "request_payload_identity", requestPayloadIdentity,
                    "schema_version", "1.0.0",
                    "transition_nonce", nonce);
                string identity = objects.Put(revocation);
                R7LedgerAppend append = ledger.Append("UPGRADE_AUTHORIZATION_REVOKED", Guid.NewGuid().ToString("D"), nonce, identity, "1.0.0");
                return RevocationResponse(revocation, identity, append.Record);
            }
        }

        private SortedDictionary<string, object> RecoverAuthorization(R7RequestContext context, string requestIdentity, string requestPayloadIdentity, string nonce, string path)
        {
            SortedDictionary<string, object> authorization;
            string identity;
            using (R7VerifiedFile file = R7SafeFile.Open(path, path, R7Fixed.UpgradeAuthorizationRoot, null, R7Fixed.UpgradeSid, null, policy.VolumeIdentity))
            {
                identity = file.Measurement.Sha256;
                authorization = R7Crypto.VerifyEnvelope(file.Bytes, policy.PublicCertificateSha256, verifier);
            }
            R7Json.ExactKeys(authorization, "activation_sequence", "authorization_time", "authority_class", "build_receipt_sha256", "components", "dependency_manifest_sha256", "host_binding", "installer_identity", "new_interface_version", "old_interface_version", "old_policy_sha256", "old_service_binary_sha256", "operation", "request_frame_sha256", "request_identity", "request_payload_identity", "revocation_state", "rollback_constraints", "schema_version", "source_commit", "source_tree", "staging_root", "transition_nonce", "verification_object_identity");
            if (R7Json.String(authorization, "operation", 1, 128) != "AUTHORIZE_TERMINAL_UPGRADE" ||
                R7Json.String(authorization, "transition_nonce", 36, 36) != nonce ||
                R7Json.String(authorization, "request_identity", 36, 36) != requestIdentity ||
                R7Json.String(authorization, "request_frame_sha256", 64, 64) != context.RequestFrameSha256 ||
                R7Json.String(authorization, "request_payload_identity", 64, 64) != requestPayloadIdentity) throw new R7ProtocolException("CONFLICTING_UPGRADE_AUTHORIZATION_RETRY");
            string verificationIdentity = R7Json.String(authorization, "verification_object_identity", 64, 64);
            SortedDictionary<string, object> verification = objects.Get(verificationIdentity);
            R7Json.ExactKeys(verification, "artifact_type", "measured_components", "request_frame", "request_frame_sha256", "request_identity", "request_payload_identity", "schema_version", "transition_nonce");
            byte[] rawRequest = Convert.FromBase64String(R7Json.String(verification, "request_frame", 1, 100000));
            if (R7Json.String(verification, "artifact_type", 1, 256) != "R7_UPGRADE_AUTHORIZATION_RAW_REQUEST_EVIDENCE" ||
                R7Json.String(verification, "request_identity", 36, 36) != requestIdentity ||
                R7Json.String(verification, "request_payload_identity", 64, 64) != requestPayloadIdentity ||
                R7Json.String(verification, "request_frame_sha256", 64, 64) != context.RequestFrameSha256 ||
                R7Hash.Bytes(rawRequest) != context.RequestFrameSha256 ||
                R7Json.String(verification, "transition_nonce", 36, 36) != nonce) throw new R7ProtocolException("UPGRADE_REQUEST_EVIDENCE_MISMATCH");
            R7LedgerRecord record = RecoverPreparedRecord("UPGRADE_AUTHORIZATION_ISSUED", nonce, identity);
            return AuthorizationResponse(authorization, identity, path, record);
        }

        private SortedDictionary<string, object> RecoverActivation(R7RequestContext context, string requestIdentity, string requestPayloadIdentity, string nonce, string authorizationIdentity, string path)
        {
            SortedDictionary<string, object> activation;
            string identity;
            using (R7VerifiedFile file = R7SafeFile.Open(path, path, R7Fixed.UpgradeActivationRoot, null, R7Fixed.UpgradeSid, null, policy.VolumeIdentity))
            {
                identity = file.Measurement.Sha256;
                activation = R7Crypto.VerifyEnvelope(file.Bytes, policy.PublicCertificateSha256, verifier);
            }
            R7Json.ExactKeys(activation, "activation_sequence", "activation_time", "authority_class", "authority_directories", "authorization_identity", "caller", "installed_components", "new_interface_version", "operation", "request_frame_sha256", "request_identity", "request_payload_identity", "schema_version", "transition_nonce");
            if (R7Json.String(activation, "operation", 1, 128) != "ACTIVATE_TERMINAL_UPGRADE" ||
                R7Json.String(activation, "transition_nonce", 36, 36) != nonce ||
                R7Json.String(activation, "authorization_identity", 64, 64) != authorizationIdentity ||
                R7Json.String(activation, "request_identity", 36, 36) != requestIdentity ||
                R7Json.String(activation, "request_frame_sha256", 64, 64) != context.RequestFrameSha256 ||
                R7Json.String(activation, "request_payload_identity", 64, 64) != requestPayloadIdentity) throw new R7ProtocolException("CONFLICTING_UPGRADE_ACTIVATION_RETRY");
            R7LedgerRecord[] issued = ledger.Find("UPGRADE_AUTHORIZATION_ISSUED", nonce);
            if (issued.Length != 1 || issued[0].ContentAddress != authorizationIdentity || ledger.Find("UPGRADE_AUTHORIZATION_REVOKED", nonce).Length != 0) throw new R7ProtocolException("UPGRADE_AUTHORIZATION_STATE_INVALID");
            R7LedgerRecord record = RecoverPreparedRecord("UPGRADE_ACTIVATED", nonce, identity);
            return ActivationResponse(activation, identity, record);
        }

        private R7LedgerRecord RecoverPreparedRecord(string operation, string nonce, string contentIdentity)
        {
            R7LedgerRecord[] records = ledger.Find(operation, nonce);
            if (records.Length > 1) throw new R7ProtocolException("UPGRADE_LEDGER_DUPLICATE_STATE", operation);
            if (records.Length == 1)
            {
                if (records[0].ContentAddress != contentIdentity) throw new R7ProtocolException("UPGRADE_LEDGER_CONTENT_MISMATCH", operation);
                return records[0];
            }
            return ledger.Append(operation, Guid.NewGuid().ToString("D"), nonce, contentIdentity, "1.0.0").Record;
        }

        private static SortedDictionary<string, object> AuthorizationResponse(SortedDictionary<string, object> authorization, string identity, string path, R7LedgerRecord record)
        {
            SortedDictionary<string, object> response = R7PipeWindowsService.Success("UPGRADE_AUTHORIZED_PREINSTALL");
            response.Add("activation_sequence", R7Json.Integer(authorization, "activation_sequence", 1, Int64.MaxValue));
            response.Add("authorization_identity", identity);
            response.Add("authorization_path", path);
            response.Add("ledger_entry_identity", record.EntryIdentity);
            response.Add("ledger_sequence", record.Sequence);
            response.Add("transition_nonce", R7Json.String(authorization, "transition_nonce", 36, 36));
            response.Add("verification_object_identity", R7Json.String(authorization, "verification_object_identity", 64, 64));
            return response;
        }

        private static SortedDictionary<string, object> ActivationResponse(SortedDictionary<string, object> activation, string identity, R7LedgerRecord record)
        {
            SortedDictionary<string, object> response = R7PipeWindowsService.Success("UPGRADE_ACTIVATED");
            response.Add("activation_identity", identity);
            response.Add("activation_sequence", R7Json.Integer(activation, "activation_sequence", 1, Int64.MaxValue));
            response.Add("authorization_identity", R7Json.String(activation, "authorization_identity", 64, 64));
            response.Add("ledger_entry_identity", record.EntryIdentity);
            response.Add("ledger_sequence", record.Sequence);
            response.Add("transition_nonce", R7Json.String(activation, "transition_nonce", 36, 36));
            return response;
        }

        private static SortedDictionary<string, object> RevocationResponse(SortedDictionary<string, object> revocation, string identity, R7LedgerRecord record)
        {
            SortedDictionary<string, object> response = R7PipeWindowsService.Success("UPGRADE_AUTHORIZATION_REVOKED");
            response.Add("ledger_entry_identity", record.EntryIdentity);
            response.Add("ledger_sequence", record.Sequence);
            response.Add("revocation_identity", identity);
            response.Add("transition_nonce", R7Json.String(revocation, "transition_nonce", 36, 36));
            return response;
        }

        private SortedDictionary<string, object> GetInteraction(SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "request_identity");
            string requestIdentity = CanonicalGuid(R7Json.String(payload, "request_identity", 36, 36));
            R7LedgerRecord[] records = ledger.Find("UPGRADE_INTERFACE_INTERACTION", requestIdentity);
            if (records.Length != 1) throw new R7ProtocolException("UPGRADE_INTERACTION_UNRESOLVED");
            SortedDictionary<string, object> interaction = objects.Get(records[0].ContentAddress);
            R7Json.ExactKeys(interaction,
                "artifact_type", "authority_ledger_root_after_dispatch", "authority_ledger_root_before", "authority_ledger_sequence_after_dispatch",
                "authority_ledger_sequence_before", "caller", "operation", "request", "request_frame", "request_frame_sha256", "request_identity",
                "response", "response_frame", "response_frame_sha256", "schema_version");
            if (!String.Equals(R7Json.String(interaction, "artifact_type", 1, 256), "R7_UPGRADE_AUTHORITY_SERVER_CAPTURED_INTERACTION", StringComparison.Ordinal) ||
                !String.Equals(R7Json.String(interaction, "request_identity", 36, 36), requestIdentity, StringComparison.Ordinal)) throw new R7ProtocolException("UPGRADE_INTERACTION_SEMANTICS_INVALID");
            SortedDictionary<string, object> response = R7PipeWindowsService.Success("UPGRADE_INTERACTION_RESOLVED");
            response.Add("interaction", interaction);
            response.Add("interaction_identity", records[0].ContentAddress);
            response.Add("ledger_entry_identity", records[0].EntryIdentity);
            response.Add("ledger_sequence", records[0].Sequence);
            response.Add("request_identity", requestIdentity);
            return response;
        }

        private SortedDictionary<string, object> GetRecord(SortedDictionary<string, object> payload, bool activation)
        {
            R7Json.ExactKeys(payload, "transition_nonce");
            string nonce = CanonicalGuid(R7Json.String(payload, "transition_nonce", 36, 36));
            string path = Path.Combine(activation ? R7Fixed.UpgradeActivationRoot : R7Fixed.UpgradeAuthorizationRoot, nonce + (activation ? ".activation.json" : ".upgrade.json"));
            string root = activation ? R7Fixed.UpgradeActivationRoot : R7Fixed.UpgradeAuthorizationRoot;
            using (R7VerifiedFile file = R7SafeFile.Open(path, path, root, null, R7Fixed.UpgradeSid, null, policy.VolumeIdentity))
            {
                SortedDictionary<string, object> record = R7Crypto.VerifyEnvelope(file.Bytes, policy.PublicCertificateSha256, verifier);
                string expectedOperation = activation ? "ACTIVATE_TERMINAL_UPGRADE" : "AUTHORIZE_TERMINAL_UPGRADE";
                if (R7Json.String(record, "operation", 1, 128) != expectedOperation || R7Json.String(record, "transition_nonce", 36, 36) != nonce) throw new R7ProtocolException("UPGRADE_RECORD_SEMANTICS_INVALID");
                R7LedgerRecord[] committed = ledger.Find(activation ? "UPGRADE_ACTIVATED" : "UPGRADE_AUTHORIZATION_ISSUED", nonce);
                if (committed.Length != 1 || committed[0].ContentAddress != file.Measurement.Sha256) throw new R7ProtocolException("UPGRADE_RECORD_NOT_COMMITTED");
                SortedDictionary<string, object> response = R7PipeWindowsService.Success(activation ? "UPGRADE_ACTIVATION_RESOLVED" : "UPGRADE_AUTHORIZATION_RESOLVED");
                response.Add(activation ? "activation_identity" : "authorization_identity", file.Measurement.Sha256);
                response.Add("ledger_entry_identity", committed[0].EntryIdentity);
                response.Add("ledger_sequence", committed[0].Sequence);
                response.Add("record", Convert.ToBase64String(file.Bytes));
                response.Add("transition_nonce", nonce);
                return response;
            }
        }

        private void VerifyOldLiveSet()
        {
            const string oldBinary = @"C:\Program Files\RandleAI\TerminalAuthority\RandleTerminalAuthority.exe";
            const string oldPolicy = @"C:\ProgramData\RandleAI\TerminalAuthority\Config\r7_terminal_authority_policy.json";
            using (R7VerifiedFile binary = R7SafeFile.Open(oldBinary, oldBinary, @"C:\Program Files\RandleAI\TerminalAuthority", policy.OldBinarySha256, R7Fixed.SystemSid, null, policy.VolumeIdentity)) { }
            using (R7VerifiedFile oldPolicyFile = R7SafeFile.Open(oldPolicy, oldPolicy, @"C:\ProgramData\RandleAI\TerminalAuthority\Config", policy.OldPolicySha256, R7Fixed.SystemSid, null, policy.VolumeIdentity)) { }
        }

        private long NextActivationSequence()
        {
            long highest = 0;
            foreach (R7LedgerRecord record in ledger.Find("UPGRADE_ACTIVATED", null)) highest++;
            return highest + 1;
        }

        private static void VerifyComponentHash(List<object> measured, string role, string expected)
        {
            foreach (object raw in measured)
            {
                SortedDictionary<string, object> item = RequireObject(raw);
                if (String.Equals(R7Json.String(item, "role", 1, 256), role, StringComparison.Ordinal))
                {
                    if (!String.Equals(R7Json.String(item, "sha256", 64, 64), expected, StringComparison.Ordinal)) throw new R7ProtocolException("COMPONENT_HASH_MISMATCH", role);
                    return;
                }
            }
            throw new R7ProtocolException("COMPONENT_MISSING", role);
        }

        private static string CanonicalGuid(string value)
        {
            Guid parsed;
            if (!Guid.TryParseExact(value, "D", out parsed) || !String.Equals(parsed.ToString("D"), value, StringComparison.Ordinal)) throw new R7ProtocolException("GUID_INVALID");
            return value;
        }

        private static SortedDictionary<string, object> RequireObject(object value)
        {
            SortedDictionary<string, object> result = value as SortedDictionary<string, object>;
            if (result == null) throw new R7ProtocolException("OBJECT_REQUIRED");
            return result;
        }

        private static void RequirePublic(R7CallerIdentity caller)
        {
            if (caller.UserSid != R7Fixed.OperatorSid && caller.UserSid != R7Fixed.SystemSid && caller.UserSid != R7Fixed.TerminalSid && caller.UserSid != R7Fixed.ExecutionSid) throw new SecurityException("CALLER_NOT_AUTHORIZED");
        }

        private static void RequireOperator(R7CallerIdentity caller)
        {
            if (caller.UserSid != R7Fixed.OperatorSid && caller.UserSid != R7Fixed.SystemSid) throw new SecurityException("UPGRADE_CALLER_NOT_AUTHORIZED");
        }

        private static void RequireTerminal(R7CallerIdentity caller)
        {
            if (caller.UserSid != R7Fixed.TerminalSid || !caller.ContainsTerminalSignerSid) throw new SecurityException("CALLER_NOT_TERMINAL_SIGNER");
        }

    }

    internal static class R7UpgradeServiceProgram
    {
        private static void Main()
        {
            R7RuntimeBoundary.Enforce(R7Fixed.UpgradeInstallRoot);
            ServiceBase.Run(new R7PipeWindowsService(
                R7Fixed.UpgradeService,
                R7Fixed.UpgradePipe,
                new string[] { R7Fixed.OperatorSid, R7Fixed.SystemSid, R7Fixed.TerminalSid, R7Fixed.ExecutionSid, R7Fixed.UpgradeSid },
                delegate() { return new R7UpgradeProcessor(); }));
        }
    }
}
