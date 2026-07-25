using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using System.Web.Script.Serialization;

// Independent review utility.  It deliberately does not reference any Randle
// assembly or package verifier.  It reconstructs the signed ledger rules from
// the public envelope bytes and the governing provisioning identities.
internal static class IndependentLedgerVerifier
{
    private const string LedgerId = "899e4db2b5c0f4ad58a09c682324a2ee9e5d7e2f180822ce9300922e56741d52";
    private const string PublicKeyIdentity = "b84a4de14577580c64ff5b2446f120aa6f9ea60faa2cb5465b495282f0273285";
    private const string ServiceSid = "S-1-5-80-1950096479-1020125124-2173088643-1633316353-879035948";
    private const string ZeroHash = "0000000000000000000000000000000000000000000000000000000000000000";
    private static readonly UTF8Encoding StrictUtf8 = new UTF8Encoding(false, true);
    private static readonly JavaScriptSerializer Parser = new JavaScriptSerializer { MaxJsonLength = Int32.MaxValue, RecursionLimit = 512 };

    private sealed class Row
    {
        internal long Sequence;
        internal string Operation;
        internal string RequestNonce;
        internal string SubjectId;
        internal string ContentAddress;
        internal string EntryHash;
        internal string FileIdentity;
    }

    private static int Main(string[] args)
    {
        if (args.Length != 4)
        {
            Console.Error.WriteLine("usage: verifier LEDGER_ROOT PUBLIC_CERT AUTHORITY_STATE_ROOT OUTPUT");
            return 2;
        }
        try
        {
            SortedDictionary<string, object> result = Verify(args[0], args[1], args[2]);
            string json = Canonical(result) + "\n";
            File.WriteAllText(args[3], json, StrictUtf8);
            Console.Out.Write(json);
            return 0;
        }
        catch (Exception ex)
        {
            SortedDictionary<string, object> result = Map(
                "artifact_type", "R7_INDEPENDENT_LEDGER_VERIFICATION",
                "error", ex.GetType().FullName + ": " + ex.Message,
                "schema_version", "1.0.0",
                "status", "FAIL");
            string json = Canonical(result) + "\n";
            File.WriteAllText(args[3], json, StrictUtf8);
            Console.Out.Write(json);
            return 1;
        }
    }

    private static SortedDictionary<string, object> Verify(string ledgerRoot, string certPath, string authorityRoot)
    {
        byte[] certBytes = File.ReadAllBytes(certPath);
        Require(Sha256(certBytes) == PublicKeyIdentity, "public certificate identity mismatch");
        X509Certificate2 certificate = new X509Certificate2(certBytes);
        RSA verifier = RSACertificateExtensions.GetRSAPublicKey(certificate);
        Require(verifier != null, "certificate has no RSA public key");

        string[] files = Directory.GetFiles(ledgerRoot, "*.entry.json", SearchOption.TopDirectoryOnly);
        Array.Sort(files, StringComparer.OrdinalIgnoreCase);
        Require(files.Length > 0, "ledger is empty");
        List<Row> rows = new List<Row>();
        Dictionary<string, int> operationCounts = new Dictionary<string, int>(StringComparer.Ordinal);
        Dictionary<string, int> nonemptyNonces = new Dictionary<string, int>(StringComparer.Ordinal);
        string prior = ZeroHash;

        for (int index = 0; index < files.Length; index++)
        {
            long expectedSequence = index + 1L;
            string expectedName = expectedSequence.ToString("D20", CultureInfo.InvariantCulture) + ".entry.json";
            Require(String.Equals(Path.GetFileName(files[index]), expectedName, StringComparison.Ordinal), "sequence filename mismatch at " + expectedSequence);
            byte[] bytes = File.ReadAllBytes(files[index]);
            IDictionary<string, object> envelope = ParseCanonicalObject(bytes);
            RequireKeys(envelope, "payload", "public_key_identity", "signature", "signature_algorithm");
            IDictionary<string, object> payload = Object(envelope, "payload");
            RequireKeys(payload, "content_address", "entry_hash", "issue_time", "ledger_id", "operation", "prior_entry_hash", "public_key_identity", "request_nonce", "schema_version", "sequence", "service_sid", "subject_id");
            Require(StringValue(envelope, "public_key_identity") == PublicKeyIdentity, "envelope trust mismatch");
            Require(StringValue(envelope, "signature_algorithm") == "RSA-PSS-SHA256", "signature algorithm mismatch");
            Require(verifier.VerifyData(StrictUtf8.GetBytes(Canonical(payload)), Convert.FromBase64String(StringValue(envelope, "signature")), HashAlgorithmName.SHA256, RSASignaturePadding.Pss), "signature rejected at " + expectedSequence);
            Require(Integer(payload, "sequence") == expectedSequence, "payload sequence mismatch");
            Require(StringValue(payload, "ledger_id") == LedgerId, "ledger identity mismatch");
            Require(StringValue(payload, "public_key_identity") == PublicKeyIdentity, "payload trust mismatch");
            Require(StringValue(payload, "service_sid") == ServiceSid, "service SID mismatch");
            Require(StringValue(payload, "prior_entry_hash") == prior, "prior-hash mismatch at " + expectedSequence);

            SortedDictionary<string, object> core = new SortedDictionary<string, object>(StringComparer.Ordinal);
            foreach (KeyValuePair<string, object> pair in payload) if (pair.Key != "entry_hash") core.Add(pair.Key, pair.Value);
            string computed = Sha256(StrictUtf8.GetBytes(Canonical(core)));
            string recorded = StringValue(payload, "entry_hash");
            Require(computed == recorded, "entry hash mismatch at " + expectedSequence);
            prior = recorded;

            string operation = StringValue(payload, "operation");
            operationCounts[operation] = operationCounts.ContainsKey(operation) ? operationCounts[operation] + 1 : 1;
            string nonce = StringValue(payload, "request_nonce");
            if (nonce.Length != 0) nonemptyNonces[nonce] = nonemptyNonces.ContainsKey(nonce) ? nonemptyNonces[nonce] + 1 : 1;
            rows.Add(new Row
            {
                Sequence = expectedSequence,
                Operation = operation,
                RequestNonce = nonce,
                SubjectId = StringValue(payload, "subject_id"),
                ContentAddress = StringValue(payload, "content_address"),
                EntryHash = recorded,
                FileIdentity = Sha256(bytes)
            });
        }

        byte[] checkpointBytes = File.ReadAllBytes(Path.Combine(ledgerRoot, "checkpoint.json"));
        IDictionary<string, object> checkpointEnvelope = ParseCanonicalObject(checkpointBytes);
        RequireKeys(checkpointEnvelope, "payload", "public_key_identity", "signature", "signature_algorithm");
        IDictionary<string, object> checkpoint = Object(checkpointEnvelope, "payload");
        RequireKeys(checkpoint, "issue_time", "ledger_id", "public_key_identity", "root_hash", "schema_version", "sequence", "service_sid");
        Require(StringValue(checkpointEnvelope, "public_key_identity") == PublicKeyIdentity, "checkpoint envelope trust mismatch");
        Require(StringValue(checkpointEnvelope, "signature_algorithm") == "RSA-PSS-SHA256", "checkpoint signature algorithm mismatch");
        Require(verifier.VerifyData(StrictUtf8.GetBytes(Canonical(checkpoint)), Convert.FromBase64String(StringValue(checkpointEnvelope, "signature")), HashAlgorithmName.SHA256, RSASignaturePadding.Pss), "checkpoint signature rejected");
        Require(Integer(checkpoint, "sequence") == rows.Count, "checkpoint sequence mismatch");
        Require(StringValue(checkpoint, "root_hash") == prior, "checkpoint root mismatch");
        Require(StringValue(checkpoint, "ledger_id") == LedgerId, "checkpoint ledger mismatch");
        Require(StringValue(checkpoint, "public_key_identity") == PublicKeyIdentity, "checkpoint trust mismatch");
        Require(StringValue(checkpoint, "service_sid") == ServiceSid, "checkpoint SID mismatch");

        int terminalReservations = 0, terminalCommits = 0, terminalUnmatched = 0;
        int reconciliationReservations = 0, reconciliationCommits = 0, reconciliationUnmatched = 0;
        for (int index = 0; index < rows.Count; index++)
        {
            Row row = rows[index];
            if (row.Operation == "R7_TERMINAL_RESERVED") terminalReservations++;
            if (row.Operation == "R7_RECONCILIATION_RESERVED") reconciliationReservations++;
            if (row.Operation == "R7_TERMINAL_RECEIPT_COMMITTED")
            {
                terminalCommits++;
                if (index == 0 || rows[index - 1].Operation != "R7_TERMINAL_RESERVED" || rows[index - 1].SubjectId != row.SubjectId) terminalUnmatched++;
            }
            if (row.Operation == "R7_RECONCILIATION_COMMITTED" || row.Operation == "R7_RECONCILIATION_RECEIPT_COMMITTED")
            {
                reconciliationCommits++;
                if (index == 0 || rows[index - 1].Operation != "R7_RECONCILIATION_RESERVED" || rows[index - 1].SubjectId != row.SubjectId) reconciliationUnmatched++;
            }
        }
        terminalUnmatched += Math.Max(0, terminalReservations - terminalCommits);
        reconciliationUnmatched += Math.Max(0, reconciliationReservations - reconciliationCommits);

        List<object> upgradeSequences = rows.Where(r => r.Operation == "R7_SERVICE_UPGRADE_ACTIVATED").Select(r => (object)r.Sequence).ToList();
        int resolvedUpgradeContent = 0;
        foreach (Row row in rows.Where(r => r.Operation == "R7_SERVICE_UPGRADE_ACTIVATED"))
        {
            if (Directory.GetFiles(authorityRoot, row.ContentAddress + "*", SearchOption.AllDirectories).Length != 0) resolvedUpgradeContent++;
        }

        SortedDictionary<string, object> counts = new SortedDictionary<string, object>(StringComparer.Ordinal);
        foreach (KeyValuePair<string, int> pair in operationCounts) counts.Add(pair.Key, pair.Value);
        int duplicatedNonces = nonemptyNonces.Count(pair => pair.Value != 1);
        return Map(
            "artifact_type", "R7_INDEPENDENT_LEDGER_VERIFICATION",
            "checkpoint", Map(
                "identity_sha256", Sha256(checkpointBytes),
                "root_hash", prior,
                "sequence", rows.Count,
                "signature_valid", true),
            "entry_count", rows.Count,
            "entry_hashes_valid", true,
            "final_root", prior,
            "genesis_entry_hash", rows[0].EntryHash,
            "genesis_envelope_identity_sha256", rows[0].FileIdentity,
            "identity_bindings_valid", true,
            "missing_sequences", 0,
            "nonempty_duplicate_request_nonce_count", duplicatedNonces,
            "operation_counts", counts,
            "pairing", Map(
                "reconciliation_commits", reconciliationCommits,
                "reconciliation_reservations", reconciliationReservations,
                "reconciliation_unmatched", reconciliationUnmatched,
                "rule", "commit immediately follows reservation and has identical subject_id; commit nonce is intentionally distinct",
                "terminal_commits", terminalCommits,
                "terminal_reservations", terminalReservations,
                "terminal_unmatched", terminalUnmatched),
            "public_certificate_sha256", Sha256(certBytes),
            "schema_version", "1.0.0",
            "signatures_valid", true,
            "status", "PASS_CRYPTOGRAPHIC_CONTINUITY_ONLY",
            "upgrade_activation", Map(
                "count", upgradeSequences.Count,
                "content_addresses_resolved_to_stored_objects", resolvedUpgradeContent,
                "sequences", upgradeSequences.ToArray()));
    }

    private static IDictionary<string, object> ParseCanonicalObject(byte[] bytes)
    {
        string text = StrictUtf8.GetString(bytes);
        object parsed = Parser.DeserializeObject(text);
        IDictionary<string, object> obj = parsed as IDictionary<string, object>;
        Require(obj != null, "root is not an object");
        Require(String.Equals(text, Canonical(obj), StringComparison.Ordinal), "input is not unique canonical JSON");
        return obj;
    }

    private static IDictionary<string, object> Object(IDictionary<string, object> obj, string key)
    {
        object raw;
        Require(obj.TryGetValue(key, out raw), "missing object " + key);
        IDictionary<string, object> value = raw as IDictionary<string, object>;
        Require(value != null, "invalid object " + key);
        return value;
    }

    private static string StringValue(IDictionary<string, object> obj, string key)
    {
        object raw;
        Require(obj.TryGetValue(key, out raw) && raw is string, "invalid string " + key);
        return (string)raw;
    }

    private static long Integer(IDictionary<string, object> obj, string key)
    {
        object raw;
        Require(obj.TryGetValue(key, out raw), "missing integer " + key);
        Require(raw is int || raw is long, "non-integer numeric representation " + key);
        return Convert.ToInt64(raw, CultureInfo.InvariantCulture);
    }

    private static void RequireKeys(IDictionary<string, object> obj, params string[] expected)
    {
        string[] actual = obj.Keys.OrderBy(x => x, StringComparer.Ordinal).ToArray();
        string[] wanted = expected.OrderBy(x => x, StringComparer.Ordinal).ToArray();
        Require(actual.SequenceEqual(wanted, StringComparer.Ordinal), "object key set mismatch");
    }

    private static void Require(bool condition, string message)
    {
        if (!condition) throw new InvalidDataException(message);
    }

    private static SortedDictionary<string, object> Map(params object[] pairs)
    {
        Require(pairs.Length % 2 == 0, "invalid map construction");
        SortedDictionary<string, object> result = new SortedDictionary<string, object>(StringComparer.Ordinal);
        for (int index = 0; index < pairs.Length; index += 2) result.Add((string)pairs[index], pairs[index + 1]);
        return result;
    }

    private static string Sha256(byte[] bytes)
    {
        using (SHA256 sha = SHA256.Create()) return String.Concat(sha.ComputeHash(bytes).Select(x => x.ToString("x2", CultureInfo.InvariantCulture)));
    }

    private static string Canonical(object value)
    {
        StringBuilder builder = new StringBuilder();
        WriteCanonical(builder, value);
        return builder.ToString();
    }

    private static void WriteCanonical(StringBuilder builder, object value)
    {
        if (value == null) { builder.Append("null"); return; }
        if (value is string) { WriteString(builder, (string)value); return; }
        if (value is bool) { builder.Append((bool)value ? "true" : "false"); return; }
        if (value is byte || value is sbyte || value is short || value is ushort || value is int || value is uint || value is long || value is ulong)
        {
            builder.Append(Convert.ToString(value, CultureInfo.InvariantCulture)); return;
        }
        if (value is float || value is double || value is decimal) throw new InvalidDataException("floating point forbidden");
        IDictionary<string, object> generic = value as IDictionary<string, object>;
        if (generic != null)
        {
            builder.Append('{'); bool first = true;
            foreach (string key in generic.Keys.OrderBy(x => x, StringComparer.Ordinal))
            {
                if (!first) builder.Append(','); first = false; WriteString(builder, key); builder.Append(':'); WriteCanonical(builder, generic[key]);
            }
            builder.Append('}'); return;
        }
        IDictionary dictionary = value as IDictionary;
        if (dictionary != null)
        {
            SortedDictionary<string, object> converted = new SortedDictionary<string, object>(StringComparer.Ordinal);
            foreach (DictionaryEntry entry in dictionary) { Require(entry.Key is string, "non-string key"); converted.Add((string)entry.Key, entry.Value); }
            WriteCanonical(builder, converted); return;
        }
        IEnumerable sequence = value as IEnumerable;
        if (sequence != null)
        {
            builder.Append('['); bool first = true;
            foreach (object item in sequence) { if (!first) builder.Append(','); first = false; WriteCanonical(builder, item); }
            builder.Append(']'); return;
        }
        throw new InvalidDataException("unsupported JSON value " + value.GetType().FullName);
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
                    if (c < 0x20) builder.Append("\\u" + ((int)c).ToString("x4", CultureInfo.InvariantCulture)); else builder.Append(c);
                    break;
            }
        }
        builder.Append('"');
    }
}
