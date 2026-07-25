using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Security.Principal;

namespace RandleAI.R7Remediation
{
    internal static class R7Unit2UpgradePublicVerifierProgram
    {
        private static int Main(string[] args)
        {
            try
            {
                R7RuntimeBoundary.Enforce(R7Fixed.UpgradeInstallRoot);
                bool attackCopies = args.Length == 3 && String.Equals(args[0], "attack-copies", StringComparison.Ordinal);
                if ((!attackCopies && args.Length != 2) || (attackCopies && args.Length != 3)) throw new ArgumentException("usage: <apply-boundary|measure-boundary|key-open-denied|provisioned|authorized> <new-output-json> | attack-copies <new-disposable-root> <new-output-json>");
                bool requireAuthorization = String.Equals(args[0], "authorized", StringComparison.Ordinal);
                R7Unit2UpgradePolicy policy = R7Unit2UpgradePolicy.LoadPublic(R7Unit2BuildIdentity.PublicCertificateSha256);
                string executable = Path.GetFullPath(Assembly.GetExecutingAssembly().Location);
                string expectedExecutable = Path.Combine(R7Fixed.UpgradeInstallRoot, "RandleTerminalUpgradePublicVerifier.exe");
                using (R7VerifiedFile self = R7SafeFile.Open(executable, expectedExecutable, R7Fixed.UpgradeInstallRoot, policy.UpgradeVerifierSha256, R7Fixed.SystemSid, null, policy.VolumeIdentity))
                using (R7DependencyClosure dependencies = new R7DependencyClosure(R7Fixed.UpgradeDependencyManifestPath, policy.DependencyManifestSha256, R7Fixed.UpgradeInstallRoot))
                {
                    if (String.Equals(args[0], "apply-boundary", StringComparison.Ordinal) || String.Equals(args[0], "measure-boundary", StringComparison.Ordinal))
                    {
                        bool apply = String.Equals(args[0], "apply-boundary", StringComparison.Ordinal);
                        SortedDictionary<string, object> boundary = apply ? R7ServiceBoundary.EnforceAndMeasure(R7Fixed.UpgradeService, R7Fixed.UpgradeSid, Path.Combine(R7Fixed.UpgradeInstallRoot, "RandleTerminalUpgradeAuthority.exe")) : R7ServiceBoundary.MeasureOnly(R7Fixed.UpgradeService, R7Fixed.UpgradeSid, Path.Combine(R7Fixed.UpgradeInstallRoot, "RandleTerminalUpgradeAuthority.exe"));
                        dependencies.VerifyNoNewModules();
                        SortedDictionary<string, object> boundaryResult = R7Json.Object("artifact_type", "R7_UNIT2_BOUNDARY_OPERATION_RESULT", "boundary", boundary, "mutation_performed", apply, "schema_version", "1.0.0", "status", "PASS", "verifier_sha256", self.Measurement.Sha256);
                        WriteResult(args[1], boundaryResult);
                        Console.WriteLine(R7Json.Text(boundaryResult));
                        return 0;
                    }
                    if (String.Equals(args[0], "key-open-denied", StringComparison.Ordinal))
                    {
                        bool denied = false;
                        string error = String.Empty;
                        try { using (CngKey forbidden = CngKey.Open(policy.KeyUniqueName, CngProvider.MicrosoftSoftwareKeyStorageProvider, CngKeyOpenOptions.MachineKey)) { } }
                        catch (CryptographicException exception) { denied = true; error = exception.GetType().FullName + "|" + exception.Message; }
                        if (!denied) throw new CryptographicException("UNIT2_INTERACTIVE_KEY_OPEN_UNEXPECTEDLY_SUCCEEDED");
                        dependencies.VerifyNoNewModules();
                        using (WindowsIdentity caller = WindowsIdentity.GetCurrent())
                        {
                            bool administrator = new WindowsPrincipal(caller).IsInRole(WindowsBuiltInRole.Administrator);
                            SortedDictionary<string, object> keyResult = R7Json.Object("artifact_type", "R7_UNIT2_INTERACTIVE_KEY_OPEN_PROBE", "caller_is_administrator", administrator, "caller_sid", caller.User == null ? String.Empty : caller.User.Value, "error", error, "key_open_denied", true, "private_bytes_exported", false, "schema_version", "1.0.0", "status", "PASS", "verifier_sha256", self.Measurement.Sha256);
                            WriteResult(args[1], keyResult);
                            Console.WriteLine(R7Json.Text(keyResult));
                        }
                        return 0;
                    }
                    if (attackCopies)
                    {
                        SortedDictionary<string, object> attackResult = AttackCopies(policy, args[1]);
                        dependencies.VerifyNoNewModules();
                        WriteResult(args[2], attackResult);
                        Console.WriteLine(R7Json.Text(attackResult));
                        return 0;
                    }
                    if (!String.Equals(args[0], "provisioned", StringComparison.Ordinal) && !requireAuthorization) throw new ArgumentException("VERIFIER_OPERATION_NOT_EXPOSED");
                using (X509Certificate2 certificate = R7Crypto.LoadPublicCertificate(R7Fixed.UpgradePublicCertificatePath, policy.PublicCertificateSha256, R7Fixed.UpgradeTrustRoot))
                using (RSA verifier = RSACertificateExtensions.GetRSAPublicKey(certificate))
                {
                    if (verifier == null || verifier.KeySize != 3072) throw new CryptographicException("UNIT2_PUBLIC_RSA3072_REQUIRED");
                    R7VersionedLedger ledger = new R7VersionedLedger(R7Fixed.UpgradeLedgerRoot, policy.LedgerId, policy.PublicCertificateSha256, R7Fixed.UpgradeSid, null, verifier);
                    if (!String.IsNullOrEmpty(ledger.CheckpointRecoveryReason) || ledger.PendingCheckpointArtifacts.Length != 0) throw new InvalidDataException("UNIT2_PUBLIC_CHECKPOINT_NOT_CURRENT");
                    R7LedgerRecord[] records = ledger.Records;
                    if (records.Length < 3 || !String.Equals(records[0].Operation, "UPGRADE_LEDGER_GENESIS", StringComparison.Ordinal)) throw new InvalidDataException("UNIT2_PUBLIC_GENESIS_INVALID");
                    VerifyGenesis(policy, records[0], verifier);
                    string attestationIdentity = VerifyProvisioning(policy, ledger, verifier);
                    VerifyStartupRecords(policy, ledger);
                    string authorizationIdentity = R7Fixed.ZeroHash;
                    if (requireAuthorization) authorizationIdentity = VerifyAuthorization(policy, ledger, verifier);
                    else if (ledger.Find("UPGRADE_TRANSITION_AUTHORIZED", policy.TransitionNonce).Length != 0) throw new InvalidDataException("UNIT2_UNEXPECTED_AUTHORIZATION_DURING_PROVISIONING_VERIFICATION");
                    if (Directory.Exists(R7Fixed.UpgradeActivationRoot) && Directory.GetFileSystemEntries(R7Fixed.UpgradeActivationRoot).Length != 0) throw new InvalidDataException("UNIT2_ACTIVATION_ARTIFACT_FORBIDDEN");
                    dependencies.VerifyNoNewModules();
                    SortedDictionary<string, object> result = R7Json.Object(
                        "artifact_type", "R7_UNIT2_PUBLIC_ONLY_VERIFICATION",
                        "authorization_identity", authorizationIdentity,
                        "authorization_required", requireAuthorization,
                        "checkpoint_sha256", ledger.CheckpointIdentity,
                        "installation_performed", false,
                        "ledger_id", policy.LedgerId,
                        "ledger_root", ledger.RootHash,
                        "ledger_sequence", ledger.Sequence,
                        "policy_sha256", policy.Sha256,
                        "private_key_used", false,
                        "provisioning_attestation_identity", attestationIdentity,
                        "public_certificate_sha256", policy.PublicCertificateSha256,
                        "schema_version", "1.0.0",
                        "service_connection_attempted", false,
                        "status", "PASS",
                        "verifier_sha256", self.Measurement.Sha256);
                    WriteResult(args[1], result);
                    Console.WriteLine(R7Json.Text(result));
                    return 0;
                }
                }
            }
            catch (Exception exception)
            {
                Console.Error.WriteLine(exception.GetType().FullName + "|" + exception.Message);
                return 1;
            }
        }

        private static void VerifyGenesis(R7Unit2UpgradePolicy policy, R7LedgerRecord genesis, RSA verifier)
        {
            R7ObjectStore objects = new R7ObjectStore(R7Fixed.UpgradeObjectRoot, R7Fixed.UpgradeSid, policy.VolumeIdentity);
            SortedDictionary<string, object> value = objects.Get(genesis.ContentAddress);
            R7Json.ExactKeys(value, "artifact_type", "binary_sha256", "build_receipt_sha256", "dependency_manifest_sha256", "ledger_id", "policy_sha256", "public_key_identity", "schema_version", "service_sid", "source_commit", "source_tree");
            if (!String.Equals(R7Json.String(value, "artifact_type", 1, 256), "R7_UNIT2_UPGRADE_LEDGER_GENESIS_MANIFEST", StringComparison.Ordinal) ||
                !String.Equals(R7Json.String(value, "ledger_id", 64, 64), policy.LedgerId, StringComparison.Ordinal) ||
                !String.Equals(R7Json.String(value, "service_sid", 1, 256), R7Fixed.UpgradeSid, StringComparison.Ordinal) ||
                !String.Equals(R7Json.String(value, "source_commit", 40, 40), policy.SourceCommit, StringComparison.Ordinal) ||
                !String.Equals(R7Json.String(value, "source_tree", 40, 40), policy.SourceTree, StringComparison.Ordinal) ||
                !R7Hash.FixedTimeEquals(R7Json.String(value, "policy_sha256", 64, 64), policy.Sha256) ||
                !R7Hash.FixedTimeEquals(R7Json.String(value, "public_key_identity", 64, 64), policy.PublicCertificateSha256)) throw new InvalidDataException("UNIT2_PUBLIC_GENESIS_BINDING_INVALID");
        }

        private static string VerifyProvisioning(R7Unit2UpgradePolicy policy, R7VersionedLedger ledger, RSA verifier)
        {
            string path = Path.Combine(R7Fixed.UpgradeEvidenceRoot, policy.ProvisioningNonce + ".provisioning-attestation.json");
            using (R7VerifiedFile file = R7SafeFile.Open(path, path, R7Fixed.UpgradeEvidenceRoot, null, R7Fixed.UpgradeSid, null, policy.VolumeIdentity))
            {
                SortedDictionary<string, object> payload = R7Crypto.VerifyEnvelope(file.Bytes, policy.PublicCertificateSha256, verifier);
                R7Json.ExactKeys(payload, "administrator_exclusion", "artifact_type", "authority_bindings", "authorization_scope_sha256", "binary_identity", "build_receipt_sha256", "dependency_manifest_sha256", "disposition", "fixed_roots", "interface_version", "ipc_identity", "isolation_probes", "key", "ledger_id", "operation_allowlist", "preflight_baseline_sha256", "principal", "provisioned_at", "provisioning_nonce", "provisioning_script_sha256", "public_certificate_sha256", "schema_version", "service_boundary_measurement_sha256", "service_effective_token", "source_bindings", "target_bindings", "terminal_authority_effect", "threat_model", "transition_nonce");
                if (!String.Equals(R7Json.String(payload, "artifact_type", 1, 256), "R7_UNIT2_SIGNED_PROVISIONING_ATTESTATION", StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(payload, "disposition", 1, 256), "UPGRADE_AUTHORITY_PROVISIONED_NO_TERMINAL_TRANSITION", StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(payload, "provisioning_nonce", 36, 36), policy.ProvisioningNonce, StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(payload, "terminal_authority_effect", 1, 64), "NONE", StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(payload, "ipc_identity", 1, 256), R7Fixed.UpgradePipe, StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(payload, "ledger_id", 64, 64), policy.LedgerId, StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(payload, "transition_nonce", 36, 36), policy.TransitionNonce, StringComparison.Ordinal) ||
                    !R7Hash.FixedTimeEquals(R7Json.String(payload, "public_certificate_sha256", 64, 64), policy.PublicCertificateSha256) ||
                    !R7Hash.FixedTimeEquals(R7Json.String(payload, "preflight_baseline_sha256", 64, 64), policy.PreflightBaselineSha256) ||
                    !R7Hash.FixedTimeEquals(R7Json.String(payload, "authorization_scope_sha256", 64, 64), policy.AuthorizationScopeSha256) ||
                    !R7Hash.FixedTimeEquals(R7Json.String(payload, "dependency_manifest_sha256", 64, 64), policy.DependencyManifestSha256) ||
                    !R7Hash.FixedTimeEquals(R7Json.String(payload, "provisioning_script_sha256", 64, 64), policy.ProvisioningScriptSha256) ||
                    !R7Json.Boolean(payload, "administrator_exclusion") ||
                    !SameJson(R7Json.Child(payload, "authority_bindings"), policy.AuthorityBindings) ||
                    !SameJson(R7Json.Child(payload, "target_bindings"), policy.TargetBindings) ||
                    !SameJson(R7Json.Child(payload, "threat_model"), policy.ThreatModel)) throw new InvalidDataException("UNIT2_PUBLIC_PROVISIONING_ATTESTATION_INVALID");
                SortedDictionary<string, object> principal = R7Json.Child(payload, "principal");
                if (!String.Equals(R7Json.String(principal, "account", 1, 256), "NT SERVICE\\" + R7Fixed.UpgradeService, StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(principal, "service_sid", 1, 256), R7Fixed.UpgradeSid, StringComparison.Ordinal) ||
                    R7Json.Boolean(principal, "administrator_member")) throw new InvalidDataException("UNIT2_PUBLIC_PRINCIPAL_ATTESTATION_INVALID");
                SortedDictionary<string, object> token = R7Json.Child(payload, "service_effective_token");
                if (!String.Equals(R7Json.String(token, "user_sid", 1, 256), R7Fixed.UpgradeSid, StringComparison.Ordinal) ||
                    R7Json.Boolean(token, "contains_terminal_signer_sid") || ContainsString(R7Json.Array(token, "group_sids"), "S-1-5-32-544") ||
                    !SinglePrivilege(R7Json.Array(token, "privileges"), "SeChangeNotifyPrivilege:")) throw new InvalidDataException("UNIT2_PUBLIC_EFFECTIVE_TOKEN_INVALID");
                R7LedgerRecord[] rows = ledger.Find("UPGRADE_AUTHORITY_PROVISIONED", policy.ProvisioningNonce);
                if (rows.Length != 1 || !R7Hash.FixedTimeEquals(rows[0].ContentAddress, file.Measurement.Sha256)) throw new InvalidDataException("UNIT2_PUBLIC_PROVISIONING_LEDGER_BINDING_INVALID");
                return file.Measurement.Sha256;
            }
        }

        private static void VerifyStartupRecords(R7Unit2UpgradePolicy policy, R7VersionedLedger ledger)
        {
            R7LedgerRecord[] rows = ledger.Find("UPGRADE_AUTHORITY_SERVICE_STARTED", policy.ProvisioningNonce);
            if (rows.Length < 1) throw new InvalidDataException("UNIT2_PUBLIC_STARTUP_RECORD_MISSING");
            R7ObjectStore objects = new R7ObjectStore(R7Fixed.UpgradeObjectRoot, R7Fixed.UpgradeSid, policy.VolumeIdentity);
            foreach (R7LedgerRecord row in rows)
            {
                SortedDictionary<string, object> value = objects.Get(row.ContentAddress);
                if (!String.Equals(R7Json.String(value, "artifact_type", 1, 256), "R7_UNIT2_UPGRADE_SERVICE_START", StringComparison.Ordinal) || !R7Hash.FixedTimeEquals(R7Json.String(value, "policy_sha256", 64, 64), policy.Sha256)) throw new InvalidDataException("UNIT2_PUBLIC_STARTUP_RECORD_INVALID");
            }
        }

        private static string VerifyAuthorization(R7Unit2UpgradePolicy policy, R7VersionedLedger ledger, RSA verifier)
        {
            R7LedgerRecord[] reserved = ledger.Find("UPGRADE_TRANSITION_AUTHORIZATION_RESERVED", policy.TransitionNonce);
            R7LedgerRecord[] committed = ledger.Find("UPGRADE_TRANSITION_AUTHORIZED", policy.TransitionNonce);
            R7LedgerRecord[] available = ledger.Find("UPGRADE_TRANSITION_RESPONSE_AVAILABLE", policy.TransitionNonce);
            if (reserved.Length != 1 || committed.Length != 1 || available.Length != 1 || reserved[0].Sequence >= committed[0].Sequence || committed[0].Sequence >= available[0].Sequence) throw new InvalidDataException("UNIT2_PUBLIC_AUTHORIZATION_STATE_INVALID");
            string path = Path.Combine(R7Fixed.UpgradeAuthorizationRoot, policy.TransitionNonce + ".authorization.json");
            using (R7VerifiedFile file = R7SafeFile.Open(path, path, R7Fixed.UpgradeAuthorizationRoot, null, R7Fixed.UpgradeSid, null, policy.VolumeIdentity))
            {
                SortedDictionary<string, object> payload = R7Crypto.VerifyEnvelope(file.Bytes, policy.PublicCertificateSha256, verifier);
                R7Json.ExactKeys(payload, "anti_downgrade", "authority_bindings", "authority_class", "authorization_expiration", "authorization_time", "components", "consumption_state", "current_state", "disposition", "host_bound", "installation_performed", "one_time_use", "operation", "request_frame_sha256", "request_identity", "request_payload_identity", "revocation_state", "rollback_constraints", "schema_version", "target_bindings", "target_source_commit", "target_source_tree", "transition_nonce", "transition_plan_sha256", "upgrade_authority_may_install");
                if (!String.Equals(R7Json.String(payload, "authority_class", 1, 256), "TERMINAL_TRANSITION_PREINSTALL_AUTHORIZATION", StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(payload, "disposition", 1, 256), "AUTHORIZED FOR FUTURE INSTALLATION CONSIDERATION", StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(payload, "operation", 1, 128), "AUTHORIZE_TERMINAL_TRANSITION", StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(payload, "transition_nonce", 36, 36), policy.TransitionNonce, StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(payload, "target_source_commit", 40, 40), policy.TargetCommit, StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(payload, "target_source_tree", 40, 40), policy.TargetTree, StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(payload, "consumption_state", 1, 128), "PENDING_FUTURE_SEPARATE_UNIT", StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(payload, "revocation_state", 1, 64), "ACTIVE", StringComparison.Ordinal) ||
                    !R7Json.Boolean(payload, "host_bound") || !R7Json.Boolean(payload, "one_time_use") ||
                    R7Json.Boolean(payload, "installation_performed") || R7Json.Boolean(payload, "upgrade_authority_may_install") ||
                    !R7Hash.FixedTimeEquals(R7Json.String(payload, "transition_plan_sha256", 64, 64), policy.TransitionPlanSha256) ||
                    !R7Hash.FixedTimeEquals(R7Json.String(payload, "authorization_expiration", 28, 28), policy.AuthorizationExpiresAt) ||
                    !R7Hash.IsLowerSha256(R7Json.String(payload, "request_frame_sha256", 64, 64)) ||
                    !R7Hash.IsLowerSha256(R7Json.String(payload, "request_payload_identity", 64, 64)) ||
                    !SameJson(R7Json.Child(payload, "authority_bindings"), policy.AuthorityBindings) ||
                    !SameJson(R7Json.Child(payload, "target_bindings"), policy.TargetBindings) ||
                    !SameJson(R7Json.Child(payload, "rollback_constraints"), policy.RollbackConstraints) ||
                    !R7Hash.FixedTimeEquals(committed[0].ContentAddress, file.Measurement.Sha256)) throw new InvalidDataException("UNIT2_PUBLIC_AUTHORIZATION_INVALID");
                SortedDictionary<string, object> current = R7Json.Child(payload, "current_state");
                R7Json.ExactKeys(current, "checkpoint_sha256", "consumption_remeasurement_required", "host_identity", "issuance_measurement_mode", "preflight_baseline_sha256", "terminal_interface", "terminal_ledger_id", "terminal_ledger_root", "terminal_ledger_sequence", "terminal_policy_sha256", "terminal_public_trust_sha256", "terminal_service_binary_sha256", "terminal_service_name", "terminal_service_sid", "volume_identity");
                if (!R7Json.Boolean(current, "consumption_remeasurement_required") ||
                    !String.Equals(R7Json.String(current, "issuance_measurement_mode", 1, 128), "IMMUTABLE_ELEVATED_PREFLIGHT_CAPTURE", StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(current, "terminal_interface", 1, 128), policy.OldInterface, StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(current, "terminal_service_name", 1, 128), R7Fixed.TerminalService, StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(current, "terminal_service_sid", 1, 256), R7Fixed.TerminalSid, StringComparison.Ordinal) ||
                    R7Json.Integer(current, "terminal_ledger_sequence", 1, Int64.MaxValue) != policy.OldLedgerSequence ||
                    !R7Hash.FixedTimeEquals(R7Json.String(current, "checkpoint_sha256", 64, 64), policy.OldCheckpointSha256) ||
                    !R7Hash.FixedTimeEquals(R7Json.String(current, "host_identity", 64, 64), policy.HostIdentity) ||
                    !R7Hash.FixedTimeEquals(R7Json.String(current, "preflight_baseline_sha256", 64, 64), policy.PreflightBaselineSha256) ||
                    !R7Hash.FixedTimeEquals(R7Json.String(current, "terminal_ledger_id", 64, 64), policy.OldLedgerId) ||
                    !R7Hash.FixedTimeEquals(R7Json.String(current, "terminal_ledger_root", 64, 64), policy.OldLedgerRoot) ||
                    !R7Hash.FixedTimeEquals(R7Json.String(current, "terminal_policy_sha256", 64, 64), policy.OldPolicySha256) ||
                    !R7Hash.FixedTimeEquals(R7Json.String(current, "terminal_public_trust_sha256", 64, 64), policy.OldTrustSha256) ||
                    !R7Hash.FixedTimeEquals(R7Json.String(current, "terminal_service_binary_sha256", 64, 64), policy.OldBinarySha256)) throw new InvalidDataException("UNIT2_PUBLIC_CURRENT_STATE_BINDING_INVALID");
                SortedDictionary<string, object> antiDowngrade = R7Json.Child(payload, "anti_downgrade");
                R7Json.ExactKeys(antiDowngrade, "minimum_terminal_version", "prohibited_component_sha256");
                if (!String.Equals(R7Json.String(antiDowngrade, "minimum_terminal_version", 1, 128), policy.MinimumVersion, StringComparison.Ordinal) || !SameStringSet(R7Json.Array(antiDowngrade, "prohibited_component_sha256"), policy.RevokedHashes)) throw new InvalidDataException("UNIT2_PUBLIC_ANTI_DOWNGRADE_INVALID");
                object[] componentRows = R7Json.Array(payload, "components");
                if (componentRows.Length != policy.Components.Length) throw new InvalidDataException("UNIT2_PUBLIC_COMPONENT_COUNT_INVALID");
                string stagingRoot = Path.Combine(R7Fixed.UpgradeStagingRoot, policy.TransitionNonce);
                HashSet<string> seenRoles = new HashSet<string>(StringComparer.Ordinal);
                foreach (object raw in componentRows)
                {
                    SortedDictionary<string, object> row = R7Unit2UpgradePolicy.RequireObject(raw);
                    R7Json.ExactKeys(row, "file_identity", "final_path", "final_path_preinstall_state", "hard_link_count", "role", "sha256", "size", "staging_relative_path", "volume_identity");
                    string role = R7Json.String(row, "role", 1, 256); if (!seenRoles.Add(role)) throw new InvalidDataException("UNIT2_PUBLIC_COMPONENT_ROLE_DUPLICATE");
                    R7Unit2Component expected = policy.Component(role);
                    string relative = R7Json.String(row, "staging_relative_path", 1, 2048);
                    string stagePath = Path.Combine(stagingRoot, relative.Replace('/', Path.DirectorySeparatorChar));
                    using (R7VerifiedFile staged = R7SafeFile.Open(stagePath, stagePath, stagingRoot, expected.Sha256, R7Fixed.SystemSid, null, policy.VolumeIdentity))
                    {
                        if (!String.Equals(relative, expected.RelativePath, StringComparison.Ordinal) || !String.Equals(R7Json.String(row, "final_path", 3, 4096), expected.FinalPath, StringComparison.Ordinal) ||
                            !R7Hash.FixedTimeEquals(R7Json.String(row, "sha256", 64, 64), expected.Sha256) || !String.Equals(R7Json.String(row, "file_identity", 1, 128), staged.Measurement.FileIdentity, StringComparison.Ordinal) ||
                            R7Json.Integer(row, "hard_link_count", 1, UInt32.MaxValue) != staged.Measurement.LinkCount || R7Json.Integer(row, "size", 0, Int64.MaxValue) != staged.Measurement.Size ||
                            !String.Equals(R7Json.String(row, "volume_identity", 1, 128), staged.Measurement.VolumeIdentity, StringComparison.Ordinal)) throw new InvalidDataException("UNIT2_PUBLIC_COMPONENT_BINDING_INVALID|" + role);
                    }
                }
                string requestIdentity = R7Unit2UpgradePolicy.CanonicalGuid(R7Json.String(payload, "request_identity", 36, 36));
                R7ObjectStore objects = new R7ObjectStore(R7Fixed.UpgradeObjectRoot, R7Fixed.UpgradeSid, policy.VolumeIdentity);
                SortedDictionary<string, object> requestEvidence = objects.Get(reserved[0].ContentAddress);
                if (!String.Equals(R7Json.String(requestEvidence, "request_identity", 36, 36), requestIdentity, StringComparison.Ordinal) || !R7Hash.FixedTimeEquals(R7Json.String(requestEvidence, "request_frame_sha256", 64, 64), R7Json.String(payload, "request_frame_sha256", 64, 64))) throw new InvalidDataException("UNIT2_PUBLIC_REQUEST_EVIDENCE_INVALID");
                string responsePath = Path.Combine(R7Fixed.UpgradeResponseRoot, requestIdentity + ".response.json");
                using (R7VerifiedFile responseFile = R7SafeFile.Open(responsePath, responsePath, R7Fixed.UpgradeResponseRoot, null, R7Fixed.UpgradeSid, null, policy.VolumeIdentity))
                {
                    SortedDictionary<string, object> response = R7Json.ParseCanonicalObject(responseFile.Bytes);
                    if (!String.Equals(R7Json.String(response, "authorization_identity", 64, 64), file.Measurement.Sha256, StringComparison.Ordinal) || !String.Equals(R7Json.String(response, "request_identity", 36, 36), requestIdentity, StringComparison.Ordinal) || R7Json.Boolean(response, "installation_performed")) throw new InvalidDataException("UNIT2_PUBLIC_RESPONSE_INVALID");
                    SortedDictionary<string, object> responseRecord = objects.Get(available[0].ContentAddress);
                    if (!R7Hash.FixedTimeEquals(R7Json.String(responseRecord, "response_identity", 64, 64), responseFile.Measurement.Sha256)) throw new InvalidDataException("UNIT2_PUBLIC_RESPONSE_LEDGER_BINDING_INVALID");
                }
                if (ledger.Find("UPGRADE_TRANSITION_REVOKED", policy.TransitionNonce).Length != 0) throw new InvalidDataException("UNIT2_PUBLIC_AUTHORIZATION_REVOKED");
                return file.Measurement.Sha256;
            }
        }

        private static bool SameJson(SortedDictionary<string, object> left, SortedDictionary<string, object> right)
        {
            return R7Hash.FixedTimeEquals(R7Hash.Bytes(R7Json.Encode(left)), R7Hash.Bytes(R7Json.Encode(right)));
        }

        private static bool ContainsString(object[] values, string expected)
        {
            foreach (object value in values) if (String.Equals(value as string, expected, StringComparison.Ordinal)) return true;
            return false;
        }

        private static bool SinglePrivilege(object[] values, string prefix)
        {
            return values.Length == 1 && values[0] is string && ((string)values[0]).StartsWith(prefix, StringComparison.Ordinal);
        }

        private static bool SameStringSet(object[] values, string[] expected)
        {
            if (values.Length != expected.Length) return false;
            string[] left = new string[values.Length];
            for (int index = 0; index < values.Length; index++) { left[index] = values[index] as string; if (left[index] == null) return false; }
            string[] right = (string[])expected.Clone(); Array.Sort(left, StringComparer.Ordinal); Array.Sort(right, StringComparer.Ordinal);
            for (int index = 0; index < left.Length; index++) if (!String.Equals(left[index], right[index], StringComparison.Ordinal)) return false;
            return true;
        }

        private static SortedDictionary<string, object> AttackCopies(R7Unit2UpgradePolicy policy, string requestedRoot)
        {
            string root = Path.GetFullPath(requestedRoot);
            string temporary = Path.GetFullPath(Path.GetTempPath()).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            if (!root.StartsWith(temporary, StringComparison.OrdinalIgnoreCase) || root.IndexOf(Path.DirectorySeparatorChar + "R7Unit2PublicAttacks" + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase) < 0) throw new InvalidDataException("UNIT2_ATTACK_ROOT_NOT_DISPOSABLE");
            if (Directory.Exists(root) && Directory.GetFileSystemEntries(root).Length != 0) throw new InvalidDataException("UNIT2_ATTACK_ROOT_NOT_EMPTY");
            Directory.CreateDirectory(root);
            using (X509Certificate2 certificate = R7Crypto.LoadPublicCertificate(R7Fixed.UpgradePublicCertificatePath, policy.PublicCertificateSha256, R7Fixed.UpgradeTrustRoot))
            using (RSA verifier = RSACertificateExtensions.GetRSAPublicKey(certificate))
            {
                R7VersionedLedger live = new R7VersionedLedger(R7Fixed.UpgradeLedgerRoot, policy.LedgerId, policy.PublicCertificateSha256, R7Fixed.UpgradeSid, null, verifier);
                string validRoot = Path.Combine(root, "valid-copy", "Ledger"); CopyTree(R7Fixed.UpgradeLedgerRoot, validRoot);
                R7VersionedLedger valid = new R7VersionedLedger(validRoot, policy.LedgerId, policy.PublicCertificateSha256, R7Fixed.UpgradeSid, null, verifier);
                if (valid.Sequence != live.Sequence || !R7Hash.FixedTimeEquals(valid.RootHash, live.RootHash) || !R7Hash.FixedTimeEquals(valid.CheckpointIdentity, live.CheckpointIdentity)) throw new InvalidDataException("UNIT2_VALID_COPY_CRYPTOGRAPHIC_MISMATCH");
                List<object> attacks = new List<object>();
                attacks.Add(R7Json.Object("attack", "COPIED_LEDGER_ROOT", "classification", "CRYPTOGRAPHICALLY_VALID_COPY_NONAUTHORITY", "copied_root", validRoot, "fixed_authority_root", R7Fixed.UpgradeLedgerRoot, "status", "PASS"));

                string mutationRoot = Path.Combine(root, "entry-mutation", "Ledger"); CopyTree(R7Fixed.UpgradeLedgerRoot, mutationRoot);
                string mutationEntry = Directory.GetFiles(mutationRoot, "*.entry.json")[0]; byte[] mutationBytes = File.ReadAllBytes(mutationEntry); mutationBytes[mutationBytes.Length / 2] ^= 1; File.WriteAllBytes(mutationEntry, mutationBytes);
                attacks.Add(ExpectLedgerRejection("ENTRY_MUTATION", mutationRoot, policy, verifier));

                string truncationRoot = Path.Combine(root, "truncation", "Ledger"); CopyTree(R7Fixed.UpgradeLedgerRoot, truncationRoot);
                string[] truncationEntries = Directory.GetFiles(truncationRoot, "*.entry.json"); Array.Sort(truncationEntries, StringComparer.Ordinal); File.Move(truncationEntries[truncationEntries.Length - 1], truncationEntries[truncationEntries.Length - 1] + ".removed-evidence");
                attacks.Add(ExpectLedgerRejection("TRUNCATION", truncationRoot, policy, verifier));

                string missingRoot = Path.Combine(root, "missing-entry", "Ledger"); CopyTree(R7Fixed.UpgradeLedgerRoot, missingRoot);
                string[] missingEntries = Directory.GetFiles(missingRoot, "*.entry.json"); Array.Sort(missingEntries, StringComparer.Ordinal); if (missingEntries.Length < 3) throw new InvalidDataException("UNIT2_LEDGER_TOO_SHORT_FOR_MISSING_ATTACK"); File.Move(missingEntries[1], missingEntries[1] + ".missing-evidence");
                attacks.Add(ExpectLedgerRejection("MISSING_ENTRY", missingRoot, policy, verifier));

                string authorizationPath = Path.Combine(R7Fixed.UpgradeAuthorizationRoot, policy.TransitionNonce + ".authorization.json");
                string detachedRoot = Path.Combine(root, "detached-authorization"); Directory.CreateDirectory(detachedRoot); string detachedPath = Path.Combine(detachedRoot, Path.GetFileName(authorizationPath)); File.Copy(authorizationPath, detachedPath, false);
                byte[] detachedBytes = File.ReadAllBytes(detachedPath); R7Crypto.VerifyEnvelope(detachedBytes, policy.PublicCertificateSha256, verifier);
                attacks.Add(R7Json.Object("attack", "DETACHED_AUTHORIZATION", "authorization_sha256", R7Hash.Bytes(detachedBytes), "classification", "VALID_SIGNATURE_BUT_NO_FIXED_LEDGER_MEMBERSHIP_NONAUTHORITY", "status", "PASS"));
                return R7Json.Object("artifact_type", "R7_UNIT2_PUBLIC_COPY_AND_MUTATION_ATTACKS", "attack_count", (long)attacks.Count, "attacks", attacks.ToArray(), "checkpoint_sha256", live.CheckpointIdentity, "ledger_root", live.RootHash, "ledger_sequence", live.Sequence, "private_key_used", false, "schema_version", "1.0.0", "status", "PASS");
            }
        }

        private static SortedDictionary<string, object> ExpectLedgerRejection(string attack, string root, R7Unit2UpgradePolicy policy, RSA verifier)
        {
            try { new R7VersionedLedger(root, policy.LedgerId, policy.PublicCertificateSha256, R7Fixed.UpgradeSid, null, verifier); }
            catch (Exception exception) { return R7Json.Object("attack", attack, "classification", "REJECTED", "error", exception.GetType().FullName + "|" + exception.Message, "status", "PASS"); }
            throw new InvalidDataException("UNIT2_ATTACK_UNEXPECTEDLY_VERIFIED|" + attack);
        }

        private static void CopyTree(string source, string destination)
        {
            Directory.CreateDirectory(destination);
            foreach (string file in Directory.GetFiles(source)) File.Copy(file, Path.Combine(destination, Path.GetFileName(file)), false);
            foreach (string directory in Directory.GetDirectories(source)) CopyTree(directory, Path.Combine(destination, Path.GetFileName(directory)));
        }

        private static void WriteResult(string requestedPath, SortedDictionary<string, object> result)
        {
            string output = Path.GetFullPath(requestedPath);
            string root = Path.GetDirectoryName(output);
            R7SafeFile.MeasureDirectory(root, root, null, null, null);
            R7SafeFile.AssertAbsent(output, output, root);
            byte[] bytes = R7Json.Encode(result);
            R7DurableFile.CreateNew(output, bytes);
            using (R7VerifiedFile written = R7SafeFile.Open(output, output, root, R7Hash.Bytes(bytes), null, null, null)) { }
        }
    }
}
