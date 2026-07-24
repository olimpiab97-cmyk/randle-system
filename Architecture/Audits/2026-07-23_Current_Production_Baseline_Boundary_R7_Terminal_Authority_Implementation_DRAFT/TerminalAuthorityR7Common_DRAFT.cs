using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using System.Web.Script.Serialization;
using Microsoft.Win32.SafeHandles;

namespace RandleAI.TerminalAuthority
{
    internal static class R7Constants
    {
        internal const string InterfaceVersion = "3.0.0-DRAFT";
        internal const string SchemaVersion = "7.1.0-DRAFT";
        internal const string ServiceName = "RandleTerminalAuthority";
        internal const string ServiceSid = "S-1-5-80-1950096479-1020125124-2173088643-1633316353-879035948";
        internal const string OperatorSid = "S-1-5-21-4259795780-3461844753-1172372902-1001";
        internal const string SystemSid = "S-1-5-18";
        internal const string R6Commit = "87d066eb16d7fe0b6a1677ea7739c5c2ead4ad94";
        internal const string R6Tree = "f9891562ea09d011d4d9803d9cf64b88ff1f2dbf";
        internal const string R7IncompleteCommit = "06c6805ed52a0d539a73088c097c60dec335462a";
        internal const string R7IncompleteBlob = "1be3b0b5f15ac8e68b88202e0e9d3787b69d1856";
        internal const string R7BlockedCommit = "8ec5697b3c6fd9d93b972113b7e79d033b4cb1f6";
        internal const string R7BlockedBlob = "dfa98a89049b9596387143c002252d91d608fbfc";
        internal const string ProvisioningCommit = "bb04ac54fb328516d0c785f4e6551e6a20d73759";
        internal const string ProvisioningTree = "b25b41d9cfb5a0dbfdb271e4519734f60a11ad80";
        internal const string ProvisioningAttestationIdentity = "63494d8840af241b7916e8ef75e5eae350ea31d8bafbcd0dc1a790f8945e7697";
        internal const string ProvisioningPolicySha256 = "675a9fa9c761b2738e6b7115366eaf8bb001f6f9ff1f3fb598db2f68ad57fc19";
        internal const string PublicKeyIdentity = "b84a4de14577580c64ff5b2446f120aa6f9ea60faa2cb5465b495282f0273285";
        internal const string SignatureAlgorithm = "RSA-PSS-SHA256";
        internal const string LedgerId = "899e4db2b5c0f4ad58a09c682324a2ee9e5d7e2f180822ce9300922e56741d52";
        internal const string ZeroHash = "0000000000000000000000000000000000000000000000000000000000000000";
        internal const string InstallRoot = @"C:\Program Files\RandleAI\TerminalAuthority";
        internal const string ServiceExecutablePath = @"C:\Program Files\RandleAI\TerminalAuthority\RandleTerminalAuthority.exe";
        internal const string WorkerExecutablePath = @"C:\Program Files\RandleAI\TerminalAuthority\RandleTerminalAuthorityR7Worker.exe";
        internal const string StateRoot = @"C:\ProgramData\RandleAI\TerminalAuthority";
        internal const string ConfigRoot = @"C:\ProgramData\RandleAI\TerminalAuthority\Config";
        internal const string LedgerRoot = @"C:\ProgramData\RandleAI\TerminalAuthority\Ledger";
        internal const string TrustRoot = @"C:\ProgramData\RandleAI\TerminalAuthority\Trust";
        internal const string EvidenceRoot = @"C:\ProgramData\RandleAI\TerminalAuthority\Evidence";
        internal const string ReceiptRoot = @"C:\ProgramData\RandleAI\TerminalAuthority\Receipts";
        internal const string ReconciliationRoot = @"C:\ProgramData\RandleAI\TerminalAuthority\Reconciliations";
        internal const string ResponseRoot = @"C:\ProgramData\RandleAI\TerminalAuthority\Responses";
        internal const string SessionRoot = @"C:\ProgramData\RandleAI\TerminalAuthority\Sessions";
        internal const string RunEvidenceRoot = @"C:\ProgramData\RandleAI\TerminalAuthority\Evidence\Runs";
        internal const string PolicyPath = @"C:\ProgramData\RandleAI\TerminalAuthority\Config\r7_terminal_authority_policy.json";
        internal const string CaseDefinitionPath = @"C:\ProgramData\RandleAI\TerminalAuthority\Config\R7Authorities\r7_real_case_definitions.json";
        internal const string ExpectationPath = @"C:\ProgramData\RandleAI\TerminalAuthority\Config\R7Authorities\r7_independent_expectations.json";
        internal const string CorrectionRequirementsPath = @"C:\ProgramData\RandleAI\TerminalAuthority\Config\R7Authorities\R7I_B01_CORRECTION_REQUIREMENTS.md";
        internal const string AdversarialProbePath = @"C:\ProgramData\RandleAI\TerminalAuthority\Config\R7Authorities\r7i_b01_adversarial_probes.json";
        internal const string SubjectRepositoryPath = @"C:\ProgramData\RandleAI\TerminalAuthority\Config\R7ExecutionSubjectRepository";
        internal const string SubjectTemporaryRoot = @"C:\ProgramData\RandleAI\TerminalAuthority\Evidence\R7ExecutionSubjectTemp";
        internal const string FixtureReceiptRoot = @"C:\ProgramData\RandleAI\TerminalAuthority\Evidence\R7FixtureProcessReceipts";
        internal const string PythonRuntimeManifestPath = @"C:\ProgramData\RandleAI\TerminalAuthority\Config\R7Authorities\r7_python_runtime_manifest.json";
        internal const string SubjectPythonPath = @"C:\Program Files\RandleAI\TerminalAuthority\PythonRuntime\python.exe";
        internal const string SubjectLauncherPath = @"C:\Program Files\RandleAI\TerminalAuthority\RandleTerminalAuthorityR7SubjectLauncher.exe";
        internal const string SubjectFixtureHostPath = @"C:\Program Files\RandleAI\TerminalAuthority\R7ExecutionSubject\powershell.exe";
        internal const string SubjectServicePath = @"C:\Program Files\RandleAI\TerminalAuthority\R7ExecutionSubject\external_authority_service_R7_DRAFT.py";
        internal const string SubjectDirectInterfacePath = @"C:\Program Files\RandleAI\TerminalAuthority\R7ExecutionSubject\r7_direct_interfaces_DRAFT.py";
        internal const string SubjectVerifierPath = @"C:\Program Files\RandleAI\TerminalAuthority\R7ExecutionSubject\r7_authority_verifier_DRAFT.py";
        internal const string SubjectLedgerPath = @"C:\Program Files\RandleAI\TerminalAuthority\R7ExecutionSubject\durable_ledger_R7_DRAFT.py";
        internal const string SubjectGovernedAccessPath = @"C:\Program Files\RandleAI\TerminalAuthority\R7ExecutionSubject\governed_file_access_DRAFT.py";
        internal const string HistoricalLogPath = @"C:\ProgramData\RandleAI\TerminalAuthority\Config\R6Evidence\18_broad_captured_entry_agent_pytest.log";
        internal const string RetainedEvidenceRoot = @"C:\ProgramData\RandleAI\TerminalAuthority\Config\R6Evidence";
        internal const string PipeName = "RandleAI.TerminalAuthority.v1";
        internal const int MaximumMessageBytes = 65536;
        internal const int RequiredCaseCount = 178;
        internal const int RequiredParserCount = 1;
        internal const int RequiredRecorderCount = 1;
        internal const int RequiredComparatorCount = 1;
        internal const int RequiredValidatorCount = 1;
        internal const int RequiredMandatoryCount = 1;
        internal const int RequiredEnforcementCount = 1;
        internal const string ThreatModel = "FILTERED_INTERACTIVE_USER_HOSTILE_ELEVATED_ADMIN_AND_KERNEL_OUT_OF_SCOPE";

        internal const string CaseDefinitionGitBlob = "dae357d801cabdde7ca8a314c83380984161e687";
        internal const string CaseDefinitionSha256 = "58d6c043b857b6950d375724ef1f05b695028a3778ee47067284148c477b9214";
        internal const long CaseDefinitionSize = 995804;
        internal const string ExpectationGitBlob = "c21ea8f5ab4b54fc0d0638e9bb20df83c8a88f1d";
        internal const string ExpectationSha256 = "7563a8b8af74f15ad226d61015d0946867fa1d18495143e8206600f1c3c81005";
        internal const long ExpectationSize = 285399;
        internal const string AdversarialProbeGitBlob = "4694125882526d5bd9abb14b394d17d463d32564";
        internal const string AdversarialProbeSha256 = "f5e4d9ac5c68a9190921bdec0b5fee88d11957d47a9d68dd2f95f02eef30ba9d";
        internal const long AdversarialProbeSize = 6777;
        internal const string SubjectCommit = "f0cfbce97e913a133530dd66a70326b1e03a0fb6";
        internal const string SubjectTree = "02324c2b2dc3415fa2dbe21144e12ab667bf40d9";
        internal const string SubjectServiceGitBlob = "cc6099f244fae8d052927b3abddddd702c09b505";
        internal const string SubjectServiceSha256 = "12fcf7209567e565b1314dd7ac0389bbb42da794fc08810ac0fe7d70f407cb57";
        internal const string SubjectDirectInterfaceGitBlob = "3420572d96a65ffb8feb708657fdfa95eb1e08a4";
        internal const string SubjectDirectInterfaceSha256 = "69e18f2cb7273c09db0479aa5318c69a3f1e2104476f1b166e38db7f75a38877";
        internal const string SubjectVerifierSha256 = "75ca67e6fb7e1d39805cf1be46a36a7b3f550cd877044f8ea350549503ab5461";
        internal const string SubjectLedgerSha256 = "ea58dea2c9385f20c2d0761b3fd75670980d4214a168e6be2ab9fb1486313cf7";
        internal const string SubjectGovernedAccessSha256 = "716c4168dfd6ea37ac9d01d811f3e687e9136b38dc2fff5cb06f1159979e9fdc";
        internal const string SubjectPythonSha256 = "624bbc0586d8855633b875e911883bbef8a0e8b8711e11126df480dd86f54181";
        internal const string SubjectLauncherSha256 = "3445e5effd6398b648afa6898391f4e2b5de34f696dd91bfedc2dc29be4e3877";
        internal const string SubjectFixtureHostSha256 = "7a82bab5acfa36555d0e3b9cf29084101f8276b4ceba93cd48cc1e85fadf1454";
        internal const string PythonRuntimeManifestGitBlob = "950b69e03584f60202eeab494bab11ab9704d114";
        internal const string PythonRuntimeManifestSha256 = "35140cb03dad5984572fbccbb99fbfc20a5496440411c5ad21a690656a7471f2";
        internal const long PythonRuntimeManifestSize = 439239;
        internal const string PythonRuntimeRootIdentity = "1e545dc3e7a1e63563674d5b0774329ab63d54bf61d44bcce7ea7dc5d26d1bc0";
        internal const string CorrectionRequirementsGitBlob = "b781cb5cfed4c2ccc7c91c55ca22f73fb01051a7";
        internal const string CorrectionRequirementsSha256 = "cfeae6afaa86a851b6b44a5bec65922879114d641ffcc24e37d69d328cbe5756";
        internal const long CorrectionRequirementsSize = 3788;

        internal const string R6SpecificationSha256 = "7c5fc26a75dff3fe3d23167424d6d4c12ac04e9fda21fc20cce63e04000399b6";
        internal const string R6AuthorityBindingsSha256 = "11c38174eb46e4d9487a0affb685eb673b7884c87a6911b1240a800e1f7a6f8d";
        internal const string R6CaseDefinitionSha256 = "8118a0aee035550535b4eced560b864678b79858a250d3f98caf42618178bf5d";
        internal const string R6CaseSetIdentity = "e241fa6ff514fcb13669b8025d5922be9cb7800c3018e7590e67234c4a815cee";
        internal const string R6ExpectationsSha256 = "fb1aeeac7f586b8275b8f1e8794a31b4374f881b8b318c394ce9d28397c49b53";
        internal const string R6ValidatorLockSha256 = "38540c638f888b9a458398e68f8ed927d00a3f4ec36ee35e782a7803484d8334";
        internal const string R6MandatoryAuthoritySha256 = "fbf4bc63cd5002261cc42b390a469a1a2cfcf50e640c8d934ca3d2f4639ab900";
        internal const string R6TraceSha256 = "ed8a2401a3c5b08396a7a484ada1030df4cb915b70f4b01bd64bd24043f50f49";
        internal const string R6ReviewEvidenceSha256 = "72edd432d71542367f82e636f948ccdbbed0dc63a778fd6ece7d7850081c9be9";
        internal const string R6CompatibilityEvidenceSha256 = "14dd26a54685f4abfa593fe02bb4efab47f2358ed6a7142416a1f8578bb7f9a4";
        internal const string HistoricalLogSha256 = "6f1b876c814b25d27f5ef8b4cfe3a66c4b0e847263fec784c56896dc8ff3194a";
        internal const long HistoricalLogSize = 2226181;
    }

    internal sealed class R7LedgerState
    {
        internal long Sequence;
        internal string RootHash;
        internal string CheckpointIdentity;
        internal string GenesisIdentity;
        internal readonly List<IDictionary<string, object>> Payloads = new List<IDictionary<string, object>>();
        internal readonly List<string> EntryIdentities = new List<string>();
    }

    internal static class R7Support
    {
        internal static string Timestamp()
        {
            return DateTimeOffset.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture);
        }

        internal static string RandomHex(int byteCount)
        {
            byte[] bytes = new byte[byteCount];
            using (RandomNumberGenerator generator = RandomNumberGenerator.Create()) generator.GetBytes(bytes);
            return CryptoUtil.ToHex(bytes);
        }

        internal static bool IsLowerHex(string value, int length)
        {
            if (value == null || value.Length != length) return false;
            for (int index = 0; index < value.Length; index++)
            {
                char character = value[index];
                if (!((character >= '0' && character <= '9') || (character >= 'a' && character <= 'f'))) return false;
            }
            return true;
        }

        internal static string RequireLowerHex(IDictionary<string, object> value, string key, int length)
        {
            string result = StrictJson.RequireString(value, key);
            if (!IsLowerHex(result, length)) throw new InvalidDataException(key + " is not canonical lowercase hexadecimal");
            return result;
        }

        internal static string RequireEnum(IDictionary<string, object> value, string key, params string[] allowed)
        {
            string result = StrictJson.RequireString(value, key);
            foreach (string item in allowed) if (String.Equals(result, item, StringComparison.Ordinal)) return result;
            throw new InvalidDataException(key + " is outside its closed vocabulary");
        }

        internal static long RequireLong(IDictionary<string, object> value, string key)
        {
            object raw;
            if (!value.TryGetValue(key, out raw) || raw == null) throw new InvalidDataException("missing integer: " + key);
            try { return Convert.ToInt64(raw, CultureInfo.InvariantCulture); }
            catch (Exception exception) { throw new InvalidDataException("invalid integer: " + key, exception); }
        }

        internal static bool RequireBool(IDictionary<string, object> value, string key)
        {
            object raw;
            if (!value.TryGetValue(key, out raw) || !(raw is bool)) throw new InvalidDataException("invalid boolean: " + key);
            return (bool)raw;
        }

        internal static object[] RequireArray(IDictionary<string, object> value, string key)
        {
            object raw;
            if (!value.TryGetValue(key, out raw) || !(raw is object[])) throw new InvalidDataException("invalid array: " + key);
            return (object[])raw;
        }

        internal static string Sha256Utf8(string value)
        {
            return CryptoUtil.Sha256Hex(new UTF8Encoding(false, true).GetBytes(value));
        }

        internal static string GitBlobId(byte[] bytes)
        {
            byte[] header = Encoding.ASCII.GetBytes("blob " + bytes.Length.ToString(CultureInfo.InvariantCulture) + "\0");
            byte[] value = new byte[header.Length + bytes.Length];
            Buffer.BlockCopy(header, 0, value, 0, header.Length);
            Buffer.BlockCopy(bytes, 0, value, header.Length, bytes.Length);
            using (SHA1 sha1 = SHA1.Create()) return CryptoUtil.ToHex(sha1.ComputeHash(value));
        }

        internal static byte[] ReadPinnedBytes(string path, string rawSha256, string gitBlob, long expectedSize)
        {
            string full = Path.GetFullPath(path);
            string configRoot = Path.GetFullPath(R7Constants.ConfigRoot).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            if (!full.StartsWith(configRoot, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("pinned authority escaped config root");
            byte[] bytes = File.ReadAllBytes(full);
            if (bytes.LongLength != expectedSize || !String.Equals(CryptoUtil.Sha256Hex(bytes), rawSha256, StringComparison.Ordinal) ||
                !String.Equals(GitBlobId(bytes), gitBlob, StringComparison.Ordinal))
                throw new InvalidDataException("pinned authority identity mismatch");
            return bytes;
        }

        internal static IDictionary<string, object> ReadCaseAuthority()
        {
            return ParseCanonicalObject(ReadPinnedBytes(R7Constants.CaseDefinitionPath, R7Constants.CaseDefinitionSha256, R7Constants.CaseDefinitionGitBlob, R7Constants.CaseDefinitionSize));
        }

        internal static IDictionary<string, object> ReadExpectationAuthority()
        {
            return ParseCanonicalObject(ReadPinnedBytes(R7Constants.ExpectationPath, R7Constants.ExpectationSha256, R7Constants.ExpectationGitBlob, R7Constants.ExpectationSize));
        }

        internal static IDictionary<string, object> ReadAdversarialProbeAuthority()
        {
            return ParseCanonicalObject(ReadPinnedBytes(R7Constants.AdversarialProbePath, R7Constants.AdversarialProbeSha256, R7Constants.AdversarialProbeGitBlob, R7Constants.AdversarialProbeSize));
        }

        internal static string ContentLocator(string kind, string identity)
        {
            if (!IsLowerHex(identity, 64)) throw new InvalidDataException("locator identity is invalid");
            if (kind != "evidence" && kind != "terminal" && kind != "reconciliation") throw new InvalidDataException("locator kind is invalid");
            return "randle-" + kind + "://sha256/" + identity;
        }

        internal static string ParseLocator(string locator, string expectedKind)
        {
            if (locator == null) throw new InvalidDataException("locator missing");
            string prefix = "randle-" + expectedKind + "://sha256/";
            if (!locator.StartsWith(prefix, StringComparison.Ordinal)) throw new InvalidDataException("locator scheme rejected");
            string identity = locator.Substring(prefix.Length);
            if (!IsLowerHex(identity, 64) || !String.Equals(locator, prefix + identity, StringComparison.Ordinal))
                throw new InvalidDataException("locator is not canonical");
            return identity;
        }

        internal static byte[] ReadContentAddressed(string locator, string kind)
        {
            string identity = ParseLocator(locator, kind);
            string root = kind == "terminal" ? R7Constants.ReceiptRoot :
                          kind == "reconciliation" ? R7Constants.ReconciliationRoot : R7Constants.EvidenceRoot;
            string json = Path.Combine(root, identity + ".json");
            string binary = Path.Combine(root, identity + ".bin");
            bool hasJson = File.Exists(json);
            bool hasBinary = File.Exists(binary);
            if (hasJson == hasBinary) throw new InvalidDataException("locator resolution is ambiguous or missing");
            string path = hasJson ? json : binary;
            string full = Path.GetFullPath(path);
            string expectedRoot = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            if (!full.StartsWith(expectedRoot, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("locator escaped fixed root");
            byte[] bytes = File.ReadAllBytes(full);
            if (!String.Equals(CryptoUtil.Sha256Hex(bytes), identity, StringComparison.Ordinal))
                throw new InvalidDataException("content-address mismatch");
            return bytes;
        }

        internal static IDictionary<string, object> ParseCanonicalObject(byte[] bytes)
        {
            if (bytes == null || bytes.Length == 0 || bytes.Length > 16 * 1024 * 1024)
                throw new InvalidDataException("authority JSON size rejected");
            string text = new UTF8Encoding(false, true).GetString(bytes);
            string canonicalText = text.EndsWith("\n", StringComparison.Ordinal) && !text.EndsWith("\r\n", StringComparison.Ordinal)
                ? text.Substring(0, text.Length - 1)
                : text;
            JavaScriptSerializer serializer = new JavaScriptSerializer();
            serializer.MaxJsonLength = 16 * 1024 * 1024;
            object parsed = serializer.DeserializeObject(canonicalText);
            IDictionary<string, object> value = parsed as IDictionary<string, object>;
            if (value == null) throw new InvalidDataException("authority JSON root must be an object");
            ValidateCanonicalPlain(value, 0);
            if (!String.Equals(CanonicalJson.Serialize(value), canonicalText, StringComparison.Ordinal))
                throw new InvalidDataException("JSON is not in canonical serialization");
            return value;
        }

        private static void ValidateCanonicalPlain(object value, int depth)
        {
            if (depth > 32) throw new InvalidDataException("authority JSON nesting is too deep");
            if (value == null || value is string || value is bool || value is int || value is long || value is decimal) return;
            if (value is double || value is float) throw new InvalidDataException("floating-point values are forbidden");
            IDictionary<string, object> dictionary = value as IDictionary<string, object>;
            if (dictionary != null)
            {
                HashSet<string> keys = new HashSet<string>(StringComparer.Ordinal);
                foreach (KeyValuePair<string, object> item in dictionary)
                {
                    if (item.Key == null || !item.Key.IsNormalized(NormalizationForm.FormC) || !keys.Add(item.Key))
                        throw new InvalidDataException("invalid or duplicate authority JSON key");
                    ValidateCanonicalPlain(item.Value, depth + 1);
                }
                return;
            }
            object[] array = value as object[];
            if (array != null)
            {
                foreach (object item in array) ValidateCanonicalPlain(item, depth + 1);
                return;
            }
            throw new InvalidDataException("non-plain authority JSON value");
        }

        internal static IDictionary<string, object> VerifySignedEnvelope(byte[] bytes, RSA verifier)
        {
            IDictionary<string, object> envelope = ParseCanonicalObject(bytes);
            StrictJson.RequireExactKeys(envelope, "payload", "public_key_identity", "signature", "signature_algorithm");
            if (!String.Equals(StrictJson.RequireString(envelope, "public_key_identity"), R7Constants.PublicKeyIdentity, StringComparison.Ordinal))
                throw new InvalidDataException("signed envelope key rejected");
            if (!String.Equals(StrictJson.RequireString(envelope, "signature_algorithm"), R7Constants.SignatureAlgorithm, StringComparison.Ordinal))
                throw new InvalidDataException("signed envelope algorithm rejected");
            IDictionary<string, object> payload = StrictJson.RequireObject(envelope, "payload");
            byte[] signature;
            try { signature = Convert.FromBase64String(StrictJson.RequireString(envelope, "signature")); }
            catch (FormatException exception) { throw new InvalidDataException("signature encoding rejected", exception); }
            if (signature.Length == 0 || !CryptoUtil.Verify(verifier, CanonicalJson.SerializeBytes(payload), signature))
                throw new CryptographicException("signed envelope verification failed");
            return payload;
        }

        internal static byte[] CreateSignedEnvelope(IDictionary<string, object> payload, RSA signer)
        {
            byte[] signature = CryptoUtil.Sign(signer, CanonicalJson.SerializeBytes(payload));
            SortedDictionary<string, object> envelope = new SortedDictionary<string, object>(StringComparer.Ordinal);
            envelope["payload"] = payload;
            envelope["public_key_identity"] = R7Constants.PublicKeyIdentity;
            envelope["signature"] = Convert.ToBase64String(signature);
            envelope["signature_algorithm"] = R7Constants.SignatureAlgorithm;
            return CanonicalJson.SerializeBytes(envelope);
        }

        internal static void DurableCreate(string path, byte[] bytes)
        {
            string parent = Path.GetDirectoryName(path);
            Directory.CreateDirectory(parent);
            using (FileStream stream = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.Read, 4096, FileOptions.WriteThrough))
            {
                stream.Write(bytes, 0, bytes.Length);
                stream.Flush(true);
            }
        }

        internal static void DurableReplace(string path, byte[] bytes)
        {
            string temporary = path + ".new." + Guid.NewGuid().ToString("N");
            DurableCreate(temporary, bytes);
            if (File.Exists(path)) File.Replace(temporary, path, null, true);
            else File.Move(temporary, path);
        }

        internal static string StoreContentAddressed(string root, byte[] bytes, string extension)
        {
            if (extension != ".json" && extension != ".bin") throw new InvalidDataException("content extension rejected");
            string identity = CryptoUtil.Sha256Hex(bytes);
            string path = Path.Combine(root, identity + extension);
            if (!File.Exists(path)) DurableCreate(path, bytes);
            else if (!String.Equals(CryptoUtil.Sha256File(path), identity, StringComparison.Ordinal))
                throw new InvalidDataException("existing content-addressed bytes mismatch");
            return identity;
        }

        internal static R7LedgerState VerifyLedger(RSA verifier)
        {
            string[] paths = Directory.GetFiles(R7Constants.LedgerRoot, "*.entry.json", SearchOption.TopDirectoryOnly);
            Array.Sort(paths, StringComparer.Ordinal);
            if (paths.Length == 0) throw new InvalidDataException("ledger has no genesis");
            R7LedgerState state = new R7LedgerState();
            state.RootHash = R7Constants.ZeroHash;
            long expectedSequence = 1;
            foreach (string path in paths)
            {
                byte[] bytes = File.ReadAllBytes(path);
                IDictionary<string, object> payload = VerifySignedEnvelope(bytes, verifier);
                StrictJson.RequireExactKeys(payload, "content_address", "entry_hash", "issue_time", "ledger_id", "operation", "prior_entry_hash", "public_key_identity", "request_nonce", "schema_version", "sequence", "service_sid", "subject_id");
                long sequence = RequireLong(payload, "sequence");
                if (sequence != expectedSequence) throw new InvalidDataException("ledger sequence rejected");
                if (!String.Equals(StrictJson.RequireString(payload, "ledger_id"), R7Constants.LedgerId, StringComparison.Ordinal)) throw new InvalidDataException("ledger identity rejected");
                if (!String.Equals(StrictJson.RequireString(payload, "prior_entry_hash"), state.RootHash, StringComparison.Ordinal)) throw new InvalidDataException("ledger prior hash rejected");
                if (!String.Equals(StrictJson.RequireString(payload, "public_key_identity"), R7Constants.PublicKeyIdentity, StringComparison.Ordinal)) throw new InvalidDataException("ledger key rejected");
                if (!String.Equals(StrictJson.RequireString(payload, "service_sid"), R7Constants.ServiceSid, StringComparison.Ordinal)) throw new InvalidDataException("ledger service rejected");
                SortedDictionary<string, object> core = new SortedDictionary<string, object>(payload, StringComparer.Ordinal);
                string recorded = StrictJson.RequireString(core, "entry_hash");
                core.Remove("entry_hash");
                string computed = CryptoUtil.Sha256Hex(CanonicalJson.SerializeBytes(core));
                if (!String.Equals(recorded, computed, StringComparison.Ordinal)) throw new InvalidDataException("ledger entry hash rejected");
                if (expectedSequence == 1)
                {
                    string expectedGenesis = CryptoUtil.Sha256Hex(Encoding.UTF8.GetBytes(R7Constants.PublicKeyIdentity + "|" + R7Constants.ProvisioningPolicySha256 + "|" + R7Constants.LedgerId));
                    if (!String.Equals(StrictJson.RequireString(payload, "operation"), "LEDGER_GENESIS", StringComparison.Ordinal) ||
                        !String.Equals(StrictJson.RequireString(payload, "content_address"), expectedGenesis, StringComparison.Ordinal))
                        throw new InvalidDataException("ledger genesis authority rejected");
                    state.GenesisIdentity = recorded;
                }
                state.Payloads.Add(payload);
                state.EntryIdentities.Add(CryptoUtil.Sha256Hex(bytes));
                state.RootHash = recorded;
                state.Sequence = sequence;
                expectedSequence++;
            }

            string checkpointPath = Path.Combine(R7Constants.LedgerRoot, "checkpoint.json");
            byte[] checkpointBytes = File.ReadAllBytes(checkpointPath);
            IDictionary<string, object> checkpoint = VerifySignedEnvelope(checkpointBytes, verifier);
            StrictJson.RequireExactKeys(checkpoint, "issue_time", "ledger_id", "public_key_identity", "root_hash", "schema_version", "sequence", "service_sid");
            if (RequireLong(checkpoint, "sequence") != state.Sequence) throw new InvalidDataException("checkpoint sequence rejected");
            if (!String.Equals(StrictJson.RequireString(checkpoint, "root_hash"), state.RootHash, StringComparison.Ordinal)) throw new InvalidDataException("checkpoint root rejected");
            if (!String.Equals(StrictJson.RequireString(checkpoint, "ledger_id"), R7Constants.LedgerId, StringComparison.Ordinal)) throw new InvalidDataException("checkpoint ledger rejected");
            state.CheckpointIdentity = CryptoUtil.Sha256Hex(checkpointBytes);
            return state;
        }

        internal static IDictionary<string, object> FindLedgerEntry(R7LedgerState state, string operation, string contentAddress)
        {
            IDictionary<string, object> found = null;
            foreach (IDictionary<string, object> payload in state.Payloads)
            {
                if (String.Equals(StrictJson.RequireString(payload, "operation"), operation, StringComparison.Ordinal) &&
                    String.Equals(StrictJson.RequireString(payload, "content_address"), contentAddress, StringComparison.Ordinal))
                {
                    if (found != null) throw new InvalidDataException("duplicate authoritative ledger resolution");
                    found = payload;
                }
            }
            if (found == null) throw new InvalidDataException("authoritative ledger resolution missing");
            return found;
        }
    }

    internal static class R7ReparseEvidence
    {
        private const uint IoReparseTagMountPoint = 0xA0000003;

        internal static void ValidateMountPoint(byte[] data, string expectedTargetPath)
        {
            if (data == null || data.Length < 20 || ReadUInt32(data, 0) != IoReparseTagMountPoint || ReadUInt16(data, 6) != 0)
                throw new InvalidDataException("mount-point reparse header rejected");
            int dataLength = ReadUInt16(data, 4);
            if (data.Length != checked(8 + dataLength) || dataLength < 12)
                throw new InvalidDataException("mount-point reparse length rejected");
            int substituteOffset = ReadUInt16(data, 8);
            int substituteLength = ReadUInt16(data, 10);
            int printOffset = ReadUInt16(data, 12);
            int printLength = ReadUInt16(data, 14);
            int pathBufferLength = dataLength - 8;
            if ((substituteOffset | substituteLength | printOffset | printLength) % 2 != 0 ||
                substituteOffset < 0 || substituteLength <= 0 || printOffset < 0 || printLength <= 0 ||
                substituteOffset + substituteLength + 2 > pathBufferLength ||
                printOffset + printLength + 2 > pathBufferLength)
                throw new InvalidDataException("mount-point reparse name range rejected");
            int pathBufferStart = 16;
            if (data[pathBufferStart + substituteOffset + substituteLength] != 0 ||
                data[pathBufferStart + substituteOffset + substituteLength + 1] != 0 ||
                data[pathBufferStart + printOffset + printLength] != 0 ||
                data[pathBufferStart + printOffset + printLength + 1] != 0)
                throw new InvalidDataException("mount-point reparse terminator rejected");
            string target = Path.GetFullPath(expectedTargetPath);
            string substituteName = Encoding.Unicode.GetString(data, pathBufferStart + substituteOffset, substituteLength);
            string printName = Encoding.Unicode.GetString(data, pathBufferStart + printOffset, printLength);
            if (!String.Equals(substituteName, @"\??\" + target, StringComparison.OrdinalIgnoreCase) ||
                !String.Equals(printName, target, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("mount-point reparse target rejected");
        }

        private static int ReadUInt16(byte[] data, int offset)
        {
            return data[offset] | (data[offset + 1] << 8);
        }

        private static uint ReadUInt32(byte[] data, int offset)
        {
            return (uint)(data[offset] | (data[offset + 1] << 8) | (data[offset + 2] << 16) | (data[offset + 3] << 24));
        }
    }

    internal static class R7FileIdentity
    {
        internal static string Get(string path)
        {
            using (FileStream stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read | FileShare.Delete))
            {
                ByHandleFileInformation information;
                if (!GetFileInformationByHandle(stream.SafeFileHandle, out information))
                    throw new Win32Exception(Marshal.GetLastWin32Error(), "file identity query failed");
                return information.VolumeSerialNumber.ToString("x8", CultureInfo.InvariantCulture) + ":" +
                    information.FileIndexHigh.ToString("x8", CultureInfo.InvariantCulture) + ":" +
                    information.FileIndexLow.ToString("x8", CultureInfo.InvariantCulture);
            }
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct FileTime
        {
            internal uint Low;
            internal uint High;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct ByHandleFileInformation
        {
            internal uint FileAttributes;
            internal FileTime CreationTime;
            internal FileTime LastAccessTime;
            internal FileTime LastWriteTime;
            internal uint VolumeSerialNumber;
            internal uint FileSizeHigh;
            internal uint FileSizeLow;
            internal uint NumberOfLinks;
            internal uint FileIndexHigh;
            internal uint FileIndexLow;
        }

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool GetFileInformationByHandle(SafeFileHandle file, out ByHandleFileInformation information);
    }
}
