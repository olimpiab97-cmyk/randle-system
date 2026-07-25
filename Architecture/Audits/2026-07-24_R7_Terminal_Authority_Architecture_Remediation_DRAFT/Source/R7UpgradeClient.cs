using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;

namespace RandleAI.R7Remediation
{
    internal static class R7UpgradeClientProgram
    {
        private static int Main(string[] args)
        {
            try
            {
                R7RuntimeBoundary.Enforce(R7Fixed.UpgradeInstallRoot);
                if (args.Length != 3) throw new ArgumentException("usage: <operation> <canonical-payload-json> <new-output-json>");
                R7UpgradePolicy policy = R7UpgradePolicy.Load(R7BuildIdentity.UpgradePolicySha256, R7BuildIdentity.UpgradePublicCertificateSha256);
                string executable = Path.GetFullPath(System.Reflection.Assembly.GetExecutingAssembly().Location);
                string expectedExecutable = Path.Combine(R7Fixed.UpgradeInstallRoot, "RandleTerminalUpgradeClient.exe");
                using (R7VerifiedFile self = R7SafeFile.Open(executable, expectedExecutable, R7Fixed.UpgradeInstallRoot, policy.UpgradeClientSha256, R7Fixed.SystemSid, null, policy.VolumeIdentity))
                using (R7DependencyClosure dependencies = new R7DependencyClosure(R7Fixed.UpgradeDependencyManifestPath, policy.DependencyManifestSha256, R7Fixed.UpgradeInstallRoot))
                {
                    string operation = args[0];
                    string input = Path.GetFullPath(args[1]);
                    object parsed;
                    using (R7VerifiedFile inputFile = R7SafeFile.OpenMeasured(input, input, Path.GetDirectoryName(input))) parsed = R7Json.ParseCanonicalObject(inputFile.Bytes);
                    SortedDictionary<string, object> payload = parsed as SortedDictionary<string, object>;
                    if (payload == null) throw new InvalidDataException("payload object required");
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
                        "artifact_type", "R7_MEASURED_UPGRADE_CLIENT_INTERACTION",
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
                    string output = Path.GetFullPath(args[2]);
                    string outputRoot = Path.GetDirectoryName(output);
                    R7SafeFile.MeasureDirectory(outputRoot, outputRoot, null, null, null);
                    R7SafeFile.AssertAbsent(output, output, outputRoot);
                    byte[] resultBytes = R7Json.Encode(result);
                    R7DurableFile.CreateNew(output, resultBytes);
                    using (R7VerifiedFile written = R7SafeFile.Open(output, output, outputRoot, R7Hash.Bytes(resultBytes), null, null, null)) { }
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

        private static string DeterministicRequestIdentity(string operation, SortedDictionary<string, object> payload)
        {
            byte[] bytes = R7Json.Encode(R7Json.Object("operation", operation, "payload", payload));
            string hex;
            using (SHA256 algorithm = SHA256.Create()) hex = BitConverter.ToString(algorithm.ComputeHash(bytes)).Replace("-", String.Empty).ToLowerInvariant();
            char[] value = hex.Substring(0, 32).ToCharArray();
            value[12] = '4';
            int variant = Convert.ToInt32(value[16].ToString(), 16);
            value[16] = "89ab"[variant & 3];
            string compact = new string(value);
            return Guid.ParseExact(compact.Substring(0, 8) + "-" + compact.Substring(8, 4) + "-" + compact.Substring(12, 4) + "-" + compact.Substring(16, 4) + "-" + compact.Substring(20, 12), "D").ToString("D");
        }
    }
}
