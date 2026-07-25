using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;

namespace RandleAI.R7Remediation
{
    internal sealed class R7InteractionEvidence
    {
        internal string InteractionIdentity;
        internal string CaptureIdentity;
        internal SortedDictionary<string, object> Capture;
    }

    internal sealed class R7EvidenceStore
    {
        private readonly object sync = new object();
        private readonly string root;
        private readonly R7ObjectStore objects;
        private readonly string expectedOwnerSid;
        private readonly string expectedVolumeIdentity;
        private readonly Dictionary<string, string> captureByInteraction = new Dictionary<string, string>(StringComparer.Ordinal);
        private readonly Dictionary<string, List<string>> interactionsByRequestFrame = new Dictionary<string, List<string>>(StringComparer.Ordinal);

        internal R7EvidenceStore(string fixedRoot, R7ObjectStore objectStore) : this(fixedRoot, objectStore, null, null) { }

        internal R7EvidenceStore(string fixedRoot, R7ObjectStore objectStore, string ownerSid, string volumeIdentity)
        {
            root = Path.GetFullPath(fixedRoot);
            objects = objectStore;
            expectedOwnerSid = ownerSid;
            expectedVolumeIdentity = volumeIdentity;
            R7SafeFile.MeasureDirectory(root, root, expectedOwnerSid == null ? null : R7Fixed.SystemSid, null, expectedVolumeIdentity);
            LoadIndex();
        }

        internal string Record(R7RequestContext context, SortedDictionary<string, object> request, SortedDictionary<string, object> response, long ledgerBefore, string rootBefore, long ledgerAfter, string rootAfter, SortedDictionary<string, object> protectedStateBefore, SortedDictionary<string, object> protectedStateAfter, string derivation)
        {
            lock (sync)
            {
                string seed = context.ConnectionIdentity + "|" + context.RequestFrameSha256 + "|" + context.Caller.TokenId + "|" + context.ReceiveTime.ToString("o", CultureInfo.InvariantCulture);
                string interaction = R7Hash.Bytes(new UTF8Encoding(false, true).GetBytes(seed));
                byte[] responseFrame = R7Framing.Encode(response);
                SortedDictionary<string, object> capture = R7Json.Object(
                    "artifact_type", "R7_SERVER_OBSERVED_OUTER_INTERACTION",
                    "caller", context.Caller.ToJson(),
                    "connection_identity", context.ConnectionIdentity,
                    "concurrent_connection_count_at_receive", (long)context.ConcurrentConnectionCountAtReceive,
                    "derivation", derivation,
                    "interaction_identity", interaction,
                    "ledger_root_after", rootAfter,
                    "ledger_root_before", rootBefore,
                    "ledger_sequence_after", ledgerAfter,
                    "ledger_sequence_before", ledgerBefore,
                    "receive_time", context.ReceiveTime.ToString("yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture),
                    "request_frame", Convert.ToBase64String(context.RequestFrame ?? new byte[0]),
                    "request_frame_sha256", context.RequestFrameSha256 ?? R7Fixed.ZeroHash,
                    "request_payload_sha256", context.RequestPayloadSha256 ?? R7Fixed.ZeroHash,
                    "response_frame", Convert.ToBase64String(responseFrame),
                    "response_frame_sha256", R7Hash.Bytes(responseFrame),
                    "response_message", response,
                    "server_derived_evidence", context.ServerDerivedEvidence ?? R7Json.Object(),
                    "protected_state_after", protectedStateAfter,
                    "protected_state_before", protectedStateBefore,
                    "protocol_error_code", context.ProtocolErrorCode ?? String.Empty,
                    "protocol_error_offset", (long)context.ProtocolErrorOffset,
                    "schema_version", "1.0.0");
                string captureIdentity = objects.Put(capture);
                SortedDictionary<string, object> mapping = R7Json.Object(
                    "capture_identity", captureIdentity,
                    "interaction_identity", interaction,
                    "request_frame_sha256", context.RequestFrameSha256 ?? R7Fixed.ZeroHash,
                    "schema_version", "1.0.0");
                string mappingPath = Path.Combine(root, interaction + ".interaction.json");
                R7VerifiedFile existing;
                if (R7SafeFile.TryOpen(mappingPath, mappingPath, root, null, expectedOwnerSid, null, expectedVolumeIdentity, out existing))
                {
                    existing.Dispose();
                    throw new InvalidDataException("INTERACTION_IDENTITY_COLLISION");
                }
                R7DurableFile.CreateNew(mappingPath, R7Json.Encode(mapping));
                using (R7VerifiedFile verify = R7SafeFile.Open(mappingPath, mappingPath, root, null, expectedOwnerSid, null, expectedVolumeIdentity)) { }
                Index(interaction, captureIdentity, context.RequestFrameSha256 ?? R7Fixed.ZeroHash);
                return interaction;
            }
        }

        internal R7InteractionEvidence Resolve(string interactionIdentity)
        {
            if (!R7Hash.IsLowerSha256(interactionIdentity)) throw new R7ProtocolException("INTERACTION_IDENTITY_INVALID");
            lock (sync)
            {
                string captureIdentity;
                if (!captureByInteraction.TryGetValue(interactionIdentity, out captureIdentity)) throw new R7ProtocolException("INTERACTION_UNRESOLVED");
                SortedDictionary<string, object> capture = objects.Get(captureIdentity);
                if (!String.Equals(R7Json.String(capture, "interaction_identity", 64, 64), interactionIdentity, StringComparison.Ordinal)) throw new InvalidDataException("INTERACTION_MAPPING_MISMATCH");
                return new R7InteractionEvidence { InteractionIdentity = interactionIdentity, CaptureIdentity = captureIdentity, Capture = capture };
            }
        }

        internal string ResolveLatestByRequestFrame(string requestFrameSha256, string callerSid)
        {
            if (!R7Hash.IsLowerSha256(requestFrameSha256)) throw new R7ProtocolException("REQUEST_FRAME_IDENTITY_INVALID");
            lock (sync)
            {
                List<string> values;
                if (!interactionsByRequestFrame.TryGetValue(requestFrameSha256, out values)) throw new R7ProtocolException("INTERACTION_UNRESOLVED");
                for (int i = values.Count - 1; i >= 0; i--)
                {
                    R7InteractionEvidence evidence = Resolve(values[i]);
                    SortedDictionary<string, object> caller = R7Json.Child(evidence.Capture, "caller");
                    if (String.Equals(R7Json.String(caller, "user_sid", 1, 256), callerSid, StringComparison.Ordinal)) return values[i];
                }
                throw new R7ProtocolException("INTERACTION_CALLER_MISMATCH");
            }
        }

        internal R7InteractionEvidence ResolveLatestByRequestFrame(string requestFrameSha256)
        {
            if (!R7Hash.IsLowerSha256(requestFrameSha256)) throw new R7ProtocolException("REQUEST_FRAME_IDENTITY_INVALID");
            lock (sync)
            {
                List<string> values;
                if (!interactionsByRequestFrame.TryGetValue(requestFrameSha256, out values) || values.Count == 0) throw new R7ProtocolException("INTERACTION_UNRESOLVED");
                return Resolve(values[values.Count - 1]);
            }
        }

        internal R7InteractionEvidence[] ResolveAllByRequestFrame(string requestFrameSha256)
        {
            if (!R7Hash.IsLowerSha256(requestFrameSha256)) throw new R7ProtocolException("REQUEST_FRAME_IDENTITY_INVALID");
            lock (sync)
            {
                List<string> values;
                if (!interactionsByRequestFrame.TryGetValue(requestFrameSha256, out values) || values.Count == 0) throw new R7ProtocolException("INTERACTION_UNRESOLVED");
                R7InteractionEvidence[] result = new R7InteractionEvidence[values.Count];
                for (int index = 0; index < values.Count; index++) result[index] = Resolve(values[index]);
                return result;
            }
        }

        private void LoadIndex()
        {
            if (Directory.GetDirectories(root, "*", SearchOption.TopDirectoryOnly).Length != 0) throw new InvalidDataException("INTERACTION_DIRECTORY_ENTRY_REJECTED");
            string[] files = Directory.GetFiles(root, "*", SearchOption.TopDirectoryOnly);
            Array.Sort(files, StringComparer.Ordinal);
            foreach (string path in files)
            {
                string name = Path.GetFileName(path);
                if (name.Length != 64 + ".interaction.json".Length || !name.EndsWith(".interaction.json", StringComparison.Ordinal)) throw new InvalidDataException("INTERACTION_MAPPING_FILENAME");
                string interaction = name.Substring(0, 64);
                if (!R7Hash.IsLowerSha256(interaction)) throw new InvalidDataException("INTERACTION_MAPPING_FILENAME");
                using (R7VerifiedFile file = R7SafeFile.Open(path, path, root, null, expectedOwnerSid, null, expectedVolumeIdentity))
                {
                    SortedDictionary<string, object> mapping = R7Json.ParseCanonicalObject(file.Bytes);
                    R7Json.ExactKeys(mapping, "capture_identity", "interaction_identity", "request_frame_sha256", "schema_version");
                    if (!String.Equals(R7Json.String(mapping, "interaction_identity", 64, 64), interaction, StringComparison.Ordinal)) throw new InvalidDataException("INTERACTION_MAPPING_MISMATCH");
                    string capture = R7Json.String(mapping, "capture_identity", 64, 64);
                    string request = R7Json.String(mapping, "request_frame_sha256", 64, 64);
                    SortedDictionary<string, object> captureObject = objects.Get(capture);
                    if (!String.Equals(R7Json.String(captureObject, "interaction_identity", 64, 64), interaction, StringComparison.Ordinal)) throw new InvalidDataException("INTERACTION_CAPTURE_BINDING_MISMATCH");
                    Index(interaction, capture, request);
                }
            }
        }

        private void Index(string interaction, string capture, string request)
        {
            if (captureByInteraction.ContainsKey(interaction)) throw new InvalidDataException("DUPLICATE_INTERACTION_IDENTITY");
            captureByInteraction.Add(interaction, capture);
            List<string> values;
            if (!interactionsByRequestFrame.TryGetValue(request, out values)) { values = new List<string>(); interactionsByRequestFrame.Add(request, values); }
            values.Add(interaction);
        }
    }
}
