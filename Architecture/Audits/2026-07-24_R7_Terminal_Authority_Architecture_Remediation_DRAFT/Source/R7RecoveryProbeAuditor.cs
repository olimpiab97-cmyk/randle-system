using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Security.Cryptography;

namespace RandleAI.R7Remediation
{
    internal static class R7RecoveryProbeAuditor
    {
        internal static SortedDictionary<string, object> Verify(string isolatedRoot, string faultPoint, string resultIdentity)
        {
            return VerifyCore(isolatedRoot, faultPoint, resultIdentity, false);
        }

        internal static SortedDictionary<string, object> VerifyOffline(string isolatedRoot, string faultPoint, string resultIdentity)
        {
            return VerifyCore(isolatedRoot, faultPoint, resultIdentity, true);
        }

        private static SortedDictionary<string, object> VerifyCore(string isolatedRoot, string faultPoint, string resultIdentity, bool offlineStatic)
        {
            string root = Path.GetFullPath(isolatedRoot);
            RequireIsolatedRoot(root, offlineStatic);
            R7SafeFile.MeasureDirectory(root, root, null, null, null);
            if (!R7Hash.IsLowerSha256(resultIdentity)) throw new R7ProtocolException("RECOVERY_RESULT_IDENTITY_INVALID");
            string evidenceRoot = Path.Combine(root, "ProbeEvidence");
            string resultPath = Path.Combine(evidenceRoot, resultIdentity + ".json");
            SortedDictionary<string, object> result;
            using (R7VerifiedFile file = R7SafeFile.Open(resultPath, resultPath, evidenceRoot, resultIdentity, null, null, null)) result = R7Json.ParseCanonicalObject(file.Bytes);
            ValidateResultSchema(result, faultPoint);

            string metadataPath = Path.Combine(root, "probe_metadata.json");
            SortedDictionary<string, object> metadata;
            using (R7VerifiedFile file = R7SafeFile.OpenMeasured(metadataPath, metadataPath, root)) metadata = R7Json.ParseCanonicalObject(file.Bytes);
            R7Json.ExactKeys(metadata, "artifact_type", "fault_point", "isolated_root", "ledger_id", "public_exponent", "public_key_identity", "public_modulus", "request_identity", "request_sha256", "schema_version", "service_sid");
            string ledgerId = Sha(metadata, "ledger_id");
            string publicIdentity = Sha(metadata, "public_key_identity");
            string requestIdentity = R7Json.String(metadata, "request_identity", 36, 36);
            string requestSha256 = Sha(metadata, "request_sha256");
            Guid requestGuid;
            if (R7Json.String(metadata, "artifact_type", 1, 256) != "R7_ISOLATED_RECOVERY_PROBE_METADATA" || R7Json.String(metadata, "schema_version", 1, 64) != "1.0.0" ||
                R7Json.String(metadata, "fault_point", 1, 256) != faultPoint || R7Json.String(metadata, "isolated_root", 3, 4096) != root ||
                R7Json.String(metadata, "service_sid", 1, 256) != R7Fixed.ExecutionSid || !Guid.TryParseExact(requestIdentity, "D", out requestGuid) || requestGuid.ToString("D") != requestIdentity) throw new InvalidDataException("RECOVERY_PROBE_METADATA_INVALID");
            byte[] modulus;
            byte[] exponent;
            try
            {
                modulus = Convert.FromBase64String(R7Json.String(metadata, "public_modulus", 1, 4096));
                exponent = Convert.FromBase64String(R7Json.String(metadata, "public_exponent", 1, 64));
            }
            catch (FormatException) { throw new InvalidDataException("RECOVERY_PUBLIC_KEY_ENCODING_INVALID"); }
            if (modulus.Length != 384 || exponent.Length < 3 || R7Hash.Bytes(Combine(modulus, exponent)) != publicIdentity) throw new InvalidDataException("RECOVERY_PUBLIC_KEY_IDENTITY_INVALID");

            using (RSACng verifier = new RSACng())
            {
                verifier.ImportParameters(new RSAParameters { Modulus = modulus, Exponent = exponent });
                string ledgerRoot = Path.Combine(root, "Ledger");
                string objectRoot = Path.Combine(root, "Objects");
                string receiptRoot = Path.Combine(root, "Receipts");
                string responseRoot = Path.Combine(root, "Responses");
                R7VersionedLedger ledger = new R7VersionedLedger(ledgerRoot, ledgerId, publicIdentity, R7Fixed.ExecutionSid, null, verifier);
                if (!String.IsNullOrEmpty(ledger.CheckpointRecoveryReason) || ledger.CheckpointIdentity == R7Fixed.ZeroHash) throw new InvalidDataException("ISOLATED_RECOVERY_CHECKPOINT_NOT_CURRENT");
                R7ObjectStore objects = new R7ObjectStore(objectRoot);
                long sequence = R7Json.Integer(result, "final_ledger_sequence", 1, Int64.MaxValue);
                string rootHash = R7Json.String(result, "final_ledger_root", 64, 64);
                if (sequence != ledger.Sequence || rootHash != ledger.RootHash || R7Json.String(result, "fault_point", 1, 256) != faultPoint || R7Json.String(result, "isolated_root", 3, 4096) != root || !R7Json.Boolean(result, "history_preserved") || !R7Json.Boolean(result, "second_recovery_idempotent")) throw new InvalidDataException("RECOVERY_RESULT_LEDGER_BINDING_INVALID");
                R7TransactionManager firstView = new R7TransactionManager(ledger, objects, null, publicIdentity, receiptRoot, responseRoot, "TEST-1.0.0", String.Empty);
                R7TransactionSnapshot snapshot = firstView.Find(requestIdentity);
                string derivedCode = DeriveCode(faultPoint, result, snapshot, ledger, verifier, publicIdentity, root);
                if (derivedCode != R7Json.String(result, "result_code", 1, 256)) throw new InvalidDataException("RECOVERY_WORKER_RESULT_NOT_REDERIVED");
                long beforeSecondView = ledger.Sequence;
                string beforeSecondRoot = ledger.RootHash;
                R7TransactionManager secondView = new R7TransactionManager(ledger, objects, null, publicIdentity, receiptRoot, responseRoot, "TEST-1.0.0", String.Empty);
                R7TransactionSnapshot secondSnapshot = secondView.Find(requestIdentity);
                if (ledger.Sequence != beforeSecondView || ledger.RootHash != beforeSecondRoot || (snapshot == null) != (secondSnapshot == null) || snapshot != null && snapshot.State != secondSnapshot.State) throw new InvalidDataException("RECOVERY_PUBLIC_REPLAY_NOT_IDEMPOTENT");
                return R7Json.Object(
                    "derived_result_code", derivedCode,
                    "ledger_root", ledger.RootHash,
                    "ledger_sequence", ledger.Sequence,
                    "public_key_identity", publicIdentity,
                    "request_identity", requestIdentity,
                    "request_sha256", requestSha256,
                    "result_identity", resultIdentity,
                    "service_sid", R7Fixed.ExecutionSid,
                    "status", "PASS",
                    "transaction_state", snapshot == null ? "NO_STATE" : snapshot.State);
            }
        }

        private static void RequireIsolatedRoot(string root, bool offlineStatic)
        {
            if (!offlineStatic)
            {
                if (!root.StartsWith(R7Fixed.ExecutionTestRoot + Path.DirectorySeparatorChar, StringComparison.Ordinal) || root.IndexOf(Path.DirectorySeparatorChar + "IsolatedTests" + Path.DirectorySeparatorChar, StringComparison.Ordinal) < 0) throw new R7ProtocolException("ISOLATED_RECOVERY_ROOT_REQUIRED");
                return;
            }
            string temporaryRoot = Path.GetFullPath(Path.GetTempPath()).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            if (!root.StartsWith(temporaryRoot, StringComparison.OrdinalIgnoreCase) || root.IndexOf(Path.DirectorySeparatorChar + "R7StaticIsolatedTests" + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase) < 0) throw new R7ProtocolException("OFFLINE_STATIC_RECOVERY_ROOT_REQUIRED");
        }

        private static string DeriveCode(string faultPoint, SortedDictionary<string, object> result, R7TransactionSnapshot snapshot, R7VersionedLedger ledger, RSA verifier, string publicIdentity, string root)
        {
            if (faultPoint == "STALE_CHECKPOINT" || faultPoint == "PARTIAL_CHECKPOINT" || faultPoint == "BEFORE_CHECKPOINT_UPDATE" || faultPoint == "DURING_CHECKPOINT_UPDATE")
            {
                if (ledger.Find("ISOLATED_CHECKPOINT_RECOVERY_INTENT", null).Length != 1) throw new InvalidDataException("ISOLATED_CHECKPOINT_RECOVERY_INTENT_MISSING");
                if (faultPoint == "STALE_CHECKPOINT" || faultPoint == "BEFORE_CHECKPOINT_UPDATE") return "CHECKPOINT_ADVANCED_BY_REPLAY";
                return "PARTIAL_CHECKPOINT_QUARANTINED";
            }
            if (faultPoint == "PARTIAL_WRITE")
            {
                string identity = Sha(result, "partial_artifact_identity");
                string path = Path.Combine(root, "Recovery", "partial." + identity + ".preserved");
                using (R7VerifiedFile file = R7SafeFile.OpenMeasured(path, path, Path.Combine(root, "Recovery")))
                {
                    if (file.Measurement.Sha256 != identity) throw new InvalidDataException("PARTIAL_WRITE_PRESERVED_IDENTITY_INVALID");
                }
                return "PARTIAL_WRITE_REJECTED";
            }
            if (faultPoint == "RESPONSE_NO_COMMIT")
            {
                string identity = Sha(result, "orphan_response_identity");
                string path = Path.Combine(root, "Responses", identity + ".frame");
                using (R7VerifiedFile file = R7SafeFile.Open(path, path, Path.Combine(root, "Responses"), identity, null, null, null)) R7Framing.Decode(file.Bytes);
                if (snapshot != null) throw new InvalidDataException("ORPHAN_RESPONSE_TRANSACTION_PRESENT");
                return "ORPHAN_RESPONSE_NONAUTHORITY";
            }
            if (faultPoint == "RECONCILIATION_UNCOMMITTED")
            {
                string identity = Sha(result, "orphan_receipt_identity");
                string path = Path.Combine(root, "Receipts", identity + ".receipt.json");
                using (R7VerifiedFile file = R7SafeFile.Open(path, path, Path.Combine(root, "Receipts"), identity, null, null, null)) R7Crypto.VerifyEnvelope(file.Bytes, publicIdentity, verifier);
                if (snapshot != null) throw new InvalidDataException("UNCOMMITTED_RECONCILIATION_TRANSACTION_PRESENT");
                return "RECEIPT_NOT_COMMITTED";
            }
            if (faultPoint == "DUPLICATE_COMPLETION") { RequireState(snapshot, "RESPONSE_AVAILABLE"); return "ILLEGAL_DUPLICATE_TRANSITION"; }
            if (faultPoint == "CONFLICTING_SUPERSESSION") { RequireState(snapshot, "SUPERSEDED"); return "CONFLICTING_CLASSIFICATION"; }
            if (faultPoint == "DURING_RESTART_RECOVERY" || faultPoint == "RESTART_DURING_RECOVERY") { RequireState(snapshot, "ABORTED"); return "RECOVERY_RESUMED"; }
            if (faultPoint == "DURING_ABORT_OR_SUPERSESSION") { RequireState(snapshot, "SUPERSEDED"); return "CLASSIFICATION_TRANSITION_RECOVERED"; }
            if (faultPoint == "BEFORE_RESERVATION") { if (snapshot != null) throw new InvalidDataException("BEFORE_RESERVATION_STATE_PRESENT"); return "NO_RESERVATION"; }
            if (faultPoint == "AFTER_RESERVATION") { RequireState(snapshot, "ABORTED"); return "RESERVATION_ABORTED"; }
            if (faultPoint == "AFTER_EVIDENCE_VALIDATION") { RequireState(snapshot, "ABORTED"); return "VALIDATED_TRANSACTION_ABORTED"; }
            if (faultPoint == "AFTER_RECEIPT_PREPARATION") { RequireState(snapshot, "SUPERSEDED"); return "PREPARED_TRANSACTION_ABORTED"; }
            if (faultPoint == "AFTER_RECEIPT_STORAGE") { RequireState(snapshot, "SUPERSEDED"); return "UNCOMMITTED_RECEIPT_QUARANTINED"; }
            if (faultPoint == "AFTER_COMMIT_APPEND" || faultPoint == "AFTER_CHECKPOINT_BEFORE_RESPONSE" || faultPoint == "CLIENT_DISCONNECT_AFTER_COMMIT" || faultPoint == "DISCONNECT_AFTER_COMMIT" || faultPoint == "COMMIT_NO_RESPONSE") { RequireCommitted(snapshot); return "RESPONSE_RECONSTRUCTED"; }
            if (faultPoint == "INCOMPLETE_RESERVATION") { RequireState(snapshot, "ABORTED"); return "INCOMPLETE_RESERVATION_ABORTED"; }
            if (faultPoint == "DURING_RECONCILIATION") { RequireState(snapshot, "ABORTED"); return "RECONCILIATION_ABORTED"; }
            if (faultPoint == "DISK_FULL") { RequireState(snapshot, "SUPERSEDED"); return "DURABLE_WRITE_FAILED"; }
            if (faultPoint == "ACCESS_DENIED") { RequireState(snapshot, "SUPERSEDED"); return "ACCESS_DENIED"; }
            if (faultPoint == "PARENT_DIRECTORY_PERSISTENCE_FAILURE") { RequireState(snapshot, "SUPERSEDED"); return "DIRECTORY_DURABILITY_FAILED"; }
            throw new InvalidDataException("RECOVERY_FAULT_POINT_UNGOVERNED:" + faultPoint);
        }

        private static void ValidateResultSchema(SortedDictionary<string, object> result, string faultPoint)
        {
            HashSet<string> allowed = new HashSet<string>(new string[] {
                "durable_transaction_state", "fault_injection_path", "fault_injection_stage", "fault_injection_triggered", "fault_point", "final_ledger_root", "final_ledger_sequence",
                "final_transaction_state", "history_preserved", "initial_outcome", "interrupted_recovery_observed", "isolated_root", "orphan_receipt_identity", "orphan_response_identity",
                "partial_artifact_identity", "recovery_reason", "result_code", "second_recovery_idempotent" }, StringComparer.Ordinal);
            foreach (string key in result.Keys) if (!allowed.Contains(key)) throw new InvalidDataException("RECOVERY_RESULT_UNKNOWN_FIELD:" + key);
            foreach (string required in new string[] { "durable_transaction_state", "fault_point", "final_ledger_root", "final_ledger_sequence", "final_transaction_state", "history_preserved", "isolated_root", "result_code", "second_recovery_idempotent" }) if (!result.ContainsKey(required)) throw new InvalidDataException("RECOVERY_RESULT_REQUIRED_FIELD_MISSING:" + required);
            if (faultPoint == "PARTIAL_WRITE" && !result.ContainsKey("partial_artifact_identity") || faultPoint == "RESPONSE_NO_COMMIT" && !result.ContainsKey("orphan_response_identity") || faultPoint == "RECONCILIATION_UNCOMMITTED" && !result.ContainsKey("orphan_receipt_identity")) throw new InvalidDataException("RECOVERY_RESULT_FAULT_EVIDENCE_MISSING");
        }

        private static void RequireState(R7TransactionSnapshot snapshot, string state)
        {
            if (snapshot == null || snapshot.State != state) throw new InvalidDataException("RECOVERY_TRANSACTION_STATE_INVALID:" + state);
        }

        private static void RequireCommitted(R7TransactionSnapshot snapshot)
        {
            if (snapshot == null || snapshot.State != "COMMITTED" && snapshot.State != "RESPONSE_AVAILABLE") throw new InvalidDataException("RECOVERY_COMMITTED_STATE_MISSING");
        }

        private static string Sha(IDictionary<string, object> value, string name)
        {
            string result = R7Json.String(value, name, 64, 64);
            if (!R7Hash.IsLowerSha256(result)) throw new InvalidDataException("RECOVERY_SHA256_INVALID:" + name);
            return result;
        }

        private static byte[] Combine(byte[] left, byte[] right)
        {
            byte[] value = new byte[left.Length + right.Length];
            Buffer.BlockCopy(left, 0, value, 0, left.Length);
            Buffer.BlockCopy(right, 0, value, left.Length, right.Length);
            return value;
        }
    }
}
