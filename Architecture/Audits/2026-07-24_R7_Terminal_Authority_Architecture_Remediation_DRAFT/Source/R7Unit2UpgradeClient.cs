using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;

namespace RandleAI.R7Remediation
{
    internal static class R7Unit2UpgradeClientProgram
    {
        private static int Main(string[] args)
        {
            try
            {
                R7RuntimeBoundary.Enforce(R7Fixed.UpgradeInstallRoot);
                if (args.Length != 2) throw new ArgumentException("usage: <health|identity|authorize|get> <new-output-json>");
                R7Unit2UpgradePolicy policy = R7Unit2UpgradePolicy.LoadPublic(R7Unit2BuildIdentity.PublicCertificateSha256);
                string executable = Path.GetFullPath(Assembly.GetExecutingAssembly().Location);
                string expectedExecutable = Path.Combine(R7Fixed.UpgradeInstallRoot, "RandleTerminalUpgradeClient.exe");
                using (R7VerifiedFile self = R7SafeFile.Open(executable, expectedExecutable, R7Fixed.UpgradeInstallRoot, policy.UpgradeClientSha256, R7Fixed.SystemSid, null, policy.VolumeIdentity))
                using (R7DependencyClosure dependencies = new R7DependencyClosure(R7Fixed.UpgradeDependencyManifestPath, policy.DependencyManifestSha256, R7Fixed.UpgradeInstallRoot))
                {
                    string operation;
                    SortedDictionary<string, object> payload;
                    if (String.Equals(args[0], "health", StringComparison.Ordinal)) { operation = "GET_HEALTH"; payload = R7Json.Object(); }
                    else if (String.Equals(args[0], "identity", StringComparison.Ordinal)) { operation = "GET_PUBLIC_IDENTITY"; payload = R7Json.Object(); }
                    else if (String.Equals(args[0], "authorize", StringComparison.Ordinal)) { operation = "AUTHORIZE_TERMINAL_TRANSITION"; payload = R7Json.Object("transition_nonce", policy.TransitionNonce, "transition_plan_sha256", policy.TransitionPlanSha256); }
                    else if (String.Equals(args[0], "get", StringComparison.Ordinal)) { operation = "GET_AUTHORIZATION"; payload = R7Json.Object("transition_nonce", policy.TransitionNonce); }
                    else throw new ArgumentException("CLIENT_OPERATION_NOT_EXPOSED");
                    string requestIdentity = DeterministicRequestIdentity(operation, payload);
                    SortedDictionary<string, object> request = R7Json.Object(
                        "interface_version", "1.0.0",
                        "operation", operation,
                        "payload", payload,
                        "protocol_version", R7Fixed.ProtocolVersion,
                        "request_identity", requestIdentity);
                    byte[] sent;
                    byte[] received;
                    SortedDictionary<string, object> response = R7Framing.Call(R7Fixed.UpgradePipe, request, 30000, out sent, out received);
                    SortedDictionary<string, object> result = R7Json.Object(
                        "artifact_type", "R7_UNIT2_MEASURED_UPGRADE_CLIENT_INTERACTION",
                        "client_file_identity", self.Measurement.FileIdentity,
                        "client_sha256", self.Measurement.Sha256,
                        "operation", operation,
                        "request_frame", Convert.ToBase64String(sent),
                        "request_frame_sha256", R7Hash.Bytes(sent),
                        "request_identity", requestIdentity,
                        "response", response,
                        "response_frame", Convert.ToBase64String(received),
                        "response_frame_sha256", R7Hash.Bytes(received),
                        "schema_version", "1.0.0");
                    dependencies.VerifyNoNewModules();
                    WriteResult(args[1], result);
                    Console.WriteLine(R7Json.Text(result));
                    return String.Equals(R7Json.String(response, "status", 1, 64), "COMPLETE", StringComparison.Ordinal) ? 0 : 2;
                }
            }
            catch (Exception exception)
            {
                Console.Error.WriteLine(exception.GetType().FullName + "|" + exception.Message);
                return 1;
            }
        }

        private static void WriteResult(string requestedPath, SortedDictionary<string, object> result)
        {
            string output = Path.GetFullPath(requestedPath);
            string root = Path.GetDirectoryName(output);
            R7SafeFile.MeasureDirectory(root, root, null, null, null);
            R7SafeFile.AssertAbsent(output, output, root);
            byte[] bytes = R7Json.Encode(result);
            R7DurableFile.CreateNew(output, bytes);
            using (R7VerifiedFile written = R7SafeFile.Open(output, output, root, R7Hash.Bytes(bytes), null, null, null)) { }
        }

        private static string DeterministicRequestIdentity(string operation, SortedDictionary<string, object> payload)
        {
            byte[] bytes = R7Json.Encode(R7Json.Object("operation", operation, "payload", payload));
            string hex = R7Hash.Bytes(bytes);
            char[] value = hex.Substring(0, 32).ToCharArray();
            value[12] = '4';
            int variant = Convert.ToInt32(value[16].ToString(), 16);
            value[16] = "89ab"[variant & 3];
            string compact = new string(value);
            return Guid.ParseExact(compact.Substring(0, 8) + "-" + compact.Substring(8, 4) + "-" + compact.Substring(12, 4) + "-" + compact.Substring(16, 4) + "-" + compact.Substring(20, 12), "D").ToString("D");
        }
    }
}
