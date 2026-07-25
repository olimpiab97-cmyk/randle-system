using Microsoft.Win32.SafeHandles;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Security.Principal;
using System.ServiceProcess;
using System.Text;

namespace RandleAI.R7Remediation
{
    internal sealed class R7ActiveUpgrade
    {
        private readonly object activationSync = new object();
        internal string AuthorizationIdentity;
        internal string ActivationIdentity;
        internal string TransitionNonce;
        internal string TerminalPolicySha256;
        internal string[] ComponentHashes;
        internal SortedDictionary<string, object> AuthorizationPayload;
        internal SortedDictionary<string, object> ActivationPayload;
        internal Dictionary<string, string> InstalledFileIdentities = new Dictionary<string, string>(StringComparer.Ordinal);

        internal static R7ActiveUpgrade ResolveAuthorization()
        {
            return ResolveAuthorization("TERMINAL_SIGNER");
        }

        internal static R7ActiveUpgrade ResolveAuthorization(string requiredExecutingRole)
        {
            if (String.IsNullOrEmpty(requiredExecutingRole)) throw new ArgumentException("Executing role is required.", "requiredExecutingRole");
            X509Certificate2 certificate = R7Crypto.LoadPublicCertificate(R7Fixed.UpgradePublicCertificatePath, R7BuildIdentity.UpgradePublicCertificateSha256, Path.GetDirectoryName(R7Fixed.UpgradePublicCertificatePath));
            try
            {
                using (RSA verifier = System.Security.Cryptography.X509Certificates.RSACertificateExtensions.GetRSAPublicKey(certificate))
                using (R7VerifiedFile authorizationFile = R7SafeFile.Open(R7Fixed.ActiveTransitionPath, R7Fixed.ActiveTransitionPath, Path.GetDirectoryName(R7Fixed.ActiveTransitionPath), null, R7Fixed.SystemSid, null, null))
                {
                    SortedDictionary<string, object> payload = R7Crypto.VerifyEnvelope(authorizationFile.Bytes, R7BuildIdentity.UpgradePublicCertificateSha256, verifier);
                    R7Json.ExactKeys(payload,
                        "activation_sequence", "authorization_time", "authority_class", "build_receipt_sha256", "components", "dependency_manifest_sha256",
                        "host_binding", "installer_identity", "new_interface_version", "old_interface_version", "old_policy_sha256", "old_service_binary_sha256",
                        "operation", "request_frame_sha256", "request_identity", "request_payload_identity", "revocation_state", "rollback_constraints", "schema_version",
                        "source_commit", "source_tree", "staging_root", "transition_nonce", "verification_object_identity");
                    if (!String.Equals(R7Json.String(payload, "authority_class", 1, 128), "TERMINAL_UPGRADE_AUTHORIZATION", StringComparison.Ordinal) ||
                        !String.Equals(R7Json.String(payload, "operation", 1, 128), "AUTHORIZE_TERMINAL_UPGRADE", StringComparison.Ordinal) ||
                        !String.Equals(R7Json.String(payload, "new_interface_version", 1, 128), R7Fixed.InterfaceVersion, StringComparison.Ordinal) ||
                        !String.Equals(R7Json.String(payload, "revocation_state", 1, 64), "ACTIVE", StringComparison.Ordinal) ||
                        !String.Equals(R7Json.String(payload, "source_commit", 40, 40), R7BuildIdentity.SourceCommit, StringComparison.Ordinal) ||
                        !String.Equals(R7Json.String(payload, "source_tree", 40, 40), R7BuildIdentity.SourceTree, StringComparison.Ordinal)) throw new SecurityException("UPGRADE_AUTHORIZATION_SEMANTICS_MISMATCH");
                    SortedDictionary<string, object> host = R7Json.Child(payload, "host_binding");
                    R7Json.ExactKeys(host, "terminal_ledger_id", "terminal_service_sid", "volume_identity");
                    if (!String.Equals(R7Json.String(host, "terminal_ledger_id", 64, 64), R7Fixed.LedgerId, StringComparison.Ordinal) || !String.Equals(R7Json.String(host, "terminal_service_sid", 1, 256), R7Fixed.TerminalSid, StringComparison.Ordinal)) throw new SecurityException("UPGRADE_AUTHORIZATION_HOST_MISMATCH");
                    DateTimeOffset authorizationTime;
                    if (!DateTimeOffset.TryParseExact(R7Json.String(payload, "authorization_time", 1, 128), "yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out authorizationTime)) throw new SecurityException("UPGRADE_AUTHORIZATION_TIME_INVALID");
                    Dictionary<string, string> roleHashes = new Dictionary<string, string>(StringComparer.Ordinal);
                    List<string> componentHashes = new List<string>();
                    foreach (object rawComponent in R7Json.Array(payload, "components"))
                    {
                        SortedDictionary<string, object> component = RequireObject(rawComponent);
                        R7Json.ExactKeys(component, "file_identity", "final_path", "final_path_preinstall_state", "role", "sha256", "size", "staging_relative_path");
                        string role = R7Json.String(component, "role", 1, 256);
                        string path = R7Json.String(component, "final_path", 3, 4096);
                        string sha = R7Json.String(component, "sha256", 64, 64);
                        if (!String.Equals(R7Json.String(component, "final_path_preinstall_state", 1, 64), "ABSENT", StringComparison.Ordinal) || roleHashes.ContainsKey(role)) throw new SecurityException("UPGRADE_COMPONENT_AUTHORIZATION_INVALID");
                        string root = path.StartsWith(R7Fixed.TerminalInstallRoot + Path.DirectorySeparatorChar, StringComparison.Ordinal) ? R7Fixed.TerminalInstallRoot : R7Fixed.RemediationRoot;
                        using (R7VerifiedFile installed = R7SafeFile.Open(path, path, root, sha, R7Fixed.SystemSid, null, R7Json.String(host, "volume_identity", 8, 64)))
                        {
                            DateTimeOffset creation;
                            if (!DateTimeOffset.TryParseExact(installed.Measurement.CreationTime, "yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out creation) || creation < authorizationTime) throw new SecurityException("UPGRADE_AUTHORIZATION_NOT_PREINSTALL");
                        }
                        roleHashes.Add(role, sha);
                        componentHashes.Add(sha);
                    }
                    string executable = Path.GetFullPath(Assembly.GetExecutingAssembly().Location);
                    string executableSha;
                    using (R7VerifiedFile current = R7SafeFile.Open(executable, executable, R7Fixed.TerminalInstallRoot, null, R7Fixed.SystemSid, null, R7Json.String(host, "volume_identity", 8, 64))) executableSha = current.Measurement.Sha256;
                    string expectedExecutable;
                    if (!roleHashes.TryGetValue(requiredExecutingRole, out expectedExecutable) || !R7Hash.FixedTimeEquals(executableSha, expectedExecutable)) throw new SecurityException("ACTIVE_EXECUTING_ROLE_NOT_AUTHORIZED:" + requiredExecutingRole);
                    string policySha;
                    if (!roleHashes.TryGetValue("TERMINAL_POLICY", out policySha)) throw new SecurityException("TERMINAL_POLICY_NOT_AUTHORIZED");
                    string buildReceiptSha;
                    string dependencyManifestSha;
                    if (!roleHashes.TryGetValue("BUILD_RECEIPT", out buildReceiptSha) || !R7Hash.FixedTimeEquals(buildReceiptSha, R7Json.String(payload, "build_receipt_sha256", 64, 64)) ||
                        !roleHashes.TryGetValue("DEPENDENCY_MANIFEST", out dependencyManifestSha) || !R7Hash.FixedTimeEquals(dependencyManifestSha, R7Json.String(payload, "dependency_manifest_sha256", 64, 64))) throw new SecurityException("UPGRADE_ARTIFACT_BINDING_MISMATCH");
                    string nonce = R7Json.String(payload, "transition_nonce", 36, 36);
                    string authorizationIdentity = authorizationFile.Measurement.Sha256;
                    return new R7ActiveUpgrade
                    {
                        AuthorizationIdentity = authorizationIdentity,
                        ActivationIdentity = String.Empty,
                        TransitionNonce = nonce,
                        TerminalPolicySha256 = policySha,
                        ComponentHashes = componentHashes.ToArray(),
                        AuthorizationPayload = payload
                    };
                }
            }
            finally { certificate.Dispose(); }
        }

        internal void Activate()
        {
            ResolveActivation(true);
        }

        internal void RequireActivatedComponent(string role, string currentFileIdentity)
        {
            ResolveActivation(false);
            VerifyAuthorityDirectories(ActivationPayload, R7Json.String(R7Json.Child(AuthorizationPayload, "host_binding"), "volume_identity", 8, 64));
            string expected;
            if (!InstalledFileIdentities.TryGetValue(role, out expected) || !String.Equals(expected, currentFileIdentity, StringComparison.Ordinal)) throw new SecurityException("ACTIVE_INSTALLED_FILE_IDENTITY_MISMATCH:" + role);
        }

        private void ResolveActivation(bool allowActivation)
        {
            lock (activationSync)
            {
                if (!String.IsNullOrEmpty(ActivationIdentity)) return;
                using (X509Certificate2 certificate = R7Crypto.LoadPublicCertificate(R7Fixed.UpgradePublicCertificatePath, R7BuildIdentity.UpgradePublicCertificateSha256, Path.GetDirectoryName(R7Fixed.UpgradePublicCertificatePath)))
                using (RSA verifier = System.Security.Cryptography.X509Certificates.RSACertificateExtensions.GetRSAPublicKey(certificate))
                {
                    SortedDictionary<string, string> installed;
                    SortedDictionary<string, object> activation;
                    ActivationIdentity = EnsureActivation(TransitionNonce, AuthorizationIdentity, AuthorizationPayload, verifier, allowActivation, out installed, out activation);
                    InstalledFileIdentities = new Dictionary<string, string>(installed, StringComparer.Ordinal);
                    ActivationPayload = activation;
                }
            }
        }

        private static string EnsureActivation(string nonce, string authorizationIdentity, SortedDictionary<string, object> authorization, RSA verifier, bool allowActivation, out SortedDictionary<string, string> installedFileIdentities, out SortedDictionary<string, object> resolvedActivation)
        {
            SortedDictionary<string, object> response;
            if (!allowActivation)
            {
                R7UpgradePolicy publicPolicy = R7UpgradePolicy.Load(R7BuildIdentity.UpgradePolicySha256, R7BuildIdentity.UpgradePublicCertificateSha256);
                R7VersionedLedger publicLedger = new R7VersionedLedger(R7Fixed.UpgradeLedgerRoot, publicPolicy.LedgerId, R7BuildIdentity.UpgradePublicCertificateSha256, R7Fixed.UpgradeSid, null, verifier);
                R7LedgerRecord[] publicActivations = publicLedger.Find("UPGRADE_ACTIVATED", nonce);
                if (publicActivations.Length != 1 || publicLedger.Find("UPGRADE_AUTHORIZATION_REVOKED", nonce).Length != 0) throw new SecurityException("UPGRADE_NOT_ACTIVATED");
                R7LedgerRecord publicActivation = publicActivations[0];
                R7ObjectStore publicObjects = new R7ObjectStore(R7Fixed.UpgradeObjectRoot, R7Fixed.UpgradeSid, publicPolicy.VolumeIdentity);
                byte[] publicRecord = R7Json.Encode(publicObjects.Get(publicActivation.ContentAddress));
                if (!R7Hash.FixedTimeEquals(R7Hash.Bytes(publicRecord), publicActivation.ContentAddress)) throw new SecurityException("UPGRADE_ACTIVATION_OBJECT_IDENTITY_MISMATCH");
                response = R7Json.Object(
                    "activation_identity", publicActivation.ContentAddress,
                    "interface_version", R7Fixed.InterfaceVersion,
                    "ledger_entry_identity", publicActivation.EntryIdentity,
                    "ledger_sequence", publicActivation.Sequence,
                    "protocol_version", R7Fixed.ProtocolVersion,
                    "record", Convert.ToBase64String(publicRecord),
                    "result_code", "UPGRADE_ACTIVATION_RESOLVED",
                    "status", "COMPLETE",
                    "transition_nonce", nonce);
            }
            else
            {
                byte[] requestFrame;
                byte[] responseFrame;
                SortedDictionary<string, object> get = UpgradeRequest("GET_ACTIVATION", R7Json.Object("transition_nonce", nonce));
                response = R7Framing.Call(R7Fixed.UpgradePipe, get, 10000, out requestFrame, out responseFrame);
                if (!String.Equals(R7Json.String(response, "status", 1, 64), "COMPLETE", StringComparison.Ordinal))
                {
                    SortedDictionary<string, object> activate = UpgradeRequest("ACTIVATE_TERMINAL_UPGRADE", R7Json.Object("authorization_identity", authorizationIdentity, "transition_nonce", nonce));
                    response = R7Framing.Call(R7Fixed.UpgradePipe, activate, 30000, out requestFrame, out responseFrame);
                    if (!String.Equals(R7Json.String(response, "status", 1, 64), "COMPLETE", StringComparison.Ordinal) || !String.Equals(R7Json.String(response, "result_code", 1, 128), "UPGRADE_ACTIVATED", StringComparison.Ordinal)) throw new SecurityException("UPGRADE_ACTIVATION_REFUSED");
                    response = R7Framing.Call(R7Fixed.UpgradePipe, get, 10000, out requestFrame, out responseFrame);
                }
            }
            R7Json.ExactKeys(response, "activation_identity", "interface_version", "ledger_entry_identity", "ledger_sequence", "protocol_version", "record", "result_code", "status", "transition_nonce");
            if (!String.Equals(R7Json.String(response, "status", 1, 64), "COMPLETE", StringComparison.Ordinal) ||
                !String.Equals(R7Json.String(response, "result_code", 1, 128), "UPGRADE_ACTIVATION_RESOLVED", StringComparison.Ordinal) ||
                !String.Equals(R7Json.String(response, "interface_version", 1, 128), R7Fixed.InterfaceVersion, StringComparison.Ordinal) ||
                !String.Equals(R7Json.String(response, "protocol_version", 1, 64), R7Fixed.ProtocolVersion, StringComparison.Ordinal) ||
                !String.Equals(R7Json.String(response, "transition_nonce", 36, 36), nonce, StringComparison.Ordinal)) throw new SecurityException("UPGRADE_ACTIVATION_UNRESOLVED");
            string identity = R7Json.String(response, "activation_identity", 64, 64);
            string ledgerEntryIdentity = R7Json.String(response, "ledger_entry_identity", 64, 64);
            long ledgerSequence = R7Json.Integer(response, "ledger_sequence", 1, Int64.MaxValue);
            byte[] record;
            try { record = Convert.FromBase64String(R7Json.String(response, "record", 1, R7Fixed.MaximumEncodedFrameChars)); }
            catch (FormatException) { throw new SecurityException("UPGRADE_ACTIVATION_RECORD_ENCODING_INVALID"); }
            if (!R7Hash.FixedTimeEquals(identity, R7Hash.Bytes(record))) throw new SecurityException("UPGRADE_ACTIVATION_IDENTITY_MISMATCH");
            SortedDictionary<string, object> activation = R7Crypto.VerifyEnvelope(record, R7BuildIdentity.UpgradePublicCertificateSha256, verifier);
            R7Json.ExactKeys(activation, "activation_sequence", "activation_time", "authority_class", "authority_directories", "authorization_identity", "caller", "installed_components", "new_interface_version", "operation", "request_frame_sha256", "request_identity", "request_payload_identity", "schema_version", "transition_nonce");
            if (!String.Equals(R7Json.String(activation, "authority_class", 1, 128), "TERMINAL_UPGRADE_ACTIVATION", StringComparison.Ordinal) ||
                !String.Equals(R7Json.String(activation, "operation", 1, 128), "ACTIVATE_TERMINAL_UPGRADE", StringComparison.Ordinal) ||
                !String.Equals(R7Json.String(activation, "authorization_identity", 64, 64), authorizationIdentity, StringComparison.Ordinal) ||
                !String.Equals(R7Json.String(activation, "transition_nonce", 36, 36), nonce, StringComparison.Ordinal) ||
                !String.Equals(R7Json.String(activation, "new_interface_version", 1, 128), R7Fixed.InterfaceVersion, StringComparison.Ordinal) ||
                !String.Equals(R7Json.String(activation, "schema_version", 1, 128), "1.0.0", StringComparison.Ordinal) ||
                R7Json.Integer(activation, "activation_sequence", 1, Int64.MaxValue) != R7Json.Integer(authorization, "activation_sequence", 1, Int64.MaxValue)) throw new SecurityException("UPGRADE_ACTIVATION_BINDING_MISMATCH");
            DateTimeOffset authorizationTime;
            DateTimeOffset activationTime;
            if (!DateTimeOffset.TryParseExact(R7Json.String(authorization, "authorization_time", 1, 128), "yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out authorizationTime) ||
                !DateTimeOffset.TryParseExact(R7Json.String(activation, "activation_time", 1, 128), "yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out activationTime) || activationTime < authorizationTime) throw new SecurityException("UPGRADE_ACTIVATION_TIME_INVALID");
            SortedDictionary<string, object> caller = R7Json.Child(activation, "caller");
            R7Json.ExactKeys(caller, "authentication_id", "contains_terminal_signer_sid", "elevation_type", "group_sids", "privileges", "process_file_identity", "process_id", "process_path", "process_sha256", "process_start_time", "token_id", "user_sid");
            if (!String.Equals(R7Json.String(caller, "user_sid", 1, 256), R7Fixed.TerminalSid, StringComparison.Ordinal) || !R7Json.Boolean(caller, "contains_terminal_signer_sid")) throw new SecurityException("UPGRADE_ACTIVATION_CALLER_INVALID");
            Dictionary<string, SortedDictionary<string, object>> authorizedByRole = new Dictionary<string, SortedDictionary<string, object>>(StringComparer.Ordinal);
            foreach (object rawAuthorized in R7Json.Array(authorization, "components"))
            {
                SortedDictionary<string, object> authorized = RequireObject(rawAuthorized);
                R7Json.ExactKeys(authorized, "file_identity", "final_path", "final_path_preinstall_state", "role", "sha256", "size", "staging_relative_path");
                string authorizedRole = R7Json.String(authorized, "role", 1, 256);
                if (authorizedByRole.ContainsKey(authorizedRole)) throw new SecurityException("UPGRADE_AUTHORIZED_COMPONENT_DUPLICATE");
                authorizedByRole.Add(authorizedRole, authorized);
            }
            SortedDictionary<string, object> host = R7Json.Child(authorization, "host_binding");
            string volumeIdentity = R7Json.String(host, "volume_identity", 8, 64);
            VerifyAuthorityDirectories(activation, volumeIdentity);
            installedFileIdentities = new SortedDictionary<string, string>(StringComparer.Ordinal);
            foreach (object rawInstalled in R7Json.Array(activation, "installed_components"))
            {
                SortedDictionary<string, object> installed = RequireObject(rawInstalled);
                R7Json.ExactKeys(installed, "canonical_path", "creation_time", "file_identity", "final_nt_path", "hard_link_count", "owner_sid", "role", "security_descriptor_sha256", "sha256", "size", "streams", "volume_identity");
                string role = R7Json.String(installed, "role", 1, 256);
                SortedDictionary<string, object> authorized;
                if (!authorizedByRole.TryGetValue(role, out authorized) || installedFileIdentities.ContainsKey(role)) throw new SecurityException("UPGRADE_INSTALLED_COMPONENT_SET_INVALID");
                string path = R7Json.String(installed, "canonical_path", 3, 4096);
                string sha = R7Json.String(installed, "sha256", 64, 64);
                string fileIdentity = R7Json.String(installed, "file_identity", 1, 128);
                object[] streams = R7Json.Array(installed, "streams");
                if (!String.Equals(path, R7Json.String(authorized, "final_path", 3, 4096), StringComparison.Ordinal) ||
                    !R7Hash.FixedTimeEquals(sha, R7Json.String(authorized, "sha256", 64, 64)) ||
                    R7Json.Integer(installed, "size", 0, Int64.MaxValue) != R7Json.Integer(authorized, "size", 0, Int64.MaxValue) ||
                    R7Json.Integer(installed, "hard_link_count", 1, 1) != 1 ||
                    !String.Equals(R7Json.String(installed, "owner_sid", 1, 256), R7Fixed.SystemSid, StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(installed, "volume_identity", 8, 64), volumeIdentity, StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(installed, "final_nt_path", 3, 4096), @"\\?\" + path, StringComparison.Ordinal) ||
                    streams.Length != 1 || !String.Equals(streams[0] as string, "::$DATA", StringComparison.Ordinal) ||
                    !R7Hash.IsLowerSha256(R7Json.String(installed, "security_descriptor_sha256", 64, 64))) throw new SecurityException("UPGRADE_INSTALLED_COMPONENT_MEASUREMENT_INVALID:" + role);
                string root = path.StartsWith(R7Fixed.TerminalInstallRoot + Path.DirectorySeparatorChar, StringComparison.Ordinal) ? R7Fixed.TerminalInstallRoot : R7Fixed.RemediationRoot;
                using (R7VerifiedFile current = R7SafeFile.Open(path, path, root, sha, R7Fixed.SystemSid, R7Json.String(installed, "security_descriptor_sha256", 64, 64), volumeIdentity))
                {
                    if (!String.Equals(current.Measurement.FileIdentity, fileIdentity, StringComparison.Ordinal) || current.Measurement.Size != R7Json.Integer(installed, "size", 0, Int64.MaxValue) || !String.Equals(current.Measurement.CreationTime, R7Json.String(installed, "creation_time", 1, 128), StringComparison.Ordinal)) throw new SecurityException("UPGRADE_INSTALLED_COMPONENT_CURRENT_IDENTITY_MISMATCH:" + role);
                }
                installedFileIdentities.Add(role, fileIdentity);
            }
            if (installedFileIdentities.Count != authorizedByRole.Count) throw new SecurityException("UPGRADE_INSTALLED_COMPONENT_SET_INCOMPLETE");
            string terminalSignerSha = R7Json.String(authorizedByRole["TERMINAL_SIGNER"], "sha256", 64, 64);
            if (!R7Hash.FixedTimeEquals(R7Json.String(caller, "process_sha256", 64, 64), terminalSignerSha) || !String.Equals(R7Json.String(caller, "process_file_identity", 1, 256), installedFileIdentities["TERMINAL_SIGNER"], StringComparison.Ordinal)) throw new SecurityException("UPGRADE_ACTIVATION_CALLER_BINARY_INVALID");
            R7UpgradePolicy upgradePolicy = R7UpgradePolicy.Load(R7BuildIdentity.UpgradePolicySha256, R7BuildIdentity.UpgradePublicCertificateSha256);
            R7VersionedLedger upgradeLedger = new R7VersionedLedger(R7Fixed.UpgradeLedgerRoot, upgradePolicy.LedgerId, R7BuildIdentity.UpgradePublicCertificateSha256, R7Fixed.UpgradeSid, null, verifier);
            R7LedgerRecord[] issued = upgradeLedger.Find("UPGRADE_AUTHORIZATION_ISSUED", nonce);
            R7LedgerRecord[] activated = upgradeLedger.Find("UPGRADE_ACTIVATED", nonce);
            if (issued.Length != 1 || !String.Equals(issued[0].ContentAddress, authorizationIdentity, StringComparison.Ordinal) || activated.Length != 1 || !String.Equals(activated[0].ContentAddress, identity, StringComparison.Ordinal) || !String.Equals(activated[0].EntryIdentity, ledgerEntryIdentity, StringComparison.Ordinal) || activated[0].Sequence != ledgerSequence || upgradeLedger.Find("UPGRADE_AUTHORIZATION_REVOKED", nonce).Length != 0) throw new SecurityException("UPGRADE_ACTIVATION_LEDGER_MEMBERSHIP_INVALID");
            resolvedActivation = activation;
            return identity;
        }

        private static void VerifyAuthorityDirectories(SortedDictionary<string, object> activation, string volumeIdentity)
        {
            SortedDictionary<string, string> expected = R7Fixed.AuthorityDirectories();
            HashSet<string> seen = new HashSet<string>(StringComparer.Ordinal);
            foreach (object rawDirectory in R7Json.Array(activation, "authority_directories"))
            {
                SortedDictionary<string, object> directory = RequireObject(rawDirectory);
                R7Json.ExactKeys(directory, "canonical_path", "creation_time", "file_identity", "final_nt_path", "hard_link_count", "owner_sid", "role", "security_descriptor_sha256", "sha256", "short_path", "size", "streams", "volume_identity");
                string role = R7Json.String(directory, "role", 1, 256);
                string expectedPath;
                if (!expected.TryGetValue(role, out expectedPath) || !seen.Add(role)) throw new SecurityException("UPGRADE_AUTHORITY_DIRECTORY_SET_INVALID:" + role);
                string path = R7Json.String(directory, "canonical_path", 3, 4096);
                string aclIdentity = R7Json.String(directory, "security_descriptor_sha256", 64, 64);
                string fileIdentity = R7Json.String(directory, "file_identity", 1, 128);
                string creationTime = R7Json.String(directory, "creation_time", 1, 128);
                string shortPath = R7Json.String(directory, "short_path", 0, 4096);
                long linkCount = R7Json.Integer(directory, "hard_link_count", 1, UInt32.MaxValue);
                object[] streams = R7Json.Array(directory, "streams");
                DateTimeOffset parsedCreationTime;
                if (!String.Equals(path, expectedPath, StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(directory, "final_nt_path", 3, 4096), @"\\?\" + path, StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(directory, "owner_sid", 1, 256), R7Fixed.SystemSid, StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(directory, "volume_identity", 8, 64), volumeIdentity, StringComparison.Ordinal) ||
                    !R7Hash.IsLowerSha256(aclIdentity) ||
                    R7Json.String(directory, "sha256", 0, 0).Length != 0 ||
                    R7Json.Integer(directory, "size", 0, 0) != 0 ||
                    streams.Length != 1 || !String.Equals(streams[0] as string, "::$DATA", StringComparison.Ordinal) ||
                    !DateTimeOffset.TryParseExact(creationTime, "yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out parsedCreationTime)) throw new SecurityException("UPGRADE_AUTHORITY_DIRECTORY_MEASUREMENT_INVALID:" + role);
                R7FileMeasurement current = R7SafeFile.MeasureDirectory(path, path, R7Fixed.SystemSid, aclIdentity, volumeIdentity);
                if (!String.Equals(current.FileIdentity, fileIdentity, StringComparison.Ordinal) ||
                    !String.Equals(current.CreationTime, creationTime, StringComparison.Ordinal) ||
                    !String.Equals(current.FinalNtPath, R7Json.String(directory, "final_nt_path", 3, 4096), StringComparison.Ordinal) ||
                    !String.Equals(current.ShortPath ?? String.Empty, shortPath, StringComparison.Ordinal) ||
                    current.LinkCount != (uint)linkCount || current.Streams.Length != 1 || !String.Equals(current.Streams[0], "::$DATA", StringComparison.Ordinal)) throw new SecurityException("ACTIVE_AUTHORITY_DIRECTORY_IDENTITY_CHANGED:" + role);
            }
            if (seen.Count != expected.Count) throw new SecurityException("UPGRADE_AUTHORITY_DIRECTORY_SET_INCOMPLETE");
        }

        private static SortedDictionary<string, object> UpgradeRequest(string operation, SortedDictionary<string, object> payload)
        {
            return R7Json.Object("interface_version", "1.0.0", "operation", operation, "payload", payload, "protocol_version", R7Fixed.ProtocolVersion, "request_identity", Guid.NewGuid().ToString("D"));
        }

        private static SortedDictionary<string, object> RequireObject(object value)
        {
            SortedDictionary<string, object> result = value as SortedDictionary<string, object>;
            if (result == null) throw new R7ProtocolException("OBJECT_REQUIRED");
            return result;
        }
    }

    internal sealed class R7TerminalProcessor : R7PipeProcessor
    {
        private readonly object sync = new object();
        private readonly R7ActiveUpgrade activeUpgrade;
        private readonly R7TerminalPolicy policy;
        private readonly R7AuthoritySet authority;
        private readonly X509Certificate2 publicCertificate;
        private readonly RSA verifier;
        private readonly RSA signer;
        private readonly R7VerifiedMetadataFile signingKeyFile;
        private readonly R7VerifiedFile signingBinaryFile;
        private readonly R7VersionedLedger ledger;
        private readonly R7ObjectStore objects;
        private readonly R7EvidenceStore evidence;
        private readonly R7TransactionManager transactions;
        private readonly string binarySha256;
        private readonly string binaryFileIdentity;
        private readonly long signerProcessId;
        private readonly string signerProcessStartTime;
        private readonly string signerProcessInstanceIdentity;
        private readonly R7DependencyClosure dependencies;

        internal R7TerminalProcessor()
        {
            string currentSid = WindowsIdentity.GetCurrent().User.Value;
            if (!String.Equals(currentSid, R7Fixed.TerminalSid, StringComparison.Ordinal)) throw new SecurityException("TERMINAL_SERVICE_SID_MISMATCH");
            activeUpgrade = R7ActiveUpgrade.ResolveAuthorization();
            policy = R7TerminalPolicy.Load(activeUpgrade.TerminalPolicySha256);
            if (!String.Equals(policy.SourceCommit, R7BuildIdentity.SourceCommit, StringComparison.Ordinal) || !String.Equals(policy.SourceTree, R7BuildIdentity.SourceTree, StringComparison.Ordinal) || !String.Equals(policy.UpgradePublicCertificateSha256, R7BuildIdentity.UpgradePublicCertificateSha256, StringComparison.Ordinal) || !R7Hash.FixedTimeEquals(policy.DependencyManifestSha256, R7BuildIdentity.DependencyManifestSha256)) throw new SecurityException("TERMINAL_POLICY_SOURCE_MISMATCH");
            if (!R7Hash.FixedTimeEquals(policy.BuildReceiptSha256, R7Json.String(activeUpgrade.AuthorizationPayload, "build_receipt_sha256", 64, 64)) ||
                !R7Hash.FixedTimeEquals(policy.DependencyManifestSha256, R7Json.String(activeUpgrade.AuthorizationPayload, "dependency_manifest_sha256", 64, 64))) throw new SecurityException("TERMINAL_POLICY_AUTHORIZATION_BINDING_MISMATCH");
            string executable = Path.GetFullPath(Assembly.GetExecutingAssembly().Location);
            R7ComponentIdentity signerComponent = policy.Component("TERMINAL_SIGNER");
            signingBinaryFile = R7SafeFile.Open(executable, signerComponent.Path, R7Fixed.TerminalInstallRoot, signerComponent.Sha256, R7Fixed.SystemSid, null, policy.VolumeIdentity);
            binarySha256 = signingBinaryFile.Measurement.Sha256;
            binaryFileIdentity = signingBinaryFile.Measurement.FileIdentity;
            // The separately signed transition must be durably activated before this
            // process opens either the terminal private key or the terminal ledger.
            activeUpgrade.Activate();
            activeUpgrade.RequireActivatedComponent("TERMINAL_SIGNER", binaryFileIdentity);
            dependencies = new R7DependencyClosure(R7Fixed.DependencyManifestPath, R7BuildIdentity.DependencyManifestSha256, R7Fixed.TerminalInstallRoot);
            authority = new R7AuthoritySet(policy.AuthorityIdentities);
            publicCertificate = R7Crypto.LoadPublicCertificate(R7Fixed.TerminalPublicCertificatePath, R7Fixed.TerminalPublicKeyIdentity, Path.GetDirectoryName(R7Fixed.TerminalPublicCertificatePath));
            verifier = System.Security.Cryptography.X509Certificates.RSACertificateExtensions.GetRSAPublicKey(publicCertificate);
            signingKeyFile = R7SafeFile.HoldMetadataFile(R7BuildIdentity.TerminalKeyFilePath, R7BuildIdentity.TerminalKeyFilePath, Path.GetDirectoryName(R7BuildIdentity.TerminalKeyFilePath), R7BuildIdentity.TerminalKeyFileOwnerSid, R7BuildIdentity.TerminalKeyFileSecurityDescriptorSha256, R7BuildIdentity.TerminalKeyFileVolumeIdentity, R7BuildIdentity.TerminalKeyFileIdentity, R7BuildIdentity.TerminalKeyFileLinkCount);
            signer = R7Crypto.LoadTerminalSigner();
            using (System.Diagnostics.Process process = System.Diagnostics.Process.GetCurrentProcess())
            {
                signerProcessId = process.Id;
                signerProcessStartTime = process.StartTime.ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture);
                signerProcessInstanceIdentity = R7Hash.Bytes(R7Json.Encode(R7Json.Object("binary_file_identity", binaryFileIdentity, "process_id", signerProcessId, "process_start_time", signerProcessStartTime, "service_sid", R7Fixed.TerminalSid)));
            }
            ledger = new R7VersionedLedger(R7Fixed.LedgerRoot, R7Fixed.LedgerId, R7Fixed.TerminalPublicKeyIdentity, R7Fixed.TerminalSid, signer, verifier);
            objects = new R7ObjectStore(R7Fixed.ObjectRoot, R7Fixed.TerminalSid, policy.VolumeIdentity);
            evidence = new R7EvidenceStore(R7Fixed.EvidenceRoot, objects, R7Fixed.TerminalSid, policy.VolumeIdentity);
            transactions = new R7TransactionManager(ledger, objects, signer, R7Fixed.TerminalPublicKeyIdentity, R7Fixed.ReceiptRoot, R7Fixed.ResponseRoot, R7Fixed.InterfaceVersion, String.Empty);
            RecoverCheckpointIfRequired();
            transactions.RecoverIncomplete();
            RegisterUpgradeAndHistory();
        }

        internal override SortedDictionary<string, object> Process(R7RequestContext context, SortedDictionary<string, object> request)
        {
            lock (sync)
            {
                activeUpgrade.RequireActivatedComponent("TERMINAL_SIGNER", binaryFileIdentity);
                dependencies.VerifyNoNewModules();
                long beforeSequence = ledger.Sequence;
                string beforeRoot = ledger.RootHash;
                SortedDictionary<string, object> protectedBefore = CaptureProtectedState();
                SortedDictionary<string, object> response;
                try { response = Dispatch(context, request); }
                catch (R7ProtocolException exception) { context.ProtocolErrorCode = exception.Code; context.ProtocolErrorOffset = exception.Offset >= 0 ? exception.Offset : (context.RequestFrame == null ? -1 : context.RequestFrame.Length); response = R7PipeWindowsService.Rejection(NormalizeError(exception.Code)); }
                catch (SecurityException exception) { response = R7PipeWindowsService.Rejection(String.IsNullOrEmpty(exception.Message) ? "CALLER_NOT_AUTHORIZED" : exception.Message); }
                dependencies.VerifyNoNewModules();
                SortedDictionary<string, object> protectedAfter = CaptureProtectedState();
                evidence.Record(context, request, response, beforeSequence, beforeRoot, ledger.Sequence, ledger.RootHash, protectedBefore, protectedAfter, "SIGNER_SERVER_CAPTURE");
                return response;
            }
        }

        internal override void ProtocolRejected(R7RequestContext context, R7ProtocolException exception)
        {
            lock (sync)
            {
                if (context.Caller == null) return;
                activeUpgrade.RequireActivatedComponent("TERMINAL_SIGNER", binaryFileIdentity);
                dependencies.VerifyNoNewModules();
                SortedDictionary<string, object> response = R7PipeWindowsService.Rejection(NormalizeError(exception.Code));
                SortedDictionary<string, object> state = CaptureProtectedState();
                evidence.Record(context, null, response, ledger.Sequence, ledger.RootHash, ledger.Sequence, ledger.RootHash, state, state, "STRICT_PARSER_REJECTION_BEFORE_DISPATCH");
                dependencies.VerifyNoNewModules();
            }
        }

        private SortedDictionary<string, object> CaptureProtectedState()
        {
            return R7Json.Object(
                "authority_identity", SnapshotTree(Path.Combine(R7Fixed.RemediationRoot, "Authority")),
                "configuration_identity", SnapshotTree(Path.Combine(R7Fixed.RemediationRoot, "Config")),
                "receipt_identity", SnapshotTree(R7Fixed.ReceiptRoot),
                "response_identity", SnapshotTree(R7Fixed.ResponseRoot),
                "signer_process_id", signerProcessId,
                "signer_process_instance_identity", signerProcessInstanceIdentity,
                "signer_process_start_time", signerProcessStartTime,
                "terminal_trust_identity", SnapshotTree(Path.Combine(R7Fixed.TerminalStateRoot, "Trust")),
                "upgrade_authorization_identity", SnapshotTree(R7Fixed.UpgradeAuthorizationRoot),
                "upgrade_trust_identity", SnapshotTree(Path.Combine(R7Fixed.UpgradeStateRoot, "Trust")));
        }

        private string SnapshotTree(string root)
        {
            if (!Directory.Exists(root)) return R7Fixed.ZeroHash;
            using (R7VerifiedDirectory directory = R7SafeFile.HoldDirectory(root, root, null, null, policy.VolumeIdentity))
            {
                List<object> files = new List<object>();
                List<string> pending = new List<string>();
                pending.Add(root);
                for (int directoryIndex = 0; directoryIndex < pending.Count; directoryIndex++)
                {
                    string current = pending[directoryIndex];
                    using (R7VerifiedDirectory currentDirectory = R7SafeFile.HoldDirectory(current, current, null, null, policy.VolumeIdentity))
                    {
                        string[] childDirectories = Directory.GetDirectories(current, "*", SearchOption.TopDirectoryOnly);
                        Array.Sort(childDirectories, StringComparer.Ordinal);
                        foreach (string childDirectory in childDirectories) pending.Add(childDirectory);
                        string[] paths = Directory.GetFiles(current, "*", SearchOption.TopDirectoryOnly);
                        Array.Sort(paths, StringComparer.Ordinal);
                        foreach (string path in paths)
                        {
                            using (R7VerifiedFile file = R7SafeFile.Open(path, path, root, null, null, null, policy.VolumeIdentity))
                            {
                                files.Add(R7Json.Object("file_id", file.Measurement.FileIdentity, "path", file.Measurement.FinalNtPath, "sha256", file.Measurement.Sha256, "size", file.Measurement.Size));
                            }
                        }
                    }
                }
                return R7Hash.Bytes(R7Json.Encode(R7Json.Object("directory_file_id", directory.Measurement.FileIdentity, "files", files.ToArray(), "root", directory.Measurement.FinalNtPath)));
            }
        }

        public override void Dispose()
        {
            dependencies.Dispose();
            signer.Dispose();
            signingKeyFile.Dispose();
            signingBinaryFile.Dispose();
            verifier.Dispose();
            publicCertificate.Dispose();
        }

        private SortedDictionary<string, object> Dispatch(R7RequestContext context, SortedDictionary<string, object> request)
        {
            R7Json.ExactKeys(request, "interface_version", "operation", "payload", "protocol_version", "request_identity");
            if (!String.Equals(R7Json.String(request, "interface_version", 1, 128), R7Fixed.InterfaceVersion, StringComparison.Ordinal) || !String.Equals(R7Json.String(request, "protocol_version", 1, 64), R7Fixed.ProtocolVersion, StringComparison.Ordinal)) throw new R7ProtocolException("INTERFACE_VERSION_REJECTED");
            string operation = R7Json.String(request, "operation", 1, 128);
            string requestIdentity = CanonicalGuid(R7Json.String(request, "request_identity", 36, 36));
            SortedDictionary<string, object> payload = R7Json.Child(request, "payload");
            AuthorizeCaller(context.Caller, operation);
            if (operation == "GET_HEALTH") { R7Json.ExactKeys(payload); return Health(); }
            if (operation == "GET_PUBLIC_TRUST") { R7Json.ExactKeys(payload); return PublicTrust(); }
            if (operation == "GET_LEDGER_STATUS") { R7Json.ExactKeys(payload); return LedgerStatus(); }
            if (operation == "VERIFY_PUBLIC_IDENTITY") return VerifyPublicIdentity(payload);
            if (operation == "GET_LEDGER_ENTRY") return LedgerEntry(payload);
            if (operation == "GET_TERMINAL_RECEIPT" || operation == "GET_RECONCILIATION") return Receipt(payload);
            if (operation == "GET_RECOVERY_STATE") return RecoveryState(payload);
            if (operation == "RESOLVE_INTERACTION") return ResolveInteraction(context, payload);
            if (operation == "RESOLVE_EVIDENCE_SUBMISSION") return ResolveEvidenceSubmission(payload);
            if (operation == "GET_INTERACTION_EVIDENCE") return InteractionEvidence(payload);
            if (operation == "GET_INTERACTION_RAW_EVIDENCE") return RawInteractionEvidence(payload);
            if (operation == "VERIFY_TERMINAL_RECEIPT" || operation == "VERIFY_RECONCILIATION" || operation == "CLASSIFY_RECEIPT") return VerifyReceiptOperation(operation, payload);
            if (operation == "CLASSIFY_LEDGER_SEQUENCE") return ClassifySequence(payload);
            if (operation == "GET_VERSION_HISTORY") return VersionHistory(payload);
            if (operation == "SUBMIT_PUBLIC_VERIFICATION_EVIDENCE") return PublicVerificationEvidence(payload);
            if (operation == "SUBMIT_EXECUTION_EVIDENCE") return SubmitExecutionEnvelope(context, payload);
            if (operation == "SUBMIT_OBSERVATION_EVIDENCE") return SubmitObservationEnvelope(context, payload);
            if (operation == "SUBMIT_COMPARATOR_EVIDENCE") return SubmitComparatorEnvelope(context, payload);
            if (operation == "VERIFY_CASE_AUTHORITY") return AuthorityProbe(payload);
            if (operation == "VERIFY_COVERAGE") return CoverageProbe(payload);
            if (operation == "VERIFY_CONCURRENT_INTERACTIONS") return ConcurrencyProbe(payload);
            if (operation == "FRAME_BOUNDARY") return FrameBoundary(context, payload);
            if (operation == "RUN_PATH_PROBE") return PathProbe(payload);
            if (operation == "RUN_DEPENDENCY_PROBE") return DependencyProbe(payload);
            if (operation == "SUBMIT_RECOVERY_EVIDENCE") return RecoveryEvidence(payload);
            if (operation == "VERIFY_HISTORY") return HistoryProbe(payload);
            if (operation == "VERIFY_TRACE") return TraceProbe(payload);
            if (operation == "VERIFY_DOCUMENT_CLAIM") return ClaimProbe(payload);
            if (operation == "SUBMIT_EXTERNAL_INTERACTION") return ExternalEvidence(payload);
            if (operation == "RUN_SELF_UPGRADE_PROBE") return SelfUpgradeProbe(payload);
            if (operation == "SUBMIT_SERVICE_STOP_EVIDENCE") return ServiceStopEvidence(payload);
            if (operation == "SUBMIT_TERMINAL_PROPOSAL") return SubmitProposal(context, requestIdentity, request, payload);
            if (operation == "SUBMIT_RUN_GRAPH") return SubmitGraph(context, requestIdentity, request, payload);
            if (operation == "SUBMIT_RECONCILIATION") return SubmitReconciliation(context, requestIdentity, request, payload);
            if (operation == "RETRY_REQUEST") return Retry(payload);
            if (operation == "SIGNER_ONLY_OPERATION") throw new SecurityException("CALLER_NOT_AUTHORIZED");
            throw new R7ProtocolException("OPERATION_NOT_ALLOWED");
        }

        private SortedDictionary<string, object> Health()
        {
            SortedDictionary<string, object> result = R7PipeWindowsService.Success("AUTHORITY_HEALTHY");
            result.Add("activation_identity", activeUpgrade.ActivationIdentity);
            result.Add("binary_file_identity", binaryFileIdentity);
            result.Add("binary_sha256", binarySha256);
            result.Add("case_definitions_sha256", policy.AuthorityIdentities.CaseSha256);
            result.Add("expectations_sha256", policy.AuthorityIdentities.ExpectationSha256);
            result.Add("ledger_id", R7Fixed.LedgerId);
            result.Add("ledger_root", ledger.RootHash);
            result.Add("ledger_sequence", ledger.Sequence);
            result.Add("policy_sha256", policy.PolicySha256);
            result.Add("public_key_identity", R7Fixed.TerminalPublicKeyIdentity);
            result.Add("repository_write_access", false);
            result.Add("service_sid", R7Fixed.TerminalSid);
            return result;
        }

        private SortedDictionary<string, object> PublicTrust()
        {
            SortedDictionary<string, object> result = R7PipeWindowsService.Success("PUBLIC_TRUST_RESOLVED");
            result.Add("terminal_public_certificate_path", R7Fixed.TerminalPublicCertificatePath);
            result.Add("terminal_public_key_identity", R7Fixed.TerminalPublicKeyIdentity);
            result.Add("upgrade_public_certificate_path", R7Fixed.UpgradePublicCertificatePath);
            result.Add("upgrade_public_key_identity", R7BuildIdentity.UpgradePublicCertificateSha256);
            result.Add("version_history_classification", "VERSION_AWARE_APPEND_ONLY");
            return result;
        }

        private SortedDictionary<string, object> LedgerStatus()
        {
            SortedDictionary<string, object> result = R7PipeWindowsService.Success("LEDGER_STATUS_RESOLVED");
            result.Add("checkpoint_identity", ledger.CheckpointIdentity);
            result.Add("ledger_id", R7Fixed.LedgerId);
            result.Add("root_hash", ledger.RootHash);
            result.Add("sequence", ledger.Sequence);
            return result;
        }

        private SortedDictionary<string, object> VerifyPublicIdentity(SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "ledger_identity", "trust_identity");
            string ledgerIdentity = R7Json.String(payload, "ledger_identity", 64, 64);
            string trustIdentity = R7Json.String(payload, "trust_identity", 64, 64);
            if (!R7Hash.IsLowerSha256(ledgerIdentity) || !R7Hash.IsLowerSha256(trustIdentity)) throw new R7ProtocolException("PUBLIC_IDENTITY_FORMAT_INVALID");
            if (!R7Hash.FixedTimeEquals(trustIdentity, R7Fixed.TerminalPublicKeyIdentity)) throw new R7ProtocolException("TRUST_IDENTITY_MISMATCH");
            if (!R7Hash.FixedTimeEquals(ledgerIdentity, R7Fixed.LedgerId)) throw new R7ProtocolException("LEDGER_IDENTITY_MISMATCH");
            SortedDictionary<string, object> result = R7PipeWindowsService.Success("PUBLIC_IDENTITY_RESOLVED");
            result.Add("ledger_identity", ledgerIdentity);
            result.Add("trust_identity", trustIdentity);
            return result;
        }

        private SortedDictionary<string, object> LedgerEntry(SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "sequence");
            long sequence = R7Json.Integer(payload, "sequence", 1, Int64.MaxValue);
            R7LedgerRecord record = ledger.FindSequence(sequence);
            if (record == null) throw new R7ProtocolException("LEDGER_ENTRY_UNRESOLVED");
            SortedDictionary<string, object> result = R7PipeWindowsService.Success("LEDGER_ENTRY_RESOLVED");
            result.Add("content_address", record.ContentAddress);
            result.Add("entry_hash", record.EntryHash);
            result.Add("entry_identity", record.EntryIdentity);
            result.Add("operation", record.Operation);
            result.Add("schema_version", record.SchemaVersion);
            result.Add("sequence", record.Sequence);
            result.Add("subject_id", record.SubjectId);
            return result;
        }

        private SortedDictionary<string, object> Receipt(SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "receipt_identity");
            string identity = R7Json.String(payload, "receipt_identity", 64, 64);
            R7TransactionSnapshot transaction = transactions.FindByReceipt(identity);
            if (transaction == null || (transaction.State != "COMMITTED" && transaction.State != "RESPONSE_AVAILABLE")) throw new R7ProtocolException("RECEIPT_NOT_COMMITTED");
            string path = Path.Combine(R7Fixed.ReceiptRoot, identity + ".receipt.json");
            using (R7VerifiedFile file = R7SafeFile.Open(path, path, R7Fixed.ReceiptRoot, identity, R7Fixed.TerminalSid, null, policy.VolumeIdentity))
            {
                SortedDictionary<string, object> receiptPayload = R7Crypto.VerifyEnvelope(file.Bytes, R7Fixed.TerminalPublicKeyIdentity, verifier);
                SortedDictionary<string, object> result = R7PipeWindowsService.Success("TERMINAL_RECEIPT_RESOLVED");
                result.Add("receipt", Convert.ToBase64String(file.Bytes));
                result.Add("receipt_identity", identity);
                result.Add("terminal_classification", R7Json.String(receiptPayload, "terminal_classification", 1, 256));
                result.Add("transaction_state", transaction.State);
                return result;
            }
        }

        private SortedDictionary<string, object> RecoveryState(SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "request_identity");
            string identity = CanonicalGuid(R7Json.String(payload, "request_identity", 36, 36));
            R7TransactionSnapshot transaction = transactions.Find(identity);
            if (transaction == null) throw new R7ProtocolException("REQUEST_IDENTITY_UNRESOLVED");
            SortedDictionary<string, object> result = R7PipeWindowsService.Success("RECOVERY_STATE_RESOLVED");
            result.Add("last_sequence", transaction.LastSequence);
            result.Add("receipt_identity", transaction.ReceiptIdentity ?? String.Empty);
            result.Add("request_identity", identity);
            result.Add("response_identity", transaction.ResponseIdentity ?? String.Empty);
            result.Add("state", transaction.State);
            return result;
        }

        private SortedDictionary<string, object> ResolveInteraction(R7RequestContext context, SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "request_frame_sha256");
            string requestHash = R7Json.String(payload, "request_frame_sha256", 64, 64);
            string identity = evidence.ResolveLatestByRequestFrame(requestHash, context.Caller.UserSid);
            SortedDictionary<string, object> result = R7PipeWindowsService.Success("INTERACTION_RESOLVED");
            result.Add("interaction_identity", identity);
            result.Add("request_frame_sha256", requestHash);
            return result;
        }

        private SortedDictionary<string, object> InteractionEvidence(SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "interaction_identity");
            R7InteractionEvidence item = evidence.Resolve(R7Json.String(payload, "interaction_identity", 64, 64));
            SortedDictionary<string, object> responseMessage = R7Json.Child(item.Capture, "response_message");
            string status = R7Json.String(responseMessage, "status", 1, 64);
            string code = status == "COMPLETE" ? R7Json.String(responseMessage, "result_code", 1, 256) : R7Json.String(responseMessage, "error_code", 1, 256);
            SortedDictionary<string, object> result = R7PipeWindowsService.Success("INTERACTION_EVIDENCE_RESOLVED");
            result.Add("actual_code", code);
            result.Add("actual_status", status);
            result.Add("caller", R7Json.Child(item.Capture, "caller"));
            result.Add("capture_identity", item.CaptureIdentity);
            result.Add("interaction_identity", item.InteractionIdentity);
            result.Add("ledger_sequence_after", R7Json.Integer(item.Capture, "ledger_sequence_after", 0, Int64.MaxValue));
            result.Add("ledger_sequence_before", R7Json.Integer(item.Capture, "ledger_sequence_before", 0, Int64.MaxValue));
            result.Add("request_frame_sha256", R7Json.String(item.Capture, "request_frame_sha256", 64, 64));
            result.Add("response_frame_sha256", R7Json.String(item.Capture, "response_frame_sha256", 64, 64));
            return result;
        }

        private SortedDictionary<string, object> ResolveEvidenceSubmission(SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "request_frame_sha256", "service_role");
            string requestHash = R7Json.String(payload, "request_frame_sha256", 64, 64);
            string role = R7Json.String(payload, "service_role", 1, 64);
            string sid;
            if (role == "EXECUTION") sid = R7Fixed.ExecutionSid;
            else if (role == "OBSERVATION") sid = R7Fixed.ObservationSid;
            else if (role == "COMPARATOR") sid = R7Fixed.ComparatorSid;
            else throw new R7ProtocolException("EVIDENCE_SERVICE_ROLE_INVALID");
            R7InteractionEvidence item = evidence.ResolveLatestByRequestFrame(requestHash);
            RequireCaptureCaller(item.Capture, sid, role, "submission-resolution");
            SortedDictionary<string, object> result = R7PipeWindowsService.Success("EVIDENCE_SUBMISSION_RESOLVED");
            result.Add("interaction_identity", item.InteractionIdentity);
            result.Add("request_frame_sha256", requestHash);
            result.Add("service_role", role);
            return result;
        }

        private SortedDictionary<string, object> RawInteractionEvidence(SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "interaction_identity");
            R7InteractionEvidence item = evidence.Resolve(R7Json.String(payload, "interaction_identity", 64, 64));
            SortedDictionary<string, object> result = R7PipeWindowsService.Success("RAW_INTERACTION_EVIDENCE_RESOLVED");
            result.Add("capture_identity", item.CaptureIdentity);
            result.Add("interaction_identity", item.InteractionIdentity);
            result.Add("request_frame", R7Json.String(item.Capture, "request_frame", 1, R7Fixed.MaximumEncodedCaptureChars));
            result.Add("request_frame_sha256", R7Json.String(item.Capture, "request_frame_sha256", 64, 64));
            result.Add("response_frame", R7Json.String(item.Capture, "response_frame", 1, R7Fixed.MaximumEncodedFrameChars));
            result.Add("response_frame_sha256", R7Json.String(item.Capture, "response_frame_sha256", 64, 64));
            return result;
        }

        private SortedDictionary<string, object> VerifyReceiptOperation(string operation, SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "receipt_identity");
            string identity = R7Json.String(payload, "receipt_identity", 64, 64);
            if (operation == "CLASSIFY_RECEIPT" && transactions.FindByReceipt(identity) == null)
            {
                string legacyReceipt = Path.Combine(R7Fixed.TerminalStateRoot, "Receipts", identity + ".json");
                string legacyReconciliation = Path.Combine(R7Fixed.TerminalStateRoot, "Reconciliations", identity + ".json");
                R7VerifiedFile receiptFile;
                R7VerifiedFile reconciliationFile;
                bool hasReceipt = R7SafeFile.TryOpen(legacyReceipt, legacyReceipt, R7Fixed.LegacyReceiptRoot, identity, null, null, policy.VolumeIdentity, out receiptFile);
                bool hasReconciliation = R7SafeFile.TryOpen(legacyReconciliation, legacyReconciliation, R7Fixed.LegacyReconciliationRoot, identity, null, null, policy.VolumeIdentity, out reconciliationFile);
                if (hasReceipt && hasReconciliation) { receiptFile.Dispose(); reconciliationFile.Dispose(); throw new R7ProtocolException("RECEIPT_IDENTITY_AMBIGUOUS"); }
                if (!hasReceipt && !hasReconciliation) throw new R7ProtocolException("RECEIPT_IDENTITY_UNRESOLVED");
                using (R7VerifiedFile file = hasReceipt ? receiptFile : reconciliationFile) R7Crypto.VerifyEnvelope(file.Bytes, R7Fixed.TerminalPublicKeyIdentity, verifier);
                SortedDictionary<string, object> legacyResult = R7PipeWindowsService.Success("OLDEST_RECEIPT_CLASSIFIED");
                legacyResult.Add("classification", "VERSION_RESOLVED_HISTORICAL_EVIDENCE");
                legacyResult.Add("receipt_identity", identity);
                legacyResult.Add("receipt_type", hasReceipt ? "TERMINAL_RECEIPT" : "RECONCILIATION_RECEIPT");
                legacyResult.Add("underlying_authority_class", "STRUCTURALLY_VALID_REJECTED_NONAUTHORITATIVE_CANDIDATE_EVIDENCE");
                return legacyResult;
            }
            SortedDictionary<string, object> receipt = LoadCommittedReceipt(identity);
            string receiptType = R7Json.String(receipt, "receipt_type", 1, 128);
            string terminalClassification = R7Json.String(receipt, "terminal_classification", 1, 256);
            string classification = PublicReceiptClassification(terminalClassification, receiptType);
            if (operation == "VERIFY_TERMINAL_RECEIPT" && receiptType != "TERMINAL_RUN_RECEIPT") throw new R7ProtocolException("RECEIPT_TYPE_MISMATCH");
            if (operation == "VERIFY_RECONCILIATION" && receiptType != "RECONCILIATION_RECEIPT") throw new R7ProtocolException("RECEIPT_TYPE_MISMATCH");
            SortedDictionary<string, object> result = R7PipeWindowsService.Success(operation == "VERIFY_TERMINAL_RECEIPT" ? "TERMINAL_RECEIPT_VALID" : operation == "VERIFY_RECONCILIATION" ? "RECONCILIATION_VALID" : "CURRENT_RECEIPT_CLASSIFIED");
            result.Add("classification", classification);
            result.Add("receipt_identity", identity);
            result.Add("receipt_type", receiptType);
            result.Add("terminal_classification", terminalClassification);
            return result;
        }

        private static string PublicReceiptClassification(string terminalClassification, string receiptType)
        {
            if (terminalClassification == "COMMITTED_AUTHORITATIVE_FRESH_RECEIPT") return "VALID_AUTHORITATIVE_RECEIPT";
            if (terminalClassification == "COMMITTED_RECONCILIATION") return "VALID_AUTHORITATIVE_RECONCILIATION";
            if (terminalClassification == "VALID_NONAUTHORITATIVE_BOOTSTRAP_RECONCILIATION") return "STRUCTURALLY_VALID_NONAUTHORITATIVE_BOOTSTRAP_RECONCILIATION";
            if (terminalClassification == "VALID_NONAUTHORITATIVE_BOOTSTRAP_EVIDENCE") return "STRUCTURALLY_VALID_NONAUTHORITATIVE_BOOTSTRAP_EVIDENCE";
            if (terminalClassification == "VALID_NONAUTHORITATIVE_CANDIDATE_EVIDENCE") return "STRUCTURALLY_VALID_CANDIDATE_EVIDENCE";
            if (terminalClassification.IndexOf("ABORT", StringComparison.Ordinal) >= 0) return "ABORTED_ISSUANCE";
            return receiptType == "RECONCILIATION_RECEIPT" ? "VERSION_RESOLVED_NONAUTHORITATIVE_RECONCILIATION" : "VERSION_RESOLVED_NONAUTHORITY";
        }

        private SortedDictionary<string, object> ClassifySequence(SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "sequence");
            long sequence = R7Json.Integer(payload, "sequence", 1, Int64.MaxValue);
            R7LedgerRecord record = ledger.FindSequence(sequence);
            if (record == null) throw new R7ProtocolException("LEDGER_ENTRY_UNRESOLVED");
            string classification = sequence <= 5 ? "VALID_PROVISIONED_INFRASTRUCTURE_AUTHORITY" : sequence <= 678 ? "STRUCTURALLY_VALID_REJECTED_NONAUTHORITATIVE_CANDIDATE_EVIDENCE" : "VERSION_RESOLVED_REMEDIATION_ENTRY";
            string code = "HISTORICAL_ENTRY_CLASSIFIED";
            if (sequence == 332) { classification = "INCOMPLETE_ISSUANCE_SUPERSEDED_NONAUTHORITY"; code = "SEQUENCE_332_CLASSIFIED"; }
            if (sequence == 678) { classification = "ABORTED_CLIENT_REJECTED_ISSUANCE_NONAUTHORITY"; code = "SEQUENCE_678_CLASSIFIED"; }
            SortedDictionary<string, object> result = R7PipeWindowsService.Success(code);
            result.Add("classification", classification);
            result.Add("schema_version", record.SchemaVersion);
            result.Add("sequence", sequence);
            return result;
        }

        private SortedDictionary<string, object> VersionHistory(SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload);
            SortedDictionary<string, object> result = R7PipeWindowsService.Success("VERSION_HISTORY_RESOLVED");
            result.Add("current_activation_identity", activeUpgrade.ActivationIdentity);
            result.Add("current_interface_version", R7Fixed.InterfaceVersion);
            result.Add("current_policy_sha256", policy.PolicySha256);
            result.Add("rejected_v3_classification", "REJECTED_NONAUTHORITATIVE_CANDIDATE_EVIDENCE");
            result.Add("upgrade_authorization_identity", activeUpgrade.AuthorizationIdentity);
            return result;
        }

        private SortedDictionary<string, object> PublicVerificationEvidence(SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "case_id", "output_measurement", "target_operation", "target_payload");
            string caseId = R7Json.String(payload, "case_id", 1, 128);
            string operation = R7Json.String(payload, "target_operation", 1, 128);
            SortedDictionary<string, object> targetPayload = R7Json.Child(payload, "target_payload");
            R7CaseDefinition definition = authority.Case(caseId);
            if (definition.Driver != "PUBLIC_VERIFIER" || definition.Operation != operation) throw new R7ProtocolException("PUBLIC_VERIFIER_CASE_AUTHORITY_MISMATCH");
            SortedDictionary<string, object> claimedMeasurement = R7Json.Child(payload, "output_measurement");
            R7Json.ExactKeys(claimedMeasurement, "canonical_path", "creation_time", "file_identity", "final_nt_path", "hard_link_count", "owner_sid", "security_descriptor_sha256", "sha256", "short_path", "size", "streams", "volume_identity");
            string path = R7Json.String(claimedMeasurement, "canonical_path", 3, 4096);
            if (!path.StartsWith(R7Fixed.PublicVerifierProbeRoot + Path.DirectorySeparatorChar, StringComparison.Ordinal) ||
                !String.Equals(Path.GetFileName(path), "public-result.json", StringComparison.Ordinal)) throw new R7ProtocolException("PUBLIC_VERIFIER_OUTPUT_PATH_INVALID");
            long linkCount = R7Json.Integer(claimedMeasurement, "hard_link_count", 1, 1);
            SortedDictionary<string, object> output;
            using (R7VerifiedFile file = R7SafeFile.OpenDependency(
                path,
                path,
                R7Fixed.PublicVerifierProbeRoot,
                R7Json.String(claimedMeasurement, "sha256", 64, 64),
                R7Json.String(claimedMeasurement, "owner_sid", 1, 256),
                R7Json.String(claimedMeasurement, "security_descriptor_sha256", 64, 64),
                R7Json.String(claimedMeasurement, "volume_identity", 8, 64),
                (uint)linkCount))
            {
                if (!R7Hash.FixedTimeEquals(R7Hash.Bytes(R7Json.Encode(file.Measurement.ToJson())), R7Hash.Bytes(R7Json.Encode(claimedMeasurement)))) throw new R7ProtocolException("PUBLIC_VERIFIER_OUTPUT_FILE_IDENTITY_CHANGED");
                output = RequireObject(R7Json.Parse(file.Bytes));
            }
            R7Json.ExactKeys(output, "artifact_type", "case_id", "private_key_required", "public_verification", "running_service_required_for_public_verification", "schema_version", "status", "target_operation", "target_payload_sha256", "target_result");
            if (R7Json.String(output, "artifact_type", 1, 256) != "R7_PUBLIC_VERIFIER_OUTER_CASE_RESULT" ||
                R7Json.String(output, "case_id", 1, 128) != caseId ||
                R7Json.String(output, "target_operation", 1, 128) != operation ||
                R7Json.String(output, "schema_version", 1, 128) != "1.0.0" ||
                R7Json.String(output, "status", 1, 64) != "PASS" ||
                R7Json.Boolean(output, "private_key_required") ||
                R7Json.Boolean(output, "running_service_required_for_public_verification") ||
                !R7Hash.FixedTimeEquals(R7Json.String(output, "target_payload_sha256", 64, 64), R7Hash.Bytes(R7Json.Encode(targetPayload)))) throw new R7ProtocolException("PUBLIC_VERIFIER_OUTPUT_BINDING_INVALID");
            SortedDictionary<string, object> publicVerification = R7Json.Child(output, "public_verification");
            SortedDictionary<string, object> signerVerification = R7PublicVerifierProgram.VerifyAll();
            if (!R7Hash.FixedTimeEquals(R7Hash.Bytes(R7Json.Encode(publicVerification)), R7Hash.Bytes(R7Json.Encode(signerVerification)))) throw new R7ProtocolException("PUBLIC_VERIFICATION_REDERIVATION_MISMATCH");
            SortedDictionary<string, object> signerTarget = DerivePublicVerifierTarget(caseId, operation, targetPayload, signerVerification);
            SortedDictionary<string, object> publicTarget = R7Json.Child(output, "target_result");
            if (!R7Hash.FixedTimeEquals(R7Hash.Bytes(R7Json.Encode(publicTarget)), R7Hash.Bytes(R7Json.Encode(signerTarget)))) throw new R7ProtocolException("PUBLIC_TARGET_REDERIVATION_MISMATCH");
            return signerTarget;
        }

        private SortedDictionary<string, object> DerivePublicVerifierTarget(string caseId, string operation, SortedDictionary<string, object> payload, SortedDictionary<string, object> verification)
        {
            if (R7Json.String(verification, "status", 1, 64) != "PASS" || R7Json.Boolean(verification, "private_key_required") || R7Json.Boolean(verification, "running_service_required")) throw new R7ProtocolException("SIGNER_PUBLIC_VERIFICATION_PREREQUISITE_INVALID");
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
                R7LedgerRecord record = ledger.FindSequence(sequence);
                if (record == null || (sequence != 332 && sequence != 678)) throw new R7ProtocolException("PUBLIC_SPECIAL_SEQUENCE_UNRESOLVED");
                string classification = sequence == 332 ? "INCOMPLETE_ISSUANCE_SUPERSEDED_NONAUTHORITY" : "ABORTED_CLIENT_REJECTED_ISSUANCE_NONAUTHORITY";
                SortedDictionary<string, object> row = R7Json.Child(verification, sequence == 332 ? "sequence_332" : "sequence_678");
                if (R7Json.String(row, "classification", 1, 256) != classification) throw new R7ProtocolException("PUBLIC_SPECIAL_SEQUENCE_CLASSIFICATION_MISMATCH");
                SortedDictionary<string, object> result = R7PipeWindowsService.Success(sequence == 332 ? "SEQUENCE_332_CLASSIFIED" : "SEQUENCE_678_CLASSIFIED");
                result.Add("classification", classification);
                result.Add("sequence", sequence);
                return result;
            }
            if (operation == "VERIFY_TERMINAL_RECEIPT" || operation == "VERIFY_RECONCILIATION" || operation == "CLASSIFY_RECEIPT")
            {
                if (caseId == "HIS-001")
                {
                    R7Json.ExactKeys(payload, "claimed_schema_version", "receipt_identity");
                    string receiptIdentity = R7Json.String(payload, "receipt_identity", 64, 64);
                    SortedDictionary<string, object> receipt = LoadCommittedReceipt(receiptIdentity);
                    string actualSchema = R7Json.String(receipt, "schema_version", 1, 128);
                    if (String.Equals(R7Json.String(payload, "claimed_schema_version", 1, 128), actualSchema, StringComparison.Ordinal)) throw new R7ProtocolException("WRONG_VERSION_ATTACK_NOT_PRESENT");
                    return R7PipeWindowsService.Rejection("VERSION_RULE_MISMATCH");
                }
                R7Json.ExactKeys(payload, "receipt_identity");
                SortedDictionary<string, object> resolved = VerifyReceiptOperation(operation, payload);
                SortedDictionary<string, object> result = R7PipeWindowsService.Success(R7Json.String(resolved, "result_code", 1, 256));
                result.Add("classification", R7Json.String(resolved, "classification", 1, 256));
                result.Add("receipt_identity", R7Json.String(resolved, "receipt_identity", 64, 64));
                result.Add("receipt_type", R7Json.String(resolved, "receipt_type", 1, 128));
                return result;
            }
            throw new R7ProtocolException("PUBLIC_TARGET_OPERATION_NOT_ALLOWED");
        }

        private SortedDictionary<string, object> SubmitExecutionEnvelope(R7RequestContext context, SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "evidence", "evidence_kind");
            string kind = R7Json.String(payload, "evidence_kind", 1, 64);
            SortedDictionary<string, object> value = R7Json.Child(payload, "evidence");
            if (kind == "EVENT") return SubmitEvent(value);
            if (kind == "PRINCIPAL_PROBE") return PrincipalProbe(context, value);
            if (kind == "RECOVERY") return RecoveryEvidence(value);
            if (kind == "HOSTILE_GRAPH") return SemanticProbe(value);
            throw new R7ProtocolException("EXECUTION_EVIDENCE_KIND_NOT_ALLOWED");
        }

        private SortedDictionary<string, object> SubmitObservationEnvelope(R7RequestContext context, SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "evidence", "evidence_kind");
            string kind = R7Json.String(payload, "evidence_kind", 1, 64);
            SortedDictionary<string, object> value = R7Json.Child(payload, "evidence");
            if (kind == "OBSERVATION") return SubmitObservation(value);
            if (kind == "PRINCIPAL_PROBE") return PrincipalProbe(context, value);
            throw new R7ProtocolException("OBSERVATION_EVIDENCE_KIND_NOT_ALLOWED");
        }

        private SortedDictionary<string, object> SubmitComparatorEnvelope(R7RequestContext context, SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "evidence", "evidence_kind");
            string kind = R7Json.String(payload, "evidence_kind", 1, 64);
            SortedDictionary<string, object> value = R7Json.Child(payload, "evidence");
            if (kind == "COMPARISON") return SubmitComparator(value);
            if (kind == "PRINCIPAL_PROBE") return PrincipalProbe(context, value);
            if (kind == "HOSTILE_SUMMARY") return HostileComparatorProbe(value);
            throw new R7ProtocolException("COMPARATOR_EVIDENCE_KIND_NOT_ALLOWED");
        }

        private SortedDictionary<string, object> SubmitEvent(SortedDictionary<string, object> payload)
        {
            if (payload.ContainsKey("expected_status") || payload.ContainsKey("expected_code") || payload.ContainsKey("desired_outcome")) throw new R7ProtocolException("EXPECTED_FIELD_IN_EVENT_REJECTED");
            R7Json.ExactKeys(payload, "base_interaction_identity", "case_id", "event", "raw_request_frame", "raw_response_frame");
            string baseIdentity = R7Json.String(payload, "base_interaction_identity", 64, 64);
            authority.Case(R7Json.String(payload, "case_id", 1, 128));
            evidence.Resolve(baseIdentity);
            SortedDictionary<string, object> value = R7Json.Child(payload, "event");
            R7Json.ExactKeys(value, "operation", "request_frame_sha256", "response_frame_sha256");
            byte[] rawRequest = Convert.FromBase64String(R7Json.String(payload, "raw_request_frame", 1, R7Fixed.MaximumEncodedCaptureChars));
            byte[] rawResponse = Convert.FromBase64String(R7Json.String(payload, "raw_response_frame", 1, R7Fixed.MaximumEncodedFrameChars));
            if (!R7Hash.FixedTimeEquals(R7Hash.Bytes(rawRequest), R7Json.String(value, "request_frame_sha256", 64, 64)) ||
                !R7Hash.FixedTimeEquals(R7Hash.Bytes(rawResponse), R7Json.String(value, "response_frame_sha256", 64, 64))) throw new R7ProtocolException("EVENT_RAW_FRAME_HASH_MISMATCH");
            SortedDictionary<string, object> result = R7PipeWindowsService.Success("EVENT_EVIDENCE_RECORDED");
            result.Add("base_interaction_identity", baseIdentity);
            return result;
        }

        private SortedDictionary<string, object> SubmitObservation(SortedDictionary<string, object> payload)
        {
            if (payload.ContainsKey("expected_status") || payload.ContainsKey("expected_code") || payload.ContainsKey("desired_outcome")) throw new R7ProtocolException("EXPECTED_FIELD_IN_OBSERVATION_REJECTED");
            R7Json.ExactKeys(payload, "base_interaction_identity", "case_id", "observation", "raw_request_frame", "raw_response_frame");
            string baseIdentity = R7Json.String(payload, "base_interaction_identity", 64, 64);
            authority.Case(R7Json.String(payload, "case_id", 1, 128));
            evidence.Resolve(baseIdentity);
            SortedDictionary<string, object> value = R7Json.Child(payload, "observation");
            R7Json.ExactKeys(value, "actual_code", "actual_status", "ledger_sequence_after", "ledger_sequence_before", "side_effect_identity");
            byte[] rawRequest = Convert.FromBase64String(R7Json.String(payload, "raw_request_frame", 1, R7Fixed.MaximumEncodedCaptureChars));
            byte[] rawResponse = Convert.FromBase64String(R7Json.String(payload, "raw_response_frame", 1, R7Fixed.MaximumEncodedFrameChars));
            if (rawRequest.Length == 0 || rawResponse.Length == 0) throw new R7ProtocolException("OBSERVATION_RAW_EVIDENCE_REQUIRED");
            SortedDictionary<string, object> result = R7PipeWindowsService.Success("OBSERVATION_EVIDENCE_RECORDED");
            result.Add("base_interaction_identity", baseIdentity);
            return result;
        }

        private SortedDictionary<string, object> SubmitComparator(SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "actual_code", "actual_status", "base_interaction_identity", "case_id", "comparison", "event_interaction_identity", "observation_interaction_identity", "raw_response_frame");
            string baseIdentity = R7Json.String(payload, "base_interaction_identity", 64, 64);
            R7Json.String(payload, "actual_code", 1, 256);
            R7Json.String(payload, "actual_status", 1, 64);
            authority.Case(R7Json.String(payload, "case_id", 1, 128));
            evidence.Resolve(baseIdentity);
            evidence.Resolve(R7Json.String(payload, "event_interaction_identity", 64, 64));
            evidence.Resolve(R7Json.String(payload, "observation_interaction_identity", 64, 64));
            SortedDictionary<string, object> comparison = R7Json.Child(payload, "comparison");
            R7Json.ExactKeys(comparison, "comparison_code", "raw_graph_complete");
            byte[] rawResponse = Convert.FromBase64String(R7Json.String(payload, "raw_response_frame", 1, R7Fixed.MaximumEncodedFrameChars));
            if (rawResponse.Length == 0) throw new R7ProtocolException("COMPARATOR_RAW_EVIDENCE_REQUIRED");
            SortedDictionary<string, object> result = R7PipeWindowsService.Success("COMPARATOR_EVIDENCE_RECORDED");
            result.Add("base_interaction_identity", baseIdentity);
            return result;
        }

        private SortedDictionary<string, object> HostileComparatorProbe(SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "case_id", "mutation", "summary");
            R7CaseDefinition definition = authority.Case(R7Json.String(payload, "case_id", 1, 128));
            if (!String.Equals(definition.Mutation, R7Json.String(payload, "mutation", 1, 256), StringComparison.Ordinal)) throw new R7ProtocolException("CASE_MUTATION_MISMATCH");
            SortedDictionary<string, object> summary = R7Json.Child(payload, "summary");
            R7Json.ExactKeys(summary, "actual_code", "actual_status", "raw_evidence_present");
            R7Json.String(summary, "actual_code", 1, 256);
            R7Json.String(summary, "actual_status", 1, 64);
            if (R7Json.Boolean(summary, "raw_evidence_present")) throw new R7ProtocolException("HOSTILE_PROBE_NOT_HOSTILE");
            throw new R7ProtocolException("RAW_EVIDENCE_REQUIRED");
        }

        private SortedDictionary<string, object> AuthorityProbe(SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "case_id", "claim", "mutation");
            string caseId = R7Json.String(payload, "case_id", 1, 128);
            R7CaseDefinition definition = authority.Case(caseId);
            string mutation = R7Json.String(payload, "mutation", 1, 256);
            if (definition.Driver != "AUTHORITY_VERIFIER" || definition.Mutation != mutation) throw new R7ProtocolException("CASE_MUTATION_MISMATCH");
            SortedDictionary<string, object> claim = R7Json.Child(payload, "claim");
            R7Json.ExactKeys(claim, "clause_hash", "governing_blob", "governing_commit", "governing_path", "line_range", "requirement_id", "section_heading");
            string claimedCommit = R7Json.String(claim, "governing_commit", 40, 40);
            if (String.Equals(claimedCommit, "f0cfbce97e913a133530dd66a70326b1e03a0fb6", StringComparison.Ordinal)) throw new R7ProtocolException("PROHIBITED_AUTHORITY_SOURCE");
            SortedDictionary<string, object> requirement;
            try { requirement = authority.Requirement(R7Json.String(claim, "requirement_id", 1, 128)); }
            catch (R7ProtocolException exception)
            {
                if (exception.Code == "REQUIREMENT_IDENTITY_UNRESOLVED") throw new R7ProtocolException("UNKNOWN_CLAUSE");
                throw;
            }
            foreach (string field in new string[] { "governing_blob", "governing_commit", "governing_path", "line_range", "section_heading" })
            {
                if (!String.Equals(R7Json.String(claim, field, 1, 4096), R7Json.String(requirement, field, 1, 4096), StringComparison.Ordinal)) throw new R7ProtocolException("CLAUSE_LOCATOR_MISMATCH", field);
            }
            if (!R7Hash.FixedTimeEquals(R7Json.String(claim, "clause_hash", 64, 64), R7Json.String(requirement, "clause_raw_sha256", 64, 64))) throw new R7ProtocolException("CLAUSE_HASH_MISMATCH");
            return R7PipeWindowsService.Success("CASE_AUTHORITY_VERIFIED");
        }

        private SortedDictionary<string, object> CoverageProbe(SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "case_id", "claimed_case_ids", "claimed_requirement_ids", "mutation", "registry_identity");
            R7CaseDefinition definition = authority.Case(R7Json.String(payload, "case_id", 1, 128));
            string mutation = R7Json.String(payload, "mutation", 1, 256);
            if (definition.Driver != "AUTHORITY_VERIFIER" || definition.Mutation != mutation || !R7Hash.FixedTimeEquals(R7Json.String(payload, "registry_identity", 64, 64), policy.AuthorityIdentities.CoverageSha256)) throw new R7ProtocolException("COVERAGE_AUTHORITY_MISMATCH");
            HashSet<string> claimedCases = StrictIdentifierSet(R7Json.Array(payload, "claimed_case_ids"), "CLAIMED_CASE");
            HashSet<string> claimedRequirements = StrictIdentifierSet(R7Json.Array(payload, "claimed_requirement_ids"), "CLAIMED_REQUIREMENT");
            HashSet<string> actualCases = new HashSet<string>(authority.CaseIds, StringComparer.Ordinal);
            HashSet<string> actualRequirements = new HashSet<string>(authority.RequirementIds, StringComparer.Ordinal);
            foreach (string claimed in claimedCases) if (!actualCases.Contains(claimed)) throw new R7ProtocolException("UNAUTHORIZED_NORMATIVE_CASE", claimed);
            if (!claimedCases.SetEquals(actualCases) || !claimedRequirements.SetEquals(actualRequirements)) throw new R7ProtocolException("REQUIREMENT_COVERAGE_GAP");
            return R7PipeWindowsService.Success("COVERAGE_VERIFIED");
        }

        private static HashSet<string> StrictIdentifierSet(object[] values, string kind)
        {
            HashSet<string> result = new HashSet<string>(StringComparer.Ordinal);
            foreach (object raw in values)
            {
                string value = raw as string;
                if (value == null || value.Length < 1 || value.Length > 256 || !result.Add(value)) throw new R7ProtocolException(kind + "_SET_INVALID");
            }
            return result;
        }

        private SortedDictionary<string, object> SemanticProbe(SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "case_id", "graph", "mutation");
            R7CaseDefinition definition = authority.Case(R7Json.String(payload, "case_id", 1, 128));
            string mutation = R7Json.String(payload, "mutation", 1, 256);
            if (!String.Equals(definition.Mutation, mutation, StringComparison.Ordinal) ||
                (definition.Driver != "SEMANTIC_PROBE" && !definition.CaseId.StartsWith("SEM-", StringComparison.Ordinal))) throw new R7ProtocolException("SEMANTIC_CASE_AUTHORITY_MISMATCH");
            SortedDictionary<string, object> graph = R7Json.Child(payload, "graph");
            R7Json.ExactKeys(graph, "claimed_invocation_count", "claimed_process_id", "claimed_receipt_identity", "claimed_request_frame_sha256", "claimed_response_frame_sha256", "claimed_side_effect_identity", "raw_evidence_present", "summary_only");
            long invocationCount = R7Json.Integer(graph, "claimed_invocation_count", 0, Int64.MaxValue);
            long processId = R7Json.Integer(graph, "claimed_process_id", 0, Int64.MaxValue);
            string receiptIdentity = R7Json.String(graph, "claimed_receipt_identity", 64, 64);
            string requestIdentity = R7Json.String(graph, "claimed_request_frame_sha256", 64, 64);
            string responseIdentity = R7Json.String(graph, "claimed_response_frame_sha256", 64, 64);
            string sideEffectIdentity = R7Json.String(graph, "claimed_side_effect_identity", 64, 64);
            bool raw = R7Json.Boolean(graph, "raw_evidence_present");
            bool summaryOnly = R7Json.Boolean(graph, "summary_only");
            if ((mutation == "INNER_PASS_OUTER_NOT_INVOKED" || mutation == "WORKER_PASS_ZERO_INVOCATION") && invocationCount == 0) throw new R7ProtocolException("OUTER_INTERFACE_NOT_INVOKED");
            if (mutation == "FABRICATED_REQUEST_RESPONSE" && (!raw || requestIdentity != R7Fixed.ZeroHash || responseIdentity != R7Fixed.ZeroHash)) throw new R7ProtocolException("RAW_FRAME_EVIDENCE_MISMATCH");
            if (mutation == "FABRICATED_SIDE_EFFECTS" && (!raw || sideEffectIdentity != R7Fixed.ZeroHash)) throw new R7ProtocolException("RAW_SIDE_EFFECT_EVIDENCE_MISMATCH");
            if (mutation == "FABRICATED_RECEIPT_MEMBERSHIP" && transactions.FindByReceipt(receiptIdentity) == null) throw new R7ProtocolException("LEDGER_MEMBERSHIP_NOT_RESOLVED");
            if (mutation == "FABRICATED_PROCESS_IDENTITY" && processId > 0) throw new R7ProtocolException("PROCESS_IDENTITY_MISMATCH");
            if (mutation == "SUMMARY_ONLY_COMPARISON" && summaryOnly && !raw) throw new R7ProtocolException("RAW_EVIDENCE_REQUIRED");
            if (mutation == "TWO_INVALID_GRAPHS" && !raw) throw new R7ProtocolException("INVALID_GRAPH_RECONCILIATION");
            if (mutation == "SUPERVISOR_REPLAY_ZERO_EVENTS" && invocationCount == 0) throw new R7ProtocolException("REPLAY_WITHOUT_CURRENT_EVENTS");
            if (mutation == "SHARED_SEMANTIC_BUILDER" && !raw) throw new R7ProtocolException("SEMANTIC_STAGE_COUPLING_REJECTED");
            if (mutation == "MISSING_ACTUAL_DEFAULT" && !raw) throw new R7ProtocolException("RAW_EVIDENCE_REQUIRED");
            throw new R7ProtocolException("SEMANTIC_PROBE_DID_NOT_ESTABLISH_ATTACK");
        }

        private SortedDictionary<string, object> PrincipalProbe(R7RequestContext context, SortedDictionary<string, object> payload)
        {
            if (payload.ContainsKey("spawned_process_id")) R7Json.ExactKeys(payload, "case_id", "mutation", "probe_result", "spawned_process_id", "target_identity");
            else R7Json.ExactKeys(payload, "case_id", "mutation", "probe_result", "target_identity");
            string caseId = R7Json.String(payload, "case_id", 1, 128);
            R7CaseDefinition definition = authority.Case(caseId);
            string mutation = R7Json.String(payload, "mutation", 1, 256);
            if (!String.Equals(definition.Mutation, mutation, StringComparison.Ordinal) ||
                (definition.Driver != "ACL_PROBE" && definition.Driver != "TOKEN_PROBE" && definition.Driver != "SOURCE_PROBE")) throw new R7ProtocolException("PRINCIPAL_CASE_AUTHORITY_MISMATCH");
            if ((mutation == "DESCENDANT_CAPABILITY") != payload.ContainsKey("spawned_process_id")) throw new R7ProtocolException("DESCENDANT_PROCESS_EVIDENCE_INVALID");
            SortedDictionary<string, object> probe = R7Json.Child(payload, "probe_result");
            R7Json.ExactKeys(probe, "access_granted", "error_code", "target_sha256_before", "target_sha256_after");
            bool childReportedAccess = R7Json.Boolean(probe, "access_granted");
            string childBefore = R7Json.String(probe, "target_sha256_before", 64, 64);
            string childAfter = R7Json.String(probe, "target_sha256_after", 64, 64);
            string requestedTarget = R7Json.String(payload, "target_identity", 1, 256);
            string resolvedTarget;
            string attemptedOperation;
            string denialType;
            int nativeError;
            SortedDictionary<string, object> descendantEvidence = R7Json.Object();
            if (mutation == "DESCENDANT_CAPABILITY")
            {
                long rawProcessId = R7Json.Integer(payload, "spawned_process_id", 1, UInt32.MaxValue);
                uint parentProcessId;
                R7CallerIdentity descendant = R7NativeCaller.CaptureProcess((uint)rawProcessId, out parentProcessId);
                R7ComponentIdentity executionComponent = policy.Component("EXECUTION");
                string activatedFileIdentity;
                if (parentProcessId != (uint)context.Caller.ProcessId ||
                    !String.Equals(context.Caller.UserSid, R7Fixed.ExecutionSid, StringComparison.Ordinal) ||
                    !String.Equals(descendant.UserSid, context.Caller.UserSid, StringComparison.Ordinal) ||
                    !String.Equals(descendant.AuthenticationId, context.Caller.AuthenticationId, StringComparison.Ordinal) ||
                    !String.Equals(descendant.ProcessPath, executionComponent.Path, StringComparison.Ordinal) ||
                    !R7Hash.FixedTimeEquals(descendant.ProcessSha256, executionComponent.Sha256) ||
                    !activeUpgrade.InstalledFileIdentities.TryGetValue("EXECUTION", out activatedFileIdentity) ||
                    !String.Equals(descendant.ProcessFileIdentity, activatedFileIdentity, StringComparison.Ordinal) ||
                    descendant.ContainsTerminalSignerSid || !StringArrayEqual(descendant.GroupSids, context.Caller.GroupSids) ||
                    !StringArrayEqual(descendant.Privileges, context.Caller.Privileges)) throw new R7ProtocolException("DESCENDANT_PROCESS_IDENTITY_MISMATCH");
                descendantEvidence = descendant.ToJson();
                descendantEvidence.Add("parent_process_id", (long)parentProcessId);
            }
            if (mutation == "SIGNER_PROCESS_CREATION")
            {
                uint parentProcessId;
                R7CallerIdentity recapturedCaller = R7NativeCaller.CaptureProcess((uint)context.Caller.ProcessId, out parentProcessId);
                if (parentProcessId == (uint)signerProcessId || !String.Equals(recapturedCaller.ProcessFileIdentity, context.Caller.ProcessFileIdentity, StringComparison.Ordinal)) throw new R7ProtocolException("SIGNER_LAUNCHED_SEMANTIC_CHILD");
                descendantEvidence = R7Json.Object("execution_service_parent_process_id", (long)parentProcessId, "signer_process_id", signerProcessId);
            }
            bool accessGranted = DerivePrincipalAccess(context, mutation, out resolvedTarget, out attemptedOperation, out denialType, out nativeError);
            context.ServerDerivedEvidence = R7Json.Object(
                "attempt_performed", true,
                "attempted_operation", attemptedOperation,
                "caller_process_file_identity", context.Caller.ProcessFileIdentity,
                "caller_process_id", context.Caller.ProcessId,
                "caller_token_id", context.Caller.TokenId,
                "caller_user_sid", context.Caller.UserSid,
                "child_reported_access_granted", childReportedAccess,
                "child_reported_error_code", R7Json.String(probe, "error_code", 1, 64),
                "child_reported_target_sha256_after", childAfter,
                "child_reported_target_sha256_before", childBefore,
                "derivation", "SERVER_OS_PROBE_UNDER_PIPE_CLIENT_IMPERSONATION",
                "descendant_process_evidence", descendantEvidence,
                "denial_type", denialType,
                "native_error", nativeError.ToString("x8", CultureInfo.InvariantCulture),
                "requested_target_identity", requestedTarget,
                "resolved_target", resolvedTarget,
                "server_access_granted", accessGranted,
                "signer_sid_present_in_captured_token", context.Caller.ContainsTerminalSignerSid);
            if (childReportedAccess != accessGranted) throw new R7ProtocolException("CHILD_PROBE_REPORT_CONFLICT");
            if (accessGranted) throw new R7ProtocolException("PRINCIPAL_ISOLATION_BREACH");
            if (context.Caller.ContainsTerminalSignerSid) throw new R7ProtocolException("CHILD_TOKEN_CONTAINS_SIGNER_SID");
            if (mutation == "SIGNER_SID_MEMBERSHIP") throw new R7ProtocolException("SIGNER_SID_EXCLUDED");
            if (mutation == "DESCENDANT_CAPABILITY" || mutation == "IMPERSONATE_SIGNER") throw new R7ProtocolException("DESCENDANT_CAPABILITY_DENIED");
            if (mutation == "EVENT_PRODUCER_READ_EXPECTATION" || mutation == "OBSERVER_READ_EXPECTATION") throw new R7ProtocolException("EXPECTATION_ACL_ACCESS_DENIED");
            if (mutation == "SIGNER_PROCESS_CREATION")
            {
                SortedDictionary<string, object> result = R7PipeWindowsService.Success("NO_SIGNER_SEMANTIC_CHILD");
                result.Add("signer_sid_excluded_from_caller", true);
                return result;
            }
            throw new R7ProtocolException("OS_ACCESS_DENIED");
        }

        private static bool StringArrayEqual(string[] first, string[] second)
        {
            if (first == null || second == null || first.Length != second.Length) return false;
            for (int index = 0; index < first.Length; index++) if (!String.Equals(first[index], second[index], StringComparison.Ordinal)) return false;
            return true;
        }

        private SortedDictionary<string, object> ConcurrencyProbe(SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "case_id", "first_request_frame_sha256", "mutation", "request_identity", "second_request_frame_sha256");
            string caseId = R7Json.String(payload, "case_id", 1, 128);
            authority.Case(caseId);
            string mutation = R7Json.String(payload, "mutation", 1, 256);
            string requestIdentity = CanonicalGuid(R7Json.String(payload, "request_identity", 36, 36));
            string firstHash = R7Json.String(payload, "first_request_frame_sha256", 64, 64);
            string secondHash = R7Json.String(payload, "second_request_frame_sha256", 64, 64);
            if (!R7Hash.IsLowerSha256(firstHash) || !R7Hash.IsLowerSha256(secondHash)) throw new R7ProtocolException("REQUEST_FRAME_IDENTITY_INVALID");

            R7InteractionEvidence first;
            R7InteractionEvidence second;
            if (R7Hash.FixedTimeEquals(firstHash, secondHash))
            {
                R7InteractionEvidence[] matches = evidence.ResolveAllByRequestFrame(firstHash);
                if (matches.Length != 2) throw new R7ProtocolException("CONCURRENT_INTERACTION_COUNT_MISMATCH");
                first = matches[0];
                second = matches[1];
            }
            else
            {
                R7InteractionEvidence[] firstMatches = evidence.ResolveAllByRequestFrame(firstHash);
                R7InteractionEvidence[] secondMatches = evidence.ResolveAllByRequestFrame(secondHash);
                if (firstMatches.Length != 1 || secondMatches.Length != 1) throw new R7ProtocolException("CONCURRENT_INTERACTION_COUNT_MISMATCH");
                first = firstMatches[0];
                second = secondMatches[0];
            }
            if (String.Equals(first.InteractionIdentity, second.InteractionIdentity, StringComparison.Ordinal)) throw new R7ProtocolException("CONCURRENT_INTERACTIONS_NOT_DISTINCT");
            RequireCaptureCaller(first.Capture, R7Fixed.OperatorSid, "ADVERSARIAL_HARNESS", "concurrent-first");
            RequireCaptureCaller(second.Capture, R7Fixed.OperatorSid, "ADVERSARIAL_HARNESS", "concurrent-second");
            if (String.Equals(R7Json.String(first.Capture, "connection_identity", 36, 36), R7Json.String(second.Capture, "connection_identity", 36, 36), StringComparison.Ordinal)) throw new R7ProtocolException("CONCURRENT_CONNECTION_IDENTITY_REUSED");
            long firstConcurrent = R7Json.Integer(first.Capture, "concurrent_connection_count_at_receive", 1, Int64.MaxValue);
            long secondConcurrent = R7Json.Integer(second.Capture, "concurrent_connection_count_at_receive", 1, Int64.MaxValue);
            if (Math.Max(firstConcurrent, secondConcurrent) < 2) throw new R7ProtocolException("OS_CONCURRENT_CONNECTION_NOT_OBSERVED");

            SortedDictionary<string, object> firstRequest = CaptureRequest(first.Capture);
            SortedDictionary<string, object> secondRequest = CaptureRequest(second.Capture);
            VerifyConcurrentProposalRequest(firstRequest, requestIdentity);
            VerifyConcurrentProposalRequest(secondRequest, requestIdentity);
            SortedDictionary<string, object> firstResponse = R7Json.Child(first.Capture, "response_message");
            SortedDictionary<string, object> secondResponse = R7Json.Child(second.Capture, "response_message");
            string firstStatus = R7Json.String(firstResponse, "status", 1, 64);
            string secondStatus = R7Json.String(secondResponse, "status", 1, 64);
            string firstCode = firstStatus == "COMPLETE" ? R7Json.String(firstResponse, "result_code", 1, 256) : R7Json.String(firstResponse, "error_code", 1, 256);
            string secondCode = secondStatus == "COMPLETE" ? R7Json.String(secondResponse, "result_code", 1, 256) : R7Json.String(secondResponse, "error_code", 1, 256);
            int advanced = 0;
            if (R7Json.Integer(first.Capture, "ledger_sequence_after", 0, Int64.MaxValue) > R7Json.Integer(first.Capture, "ledger_sequence_before", 0, Int64.MaxValue)) advanced++;
            if (R7Json.Integer(second.Capture, "ledger_sequence_after", 0, Int64.MaxValue) > R7Json.Integer(second.Capture, "ledger_sequence_before", 0, Int64.MaxValue)) advanced++;
            if (advanced != 1) throw new R7ProtocolException("CONCURRENT_TRANSACTION_ADVANCEMENT_AMBIGUOUS");
            R7TransactionSnapshot transaction = transactions.Find(requestIdentity);
            if (transaction == null || transaction.State != "RESPONSE_AVAILABLE" || !R7Hash.IsLowerSha256(transaction.ReceiptIdentity) || !R7Hash.IsLowerSha256(transaction.ResponseIdentity)) throw new R7ProtocolException("CONCURRENT_TRANSACTION_STATE_UNRESOLVED");

            string resultCode;
            if (mutation == "CONCURRENT_IDENTICAL_RETRY")
            {
                if (!R7Hash.FixedTimeEquals(firstHash, secondHash) || firstStatus != "COMPLETE" || secondStatus != "COMPLETE" || firstCode != "REQUEST_RECEIVED" || secondCode != "REQUEST_RECEIVED" ||
                    !R7Hash.FixedTimeEquals(R7Json.String(first.Capture, "response_frame_sha256", 64, 64), R7Json.String(second.Capture, "response_frame_sha256", 64, 64)) ||
                    !R7Hash.FixedTimeEquals(transaction.RequestSha256, firstHash) || !R7Hash.FixedTimeEquals(transaction.ResponseIdentity, R7Json.String(first.Capture, "response_frame_sha256", 64, 64))) throw new R7ProtocolException("CONCURRENT_IDENTICAL_RETRY_NOT_IDEMPOTENT");
                resultCode = "CONCURRENT_IDENTICAL_RETRY_RESOLVED";
            }
            else if (mutation == "CONCURRENT_CONFLICTING_BYTES")
            {
                if (R7Hash.FixedTimeEquals(firstHash, secondHash)) throw new R7ProtocolException("CONCURRENT_CONFLICT_BYTES_NOT_DISTINCT");
                int completeCount = (firstStatus == "COMPLETE" && firstCode == "REQUEST_RECEIVED" ? 1 : 0) + (secondStatus == "COMPLETE" && secondCode == "REQUEST_RECEIVED" ? 1 : 0);
                int conflictCount = (firstStatus == "REJECTED" && firstCode == "REQUEST_IDENTITY_CONFLICT" ? 1 : 0) + (secondStatus == "REJECTED" && secondCode == "REQUEST_IDENTITY_CONFLICT" ? 1 : 0);
                string committedHash = firstStatus == "COMPLETE" ? firstHash : secondHash;
                string committedResponseHash = firstStatus == "COMPLETE" ? R7Json.String(first.Capture, "response_frame_sha256", 64, 64) : R7Json.String(second.Capture, "response_frame_sha256", 64, 64);
                if (completeCount != 1 || conflictCount != 1 || !R7Hash.FixedTimeEquals(transaction.RequestSha256, committedHash) || !R7Hash.FixedTimeEquals(transaction.ResponseIdentity, committedResponseHash)) throw new R7ProtocolException("CONCURRENT_CONFLICT_CLASSIFICATION_INVALID");
                resultCode = "CONCURRENT_CONFLICT_REJECTED";
            }
            else throw new R7ProtocolException("CONCURRENCY_MUTATION_INVALID");

            string proof = objects.Put(R7Json.Object(
                "case_id", caseId,
                "first_capture_identity", first.CaptureIdentity,
                "first_concurrent_connection_count", firstConcurrent,
                "first_request_frame_sha256", firstHash,
                "first_response_frame_sha256", R7Json.String(first.Capture, "response_frame_sha256", 64, 64),
                "mutation", mutation,
                "request_identity", requestIdentity,
                "second_capture_identity", second.CaptureIdentity,
                "second_concurrent_connection_count", secondConcurrent,
                "second_request_frame_sha256", secondHash,
                "second_response_frame_sha256", R7Json.String(second.Capture, "response_frame_sha256", 64, 64),
                "terminal_receipt_identity", transaction.ReceiptIdentity,
                "terminal_response_identity", transaction.ResponseIdentity,
                "terminal_state", transaction.State));
            SortedDictionary<string, object> result = R7PipeWindowsService.Success(resultCode);
            result.Add("concurrency_evidence_identity", proof);
            result.Add("request_identity_under_test", requestIdentity);
            return result;
        }

        private static void VerifyConcurrentProposalRequest(SortedDictionary<string, object> request, string requestIdentity)
        {
            R7Json.ExactKeys(request, "interface_version", "operation", "payload", "protocol_version", "request_identity");
            if (!String.Equals(R7Json.String(request, "operation", 1, 128), "SUBMIT_TERMINAL_PROPOSAL", StringComparison.Ordinal) ||
                !String.Equals(R7Json.String(request, "request_identity", 36, 36), requestIdentity, StringComparison.Ordinal) ||
                !String.Equals(R7Json.String(request, "interface_version", 1, 128), R7Fixed.InterfaceVersion, StringComparison.Ordinal) ||
                !String.Equals(R7Json.String(request, "protocol_version", 1, 64), R7Fixed.ProtocolVersion, StringComparison.Ordinal)) throw new R7ProtocolException("CONCURRENT_REQUEST_IDENTITY_MISMATCH");
            SortedDictionary<string, object> proposal = R7Json.Child(request, "payload");
            R7Json.ExactKeys(proposal, "checkout_identity", "configuration", "proposal_identity");
            string checkout = R7Json.String(proposal, "checkout_identity", 64, 64);
            string proposalIdentity = R7Json.String(proposal, "proposal_identity", 64, 64);
            if (!R7Hash.IsLowerSha256(checkout) || !R7Hash.IsLowerSha256(proposalIdentity)) throw new R7ProtocolException("CONCURRENT_PROPOSAL_IDENTITY_INVALID");
            ValidateConfiguration(R7Json.Child(proposal, "configuration"));
        }

        private bool DerivePrincipalAccess(R7RequestContext context, string mutation, out string resolvedTarget, out string attemptedOperation, out string denialType, out int nativeError)
        {
            if (context.RunAsCaller == null) throw new SecurityException("CALLER_IMPERSONATION_CONTEXT_UNAVAILABLE");
            resolvedTarget = String.Empty;
            attemptedOperation = String.Empty;
            denialType = String.Empty;
            nativeError = 0;
            if (mutation == "SIGNER_SID_MEMBERSHIP")
            {
                attemptedOperation = "CAPTURE_EFFECTIVE_TOKEN_MEMBERSHIP";
                resolvedTarget = R7Fixed.TerminalSid;
                return context.Caller.ContainsTerminalSignerSid;
            }
            if (mutation == "SIGNER_PROCESS_CREATION")
            {
                attemptedOperation = "VERIFY_SIGNER_DOES_NOT_SPAWN_SEMANTIC_CHILD";
                uint[] children = R7NativeCaller.DirectChildProcessIds((uint)signerProcessId);
                resolvedTarget = signerProcessInstanceIdentity + "|DIRECT_CHILD_COUNT=" + children.Length.ToString(CultureInfo.InvariantCulture);
                denialType = children.Length == 0 ? "NO_DIRECT_CHILD_PROCESSES" : "UNEXPECTED_SIGNER_CHILD_PROCESSES";
                return children.Length != 0;
            }

            string target = ResolvePrincipalProbeTarget(mutation);
            string operation = PrincipalProbeOperation(mutation);
            bool granted = false;
            string capturedDenial = String.Empty;
            int capturedError = 0;
            context.RunAsCaller(delegate()
            {
                try
                {
                    if (mutation == "DIRECT_LEDGER_APPEND" || mutation == "DIRECT_RECEIPT_WRITE" || mutation == "DIRECT_EVIDENCE_WRITE")
                    {
                        using (SafeFileHandle handle = CreateFileW(target, FileAddFile, FileShareRead | FileShareWrite | FileShareDelete, IntPtr.Zero, OpenExisting, FileFlagBackupSemantics | FileFlagOpenReparsePoint, IntPtr.Zero))
                        {
                            granted = !handle.IsInvalid;
                            if (!granted) capturedError = Marshal.GetLastWin32Error();
                        }
                    }
                    else if (mutation == "SIGN_ARBITRARY_BYTES")
                    {
                        using (RSA attemptedSigner = R7Crypto.LoadTerminalSigner())
                        {
                            byte[] signature = R7Crypto.Sign(attemptedSigner, new UTF8Encoding(false, true).GetBytes("R7_HOSTILE_CHILD_ARBITRARY_SIGNING_PROBE"));
                            granted = signature != null && signature.Length > 0;
                        }
                    }
                    else if (mutation == "IMPERSONATE_SIGNER" || mutation == "DESCENDANT_CAPABILITY")
                    {
                        granted = TryDuplicateSignerToken(out capturedError);
                    }
                    else
                    {
                        FileAccess access = mutation == "CONTROL_PUBLIC_TRUST_READ" || mutation == "DIRECT_KEY_OPEN" || mutation == "DIRECT_UPGRADE_KEY_OPEN" || mutation == "EVENT_PRODUCER_READ_EXPECTATION" || mutation == "OBSERVER_READ_EXPECTATION" ? FileAccess.Read : FileAccess.Write;
                        using (FileStream stream = new FileStream(target, FileMode.Open, access, FileShare.Read)) { granted = true; }
                    }
                }
                catch (UnauthorizedAccessException exception) { capturedDenial = exception.GetType().FullName; capturedError = exception.HResult; }
                catch (CryptographicException exception) { capturedDenial = exception.GetType().FullName; capturedError = exception.HResult; }
                catch (SecurityException exception) { capturedDenial = exception.GetType().FullName; capturedError = exception.HResult; }
                catch (IOException exception) { capturedDenial = exception.GetType().FullName; capturedError = exception.HResult; }
            });
            resolvedTarget = target;
            attemptedOperation = operation;
            denialType = capturedDenial;
            nativeError = capturedError;
            return granted;
        }

        private string ResolvePrincipalProbeTarget(string mutation)
        {
            if (mutation == "DIRECT_KEY_OPEN" || mutation == "SIGN_ARBITRARY_BYTES") return R7BuildIdentity.TerminalKeyFilePath;
            if (mutation == "DIRECT_UPGRADE_KEY_OPEN") return R7BuildIdentity.UpgradeKeyFilePath;
            if (mutation == "EVENT_PRODUCER_READ_EXPECTATION" || mutation == "OBSERVER_READ_EXPECTATION") return R7Fixed.ExpectationPath;
            if (mutation == "DIRECT_LEDGER_APPEND") return R7Fixed.LedgerRoot;
            if (mutation == "DIRECT_TRUST_WRITE" || mutation == "CONTROL_PUBLIC_TRUST_READ") return R7Fixed.TerminalPublicCertificatePath;
            if (mutation == "DIRECT_RECEIPT_WRITE") return R7Fixed.ReceiptRoot;
            if (mutation == "DIRECT_EVIDENCE_WRITE") return R7Fixed.EvidenceRoot;
            if (mutation == "DIRECT_RECEIPT_REPLACE") return FirstPrincipalProbeFile(R7Fixed.ReceiptRoot, "*.receipt.json");
            if (mutation == "DIRECT_EVIDENCE_REPLACE") return FirstPrincipalProbeFile(R7Fixed.EvidenceRoot, "*.interaction.json");
            if (mutation == "IMPERSONATE_SIGNER" || mutation == "DESCENDANT_CAPABILITY") return "PROCESS_TOKEN:" + signerProcessId.ToString(CultureInfo.InvariantCulture);
            throw new R7ProtocolException("PRINCIPAL_PROBE_MUTATION_NOT_ALLOWED", mutation);
        }

        private static string PrincipalProbeOperation(string mutation)
        {
            if (mutation == "SIGN_ARBITRARY_BYTES") return "OPEN_CNG_KEY_AND_SIGN_ARBITRARY_BYTES";
            if (mutation == "IMPERSONATE_SIGNER" || mutation == "DESCENDANT_CAPABILITY") return "OPEN_AND_DUPLICATE_TERMINAL_SIGNER_PROCESS_TOKEN";
            if (mutation == "DIRECT_LEDGER_APPEND" || mutation == "DIRECT_RECEIPT_WRITE" || mutation == "DIRECT_EVIDENCE_WRITE") return "OPEN_FIXED_DIRECTORY_FOR_FILE_ADD";
            if (mutation == "DIRECT_TRUST_WRITE" || mutation == "DIRECT_RECEIPT_REPLACE" || mutation == "DIRECT_EVIDENCE_REPLACE") return "OPEN_EXISTING_AUTHORITY_FILE_FOR_WRITE_WITHOUT_MODIFICATION";
            return "OPEN_FIXED_AUTHORITY_FILE_FOR_READ";
        }

        private static string FirstPrincipalProbeFile(string root, string pattern)
        {
            string[] paths = Directory.GetFiles(root, pattern, SearchOption.TopDirectoryOnly);
            Array.Sort(paths, StringComparer.Ordinal);
            if (paths.Length == 0) throw new R7ProtocolException("PRINCIPAL_PROBE_TARGET_UNAVAILABLE", root);
            return paths[0];
        }

        private bool TryDuplicateSignerToken(out int error)
        {
            error = 0;
            using (SafeProcessHandle process = OpenProcessForProbe(ProcessQueryLimitedInformation, false, (uint)signerProcessId))
            {
                if (process.IsInvalid) { error = Marshal.GetLastWin32Error(); return false; }
                SafeTokenHandle source;
                if (!OpenProcessTokenForProbe(process, TokenDuplicate | TokenQuery | TokenAssignPrimary, out source)) { error = Marshal.GetLastWin32Error(); return false; }
                using (source)
                {
                    SafeTokenHandle duplicate;
                    if (!DuplicateTokenExForProbe(source, TokenAllAccess, IntPtr.Zero, SecurityImpersonation, TokenImpersonation, out duplicate)) { error = Marshal.GetLastWin32Error(); return false; }
                    using (duplicate) return true;
                }
            }
        }

        private const uint FileAddFile = 0x00000002;
        private const uint FileShareRead = 0x00000001;
        private const uint FileShareWrite = 0x00000002;
        private const uint FileShareDelete = 0x00000004;
        private const uint OpenExisting = 3;
        private const uint FileFlagBackupSemantics = 0x02000000;
        private const uint FileFlagOpenReparsePoint = 0x00200000;
        private const uint LoadLibrarySearchDefaultDirs = 0x00001000;
        private const uint ProcessQueryLimitedInformation = 0x00001000;
        private const uint TokenAssignPrimary = 0x0001;
        private const uint TokenDuplicate = 0x0002;
        private const uint TokenQuery = 0x0008;
        private const uint TokenAllAccess = 0x000F01FF;
        private const int SecurityImpersonation = 2;
        private const int TokenImpersonation = 2;
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)] private static extern SafeFileHandle CreateFileW(string name, uint access, uint share, IntPtr security, uint creation, uint flags, IntPtr templateFile);
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)] private static extern IntPtr LoadLibraryExW(string fileName, IntPtr file, uint flags);
        [DllImport("kernel32.dll", SetLastError = true)] private static extern bool FreeLibrary(IntPtr module);
        [DllImport("kernel32.dll", EntryPoint = "OpenProcess", SetLastError = true)] private static extern SafeProcessHandle OpenProcessForProbe(uint access, bool inherit, uint processId);
        [DllImport("advapi32.dll", EntryPoint = "OpenProcessToken", SetLastError = true)] private static extern bool OpenProcessTokenForProbe(SafeProcessHandle process, uint access, out SafeTokenHandle token);
        [DllImport("advapi32.dll", EntryPoint = "DuplicateTokenEx", SetLastError = true)] private static extern bool DuplicateTokenExForProbe(SafeTokenHandle source, uint access, IntPtr attributes, int impersonationLevel, int tokenType, out SafeTokenHandle duplicate);

        private SortedDictionary<string, object> FrameBoundary(R7RequestContext context, SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "padding");
            R7Json.String(payload, "padding", 0, R7Fixed.MaximumPayloadBytes);
            if (context.RequestPayload == null || context.RequestPayload.Length != R7Fixed.MaximumPayloadBytes || context.RequestFrame == null || context.RequestFrame.Length != R7Fixed.MaximumFrameBytes) throw new R7ProtocolException("FRAME_BOUNDARY_SIZE_MISMATCH");
            return R7PipeWindowsService.Success("FRAME_SIZE_ACCEPTED");
        }

        private SortedDictionary<string, object> PathProbe(SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "attack_path", "case_id", "mutation", "reference_path");
            authority.Case(R7Json.String(payload, "case_id", 1, 128));
            string attack = Path.GetFullPath(R7Json.String(payload, "attack_path", 3, 4096));
            string reference = Path.GetFullPath(R7Json.String(payload, "reference_path", 3, 4096));
            string derivedReferenceSha = String.Empty;
            string rejection = String.Empty;
            try
            {
                if (!attack.StartsWith(R7Fixed.ExecutionTestRoot + Path.DirectorySeparatorChar, StringComparison.Ordinal) || !reference.StartsWith(R7Fixed.ExecutionTestRoot + Path.DirectorySeparatorChar, StringComparison.Ordinal)) throw new R7ProtocolException("TEST_ROOT_ESCAPE");
                using (R7VerifiedFile referenceFile = R7SafeFile.Open(reference, reference, R7Fixed.ExecutionTestRoot, null, null, null, policy.VolumeIdentity))
                {
                    derivedReferenceSha = referenceFile.Measurement.Sha256;
                    using (R7VerifiedFile attackFile = R7SafeFile.Open(attack, attack, R7Fixed.ExecutionTestRoot, derivedReferenceSha, referenceFile.Measurement.OwnerSid, referenceFile.Measurement.SecurityDescriptorSha256, referenceFile.Measurement.VolumeIdentity))
                    {
                        if (!String.Equals(attackFile.Measurement.FileIdentity, referenceFile.Measurement.FileIdentity, StringComparison.Ordinal)) throw new R7ProtocolException("REFERENCE_FILE_IDENTITY_MISMATCH");
                    }
                }
            }
            catch (R7ProtocolException exception) { rejection = exception.Code; }
            if (String.IsNullOrEmpty(rejection)) throw new R7ProtocolException("PATH_ATTACK_ACCEPTED");
            string proof = objects.Put(R7Json.Object(
                "attack_path", attack,
                "case_id", R7Json.String(payload, "case_id", 1, 128),
                "derived_reference_sha256", derivedReferenceSha,
                "held_handle_validation_error", rejection,
                "mutation", R7Json.String(payload, "mutation", 1, 256),
                "reference_path", reference));
            SortedDictionary<string, object> result = R7PipeWindowsService.Rejection("UNSAFE_FILE_IDENTITY");
            result.Add("path_probe_evidence_identity", proof);
            return result;
        }

        private SortedDictionary<string, object> DependencyProbe(SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "attack_path", "case_id", "claimed_component_sha256", "mutation", "reference_path", "role");
            string caseId = R7Json.String(payload, "case_id", 1, 128);
            R7CaseDefinition definition = authority.Case(caseId);
            string mutation = R7Json.String(payload, "mutation", 1, 256);
            if (definition.Driver != "DEPENDENCY_PROBE" || definition.Mutation != mutation) throw new R7ProtocolException("DEPENDENCY_CASE_AUTHORITY_MISMATCH");
            string attackText = R7Json.String(payload, "attack_path", 0, 4096);
            string referenceText = R7Json.String(payload, "reference_path", 0, 4096);
            if (mutation == "PYTHON_USER_SITE" || mutation == "PYTHON_CURRENT_DIRECTORY" || mutation == "UNMANIFESTED_MODULE" || mutation == "GLOBAL_GIT_REPLACEMENT")
            {
                if (attackText.Length != 0 || referenceText.Length != 0) throw new R7ProtocolException("REMOVED_DEPENDENCY_ATTACK_PATH_UNEXPECTED");
                List<object> measuredModules = new List<object>();
                foreach (ProcessModule module in System.Diagnostics.Process.GetCurrentProcess().Modules)
                {
                    string name = module.ModuleName.ToLowerInvariant();
                    if (name.Contains("python") || name == "git.exe" || name.StartsWith("libgit")) throw new R7ProtocolException("FORBIDDEN_RUNTIME_DEPENDENCY_LOADED");
                    string path = Path.GetFullPath(module.FileName);
                    using (R7VerifiedFile file = R7SafeFile.OpenMeasured(path, path, Path.GetDirectoryName(path))) measuredModules.Add(R7Json.Object("file_identity", file.Measurement.FileIdentity, "path", file.Measurement.FinalNtPath, "sha256", file.Measurement.Sha256));
                }
                string proof = objects.Put(R7Json.Object(
                    "case_id", caseId,
                    "closed_dependency_manifest_sha256", policy.DependencyManifestSha256,
                    "git_runtime_invocations", 0L,
                    "mutation", mutation,
                    "process_modules", measuredModules.ToArray(),
                    "python_runtime_invocations", 0L));
                SortedDictionary<string, object> result = R7PipeWindowsService.Success("REMOVED_FROM_AUTHORITY_PATH");
                result.Add("dependency_probe_evidence_identity", proof);
                result.Add("git_runtime_invocations", 0L);
                result.Add("python_runtime_invocations", 0L);
                return result;
            }
            string role = R7Json.String(payload, "role", 1, 128);
            string claimed = R7Json.String(payload, "claimed_component_sha256", 64, 64);
            string governedRole = mutation == "DLL_SIDELOAD" ? "EXECUTION" : mutation == "COMPILER_REFERENCE_SUBSTITUTION" ? "BUILD_RECEIPT" : "TERMINAL_SIGNER";
            if (!String.Equals(role, governedRole, StringComparison.Ordinal)) throw new R7ProtocolException("DEPENDENCY_ROLE_MISMATCH");
            string expectedReference;
            string expectedHash;
            string expectedOwner;
            string expectedAcl;
            string expectedVolume;
            uint expectedLinks;
            if (mutation == "FRAMEWORK_ASSEMBLY_REPLACEMENT")
            {
                expectedReference = @"C:\Program Files (x86)\Reference Assemblies\Microsoft\Framework\.NETFramework\v4.8\System.dll";
                R7DependencyIdentity expected = dependencies.ResolveManifestedIdentity(expectedReference);
                expectedHash = expected.Sha256; expectedOwner = expected.OwnerSid; expectedAcl = expected.SecurityDescriptorSha256; expectedVolume = expected.VolumeIdentity; expectedLinks = expected.LinkCount;
            }
            else if (mutation == "DLL_SIDELOAD")
            {
                R7ComponentIdentity expected = policy.Component("EXECUTION");
                expectedReference = expected.Path;
                expectedHash = expected.Sha256; expectedOwner = R7Fixed.SystemSid; expectedAcl = null; expectedVolume = policy.VolumeIdentity; expectedLinks = 1;
            }
            else if (mutation == "COMPILER_REFERENCE_SUBSTITUTION")
            {
                expectedReference = @"C:\Program Files (x86)\Reference Assemblies\Microsoft\Framework\.NETFramework\v4.8\mscorlib.dll";
                R7DependencyIdentity expected = dependencies.ResolveManifestedIdentity(expectedReference);
                expectedHash = expected.Sha256; expectedOwner = expected.OwnerSid; expectedAcl = expected.SecurityDescriptorSha256; expectedVolume = expected.VolumeIdentity; expectedLinks = expected.LinkCount;
            }
            else throw new R7ProtocolException("DEPENDENCY_MUTATION_NOT_ALLOWED");
            string reference = Path.GetFullPath(referenceText);
            string attack = Path.GetFullPath(attackText);
            if (!String.Equals(reference, expectedReference, StringComparison.Ordinal) || !attack.StartsWith(R7Fixed.ExecutionTestRoot + Path.DirectorySeparatorChar, StringComparison.Ordinal)) throw new R7ProtocolException("DEPENDENCY_PROBE_PATH_INVALID");
            string rejection = String.Empty;
            string referenceIdentity;
            bool namedLoadAttempted = false;
            bool namedLoadSucceeded = false;
            int namedLoadError = 0;
            using (R7VerifiedFile referenceFile = R7SafeFile.OpenDependency(reference, expectedReference, Path.GetDirectoryName(expectedReference), expectedHash, expectedOwner, expectedAcl, expectedVolume, expectedLinks))
            {
                referenceIdentity = referenceFile.Measurement.FileIdentity;
                if (mutation == "DLL_SIDELOAD")
                {
                    namedLoadAttempted = true;
                    IntPtr loaded = LoadLibraryExW(Path.GetFileName(attack), IntPtr.Zero, LoadLibrarySearchDefaultDirs);
                    if (loaded != IntPtr.Zero)
                    {
                        namedLoadSucceeded = true;
                        FreeLibrary(loaded);
                        throw new R7ProtocolException("DLL_SIDELOAD_SEARCH_PATH_BREACH");
                    }
                    namedLoadError = Marshal.GetLastWin32Error();
                    if (namedLoadError != 126) throw new R7ProtocolException("DLL_SIDELOAD_PROBE_ERROR_UNEXPECTED", namedLoadError.ToString(CultureInfo.InvariantCulture));
                    foreach (ProcessModule module in System.Diagnostics.Process.GetCurrentProcess().Modules)
                    {
                        if (String.Equals(Path.GetFullPath(module.FileName), attack, StringComparison.OrdinalIgnoreCase)) throw new R7ProtocolException("DLL_SIDELOAD_MODULE_LOADED");
                    }
                }
                try
                {
                    using (R7VerifiedFile attackFile = R7SafeFile.OpenDependency(attack, attack, R7Fixed.ExecutionTestRoot, expectedHash, expectedOwner, expectedAcl, expectedVolume, expectedLinks))
                    {
                        if (!String.Equals(attackFile.Measurement.FileIdentity, referenceIdentity, StringComparison.Ordinal)) rejection = "DEPENDENCY_FILE_IDENTITY_MISMATCH";
                    }
                }
                catch (Exception exception)
                {
                    if (!(exception is R7ProtocolException) && !(exception is SecurityException) && !(exception is UnauthorizedAccessException) && !(exception is IOException)) throw;
                    rejection = exception.GetType().Name + "|" + exception.Message;
                }
            }
            if (String.IsNullOrEmpty(rejection)) throw new R7ProtocolException("DEPENDENCY_PROBE_DID_NOT_SUBSTITUTE");
            string proofIdentity = objects.Put(R7Json.Object(
                "attack_path", attack,
                "case_id", caseId,
                "child_claimed_component_sha256", claimed,
                "expected_component_sha256", expectedHash,
                "held_reference_file_identity", referenceIdentity,
                "mutation", mutation,
                "named_load_attempted", namedLoadAttempted,
                "named_load_error", namedLoadError,
                "named_load_succeeded", namedLoadSucceeded,
                "reference_path", reference,
                "rejection", rejection,
                "role", role));
            SortedDictionary<string, object> rejected = R7PipeWindowsService.Rejection("DEPENDENCY_IDENTITY_MISMATCH");
            rejected.Add("dependency_probe_evidence_identity", proofIdentity);
            return rejected;
        }

        private SortedDictionary<string, object> RecoveryEvidence(SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "case_id", "fault_point", "isolated_root", "mutation", "result_identity");
            R7CaseDefinition definition = authority.Case(R7Json.String(payload, "case_id", 1, 128));
            string root = Path.GetFullPath(R7Json.String(payload, "isolated_root", 3, 4096));
            if (!root.StartsWith(R7Fixed.ExecutionTestRoot + Path.DirectorySeparatorChar, StringComparison.Ordinal)) throw new R7ProtocolException("TEST_ROOT_ESCAPE");
            string fault = R7Json.String(payload, "fault_point", 1, 256);
            string mutation = R7Json.String(payload, "mutation", 1, 256);
            if (definition.Driver != "RECOVERY_HARNESS" || definition.Mutation != mutation || definition.Mutation != fault) throw new R7ProtocolException("RECOVERY_CASE_AUTHORITY_MISMATCH");
            SortedDictionary<string, object> recovery = R7RecoveryProbeAuditor.Verify(root, fault, R7Json.String(payload, "result_identity", 64, 64));
            string code = R7Json.String(recovery, "derived_result_code", 1, 256);
            bool rejected = code == "ORPHAN_RESPONSE_NONAUTHORITY" || code == "ILLEGAL_DUPLICATE_TRANSITION" || code == "RECEIPT_NOT_COMMITTED" || code == "CONFLICTING_CLASSIFICATION";
            SortedDictionary<string, object> result = rejected ? R7PipeWindowsService.Rejection(code) : R7PipeWindowsService.Success(code);
            result.Add("independent_recovery_rederivation", recovery);
            return result;
        }

        private SortedDictionary<string, object> HistoryProbe(SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "case_id", "claimed_classification", "claimed_schema_version", "mutation", "sequence");
            R7CaseDefinition definition = authority.Case(R7Json.String(payload, "case_id", 1, 128));
            string mutation = R7Json.String(payload, "mutation", 1, 256);
            if (definition.Mutation != mutation) throw new R7ProtocolException("HISTORY_CASE_AUTHORITY_MISMATCH");
            long sequence = R7Json.Integer(payload, "sequence", 0, Int64.MaxValue);
            string claimedClassification = R7Json.String(payload, "claimed_classification", 1, 256);
            string claimedSchema = R7Json.String(payload, "claimed_schema_version", 0, 128);
            if (sequence == 0 && claimedClassification == "VERIFY_ALL")
            {
                for (long index = 1; index <= ledger.Sequence; index++)
                {
                    R7LedgerRecord retained = ledger.FindSequence(index);
                    if (retained == null || String.IsNullOrEmpty(HistoricalClassification(retained))) throw new R7ProtocolException("HISTORICAL_ENTRY_UNCLASSIFIED", index.ToString(CultureInfo.InvariantCulture));
                }
                SortedDictionary<string, object> result = R7PipeWindowsService.Success("ALL_ENTRIES_CLASSIFIED");
                result.Add("verified_entry_count", ledger.Sequence);
                return result;
            }
            R7LedgerRecord record = ledger.FindSequence(sequence);
            if (record == null) throw new R7ProtocolException("LEDGER_ENTRY_UNRESOLVED");
            if (claimedClassification == "REQUEST_NEW_SEQUENCE") throw new R7ProtocolException("HISTORICAL_SEQUENCE_NONREUSABLE");
            if (claimedSchema.Length != 0 && !String.Equals(claimedSchema, record.SchemaVersion, StringComparison.Ordinal)) throw new R7ProtocolException("VERSION_RULE_MISMATCH");
            string classification = HistoricalClassification(record);
            if (!String.Equals(claimedClassification, classification, StringComparison.Ordinal)) throw new R7ProtocolException("CONFLICTING_CLASSIFICATION");
            SortedDictionary<string, object> response = R7PipeWindowsService.Success(sequence == 332 ? "SEQUENCE_332_CLASSIFIED" : sequence == 678 ? "SEQUENCE_678_CLASSIFIED" : "HISTORICAL_ENTRY_CLASSIFIED");
            response.Add("classification", classification);
            response.Add("sequence", sequence);
            return response;
        }

        private static string HistoricalClassification(R7LedgerRecord record)
        {
            if (record.Sequence == 332) return "INCOMPLETE_ISSUANCE_SUPERSEDED_NONAUTHORITY";
            if (record.Sequence == 678) return "ABORTED_CLIENT_REJECTED_ISSUANCE_NONAUTHORITY";
            if (record.Sequence <= 5) return "VALID_PROVISIONED_INFRASTRUCTURE_AUTHORITY";
            if (record.Sequence <= 678) return "STRUCTURALLY_VALID_REJECTED_NONAUTHORITATIVE_CANDIDATE_EVIDENCE";
            return "VERSION_RESOLVED_REMEDIATION_ENTRY";
        }

        private SortedDictionary<string, object> TraceProbe(SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "case_id", "mutation", "trace");
            R7CaseDefinition definition = authority.Case(R7Json.String(payload, "case_id", 1, 128));
            string mutation = R7Json.String(payload, "mutation", 1, 256);
            if (definition.Driver != "TRACE_VERIFIER" || definition.Mutation != mutation) throw new R7ProtocolException("TRACE_CASE_AUTHORITY_MISMATCH");
            SortedDictionary<string, object> trace = R7Json.Child(payload, "trace");
            R7Json.ExactKeys(trace, "edges", "nodes");
            Dictionary<string, string> kinds = new Dictionary<string, string>(StringComparer.Ordinal);
            Dictionary<string, string> evidenceIdentities = new Dictionary<string, string>(StringComparer.Ordinal);
            Dictionary<string, string> provenanceIdentities = new Dictionary<string, string>(StringComparer.Ordinal);
            Dictionary<string, List<string>> edges = new Dictionary<string, List<string>>(StringComparer.Ordinal);
            foreach (object raw in R7Json.Array(trace, "nodes"))
            {
                SortedDictionary<string, object> node = RequireObject(raw);
                R7Json.ExactKeys(node, "authority_requirement_id", "evidence_identity", "id", "kind", "provenance_identity");
                string id = R7Json.String(node, "id", 1, 128);
                string kind = R7Json.String(node, "kind", 1, 128);
                if (kinds.ContainsKey(id)) throw new R7ProtocolException("TRACE_NODE_DUPLICATE");
                string requirementId = R7Json.String(node, "authority_requirement_id", 1, 128);
                try { authority.Requirement(requirementId); }
                catch (R7ProtocolException exception)
                {
                    if (kind == "DEPENDENCY" && exception.Code == "REQUIREMENT_IDENTITY_UNRESOLVED") throw new R7ProtocolException("UNAUTHORIZED_DEPENDENCY");
                    throw new R7ProtocolException("TRACE_AUTHORITY_UNRESOLVED");
                }
                kinds.Add(id, kind);
                evidenceIdentities.Add(id, R7Json.String(node, "evidence_identity", 64, 64));
                provenanceIdentities.Add(id, R7Json.String(node, "provenance_identity", 64, 64));
                edges.Add(id, new List<string>());
            }
            if (kinds.Count == 0) throw new R7ProtocolException("TRACE_NODE_MISSING");
            HashSet<string> edgeSet = new HashSet<string>(StringComparer.Ordinal);
            foreach (object raw in R7Json.Array(trace, "edges"))
            {
                SortedDictionary<string, object> edge = RequireObject(raw);
                R7Json.ExactKeys(edge, "from", "to");
                string from = R7Json.String(edge, "from", 1, 128);
                string to = R7Json.String(edge, "to", 1, 128);
                if (!kinds.ContainsKey(from) || !kinds.ContainsKey(to) || !edgeSet.Add(from + "\n" + to)) throw new R7ProtocolException("TRACE_EDGE_INVALID");
                edges[from].Add(to);
            }
            if (TraceHasCycle(edges)) throw new R7ProtocolException("CIRCULAR_TRACE");
            foreach (KeyValuePair<string, string> node in kinds)
            {
                if (node.Value == "SOURCE" && !TraceReachesKind(node.Key, "EXECUTION", kinds, edges)) throw new R7ProtocolException("EXECUTION_PROOF_MISSING");
                if (node.Value == "EVENT" && R7Hash.FixedTimeEquals(evidenceIdentities[node.Key], R7Fixed.ZeroHash)) throw new R7ProtocolException("RAW_EVIDENCE_MISSING");
                if (node.Value == "HOST_ARTIFACT" && R7Hash.FixedTimeEquals(provenanceIdentities[node.Key], R7Fixed.ZeroHash)) throw new R7ProtocolException("PROVENANCE_MISSING");
            }
            return R7PipeWindowsService.Success("TRACE_VERIFIED");
        }

        private static bool TraceHasCycle(Dictionary<string, List<string>> edges)
        {
            HashSet<string> visiting = new HashSet<string>(StringComparer.Ordinal);
            HashSet<string> complete = new HashSet<string>(StringComparer.Ordinal);
            foreach (string node in edges.Keys) if (TraceCycleVisit(node, edges, visiting, complete)) return true;
            return false;
        }

        private static bool TraceCycleVisit(string node, Dictionary<string, List<string>> edges, HashSet<string> visiting, HashSet<string> complete)
        {
            if (complete.Contains(node)) return false;
            if (!visiting.Add(node)) return true;
            foreach (string next in edges[node]) if (TraceCycleVisit(next, edges, visiting, complete)) return true;
            visiting.Remove(node);
            complete.Add(node);
            return false;
        }

        private static bool TraceReachesKind(string start, string desiredKind, Dictionary<string, string> kinds, Dictionary<string, List<string>> edges)
        {
            Queue<string> pending = new Queue<string>();
            HashSet<string> seen = new HashSet<string>(StringComparer.Ordinal);
            pending.Enqueue(start);
            while (pending.Count != 0)
            {
                string current = pending.Dequeue();
                if (!seen.Add(current)) continue;
                if (current != start && kinds[current] == desiredKind) return true;
                foreach (string next in edges[current]) pending.Enqueue(next);
            }
            return false;
        }

        private SortedDictionary<string, object> ClaimProbe(SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "case_id", "claim", "mutation");
            R7CaseDefinition definition = authority.Case(R7Json.String(payload, "case_id", 1, 128));
            string mutation = R7Json.String(payload, "mutation", 1, 256);
            if (definition.Driver != "CLAIM_VERIFIER" || definition.Mutation != mutation) throw new R7ProtocolException("CLAIM_CASE_AUTHORITY_MISMATCH");
            string claim = R7Json.String(payload, "claim", 1, 4096).Normalize(NormalizationForm.FormC).ToLowerInvariant();
            if (claim.Contains("canonically incorporated") || claim.Contains("canonical incorporation") || claim.Contains("incorporated into governing authority")) throw new R7ProtocolException("PROPOSAL_CANONICALITY_VIOLATION");
            if (claim.Contains("greenlit") || claim.Contains("approved") || claim.Contains("accepted") || claim.Contains("production ready")) throw new R7ProtocolException("PROTECTED_APPROVAL_CLAIM");
            return R7PipeWindowsService.Success("DOCUMENT_CLAIM_ALLOWED");
        }

        private SortedDictionary<string, object> ExternalEvidence(SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "case_id", "external_interface", "external_request_frame", "external_response_frame", "upgrade_request_identity");
            R7CaseDefinition definition = authority.Case(R7Json.String(payload, "case_id", 1, 128));
            byte[] request = Convert.FromBase64String(R7Json.String(payload, "external_request_frame", 1, R7Fixed.MaximumEncodedFrameChars));
            byte[] response = Convert.FromBase64String(R7Json.String(payload, "external_response_frame", 1, R7Fixed.MaximumEncodedFrameChars));
            SortedDictionary<string, object> externalRequest = R7Framing.Decode(request);
            SortedDictionary<string, object> externalResponse = R7Framing.Decode(response);
            string externalInterface = R7Json.String(payload, "external_interface", 1, 128);
            if (externalInterface == "UPGRADE_PIPE")
            {
                string upgradeRequestIdentity = R7Json.String(payload, "upgrade_request_identity", 36, 36);
                if (!String.Equals(R7Json.String(externalRequest, "request_identity", 36, 36), upgradeRequestIdentity, StringComparison.Ordinal)) throw new R7ProtocolException("EXTERNAL_REQUEST_IDENTITY_MISMATCH");
                byte[] lookupRequest;
                byte[] lookupResponse;
                SortedDictionary<string, object> resolved = R7Framing.Call(R7Fixed.UpgradePipe, R7Json.Object("interface_version", "1.0.0", "operation", "GET_UPGRADE_INTERACTION", "payload", R7Json.Object("request_identity", upgradeRequestIdentity), "protocol_version", R7Fixed.ProtocolVersion, "request_identity", Guid.NewGuid().ToString("D")), 10000, out lookupRequest, out lookupResponse);
                if (!String.Equals(R7Json.String(resolved, "status", 1, 64), "COMPLETE", StringComparison.Ordinal) || !String.Equals(R7Json.String(resolved, "result_code", 1, 256), "UPGRADE_INTERACTION_RESOLVED", StringComparison.Ordinal)) throw new R7ProtocolException("UPGRADE_INTERACTION_UNRESOLVED");
                SortedDictionary<string, object> interaction = R7Json.Child(resolved, "interaction");
                byte[] serverRequest = Convert.FromBase64String(R7Json.String(interaction, "request_frame", 1, R7Fixed.MaximumEncodedFrameChars));
                byte[] serverResponse = Convert.FromBase64String(R7Json.String(interaction, "response_frame", 1, R7Fixed.MaximumEncodedFrameChars));
                if (!R7Hash.FixedTimeEquals(R7Hash.Bytes(request), R7Hash.Bytes(serverRequest)) || !R7Hash.FixedTimeEquals(R7Hash.Bytes(response), R7Hash.Bytes(serverResponse)) ||
                    !R7Hash.FixedTimeEquals(R7Hash.Bytes(request), R7Json.String(interaction, "request_frame_sha256", 64, 64)) ||
                    !R7Hash.FixedTimeEquals(R7Hash.Bytes(response), R7Json.String(interaction, "response_frame_sha256", 64, 64))) throw new R7ProtocolException("UPGRADE_SERVER_CAPTURE_MISMATCH");
                if (R7Json.Integer(interaction, "authority_ledger_sequence_after_dispatch", 0, Int64.MaxValue) != R7Json.Integer(interaction, "authority_ledger_sequence_before", 0, Int64.MaxValue) ||
                    !String.Equals(R7Json.String(interaction, "authority_ledger_root_after_dispatch", 64, 64), R7Json.String(interaction, "authority_ledger_root_before", 64, 64), StringComparison.Ordinal)) throw new R7ProtocolException("EXTERNAL_LEDGER_EFFECT_UNEXPECTED");
                SortedDictionary<string, object> caller = R7Json.Child(interaction, "caller");
                string expectedCallerSid = definition.CallerRole == "SIGNER" ? R7Fixed.TerminalSid : definition.CallerRole == "OPERATOR" ? R7Fixed.OperatorSid : definition.CallerRole == "EXECUTION" ? R7Fixed.ExecutionSid : String.Empty;
                if (String.IsNullOrEmpty(expectedCallerSid) || !String.Equals(R7Json.String(caller, "user_sid", 1, 256), expectedCallerSid, StringComparison.Ordinal)) throw new R7ProtocolException("UPGRADE_CALLER_IDENTITY_MISMATCH");
                if (definition.CallerRole == "SIGNER" && !R7Json.Boolean(caller, "contains_terminal_signer_sid")) throw new R7ProtocolException("UPGRADE_SIGNER_TOKEN_NOT_OBSERVED");
                if (definition.CallerRole != "SIGNER" && R7Json.Boolean(caller, "contains_terminal_signer_sid")) throw new R7ProtocolException("UPGRADE_CALLER_RETAINED_SIGNER_SID");
                string expectedCallerBinary = definition.CallerRole == "SIGNER" ? policy.Component("TERMINAL_SIGNER").Sha256 : definition.CallerRole == "OPERATOR" ? R7Json.String(R7Json.Child(activeUpgrade.AuthorizationPayload, "installer_identity"), "executable_sha256", 64, 64) : policy.Component("EXECUTION").Sha256;
                if (!R7Hash.FixedTimeEquals(R7Json.String(caller, "process_sha256", 64, 64), expectedCallerBinary)) throw new R7ProtocolException("UPGRADE_CALLER_BINARY_MISMATCH");
            }
            else throw new R7ProtocolException("EXTERNAL_INTERFACE_NOT_GOVERNED");
            string externalStatus = R7Json.String(externalResponse, "status", 1, 64);
            SortedDictionary<string, object> result = externalStatus == "COMPLETE"
                ? R7PipeWindowsService.Success(R7Json.String(externalResponse, "result_code", 1, 256))
                : R7PipeWindowsService.Rejection(R7Json.String(externalResponse, "error_code", 1, 256));
            result.Add("external_request_sha256", R7Hash.Bytes(request));
            result.Add("external_response_sha256", R7Hash.Bytes(response));
            result.Add("upgrade_request_identity", R7Json.String(payload, "upgrade_request_identity", 36, 36));
            result.Add("upgrade_server_capture_resolved", true);
            result.Add("external_semantics_rederived", true);
            return result;
        }

        private SortedDictionary<string, object> SelfUpgradeProbe(SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "case_id");
            string caseId = R7Json.String(payload, "case_id", 1, 128);
            if (!String.Equals(caseId, "UPG-001", StringComparison.Ordinal)) throw new R7ProtocolException("SELF_UPGRADE_PROBE_CASE_INVALID");
            authority.Case(caseId);
            string requestIdentity = Guid.NewGuid().ToString("D");
            SortedDictionary<string, object> request = R7Json.Object(
                "interface_version", "1.0.0",
                "operation", "AUTHORIZE_TERMINAL_UPGRADE",
                "payload", R7Json.Object(),
                "protocol_version", R7Fixed.ProtocolVersion,
                "request_identity", requestIdentity);
            byte[] sent;
            byte[] received;
            SortedDictionary<string, object> response = R7Framing.Call(R7Fixed.UpgradePipe, request, 30000, out sent, out received);
            if (!String.Equals(R7Json.String(response, "status", 1, 64), "REJECTED", StringComparison.Ordinal) || !String.Equals(R7Json.String(response, "error_code", 1, 256), "UPGRADE_CALLER_NOT_AUTHORIZED", StringComparison.Ordinal)) throw new R7ProtocolException("SELF_UPGRADE_AUTHORIZATION_NOT_REJECTED");
            SortedDictionary<string, object> result = R7PipeWindowsService.Success("SELF_UPGRADE_PROBE_CAPTURED");
            result.Add("external_request_frame", Convert.ToBase64String(sent));
            result.Add("external_response_frame", Convert.ToBase64String(received));
            result.Add("upgrade_request_identity", requestIdentity);
            return result;
        }

        private SortedDictionary<string, object> ServiceStopEvidence(SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "client_error_code", "observation_time", "request_frame", "request_frame_sha256", "service_name");
            if (!String.Equals(R7Json.String(payload, "service_name", 1, 128), R7Fixed.TerminalService, StringComparison.Ordinal)) throw new R7ProtocolException("SERVICE_CONTROL_IDENTITY_MISMATCH");
            byte[] requestFrame;
            try { requestFrame = Convert.FromBase64String(R7Json.String(payload, "request_frame", 1, R7Fixed.MaximumEncodedFrameChars)); }
            catch (FormatException) { throw new R7ProtocolException("REQUEST_FRAME_ENCODING_INVALID"); }
            string requestHash = R7Json.String(payload, "request_frame_sha256", 64, 64);
            if (!R7Hash.FixedTimeEquals(R7Hash.Bytes(requestFrame), requestHash)) throw new R7ProtocolException("RAW_FRAME_EVIDENCE_MISMATCH");
            SortedDictionary<string, object> request = R7Framing.Decode(requestFrame);
            if (!String.Equals(R7Json.String(request, "operation", 1, 128), "GET_HEALTH", StringComparison.Ordinal) || R7Json.Child(request, "payload").Count != 0) throw new R7ProtocolException("SERVICE_UNAVAILABLE_REQUEST_INVALID");
            DateTimeOffset observation;
            if (!DateTimeOffset.TryParseExact(R7Json.String(payload, "observation_time", 1, 128), "yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out observation)) throw new R7ProtocolException("SERVICE_OBSERVATION_TIME_INVALID");
            DateTimeOffset now = DateTimeOffset.UtcNow;
            if (observation > now || now - observation > TimeSpan.FromMinutes(15)) throw new R7ProtocolException("SERVICE_OBSERVATION_STALE");
            EventLogEntry stopped = null;
            EventLogEntry running = null;
            string serviceDisplayName;
            using (ServiceController controller = new ServiceController(R7Fixed.TerminalService)) serviceDisplayName = controller.DisplayName;
            using (EventLog system = new EventLog("System"))
            {
                for (int index = system.Entries.Count - 1; index >= 0 && index >= system.Entries.Count - 4096; index--)
                {
                    EventLogEntry entry = system.Entries[index];
                    if (entry.InstanceId != 7036 || !String.Equals(entry.Source, "Service Control Manager", StringComparison.OrdinalIgnoreCase)) continue;
                    string[] replacements = entry.ReplacementStrings;
                    if (replacements == null || replacements.Length < 2 || (replacements[0].IndexOf(R7Fixed.TerminalService, StringComparison.OrdinalIgnoreCase) < 0 && replacements[0].IndexOf(serviceDisplayName, StringComparison.OrdinalIgnoreCase) < 0)) continue;
                    DateTimeOffset time = new DateTimeOffset(entry.TimeGenerated.ToUniversalTime(), TimeSpan.Zero);
                    if (time <= observation && observation - time <= TimeSpan.FromMinutes(5) && replacements[1].IndexOf("stopped", StringComparison.OrdinalIgnoreCase) >= 0 && stopped == null) stopped = entry;
                    if (time >= observation && now - time <= TimeSpan.FromMinutes(15) && replacements[1].IndexOf("running", StringComparison.OrdinalIgnoreCase) >= 0 && running == null) running = entry;
                    if (stopped != null && running != null) break;
                }
            }
            if (stopped == null || running == null) throw new R7ProtocolException("SERVICE_CONTROL_EVENT_NOT_RESOLVED");
            string proof = objects.Put(R7Json.Object(
                "client_error_code", R7Json.String(payload, "client_error_code", 1, 32),
                "observation_time", observation.ToString("yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture),
                "request_frame_sha256", requestHash,
                "running_event_index", (long)running.Index,
                "running_event_time", running.TimeGenerated.ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture),
                "stopped_event_index", (long)stopped.Index,
                "stopped_event_time", stopped.TimeGenerated.ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture)));
            SortedDictionary<string, object> result = R7PipeWindowsService.Unavailable("SERVICE_UNAVAILABLE");
            result.Add("service_control_proof_identity", proof);
            return result;
        }

        private SortedDictionary<string, object> SubmitProposal(R7RequestContext context, string requestIdentity, SortedDictionary<string, object> request, SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "checkout_identity", "configuration", "proposal_identity");
            string checkout = Sha(payload, "checkout_identity");
            string proposal = Sha(payload, "proposal_identity");
            SortedDictionary<string, object> configuration = R7Json.Child(payload, "configuration");
            ValidateConfiguration(configuration);
            return transactions.Execute(requestIdentity, context.RequestFrameSha256, "SUBMIT_TERMINAL_PROPOSAL", delegate()
            {
                string evidenceIdentity = objects.Put(R7Json.Object("caller", context.Caller.ToJson(), "checkout_identity", checkout, "configuration", configuration, "proposal_identity", proposal, "request_frame_sha256", context.RequestFrameSha256));
                SortedDictionary<string, object> receipt = ReceiptPayload(
                    "TERMINAL_PROPOSAL_RECEIPT",
                    requestIdentity,
                    context.RequestFrameSha256,
                    evidenceIdentity,
                    "REQUEST_RECEIVED_NONAUTHORITY",
                    R7Json.Object("checkout_identity", checkout, "configuration", configuration, "proposal_identity", proposal));
                SortedDictionary<string, object> response = R7PipeWindowsService.Success("REQUEST_RECEIVED");
                response.Add("proposal_identity", proposal);
                response.Add("request_identity", requestIdentity);
                return new R7PreparedTransaction(receipt, response, evidenceIdentity, "REQUEST_RECEIVED_NONAUTHORITY");
            });
        }

        private SortedDictionary<string, object> SubmitGraph(R7RequestContext context, string requestIdentity, SortedDictionary<string, object> request, SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "case_graphs", "checkout_identity", "configuration", "provenance_identity", "run_kind");
            string runKind = R7Json.String(payload, "run_kind", 1, 64);
            if (runKind != "CANDIDATE" && runKind != "FRESH" && runKind != "BOOTSTRAP_CANDIDATE" && runKind != "BOOTSTRAP_FRESH" && runKind != "CASE_CANDIDATE" && runKind != "CASE_FRESH") throw new R7ProtocolException("RUN_KIND_INVALID");
            string checkout = Sha(payload, "checkout_identity");
            string provenance = Sha(payload, "provenance_identity");
            SortedDictionary<string, object> configuration = R7Json.Child(payload, "configuration");
            ValidateConfiguration(configuration);
            object[] graphRows = R7Json.Array(payload, "case_graphs");
            if (graphRows.Length < 1 || graphRows.Length > authority.CaseIds.Length) throw new R7ProtocolException("CASE_GRAPH_COUNT");
            return transactions.Execute(requestIdentity, context.RequestFrameSha256, "SUBMIT_RUN_GRAPH", delegate()
            {
                R7GraphEvaluation evaluation = EvaluateGraph(context, runKind, graphRows);
                bool complete = evaluation.CompleteForRun;
                if (!evaluation.Passed) throw new R7ProtocolException("GRAPH_SEMANTIC_MISMATCH");
                string classification;
                string code;
                if ((runKind == "FRESH" || runKind == "CASE_FRESH") && complete) { classification = "COMMITTED_AUTHORITATIVE_FRESH_RECEIPT"; code = "TERMINAL_RECEIPT_COMMITTED"; }
                else if ((runKind == "CANDIDATE" || runKind == "CASE_CANDIDATE") && complete) { classification = "VALID_NONAUTHORITATIVE_CANDIDATE_EVIDENCE"; code = "CANDIDATE_GRAPH_RECORDED"; }
                else { classification = "VALID_NONAUTHORITATIVE_BOOTSTRAP_EVIDENCE"; code = runKind.IndexOf("CANDIDATE", StringComparison.Ordinal) >= 0 ? "CANDIDATE_GRAPH_RECORDED" : "FRESH_BOOTSTRAP_RECORDED"; }
                SortedDictionary<string, object> receipt = ReceiptPayload(
                    "TERMINAL_RUN_RECEIPT",
                    requestIdentity,
                    context.RequestFrameSha256,
                    evaluation.EvidenceIdentity,
                    classification,
                    R7Json.Object(
                        "case_count", (long)evaluation.CaseCount,
                        "checkout_identity", checkout,
                        "complete_case_registry", complete && runKind != "CASE_CANDIDATE" && runKind != "CASE_FRESH",
                        "completion_scope", runKind == "CASE_CANDIDATE" || runKind == "CASE_FRESH" ? "NONRECURSIVE_CASE_SUBMISSION_PROBE" : complete ? "FULL_GOVERNED_CASE_REGISTRY" : "PARTIAL_BOOTSTRAP_GRAPH",
                        "configuration", configuration,
                        "provenance_identity", provenance,
                        "run_kind", runKind));
                SortedDictionary<string, object> response = R7PipeWindowsService.Success(code);
                response.Add("case_count", (long)evaluation.CaseCount);
                response.Add("complete_case_registry", complete && runKind != "CASE_CANDIDATE" && runKind != "CASE_FRESH");
                response.Add("evidence_identity", evaluation.EvidenceIdentity);
                response.Add("provenance_identity", provenance);
                response.Add("request_identity", requestIdentity);
                response.Add("run_kind", runKind);
                return new R7PreparedTransaction(receipt, response, evaluation.EvidenceIdentity, classification);
            });
        }

        private SortedDictionary<string, object> SubmitReconciliation(R7RequestContext context, string requestIdentity, SortedDictionary<string, object> request, SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "candidate_receipt_identity", "fresh_receipt_identity", "reconciliation_provenance_identity");
            string candidateIdentity = Sha(payload, "candidate_receipt_identity");
            string freshIdentity = Sha(payload, "fresh_receipt_identity");
            string provenance = Sha(payload, "reconciliation_provenance_identity");
            if (String.Equals(candidateIdentity, freshIdentity, StringComparison.Ordinal)) throw new R7ProtocolException("RECONCILIATION_PROVENANCE_NOT_DISJOINT");
            return transactions.Execute(requestIdentity, context.RequestFrameSha256, "SUBMIT_RECONCILIATION", delegate()
            {
                SortedDictionary<string, object> candidate = LoadCommittedReceipt(candidateIdentity);
                SortedDictionary<string, object> fresh = LoadCommittedReceipt(freshIdentity);
                if (!String.Equals(R7Json.String(candidate, "receipt_type", 1, 128), "TERMINAL_RUN_RECEIPT", StringComparison.Ordinal) || !String.Equals(R7Json.String(fresh, "receipt_type", 1, 128), "TERMINAL_RUN_RECEIPT", StringComparison.Ordinal)) throw new R7ProtocolException("INVALID_GRAPH_RECONCILIATION");
                SortedDictionary<string, object> candidateDetails = R7Json.Child(candidate, "details");
                SortedDictionary<string, object> freshDetails = R7Json.Child(fresh, "details");
                bool candidateComplete = R7Json.Boolean(candidateDetails, "complete_case_registry");
                bool freshComplete = R7Json.Boolean(freshDetails, "complete_case_registry");
                if (candidateComplete || freshComplete)
                {
                    if (!candidateComplete || !freshComplete) throw new R7ProtocolException("RECONCILIATION_COMPLETENESS_MISMATCH");
                    ValidateCommittedCurrentGraphObligation(candidateIdentity, candidate, "CANDIDATE", "POS-005", "VALID_NONAUTHORITATIVE_CANDIDATE_EVIDENCE");
                    ValidateCommittedCurrentGraphObligation(freshIdentity, fresh, "FRESH", "POS-006", "COMMITTED_AUTHORITATIVE_FRESH_RECEIPT");
                }
                string candidateProvenance = Sha(candidateDetails, "provenance_identity");
                string freshProvenance = Sha(freshDetails, "provenance_identity");
                if (String.Equals(candidateProvenance, freshProvenance, StringComparison.Ordinal)) throw new R7ProtocolException("RECONCILIATION_PROVENANCE_NOT_DISJOINT");
                string candidateEvidence = Sha(candidate, "evidence_identity");
                string freshEvidence = Sha(fresh, "evidence_identity");
                R7ReconciliationEvaluation comparison = CompareGraphEvidence(candidateEvidence, freshEvidence);
                if (!comparison.Matched) throw new R7ProtocolException("RECONCILIATION_MISMATCH");
                string evidenceIdentity = objects.Put(R7Json.Object(
                    "candidate_evidence_identity", candidateEvidence,
                    "candidate_receipt_identity", candidateIdentity,
                    "compared_case_count", (long)comparison.ComparedCaseCount,
                    "fresh_evidence_identity", freshEvidence,
                    "fresh_receipt_identity", freshIdentity,
                    "matched", true,
                    "provenance_identity", provenance));
                bool full = comparison.ComplementaryMetaCasesVerified && comparison.ComparedCaseCount == authority.CaseIds.Length - 2 && candidateComplete && freshComplete;
                string classification = full ? "COMMITTED_RECONCILIATION" : "VALID_NONAUTHORITATIVE_BOOTSTRAP_RECONCILIATION";
                SortedDictionary<string, object> receipt = ReceiptPayload(
                    "RECONCILIATION_RECEIPT",
                    requestIdentity,
                    context.RequestFrameSha256,
                    evidenceIdentity,
                    classification,
                    R7Json.Object(
                        "candidate_receipt_identity", candidateIdentity,
                        "compared_case_count", (long)comparison.ComparedCaseCount,
                        "fresh_receipt_identity", freshIdentity,
                        "full_case_registry", full,
                        "provenance_identity", provenance));
                SortedDictionary<string, object> response = R7PipeWindowsService.Success("RECONCILIATION_COMMITTED");
                response.Add("candidate_receipt_identity", candidateIdentity);
                response.Add("fresh_receipt_identity", freshIdentity);
                response.Add("full_case_registry", full);
                response.Add("request_identity", requestIdentity);
                return new R7PreparedTransaction(receipt, response, evidenceIdentity, classification);
            });
        }

        private SortedDictionary<string, object> Retry(SortedDictionary<string, object> payload)
        {
            R7Json.ExactKeys(payload, "original_request_identity");
            return transactions.Reconstruct(CanonicalGuid(R7Json.String(payload, "original_request_identity", 36, 36)));
        }

        private R7GraphEvaluation EvaluateGraph(R7RequestContext context, string runKind, object[] rows)
        {
            HashSet<string> seen = new HashSet<string>(StringComparer.Ordinal);
            List<object> resultLocators = new List<object>();
            bool passed = true;
            foreach (object rawRow in rows)
            {
                SortedDictionary<string, object> row = RequireObject(rawRow);
                R7Json.ExactKeys(row, "base_interaction_identity", "case_id", "comparator_interaction_identity", "event_interaction_identity", "observation_interaction_identity");
                string caseId = R7Json.String(row, "case_id", 1, 128);
                if (!seen.Add(caseId)) throw new R7ProtocolException("DUPLICATE_CASE_GRAPH");
                R7CaseDefinition definition = authority.Case(caseId);
                R7Expectation expectation = authority.Expectation(caseId);
                string baseIdentity = R7Json.String(row, "base_interaction_identity", 64, 64);
                if (!R7Hash.IsLowerSha256(baseIdentity)) throw new R7ProtocolException("CASE_GRAPH_BASE_CAPTURE_IDENTITY_INVALID");
                SortedDictionary<string, object> caseResult = EvaluateCapturedCase(definition, expectation, row);
                bool casePassed = R7Json.Boolean(caseResult, "passed");
                passed = passed && casePassed;
                string resultIdentity = objects.Put(caseResult);
                resultLocators.Add(R7Json.Object("case_id", caseId, "result_identity", resultIdentity));
            }
            string evidenceIdentity = objects.Put(R7Json.Object(
                "artifact_type", "R7_SIGNER_REDERIVED_SUITE_EVIDENCE",
                "case_count", (long)seen.Count,
                "case_results", resultLocators.ToArray(),
                "complete_for_run", CompleteForRun(runKind, seen),
                "passed", passed,
                "run_kind", runKind,
                "schema_version", "1.0.0"));
            return new R7GraphEvaluation { CaseCount = seen.Count, CompleteForRun = CompleteForRun(runKind, seen), EvidenceIdentity = evidenceIdentity, Passed = passed };
        }

        private SortedDictionary<string, object> EvaluateCapturedCase(R7CaseDefinition definition, R7Expectation expectation, SortedDictionary<string, object> row)
        {
            R7InteractionEvidence baseEvidence = evidence.Resolve(R7Json.String(row, "base_interaction_identity", 64, 64));
            R7InteractionEvidence eventEvidence = evidence.Resolve(R7Json.String(row, "event_interaction_identity", 64, 64));
            R7InteractionEvidence observationEvidence = evidence.Resolve(R7Json.String(row, "observation_interaction_identity", 64, 64));
            R7InteractionEvidence comparatorEvidence = evidence.Resolve(R7Json.String(row, "comparator_interaction_identity", 64, 64));
            string baseRole = BaseEvidenceRole(definition);
            string baseSid = baseRole == "OBSERVATION" ? R7Fixed.ObservationSid : baseRole == "COMPARATOR" ? R7Fixed.ComparatorSid : baseRole == "EXECUTION" ? R7Fixed.ExecutionSid : R7Fixed.OperatorSid;
            RequireCaptureCaller(baseEvidence.Capture, baseSid, baseRole, "base");
            RequireCaptureCaller(eventEvidence.Capture, R7Fixed.ExecutionSid, "EXECUTION", "event");
            RequireCaptureCaller(observationEvidence.Capture, R7Fixed.ObservationSid, "OBSERVATION", "observation");
            RequireCaptureCaller(comparatorEvidence.Capture, R7Fixed.ComparatorSid, "COMPARATOR", "comparator");
            if (definition.Driver == "RAW_FRAME") return EvaluateParserCase(definition, expectation, baseEvidence, eventEvidence, observationEvidence, comparatorEvidence, baseRole);
            SortedDictionary<string, object> baseRequest = CaptureRequest(baseEvidence.Capture);
            SortedDictionary<string, object> eventRequest = CaptureRequest(eventEvidence.Capture);
            SortedDictionary<string, object> observationRequest = CaptureRequest(observationEvidence.Capture);
            SortedDictionary<string, object> comparatorRequest = CaptureRequest(comparatorEvidence.Capture);
            string baseIdentity = baseEvidence.InteractionIdentity;
            SortedDictionary<string, object> eventEnvelope = R7Json.Child(eventRequest, "payload");
            SortedDictionary<string, object> observationEnvelope = R7Json.Child(observationRequest, "payload");
            SortedDictionary<string, object> comparatorEnvelope = R7Json.Child(comparatorRequest, "payload");
            R7Json.ExactKeys(eventEnvelope, "evidence", "evidence_kind");
            R7Json.ExactKeys(observationEnvelope, "evidence", "evidence_kind");
            R7Json.ExactKeys(comparatorEnvelope, "evidence", "evidence_kind");
            if (R7Json.String(eventEnvelope, "evidence_kind", 1, 64) != "EVENT" || R7Json.String(observationEnvelope, "evidence_kind", 1, 64) != "OBSERVATION" || R7Json.String(comparatorEnvelope, "evidence_kind", 1, 64) != "COMPARISON") throw new R7ProtocolException("EVIDENCE_STAGE_KIND_MISMATCH");
            SortedDictionary<string, object> eventPayload = R7Json.Child(eventEnvelope, "evidence");
            SortedDictionary<string, object> observationPayload = R7Json.Child(observationEnvelope, "evidence");
            SortedDictionary<string, object> comparatorPayload = R7Json.Child(comparatorEnvelope, "evidence");
            if (!String.Equals(R7Json.String(eventRequest, "operation", 1, 128), "SUBMIT_EXECUTION_EVIDENCE", StringComparison.Ordinal) ||
                !String.Equals(R7Json.String(observationRequest, "operation", 1, 128), "SUBMIT_OBSERVATION_EVIDENCE", StringComparison.Ordinal) ||
                !String.Equals(R7Json.String(comparatorRequest, "operation", 1, 128), "SUBMIT_COMPARATOR_EVIDENCE", StringComparison.Ordinal)) throw new R7ProtocolException("EVIDENCE_STAGE_OPERATION_MISMATCH");
            if (!String.Equals(R7Json.String(eventPayload, "base_interaction_identity", 64, 64), baseIdentity, StringComparison.Ordinal) ||
                !String.Equals(R7Json.String(observationPayload, "base_interaction_identity", 64, 64), baseIdentity, StringComparison.Ordinal) ||
                !String.Equals(R7Json.String(comparatorPayload, "base_interaction_identity", 64, 64), baseIdentity, StringComparison.Ordinal)) throw new R7ProtocolException("EVIDENCE_GRAPH_REFERENCE_MISMATCH");
            if (!String.Equals(R7Json.String(comparatorPayload, "event_interaction_identity", 64, 64), eventEvidence.InteractionIdentity, StringComparison.Ordinal) ||
                !String.Equals(R7Json.String(comparatorPayload, "observation_interaction_identity", 64, 64), observationEvidence.InteractionIdentity, StringComparison.Ordinal)) throw new R7ProtocolException("COMPARATOR_GRAPH_REFERENCE_MISMATCH");
            SortedDictionary<string, object> comparison = R7Json.Child(comparatorPayload, "comparison");
            bool comparatorComplete = R7Json.Boolean(comparison, "raw_graph_complete");
            string comparatorCode = R7Json.String(comparison, "comparison_code", 1, 128);
            SortedDictionary<string, object> actualResponse = R7Json.Child(baseEvidence.Capture, "response_message");
            if (definition.Driver == "UPGRADE_PIPE" || definition.Driver == "UPGRADE_VERIFIER")
            {
                if (!String.Equals(R7Json.String(baseRequest, "operation", 1, 128), "SUBMIT_EXTERNAL_INTERACTION", StringComparison.Ordinal)) throw new R7ProtocolException("UPGRADE_OUTER_INTERFACE_SUBSTITUTED");
                SortedDictionary<string, object> rederivedUpgradeResponse = ExternalEvidence(R7Json.Child(baseRequest, "payload"));
                if (!R7Hash.FixedTimeEquals(R7Hash.Bytes(R7Json.Encode(rederivedUpgradeResponse)), R7Hash.Bytes(R7Json.Encode(actualResponse)))) throw new R7ProtocolException("UPGRADE_SEMANTICS_CHANGED_SINCE_CAPTURE");
            }
            string status = R7Json.String(actualResponse, "status", 1, 64);
            string code = status == "COMPLETE" ? R7Json.String(actualResponse, "result_code", 1, 256) : R7Json.String(actualResponse, "error_code", 1, 256);
            SortedDictionary<string, object> eventValue = R7Json.Child(eventPayload, "event");
            SortedDictionary<string, object> observationValue = R7Json.Child(observationPayload, "observation");
            string baseRequestFrameHash = R7Json.String(baseEvidence.Capture, "request_frame_sha256", 64, 64);
            string baseResponseFrameHash = R7Json.String(baseEvidence.Capture, "response_frame_sha256", 64, 64);
            string baseOperation = R7Json.String(baseRequest, "operation", 1, 128);
            if (!String.Equals(R7Json.String(eventValue, "operation", 1, 128), baseOperation, StringComparison.Ordinal) ||
                !R7Hash.FixedTimeEquals(R7Json.String(eventValue, "request_frame_sha256", 64, 64), baseRequestFrameHash) ||
                !R7Hash.FixedTimeEquals(R7Json.String(eventValue, "response_frame_sha256", 64, 64), baseResponseFrameHash)) throw new R7ProtocolException("EVENT_RAW_EVIDENCE_MISMATCH");
            byte[] eventRawRequest = Convert.FromBase64String(R7Json.String(eventPayload, "raw_request_frame", 1, R7Fixed.MaximumEncodedCaptureChars));
            byte[] eventRawResponse = Convert.FromBase64String(R7Json.String(eventPayload, "raw_response_frame", 1, R7Fixed.MaximumEncodedFrameChars));
            if (!R7Hash.FixedTimeEquals(R7Hash.Bytes(eventRawRequest), baseRequestFrameHash) || !R7Hash.FixedTimeEquals(R7Hash.Bytes(eventRawResponse), baseResponseFrameHash)) throw new R7ProtocolException("EVENT_RAW_FRAME_MISMATCH");
            long ledgerBefore = R7Json.Integer(baseEvidence.Capture, "ledger_sequence_before", 0, Int64.MaxValue);
            long ledgerAfter = R7Json.Integer(baseEvidence.Capture, "ledger_sequence_after", 0, Int64.MaxValue);
            if (!String.Equals(R7Json.String(observationValue, "actual_status", 1, 64), status, StringComparison.Ordinal) ||
                !String.Equals(R7Json.String(observationValue, "actual_code", 1, 256), code, StringComparison.Ordinal) ||
                R7Json.Integer(observationValue, "ledger_sequence_before", 0, Int64.MaxValue) != ledgerBefore ||
                R7Json.Integer(observationValue, "ledger_sequence_after", 0, Int64.MaxValue) != ledgerAfter) throw new R7ProtocolException("OBSERVATION_RAW_EVIDENCE_MISMATCH");
            byte[] observationRawRequest = Convert.FromBase64String(R7Json.String(observationPayload, "raw_request_frame", 1, R7Fixed.MaximumEncodedCaptureChars));
            byte[] observationRawResponse = Convert.FromBase64String(R7Json.String(observationPayload, "raw_response_frame", 1, R7Fixed.MaximumEncodedFrameChars));
            byte[] comparatorRawResponse = Convert.FromBase64String(R7Json.String(comparatorPayload, "raw_response_frame", 1, R7Fixed.MaximumEncodedFrameChars));
            if (!R7Hash.FixedTimeEquals(R7Hash.Bytes(observationRawRequest), baseRequestFrameHash) || !R7Hash.FixedTimeEquals(R7Hash.Bytes(observationRawResponse), baseResponseFrameHash) || !R7Hash.FixedTimeEquals(R7Hash.Bytes(comparatorRawResponse), baseResponseFrameHash)) throw new R7ProtocolException("STAGE_RAW_FRAME_MISMATCH");
            string derivedSideEffectIdentity = R7Hash.Bytes(R7Json.Encode(R7Json.Object(
                "ledger_sequence_after", ledgerAfter,
                "ledger_sequence_before", ledgerBefore,
                "request_frame_sha256", baseRequestFrameHash,
                "response_frame_sha256", baseResponseFrameHash)));
            if (!R7Hash.FixedTimeEquals(R7Json.String(observationValue, "side_effect_identity", 64, 64), derivedSideEffectIdentity)) throw new R7ProtocolException("RAW_SIDE_EFFECT_EVIDENCE_MISMATCH");
            if (!String.Equals(R7Json.String(comparatorPayload, "actual_status", 1, 64), status, StringComparison.Ordinal) ||
                !String.Equals(R7Json.String(comparatorPayload, "actual_code", 1, 256), code, StringComparison.Ordinal) ||
                !String.Equals(R7Json.String(comparatorPayload, "case_id", 1, 128), definition.CaseId, StringComparison.Ordinal)) throw new R7ProtocolException("COMPARATOR_INPUT_MISMATCH");
            string derivedClassification = DeriveCaseClassification(definition, baseRequest, actualResponse, status, code);
            bool semanticMatch = ExpectedMatch(expectation, status, code) && derivedClassification == expectation.Classification;
            byte[] rawRequest = Convert.FromBase64String(R7Json.String(baseEvidence.Capture, "request_frame", 1, R7Fixed.MaximumEncodedCaptureChars));
            byte[] rawResponse = Convert.FromBase64String(R7Json.String(baseEvidence.Capture, "response_frame", 1, R7Fixed.MaximumEncodedFrameChars));
            bool rawComplete = rawRequest.Length > 0 && rawResponse.Length > 0 && R7Hash.FixedTimeEquals(R7Hash.Bytes(rawRequest), baseRequestFrameHash) && R7Hash.FixedTimeEquals(R7Hash.Bytes(rawResponse), baseResponseFrameHash);
            string obligationProof = VerifyExpectationObligations(definition, expectation, baseEvidence.Capture, actualResponse, status, code, rawComplete, baseRequest);
            bool signerPass = semanticMatch && rawComplete && comparatorComplete && String.Equals(comparatorCode, semanticMatch ? "MATCH" : "MISMATCH", StringComparison.Ordinal);
            return R7Json.Object(
                "actual_code", code,
                "actual_status", status,
                "base_capture_identity", baseEvidence.CaptureIdentity,
                "base_interaction_identity", baseIdentity,
                "case_id", definition.CaseId,
                "comparator_capture_identity", comparatorEvidence.CaptureIdentity,
                "event_capture_identity", eventEvidence.CaptureIdentity,
                "effective_base_caller_role", baseRole,
                "expectation_definition_sha256", R7Hash.Bytes(R7Json.Encode(expectation.Raw)),
                "expected_code", expectation.ResultCode,
                "expected_terminal_classification", expectation.Classification,
                "expected_response_class", expectation.ResponseClass,
                "observation_capture_identity", observationEvidence.CaptureIdentity,
                "obligation_proof_identity", obligationProof,
                "obligations_verified", true,
                "passed", signerPass,
                "raw_evidence_complete", rawComplete,
                "signer_derived_terminal_classification", derivedClassification,
                "signer_rederived", true);
        }

        private SortedDictionary<string, object> EvaluateParserCase(R7CaseDefinition definition, R7Expectation expectation, R7InteractionEvidence baseEvidence, R7InteractionEvidence eventEvidence, R7InteractionEvidence observationEvidence, R7InteractionEvidence comparatorEvidence, string baseRole)
        {
            SortedDictionary<string, object> eventRequest = CaptureRequest(eventEvidence.Capture);
            SortedDictionary<string, object> observationRequest = CaptureRequest(observationEvidence.Capture);
            SortedDictionary<string, object> comparatorRequest = CaptureRequest(comparatorEvidence.Capture);
            string baseIdentity = baseEvidence.InteractionIdentity;
            SortedDictionary<string, object> eventEnvelope = R7Json.Child(eventRequest, "payload");
            SortedDictionary<string, object> observationEnvelope = R7Json.Child(observationRequest, "payload");
            SortedDictionary<string, object> comparatorEnvelope = R7Json.Child(comparatorRequest, "payload");
            R7Json.ExactKeys(eventEnvelope, "evidence", "evidence_kind");
            R7Json.ExactKeys(observationEnvelope, "evidence", "evidence_kind");
            R7Json.ExactKeys(comparatorEnvelope, "evidence", "evidence_kind");
            if (R7Json.String(eventEnvelope, "evidence_kind", 1, 64) != "EVENT" || R7Json.String(observationEnvelope, "evidence_kind", 1, 64) != "OBSERVATION" || R7Json.String(comparatorEnvelope, "evidence_kind", 1, 64) != "COMPARISON") throw new R7ProtocolException("EVIDENCE_STAGE_KIND_MISMATCH");
            SortedDictionary<string, object> eventPayload = R7Json.Child(eventEnvelope, "evidence");
            SortedDictionary<string, object> observationPayload = R7Json.Child(observationEnvelope, "evidence");
            SortedDictionary<string, object> comparatorPayload = R7Json.Child(comparatorEnvelope, "evidence");
            if (R7Json.String(eventRequest, "operation", 1, 128) != "SUBMIT_EXECUTION_EVIDENCE" || R7Json.String(observationRequest, "operation", 1, 128) != "SUBMIT_OBSERVATION_EVIDENCE" || R7Json.String(comparatorRequest, "operation", 1, 128) != "SUBMIT_COMPARATOR_EVIDENCE") throw new R7ProtocolException("EVIDENCE_STAGE_OPERATION_MISMATCH");
            if (R7Json.String(eventPayload, "base_interaction_identity", 64, 64) != baseIdentity || R7Json.String(observationPayload, "base_interaction_identity", 64, 64) != baseIdentity || R7Json.String(comparatorPayload, "base_interaction_identity", 64, 64) != baseIdentity) throw new R7ProtocolException("EVIDENCE_GRAPH_REFERENCE_MISMATCH");
            if (R7Json.String(comparatorPayload, "event_interaction_identity", 64, 64) != eventEvidence.InteractionIdentity || R7Json.String(comparatorPayload, "observation_interaction_identity", 64, 64) != observationEvidence.InteractionIdentity) throw new R7ProtocolException("COMPARATOR_GRAPH_REFERENCE_MISMATCH");
            SortedDictionary<string, object> actualResponse = R7Json.Child(baseEvidence.Capture, "response_message");
            string status = R7Json.String(actualResponse, "status", 1, 64);
            string code = status == "COMPLETE" ? R7Json.String(actualResponse, "result_code", 1, 256) : R7Json.String(actualResponse, "error_code", 1, 256);
            byte[] rawRequest = Convert.FromBase64String(R7Json.String(baseEvidence.Capture, "request_frame", 1, R7Fixed.MaximumEncodedCaptureChars));
            byte[] rawResponse = Convert.FromBase64String(R7Json.String(baseEvidence.Capture, "response_frame", 1, R7Fixed.MaximumEncodedFrameChars));
            string requestHash = R7Json.String(baseEvidence.Capture, "request_frame_sha256", 64, 64);
            string responseHash = R7Json.String(baseEvidence.Capture, "response_frame_sha256", 64, 64);
            if (!R7Hash.FixedTimeEquals(R7Hash.Bytes(rawRequest), requestHash) || !R7Hash.FixedTimeEquals(R7Hash.Bytes(rawResponse), responseHash)) throw new R7ProtocolException("RAW_FRAME_EVIDENCE_MISMATCH");
            string independentlyDerived = DeriveParserResult(rawRequest);
            if (!String.Equals(independentlyDerived, code, StringComparison.Ordinal)) throw new R7ProtocolException("PARSER_REDERIVATION_MISMATCH");
            long rejectionOffset = R7Json.Integer(baseEvidence.Capture, "protocol_error_offset", -1, Int64.MaxValue);
            if (status == "REJECTED" && rejectionOffset < 0) throw new R7ProtocolException("PARSER_REJECTION_OFFSET_MISSING");
            SortedDictionary<string, object> eventValue = R7Json.Child(eventPayload, "event");
            if (R7Json.String(eventValue, "operation", 1, 128) != definition.Operation || !R7Hash.FixedTimeEquals(R7Json.String(eventValue, "request_frame_sha256", 64, 64), requestHash) || !R7Hash.FixedTimeEquals(R7Json.String(eventValue, "response_frame_sha256", 64, 64), responseHash)) throw new R7ProtocolException("EVENT_RAW_EVIDENCE_MISMATCH");
            byte[] eventRawRequest = Convert.FromBase64String(R7Json.String(eventPayload, "raw_request_frame", 1, R7Fixed.MaximumEncodedCaptureChars));
            byte[] eventRawResponse = Convert.FromBase64String(R7Json.String(eventPayload, "raw_response_frame", 1, R7Fixed.MaximumEncodedFrameChars));
            if (!R7Hash.FixedTimeEquals(R7Hash.Bytes(eventRawRequest), requestHash) || !R7Hash.FixedTimeEquals(R7Hash.Bytes(eventRawResponse), responseHash)) throw new R7ProtocolException("EVENT_RAW_FRAME_MISMATCH");
            long ledgerBefore = R7Json.Integer(baseEvidence.Capture, "ledger_sequence_before", 0, Int64.MaxValue);
            long ledgerAfter = R7Json.Integer(baseEvidence.Capture, "ledger_sequence_after", 0, Int64.MaxValue);
            if (ledgerBefore != ledgerAfter) throw new R7ProtocolException("PARSER_REJECTION_AUTHORITY_EFFECT");
            SortedDictionary<string, object> observation = R7Json.Child(observationPayload, "observation");
            if (R7Json.String(observation, "actual_status", 1, 64) != status || R7Json.String(observation, "actual_code", 1, 256) != code || R7Json.Integer(observation, "ledger_sequence_before", 0, Int64.MaxValue) != ledgerBefore || R7Json.Integer(observation, "ledger_sequence_after", 0, Int64.MaxValue) != ledgerAfter) throw new R7ProtocolException("OBSERVATION_RAW_EVIDENCE_MISMATCH");
            byte[] observationRawRequest = Convert.FromBase64String(R7Json.String(observationPayload, "raw_request_frame", 1, R7Fixed.MaximumEncodedCaptureChars));
            byte[] observationRawResponse = Convert.FromBase64String(R7Json.String(observationPayload, "raw_response_frame", 1, R7Fixed.MaximumEncodedFrameChars));
            byte[] comparatorRawResponse = Convert.FromBase64String(R7Json.String(comparatorPayload, "raw_response_frame", 1, R7Fixed.MaximumEncodedFrameChars));
            if (!R7Hash.FixedTimeEquals(R7Hash.Bytes(observationRawRequest), requestHash) || !R7Hash.FixedTimeEquals(R7Hash.Bytes(observationRawResponse), responseHash) || !R7Hash.FixedTimeEquals(R7Hash.Bytes(comparatorRawResponse), responseHash)) throw new R7ProtocolException("STAGE_RAW_FRAME_MISMATCH");
            SortedDictionary<string, object> comparison = R7Json.Child(comparatorPayload, "comparison");
            string derivedClassification = status == "REJECTED" ? "REJECTED_NONAUTHORITY" : code == "FRAME_SIZE_ACCEPTED" ? "FRAME_ACCEPTED_NONAUTHORITY" : "PARSER_ACCEPTED_UNCLASSIFIED";
            bool semanticMatch = ExpectedMatch(expectation, status, code) && derivedClassification == expectation.Classification;
            bool comparatorMatch = R7Json.Boolean(comparison, "raw_graph_complete") && R7Json.String(comparison, "comparison_code", 1, 128) == (semanticMatch ? "MATCH" : "MISMATCH") && R7Json.String(comparatorPayload, "case_id", 1, 128) == definition.CaseId && R7Json.String(comparatorPayload, "actual_status", 1, 64) == status && R7Json.String(comparatorPayload, "actual_code", 1, 256) == code;
            string obligationProof = VerifyExpectationObligations(definition, expectation, baseEvidence.Capture, actualResponse, status, code, true, null);
            return R7Json.Object(
                "actual_code", code,
                "actual_status", status,
                "base_capture_identity", baseEvidence.CaptureIdentity,
                "base_interaction_identity", baseIdentity,
                "case_id", definition.CaseId,
                "comparator_capture_identity", comparatorEvidence.CaptureIdentity,
                "effective_base_caller_role", baseRole,
                "event_capture_identity", eventEvidence.CaptureIdentity,
                "expectation_definition_sha256", R7Hash.Bytes(R7Json.Encode(expectation.Raw)),
                "expected_code", expectation.ResultCode,
                "expected_terminal_classification", expectation.Classification,
                "expected_response_class", expectation.ResponseClass,
                "observation_capture_identity", observationEvidence.CaptureIdentity,
                "obligation_proof_identity", obligationProof,
                "obligations_verified", true,
                "parser_result_rederived", independentlyDerived,
                "parser_rejection_offset", rejectionOffset,
                "passed", semanticMatch && comparatorMatch,
                "raw_evidence_complete", true,
                "signer_derived_terminal_classification", derivedClassification,
                "signer_rederived", true);
        }

        private string DeriveCaseClassification(R7CaseDefinition definition, SortedDictionary<string, object> request, SortedDictionary<string, object> response, string status, string code)
        {
            if (status == "REJECTED") return "REJECTED_NONAUTHORITY";
            if (status == "UNAVAILABLE") return "SERVICE_UNAVAILABLE_NONAUTHORITY";
            string operation = R7Json.String(request, "operation", 1, 128);
            if (operation == "SUBMIT_TERMINAL_PROPOSAL" || operation == "SUBMIT_RUN_GRAPH" || operation == "SUBMIT_RECONCILIATION" || operation == "RETRY_REQUEST")
            {
                string receiptIdentity = R7Json.String(response, "receipt_identity", 64, 64);
                SortedDictionary<string, object> receipt = LoadCommittedReceipt(receiptIdentity);
                return R7Json.String(receipt, "terminal_classification", 1, 256);
            }
            if (operation == "SUBMIT_PUBLIC_VERIFICATION_EVIDENCE" && response.ContainsKey("classification")) return R7Json.String(response, "classification", 1, 256);
            if (operation == "VERIFY_TERMINAL_RECEIPT" || operation == "VERIFY_RECONCILIATION" || operation == "CLASSIFY_RECEIPT" || operation == "CLASSIFY_LEDGER_SEQUENCE") return R7Json.String(response, "classification", 1, 256);
            if (code == "ALL_ENTRIES_CLASSIFIED") return "VERIFY_ALL_COMPLETE";
            if (code == "NO_SIGNER_SEMANTIC_CHILD") return "ISOLATION_PROVED";
            if (code == "CONCURRENT_IDENTICAL_RETRY_RESOLVED" || code == "CONCURRENT_CONFLICT_REJECTED") return "CONCURRENCY_PROVED";
            if (code == "REMOVED_FROM_AUTHORITY_PATH") return "DEPENDENCY_ABSENT";
            if (code == "NO_RESERVATION") return "NO_STATE";
            if (code == "RESERVATION_ABORTED" || code == "VALIDATED_TRANSACTION_ABORTED" || code == "PREPARED_TRANSACTION_ABORTED" || code == "UNCOMMITTED_RECEIPT_QUARANTINED" || code == "RECONCILIATION_ABORTED" || code == "INCOMPLETE_RESERVATION_ABORTED") return "ABORTED";
            if (code == "RESPONSE_RECONSTRUCTED") return "COMMITTED_RESPONSE_RECONSTRUCTED";
            if (code == "DURABLE_WRITE_FAILED" || code == "ACCESS_DENIED" || code == "DIRECTORY_DURABILITY_FAILED") return "FAILED_CLOSED";
            if (code == "CHECKPOINT_ADVANCED_BY_REPLAY" || code == "PARTIAL_CHECKPOINT_QUARANTINED" || code == "CLASSIFICATION_TRANSITION_RECOVERED" || code == "RECOVERY_RESUMED" || code == "PARTIAL_WRITE_REJECTED") return "RECOVERED";
            if (code == "AUTHORITY_HEALTHY" || code == "PUBLIC_TRUST_RESOLVED" || code == "LEDGER_STATUS_RESOLVED" || code == "TERMINAL_RECEIPT_RESOLVED" || code == "LEDGER_ENTRY_RESOLVED" || code == "RECONCILIATION_RESOLVED" || code == "UPGRADE_AUTHORITY_STATUS_RESOLVED" || code == "VERSION_HISTORY_RESOLVED" || code == "RECOVERY_STATE_RESOLVED") return "READ_ONLY_SUCCESS";
            throw new R7ProtocolException("CASE_CLASSIFICATION_NOT_DERIVABLE", definition.CaseId);
        }

        private string VerifyExpectationObligations(R7CaseDefinition definition, R7Expectation expectation, SortedDictionary<string, object> capture, SortedDictionary<string, object> response, string status, string code, bool rawComplete, SortedDictionary<string, object> baseRequest)
        {
            long ledgerBefore = R7Json.Integer(capture, "ledger_sequence_before", 0, Int64.MaxValue);
            long ledgerAfter = R7Json.Integer(capture, "ledger_sequence_after", 0, Int64.MaxValue);
            bool ledgerUnchanged = ledgerBefore == ledgerAfter && R7Json.String(capture, "ledger_root_before", 64, 64) == R7Json.String(capture, "ledger_root_after", 64, 64);
            SortedDictionary<string, object> stateBefore = R7Json.Child(capture, "protected_state_before");
            SortedDictionary<string, object> stateAfter = R7Json.Child(capture, "protected_state_after");
            bool authorityFilesUnchanged = StateFieldEqual(stateBefore, stateAfter, "authority_identity") && StateFieldEqual(stateBefore, stateAfter, "configuration_identity");
            bool trustUnchanged = StateFieldEqual(stateBefore, stateAfter, "terminal_trust_identity") && StateFieldEqual(stateBefore, stateAfter, "upgrade_trust_identity");
            bool upgradeUnchanged = StateFieldEqual(stateBefore, stateAfter, "upgrade_authorization_identity");
            bool receiptsUnchanged = StateFieldEqual(stateBefore, stateAfter, "receipt_identity");
            bool responsesUnchanged = StateFieldEqual(stateBefore, stateAfter, "response_identity");
            bool serverPrincipalProbe = false;
            bool serverPrincipalAccessDenied = false;
            bool serverPrincipalReportConflict = false;
            bool serverSignerProcessTreeIsolated = false;
            if (capture.ContainsKey("server_derived_evidence"))
            {
                SortedDictionary<string, object> serverProbe = R7Json.Child(capture, "server_derived_evidence");
                if (serverProbe.Count != 0)
                {
                    R7Json.ExactKeys(serverProbe, "attempt_performed", "attempted_operation", "caller_process_file_identity", "caller_process_id", "caller_token_id", "caller_user_sid", "child_reported_access_granted", "child_reported_error_code", "child_reported_target_sha256_after", "child_reported_target_sha256_before", "derivation", "denial_type", "descendant_process_evidence", "native_error", "requested_target_identity", "resolved_target", "server_access_granted", "signer_sid_present_in_captured_token");
                    SortedDictionary<string, object> capturedCaller = R7Json.Child(capture, "caller");
                    serverPrincipalProbe = R7Json.Boolean(serverProbe, "attempt_performed") &&
                        String.Equals(R7Json.String(serverProbe, "derivation", 1, 128), "SERVER_OS_PROBE_UNDER_PIPE_CLIENT_IMPERSONATION", StringComparison.Ordinal) &&
                        String.Equals(R7Json.String(serverProbe, "caller_process_file_identity", 1, 256), R7Json.String(capturedCaller, "process_file_identity", 1, 256), StringComparison.Ordinal) &&
                        R7Json.Integer(serverProbe, "caller_process_id", 0, Int64.MaxValue) == R7Json.Integer(capturedCaller, "process_id", 0, Int64.MaxValue) &&
                        String.Equals(R7Json.String(serverProbe, "caller_token_id", 1, 64), R7Json.String(capturedCaller, "token_id", 1, 64), StringComparison.Ordinal) &&
                        String.Equals(R7Json.String(serverProbe, "caller_user_sid", 1, 256), R7Json.String(capturedCaller, "user_sid", 1, 256), StringComparison.Ordinal) &&
                        R7Json.Boolean(serverProbe, "signer_sid_present_in_captured_token") == R7Json.Boolean(capturedCaller, "contains_terminal_signer_sid");
                    serverPrincipalAccessDenied = serverPrincipalProbe && !R7Json.Boolean(serverProbe, "server_access_granted");
                    serverPrincipalReportConflict = serverPrincipalProbe && R7Json.Boolean(serverProbe, "child_reported_access_granted") != R7Json.Boolean(serverProbe, "server_access_granted");
                    if (definition.Mutation == "SIGNER_PROCESS_CREATION")
                    {
                        SortedDictionary<string, object> processTree = R7Json.Child(serverProbe, "descendant_process_evidence");
                        R7Json.ExactKeys(processTree, "execution_service_parent_process_id", "signer_process_id");
                        serverSignerProcessTreeIsolated = serverPrincipalAccessDenied && !R7Json.Boolean(serverProbe, "signer_sid_present_in_captured_token") &&
                            R7Json.Integer(processTree, "signer_process_id", 1, Int64.MaxValue) == signerProcessId &&
                            R7Json.Integer(processTree, "execution_service_parent_process_id", 0, Int64.MaxValue) != signerProcessId &&
                            R7Json.String(serverProbe, "resolved_target", 1, 512).EndsWith("|DIRECT_CHILD_COUNT=0", StringComparison.Ordinal) &&
                            R7Json.String(serverProbe, "denial_type", 1, 128) == "NO_DIRECT_CHILD_PROCESSES";
                    }
                }
            }
            bool concurrencyProof = false;
            if (definition.Driver == "CONCURRENCY_PROBE" && response.ContainsKey("concurrency_evidence_identity"))
            {
                string concurrencyIdentity = R7Json.String(response, "concurrency_evidence_identity", 64, 64);
                SortedDictionary<string, object> concurrency = objects.Get(concurrencyIdentity);
                R7Json.ExactKeys(concurrency, "case_id", "first_capture_identity", "first_concurrent_connection_count", "first_request_frame_sha256", "first_response_frame_sha256", "mutation", "request_identity", "second_capture_identity", "second_concurrent_connection_count", "second_request_frame_sha256", "second_response_frame_sha256", "terminal_receipt_identity", "terminal_response_identity", "terminal_state");
                concurrencyProof = String.Equals(R7Json.String(concurrency, "case_id", 1, 128), definition.CaseId, StringComparison.Ordinal) &&
                    R7Json.Integer(concurrency, "first_concurrent_connection_count", 1, Int64.MaxValue) >= 1 &&
                    R7Json.Integer(concurrency, "second_concurrent_connection_count", 1, Int64.MaxValue) >= 1 &&
                    Math.Max(R7Json.Integer(concurrency, "first_concurrent_connection_count", 1, Int64.MaxValue), R7Json.Integer(concurrency, "second_concurrent_connection_count", 1, Int64.MaxValue)) >= 2 &&
                    !String.Equals(R7Json.String(concurrency, "first_capture_identity", 64, 64), R7Json.String(concurrency, "second_capture_identity", 64, 64), StringComparison.Ordinal) &&
                    String.Equals(R7Json.String(concurrency, "terminal_state", 1, 64), "RESPONSE_AVAILABLE", StringComparison.Ordinal) &&
                    R7Hash.IsLowerSha256(R7Json.String(concurrency, "terminal_receipt_identity", 64, 64)) &&
                    R7Hash.IsLowerSha256(R7Json.String(concurrency, "terminal_response_identity", 64, 64));
            }
            bool recoveryEvidence = false;
            if (definition.Driver == "RECOVERY_HARNESS" && response.ContainsKey("independent_recovery_rederivation"))
            {
                SortedDictionary<string, object> recovery = R7Json.Child(response, "independent_recovery_rederivation");
                R7Json.ExactKeys(recovery, "derived_result_code", "ledger_root", "ledger_sequence", "public_key_identity", "request_identity", "request_sha256", "result_identity", "service_sid", "status", "transaction_state");
                Guid recoveryRequestIdentity;
                recoveryEvidence =
                    String.Equals(R7Json.String(recovery, "derived_result_code", 1, 256), code, StringComparison.Ordinal) &&
                    String.Equals(R7Json.String(recovery, "service_sid", 1, 256), R7Fixed.ExecutionSid, StringComparison.Ordinal) &&
                    String.Equals(R7Json.String(recovery, "status", 1, 64), "PASS", StringComparison.Ordinal) &&
                    R7Json.Integer(recovery, "ledger_sequence", 1, Int64.MaxValue) >= 1 &&
                    R7Hash.IsLowerSha256(R7Json.String(recovery, "ledger_root", 64, 64)) &&
                    R7Hash.IsLowerSha256(R7Json.String(recovery, "public_key_identity", 64, 64)) &&
                    R7Hash.IsLowerSha256(R7Json.String(recovery, "request_sha256", 64, 64)) &&
                    R7Hash.IsLowerSha256(R7Json.String(recovery, "result_identity", 64, 64)) &&
                    Guid.TryParseExact(R7Json.String(recovery, "request_identity", 36, 36), "D", out recoveryRequestIdentity) &&
                    R7Json.String(recovery, "transaction_state", 1, 64).Length != 0;
            }
            bool parserRejection = R7Json.String(capture, "derivation", 1, 128) == "STRICT_PARSER_REJECTION_BEFORE_DISPATCH";
            bool committedTransaction = ledgerAfter > ledgerBefore && response.ContainsKey("request_identity");
            bool retryOriginalCommitted = false;
            bool retryResponseIdentical = false;
            bool retryRestartProven = false;
            if (definition.Operation == "RETRY_REQUEST" && baseRequest != null)
            {
                SortedDictionary<string, object> retryPayload = R7Json.Child(baseRequest, "payload");
                R7Json.ExactKeys(retryPayload, "original_request_identity");
                string originalRequestIdentity = CanonicalGuid(R7Json.String(retryPayload, "original_request_identity", 36, 36));
                R7TransactionSnapshot original = transactions.Find(originalRequestIdentity);
                retryOriginalCommitted = original != null && (original.State == "COMMITTED" || original.State == "RESPONSE_AVAILABLE") && R7Hash.IsLowerSha256(original.ReceiptIdentity) && R7Hash.IsLowerSha256(original.ResponseIdentity);
                if (retryOriginalCommitted)
                {
                    retryResponseIdentical = R7Hash.FixedTimeEquals(original.ResponseIdentity, R7Json.String(capture, "response_frame_sha256", 64, 64));
                    R7InteractionEvidence originalInteraction = evidence.ResolveLatestByRequestFrame(original.RequestSha256);
                    SortedDictionary<string, object> originalState = R7Json.Child(originalInteraction.Capture, "protected_state_after");
                    retryRestartProven = !String.Equals(R7Json.String(originalState, "signer_process_instance_identity", 64, 64), R7Json.String(stateBefore, "signer_process_instance_identity", 64, 64), StringComparison.Ordinal);
                }
            }
            List<object> evidenceProofs = new List<object>();
            foreach (string token in expectation.RequiredEvidence)
            {
                bool satisfied;
                string basis;
                if (token == "EXACT_REQUEST_FRAME" || token == "EXACT_RESPONSE_FRAME" || token == "EXACT_REJECTED_FRAME" || token == "RAW_FRAME_BYTES" || token == "RAW_REQUEST_RESPONSE" || token == "COMPLETE_FRAME") { satisfied = rawComplete; basis = "SERVER_CAPTURED_HASHED_FRAMES"; }
                else if (token == "CALLER_IDENTITY" || token == "SERVER_CAPTURED_CALLER" || token == "RAW_PROCESS_EVIDENCE") { satisfied = true; basis = "MEASURED_PIPE_CALLER_TOKEN_AND_PROCESS"; }
                else if (token == "CALLER_TOKEN" || token == "EFFECTIVE_TOKEN_GROUPS" || token == "EXECUTION_SERVICE_TOKEN" || token == "PARENT_TOKEN" || token == "DESCENDANT_TOKEN" || token == "SIGNER_SID_ABSENCE" || token == "SIGNER_PROCESS_TREE") { satisfied = serverPrincipalProbe; basis = "SIGNER_VALIDATED_PIPE_CALLER_TOKEN_AND_SERVER_OS_PROBE"; }
                else if (token == "INDEPENDENT_EVENT" || token == "INDEPENDENT_OBSERVATION" || token == "COMPARATOR_RESULT" || token == "SIGNER_REDERIVATION" || token == "RAW_SIDE_EFFECTS") { satisfied = true; basis = "SIGNER_RESOLVED_STAGE_CAPTURES"; }
                else if (token == "NO_AUTHORITY_EFFECT_PROOF" || token == "NO_SIDE_EFFECT_PROOF") { satisfied = ledgerUnchanged && receiptsUnchanged && responsesUnchanged && trustUnchanged && upgradeUnchanged && authorityFilesUnchanged; basis = "PROTECTED_STATE_BEFORE_AFTER_IDENTICAL"; }
                else if (token == "NO_DISPATCH_PROOF") { satisfied = parserRejection && ledgerUnchanged; basis = "PARSER_REJECTION_BEFORE_DISPATCH"; }
                else if (token == "PARSER_REJECTION_OFFSET") { satisfied = R7Json.Integer(capture, "protocol_error_offset", -1, Int64.MaxValue) >= 0; basis = "SERVER_PARSER_BYTE_OFFSET"; }
                else if (token == "STRICT_PARSE_RESULT") { satisfied = definition.Driver == "RAW_FRAME"; basis = "SIGNER_INDEPENDENT_FRAME_REDERIVATION"; }
                else if (token == "RAW_FRAME_SIZE_65536") { satisfied = Convert.FromBase64String(R7Json.String(capture, "request_frame", 1, R7Fixed.MaximumEncodedFrameChars)).Length == R7Fixed.MaximumFrameBytes; basis = "RAW_FRAME_LENGTH"; }
                else if (token == "ACCESS_DENIED_RESULT" || token == "OBJECT_ACL" || token == "KEY_AND_LEDGER_ACCESS_DENIAL") { satisfied = serverPrincipalAccessDenied; basis = "SIGNER_OS_PROBE_UNDER_PIPE_CLIENT_IMPERSONATION"; }
                else if (token == "SERVER_DERIVED_OS_PROBE") { satisfied = serverPrincipalProbe; basis = "SIGNER_OS_PROBE_UNDER_PIPE_CLIENT_IMPERSONATION"; }
                else if (token == "CHILD_REPORT_CONFLICT") { satisfied = serverPrincipalReportConflict; basis = "CHILD_REPORT_COMPARED_WITH_SERVER_DERIVED_OS_RESULT"; }
                else if (token == "UNCHANGED_OBJECT_HASH") { satisfied = serverPrincipalAccessDenied && authorityFilesUnchanged && trustUnchanged && upgradeUnchanged && receiptsUnchanged && responsesUnchanged && ledgerUnchanged; basis = "SIGNER_OS_PROBE_AND_PROTECTED_STATE_BEFORE_AFTER_IDENTICAL"; }
                else if (token == "OS_CONCURRENT_CONNECTIONS" || token == "TWO_SERVER_INTERACTIONS" || token == "ONE_TRANSACTION_STATE") { satisfied = concurrencyProof; basis = "SIGNER_RESOLVED_SERVER_INTERACTIONS_AND_TRANSACTION_STATE"; }
                else if (token == "BYTE_IDENTICAL_RESPONSE") { satisfied = concurrencyProof && code == "CONCURRENT_IDENTICAL_RETRY_RESOLVED"; basis = "SIGNER_COMPARED_BOTH_SERVER_RESPONSE_FRAME_HASHES"; }
                else if (token == "ONE_COMMIT_ONE_CONFLICT") { satisfied = concurrencyProof && code == "CONCURRENT_CONFLICT_REJECTED"; basis = "SIGNER_DERIVED_ONE_COMMIT_AND_ONE_IDENTITY_CONFLICT"; }
                else if (token == "ATTACK_PATH" || token == "REJECTION_REASON") { satisfied = (definition.Driver == "PATH_PROBE" && response.ContainsKey("path_probe_evidence_identity")) || definition.Driver == "RAW_FRAME"; basis = "NO_FOLLOW_HANDLE_OR_STRICT_PARSER_PROBE"; }
                else if (token == "HELD_HANDLE_IDENTITIES" || token == "HELD_HANDLE_IDENTITY")
                {
                    bool protectedHandlesResolved = stateBefore.ContainsKey("authority_identity") && stateBefore.ContainsKey("configuration_identity") && stateAfter.ContainsKey("authority_identity") && stateAfter.ContainsKey("configuration_identity");
                    satisfied = (definition.Driver == "PATH_PROBE" && response.ContainsKey("path_probe_evidence_identity")) || (rawComplete && protectedHandlesResolved);
                    basis = definition.Driver == "PATH_PROBE" ? "NO_FOLLOW_ATTACK_AND_REFERENCE_HANDLES" : "SIGNER_HELD_AUTHORITY_HANDLES_AND_PROTECTED_STATE_SNAPSHOTS";
                }
                else if (token == "NO_USE_PROOF") { satisfied = definition.Driver == "DEPENDENCY_PROBE" || definition.Driver == "PATH_PROBE"; basis = definition.Driver == "PATH_PROBE" ? "REJECTED_BEFORE_AUTHORITY_FILE_USE" : "CLOSED_DEPENDENCY_MANIFEST_AND_LIVE_MODULE_SET"; }
                else if (token == "DEPENDENCY_MANIFEST" || token == "EXPECTED_MANIFEST" || token == "PROCESS_MODULE_SET" || token == "RUNTIME_INVOCATION_SCAN" || token == "SOURCE_SCAN" || token == "LOADED_OR_BUILD_IDENTITY" || token == "MISMATCH_PROOF") { satisfied = definition.Driver == "DEPENDENCY_PROBE"; basis = "CLOSED_DEPENDENCY_MANIFEST_AND_LIVE_MODULE_SET"; }
                else if (token == "UPGRADE_REQUEST" || token == "UPGRADE_LEDGER_PROOF" || token == "ACTIVE_VERSION_UNCHANGED") { satisfied = (definition.Driver == "UPGRADE_PIPE" || definition.Driver == "UPGRADE_VERIFIER") && response.ContainsKey("upgrade_server_capture_resolved") && R7Json.Boolean(response, "upgrade_server_capture_resolved") && response.ContainsKey("upgrade_request_identity"); basis = "UPGRADE_AUTHORITY_SERVER_CAPTURE_AND_SIGNED_LEDGER_LOOKUP"; }
                else if (token == "RESTART_RECOVERY_PROOF" && definition.Operation == "RETRY_REQUEST") { satisfied = retryOriginalCommitted && retryResponseIdentical && retryRestartProven; basis = "ORIGINAL_COMMIT_AND_DISTINCT_SIGNER_PROCESS_INSTANCE"; }
                else if (token == "APPEND_ONLY_TRANSACTION_LOG" || token == "CHECKPOINT_PROOF" || token == "FAULT_POINT_PROOF" || token == "LEDGER_CHAIN_PROOF" || token == "RESTART_PROOF" || token == "RECOVERY_POLICY" || token == "RECOVERY_TRANSITION_LOG" || token == "RESTART_BOUNDARY" || token == "RESTART_RECOVERY_PROOF" || token == "INVALID_CHECKPOINT_BYTES" || token == "LAST_VALID_CHECKPOINT" || token == "LATER_VALID_CHAIN" || token == "STALE_VALID_CHECKPOINT" || token == "CLIENT_DISCONNECT" || token == "ABSENT_COMMIT") { satisfied = recoveryEvidence; basis = "ISOLATED_SIGNED_RECOVERY_PROBE_EVIDENCE"; }
                else if (token == "COMPLETE_LEDGER_CHAIN" || token == "ALL_CHAIN_SIGNATURES" || token == "CLASSIFICATION_FOR_EACH_ENTRY" || token == "VERSION_RESOLUTION_FOR_EACH_ENTRY") { satisfied = code == "ALL_ENTRIES_CLASSIFIED"; basis = "VERSION_AWARE_PUBLIC_CHAIN_VERIFICATION"; }
                else if (token == "OUTER_INVOCATION") { satisfied = R7Json.String(capture, "derivation", 1, 128) == "SIGNER_SERVER_CAPTURE"; basis = "SERVER_OBSERVED_OUTER_PIPE_CALL"; }
                else if (token == "SERVICE_CONTROL_IDENTITY" && definition.CaseId.StartsWith("PRI-", StringComparison.Ordinal)) { satisfied = serverPrincipalProbe; basis = "SIGNER_PROCESS_INSTANCE_AND_CALLER_TOKEN_CAPTURE"; }
                else if (token == "PIPE_CONNECTION_FAILURE" || token == "SERVICE_STOPPED_STATE" || token == "SERVICE_CONTROL_IDENTITY") { satisfied = code == "SERVICE_UNAVAILABLE" && response.ContainsKey("service_control_proof_identity"); basis = "SCM_AND_RAW_CONNECTION_FAILURE_PROOF"; }
                else if (token == "REQUEST_CONTENT_HASH" || token == "REQUEST_IDENTITY") { satisfied = rawComplete && R7Hash.IsLowerSha256(R7Json.String(capture, "request_frame_sha256", 64, 64)); basis = "SERVER_CAPTURED_REQUEST_IDENTITY"; }
                else if (token == "COMMIT_ENTRY" || token == "RESERVATION_ENTRY" || token == "RECEIPT_CONTENT" || token == "FINAL_STATE_PROOF" || token == "ORIGINAL_COMMIT") { satisfied = committedTransaction || (definition.Operation == "RETRY_REQUEST" && retryOriginalCommitted); basis = committedTransaction ? "SIGNED_LEDGER_TRANSACTION_ADVANCED" : "ORIGINAL_SIGNED_TRANSACTION_RESOLVED"; }
                else if (token == "RECONSTRUCTED_RESPONSE_HASH") { satisfied = (definition.Operation == "RETRY_REQUEST" && retryOriginalCommitted && retryResponseIdentical) || recoveryEvidence; basis = "AUTHORITATIVE_TRANSACTION_RESPONSE_RECONSTRUCTION"; }
                else if (token == "REPLAY_PROOF") { satisfied = (definition.Operation == "RETRY_REQUEST" && retryOriginalCommitted && retryResponseIdentical) || recoveryEvidence; basis = "DETERMINISTIC_REPLAY_OR_RETRY"; }
                else if (token == "TWO_DISJOINT_VALID_GRAPHS" || token == "BOTH_TERMINAL_MEMBERSHIP_PROOFS" || token == "EXTERNAL_COMPARISON") { satisfied = code == "RECONCILIATION_COMMITTED"; basis = "SIGNER_RESOLVED_BOTH_COMMITTED_GRAPHS"; }
                else throw new R7ProtocolException("UNSUPPORTED_EXPECTATION_EVIDENCE_OBLIGATION", token);
                if (!satisfied) throw new R7ProtocolException("EXPECTATION_EVIDENCE_OBLIGATION_UNMET", token);
                evidenceProofs.Add(R7Json.Object("basis", basis, "satisfied", true, "token", token));
            }
            List<object> effectProofs = new List<object>();
            foreach (string token in expectation.RequiredEffects)
            {
                bool recoveryToken = token == "GOVERNED_RECOVERY_OR_ABORT_ENTRY_WHEN_STATE_EXISTS" || token == "ATOMIC_CHECKPOINT_REPLACEMENT" || token == "RECOVERY_ENTRY" || token == "RECOVERY_COMPLETION_ENTRY" || token == "ABORT_ENTRY" || token == "RESPONSE_AVAILABLE_ENTRY";
                bool transactionToken = token == "CANDIDATE_EVIDENCE_ENTRY" || token == "CONTENT_ADDRESSED_RESPONSE" || token == "RECEIPT_PREPARED_ENTRY" || token == "RECONCILIATION_COMMIT_ENTRY" || token == "RECONCILIATION_PREPARED_ENTRY" || token == "REQUEST_RECEIVED_ENTRY" || token == "RESERVED_ENTRY" || token == "TERMINAL_COMMIT_ENTRY";
                bool retryToken = token == "RESPONSE_AVAILABLE_ENTRY_IF_NOT_ALREADY_PRESENT";
                bool concurrencyToken = token == "ONE_NONAUTHORITY_PROPOSAL_TRANSACTION";
                if (!recoveryToken && !transactionToken && !retryToken && !concurrencyToken) throw new R7ProtocolException("UNSUPPORTED_EXPECTATION_REQUIRED_EFFECT", token);
                bool satisfied = recoveryToken ? recoveryEvidence : retryToken ? definition.Operation == "RETRY_REQUEST" && status == "COMPLETE" : concurrencyToken ? concurrencyProof : committedTransaction;
                if (!satisfied) throw new R7ProtocolException("EXPECTATION_REQUIRED_EFFECT_UNMET", token);
                effectProofs.Add(R7Json.Object("basis", recoveryToken ? "ISOLATED_RECOVERY_TRANSITION" : concurrencyToken ? "SIGNER_RESOLVED_SINGLE_CONCURRENT_TRANSACTION" : "SIGNED_TRANSACTION_LEDGER_ADVANCE", "satisfied", true, "token", token));
            }
            List<object> forbiddenProofs = new List<object>();
            foreach (string token in expectation.ForbiddenEffects)
            {
                bool absent;
                string basis;
                if (token == "TRUST_WRITE") { absent = trustUnchanged; basis = "TRUST_TREE_IDENTITY_UNCHANGED"; }
                else if (token == "UPGRADE_AUTHORIZATION") { absent = upgradeUnchanged; basis = "UPGRADE_AUTHORIZATION_TREE_UNCHANGED"; }
                else if (token == "RECEIPT_WRITE") { absent = receiptsUnchanged; basis = "RECEIPT_TREE_IDENTITY_UNCHANGED"; }
                else if (token == "LEDGER_APPEND" || token == "LEDGER_AUTHORITY_APPEND" || token == "AUTHORITY_STATE_CHANGE") { absent = ledgerUnchanged && (token != "AUTHORITY_STATE_CHANGE" || authorityFilesUnchanged); basis = "LEDGER_AND_AUTHORITY_STATE_UNCHANGED"; }
                else if (token == "TERMINAL_COMMIT" || token == "FRESH_TERMINAL_AUTHORITY" || token == "TERMINAL_RECEIPT" || token == "SECOND_TERMINAL_COMMIT" || token == "TERMINAL_COMMIT_BEFORE_EVIDENCE_VALIDATION") { absent = code != "TERMINAL_RECEIPT_COMMITTED"; basis = "NO_FRESH_TERMINAL_CLASSIFICATION"; }
                else if (token == "RECONCILIATION_COMMIT" || token == "RECONCILIATION_USE" || token == "RECONCILIATION_OF_UNCOMMITTED_OR_INVALID_GRAPH") { absent = code != "RECONCILIATION_COMMITTED"; basis = "NO_RECONCILIATION_CLASSIFICATION"; }
                else if (token == "HISTORY_DELETION" || token == "LEDGER_REWRITE") { absent = ledgerAfter >= ledgerBefore; basis = "APPEND_ONLY_CHAIN_MONOTONICITY"; }
                else if (token == "PYTHON_OR_GIT_AUTHORITY_INVOCATION") { absent = definition.Driver == "DEPENDENCY_PROBE" && code == "REMOVED_FROM_AUTHORITY_PATH"; basis = "LIVE_MODULE_AND_RUNTIME_INVOCATION_SCAN"; }
                else if (token == "SIGNER_TOKEN_CHILD") { absent = serverSignerProcessTreeIsolated; basis = "SERVER_ENUMERATED_SIGNER_PROCESS_TREE_AND_DISTINCT_CALLER_TOKEN"; }
                else if (token == "UNVERIFIED_CHILD_ASSERTION_AS_AUTHORITY") { absent = rawComplete && committedTransaction && definition.Operation == "SUBMIT_RUN_GRAPH" && status == "COMPLETE" && code == "TERMINAL_RECEIPT_COMMITTED"; basis = "SIGNER_RESOLVED_RAW_STAGE_GRAPH_AND_COMMITTED_TRANSACTION"; }
                else if (token == "AUTHORITY_EFFECT_FROM_BOUNDARY_PROBE") { absent = ledgerUnchanged && receiptsUnchanged && responsesUnchanged && trustUnchanged && upgradeUnchanged; basis = "BOUNDARY_PROBE_PROTECTED_STATE_UNCHANGED"; }
                else if (token == "AMBIGUOUS_COMMIT") { absent = recoveryEvidence; basis = "ISOLATED_RECOVERY_AUDITOR_RESOLVED_EXACT_TERMINAL_STATE"; }
                else if (token == "CLIENT_VISIBLE_REJECTION_CLASSIFICATION") { absent = recoveryEvidence && code == "RESPONSE_RECONSTRUCTED"; basis = "COMMITTED_RESPONSE_RECONSTRUCTED_FROM_TRANSACTION_LEDGER"; }
                else if (token == "DUPLICATE_AUTHORITY") { absent = recoveryEvidence && code == "RECOVERY_RESUMED"; basis = "RECOVERY_AUDITOR_PROVED_SINGLE_COMMITTED_IDENTITY"; }
                else if (token == "FALLBACK_AUTHORITY") { absent = status == "UNAVAILABLE" && code == "SERVICE_UNAVAILABLE" && ledgerUnchanged && receiptsUnchanged && responsesUnchanged; basis = "SERVICE_UNAVAILABLE_AND_PROTECTED_STATE_UNCHANGED"; }
                else if (token == "GLOBAL_FAILURE_FROM_LEGACY_CLASS") { absent = code == "ALL_ENTRIES_CLASSIFIED"; basis = "VERSION_AWARE_PUBLIC_VERIFIER_COMPLETED_ALL_ENTRIES"; }
                else if (token == "MUTATED_RESPONSE") { absent = concurrencyProof ? code == "CONCURRENT_IDENTICAL_RETRY_RESOLVED" : retryResponseIdentical; basis = concurrencyProof ? "CONCURRENT_RESPONSE_HASHES_IDENTICAL" : "RETRY_RESPONSE_IDENTITY_MATCHED_COMMITTED_RESPONSE"; }
                else if (token == "SECOND_COMMIT") { absent = concurrencyProof || retryResponseIdentical || recoveryEvidence; basis = concurrencyProof ? "ONE_TRANSACTION_STATE_FOR_CONCURRENT_REQUESTS" : retryResponseIdentical ? "RETRY_RECONSTRUCTED_ORIGINAL_COMMIT" : "RECOVERY_AUDITOR_PROVED_SINGLE_COMMIT"; }
                else if (token == "ABORT_OF_COMMITTED_AUTHORITY") { absent = recoveryEvidence && code == "RESPONSE_RECONSTRUCTED"; basis = "COMMITTED_TRANSACTION_REMAINS_RECONSTRUCTABLE"; }
                else throw new R7ProtocolException("UNSUPPORTED_EXPECTATION_FORBIDDEN_EFFECT", token);
                if (!absent) throw new R7ProtocolException("EXPECTATION_FORBIDDEN_EFFECT_OBSERVED", token);
                forbiddenProofs.Add(R7Json.Object("basis", basis, "satisfied", true, "token", token));
            }
            return objects.Put(R7Json.Object(
                "case_id", definition.CaseId,
                "evidence_obligations", evidenceProofs.ToArray(),
                "forbidden_effect_obligations", forbiddenProofs.ToArray(),
                "required_effect_obligations", effectProofs.ToArray(),
                "restart_retry_obligation", expectation.RestartRetry,
                "restart_retry_verified_by", RestartRetryBasis(definition, expectation, recoveryEvidence, committedTransaction, retryOriginalCommitted, retryResponseIdentical, retryRestartProven, concurrencyProof, status),
                "schema_version", "1.0.0"));
        }

        private static string RestartRetryBasis(R7CaseDefinition definition, R7Expectation expectation, bool recoveryEvidence, bool committedTransaction, bool retryOriginalCommitted, bool retryResponseIdentical, bool retryRestartProven, bool concurrencyProof, string status)
        {
            string obligation = expectation.RestartRetry;
            if (obligation == "IDENTICAL_RETRY_RETURNS_IDENTICAL_REJECTION" || obligation == "IDENTICAL_BOUNDARY_FRAME_HAS_IDENTICAL_PARSE_RESULT" || obligation == "REPLAY_IS_READ_ONLY_AND_DETERMINISTIC") return "DETERMINISTIC_CANONICAL_REQUEST_AND_NO_AUTHORITY_EFFECT";
            if (obligation == "RESTART_LOAD_SET_REMAINS_CLOSED") return "DEPENDENCY_CLOSURE_RECHECKED_EACH_REQUEST";
            if (obligation == "RESTART_PRESERVES_SERVICE_IDENTITY_SEPARATION") return "SERVICE_SID_AND_CALLER_TOKEN_REMEASURED";
            if (obligation == "CONCURRENT_SAME_IDENTITY_RETRY_IS_DETERMINISTIC")
            {
                if (!concurrencyProof) throw new R7ProtocolException("RESTART_RETRY_OBLIGATION_UNMET", obligation);
                return "OS_CONCURRENT_CONNECTIONS_AND_SINGLE_DURABLE_TRANSACTION_STATE";
            }
            if (obligation == "ADDITIONAL_RESTART_IS_IDEMPOTENT" || obligation == "REPEATED_RECOVERY_IS_IDEMPOTENT" || obligation == "SECOND_RECOVERY_IS_IDEMPOTENT" || obligation == "RESTART_PROOF" || obligation == "REPLAY_IS_DETERMINISTIC")
            {
                if (!recoveryEvidence) throw new R7ProtocolException("RESTART_RETRY_OBLIGATION_UNMET", obligation);
                return "ISOLATED_RECOVERY_ENGINE_RESTART_AND_REPLAY_PROOF";
            }
            if (obligation == "EVERY_RETRY_RETURNS_BYTE_IDENTICAL_RESPONSE" || obligation == "POST_RESTART_RETRY_IS_BYTE_IDENTICAL" || obligation == "RETRY_IS_BYTE_IDENTICAL" || obligation == "SAME_GRAPH_IDENTITY_REPLAYS_THE_SAME_CANDIDATE_CLASSIFICATION" || obligation == "SAME_IDENTITY_SAME_BYTES_RECONSTRUCTS_IDENTICAL_COMMITTED_RESPONSE" || obligation == "SAME_IDENTITY_SAME_BYTES_RESOLVES_THE_RESERVATION")
            {
                if (definition.Operation == "RETRY_REQUEST" && (!retryOriginalCommitted || !retryResponseIdentical || (obligation == "POST_RESTART_RETRY_IS_BYTE_IDENTICAL" && !retryRestartProven))) throw new R7ProtocolException("RESTART_RETRY_OBLIGATION_UNMET", obligation);
                if (definition.Operation != "RETRY_REQUEST" && !committedTransaction) throw new R7ProtocolException("RESTART_RETRY_OBLIGATION_UNMET", obligation);
                return "TRANSACTION_LEDGER_RESPONSE_RECONSTRUCTION";
            }
            if (obligation == "RETRY_REQUIRES_SERVICE_RETURN_AND_DOES_NOT_INFER_SUCCESS" || obligation == "RETRY_RETURNS_ABORT_CLASSIFICATION") return "FAIL_CLOSED_OR_ABORT_CLASSIFICATION";
            if (status == "REJECTED" || status == "UNAVAILABLE") return "CANONICAL_REQUEST_IDENTITY_AND_FAIL_CLOSED_CLASSIFICATION";
            throw new R7ProtocolException("UNSUPPORTED_RESTART_RETRY_OBLIGATION", obligation);
        }

        private static bool StateFieldEqual(SortedDictionary<string, object> before, SortedDictionary<string, object> after, string field)
        {
            return R7Hash.FixedTimeEquals(R7Json.String(before, field, 64, 64), R7Json.String(after, field, 64, 64));
        }

        private static string DeriveParserResult(byte[] frame)
        {
            if (frame.Length >= R7Fixed.FrameHeaderBytes)
            {
                int length = (frame[8] << 24) | (frame[9] << 16) | (frame[10] << 8) | frame[11];
                if (length <= R7Fixed.MaximumPayloadBytes && frame.Length > R7Fixed.FrameHeaderBytes + length) return "MULTIPLE_FRAMES";
            }
            try
            {
                SortedDictionary<string, object> request = R7Framing.Decode(frame);
                string operation = R7Json.String(request, "operation", 1, 128);
                SortedDictionary<string, object> payload = R7Json.Child(request, "payload");
                if (operation == "GET_LEDGER_ENTRY") { R7Json.ExactKeys(payload, "sequence"); R7Json.Integer(payload, "sequence", 1, Int64.MaxValue); return "LEDGER_ENTRY_RESOLVED"; }
                if (operation == "GET_TERMINAL_RECEIPT") { R7Json.ExactKeys(payload, "receipt_identity"); R7Json.String(payload, "receipt_identity", 64, 64); return "TERMINAL_RECEIPT_RESOLVED"; }
                if (operation == "FRAME_BOUNDARY" && frame.Length == R7Fixed.MaximumFrameBytes) return "FRAME_SIZE_ACCEPTED";
                return "PARSER_ACCEPTED_UNEXPECTEDLY";
            }
            catch (R7ProtocolException exception) { return NormalizeError(exception.Code); }
        }

        private void ValidateCommittedCurrentGraphObligation(string receiptIdentity, SortedDictionary<string, object> receipt, string runKind, string requiredCaseId, string classification)
        {
            R7TransactionSnapshot transaction = transactions.FindByReceipt(receiptIdentity);
            if (transaction == null || (transaction.State != "COMMITTED" && transaction.State != "RESPONSE_AVAILABLE")) throw new R7ProtocolException("CURRENT_GRAPH_RECEIPT_NOT_COMMITTED");
            if (R7Json.String(receipt, "terminal_classification", 1, 256) != classification) throw new R7ProtocolException("CURRENT_GRAPH_CLASSIFICATION_MISMATCH");
            SortedDictionary<string, object> details = R7Json.Child(receipt, "details");
            if (R7Json.String(details, "run_kind", 1, 64) != runKind || !R7Json.Boolean(details, "complete_case_registry")) throw new R7ProtocolException("CURRENT_GRAPH_RUN_INCOMPLETE");
            SortedDictionary<string, object> graph = objects.Get(R7Json.String(receipt, "evidence_identity", 64, 64));
            bool found = false;
            foreach (object raw in R7Json.Array(graph, "case_results"))
            {
                SortedDictionary<string, object> locator = RequireObject(raw);
                if (R7Json.String(locator, "case_id", 1, 128) != requiredCaseId) continue;
                SortedDictionary<string, object> result = objects.Get(R7Json.String(locator, "result_identity", 64, 64));
                if (!R7Hash.IsLowerSha256(R7Json.String(result, "base_interaction_identity", 64, 64)) ||
                    !R7Hash.IsLowerSha256(R7Json.String(result, "base_capture_identity", 64, 64)) ||
                    !R7Hash.IsLowerSha256(R7Json.String(result, "event_capture_identity", 64, 64)) ||
                    !R7Hash.IsLowerSha256(R7Json.String(result, "observation_capture_identity", 64, 64)) ||
                    !R7Hash.IsLowerSha256(R7Json.String(result, "comparator_capture_identity", 64, 64)) ||
                    !R7Hash.IsLowerSha256(R7Json.String(result, "obligation_proof_identity", 64, 64)) ||
                    !R7Json.Boolean(result, "raw_evidence_complete") || !R7Json.Boolean(result, "obligations_verified") || !R7Json.Boolean(result, "signer_rederived") || !R7Json.Boolean(result, "passed")) throw new R7ProtocolException("CURRENT_GRAPH_OBLIGATION_INVALID");
                found = true;
            }
            if (!found) throw new R7ProtocolException("CURRENT_GRAPH_OBLIGATION_MISSING");
        }

        private R7ReconciliationEvaluation CompareGraphEvidence(string candidateIdentity, string freshIdentity)
        {
            SortedDictionary<string, object> candidate = objects.Get(candidateIdentity);
            SortedDictionary<string, object> fresh = objects.Get(freshIdentity);
            object[] candidateRows = R7Json.Array(candidate, "case_results");
            object[] freshRows = R7Json.Array(fresh, "case_results");
            Dictionary<string, string> candidateResults = ResultMap(candidateRows);
            Dictionary<string, string> freshResults = ResultMap(freshRows);
            bool complementary = candidateResults.ContainsKey("POS-005") && !candidateResults.ContainsKey("POS-006") && freshResults.ContainsKey("POS-006") && !freshResults.ContainsKey("POS-005");
            int compared = 0;
            foreach (KeyValuePair<string, string> item in candidateResults)
            {
                string freshResultIdentity;
                if (!freshResults.TryGetValue(item.Key, out freshResultIdentity)) continue;
                SortedDictionary<string, object> left = objects.Get(item.Value);
                SortedDictionary<string, object> right = objects.Get(freshResultIdentity);
                foreach (string field in new string[] { "actual_code", "actual_status", "case_id", "expected_code", "expected_response_class", "expected_terminal_classification", "obligations_verified", "passed", "signer_derived_terminal_classification" })
                {
                    if (!JsonScalarEqual(left[field], right[field])) return new R7ReconciliationEvaluation { Matched = false, ComparedCaseCount = compared, ComplementaryMetaCasesVerified = complementary };
                }
                if (!R7Json.Boolean(left, "passed") || !R7Json.Boolean(right, "passed")) return new R7ReconciliationEvaluation { Matched = false, ComparedCaseCount = compared, ComplementaryMetaCasesVerified = complementary };
                compared++;
            }
            return new R7ReconciliationEvaluation { Matched = compared > 0, ComparedCaseCount = compared, ComplementaryMetaCasesVerified = complementary };
        }

        private bool CompleteForRun(string runKind, HashSet<string> seen)
        {
            if (runKind == "CASE_CANDIDATE" || runKind == "CASE_FRESH")
            {
                if (seen.Count != authority.CaseIds.Length - 2 || seen.Contains("POS-005") || seen.Contains("POS-006")) return false;
                foreach (string caseId in authority.CaseIds) if (caseId != "POS-005" && caseId != "POS-006" && !seen.Contains(caseId)) return false;
                return true;
            }
            bool candidate = runKind == "CANDIDATE" || runKind == "BOOTSTRAP_CANDIDATE";
            string excluded = candidate ? "POS-006" : "POS-005";
            string requiredMeta = candidate ? "POS-005" : "POS-006";
            if (seen.Count != authority.CaseIds.Length - 1 || seen.Contains(excluded) || !seen.Contains(requiredMeta)) return false;
            foreach (string caseId in authority.CaseIds) if (caseId != excluded && !seen.Contains(caseId)) return false;
            return true;
        }

        private SortedDictionary<string, object> ReceiptPayload(string receiptType, string requestIdentity, string requestSha256, string evidenceIdentity, string classification, SortedDictionary<string, object> details)
        {
            return R7Json.Object(
                "activation_identity", activeUpgrade.ActivationIdentity,
                "authority_identities", R7Json.Object(
                    "case_definitions_sha256", policy.AuthorityIdentities.CaseSha256,
                    "coverage_proof_sha256", policy.AuthorityIdentities.CoverageSha256,
                    "expectations_sha256", policy.AuthorityIdentities.ExpectationSha256,
                    "requirement_registry_sha256", policy.AuthorityIdentities.RequirementSha256,
                    "source_manifest_sha256", policy.AuthorityIdentities.SourceManifestSha256),
                "details", details,
                "evidence_identity", evidenceIdentity,
                "interface_version", R7Fixed.InterfaceVersion,
                "issue_time", DateTimeOffset.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture),
                "ledger_id", R7Fixed.LedgerId,
                "policy_sha256", policy.PolicySha256,
                "public_key_identity", R7Fixed.TerminalPublicKeyIdentity,
                "receipt_type", receiptType,
                "request_identity", requestIdentity,
                "request_sha256", requestSha256,
                "schema_version", "4.0.0",
                "source_commit", policy.SourceCommit,
                "source_tree", policy.SourceTree,
                "terminal_classification", classification,
                "upgrade_authorization_identity", activeUpgrade.AuthorizationIdentity);
        }

        private SortedDictionary<string, object> LoadCommittedReceipt(string identity)
        {
            R7TransactionSnapshot snapshot = transactions.FindByReceipt(identity);
            if (snapshot == null || (snapshot.State != "COMMITTED" && snapshot.State != "RESPONSE_AVAILABLE")) throw new R7ProtocolException("RECEIPT_NOT_COMMITTED");
            string path = Path.Combine(R7Fixed.ReceiptRoot, identity + ".receipt.json");
            using (R7VerifiedFile file = R7SafeFile.Open(path, path, R7Fixed.ReceiptRoot, identity, R7Fixed.TerminalSid, null, policy.VolumeIdentity)) return R7Crypto.VerifyEnvelope(file.Bytes, R7Fixed.TerminalPublicKeyIdentity, verifier);
        }

        private void RegisterUpgradeAndHistory()
        {
            if (ledger.Find("R7R_SERVICE_UPGRADE_ACTIVATED", activeUpgrade.AuthorizationIdentity).Length == 0)
            {
                string content = objects.Put(R7Json.Object(
                    "activation_identity", activeUpgrade.ActivationIdentity,
                    "authorization_identity", activeUpgrade.AuthorizationIdentity,
                    "interface_version", R7Fixed.InterfaceVersion,
                    "policy_sha256", policy.PolicySha256,
                    "source_commit", policy.SourceCommit,
                    "source_tree", policy.SourceTree));
                ledger.Append("R7R_SERVICE_UPGRADE_ACTIVATED", Guid.NewGuid().ToString("D"), activeUpgrade.AuthorizationIdentity, content, R7Fixed.InterfaceVersion);
            }
            string historySubject = R7BuildIdentity.HistoricalClassificationRegistrySha256;
            if (ledger.Find("R7R_HISTORICAL_CLASSIFICATION_COMMITTED", historySubject).Length == 0)
            {
                SortedDictionary<string, object> historyRegistry;
                using (R7VerifiedFile historyFile = R7SafeFile.Open(R7Fixed.HistoricalClassificationPath, R7Fixed.HistoricalClassificationPath, Path.GetDirectoryName(R7Fixed.HistoricalClassificationPath), R7BuildIdentity.HistoricalClassificationRegistrySha256, R7Fixed.SystemSid, null, policy.VolumeIdentity)) historyRegistry = RequireObject(R7Json.Parse(historyFile.Bytes));
                object[] verifiedBindings = R7HistoricalClassification.VerifyRegistry(historyRegistry, ledger, verifier, policy.VolumeIdentity);
                string content = objects.Put(R7Json.Object(
                    "classification_time", DateTimeOffset.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture),
                    "governed_registry", historyRegistry,
                    "governed_registry_raw_sha256", historySubject,
                    "infrastructure_range", R7Json.Object("classification", "VALID_PROVISIONED_INFRASTRUCTURE_AUTHORITY", "end_sequence", 5L, "start_sequence", 1L),
                    "rejected_v3_range", R7Json.Object("classification", "STRUCTURALLY_VALID_REJECTED_NONAUTHORITATIVE_CANDIDATE_EVIDENCE", "end_sequence", 678L, "start_sequence", 6L),
                    "schema_version", "1.0.0",
                    "sequence_332_reuse", "PERMANENTLY_FORBIDDEN",
                    "sequence_678_reuse", "PERMANENTLY_FORBIDDEN",
                    "superseded_policy_sha256", "76eb2900b2000aa0b41e6040335cc323f7443728aad21cd871d5b6b8e17bcd8b",
                    "superseded_service_binary_sha256", "9ea829416f37c94db2858586fa5e0042652f6caa4637a29fdbefb513577a7526",
                    "verified_historical_bindings", verifiedBindings));
                ledger.Append("R7R_HISTORICAL_CLASSIFICATION_COMMITTED", Guid.NewGuid().ToString("D"), historySubject, content, R7Fixed.InterfaceVersion);
            }
            string trustSubject = R7Hash.Bytes(new UTF8Encoding(false, true).GetBytes("R7R_TRUST_VERSION|" + R7Fixed.InterfaceVersion + "|" + activeUpgrade.AuthorizationIdentity));
            if (ledger.Find("R7R_TRUST_VERSION_REGISTERED", trustSubject).Length == 0)
            {
                string content = objects.Put(R7Json.Object(
                    "activation_identity", activeUpgrade.ActivationIdentity,
                    "interface_version", R7Fixed.InterfaceVersion,
                    "policy_sha256", policy.PolicySha256,
                    "terminal_public_key_identity", R7Fixed.TerminalPublicKeyIdentity,
                    "upgrade_public_key_identity", R7BuildIdentity.UpgradePublicCertificateSha256));
                ledger.Append("R7R_TRUST_VERSION_REGISTERED", Guid.NewGuid().ToString("D"), trustSubject, content, R7Fixed.InterfaceVersion);
            }
        }

        private void RecoverCheckpointIfRequired()
        {
            string reason = ledger.CheckpointRecoveryReason;
            if (String.IsNullOrEmpty(reason)) return;
            string checkpointPath = Path.Combine(R7Fixed.LedgerRoot, "checkpoint.json");
            string priorIdentity = R7Fixed.ZeroHash;
            R7VerifiedFile checkpoint;
            if (R7SafeFile.TryOpen(checkpointPath, checkpointPath, R7Fixed.LedgerRoot, null, null, null, policy.VolumeIdentity, out checkpoint))
            {
                using (checkpoint)
                {
                    priorIdentity = checkpoint.Measurement.Sha256;
                    string preserved = Path.Combine(R7Fixed.RecoveryRoot, "checkpoint." + priorIdentity + ".preserved");
                    PreserveContentAddressedFile(preserved, checkpoint.Bytes, priorIdentity);
                }
            }

            R7CheckpointArtifact[] pending = ledger.PendingCheckpointArtifacts;
            object[] pendingValues = new object[pending.Length];
            string[] pendingTokens = new string[pending.Length];
            for (int index = 0; index < pending.Length; index++)
            {
                pendingValues[index] = R7Json.Object("identity", pending[index].Identity, "name", pending[index].Name);
                pendingTokens[index] = pending[index].Name + "|" + pending[index].Identity;
            }
            Array.Sort(pendingTokens, StringComparer.Ordinal);
            string recoverySubject = R7Hash.Bytes(new UTF8Encoding(false, true).GetBytes(
                "R7R_CHECKPOINT_RECOVERY|" + priorIdentity + "|" + reason + "|" + String.Join("\n", pendingTokens)));
            R7LedgerRecord recoveryRecord = FindPendingCheckpointRecovery(priorIdentity, reason, pendingValues, recoverySubject);
            if (recoveryRecord == null)
            {
                long sequenceBefore = ledger.Sequence;
                string rootBefore = ledger.RootHash;
                string content = objects.Put(R7Json.Object(
                "checkpoint_identity_before", priorIdentity,
                "ledger_root_before", rootBefore,
                "ledger_sequence_before", sequenceBefore,
                "pending_checkpoint_artifacts", pendingValues,
                "recovery_subject", recoverySubject,
                "recovery_target_sequence", checked(sequenceBefore + 1),
                "reason", reason));
                recoveryRecord = ledger.Append("R7R_CHECKPOINT_RECOVERY_INTENT", Guid.NewGuid().ToString("D"), recoverySubject, content, R7Fixed.InterfaceVersion).Record;
            }
            if (pending.Length != 0) ledger.PreservePendingCheckpoints(R7Fixed.RecoveryRoot);
            if (!String.IsNullOrEmpty(ledger.CheckpointRecoveryReason)) ledger.RecoverCheckpoint(R7Fixed.InterfaceVersion);
            if (!String.IsNullOrEmpty(ledger.CheckpointRecoveryReason) || ledger.CheckpointIdentity == R7Fixed.ZeroHash) throw new R7DurabilityUncertainException("CHECKPOINT_RECOVERY_NOT_DURABLE", null);
        }

        private R7LedgerRecord FindPendingCheckpointRecovery(string priorIdentity, string reason, object[] pendingValues, string recoverySubject)
        {
            R7LedgerRecord[] records = ledger.Find("R7R_CHECKPOINT_RECOVERY_INTENT", null);
            for (int index = records.Length - 1; index >= 0; index--)
            {
                R7LedgerRecord record = records[index];
                if (record.Sequence != ledger.Sequence || !String.Equals(record.EntryHash, ledger.RootHash, StringComparison.Ordinal)) continue;
                SortedDictionary<string, object> content = objects.Get(record.ContentAddress);
                R7Json.ExactKeys(content,
                    "checkpoint_identity_before", "ledger_root_before", "ledger_sequence_before", "pending_checkpoint_artifacts",
                    "recovery_subject", "recovery_target_sequence", "reason");
                string recordedBefore = R7Json.String(content, "checkpoint_identity_before", 64, 64);
                string recordedReason = R7Json.String(content, "reason", 1, 4096);
                string recordedSubject = R7Json.String(content, "recovery_subject", 64, 64);
                long sequenceBefore = R7Json.Integer(content, "ledger_sequence_before", 0, Int64.MaxValue);
                long targetSequence = R7Json.Integer(content, "recovery_target_sequence", 1, Int64.MaxValue);
                bool currentCheckpointAlreadyAdvanced = reason.StartsWith("ORPHAN_CHECKPOINT_TEMP_", StringComparison.Ordinal) && recordedReason.EndsWith(reason, StringComparison.Ordinal);
                if (!R7Hash.IsLowerSha256(recordedBefore) || !R7Hash.IsLowerSha256(recordedSubject) ||
                    (!String.Equals(recordedBefore, priorIdentity, StringComparison.Ordinal) && !currentCheckpointAlreadyAdvanced) ||
                    sequenceBefore != record.Sequence - 1 || targetSequence != record.Sequence ||
                    !String.Equals(R7Json.String(content, "ledger_root_before", 64, 64), R7Json.String(record.Payload, "prior_entry_hash", 64, 64), StringComparison.Ordinal)) continue;
                bool reasonMatches = String.Equals(recordedReason, reason, StringComparison.Ordinal) || recordedReason.StartsWith(reason + "__AND__", StringComparison.Ordinal) || currentCheckpointAlreadyAdvanced;
                if (!reasonMatches) continue;
                object[] recordedPending = R7Json.Array(content, "pending_checkpoint_artifacts");
                if (pendingValues.Length != 0 && R7Hash.Bytes(R7Json.Encode(recordedPending)) != R7Hash.Bytes(R7Json.Encode(pendingValues))) continue;
                if (String.Equals(record.SubjectId, recoverySubject, StringComparison.Ordinal) && String.Equals(recordedSubject, recoverySubject, StringComparison.Ordinal)) return record;
                if (pendingValues.Length == 0 && String.Equals(record.SubjectId, recordedSubject, StringComparison.Ordinal)) return record;
            }
            return null;
        }

        private static void PreserveContentAddressedFile(string path, byte[] bytes, string identity)
        {
            R7VerifiedFile existing;
            if (R7SafeFile.TryOpen(path, path, R7Fixed.RecoveryRoot, identity, R7Fixed.TerminalSid, null, null, out existing))
            {
                existing.Dispose();
                return;
            }
            try { R7DurableFile.CreateNew(path, bytes); }
            catch (IOException exception)
            {
                if (!R7DurableFile.IsAlreadyExists(exception)) throw;
                if (!R7SafeFile.TryOpen(path, path, R7Fixed.RecoveryRoot, identity, R7Fixed.TerminalSid, null, null, out existing)) throw;
                existing.Dispose();
            }
        }

        private void AuthorizeCaller(R7CallerIdentity caller, string operation)
        {
            string sid = caller.UserSid;
            bool publicRead = operation == "GET_HEALTH" || operation == "GET_PUBLIC_TRUST" || operation == "GET_LEDGER_STATUS" || operation == "GET_LEDGER_ENTRY" || operation == "GET_TERMINAL_RECEIPT" || operation == "GET_RECONCILIATION" || operation == "GET_RECOVERY_STATE" || operation == "RESOLVE_INTERACTION" || operation == "GET_INTERACTION_EVIDENCE" || operation == "VERIFY_TERMINAL_RECEIPT" || operation == "VERIFY_RECONCILIATION" || operation == "CLASSIFY_RECEIPT" || operation == "CLASSIFY_LEDGER_SEQUENCE" || operation == "GET_VERSION_HISTORY";
            if (sid == R7Fixed.ExecutionSid)
            {
                RequireMeasuredCaller(caller, "EXECUTION");
                if (operation != "SUBMIT_EXECUTION_EVIDENCE") throw new SecurityException("CALLER_NOT_AUTHORIZED");
                return;
            }
            if (sid == R7Fixed.ObservationSid)
            {
                RequireMeasuredCaller(caller, "OBSERVATION");
                if (operation != "SUBMIT_OBSERVATION_EVIDENCE") throw new SecurityException("CALLER_NOT_AUTHORIZED");
                return;
            }
            if (sid == R7Fixed.ComparatorSid)
            {
                RequireMeasuredCaller(caller, "COMPARATOR");
                if (operation != "SUBMIT_COMPARATOR_EVIDENCE") throw new SecurityException("CALLER_NOT_AUTHORIZED");
                return;
            }
            if (sid == R7Fixed.OperatorSid)
            {
                if (operation == "SUBMIT_PUBLIC_VERIFICATION_EVIDENCE") { RequireMeasuredCaller(caller, "PUBLIC_VERIFIER"); return; }
                bool auditRead = publicRead || operation == "RESOLVE_EVIDENCE_SUBMISSION" || operation == "GET_INTERACTION_RAW_EVIDENCE";
                bool governedOuter = operation == "VERIFY_CASE_AUTHORITY" || operation == "VERIFY_COVERAGE" ||
                    operation == "VERIFY_CONCURRENT_INTERACTIONS" || operation == "FRAME_BOUNDARY" || operation == "RUN_PATH_PROBE" || operation == "RUN_DEPENDENCY_PROBE" ||
                    operation == "VERIFY_HISTORY" || operation == "VERIFY_TRACE" || operation == "VERIFY_DOCUMENT_CLAIM" || operation == "SUBMIT_EXTERNAL_INTERACTION" ||
                    operation == "RUN_SELF_UPGRADE_PROBE" || operation == "SUBMIT_SERVICE_STOP_EVIDENCE" || operation == "SUBMIT_TERMINAL_PROPOSAL" ||
                    operation == "SUBMIT_RUN_GRAPH" || operation == "SUBMIT_RECONCILIATION" || operation == "RETRY_REQUEST" || operation == "SIGNER_ONLY_OPERATION";
                if (auditRead) return;
                if (governedOuter) { RequireMeasuredCaller(caller, "ADVERSARIAL_HARNESS"); return; }
                throw new SecurityException("CALLER_NOT_AUTHORIZED");
            }
            if (sid == R7Fixed.SystemSid && publicRead) return;
            throw new SecurityException("CALLER_NOT_AUTHORIZED");
        }

        private void RequireMeasuredCaller(R7CallerIdentity caller, string role)
        {
            R7ComponentIdentity component = policy.Component(role);
            string installedFileIdentity;
            if (!activeUpgrade.InstalledFileIdentities.TryGetValue(role, out installedFileIdentity) ||
                !String.Equals(caller.ProcessPath, component.Path, StringComparison.Ordinal) ||
                !String.Equals(caller.ProcessSha256, component.Sha256, StringComparison.Ordinal) ||
                !String.Equals(caller.ProcessFileIdentity, installedFileIdentity, StringComparison.Ordinal) ||
                caller.ContainsTerminalSignerSid) throw new SecurityException("CALLER_EXECUTABLE_IDENTITY_MISMATCH");
        }

        private static SortedDictionary<string, object> CaptureRequest(SortedDictionary<string, object> capture)
        {
            byte[] frame = Convert.FromBase64String(R7Json.String(capture, "request_frame", 1, R7Fixed.MaximumEncodedCaptureChars));
            return R7Framing.Decode(frame);
        }

        private void RequireCaptureCaller(SortedDictionary<string, object> capture, string expectedSid, string role, string stage)
        {
            SortedDictionary<string, object> caller = R7Json.Child(capture, "caller");
            R7ComponentIdentity component = policy.Component(role);
            string installedFileIdentity;
            if (!activeUpgrade.InstalledFileIdentities.TryGetValue(role, out installedFileIdentity)) throw new R7ProtocolException("ACTIVATED_COMPONENT_FILE_IDENTITY_UNRESOLVED", stage);
            if (!String.Equals(R7Json.String(caller, "user_sid", 1, 256), expectedSid, StringComparison.Ordinal) ||
                R7Json.Boolean(caller, "contains_terminal_signer_sid") ||
                !String.Equals(R7Json.String(caller, "process_path", 3, 4096), component.Path, StringComparison.Ordinal) ||
                !R7Hash.FixedTimeEquals(R7Json.String(caller, "process_sha256", 64, 64), component.Sha256) ||
                !String.Equals(R7Json.String(caller, "process_file_identity", 1, 256), installedFileIdentity, StringComparison.Ordinal) ||
                R7Json.Integer(caller, "process_id", 1, Int64.MaxValue) <= 0 ||
                R7Json.String(caller, "token_id", 1, 128).Length == 0 ||
                R7Json.String(caller, "authentication_id", 1, 128).Length == 0) throw new R7ProtocolException("EVIDENCE_CALLER_IDENTITY_MISMATCH", stage);
        }

        private static bool ExpectedMatch(R7Expectation expectation, string status, string code)
        {
            if (expectation.ResponseClass == "COMPLETE") return status == "COMPLETE" && code == expectation.ResultCode;
            if (expectation.ResponseClass == "REJECTED") return status == "REJECTED" && code == expectation.ResultCode;
            if (expectation.ResponseClass == "UNAVAILABLE") return status == "UNAVAILABLE" && code == expectation.ResultCode;
            return false;
        }

        private static string BaseEvidenceRole(R7CaseDefinition definition)
        {
            if (definition.Driver == "PUBLIC_VERIFIER") return "PUBLIC_VERIFIER";
            if (definition.CaseId == "EXP-002" || definition.CaseId == "EXP-004") return "OBSERVATION";
            if (definition.CaseId == "PRI-002" || definition.CaseId == "SEM-007") return "COMPARATOR";
            if (definition.CaseId == "EXP-001" || definition.CaseId == "PRI-006" || definition.Driver == "SEMANTIC_PROBE" || definition.CaseId.StartsWith("SEM-", StringComparison.Ordinal) || definition.Driver == "ACL_PROBE" || definition.Driver == "TOKEN_PROBE" || definition.Driver == "SOURCE_PROBE" || definition.Driver == "RECOVERY_HARNESS") return "EXECUTION";
            return "ADVERSARIAL_HARNESS";
        }

        private static Dictionary<string, string> ResultMap(object[] rows)
        {
            Dictionary<string, string> result = new Dictionary<string, string>(StringComparer.Ordinal);
            foreach (object raw in rows)
            {
                SortedDictionary<string, object> row = RequireObject(raw);
                R7Json.ExactKeys(row, "case_id", "result_identity");
                string caseId = R7Json.String(row, "case_id", 1, 128);
                if (result.ContainsKey(caseId)) throw new R7ProtocolException("DUPLICATE_CASE_RESULT");
                result.Add(caseId, R7Json.String(row, "result_identity", 64, 64));
            }
            return result;
        }

        private static bool JsonScalarEqual(object left, object right)
        {
            if (left == null || right == null) return left == right;
            if (left.GetType() != right.GetType()) return false;
            return Object.Equals(left, right);
        }

        private static void ValidateConfiguration(SortedDictionary<string, object> configuration)
        {
            R7Json.ExactKeys(configuration, "autocrlf", "checkout_length");
            string autocrlf = R7Json.String(configuration, "autocrlf", 4, 5);
            string length = R7Json.String(configuration, "checkout_length", 4, 5);
            if ((autocrlf != "true" && autocrlf != "false") || (length != "short" && length != "long")) throw new R7ProtocolException("MATRIX_CONFIGURATION_INVALID");
        }

        private static string Sha(IDictionary<string, object> value, string name)
        {
            string result = R7Json.String(value, name, 64, 64);
            if (!R7Hash.IsLowerSha256(result)) throw new R7ProtocolException("SHA256_FORMAT", name);
            return result;
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

        private static string NormalizeError(string code)
        {
            if (code == "TRAILING_JSON" || code == "MULTIPLE_FRAMES_OR_TRAILING_BYTES") return code == "TRAILING_JSON" ? "TRAILING_BYTES" : "MULTIPLE_FRAMES";
            if (code == "PARTIAL_FRAME") return "INCOMPLETE_FRAME";
            return code;
        }
    }

    internal sealed class R7GraphEvaluation
    {
        internal int CaseCount;
        internal bool CompleteForRun;
        internal string EvidenceIdentity;
        internal bool Passed;
    }

    internal sealed class R7ReconciliationEvaluation
    {
        internal bool Matched;
        internal int ComparedCaseCount;
        internal bool ComplementaryMetaCasesVerified;
    }

    internal static class R7TerminalServiceProgram
    {
        private static void Main()
        {
            R7RuntimeBoundary.Enforce(R7Fixed.TerminalInstallRoot);
            ServiceBase.Run(new R7PipeWindowsService(
                R7Fixed.TerminalService,
                R7Fixed.TerminalPipe,
                new string[] { R7Fixed.OperatorSid, R7Fixed.SystemSid, R7Fixed.ExecutionSid, R7Fixed.ObservationSid, R7Fixed.ComparatorSid },
                delegate() { return new R7TerminalProcessor(); }));
        }
    }
}
