using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.IO.Pipes;
using System.Reflection;
using System.Security;
using System.Threading;

namespace RandleAI.R7Remediation
{
    internal static class R7AdversarialHarnessProgram
    {
        private static int Main(string[] args)
        {
            try
            {
                R7RuntimeBoundary.Enforce(R7Fixed.TerminalInstallRoot);
                R7ActiveUpgrade activeUpgrade = R7ActiveUpgrade.ResolveAuthorization("ADVERSARIAL_HARNESS");
                R7TerminalPolicy terminalPolicy = R7TerminalPolicy.Load(activeUpgrade.TerminalPolicySha256);
                R7ComponentIdentity component = terminalPolicy.Component("ADVERSARIAL_HARNESS");
                string executable = Path.GetFullPath(Assembly.GetExecutingAssembly().Location);
                using (R7VerifiedFile binary = R7SafeFile.Open(executable, component.Path, R7Fixed.TerminalInstallRoot, component.Sha256, R7Fixed.SystemSid, null, terminalPolicy.VolumeIdentity))
                using (R7DependencyClosure dependencies = new R7DependencyClosure(R7Fixed.DependencyManifestPath, terminalPolicy.DependencyManifestSha256, R7Fixed.TerminalInstallRoot))
                {
                    activeUpgrade.RequireActivatedComponent("ADVERSARIAL_HARNESS", binary.Measurement.FileIdentity);
                    dependencies.VerifyNoNewModules();
                    SortedDictionary<string, object> result;
                    if (args.Length == 5 && args[0] == "call") result = Call(args[1], args[2], args[3]);
                    else if (args.Length == 6 && args[0] == "call-id") result = Call(args[1], args[2], args[3], args[4]);
                    else if (args.Length == 4 && args[0] == "execute-outer-case") result = ExecuteOuterCase(args[1], args[2]);
                    else if (args.Length == 9 && args[0] == "submit-run") result = SubmitRun(args);
                    else if (args.Length == 5 && args[0] == "reconcile") result = Reconcile(args[1], args[2], args[3]);
                    else if (args.Length == 2 && args[0] == "service-unavailable") result = ServiceUnavailable();
                    else throw new ArgumentException("usage: call <pipe-role> <operation> <payload-json> <output> | call-id <pipe-role> <operation> <payload-json> <request-id> <output> | execute-outer-case <case-id> <fixture-json> <output> | submit-run <kind> <checkout> <provenance> <autocrlf> <length> <graphs-json> <request-id> <output> | reconcile <candidate> <fresh> <provenance> <output> | service-unavailable <output>");
                    WriteResult(args[args.Length - 1], result);
                    dependencies.VerifyNoNewModules();
                    return 0;
                }
            }
            catch (Exception exception)
            {
                Console.Error.WriteLine(exception.GetType().FullName + "|" + exception.Message);
                return 1;
            }
        }

        private static SortedDictionary<string, object> Call(string role, string operation, string payloadPath)
        {
            return Call(role, operation, payloadPath, Guid.NewGuid().ToString("D"));
        }

        private static SortedDictionary<string, object> Call(string role, string operation, string payloadPath, string requestIdentity)
        {
            string pipe;
            string interfaceVersion;
            if (role == "terminal") { pipe = R7Fixed.TerminalPipe; interfaceVersion = R7Fixed.InterfaceVersion; }
            else if (role == "execution") { pipe = R7Fixed.ExecutionPipe; interfaceVersion = "1.0.0"; }
            else if (role == "observation") { pipe = R7Fixed.ObservationPipe; interfaceVersion = "1.0.0"; }
            else if (role == "comparator") { pipe = R7Fixed.ComparatorPipe; interfaceVersion = "1.0.0"; }
            else if (role == "upgrade") { pipe = R7Fixed.UpgradePipe; interfaceVersion = "1.0.0"; }
            else throw new ArgumentException("unknown pipe role");
            SortedDictionary<string, object> payload = ReadObject(payloadPath);
            SortedDictionary<string, object> request = R7Json.Object("interface_version", interfaceVersion, "operation", operation, "payload", payload, "protocol_version", R7Fixed.ProtocolVersion, "request_identity", CanonicalGuid(requestIdentity));
            return Invoke(pipe, request);
        }

        private static SortedDictionary<string, object> ExecuteOuterCase(string caseId, string fixturePath)
        {
            SortedDictionary<string, object> build = Invoke(R7Fixed.ExecutionPipe, R7RoleClient.RoleRequest("BUILD_CASE_INVOCATION", R7Json.Object("case_id", caseId, "fixture", ReadObject(fixturePath))));
            SortedDictionary<string, object> plan = Response(build);
            RequireComplete(plan, "CASE_OUTER_INVOCATION_PLAN_BUILT");
            if (R7Json.Boolean(plan, "expectation_artifact_read")) throw new SecurityException("REQUEST_BUILDER_READ_EXPECTATION");
            if (!String.Equals(R7Json.String(plan, "request_builder_sid", 1, 256), R7Fixed.ExecutionSid, StringComparison.Ordinal)) throw new SecurityException("REQUEST_BUILDER_SID_MISMATCH");
            string planKind = R7Json.String(plan, "plan_kind", 1, 128);
            SortedDictionary<string, object> outer;
            if (planKind == "PUBLIC_VERIFIER_PROCESS") outer = InvokePublicVerifier(caseId, plan);
            else if (planKind == "CONCURRENT_OUTER_INTERFACE") outer = InvokeConcurrent(plan);
            else outer = InvokeRawFrame(R7Json.String(plan, "target_pipe", 1, 256), DecodeFrame(plan, "request_frame"), R7Json.Boolean(plan, "expect_response"));

            if (planKind == "UPGRADE_NEEDS_EXTERNAL_WRAPPER" || planKind == "SELF_UPGRADE_NEEDS_EXTERNAL_WRAPPER")
            {
                string externalRequest;
                string externalResponse;
                string upgradeRequestIdentity;
                if (planKind == "UPGRADE_NEEDS_EXTERNAL_WRAPPER")
                {
                    externalRequest = R7Json.String(outer, "request_frame", 1, R7Fixed.MaximumEncodedCaptureChars);
                    externalResponse = R7Json.String(outer, "response_frame", 1, R7Fixed.MaximumEncodedFrameChars);
                    upgradeRequestIdentity = R7Json.String(R7Framing.Decode(Convert.FromBase64String(externalRequest)), "request_identity", 36, 36);
                }
                else
                {
                    SortedDictionary<string, object> probe = Response(outer);
                    RequireComplete(probe, "SELF_UPGRADE_PROBE_CAPTURED");
                    externalRequest = R7Json.String(probe, "external_request_frame", 1, R7Fixed.MaximumEncodedFrameChars);
                    externalResponse = R7Json.String(probe, "external_response_frame", 1, R7Fixed.MaximumEncodedFrameChars);
                    upgradeRequestIdentity = R7Json.String(probe, "upgrade_request_identity", 36, 36);
                }
                SortedDictionary<string, object> wrapperBuild = Invoke(R7Fixed.ExecutionPipe, R7RoleClient.RoleRequest("BUILD_EXTERNAL_INTERACTION", R7Json.Object(
                    "case_id", caseId,
                    "external_request_frame", externalRequest,
                    "external_response_frame", externalResponse,
                    "upgrade_request_identity", upgradeRequestIdentity)));
                SortedDictionary<string, object> wrapperPlan = Response(wrapperBuild);
                RequireComplete(wrapperPlan, "EXTERNAL_INTERACTION_PLAN_BUILT");
                outer = InvokeRawFrame(R7Json.String(wrapperPlan, "target_pipe", 1, 256), DecodeFrame(wrapperPlan, "request_frame"), true);
                planKind = "DIRECT_OUTER_INTERFACE";
            }

            string baseInteraction;
            if (planKind == "ROLE_PROBE" || planKind == "PRINCIPAL_PROBE" || planKind == "RECOVERY_PROBE")
            {
                SortedDictionary<string, object> roleResponse = Response(outer);
                RequireCompleteStatus(roleResponse);
                baseInteraction = ResolveSubmission(R7Json.String(roleResponse, "submission_request_frame_sha256", 64, 64),
                    planKind == "ROLE_PROBE" && R7Json.String(plan, "target_pipe", 1, 256) == R7Fixed.ObservationPipe ? "OBSERVATION" :
                    planKind == "ROLE_PROBE" && R7Json.String(plan, "target_pipe", 1, 256) == R7Fixed.ComparatorPipe ? "COMPARATOR" : "EXECUTION");
            }
            else baseInteraction = ResolveOperatorInteraction(R7Json.String(outer, "request_frame_sha256", 64, 64));

            SortedDictionary<string, object> summary = TerminalResponse("GET_INTERACTION_EVIDENCE", R7Json.Object("interaction_identity", baseInteraction));
            SortedDictionary<string, object> raw = TerminalResponse("GET_INTERACTION_RAW_EVIDENCE", R7Json.Object("interaction_identity", baseInteraction));
            RequireComplete(raw, "RAW_INTERACTION_EVIDENCE_RESOLVED");
            RequireComplete(summary, "INTERACTION_EVIDENCE_RESOLVED");

            SortedDictionary<string, object> eventOuter = Invoke(R7Fixed.ExecutionPipe, R7RoleClient.RoleRequest("PRODUCE_EVENT_EVIDENCE", R7Json.Object(
                "base_interaction_identity", baseInteraction,
                "case_id", caseId,
                "request_frame", R7Json.String(raw, "request_frame", 1, R7Fixed.MaximumEncodedCaptureChars),
                "response_frame", R7Json.String(raw, "response_frame", 1, R7Fixed.MaximumEncodedFrameChars))));
            SortedDictionary<string, object> eventResponse = Response(eventOuter);
            RequireComplete(eventResponse, "EVENT_EVIDENCE_SUBMITTED");
            string eventInteraction = ResolveSubmission(R7Json.String(eventResponse, "submission_request_frame_sha256", 64, 64), "EXECUTION");

            SortedDictionary<string, object> observationOuter = Invoke(R7Fixed.ObservationPipe, R7RoleClient.RoleRequest("OBSERVE_RAW", R7Json.Object(
                "base_interaction_identity", baseInteraction,
                "case_id", caseId,
                "ledger_sequence_after", R7Json.Integer(summary, "ledger_sequence_after", 0, Int64.MaxValue),
                "ledger_sequence_before", R7Json.Integer(summary, "ledger_sequence_before", 0, Int64.MaxValue),
                "request_frame", R7Json.String(raw, "request_frame", 1, R7Fixed.MaximumEncodedCaptureChars),
                "response_frame", R7Json.String(raw, "response_frame", 1, R7Fixed.MaximumEncodedFrameChars))));
            SortedDictionary<string, object> observationResponse = Response(observationOuter);
            RequireComplete(observationResponse, "OBSERVATION_PRODUCED_FROM_RAW_CURRENT_RUN_EVIDENCE");
            if (R7Json.Boolean(observationResponse, "expectation_artifact_read")) throw new SecurityException("OBSERVATION_READ_EXPECTATION");
            string observationInteraction = ResolveSubmission(R7Json.String(observationResponse, "submission_request_frame_sha256", 64, 64), "OBSERVATION");

            SortedDictionary<string, object> comparatorOuter = Invoke(R7Fixed.ComparatorPipe, R7RoleClient.RoleRequest("COMPARE_RAW", R7Json.Object(
                "base_interaction_identity", baseInteraction,
                "case_id", caseId,
                "event_interaction_identity", eventInteraction,
                "observation_interaction_identity", observationInteraction,
                "response_frame", R7Json.String(raw, "response_frame", 1, R7Fixed.MaximumEncodedFrameChars))));
            SortedDictionary<string, object> comparatorResponse = Response(comparatorOuter);
            RequireComplete(comparatorResponse, "COMPARISON_PRODUCED_FROM_INDEPENDENT_EXPECTATION_AND_RAW_EVIDENCE");
            string comparatorInteraction = ResolveSubmission(R7Json.String(comparatorResponse, "submission_request_frame_sha256", 64, 64), "COMPARATOR");

            SortedDictionary<string, object> result = R7PipeWindowsService.Success("CASE_EXECUTED_THROUGH_HOSTILE_OUTER_INTERFACE");
            result.Add("actual_code", R7Json.String(summary, "actual_code", 1, 256));
            result.Add("actual_status", R7Json.String(summary, "actual_status", 1, 64));
            result.Add("case_graph", R7Json.Object(
                "base_interaction_identity", baseInteraction,
                "case_id", caseId,
                "comparator_interaction_identity", comparatorInteraction,
                "event_interaction_identity", eventInteraction,
                "observation_interaction_identity", observationInteraction));
            result.Add("event_producer_expectation_artifact_read", false);
            result.Add("outer_interface_surface", planKind == "PUBLIC_VERIFIER_PROCESS" ? R7Json.String(plan, "target_surface", 1, 256) : R7Json.String(plan, "target_pipe", 1, 256));
            result.Add("request_builder_expectation_artifact_read", false);
            return result;
        }

        private static SortedDictionary<string, object> InvokePublicVerifier(string caseId, SortedDictionary<string, object> plan)
        {
            R7Json.ExactKeys(plan, "case_id", "expect_response", "expectation_artifact_read", "plan_kind", "public_verifier_operation", "public_verifier_payload", "request_builder_sid", "result_code", "status", "target_surface");
            string operation = R7Json.String(plan, "public_verifier_operation", 1, 128);
            SortedDictionary<string, object> payload = R7Json.Child(plan, "public_verifier_payload");
            string probeRoot = Path.Combine(R7Fixed.PublicVerifierProbeRoot, caseId + "." + Guid.NewGuid().ToString("N"));
            if (Directory.Exists(probeRoot) || File.Exists(probeRoot)) throw new IOException("PUBLIC_VERIFIER_PROBE_ROOT_COLLISION");
            R7SafeFile.MeasureDirectory(R7Fixed.PublicVerifierProbeRoot, R7Fixed.PublicVerifierProbeRoot, null, null, null);
            Directory.CreateDirectory(probeRoot);
            R7SafeFile.MeasureDirectory(probeRoot, probeRoot, null, null, null);
            string publicOutput = Path.Combine(probeRoot, "public-result.json");
            string interactionOutput = Path.Combine(probeRoot, "outer-interaction.json");
            string payloadText = Convert.ToBase64String(R7Json.Encode(payload));
            R7ActiveUpgrade activeUpgrade = R7ActiveUpgrade.ResolveAuthorization("PUBLIC_VERIFIER");
            R7TerminalPolicy terminalPolicy = R7TerminalPolicy.Load(activeUpgrade.TerminalPolicySha256);
            R7ComponentIdentity component = terminalPolicy.Component("PUBLIC_VERIFIER");
            using (R7VerifiedFile binary = R7SafeFile.Open(component.Path, component.Path, R7Fixed.TerminalInstallRoot, component.Sha256, R7Fixed.SystemSid, null, terminalPolicy.VolumeIdentity))
            {
                activeUpgrade.RequireActivatedComponent("PUBLIC_VERIFIER", binary.Measurement.FileIdentity);
                ProcessStartInfo start = new ProcessStartInfo();
                start.FileName = component.Path;
                start.Arguments = "probe " + QuoteArgument(caseId) + " " + QuoteArgument(operation) + " " + QuoteArgument(payloadText) + " " + QuoteArgument(publicOutput) + " " + QuoteArgument(interactionOutput);
                start.CreateNoWindow = true;
                start.UseShellExecute = false;
                start.RedirectStandardOutput = true;
                start.RedirectStandardError = true;
                using (Process process = Process.Start(start))
                {
                    string standardOutput = process.StandardOutput.ReadToEnd();
                    string standardError = process.StandardError.ReadToEnd();
                    if (!process.WaitForExit(180000)) { try { process.Kill(); } catch { } throw new IOException("PUBLIC_VERIFIER_PROCESS_TIMEOUT"); }
                    if (process.ExitCode != 0) throw new IOException("PUBLIC_VERIFIER_PROCESS_FAILED:" + process.ExitCode.ToString(CultureInfo.InvariantCulture) + ":" + standardError + ":" + standardOutput);
                    if (standardOutput.IndexOf("PUBLIC_VERIFIER_OUTER_CASE_COMPLETED|" + caseId + "|", StringComparison.Ordinal) < 0 || standardError.Length != 0) throw new IOException("PUBLIC_VERIFIER_PROCESS_OUTPUT_INVALID");
                }
            }
            byte[] interactionBytes;
            using (R7VerifiedFile interaction = R7SafeFile.Open(interactionOutput, interactionOutput, R7Fixed.PublicVerifierProbeRoot, null, null, null, terminalPolicy.VolumeIdentity)) interactionBytes = interaction.Bytes;
            SortedDictionary<string, object> result = R7Json.Parse(interactionBytes) as SortedDictionary<string, object>;
            if (result == null) throw new InvalidDataException("PUBLIC_VERIFIER_INTERACTION_OBJECT_REQUIRED");
            return result;
        }

        private static string QuoteArgument(string value)
        {
            if (value == null) throw new ArgumentNullException("value");
            if (value.IndexOf('\0') >= 0 || value.IndexOf('\r') >= 0 || value.IndexOf('\n') >= 0 || value.IndexOf('\"') >= 0 || value.EndsWith("\\", StringComparison.Ordinal)) throw new ArgumentException("INVALID_PROCESS_ARGUMENT");
            return "\"" + value + "\"";
        }

        private static SortedDictionary<string, object> InvokeConcurrent(SortedDictionary<string, object> plan)
        {
            byte[] firstFrame = DecodeFrame(plan, "first_request_frame");
            byte[] secondFrame = DecodeFrame(plan, "second_request_frame");
            byte[][] responses = new byte[2][];
            Exception[] errors = new Exception[2];
            NamedPipeClientStream firstPipe = new NamedPipeClientStream(".", R7Fixed.TerminalPipe, PipeDirection.InOut, PipeOptions.WriteThrough);
            NamedPipeClientStream secondPipe = new NamedPipeClientStream(".", R7Fixed.TerminalPipe, PipeDirection.InOut, PipeOptions.WriteThrough);
            try
            {
                firstPipe.Connect(30000);
                firstPipe.ReadMode = PipeTransmissionMode.Message;
                secondPipe.Connect(30000);
                secondPipe.ReadMode = PipeTransmissionMode.Message;
                ManualResetEvent start = new ManualResetEvent(false);
                Thread first = new Thread(delegate()
                {
                    try { start.WaitOne(); firstPipe.Write(firstFrame, 0, firstFrame.Length); firstPipe.Flush(); SortedDictionary<string, object> ignored = R7Framing.ReadClientResponse(firstPipe, out responses[0]); }
                    catch (Exception exception) { errors[0] = exception; }
                });
                Thread second = new Thread(delegate()
                {
                    try { start.WaitOne(); secondPipe.Write(secondFrame, 0, secondFrame.Length); secondPipe.Flush(); SortedDictionary<string, object> ignored = R7Framing.ReadClientResponse(secondPipe, out responses[1]); }
                    catch (Exception exception) { errors[1] = exception; }
                });
                first.IsBackground = true;
                second.IsBackground = true;
                first.Start();
                second.Start();
                start.Set();
                first.Join(30000);
                second.Join(30000);
                start.Dispose();
                if (first.IsAlive || second.IsAlive) throw new IOException("CONCURRENT_REQUEST_TIMEOUT");
                if (errors[0] != null) throw new IOException("FIRST_CONCURRENT_REQUEST_FAILED", errors[0]);
                if (errors[1] != null) throw new IOException("SECOND_CONCURRENT_REQUEST_FAILED", errors[1]);
            }
            finally
            {
                firstPipe.Dispose();
                secondPipe.Dispose();
            }
            SortedDictionary<string, object> verification = InvokeRawFrame(R7Fixed.TerminalPipe, DecodeFrame(plan, "request_frame"), true);
            verification.Add("first_response_frame_sha256", R7Hash.Bytes(responses[0]));
            verification.Add("second_response_frame_sha256", R7Hash.Bytes(responses[1]));
            return verification;
        }

        private static string ResolveOperatorInteraction(string requestFrameSha256)
        {
            SortedDictionary<string, object> response = TerminalResponse("RESOLVE_INTERACTION", R7Json.Object("request_frame_sha256", requestFrameSha256));
            RequireComplete(response, "INTERACTION_RESOLVED");
            return R7Json.String(response, "interaction_identity", 64, 64);
        }

        private static string ResolveSubmission(string requestFrameSha256, string role)
        {
            SortedDictionary<string, object> response = TerminalResponse("RESOLVE_EVIDENCE_SUBMISSION", R7Json.Object("request_frame_sha256", requestFrameSha256, "service_role", role));
            RequireComplete(response, "EVIDENCE_SUBMISSION_RESOLVED");
            return R7Json.String(response, "interaction_identity", 64, 64);
        }

        private static SortedDictionary<string, object> TerminalResponse(string operation, SortedDictionary<string, object> payload)
        {
            return Response(Invoke(R7Fixed.TerminalPipe, R7RoleClient.Request(operation, payload)));
        }

        private static SortedDictionary<string, object> Response(SortedDictionary<string, object> invocation)
        {
            return R7Json.Child(invocation, "response");
        }

        private static void RequireComplete(SortedDictionary<string, object> response, string code)
        {
            if (!String.Equals(R7Json.String(response, "status", 1, 64), "COMPLETE", StringComparison.Ordinal) || !String.Equals(R7Json.String(response, "result_code", 1, 256), code, StringComparison.Ordinal)) throw new R7ProtocolException("OUTER_STAGE_RESPONSE_INVALID", code);
        }

        private static void RequireCompleteStatus(SortedDictionary<string, object> response)
        {
            if (!String.Equals(R7Json.String(response, "status", 1, 64), "COMPLETE", StringComparison.Ordinal)) throw new R7ProtocolException("ROLE_OUTER_RESPONSE_INVALID");
        }

        private static byte[] DecodeFrame(SortedDictionary<string, object> value, string key)
        {
            try { return Convert.FromBase64String(R7Json.String(value, key, 1, R7Fixed.MaximumEncodedCaptureChars)); }
            catch (FormatException) { throw new R7ProtocolException("FRAME_ENCODING_INVALID", key); }
        }

        private static SortedDictionary<string, object> SubmitRun(string[] args)
        {
            string requestIdentity = CanonicalGuid(args[7]);
            object[] graphs = ReadArray(args[6]);
            SortedDictionary<string, object> request = R7Json.Object(
                "interface_version", R7Fixed.InterfaceVersion,
                "operation", "SUBMIT_RUN_GRAPH",
                "payload", R7Json.Object(
                    "case_graphs", graphs,
                    "checkout_identity", Sha(args[2]),
                    "configuration", R7Json.Object("autocrlf", args[4], "checkout_length", args[5]),
                    "provenance_identity", Sha(args[3]),
                    "run_kind", args[1]),
                "protocol_version", R7Fixed.ProtocolVersion,
                "request_identity", requestIdentity);
            return Invoke(R7Fixed.TerminalPipe, request);
        }

        private static SortedDictionary<string, object> Reconcile(string candidate, string fresh, string provenance)
        {
            SortedDictionary<string, object> request = R7RoleClient.Request("SUBMIT_RECONCILIATION", R7Json.Object(
                "candidate_receipt_identity", Sha(candidate),
                "fresh_receipt_identity", Sha(fresh),
                "reconciliation_provenance_identity", Sha(provenance)));
            return Invoke(R7Fixed.TerminalPipe, request);
        }

        private static SortedDictionary<string, object> ServiceUnavailable()
        {
            byte[] request = R7Framing.Encode(R7RoleClient.Request("GET_HEALTH", R7Json.Object()));
            string outcome = "UNEXPECTED_CONNECTION";
            int error = 0;
            try
            {
                using (NamedPipeClientStream pipe = new NamedPipeClientStream(".", R7Fixed.TerminalPipe, PipeDirection.InOut, PipeOptions.WriteThrough)) pipe.Connect(3000);
            }
            catch (Exception exception)
            {
                outcome = "SERVICE_UNAVAILABLE";
                error = exception.HResult;
            }
            return R7Json.Object(
                "artifact_type", "R7_HOSTILE_CLIENT_SERVICE_UNAVAILABLE_OBSERVATION",
                "error_code", error.ToString("x8", CultureInfo.InvariantCulture),
                "observation_time", DateTimeOffset.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture),
                "outcome", outcome,
                "request_frame", Convert.ToBase64String(request),
                "request_frame_sha256", R7Hash.Bytes(request),
                "schema_version", "1.0.0");
        }

        private static SortedDictionary<string, object> Invoke(string pipeName, SortedDictionary<string, object> request)
        {
            return InvokeRawFrame(pipeName, R7Framing.Encode(request), true);
        }

        private static SortedDictionary<string, object> InvokeRawFrame(string pipeName, byte[] sent, bool expectResponse)
        {
            byte[] received = new byte[0];
            SortedDictionary<string, object> response = R7PipeWindowsService.Rejection("UNDELIVERED");
            using (NamedPipeClientStream pipe = new NamedPipeClientStream(".", pipeName, PipeDirection.InOut, PipeOptions.WriteThrough))
            {
                pipe.Connect(30000);
                pipe.ReadMode = PipeTransmissionMode.Message;
                pipe.Write(sent, 0, sent.Length);
                pipe.Flush();
                if (expectResponse)
                {
                    try { response = R7Framing.ReadClientResponse(pipe, out received); }
                    catch (IOException) { }
                }
            }
            if (!expectResponse) Thread.Sleep(150);
            return R7Json.Object(
                "artifact_type", "R7_HOSTILE_OUTER_INTERFACE_INVOCATION",
                "pipe_name", pipeName,
                "request_frame", Convert.ToBase64String(sent),
                "request_frame_sha256", R7Hash.Bytes(sent),
                "response", response,
                "response_frame", Convert.ToBase64String(received),
                "response_frame_sha256", R7Hash.Bytes(received),
                "schema_version", "1.0.0");
        }

        private static SortedDictionary<string, object> ReadObject(string path)
        {
            string full = Path.GetFullPath(path);
            object value;
            using (R7VerifiedFile file = R7SafeFile.OpenMeasured(full, full, Path.GetDirectoryName(full))) value = R7Json.ParseCanonical(file.Bytes);
            SortedDictionary<string, object> result = value as SortedDictionary<string, object>;
            if (result == null) throw new InvalidDataException("object fixture required");
            return result;
        }

        private static object[] ReadArray(string path)
        {
            string full = Path.GetFullPath(path);
            object value;
            using (R7VerifiedFile file = R7SafeFile.OpenMeasured(full, full, Path.GetDirectoryName(full))) value = R7Json.ParseCanonical(file.Bytes);
            object[] result = value as object[];
            if (result == null) throw new InvalidDataException("array fixture required");
            return result;
        }

        private static string Sha(string value) { if (!R7Hash.IsLowerSha256(value)) throw new ArgumentException("lowercase SHA-256 required"); return value; }
        private static string CanonicalGuid(string value) { Guid parsed; if (!Guid.TryParseExact(value, "D", out parsed) || parsed.ToString("D") != value) throw new ArgumentException("canonical request id required"); return value; }

        private static void WriteResult(string path, SortedDictionary<string, object> result)
        {
            string full = Path.GetFullPath(path);
            string parent = Path.GetDirectoryName(full);
            R7SafeFile.MeasureDirectory(parent, parent, null, null, null);
            R7SafeFile.AssertAbsent(full, full, parent);
            byte[] bytes = R7Json.Encode(result);
            R7DurableFile.CreateNew(full, bytes);
            using (R7VerifiedFile written = R7SafeFile.Open(full, full, parent, R7Hash.Bytes(bytes), null, null, null)) { }
            Console.WriteLine(R7Json.Text(result));
        }
    }
}
