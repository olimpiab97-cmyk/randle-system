using Microsoft.Win32.SafeHandles;
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Security;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;

namespace RandleAI.R7Remediation
{
    internal sealed class R7DurabilityFaultScope : IDisposable
    {
        [ThreadStatic]
        private static R7DurabilityFaultScope current;
        private readonly string root;
        private readonly string point;
        private bool disposed;
        internal bool Triggered;
        internal string TriggeredPath = String.Empty;
        internal string TriggeredStage = String.Empty;

        internal R7DurabilityFaultScope(string isolatedRoot, string faultPoint)
            : this(isolatedRoot, faultPoint, false)
        {
        }

        internal R7DurabilityFaultScope(string isolatedRoot, string faultPoint, bool offlineStatic)
        {
            root = Path.GetFullPath(isolatedRoot).TrimEnd(Path.DirectorySeparatorChar);
            if (!offlineStatic)
            {
                if (root.IndexOf("IsolatedTests", StringComparison.OrdinalIgnoreCase) < 0 || !root.StartsWith(R7Fixed.ExecutionTestRoot + Path.DirectorySeparatorChar, StringComparison.Ordinal)) throw new SecurityException("DURABILITY_FAULT_SCOPE_NOT_ISOLATED");
            }
            else
            {
                string temporaryRoot = Path.GetFullPath(Path.GetTempPath()).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
                if (!root.StartsWith(temporaryRoot, StringComparison.OrdinalIgnoreCase) || root.IndexOf(Path.DirectorySeparatorChar + "R7StaticIsolatedTests" + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase) < 0) throw new SecurityException("DURABILITY_OFFLINE_FAULT_SCOPE_NOT_ISOLATED");
            }
            if (current != null) throw new InvalidOperationException("DURABILITY_FAULT_SCOPE_NESTED");
            point = faultPoint ?? String.Empty;
            current = this;
        }

        internal static void BeforeCreate(string path)
        {
            R7DurabilityFaultScope scope = RequirePath(path);
            if (scope == null || scope.Triggered || !path.EndsWith(".receipt.json", StringComparison.Ordinal)) return;
            if (scope.point == "DISK_FULL") scope.Throw("BEFORE_CREATE", path, new IOException("INJECTED_DISK_FULL", 112));
            if (scope.point == "ACCESS_DENIED") scope.Throw("BEFORE_CREATE", path, new UnauthorizedAccessException("INJECTED_ACCESS_DENIED"));
        }

        internal static int PartialWriteLength(string path, int length)
        {
            R7DurabilityFaultScope scope = RequirePath(path);
            if (scope == null || scope.Triggered || scope.point != "PARTIAL_WRITE" || !path.EndsWith(".partial.json", StringComparison.Ordinal)) return -1;
            scope.Triggered = true;
            scope.TriggeredPath = Path.GetFullPath(path);
            scope.TriggeredStage = "DURING_FILE_WRITE";
            return Math.Max(1, length / 2);
        }

        internal static void BeforeDirectoryFlush(string path)
        {
            R7DurabilityFaultScope scope = RequirePath(path);
            if (scope == null || scope.Triggered || scope.point != "PARENT_DIRECTORY_PERSISTENCE_FAILURE" || !path.EndsWith(".receipt.json", StringComparison.Ordinal)) return;
            scope.Throw("BEFORE_PARENT_DIRECTORY_FLUSH", path, new IOException("INJECTED_PARENT_DIRECTORY_PERSISTENCE_FAILURE"));
        }

        internal static void AfterReplacementTemporary(string path)
        {
            R7DurabilityFaultScope scope = RequirePath(path);
            if (scope == null || scope.Triggered || scope.point != "DURING_CHECKPOINT_UPDATE" || !path.EndsWith("checkpoint.json", StringComparison.Ordinal)) return;
            scope.Throw("AFTER_CHECKPOINT_TEMP_DURABLE_BEFORE_REPLACE", path, new IOException("INJECTED_CHECKPOINT_REPLACE_INTERRUPTION"));
        }

        internal static void BeforeReplacement(string path)
        {
            R7DurabilityFaultScope scope = RequirePath(path);
            if (scope == null || scope.Triggered || scope.point != "BEFORE_CHECKPOINT_UPDATE" || !path.EndsWith("checkpoint.json", StringComparison.Ordinal)) return;
            scope.Throw("BEFORE_CHECKPOINT_TEMP_CREATE", path, new IOException("INJECTED_BEFORE_CHECKPOINT_UPDATE"));
        }

        private static R7DurabilityFaultScope RequirePath(string path)
        {
            R7DurabilityFaultScope scope = current;
            if (scope == null) return null;
            string full = Path.GetFullPath(path);
            if (!full.StartsWith(scope.root + Path.DirectorySeparatorChar, StringComparison.Ordinal)) throw new SecurityException("DURABILITY_FAULT_ESCAPED_ISOLATED_ROOT");
            return scope;
        }

        private void Throw(string stage, string path, Exception exception)
        {
            Triggered = true;
            TriggeredPath = Path.GetFullPath(path);
            TriggeredStage = stage;
            throw exception;
        }

        public void Dispose()
        {
            if (disposed) return;
            disposed = true;
            if (Object.ReferenceEquals(current, this)) current = null;
        }
    }

    internal sealed class R7DurabilityUncertainException : IOException
    {
        internal R7DurabilityUncertainException(string message, Exception inner) : base(message, inner) { }
    }

    internal static class R7Crypto
    {
        internal static X509Certificate2 LoadPublicCertificate(string path, string expectedSha256, string fixedRoot)
        {
            using (R7VerifiedFile file = R7SafeFile.Open(path, path, fixedRoot, expectedSha256, null, null, null))
            {
                X509Certificate2 certificate = new X509Certificate2(file.Bytes);
                string identity = R7Hash.Bytes(certificate.Export(X509ContentType.Cert));
                if (!R7Hash.FixedTimeEquals(identity, expectedSha256)) { certificate.Dispose(); throw new CryptographicException("PUBLIC_CERTIFICATE_IDENTITY_MISMATCH"); }
                return certificate;
            }
        }

        internal static RSA LoadTerminalSigner()
        {
            CngKey key = CngKey.Open(R7Fixed.TerminalKeyUniqueName, CngProvider.MicrosoftSoftwareKeyStorageProvider, CngKeyOpenOptions.MachineKey);
            if (key.ExportPolicy != CngExportPolicies.None) { key.Dispose(); throw new CryptographicException("TERMINAL_KEY_EXPORTABLE"); }
            if (!String.Equals(key.UniqueName, R7Fixed.TerminalKeyUniqueName, StringComparison.Ordinal)) { key.Dispose(); throw new CryptographicException("TERMINAL_KEY_IDENTITY_MISMATCH"); }
            RSACng rsa = new RSACng(key);
            if (rsa.KeySize != 3072) { rsa.Dispose(); throw new CryptographicException("TERMINAL_KEY_SIZE_MISMATCH"); }
            return rsa;
        }

        internal static RSA LoadMachineSigner(string uniqueName, int expectedBits)
        {
            CngKey key = CngKey.Open(uniqueName, CngProvider.MicrosoftSoftwareKeyStorageProvider, CngKeyOpenOptions.MachineKey);
            if (key.ExportPolicy != CngExportPolicies.None) { key.Dispose(); throw new CryptographicException("SIGNING_KEY_EXPORTABLE"); }
            if (!String.Equals(key.UniqueName, uniqueName, StringComparison.Ordinal)) { key.Dispose(); throw new CryptographicException("SIGNING_KEY_IDENTITY_MISMATCH"); }
            RSACng rsa = new RSACng(key);
            if (rsa.KeySize != expectedBits) { rsa.Dispose(); throw new CryptographicException("SIGNING_KEY_SIZE_MISMATCH"); }
            return rsa;
        }

        internal static byte[] Sign(RSA signer, byte[] payload)
        {
            return signer.SignData(payload, HashAlgorithmName.SHA256, RSASignaturePadding.Pss);
        }

        internal static bool Verify(RSA verifier, byte[] payload, byte[] signature)
        {
            return verifier.VerifyData(payload, signature, HashAlgorithmName.SHA256, RSASignaturePadding.Pss);
        }

        internal static SortedDictionary<string, object> Envelope(IDictionary<string, object> payload, string publicKeyIdentity, RSA signer)
        {
            byte[] canonical = R7Json.Encode(payload);
            byte[] signature = Sign(signer, canonical);
            return R7Json.Object(
                "payload", payload,
                "public_key_identity", publicKeyIdentity,
                "signature", Convert.ToBase64String(signature),
                "signature_algorithm", R7Fixed.SignatureAlgorithm);
        }

        internal static SortedDictionary<string, object> VerifyEnvelope(byte[] bytes, string expectedPublicKeyIdentity, RSA verifier)
        {
            SortedDictionary<string, object> envelope = R7Json.ParseCanonicalObject(bytes);
            R7Json.ExactKeys(envelope, "payload", "public_key_identity", "signature", "signature_algorithm");
            if (!String.Equals(R7Json.String(envelope, "public_key_identity", 64, 64), expectedPublicKeyIdentity, StringComparison.Ordinal)) throw new CryptographicException("ENVELOPE_KEY_IDENTITY_MISMATCH");
            if (!String.Equals(R7Json.String(envelope, "signature_algorithm", 1, 64), R7Fixed.SignatureAlgorithm, StringComparison.Ordinal)) throw new CryptographicException("ENVELOPE_ALGORITHM_MISMATCH");
            SortedDictionary<string, object> payload = R7Json.Child(envelope, "payload");
            byte[] signature;
            try { signature = Convert.FromBase64String(R7Json.String(envelope, "signature", 1, 4096)); }
            catch (FormatException) { throw new CryptographicException("SIGNATURE_ENCODING_INVALID"); }
            if (!Verify(verifier, R7Json.Encode(payload), signature)) throw new CryptographicException("SIGNATURE_INVALID");
            return payload;
        }
    }

    internal static class R7DurableFile
    {
        private const uint GenericRead = 0x80000000;
        private const uint GenericWrite = 0x40000000;
        private const uint FileShareRead = 0x00000001;
        private const uint OpenExisting = 3;
        private const uint FileFlagBackupSemantics = 0x02000000;
        private const uint MoveFileReplaceExisting = 0x00000001;
        private const uint MoveFileWriteThrough = 0x00000008;

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern SafeFileHandle CreateFileW(string name, uint access, uint share, IntPtr security, uint creation, uint flags, IntPtr templateFile);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool FlushFileBuffers(SafeFileHandle handle);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern bool MoveFileExW(string existingName, string newName, uint flags);

        internal static bool IsAlreadyExists(IOException exception)
        {
            int code = exception.HResult & 0xffff;
            return code == 80 || code == 183;
        }

        internal static void CreateNew(string path, byte[] bytes)
        {
            string full = Path.GetFullPath(path);
            string parent = Path.GetDirectoryName(full);
            R7SafeFile.VerifyDirectoryChain(parent);
            R7DurabilityFaultScope.BeforeCreate(full);
            using (FileStream stream = new FileStream(full, FileMode.CreateNew, FileAccess.Write, FileShare.None, 4096, FileOptions.WriteThrough))
            {
                int partialLength = R7DurabilityFaultScope.PartialWriteLength(full, bytes.Length);
                if (partialLength >= 0)
                {
                    stream.Write(bytes, 0, partialLength);
                    stream.Flush(true);
                    throw new IOException("INJECTED_PARTIAL_WRITE");
                }
                stream.Write(bytes, 0, bytes.Length);
                stream.Flush(true);
            }
            R7DurabilityFaultScope.BeforeDirectoryFlush(full);
            FlushDirectory(parent);
            using (R7VerifiedFile verify = R7SafeFile.Open(full, full, parent, R7Hash.Bytes(bytes), null, null, null)) { }
        }

        internal static void Replace(string path, byte[] bytes)
        {
            string full = Path.GetFullPath(path);
            string parent = Path.GetDirectoryName(full);
            string temporary = full + ".new." + Guid.NewGuid().ToString("N");
            R7DurabilityFaultScope.BeforeReplacement(full);
            CreateNew(temporary, bytes);
            R7DurabilityFaultScope.AfterReplacementTemporary(full);
            if (!MoveFileExW(temporary, full, MoveFileReplaceExisting | MoveFileWriteThrough))
            {
                int error = Marshal.GetLastWin32Error();
                throw new IOException("ATOMIC_REPLACE_FAILED", error);
            }
            FlushDirectory(parent);
            using (R7VerifiedFile verify = R7SafeFile.Open(full, full, parent, R7Hash.Bytes(bytes), null, null, null)) { }
        }

        internal static void FlushDirectory(string directory)
        {
            using (SafeFileHandle handle = CreateFileW(directory, GenericRead | GenericWrite, FileShareRead, IntPtr.Zero, OpenExisting, FileFlagBackupSemantics, IntPtr.Zero))
            {
                if (handle.IsInvalid)
                {
                    int error = Marshal.GetLastWin32Error();
                    throw new IOException("PARENT_DIRECTORY_OPEN_FAILED", error);
                }
                if (!FlushFileBuffers(handle))
                {
                    int error = Marshal.GetLastWin32Error();
                    throw new IOException("PARENT_DIRECTORY_FLUSH_FAILED", error);
                }
            }
        }

        internal static void MovePreserving(string sourcePath, string destinationPath, string sourceRoot, string destinationRoot, string expectedSha256)
        {
            string source = Path.GetFullPath(sourcePath);
            string destination = Path.GetFullPath(destinationPath);
            string sourceParent = Path.GetDirectoryName(source);
            string destinationParent = Path.GetDirectoryName(destination);
            R7SafeFile.VerifyDirectoryChain(sourceParent);
            R7SafeFile.VerifyDirectoryChain(destinationParent);
            using (R7VerifiedFile sourceFile = R7SafeFile.Open(source, source, sourceRoot, expectedSha256, null, null, null)) { }
            R7VerifiedFile unexpected;
            if (R7SafeFile.TryOpen(destination, destination, destinationRoot, null, null, null, null, out unexpected))
            {
                unexpected.Dispose();
                throw new IOException("PRESERVATION_DESTINATION_EXISTS");
            }
            if (!MoveFileExW(source, destination, MoveFileWriteThrough))
            {
                int error = Marshal.GetLastWin32Error();
                throw new IOException("PRESERVING_MOVE_FAILED", error);
            }
            FlushDirectory(sourceParent);
            if (!String.Equals(sourceParent, destinationParent, StringComparison.Ordinal)) FlushDirectory(destinationParent);
            using (R7VerifiedFile destinationFile = R7SafeFile.Open(destination, destination, destinationRoot, expectedSha256, null, null, null)) { }
        }
    }

    internal sealed class R7CheckpointArtifact
    {
        internal string Name;
        internal string Identity;
    }

    internal sealed class R7LedgerRecord
    {
        internal long Sequence;
        internal string EntryHash;
        internal string EntryIdentity;
        internal string Operation;
        internal string SubjectId;
        internal string ContentAddress;
        internal string SchemaVersion;
        internal string RequestNonce;
        internal string IssueTime;
        internal SortedDictionary<string, object> Payload;
    }

    internal sealed class R7LedgerAppend
    {
        internal R7LedgerRecord Record;
        internal string CheckpointIdentity;
    }

    internal sealed class R7VersionedLedger
    {
        private readonly object sync = new object();
        private readonly string root;
        private readonly string ledgerId;
        private readonly string publicKeyIdentity;
        private readonly string serviceSid;
        private readonly RSA signer;
        private readonly RSA verifier;
        private readonly bool createGenesis;
        private readonly string genesisContentAddress;
        private readonly string expectedDirectoryOwnerSid;
        private readonly string expectedFileOwnerSid;
        private readonly string expectedVolumeIdentity;
        private readonly List<R7LedgerRecord> records = new List<R7LedgerRecord>();
        private long sequence;
        private string rootHash = R7Fixed.ZeroHash;
        private string checkpointIdentity = R7Fixed.ZeroHash;
        private string checkpointRecoveryReason = String.Empty;
        private bool appendFaulted;
        private readonly List<R7CheckpointArtifact> pendingCheckpointArtifacts = new List<R7CheckpointArtifact>();

        internal R7VersionedLedger(string ledgerRoot, string fixedLedgerId, string fixedPublicKeyIdentity, string fixedServiceSid, RSA signingKey, RSA verificationKey)
            : this(ledgerRoot, fixedLedgerId, fixedPublicKeyIdentity, fixedServiceSid, signingKey, verificationKey, false, null)
        {
        }

        internal R7VersionedLedger(string ledgerRoot, string fixedLedgerId, string fixedPublicKeyIdentity, string fixedServiceSid, RSA signingKey, RSA verificationKey, bool allowGenesisCreation, string fixedGenesisContentAddress)
        {
            root = Path.GetFullPath(ledgerRoot);
            ledgerId = fixedLedgerId;
            publicKeyIdentity = fixedPublicKeyIdentity;
            serviceSid = fixedServiceSid;
            signer = signingKey;
            verifier = verificationKey;
            createGenesis = allowGenesisCreation;
            genesisContentAddress = fixedGenesisContentAddress;
            bool governedHostLedger = String.Equals(root, R7Fixed.LedgerRoot, StringComparison.Ordinal) || String.Equals(root, R7Fixed.UpgradeLedgerRoot, StringComparison.Ordinal);
            expectedDirectoryOwnerSid = governedHostLedger ? R7Fixed.SystemSid : null;
            expectedFileOwnerSid = governedHostLedger ? fixedServiceSid : null;
            expectedVolumeIdentity = governedHostLedger ? R7SafeFile.MeasureDirectory(root, root, expectedDirectoryOwnerSid, null, null).VolumeIdentity : null;
            Load();
        }

        internal long Sequence { get { lock (sync) return sequence; } }
        internal string RootHash { get { lock (sync) return rootHash; } }
        internal string CheckpointIdentity { get { lock (sync) return checkpointIdentity; } }
        internal string CheckpointRecoveryReason { get { lock (sync) return checkpointRecoveryReason; } }
        internal R7CheckpointArtifact[] PendingCheckpointArtifacts { get { lock (sync) return pendingCheckpointArtifacts.ToArray(); } }
        internal R7LedgerRecord[] Records { get { lock (sync) return records.ToArray(); } }

        internal R7LedgerRecord FindSequence(long requested)
        {
            lock (sync)
            {
                if (requested < 1 || requested > records.Count) return null;
                R7LedgerRecord record = records[(int)requested - 1];
                return record.Sequence == requested ? record : null;
            }
        }

        internal R7LedgerRecord[] Find(string operation, string subjectId)
        {
            lock (sync)
            {
                List<R7LedgerRecord> result = new List<R7LedgerRecord>();
                foreach (R7LedgerRecord record in records)
                {
                    if ((operation == null || String.Equals(record.Operation, operation, StringComparison.Ordinal)) &&
                        (subjectId == null || String.Equals(record.SubjectId, subjectId, StringComparison.Ordinal))) result.Add(record);
                }
                return result.ToArray();
            }
        }

        internal R7LedgerAppend Append(string operation, string transitionNonce, string subjectId, string contentAddress, string schemaVersion)
        {
            if (signer == null) throw new InvalidOperationException("LEDGER_READ_ONLY");
            if (!R7Hash.IsLowerSha256(contentAddress)) throw new R7ProtocolException("CONTENT_ADDRESS_INVALID");
            Guid nonce;
            if (!Guid.TryParseExact(transitionNonce, "D", out nonce) || !String.Equals(nonce.ToString("D"), transitionNonce, StringComparison.Ordinal)) throw new R7ProtocolException("TRANSITION_NONCE_INVALID");
            lock (sync)
            {
                if (appendFaulted) throw new R7DurabilityUncertainException("LEDGER_APPEND_DISABLED_PENDING_RESTART", null);
                foreach (R7LedgerRecord existing in records) if (String.Equals(existing.RequestNonce, transitionNonce, StringComparison.Ordinal)) throw new InvalidOperationException("TRANSITION_NONCE_REPLAY");
                long next = checked(sequence + 1);
                SortedDictionary<string, object> core = R7Json.Object(
                    "content_address", contentAddress,
                    "issue_time", DateTimeOffset.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture),
                    "ledger_id", ledgerId,
                    "operation", operation,
                    "prior_entry_hash", rootHash,
                    "public_key_identity", publicKeyIdentity,
                    "request_nonce", transitionNonce,
                    "schema_version", schemaVersion,
                    "sequence", next,
                    "service_sid", serviceSid,
                    "subject_id", subjectId ?? String.Empty);
                string entryHash = R7Hash.Bytes(R7Json.Encode(core));
                SortedDictionary<string, object> payload = new SortedDictionary<string, object>(core, StringComparer.Ordinal);
                payload.Add("entry_hash", entryHash);
                SortedDictionary<string, object> envelope = R7Crypto.Envelope(payload, publicKeyIdentity, signer);
                byte[] bytes = R7Json.Encode(envelope);
                string path = Path.Combine(root, next.ToString("D20", CultureInfo.InvariantCulture) + ".entry.json");
                try
                {
                    R7DurableFile.CreateNew(path, bytes);
                    using (R7VerifiedFile persisted = R7SafeFile.Open(path, path, root, R7Hash.Bytes(bytes), expectedFileOwnerSid, null, expectedVolumeIdentity)) { }
                }
                catch (Exception exception)
                {
                    appendFaulted = true;
                    throw new R7DurabilityUncertainException("LEDGER_ENTRY_PERSISTENCE_OUTCOME_UNCERTAIN", exception);
                }
                R7LedgerRecord record = Record(payload, R7Hash.Bytes(bytes));
                records.Add(record);
                sequence = next;
                rootHash = entryHash;
                try { WriteCheckpoint(schemaVersion); }
                catch (Exception exception)
                {
                    checkpointRecoveryReason = "CHECKPOINT_ADVANCEMENT_FAILED_" + exception.GetType().Name;
                }
                return new R7LedgerAppend { Record = record, CheckpointIdentity = checkpointIdentity };
            }
        }

        internal void RecoverCheckpoint(string schemaVersion)
        {
            if (signer == null) throw new InvalidOperationException("LEDGER_READ_ONLY");
            lock (sync)
            {
                if (String.IsNullOrEmpty(checkpointRecoveryReason)) return;
                WriteCheckpoint(schemaVersion);
            }
        }

        internal void PreservePendingCheckpoints(string recoveryRoot)
        {
            if (signer == null) throw new InvalidOperationException("LEDGER_READ_ONLY");
            string fixedRecoveryRoot = Path.GetFullPath(recoveryRoot);
            lock (sync)
            {
                R7SafeFile.MeasureDirectory(fixedRecoveryRoot, fixedRecoveryRoot, null, null, null);
                foreach (R7CheckpointArtifact artifact in pendingCheckpointArtifacts.ToArray())
                {
                    string suffix = artifact.Name.Substring("checkpoint.json.new.".Length);
                    string source = Path.Combine(root, artifact.Name);
                    string destination = Path.Combine(fixedRecoveryRoot, "checkpoint.pending." + artifact.Identity + "." + suffix + ".preserved");
                    R7DurableFile.MovePreserving(source, destination, root, fixedRecoveryRoot, artifact.Identity);
                }
                pendingCheckpointArtifacts.Clear();
                ValidateCheckpoint();
            }
        }

        private void Load()
        {
            R7SafeFile.MeasureDirectory(root, root, expectedDirectoryOwnerSid, null, expectedVolumeIdentity);
            if (Directory.GetDirectories(root, "*", SearchOption.TopDirectoryOnly).Length != 0) throw new InvalidDataException("LEDGER_DIRECTORY_ENTRY_REJECTED");
            string[] allPaths = Directory.GetFiles(root, "*", SearchOption.TopDirectoryOnly);
            Array.Sort(allPaths, StringComparer.Ordinal);
            List<string> entryPaths = new List<string>();
            foreach (string path in allPaths)
            {
                string name = Path.GetFileName(path);
                if (IsLedgerEntryName(name)) { entryPaths.Add(path); continue; }
                if (String.Equals(name, "checkpoint.json", StringComparison.Ordinal)) continue;
                if (IsPendingCheckpointName(name))
                {
                    using (R7VerifiedFile pending = R7SafeFile.Open(path, Path.Combine(root, name), root, null, expectedFileOwnerSid, null, expectedVolumeIdentity))
                    {
                        pendingCheckpointArtifacts.Add(new R7CheckpointArtifact { Name = name, Identity = pending.Measurement.Sha256 });
                    }
                    continue;
                }
                throw new InvalidDataException("LEDGER_UNEXPECTED_FILE|" + name);
            }
            string[] paths = entryPaths.ToArray();
            long expectedSequence = 1;
            string expectedPrior = R7Fixed.ZeroHash;
            foreach (string path in paths)
            {
                string expectedName = expectedSequence.ToString("D20", CultureInfo.InvariantCulture) + ".entry.json";
                if (!String.Equals(Path.GetFileName(path), expectedName, StringComparison.Ordinal)) throw new InvalidDataException("LEDGER_SEQUENCE_FILENAME_GAP");
                using (R7VerifiedFile file = R7SafeFile.Open(path, Path.Combine(root, expectedName), root, null, expectedFileOwnerSid, null, expectedVolumeIdentity))
                {
                    SortedDictionary<string, object> payload = R7Crypto.VerifyEnvelope(file.Bytes, publicKeyIdentity, verifier);
                    R7Json.ExactKeys(payload, "content_address", "entry_hash", "issue_time", "ledger_id", "operation", "prior_entry_hash", "public_key_identity", "request_nonce", "schema_version", "sequence", "service_sid", "subject_id");
                    long foundSequence = R7Json.Integer(payload, "sequence", 1, Int64.MaxValue);
                    if (foundSequence != expectedSequence) throw new InvalidDataException("LEDGER_SEQUENCE_GAP");
                    if (!String.Equals(R7Json.String(payload, "ledger_id", 64, 64), ledgerId, StringComparison.Ordinal)) throw new InvalidDataException("LEDGER_IDENTITY_MISMATCH");
                    if (!String.Equals(R7Json.String(payload, "public_key_identity", 64, 64), publicKeyIdentity, StringComparison.Ordinal)) throw new InvalidDataException("LEDGER_KEY_MISMATCH");
                    if (!String.Equals(R7Json.String(payload, "service_sid", 1, 256), serviceSid, StringComparison.Ordinal)) throw new InvalidDataException("LEDGER_SERVICE_MISMATCH");
                    if (!String.Equals(R7Json.String(payload, "prior_entry_hash", 64, 64), expectedPrior, StringComparison.Ordinal)) throw new InvalidDataException("LEDGER_PRIOR_HASH_MISMATCH");
                    SortedDictionary<string, object> core = new SortedDictionary<string, object>(payload, StringComparer.Ordinal);
                    string recorded = R7Json.String(core, "entry_hash", 64, 64);
                    core.Remove("entry_hash");
                    string computed = R7Hash.Bytes(R7Json.Encode(core));
                    if (!R7Hash.FixedTimeEquals(recorded, computed)) throw new InvalidDataException("LEDGER_ENTRY_HASH_MISMATCH");
                    R7LedgerRecord record = Record(payload, file.Measurement.Sha256);
                    records.Add(record);
                    expectedPrior = recorded;
                    expectedSequence++;
                }
            }
            if (records.Count == 0)
            {
                if (!createGenesis || signer == null || !R7Hash.IsLowerSha256(genesisContentAddress)) throw new InvalidDataException("LEDGER_GENESIS_MISSING");
                sequence = 0;
                rootHash = R7Fixed.ZeroHash;
                checkpointRecoveryReason = String.Empty;
                Append("UPGRADE_LEDGER_GENESIS", Guid.NewGuid().ToString("D"), ledgerId, genesisContentAddress, "1.0.0");
                return;
            }
            sequence = records.Count;
            rootHash = expectedPrior;
            ValidateCheckpoint();
        }

        private void ValidateCheckpoint()
        {
            string path = Path.Combine(root, "checkpoint.json");
            checkpointRecoveryReason = String.Empty;
            checkpointIdentity = R7Fixed.ZeroHash;
            R7VerifiedFile checkpoint;
            if (!R7SafeFile.TryOpen(path, path, root, null, expectedFileOwnerSid, null, expectedVolumeIdentity, out checkpoint))
            {
                checkpointRecoveryReason = "CHECKPOINT_MISSING";
                AddPendingCheckpointReason();
                return;
            }
            using (checkpoint)
            {
                checkpointIdentity = checkpoint.Measurement.Sha256;
                try
                {
                    SortedDictionary<string, object> payload = R7Crypto.VerifyEnvelope(checkpoint.Bytes, publicKeyIdentity, verifier);
                    R7Json.ExactKeys(payload, "issue_time", "ledger_id", "public_key_identity", "root_hash", "schema_version", "sequence", "service_sid");
                    long checkpointSequence = R7Json.Integer(payload, "sequence", 1, Int64.MaxValue);
                    if (!String.Equals(R7Json.String(payload, "ledger_id", 64, 64), ledgerId, StringComparison.Ordinal) ||
                        !String.Equals(R7Json.String(payload, "public_key_identity", 64, 64), publicKeyIdentity, StringComparison.Ordinal) ||
                        !String.Equals(R7Json.String(payload, "service_sid", 1, 256), serviceSid, StringComparison.Ordinal)) throw new InvalidDataException("CHECKPOINT_IDENTITY_MISMATCH");
                    if (checkpointSequence == sequence && String.Equals(R7Json.String(payload, "root_hash", 64, 64), rootHash, StringComparison.Ordinal))
                    {
                        AddPendingCheckpointReason();
                        return;
                    }
                    if (checkpointSequence >= 1 && checkpointSequence < sequence)
                    {
                        R7LedgerRecord prefix = records[(int)checkpointSequence - 1];
                        if (String.Equals(R7Json.String(payload, "root_hash", 64, 64), prefix.EntryHash, StringComparison.Ordinal))
                        {
                            checkpointRecoveryReason = "STALE_VALID_CHECKPOINT_AT_" + checkpointSequence.ToString(CultureInfo.InvariantCulture);
                            AddPendingCheckpointReason();
                            return;
                        }
                    }
                    checkpointRecoveryReason = "CHECKPOINT_NOT_A_VALID_CHAIN_PREFIX";
                }
                catch (Exception exception)
                {
                    checkpointRecoveryReason = "CHECKPOINT_INVALID_" + exception.GetType().Name;
                }
            }
            AddPendingCheckpointReason();
        }

        private void AddPendingCheckpointReason()
        {
            if (pendingCheckpointArtifacts.Count == 0) return;
            List<string> values = new List<string>();
            foreach (R7CheckpointArtifact artifact in pendingCheckpointArtifacts) values.Add(artifact.Name + "|" + artifact.Identity);
            values.Sort(StringComparer.Ordinal);
            string identity = R7Hash.Bytes(new UTF8Encoding(false, true).GetBytes(String.Join("\n", values.ToArray())));
            string pending = "ORPHAN_CHECKPOINT_TEMP_" + identity;
            checkpointRecoveryReason = String.IsNullOrEmpty(checkpointRecoveryReason) ? pending : checkpointRecoveryReason + "__AND__" + pending;
        }

        private static bool IsLedgerEntryName(string name)
        {
            if (name == null || name.Length != 31 || !name.EndsWith(".entry.json", StringComparison.Ordinal)) return false;
            for (int index = 0; index < 20; index++) if (name[index] < '0' || name[index] > '9') return false;
            return true;
        }

        private static bool IsPendingCheckpointName(string name)
        {
            const string prefix = "checkpoint.json.new.";
            if (name == null || name.Length != prefix.Length + 32 || !name.StartsWith(prefix, StringComparison.Ordinal)) return false;
            for (int index = prefix.Length; index < name.Length; index++)
            {
                char value = name[index];
                if (!((value >= '0' && value <= '9') || (value >= 'a' && value <= 'f'))) return false;
            }
            return true;
        }

        private void WriteCheckpoint(string schemaVersion)
        {
            SortedDictionary<string, object> payload = R7Json.Object(
                "issue_time", DateTimeOffset.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture),
                "ledger_id", ledgerId,
                "public_key_identity", publicKeyIdentity,
                "root_hash", rootHash,
                "schema_version", schemaVersion,
                "sequence", sequence,
                "service_sid", serviceSid);
            byte[] bytes = R7Json.Encode(R7Crypto.Envelope(payload, publicKeyIdentity, signer));
            R7DurableFile.Replace(Path.Combine(root, "checkpoint.json"), bytes);
            using (R7VerifiedFile persisted = R7SafeFile.Open(Path.Combine(root, "checkpoint.json"), Path.Combine(root, "checkpoint.json"), root, R7Hash.Bytes(bytes), expectedFileOwnerSid, null, expectedVolumeIdentity)) { }
            checkpointIdentity = R7Hash.Bytes(bytes);
            checkpointRecoveryReason = String.Empty;
        }

        private static R7LedgerRecord Record(SortedDictionary<string, object> payload, string identity)
        {
            return new R7LedgerRecord
            {
                Sequence = R7Json.Integer(payload, "sequence", 1, Int64.MaxValue),
                EntryHash = R7Json.String(payload, "entry_hash", 64, 64),
                EntryIdentity = identity,
                Operation = R7Json.String(payload, "operation", 1, 256),
                SubjectId = R7Json.String(payload, "subject_id", 0, 4096),
                ContentAddress = R7Json.String(payload, "content_address", 1, 4096),
                SchemaVersion = R7Json.String(payload, "schema_version", 1, 128),
                RequestNonce = R7Json.String(payload, "request_nonce", 0, 256),
                IssueTime = R7Json.String(payload, "issue_time", 1, 128),
                Payload = payload
            };
        }
    }

    internal sealed class R7ObjectStore
    {
        private readonly string root;
        private readonly string expectedOwnerSid;
        private readonly string expectedVolumeIdentity;
        internal R7ObjectStore(string fixedRoot) : this(fixedRoot, null, null) { }
        internal R7ObjectStore(string fixedRoot, string ownerSid, string volumeIdentity)
        {
            root = Path.GetFullPath(fixedRoot);
            expectedOwnerSid = ownerSid;
            expectedVolumeIdentity = volumeIdentity;
            R7SafeFile.MeasureDirectory(root, root, expectedOwnerSid == null ? null : R7Fixed.SystemSid, null, expectedVolumeIdentity);
            ValidateInventory();
        }

        private void ValidateInventory()
        {
            if (Directory.GetDirectories(root, "*", SearchOption.TopDirectoryOnly).Length != 0) throw new InvalidDataException("OBJECT_STORE_DIRECTORY_ENTRY_REJECTED");
            string[] files = Directory.GetFiles(root, "*", SearchOption.TopDirectoryOnly);
            Array.Sort(files, StringComparer.Ordinal);
            foreach (string path in files)
            {
                string name = Path.GetFileName(path);
                if (name.Length != 69 || !name.EndsWith(".json", StringComparison.Ordinal)) throw new InvalidDataException("OBJECT_STORE_FILENAME_INVALID|" + name);
                string identity = name.Substring(0, 64);
                if (!R7Hash.IsLowerSha256(identity)) throw new InvalidDataException("OBJECT_STORE_FILENAME_INVALID|" + name);
                using (R7VerifiedFile file = R7SafeFile.Open(path, Path.Combine(root, name), root, identity, expectedOwnerSid, null, expectedVolumeIdentity)) R7Json.ParseCanonicalObject(file.Bytes);
            }
        }

        internal string Put(IDictionary<string, object> value)
        {
            byte[] bytes = R7Json.Encode(value);
            string identity = R7Hash.Bytes(bytes);
            string path = Path.Combine(root, identity + ".json");
            R7VerifiedFile existing;
            if (R7SafeFile.TryOpen(path, path, root, identity, expectedOwnerSid, null, expectedVolumeIdentity, out existing))
            {
                existing.Dispose();
                return identity;
            }
            try { R7DurableFile.CreateNew(path, bytes); }
            catch (IOException exception)
            {
                if (!R7DurableFile.IsAlreadyExists(exception)) throw;
                if (!R7SafeFile.TryOpen(path, path, root, identity, expectedOwnerSid, null, expectedVolumeIdentity, out existing)) throw;
                existing.Dispose();
            }
            using (R7VerifiedFile verify = R7SafeFile.Open(path, path, root, identity, expectedOwnerSid, null, expectedVolumeIdentity)) { }
            return identity;
        }

        internal SortedDictionary<string, object> Get(string identity)
        {
            if (!R7Hash.IsLowerSha256(identity)) throw new R7ProtocolException("OBJECT_IDENTITY_INVALID");
            string path = Path.Combine(root, identity + ".json");
            using (R7VerifiedFile file = R7SafeFile.Open(path, path, root, identity, expectedOwnerSid, null, expectedVolumeIdentity)) return R7Json.ParseCanonicalObject(file.Bytes);
        }

        internal bool Exists(string identity)
        {
            if (!R7Hash.IsLowerSha256(identity)) return false;
            string path = Path.Combine(root, identity + ".json");
            R7VerifiedFile existing;
            if (!R7SafeFile.TryOpen(path, path, root, identity, expectedOwnerSid, null, expectedVolumeIdentity, out existing)) return false;
            existing.Dispose();
            return true;
        }
    }
}
