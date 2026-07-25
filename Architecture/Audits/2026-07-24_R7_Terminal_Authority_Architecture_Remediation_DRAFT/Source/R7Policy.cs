using System;
using System.Collections.Generic;
using System.IO;

namespace RandleAI.R7Remediation
{
    internal sealed class R7ComponentIdentity
    {
        internal string Role;
        internal string Path;
        internal string Sha256;
    }

    internal sealed class R7TerminalPolicy
    {
        internal string PolicySha256;
        internal string SourceCommit;
        internal string SourceTree;
        internal string VolumeIdentity;
        internal string DependencyManifestSha256;
        internal string BuildReceiptSha256;
        internal string UpgradePublicCertificateSha256;
        internal string[] FixedRoots;
        internal string[] RevokedComponentHashes;
        internal R7AuthorityIdentities AuthorityIdentities;
        internal Dictionary<string, R7ComponentIdentity> Components;
        internal Dictionary<string, string> CallerRoleSids;
        internal SortedDictionary<string, object> Raw;

        internal static R7TerminalPolicy Load(string expectedSha256)
        {
            using (R7VerifiedFile file = R7SafeFile.Open(R7Fixed.TerminalPolicyPath, R7Fixed.TerminalPolicyPath, Path.GetDirectoryName(R7Fixed.TerminalPolicyPath), expectedSha256, R7Fixed.SystemSid, null, null))
            {
                SortedDictionary<string, object> raw = RequireObject(R7Json.Parse(file.Bytes));
                R7Json.ExactKeys(raw,
                    "artifact_type", "authority_identities", "build_receipt_sha256", "caller_role_sids", "component_identities",
                    "dependency_manifest_sha256", "fixed_roots", "historical_classification_policy", "interface_version", "ledger_id",
                    "maximum_frame_bytes", "maximum_payload_bytes", "protocol_version", "revoked_component_sha256", "schema_version", "source_commit", "source_tree",
                    "terminal_public_key_identity", "terminal_service_sid", "threat_model", "upgrade_public_certificate_sha256", "volume_identity");
                if (!String.Equals(R7Json.String(raw, "artifact_type", 1, 256), "R7_TERMINAL_AUTHORITY_REMEDIATION_POLICY", StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(raw, "interface_version", 1, 128), R7Fixed.InterfaceVersion, StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(raw, "protocol_version", 1, 64), R7Fixed.ProtocolVersion, StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(raw, "ledger_id", 64, 64), R7Fixed.LedgerId, StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(raw, "terminal_public_key_identity", 64, 64), R7Fixed.TerminalPublicKeyIdentity, StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(raw, "terminal_service_sid", 1, 256), R7Fixed.TerminalSid, StringComparison.Ordinal) ||
                    R7Json.Integer(raw, "maximum_frame_bytes", R7Fixed.MaximumFrameBytes, R7Fixed.MaximumFrameBytes) != R7Fixed.MaximumFrameBytes ||
                    R7Json.Integer(raw, "maximum_payload_bytes", R7Fixed.MaximumPayloadBytes, R7Fixed.MaximumPayloadBytes) != R7Fixed.MaximumPayloadBytes) throw new R7ProtocolException("TERMINAL_POLICY_IDENTITY");
                R7Json.ExactKeys(R7Json.Child(raw, "historical_classification_policy"), "default_rejected_v3_class", "retained_history_start_sequence", "sequence_332_class", "sequence_678_class");

                SortedDictionary<string, object> authority = R7Json.Child(raw, "authority_identities");
                R7Json.ExactKeys(authority, "case_definitions_sha256", "coverage_proof_sha256", "expectations_sha256", "requirement_registry_sha256", "source_manifest_sha256");
                R7AuthorityIdentities authorityIdentities = new R7AuthorityIdentities(
                    Sha(authority, "requirement_registry_sha256"),
                    Sha(authority, "case_definitions_sha256"),
                    Sha(authority, "expectations_sha256"),
                    Sha(authority, "coverage_proof_sha256"),
                    Sha(authority, "source_manifest_sha256"));

                Dictionary<string, R7ComponentIdentity> components = new Dictionary<string, R7ComponentIdentity>(StringComparer.Ordinal);
                object[] componentRows = R7Json.Array(raw, "component_identities");
                foreach (object item in componentRows)
                {
                    SortedDictionary<string, object> row = RequireObject(item);
                    R7Json.ExactKeys(row, "path", "role", "sha256");
                    R7ComponentIdentity component = new R7ComponentIdentity
                    {
                        Role = R7Json.String(row, "role", 1, 128),
                        Path = R7Json.String(row, "path", 3, 4096),
                        Sha256 = Sha(row, "sha256")
                    };
                    if (components.ContainsKey(component.Role)) throw new R7ProtocolException("DUPLICATE_COMPONENT_ROLE");
                    components.Add(component.Role, component);
                }
                foreach (string role in new string[] { "TERMINAL_SIGNER", "EXECUTION", "OBSERVATION", "COMPARATOR", "PUBLIC_VERIFIER", "AUTHORITY_VERIFIER", "ADVERSARIAL_HARNESS", "STATIC_VERIFIER" }) if (!components.ContainsKey(role)) throw new R7ProtocolException("MISSING_COMPONENT_ROLE", role);

                SortedDictionary<string, object> callerRows = R7Json.Child(raw, "caller_role_sids");
                R7Json.ExactKeys(callerRows, "COMPARATOR", "EXECUTION", "OBSERVATION", "OPERATOR", "SYSTEM", "TERMINAL_SIGNER", "UPGRADE_AUTHORITY");
                Dictionary<string, string> callerSids = new Dictionary<string, string>(StringComparer.Ordinal);
                foreach (KeyValuePair<string, object> item in callerRows)
                {
                    string sid = item.Value as string;
                    if (sid == null) throw new R7ProtocolException("CALLER_SID_TYPE");
                    callerSids.Add(item.Key, sid);
                }
                if (callerSids["TERMINAL_SIGNER"] != R7Fixed.TerminalSid || callerSids["EXECUTION"] != R7Fixed.ExecutionSid || callerSids["OBSERVATION"] != R7Fixed.ObservationSid || callerSids["COMPARATOR"] != R7Fixed.ComparatorSid || callerSids["UPGRADE_AUTHORITY"] != R7Fixed.UpgradeSid || callerSids["OPERATOR"] != R7Fixed.OperatorSid || callerSids["SYSTEM"] != R7Fixed.SystemSid) throw new R7ProtocolException("CALLER_SID_IDENTITY");

                string[] roots = Strings(R7Json.Array(raw, "fixed_roots"));
                foreach (string required in new string[] { R7Fixed.TerminalInstallRoot, R7Fixed.RemediationRoot, R7Fixed.LedgerRoot, R7Fixed.UpgradeStateRoot }) if (Array.IndexOf(roots, required) < 0) throw new R7ProtocolException("FIXED_ROOT_MISSING", required);
                string[] revoked = Strings(R7Json.Array(raw, "revoked_component_sha256"));
                foreach (string hash in revoked) if (!R7Hash.IsLowerSha256(hash)) throw new R7ProtocolException("REVOKED_HASH_INVALID");
                foreach (R7ComponentIdentity component in components.Values) if (Array.IndexOf(revoked, component.Sha256) >= 0) throw new R7ProtocolException("ACTIVE_COMPONENT_REVOKED", component.Role);

                R7TerminalPolicy policy = new R7TerminalPolicy
                {
                    PolicySha256 = file.Measurement.Sha256,
                    SourceCommit = R7Json.String(raw, "source_commit", 40, 40),
                    SourceTree = R7Json.String(raw, "source_tree", 40, 40),
                    VolumeIdentity = R7Json.String(raw, "volume_identity", 8, 64),
                    DependencyManifestSha256 = Sha(raw, "dependency_manifest_sha256"),
                    BuildReceiptSha256 = Sha(raw, "build_receipt_sha256"),
                    UpgradePublicCertificateSha256 = Sha(raw, "upgrade_public_certificate_sha256"),
                    FixedRoots = roots,
                    RevokedComponentHashes = revoked,
                    AuthorityIdentities = authorityIdentities,
                    Components = components,
                    CallerRoleSids = callerSids,
                    Raw = raw
                };
                return policy;
            }
        }

        internal R7ComponentIdentity Component(string role)
        {
            R7ComponentIdentity value;
            if (!Components.TryGetValue(role, out value)) throw new R7ProtocolException("COMPONENT_ROLE_UNRESOLVED", role);
            return value;
        }

        private static string Sha(IDictionary<string, object> row, string name)
        {
            string value = R7Json.String(row, name, 64, 64);
            if (!R7Hash.IsLowerSha256(value)) throw new R7ProtocolException("SHA256_FORMAT", name);
            return value;
        }

        private static SortedDictionary<string, object> RequireObject(object value)
        {
            SortedDictionary<string, object> result = value as SortedDictionary<string, object>;
            if (result == null) throw new R7ProtocolException("OBJECT_REQUIRED");
            return result;
        }

        private static string[] Strings(object[] values)
        {
            string[] result = new string[values.Length];
            for (int i = 0; i < values.Length; i++)
            {
                result[i] = values[i] as string;
                if (result[i] == null) throw new R7ProtocolException("STRING_ARRAY_REQUIRED");
            }
            return result;
        }
    }
}
