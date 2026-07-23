using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using System.Web.Script.Serialization;

namespace RandleAI.TerminalAuthority
{
    internal static class AuthorityConstants
    {
        internal const string InterfaceVersion = "1.0.0";
        internal const string SchemaVersion = "1.0.0";
        internal const string ServiceName = "RandleTerminalAuthority";
        internal const string ServiceDisplayName = "Randle AI Terminal Authority";
        internal const string ServiceAccount = "NT SERVICE\\RandleTerminalAuthority";
        internal const string ServiceSid = "S-1-5-80-1950096479-1020125124-2173088643-1633316353-879035948";
        internal const string OperatorSid = "S-1-5-21-4259795780-3461844753-1172372902-1001";
        internal const string SystemSid = "S-1-5-18";
        internal const string BaseCommit = "87d066eb16d7fe0b6a1677ea7739c5c2ead4ad94";
        internal const string IncompleteCommit = "06c6805ed52a0d539a73088c097c60dec335462a";
        internal const string BlockerCommit = "8ec5697b3c6fd9d93b972113b7e79d033b4cb1f6";
        internal const string InstallRoot = @"C:\Program Files\RandleAI\TerminalAuthority";
        internal const string ExecutablePath = @"C:\Program Files\RandleAI\TerminalAuthority\RandleTerminalAuthority.exe";
        internal const string StateRoot = @"C:\ProgramData\RandleAI\TerminalAuthority";
        internal const string ConfigRoot = @"C:\ProgramData\RandleAI\TerminalAuthority\Config";
        internal const string PolicyPath = @"C:\ProgramData\RandleAI\TerminalAuthority\Config\terminal_authority_policy.json";
        internal const string LedgerRoot = @"C:\ProgramData\RandleAI\TerminalAuthority\Ledger";
        internal const string TrustRoot = @"C:\ProgramData\RandleAI\TerminalAuthority\Trust";
        internal const string RepositoryRoot = @"C:\Webhook\RandleSystem";
        internal const string PublicCertificatePath = @"C:\ProgramData\RandleAI\TerminalAuthority\Trust\terminal_authority_public.cer";
        internal const string AttestationPath = @"C:\ProgramData\RandleAI\TerminalAuthority\Trust\terminal_authority_provisioning_attestation.json";
        internal const string PipeName = "RandleAI.TerminalAuthority.v1";
        internal const int MaximumMessageBytes = 65536;
        internal const string PolicySha256 = "675a9fa9c761b2738e6b7115366eaf8bb001f6f9ff1f3fb598db2f68ad57fc19";
        internal const string PublicCertificateSha256 = "b84a4de14577580c64ff5b2446f120aa6f9ea60faa2cb5465b495282f0273285";
        internal const string CertificateThumbprint = "21961cfc1b10824e539172fd04efa83ad2be9203";
        internal const string KeyUniqueName = "1c9681c0b04a3dd4843d8cb457b92413_c5338977-c52f-4ca7-af6f-db9b5e287cca";
        internal const string KeyFilePath = @"C:\ProgramData\Microsoft\Crypto\Keys\1c9681c0b04a3dd4843d8cb457b92413_c5338977-c52f-4ca7-af6f-db9b5e287cca";
        internal const string LedgerId = "899e4db2b5c0f4ad58a09c682324a2ee9e5d7e2f180822ce9300922e56741d52";
        internal const string SignatureAlgorithm = "RSA-PSS-SHA256";
        internal const string ThreatModel = "FILTERED_INTERACTIVE_USER_HOSTILE_ELEVATED_ADMIN_AND_KERNEL_OUT_OF_SCOPE";
        internal const string ZeroHash = "0000000000000000000000000000000000000000000000000000000000000000";
    }

    internal static class CanonicalJson
    {
        internal static string Serialize(object value)
        {
            StringBuilder builder = new StringBuilder();
            WriteValue(builder, value);
            return builder.ToString();
        }

        internal static byte[] SerializeBytes(object value)
        {
            return new UTF8Encoding(false, true).GetBytes(Serialize(value));
        }

        private static void WriteValue(StringBuilder builder, object value)
        {
            if (value == null)
            {
                builder.Append("null");
                return;
            }
            string text = value as string;
            if (text != null)
            {
                WriteString(builder, text);
                return;
            }
            if (value is bool)
            {
                builder.Append((bool)value ? "true" : "false");
                return;
            }
            if (value is byte || value is sbyte || value is short || value is ushort ||
                value is int || value is uint || value is long || value is ulong)
            {
                builder.Append(Convert.ToString(value, CultureInfo.InvariantCulture));
                return;
            }
            if (value is float || value is double || value is decimal)
            {
                throw new InvalidDataException("floating-point values are forbidden");
            }
            IDictionary<string, object> generic = value as IDictionary<string, object>;
            if (generic != null)
            {
                WriteObject(builder, generic);
                return;
            }
            IDictionary dictionary = value as IDictionary;
            if (dictionary != null)
            {
                SortedDictionary<string, object> converted = new SortedDictionary<string, object>(StringComparer.Ordinal);
                foreach (DictionaryEntry entry in dictionary)
                {
                    if (!(entry.Key is string))
                    {
                        throw new InvalidDataException("object keys must be strings");
                    }
                    converted.Add((string)entry.Key, entry.Value);
                }
                WriteObject(builder, converted);
                return;
            }
            IEnumerable sequence = value as IEnumerable;
            if (sequence != null)
            {
                builder.Append('[');
                bool first = true;
                foreach (object item in sequence)
                {
                    if (!first) builder.Append(',');
                    first = false;
                    WriteValue(builder, item);
                }
                builder.Append(']');
                return;
            }
            throw new InvalidDataException("unsupported canonical JSON type: " + value.GetType().FullName);
        }

        private static void WriteObject(StringBuilder builder, IDictionary<string, object> dictionary)
        {
            List<string> keys = new List<string>(dictionary.Keys);
            keys.Sort(StringComparer.Ordinal);
            builder.Append('{');
            bool first = true;
            foreach (string key in keys)
            {
                if (!first) builder.Append(',');
                first = false;
                WriteString(builder, key);
                builder.Append(':');
                WriteValue(builder, dictionary[key]);
            }
            builder.Append('}');
        }

        private static void WriteString(StringBuilder builder, string value)
        {
            builder.Append('"');
            foreach (char c in value)
            {
                switch (c)
                {
                    case '"': builder.Append("\\\""); break;
                    case '\\': builder.Append("\\\\"); break;
                    case '\b': builder.Append("\\b"); break;
                    case '\f': builder.Append("\\f"); break;
                    case '\n': builder.Append("\\n"); break;
                    case '\r': builder.Append("\\r"); break;
                    case '\t': builder.Append("\\t"); break;
                    default:
                        if (c < 0x20)
                        {
                            builder.Append("\\u");
                            builder.Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
                        }
                        else
                        {
                            builder.Append(c);
                        }
                        break;
                }
            }
            builder.Append('"');
        }
    }

    internal static class CryptoUtil
    {
        internal static string Sha256Hex(byte[] bytes)
        {
            using (SHA256 sha = SHA256.Create())
            {
                return ToHex(sha.ComputeHash(bytes));
            }
        }

        internal static string Sha256File(string path)
        {
            using (FileStream stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read))
            using (SHA256 sha = SHA256.Create())
            {
                return ToHex(sha.ComputeHash(stream));
            }
        }

        internal static string ToHex(byte[] bytes)
        {
            StringBuilder builder = new StringBuilder(bytes.Length * 2);
            foreach (byte value in bytes) builder.Append(value.ToString("x2", CultureInfo.InvariantCulture));
            return builder.ToString();
        }

        internal static byte[] Sign(RSA signer, byte[] canonicalPayload)
        {
            return signer.SignData(canonicalPayload, HashAlgorithmName.SHA256, RSASignaturePadding.Pss);
        }

        internal static bool Verify(RSA verifier, byte[] canonicalPayload, byte[] signature)
        {
            return verifier.VerifyData(canonicalPayload, signature, HashAlgorithmName.SHA256, RSASignaturePadding.Pss);
        }

        internal static X509Certificate2 LoadPublicCertificate()
        {
            X509Certificate2 certificate = new X509Certificate2(AuthorityConstants.PublicCertificatePath);
            string actual = Sha256Hex(certificate.Export(X509ContentType.Cert));
            if (!String.Equals(actual, AuthorityConstants.PublicCertificateSha256, StringComparison.Ordinal))
            {
                certificate.Dispose();
                throw new CryptographicException("public certificate identity mismatch");
            }
            return certificate;
        }

        internal static X509Certificate2 LoadMachineSigningCertificate()
        {
            X509Store store = new X509Store(StoreName.My, StoreLocation.LocalMachine);
            store.Open(OpenFlags.ReadOnly | OpenFlags.OpenExistingOnly);
            try
            {
                X509Certificate2Collection matches = store.Certificates.Find(
                    X509FindType.FindByThumbprint,
                    AuthorityConstants.CertificateThumbprint,
                    false);
                if (matches.Count != 1) throw new CryptographicException("machine signing certificate is not uniquely resolved");
                X509Certificate2 certificate = new X509Certificate2(matches[0]);
                string actual = Sha256Hex(certificate.Export(X509ContentType.Cert));
                if (!String.Equals(actual, AuthorityConstants.PublicCertificateSha256, StringComparison.Ordinal))
                {
                    certificate.Dispose();
                    throw new CryptographicException("machine signing certificate identity mismatch");
                }
                return certificate;
            }
            finally
            {
                store.Close();
            }
        }
    }

    internal static class StrictJson
    {
        internal static IDictionary<string, object> ParseObject(string text)
        {
            if (text == null) throw new InvalidDataException("missing JSON");
            JavaScriptSerializer serializer = new JavaScriptSerializer();
            serializer.MaxJsonLength = AuthorityConstants.MaximumMessageBytes;
            object parsed = serializer.DeserializeObject(text);
            IDictionary<string, object> dictionary = parsed as IDictionary<string, object>;
            if (dictionary == null) throw new InvalidDataException("JSON root must be an object");
            ValidatePlain(dictionary, 0);
            return dictionary;
        }

        internal static void RequireExactKeys(IDictionary<string, object> value, params string[] expected)
        {
            HashSet<string> required = new HashSet<string>(expected, StringComparer.Ordinal);
            if (value.Count != required.Count) throw new InvalidDataException("object key count mismatch");
            foreach (string key in value.Keys)
            {
                if (!required.Remove(key)) throw new InvalidDataException("unknown object key: " + key);
            }
            if (required.Count != 0) throw new InvalidDataException("required object key missing");
        }

        internal static string RequireString(IDictionary<string, object> value, string key)
        {
            object raw;
            if (!value.TryGetValue(key, out raw) || raw == null || raw.GetType() != typeof(string))
                throw new InvalidDataException("string field missing or invalid: " + key);
            string result = (string)raw;
            if (!result.IsNormalized(NormalizationForm.FormC))
                throw new InvalidDataException("string is not NFC: " + key);
            return result;
        }

        internal static IDictionary<string, object> RequireObject(IDictionary<string, object> value, string key)
        {
            object raw;
            if (!value.TryGetValue(key, out raw)) throw new InvalidDataException("object field missing: " + key);
            IDictionary<string, object> result = raw as IDictionary<string, object>;
            if (result == null) throw new InvalidDataException("object field invalid: " + key);
            return result;
        }

        private static void ValidatePlain(object value, int depth)
        {
            if (depth > 32) throw new InvalidDataException("JSON nesting is too deep");
            if (value == null || value is string || value is bool || value is int || value is long || value is decimal) return;
            if (value is double || value is float) throw new InvalidDataException("floating-point values are forbidden");
            IDictionary<string, object> dictionary = value as IDictionary<string, object>;
            if (dictionary != null)
            {
                HashSet<string> keys = new HashSet<string>(StringComparer.Ordinal);
                foreach (KeyValuePair<string, object> item in dictionary)
                {
                    if (item.Key == null || !item.Key.IsNormalized(NormalizationForm.FormC) || !keys.Add(item.Key))
                        throw new InvalidDataException("invalid or duplicate object key");
                    ValidatePlain(item.Value, depth + 1);
                }
                return;
            }
            object[] array = value as object[];
            if (array != null)
            {
                foreach (object item in array) ValidatePlain(item, depth + 1);
                return;
            }
            throw new InvalidDataException("non-plain JSON value");
        }
    }
}
