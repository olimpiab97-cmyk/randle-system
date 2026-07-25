using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Security.Cryptography;

namespace RandleAI.R7Remediation
{
    internal static class R7HistoricalClassification
    {
        private static readonly long[] AmbiguousSequences = new long[] { 326, 329, 332, 335, 375, 378, 381, 544, 547, 678 };

        internal static object[] VerifyRegistry(
            SortedDictionary<string, object> registry,
            R7VersionedLedger ledger,
            RSA terminalVerifier,
            string expectedVolumeIdentity)
        {
            return VerifyRegistry(registry, ledger, terminalVerifier, expectedVolumeIdentity, R7Fixed.LegacyEvidenceRoot, R7Fixed.LegacyReceiptRoot, R7Fixed.LegacyResponseRoot);
        }

        internal static object[] VerifyRegistry(
            SortedDictionary<string, object> registry,
            R7VersionedLedger ledger,
            RSA terminalVerifier,
            string expectedVolumeIdentity,
            string legacyEvidenceRoot,
            string legacyReceiptRoot,
            string legacyResponseRoot)
        {
            R7Json.ExactKeys(registry, "artifact_type", "rules", "schema_version");
            if (R7Json.String(registry, "artifact_type", 1, 128) != "R7_APPEND_ONLY_HISTORICAL_CLASSIFICATION_REGISTRY" ||
                R7Json.String(registry, "schema_version", 1, 32) != "1.0.0") throw new InvalidDataException("HISTORICAL_CLASSIFICATION_REGISTRY_INVALID");
            object[] rules = R7Json.Array(registry, "rules");
            if (rules.Length != 5) throw new InvalidDataException("HISTORICAL_CLASSIFICATION_RULE_COUNT_INVALID");

            VerifyRangeRule(RequireObject(rules[0]), "VALID_PROVISIONED_INFRASTRUCTURE_AUTHORITY", 1, 5);
            VerifyRangeRule(RequireObject(rules[1]), "STRUCTURALLY_VALID_REJECTED_NONAUTHORITATIVE_CANDIDATE_EVIDENCE", 6, 678);
            VerifySpecialRule(RequireObject(rules[2]), "INCOMPLETE_ISSUANCE_SUPERSEDED_NONAUTHORITY", 332);
            VerifySpecialRule(RequireObject(rules[3]), "ABORTED_CLIENT_REJECTED_ISSUANCE_NONAUTHORITY", 678);

            SortedDictionary<string, object> ambiguityRule = RequireObject(rules[4]);
            R7Json.ExactKeys(ambiguityRule, "classification", "records", "rule");
            if (R7Json.String(ambiguityRule, "classification", 1, 256) != "SIGNED_ISSUANCE_WITHOUT_TERMINAL_RECEIPT_OR_DURABLE_RESPONSE_REQUIRES_APPEND_ONLY_CLASSIFICATION") throw new InvalidDataException("HISTORICAL_AMBIGUITY_CLASS_INVALID");
            R7Json.String(ambiguityRule, "rule", 1, 2048);
            object[] records = R7Json.Array(ambiguityRule, "records");
            if (records.Length != AmbiguousSequences.Length) throw new InvalidDataException("HISTORICAL_AMBIGUITY_RECORD_COUNT_INVALID");

            legacyEvidenceRoot = Path.GetFullPath(legacyEvidenceRoot);
            legacyReceiptRoot = Path.GetFullPath(legacyReceiptRoot);
            legacyResponseRoot = Path.GetFullPath(legacyResponseRoot);
            R7SafeFile.MeasureDirectory(legacyEvidenceRoot, legacyEvidenceRoot, null, null, expectedVolumeIdentity);
            R7SafeFile.MeasureDirectory(legacyReceiptRoot, legacyReceiptRoot, null, null, expectedVolumeIdentity);
            R7SafeFile.MeasureDirectory(legacyResponseRoot, legacyResponseRoot, null, null, expectedVolumeIdentity);
            HashSet<string> legacyReceiptSubjects = LoadLegacyReceiptSubjects(terminalVerifier, expectedVolumeIdentity, legacyReceiptRoot);
            object[] verified = new object[records.Length];
            for (int i = 0; i < records.Length; i++)
            {
                SortedDictionary<string, object> binding = RequireObject(records[i]);
                R7Json.ExactKeys(binding,
                    "classification", "original_client_response_identity", "original_entry_hash", "original_entry_identity",
                    "original_operation", "original_request_nonce", "original_sequence", "original_signed_issuance_artifact_type",
                    "original_signed_issuance_public_key_identity", "original_signed_issuance_receipt_identity", "original_subject_id",
                    "original_terminal_receipt_identity", "reuse");
                long sequence = R7Json.Integer(binding, "original_sequence", 1, Int64.MaxValue);
                if (sequence != AmbiguousSequences[i]) throw new InvalidDataException("HISTORICAL_AMBIGUITY_SEQUENCE_ORDER_INVALID");
                VerifyBinding(binding, ledger, terminalVerifier, expectedVolumeIdentity, legacyReceiptSubjects, legacyEvidenceRoot, legacyResponseRoot);
                verified[i] = binding;
            }
            return verified;
        }

        private static void VerifyRangeRule(SortedDictionary<string, object> rule, string classification, long start, long end)
        {
            R7Json.ExactKeys(rule, "classification", "end_sequence", "reason", "start_sequence");
            if (R7Json.String(rule, "classification", 1, 256) != classification ||
                R7Json.Integer(rule, "start_sequence", 1, Int64.MaxValue) != start ||
                R7Json.Integer(rule, "end_sequence", 1, Int64.MaxValue) != end) throw new InvalidDataException("HISTORICAL_RANGE_RULE_INVALID");
            R7Json.String(rule, "reason", 1, 2048);
        }

        private static void VerifySpecialRule(SortedDictionary<string, object> rule, string classification, long sequence)
        {
            R7Json.ExactKeys(rule, "classification", "original_sequence", "reuse");
            if (R7Json.String(rule, "classification", 1, 256) != classification ||
                R7Json.Integer(rule, "original_sequence", 1, Int64.MaxValue) != sequence ||
                R7Json.String(rule, "reuse", 1, 128) != "PERMANENTLY_FORBIDDEN") throw new InvalidDataException("HISTORICAL_SPECIAL_RULE_INVALID");
        }

        private static void VerifyBinding(
            SortedDictionary<string, object> binding,
            R7VersionedLedger ledger,
            RSA terminalVerifier,
            string expectedVolumeIdentity,
            HashSet<string> legacyReceiptSubjects,
            string legacyEvidenceRoot,
            string legacyResponseRoot)
        {
            long sequence = R7Json.Integer(binding, "original_sequence", 1, Int64.MaxValue);
            R7LedgerRecord record = ledger.FindSequence(sequence);
            if (record == null) throw new InvalidDataException("HISTORICAL_BOUND_ENTRY_MISSING");
            string expectedClass = sequence == 332 ? "INCOMPLETE_ISSUANCE_SUPERSEDED_NONAUTHORITY" : sequence == 678 ? "ABORTED_CLIENT_REJECTED_ISSUANCE_NONAUTHORITY" : "LEGACY_TOP_LEVEL_RESPONSE_MISSING_NONAUTHORITY";
            if (R7Json.String(binding, "classification", 1, 256) != expectedClass ||
                R7Json.String(binding, "original_entry_identity", 64, 64) != record.EntryIdentity ||
                R7Json.String(binding, "original_entry_hash", 64, 64) != record.EntryHash ||
                R7Json.String(binding, "original_operation", 1, 256) != record.Operation ||
                R7Json.String(binding, "original_subject_id", 1, 4096) != record.SubjectId ||
                R7Json.String(binding, "original_request_nonce", 1, 256) != record.RequestNonce ||
                R7Json.String(binding, "original_signed_issuance_receipt_identity", 64, 64) != record.ContentAddress ||
                R7Json.String(binding, "original_signed_issuance_public_key_identity", 64, 64) != R7Fixed.TerminalPublicKeyIdentity ||
                R7Json.String(binding, "original_terminal_receipt_identity", 1, 128) != "ABSENT" ||
                R7Json.String(binding, "original_client_response_identity", 1, 128) != "ABSENT" ||
                R7Json.String(binding, "reuse", 1, 128) != "PERMANENTLY_FORBIDDEN") throw new InvalidDataException("HISTORICAL_BOUND_ENTRY_MISMATCH");

            string issuanceIdentity = record.ContentAddress;
            string issuancePath = Path.Combine(legacyEvidenceRoot, issuanceIdentity + ".json");
            SortedDictionary<string, object> issuance;
            using (R7VerifiedFile file = R7SafeFile.Open(issuancePath, issuancePath, legacyEvidenceRoot, issuanceIdentity, null, null, expectedVolumeIdentity))
            {
                issuance = R7Crypto.VerifyEnvelope(file.Bytes, R7Fixed.TerminalPublicKeyIdentity, terminalVerifier);
            }
            string artifactType = R7Json.String(issuance, "artifact_type", 1, 256);
            if (artifactType != R7Json.String(binding, "original_signed_issuance_artifact_type", 1, 256)) throw new InvalidDataException("HISTORICAL_ISSUANCE_ARTIFACT_MISMATCH");
            if (record.Operation == "R7_RUN_ISSUED" && artifactType != "R7_REAL_EXECUTION_RUN_ISSUANCE") throw new InvalidDataException("HISTORICAL_RUN_ISSUANCE_TYPE_INVALID");
            if (record.Operation == "R7_ATTEMPT_ISSUED" && artifactType != "R7_ATTEMPT_AUTHORITY") throw new InvalidDataException("HISTORICAL_ATTEMPT_ISSUANCE_TYPE_INVALID");

            string attempt = OptionalString(issuance, "attempt_id");
            string run = OptionalString(issuance, "run_id");
            if ((!String.IsNullOrEmpty(attempt) && legacyReceiptSubjects.Contains("attempt:" + attempt)) ||
                (!String.IsNullOrEmpty(run) && legacyReceiptSubjects.Contains("run:" + run))) throw new InvalidDataException("HISTORICAL_TERMINAL_RECEIPT_NOT_ABSENT");

            string responsePath = Path.Combine(legacyResponseRoot, record.RequestNonce + ".json");
            R7VerifiedFile unexpectedResponse;
            if (R7SafeFile.TryOpen(responsePath, responsePath, legacyResponseRoot, null, null, null, expectedVolumeIdentity, out unexpectedResponse))
            {
                unexpectedResponse.Dispose();
                throw new InvalidDataException("HISTORICAL_CLIENT_RESPONSE_NOT_ABSENT");
            }
        }

        private static HashSet<string> LoadLegacyReceiptSubjects(RSA terminalVerifier, string expectedVolumeIdentity, string legacyReceiptRoot)
        {
            HashSet<string> result = new HashSet<string>(StringComparer.Ordinal);
            R7SafeFile.MeasureDirectory(legacyReceiptRoot, legacyReceiptRoot, null, null, expectedVolumeIdentity);
            if (Directory.GetDirectories(legacyReceiptRoot, "*", SearchOption.TopDirectoryOnly).Length != 0) throw new InvalidDataException("LEGACY_RECEIPT_DIRECTORY_ENTRY_REJECTED");
            string[] paths = Directory.GetFiles(legacyReceiptRoot, "*", SearchOption.TopDirectoryOnly);
            Array.Sort(paths, StringComparer.Ordinal);
            foreach (string path in paths)
            {
                string fileName = Path.GetFileName(path);
                if (fileName.Length != 69 || !fileName.EndsWith(".json", StringComparison.Ordinal)) throw new InvalidDataException("LEGACY_RECEIPT_FILENAME_INVALID");
                string identity = fileName.Substring(0, 64);
                if (!R7Hash.IsLowerSha256(identity)) throw new InvalidDataException("LEGACY_RECEIPT_FILENAME_INVALID");
                SortedDictionary<string, object> payload;
                using (R7VerifiedFile file = R7SafeFile.Open(path, path, legacyReceiptRoot, identity, null, null, expectedVolumeIdentity))
                {
                    payload = R7Crypto.VerifyEnvelope(file.Bytes, R7Fixed.TerminalPublicKeyIdentity, terminalVerifier);
                }
                string attempt = OptionalString(payload, "attempt_id");
                string run = OptionalString(payload, "run_id");
                if (!String.IsNullOrEmpty(attempt)) result.Add("attempt:" + attempt);
                if (!String.IsNullOrEmpty(run)) result.Add("run:" + run);
            }
            return result;
        }

        private static string OptionalString(SortedDictionary<string, object> value, string key)
        {
            object raw;
            if (!value.TryGetValue(key, out raw)) return String.Empty;
            string text = raw as string;
            if (text == null || text.Length == 0) throw new InvalidDataException("HISTORICAL_OPTIONAL_STRING_INVALID_" + key.ToUpperInvariant());
            return text;
        }

        private static SortedDictionary<string, object> RequireObject(object value)
        {
            SortedDictionary<string, object> result = value as SortedDictionary<string, object>;
            if (result == null) throw new InvalidDataException("HISTORICAL_OBJECT_REQUIRED");
            return result;
        }
    }
}
