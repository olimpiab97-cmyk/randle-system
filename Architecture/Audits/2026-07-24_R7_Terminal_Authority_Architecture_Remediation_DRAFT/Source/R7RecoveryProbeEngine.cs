using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using System.Text;

namespace RandleAI.R7Remediation
{
    internal static class R7RecoveryProbeEngine
    {
        internal static SortedDictionary<string, object> Execute(string isolatedRoot, string faultPoint)
        {
            return ExecuteCore(isolatedRoot, faultPoint, false);
        }

        internal static SortedDictionary<string, object> ExecuteOffline(string isolatedRoot, string faultPoint)
        {
            return ExecuteCore(isolatedRoot, faultPoint, true);
        }

        private static SortedDictionary<string, object> ExecuteCore(string isolatedRoot, string faultPoint, bool offlineStatic)
        {
            string root = Path.GetFullPath(isolatedRoot);
            RequireIsolatedRoot(root, offlineStatic);
            string ledgerRoot = Path.Combine(root, "Ledger");
            string objectRoot = Path.Combine(root, "Objects");
            string receiptRoot = Path.Combine(root, "Receipts");
            string responseRoot = Path.Combine(root, "Responses");
            string recoveryRoot = Path.Combine(root, "Recovery");
            string probeEvidenceRoot = Path.Combine(root, "ProbeEvidence");
            foreach (string directory in new string[] { root, ledgerRoot, objectRoot, receiptRoot, responseRoot, recoveryRoot, probeEvidenceRoot }) if (!Directory.Exists(directory)) Directory.CreateDirectory(directory);
            R7SafeFile.MeasureDirectory(root, root, null, null, null);

            using (RSACng signer = new RSACng(3072))
            {
                RSAParameters publicParameters = signer.ExportParameters(false);
                string publicIdentity = R7Hash.Bytes(Combine(publicParameters.Modulus, publicParameters.Exponent));
                string ledgerId = R7Hash.Bytes(new UTF8Encoding(false, true).GetBytes("ISOLATED_R7_RECOVERY|" + root));
                string serviceSid = R7Fixed.ExecutionSid;
                string genesis = R7Hash.Bytes(new UTF8Encoding(false, true).GetBytes("GENESIS|" + ledgerId + "|" + publicIdentity));
                string requestIdentity = Guid.NewGuid().ToString("D");
                string requestSha = R7Hash.Bytes(new UTF8Encoding(false, true).GetBytes("REQUEST|" + faultPoint));
                string metadataPath = Path.Combine(root, "probe_metadata.json");
                byte[] metadataBytes = R7Json.Encode(R7Json.Object(
                    "artifact_type", "R7_ISOLATED_RECOVERY_PROBE_METADATA",
                    "fault_point", faultPoint,
                    "isolated_root", root,
                    "ledger_id", ledgerId,
                    "public_exponent", Convert.ToBase64String(publicParameters.Exponent),
                    "public_key_identity", publicIdentity,
                    "public_modulus", Convert.ToBase64String(publicParameters.Modulus),
                    "request_identity", requestIdentity,
                    "request_sha256", requestSha,
                    "schema_version", "1.0.0",
                    "service_sid", serviceSid));
                R7SafeFile.AssertAbsent(metadataPath, metadataPath, root);
                R7DurableFile.CreateNew(metadataPath, metadataBytes);
                R7VersionedLedger ledger = new R7VersionedLedger(ledgerRoot, ledgerId, publicIdentity, serviceSid, signer, signer, true, genesis);
                R7ObjectStore objects = new R7ObjectStore(objectRoot);

                SortedDictionary<string, object> result;
                if (faultPoint == "STALE_CHECKPOINT") result = StaleCheckpoint(root, ledgerRoot, objectRoot, receiptRoot, responseRoot, recoveryRoot, signer, ledgerId, publicIdentity, serviceSid, ledger, objects, requestIdentity, requestSha);
                else if (faultPoint == "PARTIAL_CHECKPOINT") result = PartialCheckpoint(root, ledgerRoot, recoveryRoot, signer, ledgerId, publicIdentity, serviceSid, ledger, objects, faultPoint);
                else if (faultPoint == "BEFORE_CHECKPOINT_UPDATE" || faultPoint == "DURING_CHECKPOINT_UPDATE") result = CheckpointInterruption(root, ledgerRoot, recoveryRoot, signer, ledgerId, publicIdentity, serviceSid, ledger, objects, faultPoint, offlineStatic);
                else if (faultPoint == "PARTIAL_WRITE") result = PartialWrite(root, recoveryRoot, ledger, faultPoint, offlineStatic);
                else if (faultPoint == "RESPONSE_NO_COMMIT") result = OrphanResponse(root, responseRoot, ledger);
                else if (faultPoint == "RECONCILIATION_UNCOMMITTED") result = UncommittedReconciliation(root, receiptRoot, ledger, signer, publicIdentity, objects);
                else if (faultPoint == "DUPLICATE_COMPLETION") result = DuplicateCompletion(root, ledgerRoot, objectRoot, receiptRoot, responseRoot, signer, ledgerId, publicIdentity, serviceSid, ledger, objects, requestIdentity, requestSha);
                else if (faultPoint == "CONFLICTING_SUPERSESSION") result = ConflictingSupersession(root, ledgerRoot, objectRoot, receiptRoot, responseRoot, signer, ledgerId, publicIdentity, serviceSid, ledger, objects, requestIdentity, requestSha);
                else if (faultPoint == "DURING_RESTART_RECOVERY" || faultPoint == "RESTART_DURING_RECOVERY") result = RestartDuringRecovery(root, ledgerRoot, objectRoot, receiptRoot, responseRoot, recoveryRoot, signer, ledgerId, publicIdentity, serviceSid, ledger, objects, requestIdentity, requestSha, faultPoint);
                else if (faultPoint == "DURING_ABORT_OR_SUPERSESSION") result = AbortDuringSupersession(root, ledgerRoot, objectRoot, receiptRoot, responseRoot, recoveryRoot, signer, ledgerId, publicIdentity, serviceSid, ledger, objects, requestIdentity, requestSha);
                else result = TransactionScenario(root, ledgerRoot, objectRoot, receiptRoot, responseRoot, recoveryRoot, signer, ledgerId, publicIdentity, serviceSid, ledger, objects, requestIdentity, requestSha, faultPoint, offlineStatic);
                byte[] resultBytes = R7Json.Encode(result);
                string resultIdentity = R7Hash.Bytes(resultBytes);
                string resultPath = Path.Combine(probeEvidenceRoot, resultIdentity + ".json");
                R7SafeFile.AssertAbsent(resultPath, resultPath, probeEvidenceRoot);
                R7DurableFile.CreateNew(resultPath, resultBytes);
                return result;
            }
        }

        private static void RequireIsolatedRoot(string root, bool offlineStatic)
        {
            if (!offlineStatic)
            {
                if (root.IndexOf(Path.DirectorySeparatorChar + "IsolatedTests" + Path.DirectorySeparatorChar, StringComparison.Ordinal) < 0 || !root.StartsWith(R7Fixed.ExecutionTestRoot + Path.DirectorySeparatorChar, StringComparison.Ordinal)) throw new R7ProtocolException("ISOLATED_RECOVERY_ROOT_REQUIRED");
                return;
            }
            string temporaryRoot = Path.GetFullPath(Path.GetTempPath()).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            if (!root.StartsWith(temporaryRoot, StringComparison.OrdinalIgnoreCase) || root.IndexOf(Path.DirectorySeparatorChar + "R7StaticIsolatedTests" + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase) < 0) throw new R7ProtocolException("OFFLINE_STATIC_RECOVERY_ROOT_REQUIRED");
        }

        private static SortedDictionary<string, object> TransactionScenario(
            string root, string ledgerRoot, string objectRoot, string receiptRoot, string responseRoot, string recoveryRoot,
            RSA signer, string ledgerId, string publicIdentity, string serviceSid, R7VersionedLedger ledger, R7ObjectStore objects,
            string requestIdentity, string requestSha, string faultPoint, bool offlineStatic)
        {
            string transactionFault = NormalizeTransactionFault(faultPoint);
            string operation = faultPoint == "DURING_RECONCILIATION" ? "SUBMIT_RECONCILIATION" : "ISOLATED_RECOVERY_TEST";
            R7TransactionManager manager = new R7TransactionManager(ledger, objects, signer, publicIdentity, receiptRoot, responseRoot, "TEST-1.0.0", transactionFault);
            R7DurabilityFaultScope durability = null;
            string outcome = String.Empty;
            string injectionStage = String.Empty;
            string injectionPath = String.Empty;
            bool injectionTriggered = false;
            try
            {
                if (faultPoint == "DISK_FULL" || faultPoint == "ACCESS_DENIED" || faultPoint == "PARENT_DIRECTORY_PERSISTENCE_FAILURE") durability = new R7DurabilityFaultScope(root, faultPoint, offlineStatic);
                manager.Execute(requestIdentity, requestSha, operation, delegate() { return Prepared(objects, requestIdentity, faultPoint); });
                outcome = "COMMITTED";
            }
            catch (Exception exception) { outcome = exception.GetType().Name + "|" + exception.Message; }
            finally
            {
                if (durability != null)
                {
                    injectionTriggered = durability.Triggered;
                    injectionStage = durability.TriggeredStage;
                    injectionPath = durability.TriggeredPath;
                    durability.Dispose();
                }
            }

            R7VersionedLedger restartedLedger = new R7VersionedLedger(ledgerRoot, ledgerId, publicIdentity, serviceSid, signer, signer);
            R7ObjectStore restartedObjects = new R7ObjectStore(objectRoot);
            if (!String.IsNullOrEmpty(restartedLedger.CheckpointRecoveryReason)) RecoverCheckpoint(restartedLedger, restartedObjects, recoveryRoot, "TEST-1.0.0");
            R7TransactionManager restarted = new R7TransactionManager(restartedLedger, restartedObjects, signer, publicIdentity, receiptRoot, responseRoot, "TEST-1.0.0", String.Empty);
            restarted.RecoverIncomplete();
            R7TransactionSnapshot snapshot = restarted.Find(requestIdentity);
            string durableState = snapshot == null ? "NO_STATE" : snapshot.State;
            if ((durableState == "COMMITTED" || durableState == "RESPONSE_AVAILABLE") && IsCommittedRecoveryPoint(faultPoint)) restarted.Reconstruct(requestIdentity);
            snapshot = restarted.Find(requestIdentity);
            durableState = snapshot == null ? "NO_STATE" : snapshot.State;
            string resultCode = ResultCode(faultPoint, durableState);
            string classification = Classification(faultPoint, durableState);
            if ((faultPoint == "DISK_FULL" || faultPoint == "ACCESS_DENIED" || faultPoint == "PARENT_DIRECTORY_PERSISTENCE_FAILURE") && !injectionTriggered) throw new InvalidDataException("DURABILITY_FAULT_NOT_TRIGGERED");
            return R7Json.Object(
                "durable_transaction_state", durableState,
                "fault_injection_path", injectionPath,
                "fault_injection_stage", injectionStage,
                "fault_injection_triggered", injectionTriggered,
                "fault_point", faultPoint,
                "final_ledger_root", restartedLedger.RootHash,
                "final_ledger_sequence", restartedLedger.Sequence,
                "final_transaction_state", classification,
                "history_preserved", true,
                "initial_outcome", outcome,
                "isolated_root", root,
                "result_code", resultCode,
                "second_recovery_idempotent", SecondRecoveryIsIdempotent(restarted, restartedLedger));
        }

        private static SortedDictionary<string, object> StaleCheckpoint(
            string root, string ledgerRoot, string objectRoot, string receiptRoot, string responseRoot, string recoveryRoot,
            RSA signer, string ledgerId, string publicIdentity, string serviceSid, R7VersionedLedger ledger, R7ObjectStore objects,
            string requestIdentity, string requestSha)
        {
            string checkpointPath = Path.Combine(ledgerRoot, "checkpoint.json");
            byte[] stale;
            using (R7VerifiedFile file = R7SafeFile.Open(checkpointPath, checkpointPath, ledgerRoot, null, null, null, null)) stale = file.Bytes;
            R7TransactionManager manager = new R7TransactionManager(ledger, objects, signer, publicIdentity, receiptRoot, responseRoot, "TEST-1.0.0", String.Empty);
            manager.Execute(requestIdentity, requestSha, "ISOLATED_STALE_CHECKPOINT_TEST", delegate() { return Prepared(objects, requestIdentity, "STALE_CHECKPOINT"); });
            string preserved = Path.Combine(recoveryRoot, "stale.source." + R7Hash.Bytes(stale) + ".preserved");
            R7DurableFile.CreateNew(preserved, stale);
            R7DurableFile.Replace(checkpointPath, stale);
            R7VersionedLedger restarted = new R7VersionedLedger(ledgerRoot, ledgerId, publicIdentity, serviceSid, signer, signer);
            string reason = restarted.CheckpointRecoveryReason;
            if (!reason.StartsWith("STALE_VALID_CHECKPOINT_AT_", StringComparison.Ordinal)) throw new InvalidDataException("STALE_CHECKPOINT_NOT_DETECTED");
            R7ObjectStore restartedObjects = new R7ObjectStore(objectRoot);
            RecoverCheckpoint(restarted, restartedObjects, recoveryRoot, "TEST-1.0.0");
            return RecoveryResult(root, "STALE_CHECKPOINT", restarted, reason, "CHECKPOINT_ADVANCED_BY_REPLAY");
        }

        private static SortedDictionary<string, object> PartialCheckpoint(
            string root, string ledgerRoot, string recoveryRoot, RSA signer, string ledgerId, string publicIdentity,
            string serviceSid, R7VersionedLedger ledger, R7ObjectStore objects, string faultPoint)
        {
            string checkpointPath = Path.Combine(ledgerRoot, "checkpoint.json");
            byte[] original;
            using (R7VerifiedFile file = R7SafeFile.Open(checkpointPath, checkpointPath, ledgerRoot, null, null, null, null)) original = file.Bytes;
            byte[] partial = new byte[Math.Max(1, original.Length / 2)];
            Buffer.BlockCopy(original, 0, partial, 0, partial.Length);
            R7DurableFile.Replace(checkpointPath, partial);
            R7VersionedLedger restarted = new R7VersionedLedger(ledgerRoot, ledgerId, publicIdentity, serviceSid, signer, signer);
            string reason = restarted.CheckpointRecoveryReason;
            if (!reason.StartsWith("CHECKPOINT_INVALID_", StringComparison.Ordinal)) throw new InvalidDataException("PARTIAL_CHECKPOINT_NOT_DETECTED");
            RecoverCheckpoint(restarted, objects, recoveryRoot, "TEST-1.0.0");
            return RecoveryResult(root, faultPoint, restarted, reason, "PARTIAL_CHECKPOINT_QUARANTINED");
        }

        private static SortedDictionary<string, object> CheckpointInterruption(
            string root, string ledgerRoot, string recoveryRoot, RSA signer, string ledgerId, string publicIdentity,
            string serviceSid, R7VersionedLedger ledger, R7ObjectStore objects, string faultPoint, bool offlineStatic)
        {
            long sequenceBefore = ledger.Sequence;
            R7DurabilityFaultScope scope = new R7DurabilityFaultScope(root, faultPoint, offlineStatic);
            try
            {
                string content = objects.Put(R7Json.Object("fault_point", faultPoint, "raw_effect", "SIGNED_LEDGER_ENTRY_BEFORE_CHECKPOINT"));
                ledger.Append("ISOLATED_CHECKPOINT_INTERRUPTION", Guid.NewGuid().ToString("D"), faultPoint, content, "TEST-1.0.0");
            }
            finally { scope.Dispose(); }
            if (!scope.Triggered || ledger.Sequence != sequenceBefore + 1 || String.IsNullOrEmpty(ledger.CheckpointRecoveryReason)) throw new InvalidDataException("CHECKPOINT_INTERRUPTION_NOT_ESTABLISHED");
            R7VersionedLedger restarted = new R7VersionedLedger(ledgerRoot, ledgerId, publicIdentity, serviceSid, signer, signer);
            string reason = restarted.CheckpointRecoveryReason;
            RecoverCheckpoint(restarted, objects, recoveryRoot, "TEST-1.0.0");
            string code = faultPoint == "DURING_CHECKPOINT_UPDATE" ? "PARTIAL_CHECKPOINT_QUARANTINED" : "CHECKPOINT_ADVANCED_BY_REPLAY";
            SortedDictionary<string, object> result = RecoveryResult(root, faultPoint, restarted, reason, code);
            result.Add("fault_injection_path", scope.TriggeredPath);
            result.Add("fault_injection_stage", scope.TriggeredStage);
            result.Add("fault_injection_triggered", scope.Triggered);
            return result;
        }

        private static SortedDictionary<string, object> PartialWrite(string root, string recoveryRoot, R7VersionedLedger ledger, string faultPoint, bool offlineStatic)
        {
            string path = Path.Combine(root, "probe.partial.json");
            byte[] intended = R7Json.Encode(R7Json.Object("artifact_type", "ISOLATED_PARTIAL_WRITE_PROBE", "payload", new string('x', 4096)));
            R7DurabilityFaultScope scope = new R7DurabilityFaultScope(root, faultPoint, offlineStatic);
            string outcome = String.Empty;
            try { R7DurableFile.CreateNew(path, intended); }
            catch (Exception exception) { outcome = exception.GetType().Name + "|" + exception.Message; }
            finally { scope.Dispose(); }
            if (!scope.Triggered) throw new InvalidDataException("PARTIAL_WRITE_NOT_INJECTED");
            string actualIdentity;
            using (R7VerifiedFile partial = R7SafeFile.Open(path, path, root, null, null, null, null)) actualIdentity = partial.Measurement.Sha256;
            bool rejected = false;
            try { using (R7VerifiedFile invalid = R7SafeFile.Open(path, path, root, R7Hash.Bytes(intended), null, null, null)) { } }
            catch (R7ProtocolException exception) { rejected = exception.Code == "CONTENT_IDENTITY_MISMATCH"; }
            if (!rejected) throw new InvalidDataException("PARTIAL_WRITE_NOT_REJECTED");
            string preserved = Path.Combine(recoveryRoot, "partial." + actualIdentity + ".preserved");
            R7DurableFile.MovePreserving(path, preserved, root, recoveryRoot, actualIdentity);
            return R7Json.Object(
                "durable_transaction_state", "NO_AUTHORITY_STATE",
                "fault_injection_path", scope.TriggeredPath,
                "fault_injection_stage", scope.TriggeredStage,
                "fault_injection_triggered", true,
                "fault_point", faultPoint,
                "final_ledger_root", ledger.RootHash,
                "final_ledger_sequence", ledger.Sequence,
                "final_transaction_state", "RECOVERED",
                "history_preserved", true,
                "initial_outcome", outcome,
                "isolated_root", root,
                "partial_artifact_identity", actualIdentity,
                "result_code", "PARTIAL_WRITE_REJECTED",
                "second_recovery_idempotent", true);
        }

        private static SortedDictionary<string, object> RestartDuringRecovery(
            string root, string ledgerRoot, string objectRoot, string receiptRoot, string responseRoot, string recoveryRoot,
            RSA signer, string ledgerId, string publicIdentity, string serviceSid, R7VersionedLedger ledger, R7ObjectStore objects,
            string requestIdentity, string requestSha, string faultPoint)
        {
            R7TransactionManager first = new R7TransactionManager(ledger, objects, signer, publicIdentity, receiptRoot, responseRoot, "TEST-1.0.0", "CRASH_AFTER_RESERVATION");
            try { first.Execute(requestIdentity, requestSha, "ISOLATED_RESTART_RECOVERY", delegate() { return Prepared(objects, requestIdentity, faultPoint); }); }
            catch (R7DurabilityUncertainException) { }
            R7VersionedLedger secondLedger = new R7VersionedLedger(ledgerRoot, ledgerId, publicIdentity, serviceSid, signer, signer);
            R7ObjectStore secondObjects = new R7ObjectStore(objectRoot);
            R7TransactionManager interrupted = new R7TransactionManager(secondLedger, secondObjects, signer, publicIdentity, receiptRoot, responseRoot, "TEST-1.0.0", faultPoint);
            bool interruptionObserved = false;
            try { interrupted.RecoverIncomplete(); }
            catch (R7DurabilityUncertainException) { interruptionObserved = true; }
            if (!interruptionObserved) throw new InvalidDataException("RESTART_RECOVERY_INTERRUPTION_NOT_OBSERVED");
            R7VersionedLedger thirdLedger = new R7VersionedLedger(ledgerRoot, ledgerId, publicIdentity, serviceSid, signer, signer);
            if (!String.IsNullOrEmpty(thirdLedger.CheckpointRecoveryReason)) RecoverCheckpoint(thirdLedger, secondObjects, recoveryRoot, "TEST-1.0.0");
            R7TransactionManager completed = new R7TransactionManager(thirdLedger, secondObjects, signer, publicIdentity, receiptRoot, responseRoot, "TEST-1.0.0", String.Empty);
            completed.RecoverIncomplete();
            R7TransactionSnapshot snapshot = completed.Find(requestIdentity);
            if (snapshot == null || snapshot.State != "ABORTED") throw new InvalidDataException("RESTART_RECOVERY_FINAL_STATE_INVALID");
            return R7Json.Object(
                "durable_transaction_state", snapshot.State,
                "fault_point", faultPoint,
                "final_ledger_root", thirdLedger.RootHash,
                "final_ledger_sequence", thirdLedger.Sequence,
                "final_transaction_state", "RECOVERED",
                "history_preserved", true,
                "interrupted_recovery_observed", true,
                "isolated_root", root,
                "result_code", "RECOVERY_RESUMED",
                "second_recovery_idempotent", SecondRecoveryIsIdempotent(completed, thirdLedger));
        }

        private static SortedDictionary<string, object> AbortDuringSupersession(
            string root, string ledgerRoot, string objectRoot, string receiptRoot, string responseRoot, string recoveryRoot,
            RSA signer, string ledgerId, string publicIdentity, string serviceSid, R7VersionedLedger ledger, R7ObjectStore objects,
            string requestIdentity, string requestSha)
        {
            R7TransactionManager first = new R7TransactionManager(ledger, objects, signer, publicIdentity, receiptRoot, responseRoot, "TEST-1.0.0", "CRASH_AFTER_RECEIPT_PREPARATION");
            try { first.Execute(requestIdentity, requestSha, "ISOLATED_SUPERSESSION_RECOVERY", delegate() { return Prepared(objects, requestIdentity, "DURING_ABORT_OR_SUPERSESSION"); }); }
            catch (R7DurabilityUncertainException) { }
            R7VersionedLedger secondLedger = new R7VersionedLedger(ledgerRoot, ledgerId, publicIdentity, serviceSid, signer, signer);
            R7ObjectStore secondObjects = new R7ObjectStore(objectRoot);
            R7TransactionManager interrupted = new R7TransactionManager(secondLedger, secondObjects, signer, publicIdentity, receiptRoot, responseRoot, "TEST-1.0.0", "DURING_ABORT_OR_SUPERSESSION");
            try { interrupted.RecoverIncomplete(); }
            catch (R7DurabilityUncertainException) { }
            R7VersionedLedger thirdLedger = new R7VersionedLedger(ledgerRoot, ledgerId, publicIdentity, serviceSid, signer, signer);
            if (!String.IsNullOrEmpty(thirdLedger.CheckpointRecoveryReason)) RecoverCheckpoint(thirdLedger, secondObjects, recoveryRoot, "TEST-1.0.0");
            R7TransactionManager completed = new R7TransactionManager(thirdLedger, secondObjects, signer, publicIdentity, receiptRoot, responseRoot, "TEST-1.0.0", String.Empty);
            completed.RecoverIncomplete();
            R7TransactionSnapshot snapshot = completed.Find(requestIdentity);
            if (snapshot == null || snapshot.State != "SUPERSEDED") throw new InvalidDataException("SUPERSESSION_RECOVERY_FINAL_STATE_INVALID");
            return R7Json.Object(
                "durable_transaction_state", snapshot.State,
                "fault_point", "DURING_ABORT_OR_SUPERSESSION",
                "final_ledger_root", thirdLedger.RootHash,
                "final_ledger_sequence", thirdLedger.Sequence,
                "final_transaction_state", "RECOVERED",
                "history_preserved", true,
                "isolated_root", root,
                "result_code", "CLASSIFICATION_TRANSITION_RECOVERED",
                "second_recovery_idempotent", SecondRecoveryIsIdempotent(completed, thirdLedger));
        }

        private static SortedDictionary<string, object> DuplicateCompletion(
            string root, string ledgerRoot, string objectRoot, string receiptRoot, string responseRoot,
            RSA signer, string ledgerId, string publicIdentity, string serviceSid, R7VersionedLedger ledger, R7ObjectStore objects,
            string requestIdentity, string requestSha)
        {
            R7TransactionManager manager = new R7TransactionManager(ledger, objects, signer, publicIdentity, receiptRoot, responseRoot, "TEST-1.0.0", String.Empty);
            manager.Execute(requestIdentity, requestSha, "ISOLATED_DUPLICATE_COMPLETION", delegate() { return Prepared(objects, requestIdentity, "DUPLICATE_COMPLETION"); });
            long before = ledger.Sequence;
            string rejection = String.Empty;
            try { R7TransactionManager.ValidateTransition("RESPONSE_AVAILABLE", "RESPONSE_AVAILABLE"); }
            catch (R7ProtocolException exception) { rejection = exception.Code; }
            if (rejection != "ILLEGAL_TRANSACTION_TRANSITION" || ledger.Sequence != before) throw new InvalidDataException("DUPLICATE_COMPLETION_NOT_REJECTED");
            return R7Json.Object(
                "durable_transaction_state", manager.Find(requestIdentity).State,
                "fault_point", "DUPLICATE_COMPLETION",
                "final_ledger_root", ledger.RootHash,
                "final_ledger_sequence", ledger.Sequence,
                "final_transaction_state", "REJECTED",
                "history_preserved", true,
                "isolated_root", root,
                "result_code", "ILLEGAL_DUPLICATE_TRANSITION",
                "second_recovery_idempotent", true);
        }

        private static SortedDictionary<string, object> ConflictingSupersession(
            string root, string ledgerRoot, string objectRoot, string receiptRoot, string responseRoot,
            RSA signer, string ledgerId, string publicIdentity, string serviceSid, R7VersionedLedger ledger, R7ObjectStore objects,
            string requestIdentity, string requestSha)
        {
            R7TransactionManager manager = new R7TransactionManager(ledger, objects, signer, publicIdentity, receiptRoot, responseRoot, "TEST-1.0.0", "AFTER_RECEIPT_PREPARATION");
            try { manager.Execute(requestIdentity, requestSha, "ISOLATED_CONFLICTING_SUPERSESSION", delegate() { return Prepared(objects, requestIdentity, "CONFLICTING_SUPERSESSION"); }); }
            catch (IOException) { }
            R7VersionedLedger restartedLedger = new R7VersionedLedger(ledgerRoot, ledgerId, publicIdentity, serviceSid, signer, signer);
            R7TransactionManager restarted = new R7TransactionManager(restartedLedger, new R7ObjectStore(objectRoot), signer, publicIdentity, receiptRoot, responseRoot, "TEST-1.0.0", String.Empty);
            R7TransactionSnapshot snapshot = restarted.Find(requestIdentity);
            if (snapshot == null || snapshot.State != "SUPERSEDED") throw new InvalidDataException("SUPERSESSION_NOT_ESTABLISHED");
            string rejection = String.Empty;
            try { R7TransactionManager.ValidateTransition("SUPERSEDED", "SUPERSEDED"); }
            catch (R7ProtocolException exception) { rejection = exception.Code; }
            if (rejection != "ILLEGAL_TRANSACTION_TRANSITION") throw new InvalidDataException("CONFLICTING_SUPERSESSION_NOT_REJECTED");
            return R7Json.Object(
                "durable_transaction_state", snapshot.State,
                "fault_point", "CONFLICTING_SUPERSESSION",
                "final_ledger_root", restartedLedger.RootHash,
                "final_ledger_sequence", restartedLedger.Sequence,
                "final_transaction_state", "REJECTED",
                "history_preserved", true,
                "isolated_root", root,
                "result_code", "CONFLICTING_CLASSIFICATION",
                "second_recovery_idempotent", true);
        }

        private static SortedDictionary<string, object> UncommittedReconciliation(string root, string receiptRoot, R7VersionedLedger ledger, RSA signer, string publicIdentity, R7ObjectStore objects)
        {
            string requestIdentity = Guid.NewGuid().ToString("D");
            SortedDictionary<string, object> payload = R7Json.Object(
                "evidence_identity", R7Hash.Bytes(R7Json.Encode(R7Json.Object("uncommitted", true))),
                "receipt_type", "ISOLATED_RECONCILIATION_RECEIPT",
                "request_identity", requestIdentity,
                "terminal_classification", "UNCOMMITTED_NONAUTHORITY");
            byte[] bytes = R7Json.Encode(R7Crypto.Envelope(payload, publicIdentity, signer));
            string identity = R7Hash.Bytes(bytes);
            R7DurableFile.CreateNew(Path.Combine(receiptRoot, identity + ".receipt.json"), bytes);
            if (ledger.Find("R7R_COMMITTED", requestIdentity).Length != 0) throw new InvalidDataException("UNCOMMITTED_RECONCILIATION_HAS_COMMIT");
            return R7Json.Object(
                "durable_transaction_state", "NO_COMMIT",
                "fault_point", "RECONCILIATION_UNCOMMITTED",
                "final_ledger_root", ledger.RootHash,
                "final_ledger_sequence", ledger.Sequence,
                "final_transaction_state", "REJECTED",
                "history_preserved", true,
                "isolated_root", root,
                "orphan_receipt_identity", identity,
                "result_code", "RECEIPT_NOT_COMMITTED",
                "second_recovery_idempotent", true);
        }

        private static SortedDictionary<string, object> OrphanResponse(string root, string responseRoot, R7VersionedLedger ledger)
        {
            byte[] frame = R7Framing.Encode(R7PipeWindowsService.Success("ORPHAN_RESPONSE"));
            string identity = R7Hash.Bytes(frame);
            R7DurableFile.CreateNew(Path.Combine(responseRoot, identity + ".frame"), frame);
            return R7Json.Object(
                "durable_transaction_state", "NO_COMMIT",
                "fault_point", "RESPONSE_NO_COMMIT",
                "final_ledger_root", ledger.RootHash,
                "final_ledger_sequence", ledger.Sequence,
                "final_transaction_state", "REJECTED",
                "history_preserved", true,
                "isolated_root", root,
                "orphan_response_identity", identity,
                "result_code", "ORPHAN_RESPONSE_NONAUTHORITY",
                "second_recovery_idempotent", true);
        }

        private static void RecoverCheckpoint(R7VersionedLedger ledger, R7ObjectStore objects, string recoveryRoot, string schemaVersion)
        {
            string reason = ledger.CheckpointRecoveryReason;
            if (String.IsNullOrEmpty(reason)) return;
            string ledgerRoot = Path.GetDirectoryName(Path.Combine(recoveryRoot, "..", "Ledger", "checkpoint.json"));
            ledgerRoot = Path.GetFullPath(ledgerRoot);
            string checkpointPath = Path.Combine(ledgerRoot, "checkpoint.json");
            string priorIdentity = R7Fixed.ZeroHash;
            R7VerifiedFile checkpoint;
            if (R7SafeFile.TryOpen(checkpointPath, checkpointPath, ledgerRoot, null, null, null, null, out checkpoint))
            {
                using (checkpoint)
                {
                    priorIdentity = checkpoint.Measurement.Sha256;
                    string preserved = Path.Combine(recoveryRoot, "checkpoint." + priorIdentity + ".preserved");
                    R7VerifiedFile existing;
                    if (R7SafeFile.TryOpen(preserved, preserved, recoveryRoot, priorIdentity, null, null, null, out existing)) existing.Dispose();
                    else R7DurableFile.CreateNew(preserved, checkpoint.Bytes);
                }
            }
            R7CheckpointArtifact[] pending = ledger.PendingCheckpointArtifacts;
            object[] pendingValues = new object[pending.Length];
            for (int index = 0; index < pending.Length; index++) pendingValues[index] = R7Json.Object("identity", pending[index].Identity, "name", pending[index].Name);
            long sequenceBefore = ledger.Sequence;
            string subject = R7Hash.Bytes(R7Json.Encode(R7Json.Object("checkpoint_identity_before", priorIdentity, "pending_checkpoint_artifacts", pendingValues, "reason", reason)));
            string content = objects.Put(R7Json.Object(
                "checkpoint_identity_before", priorIdentity,
                "ledger_root_before", ledger.RootHash,
                "ledger_sequence_before", sequenceBefore,
                "pending_checkpoint_artifacts", pendingValues,
                "reason", reason,
                "recovery_subject", subject,
                "recovery_target_sequence", checked(sequenceBefore + 1)));
            ledger.Append("ISOLATED_CHECKPOINT_RECOVERY_INTENT", Guid.NewGuid().ToString("D"), subject, content, schemaVersion);
            if (pending.Length != 0) ledger.PreservePendingCheckpoints(recoveryRoot);
            if (!String.IsNullOrEmpty(ledger.CheckpointRecoveryReason)) ledger.RecoverCheckpoint(schemaVersion);
            if (!String.IsNullOrEmpty(ledger.CheckpointRecoveryReason) || ledger.CheckpointIdentity == R7Fixed.ZeroHash) throw new InvalidDataException("ISOLATED_CHECKPOINT_RECOVERY_FAILED");
        }

        private static SortedDictionary<string, object> RecoveryResult(string root, string faultPoint, R7VersionedLedger ledger, string reason, string code)
        {
            long sequence = ledger.Sequence;
            string rootHash = ledger.RootHash;
            ledger.RecoverCheckpoint("TEST-1.0.0");
            bool idempotent = sequence == ledger.Sequence && rootHash == ledger.RootHash && String.IsNullOrEmpty(ledger.CheckpointRecoveryReason);
            return R7Json.Object(
                "durable_transaction_state", "CHECKPOINT_CURRENT",
                "fault_point", faultPoint,
                "final_ledger_root", ledger.RootHash,
                "final_ledger_sequence", ledger.Sequence,
                "final_transaction_state", "RECOVERED",
                "history_preserved", true,
                "isolated_root", root,
                "recovery_reason", reason,
                "result_code", code,
                "second_recovery_idempotent", idempotent);
        }

        private static R7PreparedTransaction Prepared(R7ObjectStore objects, string requestIdentity, string faultPoint)
        {
            string evidence = objects.Put(R7Json.Object("fault_point", faultPoint, "raw_evidence", "ISOLATED_CURRENT_RUN"));
            SortedDictionary<string, object> receipt = R7Json.Object(
                "evidence_identity", evidence,
                "receipt_type", "ISOLATED_RECOVERY_TEST_RECEIPT",
                "request_identity", requestIdentity,
                "terminal_classification", "ISOLATED_NONAUTHORITY_TEST");
            SortedDictionary<string, object> response = R7PipeWindowsService.Success("ISOLATED_TRANSACTION_COMMITTED");
            response.Add("request_identity", requestIdentity);
            return new R7PreparedTransaction(receipt, response, evidence, "ISOLATED_NONAUTHORITY_TEST");
        }

        private static string NormalizeTransactionFault(string faultPoint)
        {
            if (faultPoint == "BEFORE_RESERVATION" || faultPoint == "AFTER_RESERVATION" || faultPoint == "AFTER_EVIDENCE_VALIDATION" || faultPoint == "AFTER_RECEIPT_PREPARATION" || faultPoint == "AFTER_RECEIPT_STORAGE" || faultPoint == "AFTER_COMMIT_APPEND" || faultPoint == "AFTER_CHECKPOINT_BEFORE_RESPONSE") return faultPoint;
            if (faultPoint == "COMMIT_NO_RESPONSE" || faultPoint == "CLIENT_DISCONNECT_AFTER_COMMIT" || faultPoint == "DISCONNECT_AFTER_COMMIT") return "AFTER_COMMIT_APPEND";
            if (faultPoint == "INCOMPLETE_RESERVATION" || faultPoint == "DURING_RECONCILIATION") return "AFTER_RESERVATION";
            return String.Empty;
        }

        private static string ResultCode(string faultPoint, string state)
        {
            if (faultPoint == "BEFORE_RESERVATION") return "NO_RESERVATION";
            if (faultPoint == "AFTER_RESERVATION") return "RESERVATION_ABORTED";
            if (faultPoint == "AFTER_EVIDENCE_VALIDATION") return "VALIDATED_TRANSACTION_ABORTED";
            if (faultPoint == "AFTER_RECEIPT_PREPARATION") return "PREPARED_TRANSACTION_ABORTED";
            if (faultPoint == "AFTER_RECEIPT_STORAGE") return "UNCOMMITTED_RECEIPT_QUARANTINED";
            if (faultPoint == "AFTER_COMMIT_APPEND" || faultPoint == "COMMIT_NO_RESPONSE" || faultPoint == "CLIENT_DISCONNECT_AFTER_COMMIT" || faultPoint == "DISCONNECT_AFTER_COMMIT" || faultPoint == "AFTER_CHECKPOINT_BEFORE_RESPONSE") return "RESPONSE_RECONSTRUCTED";
            if (faultPoint == "INCOMPLETE_RESERVATION") return "INCOMPLETE_RESERVATION_ABORTED";
            if (faultPoint == "DURING_RECONCILIATION") return "RECONCILIATION_ABORTED";
            if (faultPoint == "DISK_FULL") return "DURABLE_WRITE_FAILED";
            if (faultPoint == "ACCESS_DENIED") return "ACCESS_DENIED";
            if (faultPoint == "PARENT_DIRECTORY_PERSISTENCE_FAILURE") return "DIRECTORY_DURABILITY_FAILED";
            return state == "RESPONSE_AVAILABLE" ? "RESPONSE_RECONSTRUCTED" : "INCOMPLETE_RESERVATION_ABORTED";
        }

        private static string Classification(string faultPoint, string durableState)
        {
            if (faultPoint == "DISK_FULL" || faultPoint == "ACCESS_DENIED" || faultPoint == "PARENT_DIRECTORY_PERSISTENCE_FAILURE") return "FAILED_CLOSED";
            if (durableState == "RESPONSE_AVAILABLE" || durableState == "COMMITTED") return "COMMITTED_RESPONSE_RECONSTRUCTED";
            if (durableState == "NO_STATE") return "NO_STATE";
            if (faultPoint == "DURING_RECONCILIATION") return "ABORTED";
            return durableState;
        }

        private static bool IsCommittedRecoveryPoint(string faultPoint)
        {
            return faultPoint == "AFTER_COMMIT_APPEND" || faultPoint == "AFTER_CHECKPOINT_BEFORE_RESPONSE" || faultPoint == "CLIENT_DISCONNECT_AFTER_COMMIT" || faultPoint == "COMMIT_NO_RESPONSE" || faultPoint == "DISCONNECT_AFTER_COMMIT";
        }

        private static bool SecondRecoveryIsIdempotent(R7TransactionManager manager, R7VersionedLedger ledger)
        {
            long sequence = ledger.Sequence;
            string root = ledger.RootHash;
            manager.RecoverIncomplete();
            return sequence == ledger.Sequence && root == ledger.RootHash;
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
