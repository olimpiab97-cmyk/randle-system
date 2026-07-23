using Microsoft.Win32;
using Microsoft.Win32.SafeHandles;
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.IO.Pipes;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Security.Principal;
using System.ServiceProcess;
using System.Text;
using System.Threading;

namespace RandleAI.TerminalAuthority
{
    internal sealed class LedgerAppendResult
    {
        internal long Sequence;
        internal string EntryHash;
        internal string EntryIdentity;
        internal string CheckpointIdentity;
        internal string EntryPath;
    }

    internal sealed class DurableLedger
    {
        private readonly object sync = new object();
        private readonly RSA signer;
        private readonly RSA verifier;
        private long sequence;
        private string rootHash;
        private string genesisIdentity;
        private readonly List<IDictionary<string, object>> payloads = new List<IDictionary<string, object>>();

        internal DurableLedger(RSA signer, RSA verifier)
        {
            this.signer = signer;
            this.verifier = verifier;
            this.sequence = 0;
            this.rootHash = AuthorityConstants.ZeroHash;
            ValidateOrCreate();
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
                    string path = Path.Combine(AuthorityConstants.LedgerRoot, "checkpoint.json");
                    return File.Exists(path) ? CryptoUtil.Sha256File(path) : AuthorityConstants.ZeroHash;
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
            lock (sync)
            {
                foreach (IDictionary<string, object> payload in payloads)
                {
                    object op;
                    object subject;
                    if (payload.TryGetValue("operation", out op) && payload.TryGetValue("subject_id", out subject) &&
                        String.Equals(op as string, operation, StringComparison.Ordinal) &&
                        String.Equals(subject as string, subjectId, StringComparison.Ordinal)) return true;
                }
                return false;
            }
        }

        internal LedgerAppendResult Append(string operation, string requestNonce, string subjectId, string contentAddress)
        {
            lock (sync)
            {
                if (!String.IsNullOrEmpty(requestNonce) && ContainsRequestNonce(requestNonce))
                    throw new InvalidOperationException("REQUEST_NONCE_REPLAY");

                long next = checked(sequence + 1);
                SortedDictionary<string, object> core = new SortedDictionary<string, object>(StringComparer.Ordinal);
                core["content_address"] = contentAddress;
                core["issue_time"] = DateTimeOffset.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture);
                core["ledger_id"] = AuthorityConstants.LedgerId;
                core["operation"] = operation;
                core["prior_entry_hash"] = rootHash;
                core["public_key_identity"] = AuthorityConstants.PublicCertificateSha256;
                core["request_nonce"] = requestNonce ?? String.Empty;
                core["schema_version"] = AuthorityConstants.SchemaVersion;
                core["sequence"] = next;
                core["service_sid"] = AuthorityConstants.ServiceSid;
                core["subject_id"] = subjectId ?? String.Empty;
                string entryHash = CryptoUtil.Sha256Hex(CanonicalJson.SerializeBytes(core));

                SortedDictionary<string, object> payload = new SortedDictionary<string, object>(core, StringComparer.Ordinal);
                payload["entry_hash"] = entryHash;
                byte[] canonicalPayload = CanonicalJson.SerializeBytes(payload);
                byte[] signature = CryptoUtil.Sign(signer, canonicalPayload);
                SortedDictionary<string, object> envelope = new SortedDictionary<string, object>(StringComparer.Ordinal);
                envelope["payload"] = payload;
                envelope["public_key_identity"] = AuthorityConstants.PublicCertificateSha256;
                envelope["signature"] = Convert.ToBase64String(signature);
                envelope["signature_algorithm"] = AuthorityConstants.SignatureAlgorithm;
                byte[] envelopeBytes = CanonicalJson.SerializeBytes(envelope);

                string entryPath = Path.Combine(AuthorityConstants.LedgerRoot, next.ToString("D20", CultureInfo.InvariantCulture) + ".entry.json");
                DurableCreate(entryPath, envelopeBytes);

                sequence = next;
                rootHash = entryHash;
                payloads.Add(payload);
                if (next == 1) genesisIdentity = entryHash;
                string checkpointIdentity = WriteCheckpoint();

                return new LedgerAppendResult
                {
                    Sequence = next,
                    EntryHash = entryHash,
                    EntryIdentity = CryptoUtil.Sha256Hex(envelopeBytes),
                    CheckpointIdentity = checkpointIdentity,
                    EntryPath = entryPath
                };
            }
        }

        private void ValidateOrCreate()
        {
            lock (sync)
            {
                Directory.CreateDirectory(AuthorityConstants.LedgerRoot);
                string[] paths = Directory.GetFiles(AuthorityConstants.LedgerRoot, "*.entry.json", SearchOption.TopDirectoryOnly);
                Array.Sort(paths, StringComparer.Ordinal);
                if (paths.Length == 0)
                {
                    if (File.Exists(Path.Combine(AuthorityConstants.LedgerRoot, "checkpoint.json")))
                        throw new InvalidDataException("checkpoint exists without ledger entries");
                    string genesisContent = CryptoUtil.Sha256Hex(Encoding.UTF8.GetBytes(
                        AuthorityConstants.PublicCertificateSha256 + "|" + AuthorityConstants.PolicySha256 + "|" + AuthorityConstants.LedgerId));
                    Append("LEDGER_GENESIS", String.Empty, AuthorityConstants.LedgerId, genesisContent);
                    return;
                }

                long expectedSequence = 1;
                string expectedPrior = AuthorityConstants.ZeroHash;
                foreach (string path in paths)
                {
                    IDictionary<string, object> payload = VerifyEnvelope(File.ReadAllBytes(path));
                    StrictJson.RequireExactKeys(payload, "content_address", "entry_hash", "issue_time", "ledger_id", "operation", "prior_entry_hash", "public_key_identity", "request_nonce", "schema_version", "sequence", "service_sid", "subject_id");
                    long actualSequence = Convert.ToInt64(payload["sequence"], CultureInfo.InvariantCulture);
                    if (actualSequence != expectedSequence) throw new InvalidDataException("ledger sequence gap");
                    if (!String.Equals(StrictJson.RequireString(payload, "ledger_id"), AuthorityConstants.LedgerId, StringComparison.Ordinal)) throw new InvalidDataException("ledger identity mismatch");
                    if (!String.Equals(StrictJson.RequireString(payload, "prior_entry_hash"), expectedPrior, StringComparison.Ordinal)) throw new InvalidDataException("ledger prior hash mismatch");
                    if (!String.Equals(StrictJson.RequireString(payload, "public_key_identity"), AuthorityConstants.PublicCertificateSha256, StringComparison.Ordinal)) throw new InvalidDataException("ledger key mismatch");
                    if (!String.Equals(StrictJson.RequireString(payload, "service_sid"), AuthorityConstants.ServiceSid, StringComparison.Ordinal)) throw new InvalidDataException("ledger service mismatch");

                    SortedDictionary<string, object> core = new SortedDictionary<string, object>(payload, StringComparer.Ordinal);
                    string recordedHash = StrictJson.RequireString(core, "entry_hash");
                    core.Remove("entry_hash");
                    string computedHash = CryptoUtil.Sha256Hex(CanonicalJson.SerializeBytes(core));
                    if (!String.Equals(recordedHash, computedHash, StringComparison.Ordinal)) throw new InvalidDataException("ledger entry hash mismatch");
                    if (expectedSequence == 1)
                    {
                        string expectedGenesisContent = CryptoUtil.Sha256Hex(Encoding.UTF8.GetBytes(
                            AuthorityConstants.PublicCertificateSha256 + "|" + AuthorityConstants.PolicySha256 + "|" + AuthorityConstants.LedgerId));
                        if (!String.Equals(StrictJson.RequireString(payload, "operation"), "LEDGER_GENESIS", StringComparison.Ordinal) ||
                            !String.Equals(StrictJson.RequireString(payload, "content_address"), expectedGenesisContent, StringComparison.Ordinal))
                            throw new InvalidDataException("ledger genesis authority mismatch");
                    }
                    expectedPrior = recordedHash;
                    payloads.Add(payload);
                    if (expectedSequence == 1) genesisIdentity = recordedHash;
                    expectedSequence++;
                }
                sequence = expectedSequence - 1;
                rootHash = expectedPrior;
                ValidateCheckpoint();
            }
        }

        private IDictionary<string, object> VerifyEnvelope(byte[] bytes)
        {
            IDictionary<string, object> envelope = StrictJson.ParseObject(new UTF8Encoding(false, true).GetString(bytes));
            StrictJson.RequireExactKeys(envelope, "payload", "public_key_identity", "signature", "signature_algorithm");
            if (!String.Equals(StrictJson.RequireString(envelope, "public_key_identity"), AuthorityConstants.PublicCertificateSha256, StringComparison.Ordinal)) throw new InvalidDataException("envelope key mismatch");
            if (!String.Equals(StrictJson.RequireString(envelope, "signature_algorithm"), AuthorityConstants.SignatureAlgorithm, StringComparison.Ordinal)) throw new InvalidDataException("envelope algorithm mismatch");
            IDictionary<string, object> payload = StrictJson.RequireObject(envelope, "payload");
            byte[] signature = Convert.FromBase64String(StrictJson.RequireString(envelope, "signature"));
            if (!CryptoUtil.Verify(verifier, CanonicalJson.SerializeBytes(payload), signature)) throw new CryptographicException("ledger signature invalid");
            if (!String.Equals(CanonicalJson.Serialize(envelope), new UTF8Encoding(false, true).GetString(bytes), StringComparison.Ordinal)) throw new InvalidDataException("ledger envelope is not canonical");
            return payload;
        }

        private string WriteCheckpoint()
        {
            SortedDictionary<string, object> payload = new SortedDictionary<string, object>(StringComparer.Ordinal);
            payload["issue_time"] = DateTimeOffset.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture);
            payload["ledger_id"] = AuthorityConstants.LedgerId;
            payload["public_key_identity"] = AuthorityConstants.PublicCertificateSha256;
            payload["root_hash"] = rootHash;
            payload["schema_version"] = AuthorityConstants.SchemaVersion;
            payload["sequence"] = sequence;
            payload["service_sid"] = AuthorityConstants.ServiceSid;
            byte[] signature = CryptoUtil.Sign(signer, CanonicalJson.SerializeBytes(payload));
            SortedDictionary<string, object> envelope = new SortedDictionary<string, object>(StringComparer.Ordinal);
            envelope["payload"] = payload;
            envelope["public_key_identity"] = AuthorityConstants.PublicCertificateSha256;
            envelope["signature"] = Convert.ToBase64String(signature);
            envelope["signature_algorithm"] = AuthorityConstants.SignatureAlgorithm;
            byte[] bytes = CanonicalJson.SerializeBytes(envelope);
            DurableReplace(Path.Combine(AuthorityConstants.LedgerRoot, "checkpoint.json"), bytes);
            return CryptoUtil.Sha256Hex(bytes);
        }

        private void ValidateCheckpoint()
        {
            string path = Path.Combine(AuthorityConstants.LedgerRoot, "checkpoint.json");
            if (!File.Exists(path)) throw new InvalidDataException("ledger checkpoint missing");
            IDictionary<string, object> payload = VerifyEnvelope(File.ReadAllBytes(path));
            StrictJson.RequireExactKeys(payload, "issue_time", "ledger_id", "public_key_identity", "root_hash", "schema_version", "sequence", "service_sid");
            if (Convert.ToInt64(payload["sequence"], CultureInfo.InvariantCulture) != sequence) throw new InvalidDataException("checkpoint sequence mismatch");
            if (!String.Equals(StrictJson.RequireString(payload, "root_hash"), rootHash, StringComparison.Ordinal)) throw new InvalidDataException("checkpoint root mismatch");
            if (!String.Equals(StrictJson.RequireString(payload, "ledger_id"), AuthorityConstants.LedgerId, StringComparison.Ordinal)) throw new InvalidDataException("checkpoint ledger mismatch");
        }

        private static void DurableCreate(string path, byte[] bytes)
        {
            using (FileStream stream = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.Read, 4096, FileOptions.WriteThrough))
            {
                stream.Write(bytes, 0, bytes.Length);
                stream.Flush(true);
            }
        }

        private static void DurableReplace(string path, byte[] bytes)
        {
            string temporary = path + ".new." + Guid.NewGuid().ToString("N");
            DurableCreate(temporary, bytes);
            if (File.Exists(path)) File.Replace(temporary, path, null, true);
            else File.Move(temporary, path);
        }
    }

    internal static class AuthorityCore
    {
        private static readonly object sync = new object();
        private static X509Certificate2 machineCertificate;
        private static RSA signer;
        private static X509Certificate2 publicCertificate;
        private static RSA verifier;
        private static DurableLedger ledger;
        private static string binarySha256;
        private static string binaryFileIdentity;
        private static string pipeAclIdentity;

        internal static void Initialize(PipeSecurity pipeSecurity)
        {
            lock (sync)
            {
                string currentSid = WindowsIdentity.GetCurrent().User.Value;
                if (!String.Equals(currentSid, AuthorityConstants.ServiceSid, StringComparison.Ordinal)) throw new SecurityException("service SID mismatch");
                string executable = Path.GetFullPath(Assembly.GetExecutingAssembly().Location);
                if (!String.Equals(executable, AuthorityConstants.ExecutablePath, StringComparison.OrdinalIgnoreCase)) throw new SecurityException("service executable path mismatch");
                if (!File.Exists(AuthorityConstants.PolicyPath)) throw new FileNotFoundException("authority policy missing");
                byte[] policy = File.ReadAllBytes(AuthorityConstants.PolicyPath);
                if (!String.Equals(CryptoUtil.Sha256Hex(policy), AuthorityConstants.PolicySha256, StringComparison.Ordinal)) throw new SecurityException("authority policy identity mismatch");
                StrictJson.ParseObject(new UTF8Encoding(false, true).GetString(policy));

                publicCertificate = CryptoUtil.LoadPublicCertificate();
                machineCertificate = publicCertificate;
                CngKey privateKey = CngKey.Open(
                    AuthorityConstants.KeyUniqueName,
                    CngProvider.MicrosoftSoftwareKeyStorageProvider,
                    CngKeyOpenOptions.MachineKey);
                signer = new RSACng(privateKey);
                RSACng cng = signer as RSACng;
                if (cng == null || cng.KeySize != 3072) throw new CryptographicException("signing key is not RSA-3072 CNG");
                if (!String.Equals(cng.Key.Provider.Provider, "Microsoft Software Key Storage Provider", StringComparison.Ordinal)) throw new CryptographicException("signing provider mismatch");
                if (!String.Equals(cng.Key.UniqueName, AuthorityConstants.KeyUniqueName, StringComparison.Ordinal)) throw new CryptographicException("signing key container mismatch");
                if (cng.Key.ExportPolicy != CngExportPolicies.None) throw new CryptographicException("signing key is exportable");
                if (DateTime.UtcNow < machineCertificate.NotBefore.ToUniversalTime() || DateTime.UtcNow > machineCertificate.NotAfter.ToUniversalTime()) throw new CryptographicException("signing certificate outside validity interval");

                verifier = System.Security.Cryptography.X509Certificates.RSACertificateExtensions.GetRSAPublicKey(publicCertificate);
                binarySha256 = CryptoUtil.Sha256File(executable);
                binaryFileIdentity = NativeIdentity.GetFileIdentity(executable);
                string pipeSddl = pipeSecurity.GetSecurityDescriptorSddlForm(AccessControlSections.All);
                pipeAclIdentity = CryptoUtil.Sha256Hex(Encoding.UTF8.GetBytes(pipeSddl));
                ledger = new DurableLedger(signer, verifier);
            }
        }

        internal static string Process(string requestText, string callerSid)
        {
            try
            {
                if (requestText == null || Encoding.UTF8.GetByteCount(requestText) > AuthorityConstants.MaximumMessageBytes) return Failure("MESSAGE_TOO_LARGE");
                IDictionary<string, object> request = StrictJson.ParseObject(requestText);
                string operation = StrictJson.RequireString(request, "operation");
                if (operation == "ISSUE_PROVISIONING_ATTESTATION") StrictJson.RequireExactKeys(request, "interface_version", "operation", "provisioning_nonce", "request_nonce");
                else StrictJson.RequireExactKeys(request, "interface_version", "operation", "request_nonce");
                if (!String.Equals(StrictJson.RequireString(request, "interface_version"), AuthorityConstants.InterfaceVersion, StringComparison.Ordinal)) return Failure("INTERFACE_VERSION_REJECTED");
                string requestNonce = StrictJson.RequireString(request, "request_nonce");
                Guid parsedNonce;
                if (!Guid.TryParseExact(requestNonce, "D", out parsedNonce) || !String.Equals(parsedNonce.ToString("D"), requestNonce, StringComparison.Ordinal)) return Failure("REQUEST_NONCE_INVALID");
                if (!IsAuthorizedCaller(callerSid)) return Failure("CALLER_NOT_AUTHORIZED");

                if (operation == "GET_HEALTH") return Health();
                if (operation == "GET_PUBLIC_TRUST") return PublicTrust();
                if (operation == "GET_LEDGER_STATUS") return LedgerStatus();
                if (operation == "ISSUE_PROVISIONING_NONCE") return IssueProvisioningNonce(requestNonce);
                if (operation == "ISSUE_PROVISIONING_ATTESTATION") return IssueProvisioningAttestation(requestNonce, StrictJson.RequireString(request, "provisioning_nonce"));
                if (operation == "SELF_TEST_UNAUTHORIZED_PRINCIPAL") return UnauthorizedPrincipalSelfTest();
                return Failure("OPERATION_NOT_ALLOWED");
            }
            catch (InvalidOperationException exception)
            {
                return Failure(exception.Message);
            }
            catch (Exception exception)
            {
                try
                {
                    string fault = "request|" + exception.GetType().FullName + "|" + exception.HResult.ToString("x8", CultureInfo.InvariantCulture) + "|" + exception.Message;
                    File.WriteAllText(Path.Combine(AuthorityConstants.TrustRoot, "request_fault.txt"), fault, new UTF8Encoding(false, true));
                }
                catch { }
                return Failure("REQUEST_REJECTED");
            }
        }

        private static bool IsAuthorizedCaller(string sid)
        {
            return String.Equals(sid, AuthorityConstants.OperatorSid, StringComparison.Ordinal) ||
                   String.Equals(sid, AuthorityConstants.SystemSid, StringComparison.Ordinal);
        }

        private static string Health()
        {
            WindowsIdentity identity = WindowsIdentity.GetCurrent();
            WindowsPrincipal principal = new WindowsPrincipal(identity);
            List<string> groups = new List<string>();
            foreach (IdentityReference group in identity.Groups) groups.Add(group.Value);
            groups.Sort(StringComparer.Ordinal);
            SortedDictionary<string, object> value = BaseSuccess("HEALTHY");
            value["binary_file_identity"] = binaryFileIdentity;
            value["binary_sha256"] = binarySha256;
            value["group_sids"] = groups.ToArray();
            value["is_administrator"] = principal.IsInRole(WindowsBuiltInRole.Administrator);
            value["ledger_id"] = AuthorityConstants.LedgerId;
            value["ledger_sequence"] = ledger.Sequence;
            value["pipe_acl_identity"] = pipeAclIdentity;
            value["private_key_export_policy"] = "NONE";
            value["repository_write_access"] = NativeIdentity.CanAddFile(AuthorityConstants.RepositoryRoot);
            value["service_sid"] = identity.User.Value;
            return CanonicalJson.Serialize(value);
        }

        private static string PublicTrust()
        {
            SortedDictionary<string, object> value = BaseSuccess("PUBLIC_TRUST_RESOLVED");
            value["certificate_der_sha256"] = AuthorityConstants.PublicCertificateSha256;
            value["certificate_thumbprint"] = AuthorityConstants.CertificateThumbprint;
            value["key_algorithm"] = AuthorityConstants.SignatureAlgorithm;
            value["public_certificate_path"] = AuthorityConstants.PublicCertificatePath;
            return CanonicalJson.Serialize(value);
        }

        private static string LedgerStatus()
        {
            SortedDictionary<string, object> value = BaseSuccess("LEDGER_VALID");
            value["checkpoint_identity"] = ledger.CheckpointIdentity;
            value["genesis_identity"] = ledger.GenesisIdentity;
            value["ledger_id"] = AuthorityConstants.LedgerId;
            value["root_hash"] = ledger.RootHash;
            value["sequence"] = ledger.Sequence;
            return CanonicalJson.Serialize(value);
        }

        private static string IssueProvisioningNonce(string requestNonce)
        {
            if (ledger.ContainsRequestNonce(requestNonce)) return Failure("REQUEST_NONCE_REPLAY");
            byte[] random = new byte[32];
            using (RandomNumberGenerator generator = RandomNumberGenerator.Create()) generator.GetBytes(random);
            string provisioningNonce = CryptoUtil.ToHex(random);
            string subject = CryptoUtil.Sha256Hex(Encoding.UTF8.GetBytes(provisioningNonce));
            LedgerAppendResult append = ledger.Append("PROVISIONING_NONCE_ISSUED", requestNonce, subject, subject);
            SortedDictionary<string, object> value = BaseSuccess("PROVISIONING_NONCE_ISSUED");
            value["checkpoint_identity"] = append.CheckpointIdentity;
            value["ledger_entry_identity"] = append.EntryIdentity;
            value["ledger_sequence"] = append.Sequence;
            value["provisioning_nonce"] = provisioningNonce;
            value["provisioning_nonce_identity"] = subject;
            return CanonicalJson.Serialize(value);
        }

        private static string IssueProvisioningAttestation(string requestNonce, string provisioningNonce)
        {
            if (ledger.ContainsRequestNonce(requestNonce)) return Failure("REQUEST_NONCE_REPLAY");
            if (provisioningNonce == null || provisioningNonce.Length != 64) return Failure("PROVISIONING_NONCE_INVALID");
            string subject = CryptoUtil.Sha256Hex(Encoding.UTF8.GetBytes(provisioningNonce));
            if (!ledger.ContainsSubject("PROVISIONING_NONCE_ISSUED", subject)) return Failure("PROVISIONING_NONCE_UNRESOLVED");
            if (ledger.ContainsSubject("PROVISIONING_ATTESTATION_ISSUED", subject)) return Failure("PROVISIONING_NONCE_REPLAY");
            if (File.Exists(AuthorityConstants.AttestationPath)) return Failure("ATTESTATION_ALREADY_EXISTS");

            SortedDictionary<string, object> aclIdentities = new SortedDictionary<string, object>(StringComparer.Ordinal);
            aclIdentities["config_root"] = AclIdentity(AuthorityConstants.ConfigRoot, true);
            aclIdentities["executable"] = AclIdentity(AuthorityConstants.ExecutablePath, false);
            aclIdentities["install_root"] = AclIdentity(AuthorityConstants.InstallRoot, true);
            aclIdentities["ledger_root"] = AclIdentity(AuthorityConstants.LedgerRoot, true);
            aclIdentities["private_key_file"] = AclIdentity(AuthorityConstants.KeyFilePath, false);
            aclIdentities["state_root"] = AclIdentity(AuthorityConstants.StateRoot, true);
            aclIdentities["trust_root"] = AclIdentity(AuthorityConstants.TrustRoot, true);

            SortedDictionary<string, object> payload = new SortedDictionary<string, object>(StringComparer.Ordinal);
            payload["acl_identities"] = aclIdentities;
            payload["architecture_base_commit"] = AuthorityConstants.BaseCommit;
            payload["attestation_schema_version"] = AuthorityConstants.SchemaVersion;
            payload["certificate_der_sha256"] = AuthorityConstants.PublicCertificateSha256;
            payload["certificate_issuer"] = machineCertificate.Issuer;
            payload["certificate_not_after"] = machineCertificate.NotAfter.ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture);
            payload["certificate_not_before"] = machineCertificate.NotBefore.ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture);
            payload["certificate_serial_number"] = machineCertificate.SerialNumber.ToLowerInvariant();
            payload["certificate_subject"] = machineCertificate.Subject;
            payload["certificate_thumbprint"] = AuthorityConstants.CertificateThumbprint;
            payload["executable_file_identity"] = binaryFileIdentity;
            payload["executable_path"] = AuthorityConstants.ExecutablePath;
            payload["executable_sha256"] = binarySha256;
            payload["fixed_host_paths"] = new string[] { AuthorityConstants.InstallRoot, AuthorityConstants.ConfigRoot, AuthorityConstants.LedgerRoot, AuthorityConstants.TrustRoot };
            payload["incomplete_result_commit"] = AuthorityConstants.IncompleteCommit;
            payload["interface_version"] = AuthorityConstants.InterfaceVersion;
            payload["ipc_identity"] = CryptoUtil.Sha256Hex(Encoding.UTF8.GetBytes(AuthorityConstants.PipeName + "|" + pipeAclIdentity + "|" + AuthorityConstants.InterfaceVersion));
            payload["issue_time"] = DateTimeOffset.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture);
            payload["key_algorithm"] = AuthorityConstants.SignatureAlgorithm;
            payload["key_container_unique_name"] = AuthorityConstants.KeyUniqueName;
            payload["key_export_policy"] = "NONEXPORTABLE";
            payload["key_provider"] = "Microsoft Software Key Storage Provider";
            payload["key_size"] = 3072;
            payload["ledger_checkpoint_identity"] = ledger.CheckpointIdentity;
            payload["ledger_genesis_identity"] = ledger.GenesisIdentity;
            payload["ledger_id"] = AuthorityConstants.LedgerId;
            payload["policy_sha256"] = AuthorityConstants.PolicySha256;
            payload["private_key_present_in_repository"] = false;
            payload["provisioning_nonce"] = provisioningNonce;
            payload["provisioning_nonce_identity"] = subject;
            payload["provisioning_task_identity"] = "TERMINAL_AUTHORITY_INFRASTRUCTURE_PROVISIONING_20260723";
            payload["public_key_identity"] = AuthorityConstants.PublicCertificateSha256;
            payload["r7_blocker_commit"] = AuthorityConstants.BlockerCommit;
            bool repositoryWriteAccess = NativeIdentity.CanAddFile(AuthorityConstants.RepositoryRoot);
            if (repositoryWriteAccess) throw new SecurityException("service token retains repository write authority");
            payload["repository_write_access"] = repositoryWriteAccess;
            payload["service_account"] = AuthorityConstants.ServiceAccount;
            payload["service_configuration_identity"] = ServiceConfigurationIdentity();
            payload["service_name"] = AuthorityConstants.ServiceName;
            payload["service_sid"] = AuthorityConstants.ServiceSid;
            payload["service_sid_type"] = "RESTRICTED";
            payload["threat_model"] = AuthorityConstants.ThreatModel;

            byte[] canonicalPayload = CanonicalJson.SerializeBytes(payload);
            byte[] signature = CryptoUtil.Sign(signer, canonicalPayload);
            SortedDictionary<string, object> envelope = new SortedDictionary<string, object>(StringComparer.Ordinal);
            envelope["payload"] = payload;
            envelope["public_key_identity"] = AuthorityConstants.PublicCertificateSha256;
            envelope["signature"] = Convert.ToBase64String(signature);
            envelope["signature_algorithm"] = AuthorityConstants.SignatureAlgorithm;
            byte[] attestationBytes = CanonicalJson.SerializeBytes(envelope);
            DurableCreate(AuthorityConstants.AttestationPath, attestationBytes);
            string attestationIdentity = CryptoUtil.Sha256Hex(attestationBytes);
            LedgerAppendResult append = ledger.Append("PROVISIONING_ATTESTATION_ISSUED", requestNonce, subject, attestationIdentity);

            SortedDictionary<string, object> value = BaseSuccess("PROVISIONING_ATTESTATION_ISSUED");
            value["attestation_identity"] = attestationIdentity;
            value["attestation_locator"] = AuthorityConstants.AttestationPath;
            value["checkpoint_identity"] = append.CheckpointIdentity;
            value["ledger_entry_identity"] = append.EntryIdentity;
            value["ledger_sequence"] = append.Sequence;
            value["signature_identity"] = CryptoUtil.Sha256Hex(signature);
            return CanonicalJson.Serialize(value);
        }

        private static string UnauthorizedPrincipalSelfTest()
        {
            SortedDictionary<string, object> value = BaseSuccess("UNAUTHORIZED_PRINCIPAL_REJECTED");
            value["tested_sid"] = AuthorityConstants.ServiceSid;
            value["would_authorize"] = IsAuthorizedCaller(AuthorityConstants.ServiceSid);
            if ((bool)value["would_authorize"]) return Failure("SELF_TEST_FAILED");
            return CanonicalJson.Serialize(value);
        }

        private static SortedDictionary<string, object> BaseSuccess(string status)
        {
            SortedDictionary<string, object> value = new SortedDictionary<string, object>(StringComparer.Ordinal);
            value["interface_version"] = AuthorityConstants.InterfaceVersion;
            value["status"] = status;
            return value;
        }

        private static string Failure(string errorCode)
        {
            SortedDictionary<string, object> value = new SortedDictionary<string, object>(StringComparer.Ordinal);
            value["error_code"] = errorCode;
            value["interface_version"] = AuthorityConstants.InterfaceVersion;
            value["status"] = "REJECTED";
            return CanonicalJson.Serialize(value);
        }

        private static string AclIdentity(string path, bool directory)
        {
            AccessControlSections sections = AccessControlSections.Access | AccessControlSections.Owner | AccessControlSections.Group;
            string sddl;
            if (directory)
            {
                DirectorySecurity security = Directory.GetAccessControl(path, sections);
                sddl = security.GetSecurityDescriptorSddlForm(sections);
            }
            else
            {
                FileSecurity security = File.GetAccessControl(path, sections);
                sddl = security.GetSecurityDescriptorSddlForm(sections);
            }
            return CryptoUtil.Sha256Hex(Encoding.UTF8.GetBytes(sddl));
        }

        private static string ServiceConfigurationIdentity()
        {
            using (RegistryKey key = Registry.LocalMachine.OpenSubKey(@"SYSTEM\CurrentControlSet\Services\RandleTerminalAuthority", false))
            {
                if (key == null) throw new InvalidDataException("service configuration missing");
                SortedDictionary<string, object> config = new SortedDictionary<string, object>(StringComparer.Ordinal);
                config["image_path"] = Convert.ToString(key.GetValue("ImagePath"), CultureInfo.InvariantCulture);
                config["object_name"] = Convert.ToString(key.GetValue("ObjectName"), CultureInfo.InvariantCulture);
                config["service_sid_type"] = Convert.ToInt64(key.GetValue("ServiceSidType", 0), CultureInfo.InvariantCulture);
                config["start"] = Convert.ToInt64(key.GetValue("Start", 0), CultureInfo.InvariantCulture);
                config["type"] = Convert.ToInt64(key.GetValue("Type", 0), CultureInfo.InvariantCulture);
                return CryptoUtil.Sha256Hex(CanonicalJson.SerializeBytes(config));
            }
        }

        private static void DurableCreate(string path, byte[] bytes)
        {
            using (FileStream stream = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.Read, 4096, FileOptions.WriteThrough))
            {
                stream.Write(bytes, 0, bytes.Length);
                stream.Flush(true);
            }
        }
    }

    internal static class NativeIdentity
    {
        private const uint GenericRead = 0x80000000;
        private const uint FileShareRead = 0x00000001;
        private const uint FileShareWrite = 0x00000002;
        private const uint FileShareDelete = 0x00000004;
        private const uint OpenExisting = 3;
        private const uint FileAddFile = 0x00000002;
        private const uint FileFlagBackupSemantics = 0x02000000;

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

        internal static string GetFileIdentity(string path)
        {
            using (SafeFileHandle handle = CreateFile(path, GenericRead, FileShareRead | FileShareWrite | FileShareDelete, IntPtr.Zero, OpenExisting, 0, IntPtr.Zero))
            {
                if (handle.IsInvalid) throw new IOException("unable to open file identity", Marshal.GetLastWin32Error());
                ByHandleFileInformation information;
                if (!GetFileInformationByHandle(handle, out information)) throw new IOException("unable to read file identity", Marshal.GetLastWin32Error());
                return information.VolumeSerialNumber.ToString("x8", CultureInfo.InvariantCulture) + ":" +
                       information.FileIndexHigh.ToString("x8", CultureInfo.InvariantCulture) + information.FileIndexLow.ToString("x8", CultureInfo.InvariantCulture);
            }
        }

        internal static bool CanAddFile(string directory)
        {
            using (SafeFileHandle handle = CreateFile(directory, FileAddFile, FileShareRead | FileShareWrite | FileShareDelete, IntPtr.Zero, OpenExisting, FileFlagBackupSemantics, IntPtr.Zero))
            {
                return !handle.IsInvalid;
            }
        }
    }

    internal sealed class AuthorityWindowsService : ServiceBase
    {
        private volatile bool stopping;
        private Thread serverThread;

        internal AuthorityWindowsService()
        {
            ServiceName = AuthorityConstants.ServiceName;
            CanStop = true;
            CanShutdown = true;
            AutoLog = true;
        }

        protected override void OnStart(string[] args)
        {
            try
            {
                PipeSecurity security = CreatePipeSecurity();
                AuthorityCore.Initialize(security);
                stopping = false;
                serverThread = new Thread(delegate()
                {
                    try { ServerLoop(security); }
                    catch (Exception exception) { RecordPublicFault("server", exception); }
                });
                serverThread.IsBackground = true;
                serverThread.Name = "RandleTerminalAuthorityPipe";
                serverThread.Start();
            }
            catch (Exception exception)
            {
                RecordPublicFault("start", exception);
                throw;
            }
        }

        protected override void OnStop()
        {
            stopping = true;
            try
            {
                using (NamedPipeClientStream wake = new NamedPipeClientStream(".", AuthorityConstants.PipeName, PipeDirection.Out))
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
                    AuthorityConstants.PipeName,
                    PipeDirection.InOut,
                    8,
                    PipeTransmissionMode.Message,
                    PipeOptions.WriteThrough,
                    AuthorityConstants.MaximumMessageBytes,
                    AuthorityConstants.MaximumMessageBytes,
                    security))
                {
                    pipe.WaitForConnection();
                    if (stopping) return;
                    string callerSid = String.Empty;
                    try
                    {
                        pipe.RunAsClient(delegate()
                        {
                            WindowsIdentity identity = WindowsIdentity.GetCurrent(true);
                            callerSid = identity.User.Value;
                            identity.Dispose();
                        });
                    }
                    catch
                    {
                        WriteResponse(pipe, "{\"error_code\":\"CALLER_IDENTITY_UNAVAILABLE\",\"interface_version\":\"1.0.0\",\"status\":\"REJECTED\"}");
                        continue;
                    }
                    string request = ReadRequest(pipe);
                    string response = request == null ? "{\"error_code\":\"MESSAGE_TOO_LARGE\",\"interface_version\":\"1.0.0\",\"status\":\"REJECTED\"}" : AuthorityCore.Process(request, callerSid);
                    WriteResponse(pipe, response);
                }
            }
        }

        private static PipeSecurity CreatePipeSecurity()
        {
            PipeSecurity security = new PipeSecurity();
            security.SetAccessRuleProtection(true, false);
            security.AddAccessRule(new PipeAccessRule(new SecurityIdentifier(AuthorityConstants.OperatorSid), PipeAccessRights.ReadWrite, AccessControlType.Allow));
            security.AddAccessRule(new PipeAccessRule(new SecurityIdentifier(AuthorityConstants.SystemSid), PipeAccessRights.FullControl, AccessControlType.Allow));
            security.AddAccessRule(new PipeAccessRule(new SecurityIdentifier(AuthorityConstants.ServiceSid), PipeAccessRights.FullControl, AccessControlType.Allow));
            return security;
        }

        private static void RecordPublicFault(string phase, Exception exception)
        {
            try
            {
                string path = Path.Combine(AuthorityConstants.TrustRoot, "service_initialization_fault.txt");
                string value = phase + "|" + exception.GetType().FullName + "|" + exception.HResult.ToString("x8", CultureInfo.InvariantCulture) + "|" + exception.Message;
                File.WriteAllText(path, value, new UTF8Encoding(false, true));
            }
            catch { }
        }

        private static string ReadRequest(Stream pipe)
        {
            MemoryStream buffer = new MemoryStream();
            while (true)
            {
                int value = pipe.ReadByte();
                if (value < 0 || value == '\n') break;
                if (buffer.Length >= AuthorityConstants.MaximumMessageBytes) return null;
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
            ServiceBase.Run(new AuthorityWindowsService());
        }
    }
}
