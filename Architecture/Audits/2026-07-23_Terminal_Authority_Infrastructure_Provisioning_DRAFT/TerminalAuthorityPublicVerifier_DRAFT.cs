using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using Microsoft.Win32;

namespace RandleAI.TerminalAuthority
{
    internal sealed class LedgerVerification
    {
        internal long Sequence;
        internal string RootHash;
        internal string GenesisIdentity;
        internal string CheckpointIdentity;
        internal bool AttestationResolved;
    }

    internal static class PublicVerifier
    {
        private static int Main(string[] args)
        {
            try
            {
                string command = args.Length == 0 ? "verify-all" : args[0];
                string attestationPath = args.Length > 1 ? args[1] : AuthorityConstants.AttestationPath;
                string certificatePath = args.Length > 2 ? args[2] : AuthorityConstants.PublicCertificatePath;
                string ledgerRoot = args.Length > 3 ? args[3] : AuthorityConstants.LedgerRoot;

                X509Certificate2 certificate = new X509Certificate2(certificatePath);
                string certificateIdentity = CryptoUtil.Sha256Hex(certificate.Export(X509ContentType.Cert));
                if (!String.Equals(certificateIdentity, AuthorityConstants.PublicCertificateSha256, StringComparison.Ordinal)) throw new CryptographicException("UNTRUSTED_PUBLIC_KEY");
                RSA verifier = System.Security.Cryptography.X509Certificates.RSACertificateExtensions.GetRSAPublicKey(certificate);
                if (verifier == null || verifier.KeySize != 3072) throw new CryptographicException("PUBLIC_KEY_INVALID");

                SortedDictionary<string, object> result = new SortedDictionary<string, object>(StringComparer.Ordinal);
                result["interface_version"] = AuthorityConstants.InterfaceVersion;
                result["public_key_identity"] = certificateIdentity;

                if (command == "verify-envelope")
                {
                    ParseAndVerifyEnvelope(File.ReadAllBytes(attestationPath), verifier);
                    result["envelope_identity"] = CryptoUtil.Sha256File(attestationPath);
                    result["envelope_status"] = "VERIFIED";
                }
                if (command == "verify-attestation" || command == "verify-all")
                {
                    string attestationIdentity = VerifyAttestation(attestationPath, verifier);
                    result["attestation_identity"] = attestationIdentity;
                    result["attestation_status"] = "VERIFIED";
                }
                if (command == "verify-host" || command == "verify-all")
                {
                    VerifyHost(attestationPath, verifier);
                    result["host_status"] = "VERIFIED";
                    result["service_binary_sha256"] = CryptoUtil.Sha256File(AuthorityConstants.ExecutablePath);
                    result["policy_sha256"] = CryptoUtil.Sha256File(AuthorityConstants.PolicyPath);
                }
                if (command == "verify-ledger" || command == "verify-all")
                {
                    string requiredAttestation = File.Exists(attestationPath) ? CryptoUtil.Sha256File(attestationPath) : String.Empty;
                    LedgerVerification ledger = VerifyLedger(ledgerRoot, verifier, requiredAttestation);
                    result["checkpoint_identity"] = ledger.CheckpointIdentity;
                    result["genesis_identity"] = ledger.GenesisIdentity;
                    result["ledger_root_hash"] = ledger.RootHash;
                    result["ledger_sequence"] = ledger.Sequence;
                    result["ledger_status"] = "VERIFIED";
                    result["provisioning_attestation_resolved"] = ledger.AttestationResolved;
                    if (command == "verify-all" && !ledger.AttestationResolved) throw new InvalidDataException("ATTESTATION_LEDGER_ENTRY_MISSING");
                }
                if (command != "verify-envelope" && command != "verify-attestation" && command != "verify-host" && command != "verify-ledger" && command != "verify-all") throw new InvalidDataException("UNKNOWN_VERIFICATION_OPERATION");

                result["status"] = "VERIFIED";
                Console.Out.WriteLine(CanonicalJson.Serialize(result));
                verifier.Dispose();
                certificate.Dispose();
                return 0;
            }
            catch (Exception exception)
            {
                SortedDictionary<string, object> failure = new SortedDictionary<string, object>(StringComparer.Ordinal);
                failure["error_code"] = exception.Message;
                failure["exception_type"] = exception.GetType().Name;
                failure["interface_version"] = AuthorityConstants.InterfaceVersion;
                failure["status"] = "REJECTED";
                Console.Out.WriteLine(CanonicalJson.Serialize(failure));
                return 2;
            }
        }

        private static string VerifyAttestation(string path, RSA verifier)
        {
            byte[] bytes = File.ReadAllBytes(path);
            IDictionary<string, object> envelope = ParseAndVerifyEnvelope(bytes, verifier);
            IDictionary<string, object> payload = StrictJson.RequireObject(envelope, "payload");
            StrictJson.RequireExactKeys(payload,
                "acl_identities", "architecture_base_commit", "attestation_schema_version", "certificate_der_sha256",
                "certificate_issuer", "certificate_not_after", "certificate_not_before", "certificate_serial_number",
                "certificate_subject", "certificate_thumbprint", "executable_file_identity", "executable_path",
                "executable_sha256", "fixed_host_paths", "incomplete_result_commit", "interface_version", "ipc_identity",
                "issue_time", "key_algorithm", "key_container_unique_name", "key_export_policy", "key_provider", "key_size",
                "ledger_checkpoint_identity", "ledger_genesis_identity", "ledger_id", "policy_sha256",
                "private_key_present_in_repository", "provisioning_nonce", "provisioning_nonce_identity",
                "provisioning_task_identity", "public_key_identity", "r7_blocker_commit", "repository_write_access", "service_account",
                "service_configuration_identity", "service_name", "service_sid", "service_sid_type", "threat_model");
            Require(payload, "architecture_base_commit", AuthorityConstants.BaseCommit);
            Require(payload, "incomplete_result_commit", AuthorityConstants.IncompleteCommit);
            Require(payload, "r7_blocker_commit", AuthorityConstants.BlockerCommit);
            Require(payload, "certificate_der_sha256", AuthorityConstants.PublicCertificateSha256);
            Require(payload, "certificate_thumbprint", AuthorityConstants.CertificateThumbprint);
            Require(payload, "executable_path", AuthorityConstants.ExecutablePath);
            Require(payload, "interface_version", AuthorityConstants.InterfaceVersion);
            Require(payload, "key_algorithm", AuthorityConstants.SignatureAlgorithm);
            Require(payload, "key_container_unique_name", AuthorityConstants.KeyUniqueName);
            Require(payload, "key_export_policy", "NONEXPORTABLE");
            Require(payload, "ledger_id", AuthorityConstants.LedgerId);
            Require(payload, "policy_sha256", AuthorityConstants.PolicySha256);
            Require(payload, "public_key_identity", AuthorityConstants.PublicCertificateSha256);
            Require(payload, "service_account", AuthorityConstants.ServiceAccount);
            Require(payload, "service_name", AuthorityConstants.ServiceName);
            Require(payload, "service_sid", AuthorityConstants.ServiceSid);
            Require(payload, "service_sid_type", "RESTRICTED");
            Require(payload, "threat_model", AuthorityConstants.ThreatModel);
            object privateInRepository;
            if (!payload.TryGetValue("private_key_present_in_repository", out privateInRepository) || !(privateInRepository is bool) || (bool)privateInRepository) throw new InvalidDataException("PRIVATE_AUTHORITY_BOUNDARY_INVALID");
            object repositoryWrite;
            if (!payload.TryGetValue("repository_write_access", out repositoryWrite) || !(repositoryWrite is bool) || (bool)repositoryWrite) throw new InvalidDataException("REPOSITORY_WRITE_BOUNDARY_INVALID");
            string nonce = StrictJson.RequireString(payload, "provisioning_nonce");
            string nonceIdentity = CryptoUtil.Sha256Hex(Encoding.UTF8.GetBytes(nonce));
            Require(payload, "provisioning_nonce_identity", nonceIdentity);
            return CryptoUtil.Sha256Hex(bytes);
        }

        private static void VerifyHost(string attestationPath, RSA verifier)
        {
            IDictionary<string, object> envelope = ParseAndVerifyEnvelope(File.ReadAllBytes(attestationPath), verifier);
            IDictionary<string, object> payload = StrictJson.RequireObject(envelope, "payload");
            Require(payload, "executable_path", AuthorityConstants.ExecutablePath);
            Require(payload, "executable_sha256", CryptoUtil.Sha256File(AuthorityConstants.ExecutablePath));
            Require(payload, "policy_sha256", CryptoUtil.Sha256File(AuthorityConstants.PolicyPath));
            Require(payload, "certificate_der_sha256", CryptoUtil.Sha256File(AuthorityConstants.PublicCertificatePath));
            Require(payload, "service_configuration_identity", CurrentServiceConfigurationIdentity());
        }

        private static string CurrentServiceConfigurationIdentity()
        {
            using (RegistryKey key = Registry.LocalMachine.OpenSubKey(@"SYSTEM\CurrentControlSet\Services\RandleTerminalAuthority", false))
            {
                if (key == null) throw new InvalidDataException("SERVICE_CONFIGURATION_MISSING");
                SortedDictionary<string, object> config = new SortedDictionary<string, object>(StringComparer.Ordinal);
                config["image_path"] = Convert.ToString(key.GetValue("ImagePath"), CultureInfo.InvariantCulture);
                config["object_name"] = Convert.ToString(key.GetValue("ObjectName"), CultureInfo.InvariantCulture);
                config["service_sid_type"] = Convert.ToInt64(key.GetValue("ServiceSidType", 0), CultureInfo.InvariantCulture);
                config["start"] = Convert.ToInt64(key.GetValue("Start", 0), CultureInfo.InvariantCulture);
                config["type"] = Convert.ToInt64(key.GetValue("Type", 0), CultureInfo.InvariantCulture);
                return CryptoUtil.Sha256Hex(CanonicalJson.SerializeBytes(config));
            }
        }

        private static LedgerVerification VerifyLedger(string root, RSA verifier, string requiredAttestationIdentity)
        {
            string canonicalRoot = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar);
            if (!String.Equals(canonicalRoot, AuthorityConstants.LedgerRoot, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("LEDGER_ROOT_REJECTED");
            string[] paths = Directory.GetFiles(canonicalRoot, "*.entry.json", SearchOption.TopDirectoryOnly);
            Array.Sort(paths, StringComparer.Ordinal);
            if (paths.Length < 3) throw new InvalidDataException("LEDGER_ENTRY_COUNT_INSUFFICIENT");
            long expectedSequence = 1;
            string expectedPrior = AuthorityConstants.ZeroHash;
            string genesis = null;
            bool resolved = false;
            foreach (string path in paths)
            {
                byte[] bytes = File.ReadAllBytes(path);
                IDictionary<string, object> envelope = ParseAndVerifyEnvelope(bytes, verifier);
                IDictionary<string, object> payload = StrictJson.RequireObject(envelope, "payload");
                StrictJson.RequireExactKeys(payload, "content_address", "entry_hash", "issue_time", "ledger_id", "operation", "prior_entry_hash", "public_key_identity", "request_nonce", "schema_version", "sequence", "service_sid", "subject_id");
                long sequence = Convert.ToInt64(payload["sequence"], CultureInfo.InvariantCulture);
                if (sequence != expectedSequence) throw new InvalidDataException("LEDGER_SEQUENCE_INVALID");
                Require(payload, "ledger_id", AuthorityConstants.LedgerId);
                Require(payload, "prior_entry_hash", expectedPrior);
                Require(payload, "public_key_identity", AuthorityConstants.PublicCertificateSha256);
                Require(payload, "service_sid", AuthorityConstants.ServiceSid);
                SortedDictionary<string, object> core = new SortedDictionary<string, object>(payload, StringComparer.Ordinal);
                string recorded = StrictJson.RequireString(core, "entry_hash");
                core.Remove("entry_hash");
                string computed = CryptoUtil.Sha256Hex(CanonicalJson.SerializeBytes(core));
                if (!String.Equals(recorded, computed, StringComparison.Ordinal)) throw new InvalidDataException("LEDGER_ENTRY_HASH_INVALID");
                if (sequence == 1)
                {
                    Require(payload, "operation", "LEDGER_GENESIS");
                    genesis = recorded;
                }
                if (String.Equals(StrictJson.RequireString(payload, "operation"), "PROVISIONING_ATTESTATION_ISSUED", StringComparison.Ordinal) &&
                    String.Equals(StrictJson.RequireString(payload, "content_address"), requiredAttestationIdentity, StringComparison.Ordinal)) resolved = true;
                expectedPrior = recorded;
                expectedSequence++;
            }

            string checkpointPath = Path.Combine(canonicalRoot, "checkpoint.json");
            byte[] checkpointBytes = File.ReadAllBytes(checkpointPath);
            IDictionary<string, object> checkpointEnvelope = ParseAndVerifyEnvelope(checkpointBytes, verifier);
            IDictionary<string, object> checkpoint = StrictJson.RequireObject(checkpointEnvelope, "payload");
            StrictJson.RequireExactKeys(checkpoint, "issue_time", "ledger_id", "public_key_identity", "root_hash", "schema_version", "sequence", "service_sid");
            if (Convert.ToInt64(checkpoint["sequence"], CultureInfo.InvariantCulture) != expectedSequence - 1) throw new InvalidDataException("CHECKPOINT_SEQUENCE_INVALID");
            Require(checkpoint, "ledger_id", AuthorityConstants.LedgerId);
            Require(checkpoint, "root_hash", expectedPrior);
            Require(checkpoint, "public_key_identity", AuthorityConstants.PublicCertificateSha256);
            Require(checkpoint, "service_sid", AuthorityConstants.ServiceSid);
            return new LedgerVerification
            {
                Sequence = expectedSequence - 1,
                RootHash = expectedPrior,
                GenesisIdentity = genesis,
                CheckpointIdentity = CryptoUtil.Sha256Hex(checkpointBytes),
                AttestationResolved = resolved
            };
        }

        private static IDictionary<string, object> ParseAndVerifyEnvelope(byte[] bytes, RSA verifier)
        {
            string text = new UTF8Encoding(false, true).GetString(bytes);
            IDictionary<string, object> envelope = StrictJson.ParseObject(text);
            StrictJson.RequireExactKeys(envelope, "payload", "public_key_identity", "signature", "signature_algorithm");
            Require(envelope, "public_key_identity", AuthorityConstants.PublicCertificateSha256);
            Require(envelope, "signature_algorithm", AuthorityConstants.SignatureAlgorithm);
            IDictionary<string, object> payload = StrictJson.RequireObject(envelope, "payload");
            byte[] signature = Convert.FromBase64String(StrictJson.RequireString(envelope, "signature"));
            if (!CryptoUtil.Verify(verifier, CanonicalJson.SerializeBytes(payload), signature)) throw new CryptographicException("SIGNATURE_INVALID");
            if (!String.Equals(CanonicalJson.Serialize(envelope), text, StringComparison.Ordinal)) throw new InvalidDataException("NONCANONICAL_RECEIPT");
            return envelope;
        }

        private static void Require(IDictionary<string, object> value, string key, string expected)
        {
            string actual = StrictJson.RequireString(value, key);
            if (!String.Equals(actual, expected, StringComparison.Ordinal)) throw new InvalidDataException(key.ToUpperInvariant() + "_MISMATCH");
        }
    }
}
