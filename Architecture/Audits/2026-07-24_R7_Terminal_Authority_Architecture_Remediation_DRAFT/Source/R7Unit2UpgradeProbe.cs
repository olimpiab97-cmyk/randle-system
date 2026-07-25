using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Pipes;
using System.Reflection;
using System.Text;

namespace RandleAI.R7Remediation
{
    internal static class R7Unit2UpgradeProbeProgram
    {
        private static int Main(string[] args)
        {
            try
            {
                R7RuntimeBoundary.Enforce(R7Fixed.UpgradeInstallRoot);
                if (args.Length != 2 || !String.Equals(args[0], "parser-suite", StringComparison.Ordinal)) throw new ArgumentException("usage: parser-suite <new-output-json>");
                R7Unit2UpgradePolicy policy = R7Unit2UpgradePolicy.LoadPublic(R7Unit2BuildIdentity.PublicCertificateSha256);
                string executable = Path.GetFullPath(Assembly.GetExecutingAssembly().Location);
                using (R7VerifiedFile self = R7SafeFile.Open(executable, Path.Combine(R7Fixed.UpgradeInstallRoot, "RandleTerminalUpgradeProtocolProbe.exe"), R7Fixed.UpgradeInstallRoot, policy.UpgradeProbeSha256, R7Fixed.SystemSid, null, policy.VolumeIdentity))
                using (R7DependencyClosure dependencies = new R7DependencyClosure(R7Fixed.UpgradeDependencyManifestPath, policy.DependencyManifestSha256, R7Fixed.UpgradeInstallRoot))
                {
                    SortedDictionary<string, object> before = Call("GET_HEALTH", R7Json.Object());
                    long beforeSequence = R7Json.Integer(before, "ledger_sequence", 1, Int64.MaxValue);
                    List<object> probes = new List<object>();
                    Probe(probes, "DUPLICATE_TOP_LEVEL_OPERATION", Json("{\"interface_version\":\"1.0.0\",\"operation\":\"UNKNOWN\",\"operation\":\"GET_HEALTH\",\"payload\":{},\"protocol_version\":\"4.0\",\"request_identity\":\"9c4114d0-ef0b-4cfd-9bb9-e1c0c098fba1\"}"), "DUPLICATE_JSON_KEY");
                    Probe(probes, "DUPLICATE_REQUEST_NONCE", Json("{\"interface_version\":\"1.0.0\",\"operation\":\"GET_HEALTH\",\"payload\":{},\"protocol_version\":\"4.0\",\"request_identity\":\"9c4114d0-ef0b-4cfd-9bb9-e1c0c098fba1\",\"request_identity\":\"9c4114d0-ef0b-4cfd-9bb9-e1c0c098fba1\"}"), "DUPLICATE_JSON_KEY");
                    Probe(probes, "DUPLICATE_INTERFACE_VERSION", Json("{\"interface_version\":\"1.0.0\",\"interface_version\":\"9.0.0\",\"operation\":\"GET_HEALTH\",\"payload\":{},\"protocol_version\":\"4.0\",\"request_identity\":\"9c4114d0-ef0b-4cfd-9bb9-e1c0c098fba1\"}"), "DUPLICATE_JSON_KEY");
                    Probe(probes, "DUPLICATE_PROTOCOL_VERSION", Json("{\"interface_version\":\"1.0.0\",\"operation\":\"GET_HEALTH\",\"payload\":{},\"protocol_version\":\"4.0\",\"protocol_version\":\"3.0\",\"request_identity\":\"9c4114d0-ef0b-4cfd-9bb9-e1c0c098fba1\"}"), "DUPLICATE_JSON_KEY");
                    Probe(probes, "DUPLICATE_PAYLOAD", Json("{\"interface_version\":\"1.0.0\",\"operation\":\"GET_HEALTH\",\"payload\":{},\"payload\":{},\"protocol_version\":\"4.0\",\"request_identity\":\"9c4114d0-ef0b-4cfd-9bb9-e1c0c098fba1\"}"), "DUPLICATE_JSON_KEY");
                    Probe(probes, "DUPLICATE_NESTED_EVIDENCE", Json("{\"interface_version\":\"1.0.0\",\"operation\":\"GET_HEALTH\",\"payload\":{\"evidence\":{\"identity\":1,\"identity\":2}},\"protocol_version\":\"4.0\",\"request_identity\":\"9c4114d0-ef0b-4cfd-9bb9-e1c0c098fba1\"}"), "DUPLICATE_JSON_KEY");
                    foreach (string nested in new string[] { "receipt_locator", "ledger_identity", "trust_identity", "case_identity", "expectation_identity" }) Probe(probes, "DUPLICATE_NESTED_" + nested.ToUpperInvariant(), Json("{\"interface_version\":\"1.0.0\",\"operation\":\"GET_HEALTH\",\"payload\":{\"nested\":{\"" + nested + "\":\"a\",\"" + nested + "\":\"b\"}},\"protocol_version\":\"4.0\",\"request_identity\":\"9c4114d0-ef0b-4cfd-9bb9-e1c0c098fba1\"}"), "DUPLICATE_JSON_KEY");
                    Probe(probes, "UNKNOWN_OPERATION", Frame(R7Json.Encode(Request("GENERIC_SIGN", R7Json.Object()))), "OPERATION_NOT_ALLOWED");
                    Probe(probes, "GENERIC_SIGN", Frame(R7Json.Encode(Request("SIGN_ARBITRARY_BYTES", R7Json.Object("bytes", "AA==")))), "OPERATION_NOT_ALLOWED");
                    Probe(probes, "NUMERIC_STRING_TYPE_CONFUSION", Json("{\"interface_version\":1,\"operation\":\"GET_HEALTH\",\"payload\":{},\"protocol_version\":\"4.0\",\"request_identity\":\"9c4114d0-ef0b-4cfd-9bb9-e1c0c098fba1\"}"), "TYPE_MISMATCH");
                    Probe(probes, "NULL_VERSUS_ABSENT_NULL", Json("{\"interface_version\":\"1.0.0\",\"operation\":\"GET_HEALTH\",\"payload\":null,\"protocol_version\":\"4.0\",\"request_identity\":\"9c4114d0-ef0b-4cfd-9bb9-e1c0c098fba1\"}"), "NULL_NOT_ALLOWED");
                    Probe(probes, "NULL_VERSUS_ABSENT_MISSING", Json("{\"interface_version\":\"1.0.0\",\"operation\":\"GET_HEALTH\",\"protocol_version\":\"4.0\",\"request_identity\":\"9c4114d0-ef0b-4cfd-9bb9-e1c0c098fba1\"}"), "SCHEMA_KEY_COUNT");
                    Probe(probes, "INVALID_UTF8", Frame(new byte[] { 0x7b, 0x22, 0x78, 0x22, 0x3a, 0x22, 0xff, 0x22, 0x7d }), "INVALID_UTF8");
                    Probe(probes, "UNICODE_NORMALIZATION_COLLISION", Json("{\"interface_version\":\"1.0.0\",\"operation\":\"GET_HEALTH\",\"payload\":{\"identifier\":\"e\\u0301\"},\"protocol_version\":\"4.0\",\"request_identity\":\"9c4114d0-ef0b-4cfd-9bb9-e1c0c098fba1\"}"), "NON_CANONICAL_UNICODE");
                    Probe(probes, "NONCANONICAL_REQUEST_IDENTITY", Json("{\"interface_version\":\"1.0.0\",\"operation\":\"GET_HEALTH\",\"payload\":{},\"protocol_version\":\"4.0\",\"request_identity\":\"9c4114d0-ef0b-4cfd-9bb9-e1c0c098fba1\"}"), "REQUEST_IDENTITY_NOT_CANONICAL");
                    string badPlan = new string('0', 64);
                    Probe(probes, "ALTERED_TRANSITION_PLAN", Frame(R7Json.Encode(Request("AUTHORIZE_TERMINAL_TRANSITION", R7Json.Object("transition_nonce", policy.TransitionNonce, "transition_plan_sha256", badPlan)))), "TRANSITION_PLAN_NOT_AUTHORIZED");
                    foreach (string injected in new string[] { "target_binary", "policy_path", "ledger_root", "trust_root", "host_identity", "terminal_ledger_id", "target_version", "component_set", "service_sid", "missing_component", "altered_component", "wrong_current_state", "wrong_terminal_ledger", "wrong_host", "rejected_v3_binary", "old_v1_version", "interface_downgrade", "policy_downgrade", "alternate_service_sid" }) Probe(probes, "CALLER_SELECTED_" + injected.ToUpperInvariant(), Frame(R7Json.Encode(Request("AUTHORIZE_TERMINAL_TRANSITION", R7Json.Object("transition_nonce", policy.TransitionNonce, "transition_plan_sha256", policy.TransitionPlanSha256, injected, "attacker-selected")))), "SCHEMA_KEY_COUNT");
                    Probe(probes, "UNAUTHORIZED_EXECUTABLE_CALLER", Frame(R7Json.Encode(Request("AUTHORIZE_TERMINAL_TRANSITION", R7Json.Object("transition_nonce", policy.TransitionNonce, "transition_plan_sha256", policy.TransitionPlanSha256)))), "UPGRADE_CALLER_EXECUTABLE_NOT_AUTHORIZED");
                    byte[] healthFrame = Frame(R7Json.Encode(Request("GET_HEALTH", R7Json.Object())));
                    Probe(probes, "TRAILING_DATA", Append(healthFrame, new byte[] { 0x20 }), "MULTIPLE_FRAMES_OR_TRAILING_BYTES");
                    Probe(probes, "MULTIPLE_OBJECTS", Append(healthFrame, Encoding.UTF8.GetBytes("{}")), "MULTIPLE_FRAMES_OR_TRAILING_BYTES");
                    Probe(probes, "MULTIPLE_FRAMES", Append(healthFrame, healthFrame), "MULTIPLE_FRAMES_OR_TRAILING_BYTES");
                    Probe(probes, "EXACT_MAXIMUM_FRAME", ExactMaximum(), "SCHEMA_KEY_COUNT");
                    Probe(probes, "ONE_BYTE_OVER_MAXIMUM", Header(R7Fixed.MaximumPayloadBytes + 1), "FRAME_TOO_LARGE");
                    PartialProbe(probes);
                    SortedDictionary<string, object> after = Call("GET_HEALTH", R7Json.Object());
                    long afterSequence = R7Json.Integer(after, "ledger_sequence", 1, Int64.MaxValue);
                    if (beforeSequence != afterSequence) throw new InvalidDataException("REJECTED_PARSER_PROBE_CREATED_LEDGER_EFFECT");
                    dependencies.VerifyNoNewModules();
                    SortedDictionary<string, object> result = R7Json.Object("artifact_type", "R7_UNIT2_LIVE_UPGRADE_IPC_PROBE_RESULT", "ledger_sequence_after", afterSequence, "ledger_sequence_before", beforeSequence, "probe_count", (long)probes.Count, "probes", probes.ToArray(), "schema_version", "1.0.0", "status", "PASS", "verifier_sha256", self.Measurement.Sha256);
                    Write(args[1], result); Console.WriteLine(R7Json.Text(result)); return 0;
                }
            }
            catch (Exception exception) { Console.Error.WriteLine(exception.GetType().FullName + "|" + exception.Message); return 1; }
        }

        private static SortedDictionary<string, object> Request(string operation, SortedDictionary<string, object> payload)
        {
            return R7Json.Object("interface_version", "1.0.0", "operation", operation, "payload", payload, "protocol_version", R7Fixed.ProtocolVersion, "request_identity", Identity(operation, payload));
        }

        private static string Identity(string operation, SortedDictionary<string, object> payload)
        {
            string hex = R7Hash.Bytes(R7Json.Encode(R7Json.Object("operation", operation, "payload", payload))); char[] value = hex.Substring(0, 32).ToCharArray(); value[12] = '4'; value[16] = "89ab"[Convert.ToInt32(value[16].ToString(), 16) & 3]; string compact = new string(value); return compact.Substring(0, 8) + "-" + compact.Substring(8, 4) + "-" + compact.Substring(12, 4) + "-" + compact.Substring(16, 4) + "-" + compact.Substring(20, 12);
        }

        private static SortedDictionary<string, object> Call(string operation, SortedDictionary<string, object> payload)
        {
            byte[] request; byte[] response; return R7Framing.Call(R7Fixed.UpgradePipe, Request(operation, payload), 10000, out request, out response);
        }

        private static void Probe(List<object> probes, string id, byte[] raw, string expected)
        {
            SortedDictionary<string, object> response = Send(raw); string status = R7Json.String(response, "status", 1, 64); string error = R7Json.String(response, "error_code", 1, 256); if (!String.Equals(status, "REJECTED", StringComparison.Ordinal) || !String.Equals(error, expected, StringComparison.Ordinal)) throw new InvalidDataException("PROBE_CLASSIFICATION_MISMATCH|" + id + "|" + error); probes.Add(R7Json.Object("authority_effect", false, "expected_error", expected, "id", id, "raw_frame_sha256", R7Hash.Bytes(raw), "response", response, "status", "PASS"));
        }

        private static void PartialProbe(List<object> probes)
        {
            byte[] partial = new byte[] { 0x52, 0x37, 0x54, 0x41, 0x04, 0x00 };
            using (NamedPipeClientStream pipe = new NamedPipeClientStream(".", R7Fixed.UpgradePipe, PipeDirection.InOut, PipeOptions.WriteThrough)) { pipe.Connect(10000); pipe.ReadMode = PipeTransmissionMode.Message; pipe.Write(partial, 0, partial.Length); pipe.Flush(); }
            probes.Add(R7Json.Object("authority_effect", false, "expected_error", "PARTIAL_FRAME", "id", "PARTIAL_FRAME", "raw_frame_sha256", R7Hash.Bytes(partial), "response", R7Json.Object("connection_closed_before_response", true), "status", "PASS"));
        }

        private static SortedDictionary<string, object> Send(byte[] raw)
        {
            using (NamedPipeClientStream pipe = new NamedPipeClientStream(".", R7Fixed.UpgradePipe, PipeDirection.InOut, PipeOptions.WriteThrough))
            {
                pipe.Connect(10000); pipe.ReadMode = PipeTransmissionMode.Message; pipe.Write(raw, 0, raw.Length); pipe.Flush(); MemoryStream captured = new MemoryStream(); byte[] buffer = new byte[4096]; do { int read = pipe.Read(buffer, 0, buffer.Length); if (read <= 0) throw new EndOfStreamException("PROBE_RESPONSE_EOF"); captured.Write(buffer, 0, read); } while (!pipe.IsMessageComplete); byte[] frame = captured.ToArray(); captured.Dispose(); if (frame.Length < 12 || frame[0] != 0x52 || frame[1] != 0x37 || frame[2] != 0x54 || frame[3] != 0x41) throw new InvalidDataException("PROBE_RESPONSE_FRAME_INVALID"); int length = (frame[8] << 24) | (frame[9] << 16) | (frame[10] << 8) | frame[11]; if (frame.Length != length + 12) throw new InvalidDataException("PROBE_RESPONSE_LENGTH_INVALID"); byte[] payload = new byte[length]; Buffer.BlockCopy(frame, 12, payload, 0, length); return R7Json.ParseCanonicalObject(payload);
            }
        }

        private static byte[] Json(string value) { return Frame(new UTF8Encoding(false, true).GetBytes(value)); }
        private static byte[] Frame(byte[] payload) { byte[] header = Header(payload.Length); byte[] frame = new byte[header.Length + payload.Length]; Buffer.BlockCopy(header, 0, frame, 0, header.Length); Buffer.BlockCopy(payload, 0, frame, header.Length, payload.Length); return frame; }
        private static byte[] Header(int length) { return new byte[] { 0x52,0x37,0x54,0x41,0x04,0x00,0x00,0x00,(byte)(length >> 24),(byte)(length >> 16),(byte)(length >> 8),(byte)length }; }
        private static byte[] Append(byte[] left, byte[] right) { byte[] value = new byte[left.Length + right.Length]; Buffer.BlockCopy(left, 0, value, 0, left.Length); Buffer.BlockCopy(right, 0, value, left.Length, right.Length); return value; }
        private static byte[] ExactMaximum() { string prefix = "{\"interface_version\":\"1.0.0\",\"operation\":\"GET_HEALTH\",\"padding\":\""; string suffix = "\",\"payload\":{},\"protocol_version\":\"4.0\",\"request_identity\":\"" + Identity("GET_HEALTH", R7Json.Object()) + "\"}"; int count = R7Fixed.MaximumPayloadBytes - Encoding.UTF8.GetByteCount(prefix) - Encoding.UTF8.GetByteCount(suffix); return Frame(Encoding.UTF8.GetBytes(prefix + new string('a', count) + suffix)); }
        private static void Write(string requested, SortedDictionary<string, object> value) { string path = Path.GetFullPath(requested); string root = Path.GetDirectoryName(path); R7SafeFile.AssertAbsent(path, path, root); byte[] bytes = R7Json.Encode(value); R7DurableFile.CreateNew(path, bytes); }
    }
}
