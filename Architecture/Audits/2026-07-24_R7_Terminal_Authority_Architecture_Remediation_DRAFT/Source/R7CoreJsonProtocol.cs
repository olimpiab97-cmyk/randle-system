using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.IO.Pipes;
using System.Security.Cryptography;
using System.Text;

namespace RandleAI.R7Remediation
{
    internal static class R7Fixed
    {
        internal const string InterfaceVersion = "4.0.0-REMEDIATION";
        internal const string ProtocolVersion = "4.0";
        internal const int FrameHeaderBytes = 12;
        internal const int MaximumFrameBytes = 65536;
        internal const int MaximumPayloadBytes = MaximumFrameBytes - FrameHeaderBytes;
        internal const int MaximumEncodedFrameChars = ((MaximumFrameBytes + 2) / 3) * 4;
        internal const int MaximumCapturedFrameBytes = MaximumFrameBytes * 2;
        internal const int MaximumEncodedCaptureChars = ((MaximumCapturedFrameBytes + 2) / 3) * 4;
        internal const string TerminalService = "RandleTerminalAuthority";
        internal const string ExecutionService = "RandleTerminalExecution";
        internal const string ObservationService = "RandleTerminalObservation";
        internal const string ComparatorService = "RandleTerminalComparator";
        internal const string UpgradeService = "RandleTerminalUpgradeAuthority";
        internal const string TerminalSid = "S-1-5-80-1950096479-1020125124-2173088643-1633316353-879035948";
        internal const string ExecutionSid = "S-1-5-80-2354876894-2467424667-1382161683-1170422623-3885682053";
        internal const string ObservationSid = "S-1-5-80-1455550362-116536141-3163605276-3265053646-3003707260";
        internal const string ComparatorSid = "S-1-5-80-3174819085-3989415034-4266081362-372562941-1584450511";
        internal const string UpgradeSid = "S-1-5-80-238545627-4117296865-2677355104-248304369-1301198082";
        internal const string OperatorSid = "S-1-5-21-4259795780-3461844753-1172372902-1001";
        internal const string SystemSid = "S-1-5-18";
        internal const string LedgerId = "899e4db2b5c0f4ad58a09c682324a2ee9e5d7e2f180822ce9300922e56741d52";
        internal const string TerminalPublicKeyIdentity = "b84a4de14577580c64ff5b2446f120aa6f9ea60faa2cb5465b495282f0273285";
        internal const string TerminalCertificateThumbprint = "21961cfc1b10824e539172fd04efa83ad2be9203";
        internal const string TerminalKeyUniqueName = "1c9681c0b04a3dd4843d8cb457b92413_c5338977-c52f-4ca7-af6f-db9b5e287cca";
        internal const string SignatureAlgorithm = "RSA-PSS-SHA256";
        internal const string ZeroHash = "0000000000000000000000000000000000000000000000000000000000000000";

        internal const string TerminalInstallRoot = @"C:\Program Files\RandleAI\TerminalAuthorityV4";
        internal const string TerminalStateRoot = @"C:\ProgramData\RandleAI\TerminalAuthority";
        internal const string RemediationRoot = @"C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4";
        internal const string RemediationAuthorityRoot = @"C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4\Authority";
        internal const string RemediationBuildRoot = @"C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4\Build";
        internal const string RemediationConfigRoot = @"C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4\Config";
        internal const string RemediationTrustRoot = @"C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4\Trust";
        internal const string TerminalTrustRoot = @"C:\ProgramData\RandleAI\TerminalAuthority\Trust";
        internal const string TerminalPolicyPath = @"C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4\Config\terminal_authority_v4_policy.json";
        internal const string ActiveTransitionPath = @"C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4\Trust\active_upgrade_transition.json";
        internal const string TerminalPublicCertificatePath = @"C:\ProgramData\RandleAI\TerminalAuthority\Trust\terminal_authority_public.cer";
        internal const string LedgerRoot = @"C:\ProgramData\RandleAI\TerminalAuthority\Ledger";
        internal const string LegacyEvidenceRoot = @"C:\ProgramData\RandleAI\TerminalAuthority\Evidence";
        internal const string LegacyReceiptRoot = @"C:\ProgramData\RandleAI\TerminalAuthority\Receipts";
        internal const string LegacyReconciliationRoot = @"C:\ProgramData\RandleAI\TerminalAuthority\Reconciliations";
        internal const string LegacyResponseRoot = @"C:\ProgramData\RandleAI\TerminalAuthority\Responses";
        internal const string ObjectRoot = @"C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4\Objects";
        internal const string ReceiptRoot = @"C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4\Receipts";
        internal const string ResponseRoot = @"C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4\Responses";
        internal const string EvidenceRoot = @"C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4\Evidence";
        internal const string RecoveryRoot = @"C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4\Recovery";
        internal const string CasePath = @"C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4\Authority\immutable_case_definitions.json";
        internal const string ExpectationPath = @"C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4\Authority\immutable_expectations.json";
        internal const string RequirementPath = @"C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4\Authority\governed_requirement_registry.json";
        internal const string CoveragePath = @"C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4\Authority\exact_byte_coverage_proof.json";
        internal const string HistoricalClassificationPath = @"C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4\Authority\historical_classification_registry.json";
        internal const string DependencyManifestPath = @"C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4\Config\dependency_manifest.json";
        internal const string AuthoritySourceRoot = @"C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4\Authority\AuthoritySources";
        internal const string AuthoritySourceManifestPath = @"C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4\Authority\AuthoritySources\authority_source_manifest.json";
        internal const string AuthorityPackageManifestPath = @"C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4\Authority\authority_package_manifest.json";
        internal const string BuildReceiptPath = @"C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4\Build\build_receipt.json";
        internal const string BuildClosureRoot = @"C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4\Build\BuildInputClosures";
        internal const string BuildSourceInputRoot = @"C:\ProgramData\RandleAI\TerminalAuthority\RemediationV4\Build\SourceInputs";

        internal const string UpgradeInstallRoot = @"C:\Program Files\RandleAI\TerminalUpgradeAuthority";
        internal const string UpgradeStateRoot = @"C:\ProgramData\RandleAI\TerminalUpgradeAuthority";
        internal const string UpgradeConfigRoot = @"C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Config";
        internal const string UpgradeTrustRoot = @"C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Trust";
        internal const string UpgradePolicyPath = @"C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Config\upgrade_authority_policy.json";
        internal const string UpgradeDependencyManifestPath = @"C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Config\dependency_manifest.json";
        internal const string UpgradeBuildReceiptPath = @"C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Config\upgrade_authority_build_receipt.json";
        internal const string UpgradeBuildClosureRoot = @"C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Config\BuildInputClosures";
        internal const string UpgradeSourceInputRoot = @"C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Config\SourceInputs";
        internal const string UpgradePublicCertificatePath = @"C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Trust\upgrade_authority_public.cer";
        internal const string UpgradeLedgerRoot = @"C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Ledger";
        internal const string UpgradeAuthorizationRoot = @"C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Authorizations";
        internal const string UpgradeObjectRoot = @"C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Objects";
        internal const string UpgradeActivationRoot = @"C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Activations";
        internal const string UpgradeEvidenceRoot = @"C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Evidence";
        internal const string UpgradeResponseRoot = @"C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Responses";
        internal const string UpgradeStagingRoot = @"C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Staging";
        internal const string UpgradeRecoveryRoot = @"C:\ProgramData\RandleAI\TerminalUpgradeAuthority\Recovery";
        internal const string ExecutionStateRoot = @"C:\ProgramData\RandleAI\TerminalExecution";
        internal const string ExecutionTestRoot = @"C:\ProgramData\RandleAI\TerminalExecution\TestRoots";
        internal const string PublicVerifierProbeRoot = @"C:\ProgramData\RandleAI\TerminalExecution\TestRoots\PublicVerifierProbes";
        internal const string ObservationStateRoot = @"C:\ProgramData\RandleAI\TerminalObservation";
        internal const string ComparatorStateRoot = @"C:\ProgramData\RandleAI\TerminalComparator";

        internal const string TerminalPipe = "RandleAI.TerminalAuthority.v4";
        internal const string ExecutionPipe = "RandleAI.TerminalExecution.v4";
        internal const string ObservationPipe = "RandleAI.TerminalObservation.v4";
        internal const string ComparatorPipe = "RandleAI.TerminalComparator.v4";
        internal const string UpgradePipe = "RandleAI.TerminalUpgradeAuthority.v1";

        internal static SortedDictionary<string, string> AuthorityDirectories()
        {
            SortedDictionary<string, string> paths = new SortedDictionary<string, string>(StringComparer.Ordinal);
            paths.Add("COMPARATOR_STATE_ROOT", ComparatorStateRoot);
            paths.Add("EXECUTION_STATE_ROOT", ExecutionStateRoot);
            paths.Add("EXECUTION_TEST_ROOT", ExecutionTestRoot);
            paths.Add("PUBLIC_VERIFIER_PROBE_ROOT", PublicVerifierProbeRoot);
            paths.Add("OBSERVATION_STATE_ROOT", ObservationStateRoot);
            paths.Add("REMEDIATION_AUTHORITY_ROOT", RemediationAuthorityRoot);
            paths.Add("REMEDIATION_AUTHORITY_SOURCE_ROOT", AuthoritySourceRoot);
            paths.Add("REMEDIATION_BUILD_CLOSURE_ROOT", BuildClosureRoot);
            paths.Add("REMEDIATION_BUILD_ROOT", RemediationBuildRoot);
            paths.Add("REMEDIATION_BUILD_SOURCE_INPUT_ROOT", BuildSourceInputRoot);
            paths.Add("REMEDIATION_CONFIG_ROOT", RemediationConfigRoot);
            paths.Add("REMEDIATION_EVIDENCE_ROOT", EvidenceRoot);
            paths.Add("REMEDIATION_OBJECT_ROOT", ObjectRoot);
            paths.Add("REMEDIATION_RECEIPT_ROOT", ReceiptRoot);
            paths.Add("REMEDIATION_RECOVERY_ROOT", RecoveryRoot);
            paths.Add("REMEDIATION_RESPONSE_ROOT", ResponseRoot);
            paths.Add("REMEDIATION_ROOT", RemediationRoot);
            paths.Add("REMEDIATION_TRUST_ROOT", RemediationTrustRoot);
            paths.Add("TERMINAL_INSTALL_ROOT", TerminalInstallRoot);
            paths.Add("TERMINAL_LEDGER_ROOT", LedgerRoot);
            paths.Add("TERMINAL_LEGACY_EVIDENCE_ROOT", LegacyEvidenceRoot);
            paths.Add("TERMINAL_LEGACY_RECEIPT_ROOT", LegacyReceiptRoot);
            paths.Add("TERMINAL_LEGACY_RECONCILIATION_ROOT", LegacyReconciliationRoot);
            paths.Add("TERMINAL_LEGACY_RESPONSE_ROOT", LegacyResponseRoot);
            paths.Add("TERMINAL_STATE_ROOT", TerminalStateRoot);
            paths.Add("TERMINAL_TRUST_ROOT", TerminalTrustRoot);
            paths.Add("UPGRADE_ACTIVATION_ROOT", UpgradeActivationRoot);
            paths.Add("UPGRADE_AUTHORIZATION_ROOT", UpgradeAuthorizationRoot);
            paths.Add("UPGRADE_CONFIG_ROOT", UpgradeConfigRoot);
            paths.Add("UPGRADE_EVIDENCE_ROOT", UpgradeEvidenceRoot);
            paths.Add("UPGRADE_BUILD_CLOSURE_ROOT", UpgradeBuildClosureRoot);
            paths.Add("UPGRADE_INSTALL_ROOT", UpgradeInstallRoot);
            paths.Add("UPGRADE_LEDGER_ROOT", UpgradeLedgerRoot);
            paths.Add("UPGRADE_OBJECT_ROOT", UpgradeObjectRoot);
            paths.Add("UPGRADE_RECOVERY_ROOT", UpgradeRecoveryRoot);
            paths.Add("UPGRADE_RESPONSE_ROOT", UpgradeResponseRoot);
            paths.Add("UPGRADE_STAGING_ROOT", UpgradeStagingRoot);
            paths.Add("UPGRADE_STATE_ROOT", UpgradeStateRoot);
            paths.Add("UPGRADE_SOURCE_INPUT_ROOT", UpgradeSourceInputRoot);
            paths.Add("UPGRADE_TRUST_ROOT", UpgradeTrustRoot);
            return paths;
        }
    }

    internal sealed class R7ProtocolException : IOException
    {
        internal readonly string Code;
        internal byte[] RawEvidence;
        internal int Offset = -1;
        internal R7ProtocolException(string code) : base(code) { Code = code; }
        internal R7ProtocolException(string code, string detail) : base(code + ": " + detail) { Code = code; }
    }

    internal static class R7Hash
    {
        internal static string Bytes(byte[] value)
        {
            using (SHA256 sha = SHA256.Create()) return Hex(sha.ComputeHash(value));
        }

        internal static string Stream(Stream value)
        {
            using (SHA256 sha = SHA256.Create()) return Hex(sha.ComputeHash(value));
        }

        internal static string Hex(byte[] value)
        {
            StringBuilder output = new StringBuilder(value.Length * 2);
            for (int i = 0; i < value.Length; i++) output.Append(value[i].ToString("x2", CultureInfo.InvariantCulture));
            return output.ToString();
        }

        internal static bool IsLowerSha256(string value)
        {
            if (value == null || value.Length != 64) return false;
            for (int i = 0; i < value.Length; i++)
            {
                char c = value[i];
                if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return false;
            }
            return true;
        }

        internal static bool FixedTimeEquals(string left, string right)
        {
            if (left == null || right == null || left.Length != right.Length) return false;
            int difference = 0;
            for (int i = 0; i < left.Length; i++) difference |= left[i] ^ right[i];
            return difference == 0;
        }
    }

    internal static class R7Json
    {
        private static readonly UTF8Encoding StrictUtf8 = new UTF8Encoding(false, true);

        internal static object Parse(byte[] utf8)
        {
            if (utf8 == null) throw new R7ProtocolException("MISSING_JSON");
            string text;
            try { text = StrictUtf8.GetString(utf8); }
            catch (DecoderFallbackException exception) { R7ProtocolException invalid = new R7ProtocolException("INVALID_UTF8", exception.Message); invalid.Offset = exception.Index; throw invalid; }
            Parser parser = new Parser(text);
            try
            {
                object result = parser.ReadValue(0);
                if (!parser.AtEnd) throw new R7ProtocolException("TRAILING_JSON");
                return result;
            }
            catch (R7ProtocolException exception) { if (exception.Offset < 0) exception.Offset = parser.Position; throw; }
        }

        internal static SortedDictionary<string, object> ParseCanonicalObject(byte[] utf8)
        {
            object parsed = ParseCanonical(utf8);
            SortedDictionary<string, object> value = parsed as SortedDictionary<string, object>;
            if (value == null) throw new R7ProtocolException("JSON_ROOT_NOT_OBJECT");
            return value;
        }

        internal static object ParseCanonical(byte[] utf8)
        {
            object parsed = Parse(utf8);
            byte[] canonical = Encode(parsed);
            if (!ByteEqual(utf8, canonical)) throw new R7ProtocolException("NON_CANONICAL_JSON");
            return parsed;
        }

        internal static byte[] Encode(object value)
        {
            StringBuilder output = new StringBuilder();
            Write(output, value);
            return StrictUtf8.GetBytes(output.ToString());
        }

        internal static string Text(object value) { return StrictUtf8.GetString(Encode(value)); }

        internal static SortedDictionary<string, object> Object(params object[] namesAndValues)
        {
            if ((namesAndValues.Length & 1) != 0) throw new ArgumentException("name/value pairs required");
            SortedDictionary<string, object> value = new SortedDictionary<string, object>(StringComparer.Ordinal);
            for (int i = 0; i < namesAndValues.Length; i += 2) value.Add((string)namesAndValues[i], namesAndValues[i + 1]);
            return value;
        }

        internal static void ExactKeys(IDictionary<string, object> value, params string[] expected)
        {
            HashSet<string> remaining = new HashSet<string>(expected, StringComparer.Ordinal);
            if (value == null || value.Count != remaining.Count) throw new R7ProtocolException("SCHEMA_KEY_COUNT");
            foreach (string key in value.Keys) if (!remaining.Remove(key)) throw new R7ProtocolException("UNKNOWN_FIELD", key);
            if (remaining.Count != 0) throw new R7ProtocolException("MISSING_FIELD");
        }

        internal static string String(IDictionary<string, object> value, string name, int minimum, int maximum)
        {
            object raw;
            if (!value.TryGetValue(name, out raw)) throw new R7ProtocolException("MISSING_FIELD", name);
            string result = raw as string;
            if (result == null) throw new R7ProtocolException(raw == null ? "NULL_NOT_ALLOWED" : "TYPE_MISMATCH", name);
            if (result.Length < minimum || result.Length > maximum) throw new R7ProtocolException("STRING_LENGTH", name);
            if (!result.IsNormalized(NormalizationForm.FormC)) throw new R7ProtocolException("NON_CANONICAL_UNICODE", name);
            return result;
        }

        internal static long Integer(IDictionary<string, object> value, string name, long minimum, long maximum)
        {
            object raw;
            if (!value.TryGetValue(name, out raw)) throw new R7ProtocolException("MISSING_FIELD", name);
            if (!(raw is long)) throw new R7ProtocolException(raw == null ? "NULL_NOT_ALLOWED" : "TYPE_MISMATCH", name);
            long result = (long)raw;
            if (result < minimum || result > maximum) throw new R7ProtocolException("INTEGER_RANGE", name);
            return result;
        }

        internal static bool Boolean(IDictionary<string, object> value, string name)
        {
            object raw;
            if (!value.TryGetValue(name, out raw)) throw new R7ProtocolException("MISSING_FIELD", name);
            if (!(raw is bool)) throw new R7ProtocolException(raw == null ? "NULL_NOT_ALLOWED" : "TYPE_MISMATCH", name);
            return (bool)raw;
        }

        internal static SortedDictionary<string, object> Child(IDictionary<string, object> value, string name)
        {
            object raw;
            if (!value.TryGetValue(name, out raw)) throw new R7ProtocolException("MISSING_FIELD", name);
            SortedDictionary<string, object> result = raw as SortedDictionary<string, object>;
            if (result == null) throw new R7ProtocolException(raw == null ? "NULL_NOT_ALLOWED" : "TYPE_MISMATCH", name);
            return result;
        }

        internal static object[] Array(IDictionary<string, object> value, string name)
        {
            object raw;
            if (!value.TryGetValue(name, out raw)) throw new R7ProtocolException("MISSING_FIELD", name);
            object[] result = raw as object[];
            if (result == null) throw new R7ProtocolException(raw == null ? "NULL_NOT_ALLOWED" : "TYPE_MISMATCH", name);
            return result;
        }

        private static bool ByteEqual(byte[] left, byte[] right)
        {
            if (left.Length != right.Length) return false;
            int difference = 0;
            for (int i = 0; i < left.Length; i++) difference |= left[i] ^ right[i];
            return difference == 0;
        }

        private static void Write(StringBuilder output, object value)
        {
            if (value == null) { output.Append("null"); return; }
            string text = value as string;
            if (text != null) { WriteString(output, text); return; }
            if (value is bool) { output.Append((bool)value ? "true" : "false"); return; }
            if (value is long || value is int || value is short || value is sbyte || value is byte || value is ushort || value is uint)
            {
                output.Append(Convert.ToInt64(value, CultureInfo.InvariantCulture).ToString(CultureInfo.InvariantCulture));
                return;
            }
            if (value is ulong)
            {
                ulong unsigned = (ulong)value;
                if (unsigned > Int64.MaxValue) throw new R7ProtocolException("INTEGER_RANGE");
                output.Append(unsigned.ToString(CultureInfo.InvariantCulture));
                return;
            }
            IDictionary<string, object> dictionary = value as IDictionary<string, object>;
            if (dictionary != null)
            {
                output.Append('{');
                bool first = true;
                List<string> keys = new List<string>(dictionary.Keys);
                keys.Sort(StringComparer.Ordinal);
                foreach (string key in keys)
                {
                    if (key == null || !key.IsNormalized(NormalizationForm.FormC)) throw new R7ProtocolException("NON_CANONICAL_UNICODE");
                    if (!first) output.Append(',');
                    first = false;
                    WriteString(output, key);
                    output.Append(':');
                    Write(output, dictionary[key]);
                }
                output.Append('}');
                return;
            }
            IEnumerable sequence = value as IEnumerable;
            if (sequence != null)
            {
                output.Append('[');
                bool first = true;
                foreach (object item in sequence)
                {
                    if (!first) output.Append(',');
                    first = false;
                    Write(output, item);
                }
                output.Append(']');
                return;
            }
            throw new R7ProtocolException("UNSUPPORTED_JSON_TYPE", value.GetType().FullName);
        }

        private static void WriteString(StringBuilder output, string value)
        {
            if (!value.IsNormalized(NormalizationForm.FormC)) throw new R7ProtocolException("NON_CANONICAL_UNICODE");
            output.Append('"');
            for (int i = 0; i < value.Length; i++)
            {
                char c = value[i];
                switch (c)
                {
                    case '"': output.Append("\\\""); break;
                    case '\\': output.Append("\\\\"); break;
                    case '\b': output.Append("\\b"); break;
                    case '\f': output.Append("\\f"); break;
                    case '\n': output.Append("\\n"); break;
                    case '\r': output.Append("\\r"); break;
                    case '\t': output.Append("\\t"); break;
                    default:
                        if (c < 0x20) output.Append("\\u").Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
                        else output.Append(c);
                        break;
                }
            }
            output.Append('"');
        }

        private sealed class Parser
        {
            private readonly string text;
            private int index;
            internal Parser(string input) { text = input; index = 0; }
            internal bool AtEnd { get { SkipWhitespace(); return index == text.Length; } }
            internal int Position { get { return index; } }

            internal object ReadValue(int depth)
            {
                if (depth > 64) throw new R7ProtocolException("JSON_DEPTH");
                SkipWhitespace();
                if (index >= text.Length) throw new R7ProtocolException("PARTIAL_JSON");
                char c = text[index];
                if (c == '{') return ReadObject(depth + 1);
                if (c == '[') return ReadArray(depth + 1);
                if (c == '"') return ReadString();
                if (c == 't') { Literal("true"); return true; }
                if (c == 'f') { Literal("false"); return false; }
                if (c == 'n') { Literal("null"); return null; }
                if (c == '-' || (c >= '0' && c <= '9')) return ReadInteger();
                throw new R7ProtocolException("INVALID_JSON_TOKEN");
            }

            private SortedDictionary<string, object> ReadObject(int depth)
            {
                index++;
                SortedDictionary<string, object> result = new SortedDictionary<string, object>(StringComparer.Ordinal);
                SkipWhitespace();
                if (Take('}')) return result;
                while (true)
                {
                    SkipWhitespace();
                    if (index >= text.Length || text[index] != '"') throw new R7ProtocolException("OBJECT_KEY_REQUIRED");
                    string key = ReadString();
                    SkipWhitespace();
                    if (!Take(':')) throw new R7ProtocolException("COLON_REQUIRED");
                    object value = ReadValue(depth);
                    if (result.ContainsKey(key)) throw new R7ProtocolException("DUPLICATE_KEY", key);
                    result.Add(key, value);
                    SkipWhitespace();
                    if (Take('}')) return result;
                    if (!Take(',')) throw new R7ProtocolException("COMMA_REQUIRED");
                }
            }

            private object[] ReadArray(int depth)
            {
                index++;
                List<object> result = new List<object>();
                SkipWhitespace();
                if (Take(']')) return result.ToArray();
                while (true)
                {
                    result.Add(ReadValue(depth));
                    SkipWhitespace();
                    if (Take(']')) return result.ToArray();
                    if (!Take(',')) throw new R7ProtocolException("COMMA_REQUIRED");
                }
            }

            private string ReadString()
            {
                index++;
                StringBuilder result = new StringBuilder();
                bool closed = false;
                while (index < text.Length)
                {
                    char c = text[index++];
                    if (c == '"') { closed = true; break; }
                    if (c < 0x20) throw new R7ProtocolException("UNESCAPED_CONTROL");
                    if (c != '\\') { result.Append(c); continue; }
                    if (index >= text.Length) throw new R7ProtocolException("PARTIAL_ESCAPE");
                    char escape = text[index++];
                    switch (escape)
                    {
                        case '"': result.Append('"'); break;
                        case '\\': result.Append('\\'); break;
                        case '/': result.Append('/'); break;
                        case 'b': result.Append('\b'); break;
                        case 'f': result.Append('\f'); break;
                        case 'n': result.Append('\n'); break;
                        case 'r': result.Append('\r'); break;
                        case 't': result.Append('\t'); break;
                        case 'u': result.Append(ReadUnicodeEscape()); break;
                        default: throw new R7ProtocolException("INVALID_ESCAPE");
                    }
                }
                if (!closed) throw new R7ProtocolException("PARTIAL_STRING");
                string value = result.ToString();
                for (int i = 0; i < value.Length; i++)
                {
                    if (Char.IsHighSurrogate(value[i]))
                    {
                        if (i + 1 >= value.Length || !Char.IsLowSurrogate(value[i + 1])) throw new R7ProtocolException("INVALID_UNICODE_SCALAR");
                        i++;
                    }
                    else if (Char.IsLowSurrogate(value[i])) throw new R7ProtocolException("INVALID_UNICODE_SCALAR");
                }
                if (!value.IsNormalized(NormalizationForm.FormC)) throw new R7ProtocolException("NON_CANONICAL_UNICODE");
                return value;
            }

            private char ReadUnicodeEscape()
            {
                if (index + 4 > text.Length) throw new R7ProtocolException("PARTIAL_ESCAPE");
                int value = 0;
                for (int i = 0; i < 4; i++)
                {
                    char c = text[index++];
                    int digit;
                    if (c >= '0' && c <= '9') digit = c - '0';
                    else if (c >= 'a' && c <= 'f') digit = c - 'a' + 10;
                    else if (c >= 'A' && c <= 'F') digit = c - 'A' + 10;
                    else throw new R7ProtocolException("INVALID_UNICODE_ESCAPE");
                    value = (value << 4) | digit;
                }
                return (char)value;
            }

            private long ReadInteger()
            {
                int start = index;
                if (text[index] == '-') index++;
                if (index >= text.Length) throw new R7ProtocolException("PARTIAL_NUMBER");
                if (text[index] == '0')
                {
                    index++;
                    if (index < text.Length && text[index] >= '0' && text[index] <= '9') throw new R7ProtocolException("NON_CANONICAL_NUMBER");
                }
                else
                {
                    if (text[index] < '1' || text[index] > '9') throw new R7ProtocolException("INVALID_NUMBER");
                    while (index < text.Length && text[index] >= '0' && text[index] <= '9') index++;
                }
                if (index < text.Length && (text[index] == '.' || text[index] == 'e' || text[index] == 'E')) throw new R7ProtocolException("NON_INTEGER_NUMBER");
                string raw = text.Substring(start, index - start);
                if (raw == "-0") throw new R7ProtocolException("NON_CANONICAL_NUMBER");
                long value;
                if (!Int64.TryParse(raw, NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out value)) throw new R7ProtocolException("INTEGER_RANGE");
                return value;
            }

            private void Literal(string expected)
            {
                if (index + expected.Length > text.Length || !System.String.Equals(text.Substring(index, expected.Length), expected, StringComparison.Ordinal)) throw new R7ProtocolException("INVALID_LITERAL");
                index += expected.Length;
            }

            private bool Take(char expected)
            {
                if (index < text.Length && text[index] == expected) { index++; return true; }
                return false;
            }

            private void SkipWhitespace()
            {
                while (index < text.Length)
                {
                    char c = text[index];
                    if (c != ' ' && c != '\t' && c != '\r' && c != '\n') break;
                    index++;
                }
            }
        }
    }

    internal sealed class R7Frame
    {
        internal readonly byte[] Raw;
        internal readonly byte[] Payload;
        internal readonly SortedDictionary<string, object> Message;
        internal R7Frame(byte[] raw, byte[] payload, SortedDictionary<string, object> message) { Raw = raw; Payload = payload; Message = message; }
    }

    internal static class R7Framing
    {
        private static readonly byte[] Magic = new byte[] { 0x52, 0x37, 0x54, 0x41 };

        internal static byte[] Encode(IDictionary<string, object> message)
        {
            byte[] payload = R7Json.Encode(message);
            if (payload.Length > R7Fixed.MaximumPayloadBytes) throw new R7ProtocolException("FRAME_TOO_LARGE");
            byte[] frame = new byte[R7Fixed.FrameHeaderBytes + payload.Length];
            Buffer.BlockCopy(Magic, 0, frame, 0, Magic.Length);
            frame[4] = 4;
            frame[5] = 0;
            frame[6] = 0;
            frame[7] = 0;
            frame[8] = (byte)((payload.Length >> 24) & 0xff);
            frame[9] = (byte)((payload.Length >> 16) & 0xff);
            frame[10] = (byte)((payload.Length >> 8) & 0xff);
            frame[11] = (byte)(payload.Length & 0xff);
            Buffer.BlockCopy(payload, 0, frame, R7Fixed.FrameHeaderBytes, payload.Length);
            return frame;
        }

        internal static R7Frame Read(NamedPipeServerStream pipe)
        {
            MemoryStream captured = new MemoryStream();
            byte[] header = ReadServerExact(pipe, R7Fixed.FrameHeaderBytes, "PARTIAL_FRAME", captured);
            for (int i = 0; i < Magic.Length; i++) if (header[i] != Magic[i]) throw CaptureProtocolFailure(pipe, captured, "FRAME_MAGIC", i);
            if (header[4] != 4 || header[5] != 0) throw CaptureProtocolFailure(pipe, captured, "PROTOCOL_VERSION_REJECTED", 4);
            if (header[6] != 0 || header[7] != 0) throw CaptureProtocolFailure(pipe, captured, "FRAME_FLAGS_REJECTED", 6);
            int length = (header[8] << 24) | (header[9] << 16) | (header[10] << 8) | header[11];
            if (length < 0 || length > R7Fixed.MaximumPayloadBytes)
            {
                throw CaptureProtocolFailure(pipe, captured, "FRAME_TOO_LARGE", 8);
            }
            byte[] payload = ReadServerExact(pipe, length, "PARTIAL_FRAME", captured);
            if (!pipe.IsMessageComplete)
            {
                byte[] extra = new byte[4096];
                while (!pipe.IsMessageComplete && captured.Length < R7Fixed.MaximumCapturedFrameBytes)
                {
                    int remaining = R7Fixed.MaximumCapturedFrameBytes - (int)captured.Length;
                    int read = pipe.Read(extra, 0, Math.Min(extra.Length, remaining));
                    if (read <= 0) break;
                    captured.Write(extra, 0, read);
                }
                R7ProtocolException trailing = new R7ProtocolException("MULTIPLE_FRAMES_OR_TRAILING_BYTES");
                trailing.RawEvidence = captured.ToArray();
                trailing.Offset = R7Fixed.FrameHeaderBytes + length;
                throw trailing;
            }
            byte[] raw = new byte[header.Length + payload.Length];
            Buffer.BlockCopy(header, 0, raw, 0, header.Length);
            Buffer.BlockCopy(payload, 0, raw, header.Length, payload.Length);
            try { return new R7Frame(raw, payload, R7Json.ParseCanonicalObject(payload)); }
            catch (R7ProtocolException exception) { exception.RawEvidence = raw; if (exception.Offset >= 0) exception.Offset += R7Fixed.FrameHeaderBytes; throw; }
        }

        internal static SortedDictionary<string, object> ReadClientResponse(NamedPipeClientStream pipe, out byte[] raw)
        {
            byte[] header = ReadExact(pipe, R7Fixed.FrameHeaderBytes, "PARTIAL_FRAME");
            for (int i = 0; i < Magic.Length; i++) if (header[i] != Magic[i]) throw new R7ProtocolException("FRAME_MAGIC");
            if (header[4] != 4 || header[5] != 0 || header[6] != 0 || header[7] != 0) throw new R7ProtocolException("PROTOCOL_VERSION_REJECTED");
            int length = (header[8] << 24) | (header[9] << 16) | (header[10] << 8) | header[11];
            if (length < 0 || length > R7Fixed.MaximumPayloadBytes) throw new R7ProtocolException("FRAME_TOO_LARGE");
            byte[] payload = ReadExact(pipe, length, "PARTIAL_FRAME");
            if (!pipe.IsMessageComplete) throw new R7ProtocolException("MULTIPLE_FRAMES_OR_TRAILING_BYTES");
            raw = new byte[header.Length + payload.Length];
            Buffer.BlockCopy(header, 0, raw, 0, header.Length);
            Buffer.BlockCopy(payload, 0, raw, header.Length, payload.Length);
            return R7Json.ParseCanonicalObject(payload);
        }

        internal static SortedDictionary<string, object> Decode(byte[] frame)
        {
            if (frame == null || frame.Length < R7Fixed.FrameHeaderBytes) throw new R7ProtocolException("PARTIAL_FRAME");
            for (int i = 0; i < Magic.Length; i++) if (frame[i] != Magic[i]) throw new R7ProtocolException("FRAME_MAGIC");
            if (frame[4] != 4 || frame[5] != 0 || frame[6] != 0 || frame[7] != 0) throw new R7ProtocolException("PROTOCOL_VERSION_REJECTED");
            int length = (frame[8] << 24) | (frame[9] << 16) | (frame[10] << 8) | frame[11];
            if (length < 0 || length > R7Fixed.MaximumPayloadBytes) throw new R7ProtocolException("FRAME_TOO_LARGE");
            if (frame.Length != R7Fixed.FrameHeaderBytes + length) throw new R7ProtocolException("FRAME_LENGTH_MISMATCH");
            byte[] payload = new byte[length];
            Buffer.BlockCopy(frame, R7Fixed.FrameHeaderBytes, payload, 0, length);
            return R7Json.ParseCanonicalObject(payload);
        }

        internal static void Write(Stream pipe, IDictionary<string, object> message)
        {
            byte[] frame = Encode(message);
            pipe.Write(frame, 0, frame.Length);
            pipe.Flush();
        }

        internal static SortedDictionary<string, object> Call(string pipeName, IDictionary<string, object> request, int timeoutMilliseconds, out byte[] requestFrame, out byte[] responseFrame)
        {
            using (NamedPipeClientStream pipe = new NamedPipeClientStream(".", pipeName, PipeDirection.InOut, PipeOptions.WriteThrough))
            {
                pipe.Connect(timeoutMilliseconds);
                pipe.ReadMode = PipeTransmissionMode.Message;
                requestFrame = Encode(request);
                pipe.Write(requestFrame, 0, requestFrame.Length);
                pipe.Flush();
                return ReadClientResponse(pipe, out responseFrame);
            }
        }

        private static byte[] ReadExact(Stream stream, int count, string error)
        {
            byte[] value = new byte[count];
            int offset = 0;
            while (offset < count)
            {
                int read = stream.Read(value, offset, count - offset);
                if (read <= 0) throw new R7ProtocolException(error);
                offset += read;
            }
            return value;
        }

        private static byte[] ReadServerExact(Stream stream, int count, string error, MemoryStream captured)
        {
            byte[] value = new byte[count];
            int offset = 0;
            while (offset < count)
            {
                int read = stream.Read(value, offset, count - offset);
                if (read <= 0)
                {
                    R7ProtocolException exception = new R7ProtocolException(error);
                    exception.RawEvidence = captured.ToArray();
                    exception.Offset = (int)captured.Length;
                    throw exception;
                }
                captured.Write(value, offset, read);
                offset += read;
            }
            return value;
        }

        private static R7ProtocolException CaptureProtocolFailure(NamedPipeServerStream pipe, MemoryStream captured, string code, int offset)
        {
            byte[] extra = new byte[4096];
            while (!pipe.IsMessageComplete && captured.Length < R7Fixed.MaximumCapturedFrameBytes)
            {
                int remaining = R7Fixed.MaximumCapturedFrameBytes - (int)captured.Length;
                int read = pipe.Read(extra, 0, Math.Min(extra.Length, remaining));
                if (read <= 0) break;
                captured.Write(extra, 0, read);
            }
            R7ProtocolException exception = new R7ProtocolException(code);
            exception.RawEvidence = captured.ToArray();
            exception.Offset = offset;
            return exception;
        }
    }
}
