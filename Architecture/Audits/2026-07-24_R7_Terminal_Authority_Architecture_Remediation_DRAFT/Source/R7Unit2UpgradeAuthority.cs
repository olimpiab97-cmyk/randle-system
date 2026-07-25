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
using System.ComponentModel;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace RandleAI.R7Remediation
{
    internal static class R7Unit2BuildIdentity
    {
        internal const string PublicCertificateSha256 = "UNIT2_GENERATED_CERTIFICATE_SHA256";
#if UNIT2_SERVICE
        internal const string PolicySha256 = "UNIT2_GENERATED_POLICY_SHA256";
        internal const string DependencyManifestSha256 = "UNIT2_GENERATED_DEPENDENCY_SHA256";
        internal const string SourceCommit = "UNIT2_GENERATED_SOURCE_COMMIT";
        internal const string SourceTree = "UNIT2_GENERATED_SOURCE_TREE";
        internal const string KeyFilePath = @"UNIT2_GENERATED_KEY_FILE_PATH";
        internal const string KeyFileOwnerSid = "UNIT2_GENERATED_KEY_OWNER_SID";
        internal const string KeyFileSecurityDescriptorSha256 = "UNIT2_GENERATED_KEY_ACL_SHA256";
        internal const string KeyFileVolumeIdentity = "UNIT2_GENERATED_KEY_VOLUME_IDENTITY";
        internal const string KeyFileIdentity = "UNIT2_GENERATED_KEY_FILE_IDENTITY";
        internal const uint KeyFileLinkCount = 1;
#endif
    }

    internal sealed class R7Unit2Component
    {
        internal string Role;
        internal string RelativePath;
        internal string FinalPath;
        internal string Sha256;

        internal SortedDictionary<string, object> ToJson()
        {
            return R7Json.Object("final_path", FinalPath, "role", Role, "sha256", Sha256, "staging_relative_path", RelativePath);
        }
    }

    internal sealed class R7Unit2UpgradePolicy
    {
        internal string Sha256;
        internal string AuthorizationScopeSha256;
        internal string PublicCertificateSha256;
        internal string DependencyManifestSha256;
        internal string KeyUniqueName;
        internal string LedgerId;
        internal string VolumeIdentity;
        internal string UpgradeClientSha256;
        internal string UpgradeVerifierSha256;
        internal string UpgradeProbeSha256;
        internal string ProvisioningScriptSha256;
        internal string InstallerScriptSha256;
        internal string ProvisioningNonce;
        internal string TransitionNonce;
        internal string TransitionPlanSha256;
        internal string AuthorizationExpiresAt;
        internal string SourceCommit;
        internal string SourceTree;
        internal string Unit1Commit;
        internal string Unit1Tree;
        internal string TargetCommit;
        internal string TargetTree;
        internal string OldBinarySha256;
        internal string OldPolicySha256;
        internal string OldInterface;
        internal string OldTrustSha256;
        internal string OldLedgerId;
        internal long OldLedgerSequence;
        internal string OldLedgerRoot;
        internal string OldCheckpointSha256;
        internal string HostIdentity;
        internal string PreflightBaselineSha256;
        internal string MinimumVersion;
        internal string[] OperationAllowlist;
        internal string[] RevokedHashes;
        internal R7Unit2Component[] Components;
        internal SortedDictionary<string, object> AuthorityBindings;
        internal SortedDictionary<string, object> TargetBindings;
        internal SortedDictionary<string, object> RollbackConstraints;
        internal SortedDictionary<string, object> ThreatModel;
        internal SortedDictionary<string, object> Raw;

#if UNIT2_SERVICE
        internal static R7Unit2UpgradePolicy LoadForService()
        {
            return Load(R7Unit2BuildIdentity.PolicySha256, R7Unit2BuildIdentity.PublicCertificateSha256, true);
        }
#endif

        internal static R7Unit2UpgradePolicy LoadPublic(string expectedCertificateSha256)
        {
            return Load(null, expectedCertificateSha256, false);
        }

        private static R7Unit2UpgradePolicy Load(string expectedPolicySha256, string expectedCertificateSha256, bool requireEmbeddedPolicy)
        {
            using (R7VerifiedFile file = R7SafeFile.Open(R7Fixed.UpgradePolicyPath, R7Fixed.UpgradePolicyPath, R7Fixed.UpgradeConfigRoot, expectedPolicySha256, R7Fixed.SystemSid, null, null))
            {
                SortedDictionary<string, object> raw = RequireObject(R7Json.ParseCanonicalObject(file.Bytes));
                R7Json.ExactKeys(raw,
                    "artifact_type", "authority_bindings", "authorization_expiration", "authorization_scope_sha256", "bootstrap_authority",
                    "dependency_manifest_sha256", "fixed_roots", "host_binding", "installer_script_sha256", "interface_version", "key",
                    "ledger_id", "minimum_terminal_version", "operation_allowlist", "preflight_baseline_sha256", "protocol_version", "provisioning_nonce",
                    "provisioning_script_sha256", "public_certificate_sha256", "required_components", "revoked_component_sha256",
                    "rollback_constraints", "schema_version", "service", "source_bindings", "target_bindings", "threat_model",
                    "transition_nonce", "transition_plan_sha256", "upgrade_client_sha256", "upgrade_probe_sha256", "upgrade_public_verifier_sha256", "volume_identity");
                if (!String.Equals(R7Json.String(raw, "artifact_type", 1, 256), "R7_UNIT2_SEPARATE_UPGRADE_AUTHORITY_POLICY", StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(raw, "bootstrap_authority", 1, 256), "EXPLICIT_R7_REMEDIATION_UNIT_2_AUTHORIZATION", StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(raw, "interface_version", 1, 64), "1.0.0", StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(raw, "protocol_version", 1, 64), R7Fixed.ProtocolVersion, StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(raw, "schema_version", 1, 64), "2.0.0", StringComparison.Ordinal)) throw new R7ProtocolException("UNIT2_POLICY_IDENTITY_INVALID");
                string certificate = Sha(raw, "public_certificate_sha256");
                if (!R7Hash.FixedTimeEquals(certificate, expectedCertificateSha256)) throw new R7ProtocolException("UNIT2_PUBLIC_TRUST_IDENTITY_MISMATCH");
                if (requireEmbeddedPolicy && !R7Hash.FixedTimeEquals(file.Measurement.Sha256, expectedPolicySha256)) throw new R7ProtocolException("UNIT2_POLICY_EMBEDDED_IDENTITY_MISMATCH");

                SortedDictionary<string, object> service = R7Json.Child(raw, "service");
                R7Json.ExactKeys(service, "account", "denied_logon_rights", "name", "pipe", "required_privileges", "sid", "sid_type");
                if (!String.Equals(R7Json.String(service, "name", 1, 128), R7Fixed.UpgradeService, StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(service, "account", 1, 256), "NT SERVICE\\" + R7Fixed.UpgradeService, StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(service, "sid", 1, 256), R7Fixed.UpgradeSid, StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(service, "sid_type", 1, 64), "RESTRICTED", StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(service, "pipe", 1, 256), R7Fixed.UpgradePipe, StringComparison.Ordinal)) throw new R7ProtocolException("UNIT2_SERVICE_POLICY_INVALID");
                RequireExactStrings(R7Json.Array(service, "required_privileges"), new string[] { "SeChangeNotifyPrivilege" }, "UNIT2_PRIVILEGE_POLICY_INVALID");
                RequireExactStrings(R7Json.Array(service, "denied_logon_rights"), new string[] { "SeDenyInteractiveLogonRight", "SeDenyRemoteInteractiveLogonRight" }, "UNIT2_LOGON_POLICY_INVALID");

                string[] operations = Strings(R7Json.Array(raw, "operation_allowlist"));
                RequireExactStrings(operations, new string[] { "AUTHORIZE_TERMINAL_TRANSITION", "GET_AUTHORIZATION", "GET_HEALTH", "GET_PUBLIC_IDENTITY" }, "UNIT2_OPERATION_ALLOWLIST_INVALID");
                string[] roots = Strings(R7Json.Array(raw, "fixed_roots"));
                foreach (string required in new string[] { R7Fixed.UpgradeInstallRoot, R7Fixed.UpgradeConfigRoot, R7Fixed.UpgradeLedgerRoot, R7Fixed.UpgradeTrustRoot, R7Fixed.UpgradeEvidenceRoot, R7Fixed.UpgradeResponseRoot }) if (Array.IndexOf(roots, required) < 0) throw new R7ProtocolException("UNIT2_FIXED_ROOT_MISSING", required);

                SortedDictionary<string, object> key = R7Json.Child(raw, "key");
                R7Json.ExactKeys(key, "algorithm", "export_policy", "key_unique_name", "provider", "scope", "signature_algorithm");
                if (!String.Equals(R7Json.String(key, "provider", 1, 256), "Microsoft Software Key Storage Provider", StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(key, "scope", 1, 64), "LocalMachine", StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(key, "algorithm", 1, 64), "RSA-3072", StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(key, "signature_algorithm", 1, 64), R7Fixed.SignatureAlgorithm, StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(key, "export_policy", 1, 64), "NONEXPORTABLE", StringComparison.Ordinal)) throw new R7ProtocolException("UNIT2_KEY_POLICY_INVALID");

                SortedDictionary<string, object> source = R7Json.Child(raw, "source_bindings");
                R7Json.ExactKeys(source, "provisioning_commit", "provisioning_tree", "target_commit", "target_tree", "unit1_commit", "unit1_tree");
                SortedDictionary<string, object> host = R7Json.Child(raw, "host_binding");
                R7Json.ExactKeys(host, "checkpoint_sha256", "host_identity", "terminal_interface", "terminal_ledger_id", "terminal_ledger_root", "terminal_ledger_sequence", "terminal_policy_sha256", "terminal_public_trust_sha256", "terminal_service_binary_sha256", "terminal_service_name", "terminal_service_sid", "volume_identity");
                if (!String.Equals(R7Json.String(host, "terminal_service_name", 1, 128), R7Fixed.TerminalService, StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(host, "terminal_service_sid", 1, 256), R7Fixed.TerminalSid, StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(host, "terminal_ledger_id", 64, 64), R7Fixed.LedgerId, StringComparison.Ordinal)) throw new R7ProtocolException("UNIT2_HOST_POLICY_INVALID");

                List<R7Unit2Component> components = new List<R7Unit2Component>();
                HashSet<string> roles = new HashSet<string>(StringComparer.Ordinal);
                foreach (object itemRaw in R7Json.Array(raw, "required_components"))
                {
                    SortedDictionary<string, object> item = RequireObject(itemRaw);
                    R7Json.ExactKeys(item, "final_path", "role", "sha256", "staging_relative_path");
                    R7Unit2Component component = new R7Unit2Component
                    {
                        FinalPath = R7Json.String(item, "final_path", 3, 4096),
                        RelativePath = R7Json.String(item, "staging_relative_path", 1, 2048),
                        Role = R7Json.String(item, "role", 1, 256),
                        Sha256 = Sha(item, "sha256")
                    };
                    if (!roles.Add(component.Role) || Path.IsPathRooted(component.RelativePath) || component.RelativePath.IndexOf("..", StringComparison.Ordinal) >= 0) throw new R7ProtocolException("UNIT2_COMPONENT_POLICY_INVALID");
                    components.Add(component);
                }
                foreach (string role in new string[] { "TERMINAL_SIGNER", "EXECUTION", "OBSERVATION", "COMPARATOR", "PUBLIC_VERIFIER", "AUTHORITY_VERIFIER", "ADVERSARIAL_HARNESS", "STATIC_VERIFIER", "TERMINAL_POLICY", "DEPENDENCY_MANIFEST", "BUILD_RECEIPT", "INSTALLER_TOOL", "AUTHORITY_PACKAGE_MANIFEST" }) if (!roles.Contains(role)) throw new R7ProtocolException("UNIT2_COMPONENT_ROLE_MISSING", role);

                string[] revoked = Strings(R7Json.Array(raw, "revoked_component_sha256"));
                foreach (string value in revoked) if (!R7Hash.IsLowerSha256(value)) throw new R7ProtocolException("UNIT2_REVOKED_HASH_INVALID");
                DateTimeOffset expiration;
                string expirationText = R7Json.String(raw, "authorization_expiration", 28, 28);
                if (!DateTimeOffset.TryParseExact(expirationText, "yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out expiration)) throw new R7ProtocolException("UNIT2_EXPIRATION_INVALID");

                return new R7Unit2UpgradePolicy
                {
                    Sha256 = file.Measurement.Sha256,
                    AuthorizationScopeSha256 = Sha(raw, "authorization_scope_sha256"),
                    PublicCertificateSha256 = certificate,
                    DependencyManifestSha256 = Sha(raw, "dependency_manifest_sha256"),
                    KeyUniqueName = R7Json.String(key, "key_unique_name", 1, 512),
                    LedgerId = Sha(raw, "ledger_id"),
                    VolumeIdentity = R7Json.String(raw, "volume_identity", 8, 64),
                    UpgradeClientSha256 = Sha(raw, "upgrade_client_sha256"),
                    UpgradeProbeSha256 = Sha(raw, "upgrade_probe_sha256"),
                    UpgradeVerifierSha256 = Sha(raw, "upgrade_public_verifier_sha256"),
                    ProvisioningScriptSha256 = Sha(raw, "provisioning_script_sha256"),
                    InstallerScriptSha256 = Sha(raw, "installer_script_sha256"),
                    ProvisioningNonce = CanonicalGuid(R7Json.String(raw, "provisioning_nonce", 36, 36)),
                    TransitionNonce = CanonicalGuid(R7Json.String(raw, "transition_nonce", 36, 36)),
                    TransitionPlanSha256 = Sha(raw, "transition_plan_sha256"),
                    AuthorizationExpiresAt = expirationText,
                    SourceCommit = R7Json.String(source, "provisioning_commit", 40, 40),
                    SourceTree = R7Json.String(source, "provisioning_tree", 40, 40),
                    Unit1Commit = R7Json.String(source, "unit1_commit", 40, 40),
                    Unit1Tree = R7Json.String(source, "unit1_tree", 40, 40),
                    TargetCommit = R7Json.String(source, "target_commit", 40, 40),
                    TargetTree = R7Json.String(source, "target_tree", 40, 40),
                    OldBinarySha256 = Sha(host, "terminal_service_binary_sha256"),
                    OldPolicySha256 = Sha(host, "terminal_policy_sha256"),
                    OldInterface = R7Json.String(host, "terminal_interface", 1, 128),
                    OldTrustSha256 = Sha(host, "terminal_public_trust_sha256"),
                    OldLedgerId = Sha(host, "terminal_ledger_id"),
                    OldLedgerSequence = R7Json.Integer(host, "terminal_ledger_sequence", 1, Int64.MaxValue),
                    OldLedgerRoot = Sha(host, "terminal_ledger_root"),
                    OldCheckpointSha256 = Sha(host, "checkpoint_sha256"),
                    HostIdentity = Sha(host, "host_identity"),
                    PreflightBaselineSha256 = Sha(raw, "preflight_baseline_sha256"),
                    MinimumVersion = R7Json.String(raw, "minimum_terminal_version", 1, 128),
                    OperationAllowlist = operations,
                    RevokedHashes = revoked,
                    Components = components.ToArray(),
                    AuthorityBindings = R7Json.Child(raw, "authority_bindings"),
                    TargetBindings = R7Json.Child(raw, "target_bindings"),
                    RollbackConstraints = R7Json.Child(raw, "rollback_constraints"),
                    ThreatModel = R7Json.Child(raw, "threat_model"),
                    Raw = raw
                };
            }
        }

        internal R7Unit2Component Component(string role)
        {
            foreach (R7Unit2Component component in Components) if (String.Equals(component.Role, role, StringComparison.Ordinal)) return component;
            throw new R7ProtocolException("UNIT2_COMPONENT_UNRESOLVED", role);
        }

        private static string Sha(IDictionary<string, object> row, string name)
        {
            string value = R7Json.String(row, name, 64, 64);
            if (!R7Hash.IsLowerSha256(value)) throw new R7ProtocolException("UNIT2_SHA256_INVALID", name);
            return value;
        }

        internal static string CanonicalGuid(string value)
        {
            Guid parsed;
            if (!Guid.TryParseExact(value, "D", out parsed) || !String.Equals(parsed.ToString("D"), value, StringComparison.Ordinal)) throw new R7ProtocolException("UNIT2_GUID_INVALID");
            return value;
        }

        internal static SortedDictionary<string, object> RequireObject(object value)
        {
            SortedDictionary<string, object> result = value as SortedDictionary<string, object>;
            if (result == null) throw new R7ProtocolException("UNIT2_OBJECT_REQUIRED");
            return result;
        }

        private static string[] Strings(object[] values)
        {
            string[] result = new string[values.Length];
            for (int index = 0; index < values.Length; index++) { result[index] = values[index] as string; if (result[index] == null) throw new R7ProtocolException("UNIT2_STRING_ARRAY_REQUIRED"); }
            return result;
        }

        private static void RequireExactStrings(object[] values, string[] expected, string code)
        {
            RequireExactStrings(Strings(values), expected, code);
        }

        private static void RequireExactStrings(string[] values, string[] expected, string code)
        {
            string[] left = (string[])values.Clone();
            string[] right = (string[])expected.Clone();
            Array.Sort(left, StringComparer.Ordinal); Array.Sort(right, StringComparer.Ordinal);
            if (left.Length != right.Length) throw new R7ProtocolException(code);
            for (int index = 0; index < left.Length; index++) if (!String.Equals(left[index], right[index], StringComparison.Ordinal)) throw new R7ProtocolException(code);
        }
    }

#if UNIT2_SERVICE
    internal sealed class R7Unit2SafeServiceHandle : SafeHandleZeroOrMinusOneIsInvalid
    {
        private R7Unit2SafeServiceHandle() : base(true) { }
        [DllImport("advapi32.dll", SetLastError = true)] private static extern bool CloseServiceHandle(IntPtr serviceHandle);
        protected override bool ReleaseHandle() { return CloseServiceHandle(handle); }
    }

    internal static class R7Unit2Isolation
    {
        private const uint GenericWrite = 0x40000000;
        private const uint ShareRead = 0x00000001;
        private const uint ShareWrite = 0x00000002;
        private const uint ShareDelete = 0x00000004;
        private const uint OpenExisting = 3;
        private const uint OpenReparsePoint = 0x00200000;
        private const uint BackupSemantics = 0x02000000;
        private const uint ScManagerConnect = 0x0001;
        private const uint ServiceChangeConfig = 0x0002;
        private const int ErrorAccessDenied = 5;

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern SafeFileHandle CreateFileW(string name, uint access, uint share, IntPtr security, uint disposition, uint flags, IntPtr template);
        [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern R7Unit2SafeServiceHandle OpenSCManagerW(string machine, string database, uint access);
        [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern R7Unit2SafeServiceHandle OpenServiceW(R7Unit2SafeServiceHandle manager, string serviceName, uint access);

        internal static void AssertDirectoryWriteDenied(string fixedPath)
        {
            using (SafeFileHandle handle = CreateFileW(Path.GetFullPath(fixedPath), GenericWrite, ShareRead | ShareWrite | ShareDelete, IntPtr.Zero, OpenExisting, BackupSemantics | OpenReparsePoint, IntPtr.Zero))
            {
                if (!handle.IsInvalid) throw new SecurityException("UNIT2_FORBIDDEN_DIRECTORY_WRITE_OPEN_SUCCEEDED|" + fixedPath);
                int error = Marshal.GetLastWin32Error();
                if (error != ErrorAccessDenied) throw new Win32Exception(error, "UNIT2_DIRECTORY_WRITE_DENIAL_NOT_ESTABLISHED|" + fixedPath);
            }
        }

        internal static void AssertTerminalServiceConfigurationDenied()
        {
            using (R7Unit2SafeServiceHandle manager = OpenSCManagerW(null, null, ScManagerConnect))
            {
                if (manager.IsInvalid) throw new Win32Exception(Marshal.GetLastWin32Error(), "UNIT2_SCM_CONNECT_FAILED");
                using (R7Unit2SafeServiceHandle service = OpenServiceW(manager, R7Fixed.TerminalService, ServiceChangeConfig))
                {
                    if (!service.IsInvalid) throw new SecurityException("UNIT2_TERMINAL_SERVICE_CHANGE_CONFIG_OPEN_SUCCEEDED");
                    int error = Marshal.GetLastWin32Error();
                    if (error != ErrorAccessDenied) throw new Win32Exception(error, "UNIT2_TERMINAL_SERVICE_CHANGE_CONFIG_DENIAL_NOT_ESTABLISHED");
                }
            }
        }

        internal static void AssertTerminalKeyOpenDenied()
        {
            try { using (RSA forbidden = R7Crypto.LoadTerminalSigner()) { } }
            catch (CryptographicException) { return; }
            catch (UnauthorizedAccessException) { return; }
            throw new SecurityException("UNIT2_TERMINAL_KEY_OPEN_SUCCEEDED");
        }
    }

    internal sealed class R7Unit2UpgradeProcessor : R7PipeProcessor
    {
        private readonly object sync = new object();
        private readonly R7Unit2UpgradePolicy policy;
        private readonly X509Certificate2 publicCertificate;
        private readonly RSA verifier;
        private readonly RSA signer;
        private readonly R7VerifiedMetadataFile keyFile;
        private readonly R7VerifiedFile serviceBinary;
        private readonly R7DependencyClosure dependencies;
        private readonly R7ObjectStore objects;
        private readonly R7VersionedLedger ledger;
        private readonly string buildReceiptSha256;
        private readonly bool privateExportRejected;
        private readonly R7CallerIdentity serviceProcessIdentity;
        private string provisioningAttestationIdentity;

        internal R7Unit2UpgradeProcessor()
        {
            string currentSid = WindowsIdentity.GetCurrent().User.Value;
            if (!String.Equals(currentSid, R7Fixed.UpgradeSid, StringComparison.Ordinal)) throw new SecurityException("UNIT2_UPGRADE_SERVICE_SID_MISMATCH");
            uint serviceParentProcessId;
            serviceProcessIdentity = R7NativeCaller.CaptureProcess((uint)System.Diagnostics.Process.GetCurrentProcess().Id, out serviceParentProcessId);
            if (!String.Equals(serviceProcessIdentity.UserSid, R7Fixed.UpgradeSid, StringComparison.Ordinal) ||
                serviceProcessIdentity.ContainsTerminalSignerSid ||
                Array.IndexOf(serviceProcessIdentity.GroupSids, "S-1-5-32-544") >= 0 ||
                serviceProcessIdentity.Privileges.Length != 1 ||
                !serviceProcessIdentity.Privileges[0].StartsWith("SeChangeNotifyPrivilege:", StringComparison.Ordinal)) throw new SecurityException("UNIT2_EFFECTIVE_TOKEN_NOT_MINIMAL");
            policy = R7Unit2UpgradePolicy.LoadForService();
            if (!String.Equals(policy.SourceCommit, R7Unit2BuildIdentity.SourceCommit, StringComparison.Ordinal) ||
                !String.Equals(policy.SourceTree, R7Unit2BuildIdentity.SourceTree, StringComparison.Ordinal) ||
                !R7Hash.FixedTimeEquals(policy.DependencyManifestSha256, R7Unit2BuildIdentity.DependencyManifestSha256)) throw new SecurityException("UNIT2_BUILD_IDENTITY_MISMATCH");
            dependencies = new R7DependencyClosure(R7Fixed.UpgradeDependencyManifestPath, policy.DependencyManifestSha256, R7Fixed.UpgradeInstallRoot);
            publicCertificate = R7Crypto.LoadPublicCertificate(R7Fixed.UpgradePublicCertificatePath, policy.PublicCertificateSha256, R7Fixed.UpgradeTrustRoot);
            verifier = RSACertificateExtensions.GetRSAPublicKey(publicCertificate);
            if (verifier == null || verifier.KeySize != 3072) throw new CryptographicException("UNIT2_PUBLIC_RSA3072_REQUIRED");
            keyFile = R7SafeFile.HoldMetadataFile(R7Unit2BuildIdentity.KeyFilePath, R7Unit2BuildIdentity.KeyFilePath, Path.GetDirectoryName(R7Unit2BuildIdentity.KeyFilePath), R7Unit2BuildIdentity.KeyFileOwnerSid, R7Unit2BuildIdentity.KeyFileSecurityDescriptorSha256, R7Unit2BuildIdentity.KeyFileVolumeIdentity, R7Unit2BuildIdentity.KeyFileIdentity, R7Unit2BuildIdentity.KeyFileLinkCount);
            signer = R7Crypto.LoadMachineSigner(policy.KeyUniqueName, 3072);
            privateExportRejected = VerifyPrivateExportRejected(signer);
            string executable = Path.GetFullPath(Assembly.GetExecutingAssembly().Location);
            string expectedExecutable = Path.Combine(R7Fixed.UpgradeInstallRoot, "RandleTerminalUpgradeAuthority.exe");
            serviceBinary = R7SafeFile.Open(executable, expectedExecutable, R7Fixed.UpgradeInstallRoot, null, R7Fixed.SystemSid, null, policy.VolumeIdentity);
            buildReceiptSha256 = VerifyBuildReceipt(serviceBinary.Measurement.Sha256);
            R7Unit2Isolation.AssertDirectoryWriteDenied(@"C:\Webhook\RandleSystem");
            R7Unit2Isolation.AssertDirectoryWriteDenied(R7Fixed.LedgerRoot);
            R7Unit2Isolation.AssertDirectoryWriteDenied(R7Fixed.LegacyReceiptRoot);
            R7Unit2Isolation.AssertDirectoryWriteDenied(R7Fixed.TerminalTrustRoot);
            R7Unit2Isolation.AssertTerminalServiceConfigurationDenied();
            R7Unit2Isolation.AssertTerminalKeyOpenDenied();
            objects = new R7ObjectStore(R7Fixed.UpgradeObjectRoot, R7Fixed.UpgradeSid, policy.VolumeIdentity);
            string genesisIdentity = objects.Put(R7Json.Object(
                "artifact_type", "R7_UNIT2_UPGRADE_LEDGER_GENESIS_MANIFEST",
                "binary_sha256", serviceBinary.Measurement.Sha256,
                "build_receipt_sha256", buildReceiptSha256,
                "dependency_manifest_sha256", policy.DependencyManifestSha256,
                "ledger_id", policy.LedgerId,
                "policy_sha256", policy.Sha256,
                "public_key_identity", policy.PublicCertificateSha256,
                "schema_version", "1.0.0",
                "service_sid", R7Fixed.UpgradeSid,
                "source_commit", policy.SourceCommit,
                "source_tree", policy.SourceTree));
            ledger = new R7VersionedLedger(R7Fixed.UpgradeLedgerRoot, policy.LedgerId, policy.PublicCertificateSha256, R7Fixed.UpgradeSid, signer, verifier, true, genesisIdentity);
            RecoverCheckpointIfRequired();
            EnsureProvisioningAttestation();
            AppendStartupRecord();
            dependencies.VerifyNoNewModules();
        }

        internal override SortedDictionary<string, object> Process(R7RequestContext context, SortedDictionary<string, object> request)
        {
            dependencies.VerifyNoNewModules();
            try
            {
                R7Json.ExactKeys(request, "interface_version", "operation", "payload", "protocol_version", "request_identity");
                if (!String.Equals(R7Json.String(request, "interface_version", 1, 64), "1.0.0", StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(request, "protocol_version", 1, 64), R7Fixed.ProtocolVersion, StringComparison.Ordinal)) throw new R7ProtocolException("INTERFACE_VERSION_REJECTED");
                string operation = R7Json.String(request, "operation", 1, 128);
                if (Array.IndexOf(policy.OperationAllowlist, operation) < 0) throw new R7ProtocolException("OPERATION_NOT_ALLOWED");
                SortedDictionary<string, object> payload = R7Json.Child(request, "payload");
                string requestIdentity = R7Unit2UpgradePolicy.CanonicalGuid(R7Json.String(request, "request_identity", 36, 36));
                string expectedRequestIdentity = DeterministicRequestIdentity(operation, payload);
                if (!String.Equals(requestIdentity, expectedRequestIdentity, StringComparison.Ordinal)) throw new R7ProtocolException("REQUEST_IDENTITY_NOT_CANONICAL");
                RequirePublic(context.Caller);
                if (operation == "GET_HEALTH") { R7Json.ExactKeys(payload); return Health(); }
                if (operation == "GET_PUBLIC_IDENTITY") { R7Json.ExactKeys(payload); return PublicIdentity(); }
                if (operation == "GET_AUTHORIZATION") return GetAuthorization(payload);
                if (operation == "AUTHORIZE_TERMINAL_TRANSITION") ValidateAuthorizationRequest(payload);
                lock (sync)
                {
                    if (operation == "AUTHORIZE_TERMINAL_TRANSITION") { RequireMeasuredOperatorClient(context.Caller); return Authorize(context, requestIdentity, payload); }
                }
                throw new R7ProtocolException("OPERATION_NOT_ALLOWED");
            }
            catch (R7ProtocolException exception) { return Rejection(exception.Code); }
            catch (SecurityException exception) { return Rejection(String.IsNullOrEmpty(exception.Message) ? "CALLER_NOT_AUTHORIZED" : exception.Message); }
            finally { dependencies.VerifyNoNewModules(); }
        }

        public override void Dispose()
        {
            dependencies.Dispose();
            signer.Dispose();
            keyFile.Dispose();
            serviceBinary.Dispose();
            verifier.Dispose();
            publicCertificate.Dispose();
        }

        private SortedDictionary<string, object> Health()
        {
            SortedDictionary<string, object> response = Success("UPGRADE_AUTHORITY_HEALTHY");
            response.Add("binary_sha256", serviceBinary.Measurement.Sha256);
            response.Add("ledger_id", policy.LedgerId);
            response.Add("ledger_root", ledger.RootHash);
            response.Add("ledger_sequence", ledger.Sequence);
            response.Add("policy_sha256", policy.Sha256);
            response.Add("private_export_rejected", privateExportRejected);
            response.Add("provisioning_attestation_identity", provisioningAttestationIdentity);
            response.Add("public_key_identity", policy.PublicCertificateSha256);
            response.Add("service_sid", R7Fixed.UpgradeSid);
            response.Add("service_token_identity", R7Hash.Bytes(R7Json.Encode(serviceProcessIdentity.ToJson())));
            return response;
        }

        private SortedDictionary<string, object> PublicIdentity()
        {
            SortedDictionary<string, object> response = Success("UPGRADE_PUBLIC_IDENTITY_RESOLVED");
            response.Add("authorization_scope_sha256", policy.AuthorizationScopeSha256);
            response.Add("ledger_id", policy.LedgerId);
            response.Add("operation_allowlist", Objects(policy.OperationAllowlist));
            response.Add("pipe", R7Fixed.UpgradePipe);
            response.Add("policy_sha256", policy.Sha256);
            response.Add("provisioning_attestation_identity", provisioningAttestationIdentity);
            response.Add("public_key_identity", policy.PublicCertificateSha256);
            response.Add("service_sid", R7Fixed.UpgradeSid);
            response.Add("target_source_commit", policy.TargetCommit);
            response.Add("transition_nonce", policy.TransitionNonce);
            return response;
        }

        private SortedDictionary<string, object> Authorize(R7RequestContext context, string requestIdentity, SortedDictionary<string, object> payload)
        {
            ValidateAuthorizationRequest(payload);
            string nonce = R7Unit2UpgradePolicy.CanonicalGuid(R7Json.String(payload, "transition_nonce", 36, 36));
            string plan = R7Json.String(payload, "transition_plan_sha256", 64, 64);
            string responsePath = Path.Combine(R7Fixed.UpgradeResponseRoot, requestIdentity + ".response.json");
            R7VerifiedFile existingResponse;
            if (R7SafeFile.TryOpen(responsePath, responsePath, R7Fixed.UpgradeResponseRoot, null, R7Fixed.UpgradeSid, null, policy.VolumeIdentity, out existingResponse))
            {
                using (existingResponse) return R7Json.ParseCanonicalObject(existingResponse.Bytes);
            }
            string authorizationPath = Path.Combine(R7Fixed.UpgradeAuthorizationRoot, nonce + ".authorization.json");
            R7VerifiedFile prepared;
            if (R7SafeFile.TryOpen(authorizationPath, authorizationPath, R7Fixed.UpgradeAuthorizationRoot, null, R7Fixed.UpgradeSid, null, policy.VolumeIdentity, out prepared))
            {
                prepared.Dispose();
                return RecoverCommittedAuthorization(context, requestIdentity, responsePath, authorizationPath);
            }
            if (ledger.Find("UPGRADE_TRANSITION_AUTHORIZATION_RESERVED", nonce).Length != 0 || ledger.Find("UPGRADE_TRANSITION_AUTHORIZED", nonce).Length != 0) throw new R7ProtocolException("TRANSITION_NONCE_REPLAY");
            DateTimeOffset expiration = DateTimeOffset.ParseExact(policy.AuthorizationExpiresAt, "yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal);
            if (DateTimeOffset.UtcNow >= expiration) throw new R7ProtocolException("TRANSITION_AUTHORIZATION_EXPIRED");
            if (Directory.Exists(R7Fixed.UpgradeActivationRoot) && Directory.GetFileSystemEntries(R7Fixed.UpgradeActivationRoot).Length != 0) throw new R7ProtocolException("TERMINAL_INSTALLATION_MARKER_PRESENT");

            SortedDictionary<string, object> currentState = VerifyCurrentTerminalState();
            List<object> measuredComponents = MeasureFixedTargetComponents();
            string requestPayloadIdentity = R7Hash.Bytes(R7Json.Encode(payload));
            string requestEvidenceIdentity = objects.Put(R7Json.Object(
                "artifact_type", "R7_UNIT2_TRANSITION_REQUEST_EVIDENCE",
                "caller", context.Caller.ToJson(),
                "request_frame", Convert.ToBase64String(context.RequestFrame),
                "request_frame_sha256", context.RequestFrameSha256,
                "request_identity", requestIdentity,
                "request_payload_identity", requestPayloadIdentity,
                "schema_version", "1.0.0",
                "transition_nonce", nonce));
            ledger.Append("UPGRADE_TRANSITION_AUTHORIZATION_RESERVED", StateNonce(requestIdentity, "RESERVED"), nonce, requestEvidenceIdentity, "1.0.0");

            SortedDictionary<string, object> authorizationPayload = R7Json.Object(
                "anti_downgrade", R7Json.Object("minimum_terminal_version", policy.MinimumVersion, "prohibited_component_sha256", Objects(policy.RevokedHashes)),
                "authority_bindings", policy.AuthorityBindings,
                "authority_class", "TERMINAL_TRANSITION_PREINSTALL_AUTHORIZATION",
                "authorization_expiration", policy.AuthorizationExpiresAt,
                "authorization_time", DateTimeOffset.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture),
                "components", measuredComponents.ToArray(),
                "consumption_state", "PENDING_FUTURE_SEPARATE_UNIT",
                "current_state", currentState,
                "disposition", "AUTHORIZED FOR FUTURE INSTALLATION CONSIDERATION",
                "host_bound", true,
                "installation_performed", false,
                "one_time_use", true,
                "operation", "AUTHORIZE_TERMINAL_TRANSITION",
                "request_frame_sha256", context.RequestFrameSha256,
                "request_identity", requestIdentity,
                "request_payload_identity", requestPayloadIdentity,
                "revocation_state", "ACTIVE",
                "rollback_constraints", policy.RollbackConstraints,
                "schema_version", "2.0.0",
                "target_bindings", policy.TargetBindings,
                "target_source_commit", policy.TargetCommit,
                "target_source_tree", policy.TargetTree,
                "transition_nonce", nonce,
                "transition_plan_sha256", policy.TransitionPlanSha256,
                "upgrade_authority_may_install", false);
            byte[] authorizationBytes = R7Json.Encode(R7Crypto.Envelope(authorizationPayload, policy.PublicCertificateSha256, signer));
            string authorizationIdentity = R7Hash.Bytes(authorizationBytes);
            R7DurableFile.CreateNew(authorizationPath, authorizationBytes);
            R7LedgerAppend commit = ledger.Append("UPGRADE_TRANSITION_AUTHORIZED", StateNonce(requestIdentity, "COMMITTED"), nonce, authorizationIdentity, "2.0.0");
            SortedDictionary<string, object> response = AuthorizationResponse(authorizationIdentity, commit.Record, requestIdentity, nonce);
            byte[] responseBytes = R7Json.Encode(response);
            R7DurableFile.CreateNew(responsePath, responseBytes);
            string responseIdentity = R7Hash.Bytes(responseBytes);
            string responseRecord = objects.Put(R7Json.Object("authorization_identity", authorizationIdentity, "request_identity", requestIdentity, "response_identity", responseIdentity, "schema_version", "1.0.0", "transition_nonce", nonce));
            ledger.Append("UPGRADE_TRANSITION_RESPONSE_AVAILABLE", StateNonce(requestIdentity, "RESPONSE_AVAILABLE"), nonce, responseRecord, "1.0.0");
            return response;
        }

        private void ValidateAuthorizationRequest(SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "transition_nonce", "transition_plan_sha256");
            string nonce = R7Unit2UpgradePolicy.CanonicalGuid(R7Json.String(payload, "transition_nonce", 36, 36));
            string plan = R7Json.String(payload, "transition_plan_sha256", 64, 64);
            if (!String.Equals(nonce, policy.TransitionNonce, StringComparison.Ordinal) || !R7Hash.FixedTimeEquals(plan, policy.TransitionPlanSha256)) throw new R7ProtocolException("TRANSITION_PLAN_NOT_AUTHORIZED");
        }

        private SortedDictionary<string, object> RecoverCommittedAuthorization(R7RequestContext context, string requestIdentity, string responsePath, string authorizationPath)
        {
            SortedDictionary<string, object> authorization;
            string authorizationIdentity;
            using (R7VerifiedFile file = R7SafeFile.Open(authorizationPath, authorizationPath, R7Fixed.UpgradeAuthorizationRoot, null, R7Fixed.UpgradeSid, null, policy.VolumeIdentity))
            {
                authorizationIdentity = file.Measurement.Sha256;
                authorization = R7Crypto.VerifyEnvelope(file.Bytes, policy.PublicCertificateSha256, verifier);
            }
            if (!String.Equals(R7Json.String(authorization, "request_identity", 36, 36), requestIdentity, StringComparison.Ordinal) ||
                !R7Hash.FixedTimeEquals(R7Json.String(authorization, "request_frame_sha256", 64, 64), context.RequestFrameSha256)) throw new R7ProtocolException("CONFLICTING_TRANSITION_RETRY");
            R7LedgerRecord[] commits = ledger.Find("UPGRADE_TRANSITION_AUTHORIZED", policy.TransitionNonce);
            if (commits.Length != 1 || !String.Equals(commits[0].ContentAddress, authorizationIdentity, StringComparison.Ordinal)) throw new R7ProtocolException("PREPARED_AUTHORIZATION_NOT_COMMITTED");
            SortedDictionary<string, object> response = AuthorizationResponse(authorizationIdentity, commits[0], requestIdentity, policy.TransitionNonce);
            byte[] responseBytes = R7Json.Encode(response);
            R7DurableFile.CreateNew(responsePath, responseBytes);
            string responseRecord = objects.Put(R7Json.Object("authorization_identity", authorizationIdentity, "request_identity", requestIdentity, "response_identity", R7Hash.Bytes(responseBytes), "schema_version", "1.0.0", "transition_nonce", policy.TransitionNonce));
            if (ledger.Find("UPGRADE_TRANSITION_RESPONSE_AVAILABLE", policy.TransitionNonce).Length == 0) ledger.Append("UPGRADE_TRANSITION_RESPONSE_AVAILABLE", StateNonce(requestIdentity, "RESPONSE_AVAILABLE"), policy.TransitionNonce, responseRecord, "1.0.0");
            return response;
        }

        private SortedDictionary<string, object> GetAuthorization(SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "transition_nonce");
            string nonce = R7Unit2UpgradePolicy.CanonicalGuid(R7Json.String(payload, "transition_nonce", 36, 36));
            if (!String.Equals(nonce, policy.TransitionNonce, StringComparison.Ordinal)) throw new R7ProtocolException("AUTHORIZATION_NOT_FOUND");
            string path = Path.Combine(R7Fixed.UpgradeAuthorizationRoot, nonce + ".authorization.json");
            using (R7VerifiedFile file = R7SafeFile.Open(path, path, R7Fixed.UpgradeAuthorizationRoot, null, R7Fixed.UpgradeSid, null, policy.VolumeIdentity))
            {
                SortedDictionary<string, object> authorization = R7Crypto.VerifyEnvelope(file.Bytes, policy.PublicCertificateSha256, verifier);
                R7LedgerRecord[] commits = ledger.Find("UPGRADE_TRANSITION_AUTHORIZED", nonce);
                if (commits.Length != 1 || !String.Equals(commits[0].ContentAddress, file.Measurement.Sha256, StringComparison.Ordinal)) throw new R7ProtocolException("AUTHORIZATION_NOT_COMMITTED");
                SortedDictionary<string, object> response = Success("UPGRADE_AUTHORIZATION_RESOLVED");
                response.Add("authorization_identity", file.Measurement.Sha256);
                response.Add("authorization_record", Convert.ToBase64String(file.Bytes));
                response.Add("ledger_entry_identity", commits[0].EntryIdentity);
                response.Add("ledger_sequence", commits[0].Sequence);
                response.Add("transition_nonce", nonce);
                return response;
            }
        }

        private SortedDictionary<string, object> VerifyCurrentTerminalState()
        {
            string hostIdentity = R7Hash.Bytes(R7Json.Encode(R7Json.Object("terminal_ledger_id", policy.OldLedgerId, "terminal_public_trust_sha256", policy.OldTrustSha256, "terminal_service_sid", R7Fixed.TerminalSid, "volume_identity", policy.VolumeIdentity)));
            if (!R7Hash.FixedTimeEquals(hostIdentity, policy.HostIdentity)) throw new R7ProtocolException("CURRENT_HOST_IDENTITY_BINDING_INVALID");
            return R7Json.Object(
                "checkpoint_sha256", policy.OldCheckpointSha256,
                "consumption_remeasurement_required", true,
                "host_identity", hostIdentity,
                "issuance_measurement_mode", "IMMUTABLE_ELEVATED_PREFLIGHT_CAPTURE",
                "preflight_baseline_sha256", policy.PreflightBaselineSha256,
                "terminal_interface", policy.OldInterface,
                "terminal_ledger_id", policy.OldLedgerId,
                "terminal_ledger_root", policy.OldLedgerRoot,
                "terminal_ledger_sequence", policy.OldLedgerSequence,
                "terminal_policy_sha256", policy.OldPolicySha256,
                "terminal_public_trust_sha256", policy.OldTrustSha256,
                "terminal_service_binary_sha256", policy.OldBinarySha256,
                "terminal_service_name", R7Fixed.TerminalService,
                "terminal_service_sid", R7Fixed.TerminalSid,
                "volume_identity", policy.VolumeIdentity);
        }

        private List<object> MeasureFixedTargetComponents()
        {
            string stagingRoot = Path.Combine(R7Fixed.UpgradeStagingRoot, policy.TransitionNonce);
            R7SafeFile.MeasureDirectory(stagingRoot, stagingRoot, R7Fixed.SystemSid, null, policy.VolumeIdentity);
            List<object> measured = new List<object>();
            foreach (R7Unit2Component component in policy.Components)
            {
                if (Array.IndexOf(policy.RevokedHashes, component.Sha256) >= 0) throw new R7ProtocolException("REVOKED_TARGET_COMPONENT", component.Role);
                string stagePath = Path.Combine(stagingRoot, component.RelativePath.Replace('/', Path.DirectorySeparatorChar));
                using (R7VerifiedFile file = R7SafeFile.Open(stagePath, stagePath, stagingRoot, component.Sha256, R7Fixed.SystemSid, null, policy.VolumeIdentity))
                {
                    measured.Add(R7Json.Object(
                        "file_identity", file.Measurement.FileIdentity,
                        "final_path", component.FinalPath,
                        "final_path_preinstall_state", String.Equals(component.Role, "TERMINAL_SIGNER", StringComparison.Ordinal) ? "EXISTING_CURRENT_BINARY_REPLACEMENT_REQUIRES_CONSUMPTION_REMEASUREMENT" : "ABSENCE_BOUND_BY_PREFLIGHT_REQUIRES_CONSUMPTION_REMEASUREMENT",
                        "hard_link_count", (long)file.Measurement.LinkCount,
                        "role", component.Role,
                        "sha256", file.Measurement.Sha256,
                        "size", file.Measurement.Size,
                        "staging_relative_path", component.RelativePath,
                        "volume_identity", file.Measurement.VolumeIdentity));
                }
            }
            return measured;
        }

        private void EnsureProvisioningAttestation()
        {
            string path = Path.Combine(R7Fixed.UpgradeEvidenceRoot, policy.ProvisioningNonce + ".provisioning-attestation.json");
            R7LedgerRecord[] records = ledger.Find("UPGRADE_AUTHORITY_PROVISIONED", policy.ProvisioningNonce);
            R7VerifiedFile existing;
            if (R7SafeFile.TryOpen(path, path, R7Fixed.UpgradeEvidenceRoot, null, R7Fixed.UpgradeSid, null, policy.VolumeIdentity, out existing))
            {
                using (existing)
                {
                    R7Crypto.VerifyEnvelope(existing.Bytes, policy.PublicCertificateSha256, verifier);
                    if (records.Length != 1 || !String.Equals(records[0].ContentAddress, existing.Measurement.Sha256, StringComparison.Ordinal)) throw new InvalidDataException("UNIT2_PROVISIONING_ATTESTATION_LEDGER_MISMATCH");
                    provisioningAttestationIdentity = existing.Measurement.Sha256;
                    return;
                }
            }
            if (records.Length != 0) throw new InvalidDataException("UNIT2_PROVISIONING_ATTESTATION_MISSING");
            SortedDictionary<string, object> boundary = R7ServiceBoundary.MeasureOnly(R7Fixed.UpgradeService, R7Fixed.UpgradeSid, serviceBinary.Measurement.CanonicalPath);
            List<object> roots = new List<object>();
            foreach (string root in new string[] { R7Fixed.UpgradeInstallRoot, R7Fixed.UpgradeConfigRoot, R7Fixed.UpgradeLedgerRoot, R7Fixed.UpgradeTrustRoot, R7Fixed.UpgradeEvidenceRoot, R7Fixed.UpgradeResponseRoot, R7Fixed.UpgradeObjectRoot, R7Fixed.UpgradeAuthorizationRoot, R7Fixed.UpgradeRecoveryRoot, R7Fixed.UpgradeStagingRoot })
            {
                roots.Add(R7SafeFile.MeasureDirectory(root, root, R7Fixed.SystemSid, null, policy.VolumeIdentity).ToJson());
            }
            SortedDictionary<string, object> payload = R7Json.Object(
                "administrator_exclusion", true,
                "artifact_type", "R7_UNIT2_SIGNED_PROVISIONING_ATTESTATION",
                "authority_bindings", policy.AuthorityBindings,
                "authorization_scope_sha256", policy.AuthorizationScopeSha256,
                "binary_identity", serviceBinary.Measurement.ToJson(),
                "build_receipt_sha256", buildReceiptSha256,
                "dependency_manifest_sha256", policy.DependencyManifestSha256,
                "disposition", "UPGRADE_AUTHORITY_PROVISIONED_NO_TERMINAL_TRANSITION",
                "fixed_roots", roots.ToArray(),
                "interface_version", "1.0.0",
                "ipc_identity", R7Fixed.UpgradePipe,
                "isolation_probes", R7Json.Object("existing_terminal_key_open_denied", true, "existing_terminal_ledger_write_open_denied", true, "existing_terminal_receipt_write_open_denied", true, "existing_terminal_service_change_config_denied", true, "existing_terminal_trust_write_open_denied", true, "repository_write_open_denied", true),
                "key", R7Json.Object("algorithm", "RSA-3072", "export_policy", "NONEXPORTABLE", "file_identity", R7Unit2BuildIdentity.KeyFileIdentity, "file_security_descriptor_sha256", R7Unit2BuildIdentity.KeyFileSecurityDescriptorSha256, "key_unique_name", policy.KeyUniqueName, "private_export_rejected", privateExportRejected, "provider", "Microsoft Software Key Storage Provider", "scope", "LocalMachine", "signature_algorithm", R7Fixed.SignatureAlgorithm),
                "ledger_id", policy.LedgerId,
                "operation_allowlist", Objects(policy.OperationAllowlist),
                "principal", R7Json.Object("account", "NT SERVICE\\" + R7Fixed.UpgradeService, "administrator_member", false, "denied_logon_rights", new object[] { "SeDenyInteractiveLogonRight", "SeDenyRemoteInteractiveLogonRight" }, "required_privileges", new object[] { "SeChangeNotifyPrivilege" }, "service_sid", R7Fixed.UpgradeSid, "sid_type", "RESTRICTED"),
                "service_effective_token", serviceProcessIdentity.ToJson(),
                "preflight_baseline_sha256", policy.PreflightBaselineSha256,
                "provisioned_at", DateTimeOffset.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture),
                "provisioning_nonce", policy.ProvisioningNonce,
                "provisioning_script_sha256", policy.ProvisioningScriptSha256,
                "public_certificate_sha256", policy.PublicCertificateSha256,
                "schema_version", "2.0.0",
                "service_boundary_measurement_sha256", R7Hash.Bytes(R7Json.Encode(boundary)),
                "source_bindings", R7Json.Child(policy.Raw, "source_bindings"),
                "target_bindings", policy.TargetBindings,
                "terminal_authority_effect", "NONE",
                "threat_model", policy.ThreatModel,
                "transition_nonce", policy.TransitionNonce);
            byte[] bytes = R7Json.Encode(R7Crypto.Envelope(payload, policy.PublicCertificateSha256, signer));
            provisioningAttestationIdentity = R7Hash.Bytes(bytes);
            R7DurableFile.CreateNew(path, bytes);
            ledger.Append("UPGRADE_AUTHORITY_PROVISIONED", policy.ProvisioningNonce, policy.ProvisioningNonce, provisioningAttestationIdentity, "2.0.0");
        }

        private void AppendStartupRecord()
        {
            string content = objects.Put(R7Json.Object(
                "artifact_type", "R7_UNIT2_UPGRADE_SERVICE_START",
                "binary_sha256", serviceBinary.Measurement.Sha256,
                "ledger_root_before", ledger.RootHash,
                "ledger_sequence_before", ledger.Sequence,
                "policy_sha256", policy.Sha256,
                "process_id", (long)System.Diagnostics.Process.GetCurrentProcess().Id,
                "schema_version", "1.0.0",
                "service_sid", R7Fixed.UpgradeSid,
                "start_time", DateTimeOffset.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture)));
            ledger.Append("UPGRADE_AUTHORITY_SERVICE_STARTED", Guid.NewGuid().ToString("D"), policy.ProvisioningNonce, content, "1.0.0");
        }

        private void RecoverCheckpointIfRequired()
        {
            if (String.IsNullOrEmpty(ledger.CheckpointRecoveryReason)) return;
            R7CheckpointArtifact[] pending = ledger.PendingCheckpointArtifacts;
            object[] rows = new object[pending.Length];
            for (int index = 0; index < pending.Length; index++) rows[index] = R7Json.Object("identity", pending[index].Identity, "name", pending[index].Name);
            string subject = R7Hash.Bytes(R7Json.Encode(R7Json.Object("pending", rows, "reason", ledger.CheckpointRecoveryReason)));
            if (ledger.Find("UPGRADE_CHECKPOINT_RECOVERY_INTENT", subject).Length == 0)
            {
                string content = objects.Put(R7Json.Object("pending_checkpoint_artifacts", rows, "reason", ledger.CheckpointRecoveryReason, "recovery_subject", subject, "schema_version", "1.0.0"));
                ledger.Append("UPGRADE_CHECKPOINT_RECOVERY_INTENT", Guid.NewGuid().ToString("D"), subject, content, "1.0.0");
            }
            if (pending.Length != 0) ledger.PreservePendingCheckpoints(R7Fixed.UpgradeRecoveryRoot);
            if (!String.IsNullOrEmpty(ledger.CheckpointRecoveryReason)) ledger.RecoverCheckpoint("1.0.0");
            if (!String.IsNullOrEmpty(ledger.CheckpointRecoveryReason)) throw new R7DurabilityUncertainException("UNIT2_CHECKPOINT_RECOVERY_FAILED", null);
        }

        private string VerifyBuildReceipt(string binarySha256)
        {
            using (R7VerifiedFile file = R7SafeFile.Open(R7Fixed.UpgradeBuildReceiptPath, R7Fixed.UpgradeBuildReceiptPath, R7Fixed.UpgradeConfigRoot, null, R7Fixed.SystemSid, null, policy.VolumeIdentity))
            {
                SortedDictionary<string, object> receipt = R7Json.ParseCanonicalObject(file.Bytes);
                R7Json.ExactKeys(receipt, "artifact_type", "binaries", "compiler_options", "dependency_manifest_sha256", "governed_scripts", "policy_sha256", "schema_version", "source_commit", "source_files", "source_tree", "target_build_receipt_sha256", "target_source_commit", "target_source_tree", "toolchain");
                if (!String.Equals(R7Json.String(receipt, "artifact_type", 1, 256), "R7_UNIT2_UPGRADE_AUTHORITY_SOURCE_TO_BINARY_RECEIPT", StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(receipt, "source_commit", 40, 40), policy.SourceCommit, StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(receipt, "source_tree", 40, 40), policy.SourceTree, StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(receipt, "target_source_commit", 40, 40), policy.TargetCommit, StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(receipt, "target_source_tree", 40, 40), policy.TargetTree, StringComparison.Ordinal) ||
                    !R7Hash.FixedTimeEquals(R7Json.String(receipt, "policy_sha256", 64, 64), policy.Sha256) ||
                    !R7Hash.FixedTimeEquals(R7Json.String(receipt, "dependency_manifest_sha256", 64, 64), policy.DependencyManifestSha256)) throw new InvalidDataException("UNIT2_BUILD_RECEIPT_BINDING_INVALID");
                Dictionary<string, string> binaries = new Dictionary<string, string>(StringComparer.Ordinal);
                foreach (object raw in R7Json.Array(receipt, "binaries"))
                {
                    SortedDictionary<string, object> row = R7Unit2UpgradePolicy.RequireObject(raw);
                    R7Json.ExactKeys(row, "normalized_il_sha256", "raw_sha256", "role", "size");
                    string role = R7Json.String(row, "role", 1, 128);
                    string sha = R7Json.String(row, "raw_sha256", 64, 64);
                    if (!R7Hash.IsLowerSha256(sha) || binaries.ContainsKey(role)) throw new InvalidDataException("UNIT2_BUILD_BINARY_ROW_INVALID");
                    binaries.Add(role, sha);
                }
                if (binaries.Count != 4 || !R7Hash.FixedTimeEquals(binaries["UPGRADE_AUTHORITY"], binarySha256) || !R7Hash.FixedTimeEquals(binaries["UPGRADE_CLIENT"], policy.UpgradeClientSha256) || !R7Hash.FixedTimeEquals(binaries["UPGRADE_PUBLIC_VERIFIER"], policy.UpgradeVerifierSha256) || !R7Hash.FixedTimeEquals(binaries["UPGRADE_PROTOCOL_PROBE"], policy.UpgradeProbeSha256)) throw new InvalidDataException("UNIT2_BUILD_BINARY_SET_INVALID");
                return file.Measurement.Sha256;
            }
        }

        private void RequireMeasuredOperatorClient(R7CallerIdentity caller)
        {
            string expectedPath = Path.Combine(R7Fixed.UpgradeInstallRoot, "RandleTerminalUpgradeClient.exe");
            if (!String.Equals(caller.UserSid, R7Fixed.OperatorSid, StringComparison.Ordinal) && !String.Equals(caller.UserSid, R7Fixed.SystemSid, StringComparison.Ordinal)) throw new SecurityException("UPGRADE_CALLER_NOT_AUTHORIZED");
            if (!String.Equals(caller.ProcessPath, expectedPath, StringComparison.Ordinal) || !R7Hash.FixedTimeEquals(caller.ProcessSha256, policy.UpgradeClientSha256)) throw new SecurityException("UPGRADE_CALLER_EXECUTABLE_NOT_AUTHORIZED");
        }

        private static void RequirePublic(R7CallerIdentity caller)
        {
            if (!String.Equals(caller.UserSid, R7Fixed.OperatorSid, StringComparison.Ordinal) && !String.Equals(caller.UserSid, R7Fixed.SystemSid, StringComparison.Ordinal) && !String.Equals(caller.UserSid, R7Fixed.TerminalSid, StringComparison.Ordinal) && !String.Equals(caller.UserSid, R7Fixed.UpgradeSid, StringComparison.Ordinal)) throw new SecurityException("CALLER_NOT_AUTHORIZED");
        }

        internal static string DeterministicRequestIdentity(string operation, SortedDictionary<string, object> payload)
        {
            byte[] bytes = R7Json.Encode(R7Json.Object("operation", operation, "payload", payload));
            string hex = R7Hash.Bytes(bytes);
            char[] value = hex.Substring(0, 32).ToCharArray();
            value[12] = '4';
            int variant = Convert.ToInt32(value[16].ToString(), 16);
            value[16] = "89ab"[variant & 3];
            string compact = new string(value);
            return Guid.ParseExact(compact.Substring(0, 8) + "-" + compact.Substring(8, 4) + "-" + compact.Substring(12, 4) + "-" + compact.Substring(16, 4) + "-" + compact.Substring(20, 12), "D").ToString("D");
        }

        private static string StateNonce(string requestIdentity, string state)
        {
            return DeterministicRequestIdentity("UNIT2_TRANSACTION_" + state, R7Json.Object("request_identity", requestIdentity));
        }

        private static bool VerifyPrivateExportRejected(RSA rsa)
        {
            try { rsa.ExportParameters(true); }
            catch (CryptographicException) { return true; }
            throw new CryptographicException("UNIT2_PRIVATE_KEY_EXPORT_UNEXPECTEDLY_SUCCEEDED");
        }

        private static SortedDictionary<string, object> AuthorizationResponse(string authorizationIdentity, R7LedgerRecord commit, string requestIdentity, string nonce)
        {
            SortedDictionary<string, object> response = Success("UPGRADE_AUTHORIZED_PREINSTALL_CONSIDERATION");
            response.Add("authorization_identity", authorizationIdentity);
            response.Add("disposition", "AUTHORIZED FOR FUTURE INSTALLATION CONSIDERATION");
            response.Add("installation_performed", false);
            response.Add("ledger_entry_identity", commit.EntryIdentity);
            response.Add("ledger_sequence", commit.Sequence);
            response.Add("request_identity", requestIdentity);
            response.Add("transition_nonce", nonce);
            return response;
        }

        private static object[] Objects(IEnumerable<string> values)
        {
            List<object> result = new List<object>();
            foreach (string value in values) result.Add(value);
            return result.ToArray();
        }

        private static SortedDictionary<string, object> Success(string code)
        {
            return R7Json.Object("interface_version", "1.0.0", "protocol_version", R7Fixed.ProtocolVersion, "result_code", code, "status", "COMPLETE");
        }

        private static SortedDictionary<string, object> Rejection(string code)
        {
            return R7Json.Object("authority_effect", false, "error_code", String.IsNullOrEmpty(code) ? "REQUEST_REJECTED" : code, "interface_version", "1.0.0", "protocol_version", R7Fixed.ProtocolVersion, "status", "REJECTED");
        }
    }

    internal static class R7Unit2UpgradeServiceProgram
    {
        private static void Main()
        {
            R7RuntimeBoundary.Enforce(R7Fixed.UpgradeInstallRoot);
            ServiceBase.Run(new R7PipeWindowsService(
                R7Fixed.UpgradeService,
                R7Fixed.UpgradePipe,
                new string[] { R7Fixed.OperatorSid, R7Fixed.SystemSid, R7Fixed.TerminalSid, R7Fixed.UpgradeSid },
                delegate() { return new R7Unit2UpgradeProcessor(); },
                "1.0.0"));
        }
    }
#endif
}
