using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Security;
using System.Security.Cryptography;

namespace RandleAI.R7Remediation
{
    internal sealed class R7PreparedTransaction
    {
        internal SortedDictionary<string, object> ReceiptPayload;
        internal SortedDictionary<string, object> ResponseMessage;
        internal string EvidenceIdentity;
        internal string TerminalClassification;

        internal R7PreparedTransaction(SortedDictionary<string, object> receiptPayload, SortedDictionary<string, object> responseMessage, string evidenceIdentity, string terminalClassification)
        {
            ReceiptPayload = receiptPayload;
            ResponseMessage = responseMessage;
            EvidenceIdentity = evidenceIdentity;
            TerminalClassification = terminalClassification;
        }
    }

    internal sealed class R7TransactionSnapshot
    {
        internal string RequestIdentity;
        internal string RequestSha256;
        internal string Operation;
        internal string State;
        internal string ReceiptIdentity;
        internal string ResponseIdentity;
        internal string EvidenceIdentity;
        internal string TerminalClassification;
        internal long LastSequence;
    }

    internal sealed class R7TransactionManager
    {
        private readonly object sync = new object();
        private readonly R7VersionedLedger ledger;
        private readonly R7ObjectStore objects;
        private readonly RSA signer;
        private readonly string publicKeyIdentity;
        private readonly string receiptRoot;
        private readonly string responseRoot;
        private readonly string schemaVersion;
        private readonly string faultPoint;
        private readonly bool isolatedFaults;
        private readonly Dictionary<string, R7TransactionSnapshot> transactions = new Dictionary<string, R7TransactionSnapshot>(StringComparer.Ordinal);

        internal R7TransactionManager(R7VersionedLedger fixedLedger, R7ObjectStore objectStore, RSA signingKey, string keyIdentity, string fixedReceiptRoot, string fixedResponseRoot, string fixedSchemaVersion, string injectedFaultPoint)
        {
            ledger = fixedLedger;
            objects = objectStore;
            signer = signingKey;
            publicKeyIdentity = keyIdentity;
            receiptRoot = Path.GetFullPath(fixedReceiptRoot);
            responseRoot = Path.GetFullPath(fixedResponseRoot);
            schemaVersion = fixedSchemaVersion;
            faultPoint = injectedFaultPoint ?? String.Empty;
            isolatedFaults = receiptRoot.IndexOf("IsolatedTests", StringComparison.OrdinalIgnoreCase) >= 0 && responseRoot.IndexOf("IsolatedTests", StringComparison.OrdinalIgnoreCase) >= 0;
            R7SafeFile.MeasureDirectory(receiptRoot, receiptRoot, null, null, null);
            R7SafeFile.MeasureDirectory(responseRoot, responseRoot, null, null, null);
            Rebuild();
        }

        internal SortedDictionary<string, object> Execute(string requestIdentity, string requestSha256, string operation, Func<R7PreparedTransaction> prepare)
        {
            Guid parsed;
            if (!Guid.TryParseExact(requestIdentity, "D", out parsed) || !String.Equals(parsed.ToString("D"), requestIdentity, StringComparison.Ordinal)) throw new R7ProtocolException("REQUEST_IDENTITY_INVALID");
            if (!R7Hash.IsLowerSha256(requestSha256)) throw new R7ProtocolException("REQUEST_HASH_INVALID");
            lock (sync)
            {
                R7TransactionSnapshot existing;
                if (transactions.TryGetValue(requestIdentity, out existing))
                {
                    if (!R7Hash.FixedTimeEquals(existing.RequestSha256, requestSha256)) throw new R7ProtocolException("REQUEST_IDENTITY_CONFLICT");
                    if (existing.State == "COMMITTED" || existing.State == "RESPONSE_AVAILABLE") return Reconstruct(existing, true);
                    if (existing.State == "ABORTED" || existing.State == "SUPERSEDED") throw new R7ProtocolException("REQUEST_ABORTED");
                    Abort(existing, "RETRY_RECOVERED_INCOMPLETE_RESERVATION");
                    if (R7Hash.IsLowerSha256(existing.ReceiptIdentity)) Supersede(existing, "INCOMPLETE_ARTIFACTS_SUPERSEDED");
                    throw new R7ProtocolException("INCOMPLETE_RESERVATION_ABORTED");
                }

                Fault("BEFORE_RESERVATION");
                R7TransactionSnapshot snapshot = new R7TransactionSnapshot
                {
                    RequestIdentity = requestIdentity,
                    RequestSha256 = requestSha256,
                    Operation = operation,
                    State = "NONE",
                    ReceiptIdentity = String.Empty,
                    ResponseIdentity = String.Empty,
                    EvidenceIdentity = String.Empty,
                    TerminalClassification = String.Empty,
                    LastSequence = 0
                };
                transactions.Add(requestIdentity, snapshot);
                try
                {
                    Transition(snapshot, "REQUEST_RECEIVED", String.Empty, String.Empty, String.Empty, "REQUEST_ACCEPTED");
                    Transition(snapshot, "RESERVED", String.Empty, String.Empty, String.Empty, "IDENTITY_RESERVED");
                    Fault("AFTER_RESERVATION");
                    R7PreparedTransaction prepared = prepare();
                    if (prepared == null || prepared.ReceiptPayload == null || prepared.ResponseMessage == null || !R7Hash.IsLowerSha256(prepared.EvidenceIdentity)) throw new R7ProtocolException("PREPARED_TRANSACTION_INVALID");
                    Transition(snapshot, "EVIDENCE_VALIDATED", String.Empty, String.Empty, prepared.EvidenceIdentity, prepared.TerminalClassification);
                    Fault("AFTER_EVIDENCE_VALIDATION");

                    SortedDictionary<string, object> receiptEnvelope = R7Crypto.Envelope(prepared.ReceiptPayload, publicKeyIdentity, signer);
                    byte[] receiptBytes = R7Json.Encode(receiptEnvelope);
                    string receiptIdentity = R7Hash.Bytes(receiptBytes);
                    if (prepared.ResponseMessage.ContainsKey("receipt_identity")) throw new R7ProtocolException("RESPONSE_RECEIPT_FIELD_PRESET");
                    prepared.ResponseMessage.Add("receipt_identity", receiptIdentity);
                    byte[] responseFrame = R7Framing.Encode(prepared.ResponseMessage);
                    string responseIdentity = R7Hash.Bytes(responseFrame);
                    snapshot.ReceiptIdentity = receiptIdentity;
                    snapshot.ResponseIdentity = responseIdentity;
                    snapshot.EvidenceIdentity = prepared.EvidenceIdentity;
                    Transition(snapshot, "RECEIPT_PREPARED", receiptIdentity, responseIdentity, prepared.EvidenceIdentity, prepared.TerminalClassification);
                    Fault("AFTER_RECEIPT_PREPARATION");

                    string receiptPath = Path.Combine(receiptRoot, receiptIdentity + ".receipt.json");
                    PersistContentAddressed(receiptPath, receiptRoot, receiptBytes, receiptIdentity);
                    string responsePath = Path.Combine(responseRoot, responseIdentity + ".frame");
                    PersistContentAddressed(responsePath, responseRoot, responseFrame, responseIdentity);
                    Fault("AFTER_RECEIPT_STORAGE");

                    Transition(snapshot, "COMMITTED", receiptIdentity, responseIdentity, prepared.EvidenceIdentity, prepared.TerminalClassification);
                    Fault("AFTER_COMMIT_APPEND");
                    Transition(snapshot, "RESPONSE_AVAILABLE", receiptIdentity, responseIdentity, prepared.EvidenceIdentity, prepared.TerminalClassification);
                    Fault("AFTER_CHECKPOINT_BEFORE_RESPONSE");
                    return prepared.ResponseMessage;
                }
                catch (R7DurabilityUncertainException)
                {
                    throw;
                }
                catch
                {
                    if (snapshot.State == "COMMITTED" || snapshot.State == "RESPONSE_AVAILABLE") return Reconstruct(snapshot, true);
                    if (snapshot.State != "ABORTED")
                    {
                        try
                        {
                            Abort(snapshot, "TRANSACTION_PRECOMMIT_FAILURE");
                            if (R7Hash.IsLowerSha256(snapshot.ReceiptIdentity)) Supersede(snapshot, "INCOMPLETE_ARTIFACTS_SUPERSEDED");
                        }
                        catch { }
                    }
                    throw;
                }
            }
        }

        internal void RecoverIncomplete()
        {
            lock (sync)
            {
                List<R7TransactionSnapshot> incomplete = new List<R7TransactionSnapshot>();
                foreach (R7TransactionSnapshot snapshot in transactions.Values)
                {
                    if (snapshot.State != "COMMITTED" && snapshot.State != "RESPONSE_AVAILABLE" && snapshot.State != "ABORTED" && snapshot.State != "SUPERSEDED") incomplete.Add(snapshot);
                }
                incomplete.Sort(delegate(R7TransactionSnapshot left, R7TransactionSnapshot right) { return left.LastSequence.CompareTo(right.LastSequence); });
                foreach (R7TransactionSnapshot snapshot in incomplete)
                {
                    Abort(snapshot, "STARTUP_RECOVERY_ABORT");
                    if (R7Hash.IsLowerSha256(snapshot.ReceiptIdentity)) Supersede(snapshot, "INCOMPLETE_ARTIFACTS_SUPERSEDED");
                }
            }
        }

        internal R7TransactionSnapshot Find(string requestIdentity)
        {
            lock (sync)
            {
                R7TransactionSnapshot value;
                return transactions.TryGetValue(requestIdentity, out value) ? value : null;
            }
        }

        internal R7TransactionSnapshot FindByReceipt(string receiptIdentity)
        {
            if (!R7Hash.IsLowerSha256(receiptIdentity)) throw new R7ProtocolException("RECEIPT_IDENTITY_INVALID");
            lock (sync)
            {
                foreach (R7TransactionSnapshot value in transactions.Values) if (String.Equals(value.ReceiptIdentity, receiptIdentity, StringComparison.Ordinal)) return value;
                return null;
            }
        }

        internal SortedDictionary<string, object> Reconstruct(string requestIdentity)
        {
            lock (sync)
            {
                R7TransactionSnapshot value;
                if (!transactions.TryGetValue(requestIdentity, out value)) throw new R7ProtocolException("REQUEST_IDENTITY_UNRESOLVED");
                return Reconstruct(value, true);
            }
        }

        private SortedDictionary<string, object> Reconstruct(R7TransactionSnapshot snapshot, bool advanceResponseState)
        {
            if (snapshot.State != "COMMITTED" && snapshot.State != "RESPONSE_AVAILABLE") throw new R7ProtocolException("REQUEST_NOT_COMMITTED");
            string path = Path.Combine(responseRoot, snapshot.ResponseIdentity + ".frame");
            byte[] bytes;
            SortedDictionary<string, object> message;
            try
            {
                using (R7VerifiedFile file = R7SafeFile.Open(path, path, responseRoot, snapshot.ResponseIdentity, null, null, null)) bytes = file.Bytes;
                message = R7Framing.Decode(bytes);
            }
            catch (Exception exception)
            {
                throw new R7DurabilityUncertainException("COMMITTED_RESPONSE_RESOLUTION_UNCERTAIN", exception);
            }
            if (advanceResponseState && snapshot.State == "COMMITTED")
            {
                try { Transition(snapshot, "RESPONSE_AVAILABLE", snapshot.ReceiptIdentity, snapshot.ResponseIdentity, snapshot.EvidenceIdentity, "RECOVERED_RESPONSE"); }
                catch (IOException)
                {
                    // COMMITTED binds this exact content-addressed response. A
                    // failure to append the delivery-availability marker cannot
                    // turn that committed authority into a rejection.
                }
                catch (UnauthorizedAccessException)
                {
                    // The same committed response remains reconstructable and
                    // retry-safe even when the optional marker cannot advance.
                }
            }
            return message;
        }

        private void Abort(R7TransactionSnapshot snapshot, string reason)
        {
            if (snapshot.State == "COMMITTED" || snapshot.State == "RESPONSE_AVAILABLE") throw new InvalidOperationException("COMMITTED_TRANSACTION_CANNOT_ABORT");
            if (snapshot.State == "ABORTED") return;
            Transition(snapshot, "ABORTED", snapshot.ReceiptIdentity, snapshot.ResponseIdentity, snapshot.EvidenceIdentity, reason);
        }

        private void Supersede(R7TransactionSnapshot snapshot, string reason)
        {
            if (snapshot.State == "SUPERSEDED") return;
            if (snapshot.State != "ABORTED") throw new InvalidOperationException("ONLY_ABORTED_TRANSACTION_CAN_BE_SUPERSEDED");
            Transition(snapshot, "SUPERSEDED", snapshot.ReceiptIdentity, snapshot.ResponseIdentity, snapshot.EvidenceIdentity, reason);
        }

        private void Transition(R7TransactionSnapshot snapshot, string nextState, string receiptIdentity, string responseIdentity, string evidenceIdentity, string classification)
        {
            ValidateTransition(snapshot.State, nextState);
            if (nextState == "ABORTED" && (faultPoint == "DURING_ABORT_OR_SUPERSESSION" || faultPoint == "DURING_RESTART_RECOVERY" || faultPoint == "RESTART_DURING_RECOVERY")) Fault(faultPoint);
            if (nextState == "EVIDENCE_VALIDATED")
            {
                if (String.IsNullOrEmpty(classification)) throw new R7ProtocolException("TERMINAL_CLASSIFICATION_MISSING");
                snapshot.TerminalClassification = classification;
            }
            else if (nextState == "RECEIPT_PREPARED" || nextState == "COMMITTED")
            {
                if (String.IsNullOrEmpty(snapshot.TerminalClassification) || !String.Equals(snapshot.TerminalClassification, classification, StringComparison.Ordinal)) throw new R7ProtocolException("TERMINAL_CLASSIFICATION_CHANGED");
            }
            else if (nextState == "RESPONSE_AVAILABLE" && !String.Equals(snapshot.TerminalClassification, classification, StringComparison.Ordinal) && !String.Equals(classification, "RECOVERED_RESPONSE", StringComparison.Ordinal))
            {
                throw new R7ProtocolException("RESPONSE_CLASSIFICATION_INVALID");
            }
            string prior = snapshot.State;
            SortedDictionary<string, object> stateObject = R7Json.Object(
                "classification", classification ?? String.Empty,
                "evidence_identity", evidenceIdentity ?? String.Empty,
                "operation", snapshot.Operation,
                "prior_state", prior,
                "receipt_identity", receiptIdentity ?? String.Empty,
                "request_identity", snapshot.RequestIdentity,
                "request_sha256", snapshot.RequestSha256,
                "response_identity", responseIdentity ?? String.Empty,
                "schema_version", schemaVersion,
                "state", nextState,
                "transition_time", DateTimeOffset.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture));
            string content = objects.Put(stateObject);
            R7LedgerAppend append = ledger.Append("R7R_" + nextState, Guid.NewGuid().ToString("D"), snapshot.RequestIdentity, content, schemaVersion);
            snapshot.State = nextState;
            snapshot.ReceiptIdentity = receiptIdentity ?? String.Empty;
            snapshot.ResponseIdentity = responseIdentity ?? String.Empty;
            snapshot.EvidenceIdentity = evidenceIdentity ?? String.Empty;
            snapshot.LastSequence = append.Record.Sequence;
        }

        internal static void ValidateTransition(string prior, string next)
        {
            bool valid =
                (prior == "NONE" && next == "REQUEST_RECEIVED") ||
                (prior == "REQUEST_RECEIVED" && (next == "RESERVED" || next == "ABORTED")) ||
                (prior == "RESERVED" && (next == "EVIDENCE_VALIDATED" || next == "ABORTED")) ||
                (prior == "EVIDENCE_VALIDATED" && (next == "RECEIPT_PREPARED" || next == "ABORTED")) ||
                (prior == "RECEIPT_PREPARED" && (next == "COMMITTED" || next == "ABORTED")) ||
                (prior == "COMMITTED" && next == "RESPONSE_AVAILABLE") ||
                (prior == "ABORTED" && next == "SUPERSEDED");
            if (!valid) throw new R7ProtocolException("ILLEGAL_TRANSACTION_TRANSITION", prior + "->" + next);
        }

        private void Rebuild()
        {
            foreach (R7LedgerRecord record in ledger.Records)
            {
                if (!IsTransactionLedgerOperation(record.Operation)) continue;
                if (!R7Hash.IsLowerSha256(record.ContentAddress)) throw new InvalidDataException("TRANSACTION_STATE_CONTENT_IDENTITY_INVALID");
                SortedDictionary<string, object> state = objects.Get(record.ContentAddress);
                R7Json.ExactKeys(state,
                    "classification", "evidence_identity", "operation", "prior_state", "receipt_identity", "request_identity",
                    "request_sha256", "response_identity", "schema_version", "state", "transition_time");
                string requestIdentity = R7Json.String(state, "request_identity", 36, 36);
                Guid parsedRequestIdentity;
                if (!Guid.TryParseExact(requestIdentity, "D", out parsedRequestIdentity) || !String.Equals(parsedRequestIdentity.ToString("D"), requestIdentity, StringComparison.Ordinal)) throw new InvalidDataException("TRANSACTION_REQUEST_IDENTITY_INVALID");
                string requestSha256 = R7Json.String(state, "request_sha256", 64, 64);
                if (!R7Hash.IsLowerSha256(requestSha256)) throw new InvalidDataException("TRANSACTION_REQUEST_HASH_INVALID");
                string governedOperation = R7Json.String(state, "operation", 1, 256);
                string next = R7Json.String(state, "state", 1, 128);
                string prior = R7Json.String(state, "prior_state", 0, 128);
                string receiptIdentity = R7Json.String(state, "receipt_identity", 0, 64);
                string responseIdentity = R7Json.String(state, "response_identity", 0, 64);
                string evidenceIdentity = R7Json.String(state, "evidence_identity", 0, 64);
                string classification = R7Json.String(state, "classification", 1, 4096);
                string transitionTime = R7Json.String(state, "transition_time", 28, 28);
                DateTimeOffset parsedTransitionTime;
                if (!DateTimeOffset.TryParseExact(transitionTime, "yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out parsedTransitionTime)) throw new InvalidDataException("TRANSACTION_TIME_INVALID");
                if (!String.Equals(record.SubjectId, requestIdentity, StringComparison.Ordinal) ||
                    !String.Equals(record.Operation, "R7R_" + next, StringComparison.Ordinal) ||
                    !String.Equals(record.SchemaVersion, schemaVersion, StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(state, "schema_version", 1, 128), schemaVersion, StringComparison.Ordinal)) throw new InvalidDataException("TRANSACTION_LEDGER_BINDING_MISMATCH");
                if ((receiptIdentity.Length != 0 && !R7Hash.IsLowerSha256(receiptIdentity)) ||
                    (responseIdentity.Length != 0 && !R7Hash.IsLowerSha256(responseIdentity)) ||
                    (evidenceIdentity.Length != 0 && !R7Hash.IsLowerSha256(evidenceIdentity))) throw new InvalidDataException("TRANSACTION_DURABLE_IDENTITY_INVALID");
                if ((next == "REQUEST_RECEIVED" || next == "RESERVED") && (receiptIdentity.Length != 0 || responseIdentity.Length != 0 || evidenceIdentity.Length != 0)) throw new InvalidDataException("TRANSACTION_PREVALIDATION_IDENTITY_PRESENT");
                if (next == "EVIDENCE_VALIDATED" && (receiptIdentity.Length != 0 || responseIdentity.Length != 0 || !R7Hash.IsLowerSha256(evidenceIdentity))) throw new InvalidDataException("TRANSACTION_VALIDATED_IDENTITY_SET_INVALID");
                if ((next == "RECEIPT_PREPARED" || next == "COMMITTED" || next == "RESPONSE_AVAILABLE") &&
                    (!R7Hash.IsLowerSha256(receiptIdentity) || !R7Hash.IsLowerSha256(responseIdentity) || !R7Hash.IsLowerSha256(evidenceIdentity))) throw new InvalidDataException("TRANSACTION_COMMIT_IDENTITY_SET_INVALID");
                if (next == "ABORTED")
                {
                    bool validAbortIdentities =
                        ((prior == "REQUEST_RECEIVED" || prior == "RESERVED") && receiptIdentity.Length == 0 && responseIdentity.Length == 0 && evidenceIdentity.Length == 0) ||
                        (prior == "EVIDENCE_VALIDATED" && receiptIdentity.Length == 0 && responseIdentity.Length == 0 && R7Hash.IsLowerSha256(evidenceIdentity)) ||
                        (prior == "RECEIPT_PREPARED" && R7Hash.IsLowerSha256(receiptIdentity) && R7Hash.IsLowerSha256(responseIdentity) && R7Hash.IsLowerSha256(evidenceIdentity));
                    if (!validAbortIdentities) throw new InvalidDataException("TRANSACTION_ABORT_IDENTITY_SET_INVALID");
                    if (classification != "TRANSACTION_PRECOMMIT_FAILURE" && classification != "RETRY_RECOVERED_INCOMPLETE_RESERVATION" && classification != "STARTUP_RECOVERY_ABORT") throw new InvalidDataException("TRANSACTION_ABORT_CLASSIFICATION_INVALID");
                }
                if (next == "SUPERSEDED")
                {
                    if (classification != "INCOMPLETE_ARTIFACTS_SUPERSEDED") throw new InvalidDataException("TRANSACTION_SUPERSESSION_CLASSIFICATION_INVALID");
                }
                R7TransactionSnapshot snapshot;
                if (!transactions.TryGetValue(requestIdentity, out snapshot))
                {
                    snapshot = new R7TransactionSnapshot
                    {
                        RequestIdentity = requestIdentity,
                        RequestSha256 = requestSha256,
                        Operation = governedOperation,
                        State = "NONE",
                        ReceiptIdentity = String.Empty,
                        ResponseIdentity = String.Empty,
                        EvidenceIdentity = String.Empty,
                        TerminalClassification = String.Empty
                    };
                    transactions.Add(requestIdentity, snapshot);
                }
                ValidateTransition(snapshot.State, next);
                if (!String.Equals(snapshot.RequestSha256, requestSha256, StringComparison.Ordinal) ||
                    !String.Equals(snapshot.Operation, governedOperation, StringComparison.Ordinal) ||
                    !String.Equals(snapshot.State, prior, StringComparison.Ordinal)) throw new InvalidDataException("TRANSACTION_CHAIN_MISMATCH");
                if ((snapshot.ReceiptIdentity != null && snapshot.ReceiptIdentity.Length != 0 && !String.Equals(snapshot.ReceiptIdentity, receiptIdentity, StringComparison.Ordinal)) ||
                    (snapshot.ResponseIdentity != null && snapshot.ResponseIdentity.Length != 0 && !String.Equals(snapshot.ResponseIdentity, responseIdentity, StringComparison.Ordinal)) ||
                    (snapshot.EvidenceIdentity != null && snapshot.EvidenceIdentity.Length != 0 && !String.Equals(snapshot.EvidenceIdentity, evidenceIdentity, StringComparison.Ordinal))) throw new InvalidDataException("TRANSACTION_DURABLE_IDENTITY_CHANGED");
                if (next == "EVIDENCE_VALIDATED") snapshot.TerminalClassification = classification;
                else if (next == "RECEIPT_PREPARED" || next == "COMMITTED")
                {
                    if (String.IsNullOrEmpty(snapshot.TerminalClassification) || !String.Equals(snapshot.TerminalClassification, classification, StringComparison.Ordinal)) throw new InvalidDataException("TRANSACTION_TERMINAL_CLASSIFICATION_CHANGED");
                }
                else if (next == "RESPONSE_AVAILABLE" && !String.Equals(snapshot.TerminalClassification, classification, StringComparison.Ordinal) && !String.Equals(classification, "RECOVERED_RESPONSE", StringComparison.Ordinal)) throw new InvalidDataException("TRANSACTION_RESPONSE_CLASSIFICATION_INVALID");
                snapshot.State = next;
                snapshot.ReceiptIdentity = receiptIdentity;
                snapshot.ResponseIdentity = responseIdentity;
                snapshot.EvidenceIdentity = evidenceIdentity;
                snapshot.LastSequence = record.Sequence;
            }
            foreach (R7TransactionSnapshot snapshot in transactions.Values)
            {
                if (snapshot.State != "COMMITTED" && snapshot.State != "RESPONSE_AVAILABLE") continue;
                string receiptPath = Path.Combine(receiptRoot, snapshot.ReceiptIdentity + ".receipt.json");
                string responsePath = Path.Combine(responseRoot, snapshot.ResponseIdentity + ".frame");
                using (R7VerifiedFile receipt = R7SafeFile.Open(receiptPath, receiptPath, receiptRoot, snapshot.ReceiptIdentity, null, null, null)) { }
                using (R7VerifiedFile response = R7SafeFile.Open(responsePath, responsePath, responseRoot, snapshot.ResponseIdentity, null, null, null)) R7Framing.Decode(response.Bytes);
            }
        }

        internal static bool IsTransactionLedgerOperation(string operation)
        {
            return operation == "R7R_REQUEST_RECEIVED" || operation == "R7R_RESERVED" || operation == "R7R_EVIDENCE_VALIDATED" ||
                operation == "R7R_RECEIPT_PREPARED" || operation == "R7R_COMMITTED" || operation == "R7R_RESPONSE_AVAILABLE" ||
                operation == "R7R_ABORTED" || operation == "R7R_SUPERSEDED";
        }

        private static void PersistContentAddressed(string path, string root, byte[] bytes, string identity)
        {
            R7VerifiedFile existing;
            if (R7SafeFile.TryOpen(path, path, root, identity, null, null, null, out existing))
            {
                existing.Dispose();
                return;
            }
            try { R7DurableFile.CreateNew(path, bytes); }
            catch (IOException exception)
            {
                if (!R7DurableFile.IsAlreadyExists(exception)) throw;
                if (!R7SafeFile.TryOpen(path, path, root, identity, null, null, null, out existing)) throw;
                existing.Dispose();
            }
        }

        private void Fault(string point)
        {
            bool incompleteReservationCrash = faultPoint == "CRASH_AFTER_RESERVATION" && point == "AFTER_RESERVATION";
            bool incompletePreparationCrash = faultPoint == "CRASH_AFTER_RECEIPT_PREPARATION" && point == "AFTER_RECEIPT_PREPARATION";
            if (!String.Equals(faultPoint, point, StringComparison.Ordinal) && !incompleteReservationCrash && !incompletePreparationCrash) return;
            if (!isolatedFaults) throw new SecurityException("LIVE_FAULT_INJECTION_FORBIDDEN");
            if (incompleteReservationCrash || incompletePreparationCrash || point == "DURING_ABORT_OR_SUPERSESSION" || point == "DURING_RESTART_RECOVERY" || point == "RESTART_DURING_RECOVERY") throw new R7DurabilityUncertainException("INJECTED_PROCESS_CRASH_" + point, null);
            throw new IOException("INJECTED_FAULT_" + point);
        }
    }
}
