using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Pipes;
using System.Reflection;
using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Security.Principal;
using System.ServiceProcess;
using System.Text;

namespace RandleAI.R7Remediation
{
    internal static class R7ArtifactToolProgram
    {
        private static int Main(string[] args)
        {
            try
            {
                R7RuntimeBoundary.EnforceUninstalledTool();
                if (args.Length == 3 && args[0] == "canonicalize")
                {
                    byte[] source = ReadInput(args[1]);
                    byte[] canonical = R7Json.Encode(R7Json.Parse(source));
                    WriteNew(args[2], canonical);
                    Console.WriteLine(R7Hash.Bytes(canonical));
                    return 0;
                }
                if (args.Length >= 2 && args[0] == "module-snapshot")
                {
                    string[] certificates = new string[Math.Max(0, args.Length - 2)];
                    if (certificates.Length != 0) Array.Copy(args, 2, certificates, 0, certificates.Length);
                    WriteNew(args[1], R7Json.Encode(ModuleSnapshot(certificates)));
                    return 0;
                }
                if (args.Length == 2 && args[0] == "sha256")
                {
                    Console.WriteLine(R7Hash.Bytes(ReadInput(args[1])));
                    return 0;
                }
                if (args.Length == 3 && args[0] == "measure")
                {
                    WriteNew(args[2], R7Json.Encode(Row(Path.GetFullPath(args[1]))));
                    return 0;
                }
                if (args.Length == 3 && args[0] == "measure-metadata")
                {
                    string source = Path.GetFullPath(args[1]);
                    using (R7VerifiedMetadataFile file = R7SafeFile.HoldMetadataFile(source, source, Path.GetDirectoryName(source), null, null, null, null, 1)) WriteNew(args[2], R7Json.Encode(file.Measurement.ToJson()));
                    return 0;
                }
                if (args.Length == 3 && args[0] == "durable-copy")
                {
                    string source = Path.GetFullPath(args[1]);
                    string destination = Path.GetFullPath(args[2]);
                    byte[] sourceBytes = ReadInput(source);
                    string destinationRoot = Path.GetDirectoryName(destination);
                    R7SafeFile.MeasureDirectory(destinationRoot, destinationRoot, null, null, null);
                    R7SafeFile.AssertAbsent(destination, destination, destinationRoot);
                    R7DurableFile.CreateNew(destination, sourceBytes);
                    using (R7VerifiedFile copied = R7SafeFile.Open(destination, destination, destinationRoot, R7Hash.Bytes(sourceBytes), null, null, null)) Console.WriteLine(copied.Measurement.Sha256);
                    return 0;
                }
                if (args.Length == 3 && args[0] == "directory-manifest")
                {
                    WriteNew(args[2], R7Json.Encode(DirectoryManifest(args[1])));
                    return 0;
                }
                if (args.Length == 5 && args[0] == "verify-envelope")
                {
                    string envelopePath = Path.GetFullPath(args[1]);
                    string certificatePath = Path.GetFullPath(args[2]);
                    string expectedCertificateSha256 = args[3];
                    using (X509Certificate2 certificate = R7Crypto.LoadPublicCertificate(certificatePath, expectedCertificateSha256, Path.GetDirectoryName(certificatePath)))
                    using (RSA verifier = RSACertificateExtensions.GetRSAPublicKey(certificate))
                    {
                        if (verifier == null) throw new CryptographicException("PUBLIC_KEY_UNAVAILABLE");
                        SortedDictionary<string, object> payload = R7Crypto.VerifyEnvelope(ReadInput(envelopePath), expectedCertificateSha256, verifier);
                        WriteNew(args[4], R7Json.Encode(payload));
                    }
                    return 0;
                }
                if (args.Length == 5 && args[0] == "service-boundary")
                {
                    WriteNew(args[4], R7Json.Encode(R7ServiceBoundary.EnforceAndMeasure(args[1], args[2], args[3])));
                    return 0;
                }
                if (args.Length == 3 && args[0] == "restore-service-boundary")
                {
                    WriteNew(args[2], R7Json.Encode(R7ServiceBoundary.RestoreAddedRights(ReadInput(args[1]))));
                    return 0;
                }
                if (args.Length == 9 && args[0] == "run-measured-utility")
                {
                    uint expectedLinkCount;
                    if (!UInt32.TryParse(args[6], out expectedLinkCount) || expectedLinkCount < 1) throw new ArgumentException("MEASURED_UTILITY_LINK_COUNT_INVALID");
                    SortedDictionary<string, object> invocation = R7MeasuredUtility.Run(args[1], args[2], args[3], args[4], args[5], expectedLinkCount, ReadInput(args[7]));
                    WriteNew(args[8], R7Json.Encode(invocation));
                    return (long)invocation["exit_code"] == 0 ? 0 : 1;
                }
                throw new ArgumentException("usage: canonicalize <input> <output> | directory-manifest <root> <output> | durable-copy <source> <new-output> | measure-metadata <path> <output> | module-snapshot <output> [public-certificates...] | measure <path> <output> | restore-service-boundary <measurement> <output> | run-measured-utility <executable> <sha256> <owner-sid> <security-descriptor-sha256> <volume-identity> <link-count> <canonical-arguments> <output> | service-boundary <service> <expected-sid> <expected-binary> <output> | sha256 <path> | verify-envelope <envelope> <certificate> <certificate-sha256> <payload-output>");
            }
            catch (Exception exception)
            {
                Console.Error.WriteLine(exception.GetType().FullName + "|" + exception.Message);
                return 1;
            }
        }

        private static SortedDictionary<string, object> ModuleSnapshot(string[] certificatePaths)
        {
            using (SHA256 sha = SHA256.Create()) sha.ComputeHash(new byte[] { 1, 2, 3 });
            using (RSACng rsa = new RSACng(2048)) rsa.SignData(new byte[] { 1 }, HashAlgorithmName.SHA256, RSASignaturePadding.Pss);
            WindowsIdentity.GetCurrent().Dispose();
            PipeSecurity pipeSecurity = new PipeSecurity();
            pipeSecurity.AddAccessRule(new PipeAccessRule(new SecurityIdentifier(R7Fixed.SystemSid), PipeAccessRights.FullControl, AccessControlType.Allow));
            Type serviceType = typeof(ServiceBase);
            string ignored = serviceType.FullName;
            ignored = typeof(EventLog).FullName;
            try { using (EventLog systemLog = new EventLog("System")) ignored = systemLog.Entries.Count.ToString(); } catch { }
            R7ServiceBoundary.ProbeNativeDependencies();
            foreach (string certificatePath in certificatePaths)
            {
                using (X509Certificate2 certificate = new X509Certificate2(Path.GetFullPath(certificatePath)))
                using (RSA publicKey = RSACertificateExtensions.GetRSAPublicKey(certificate)) if (publicKey != null) ignored = publicKey.KeySize.ToString();
            }
            string executable = Path.GetFullPath(Assembly.GetExecutingAssembly().Location);
            using (R7VerifiedFile self = R7SafeFile.Open(executable, executable, Path.GetDirectoryName(executable), null, null, null, null)) ignored = self.Measurement.FileIdentity;

            Dictionary<string, object> native = new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase);
            foreach (ProcessModule module in Process.GetCurrentProcess().Modules)
            {
                string path = Path.GetFullPath(module.FileName);
                if (String.Equals(path, executable, StringComparison.OrdinalIgnoreCase) || native.ContainsKey(path)) continue;
                native.Add(path, Row(path));
            }
            Dictionary<string, object> managed = new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase);
            foreach (Assembly assembly in AppDomain.CurrentDomain.GetAssemblies())
            {
                string path;
                try { path = assembly.Location; } catch (NotSupportedException) { continue; }
                if (String.IsNullOrEmpty(path)) continue;
                path = Path.GetFullPath(path);
                if (String.Equals(path, executable, StringComparison.OrdinalIgnoreCase) || managed.ContainsKey(path)) continue;
                managed.Add(path, Row(path));
            }
            List<object> nativeRows = Values(native);
            List<object> managedRows = Values(managed);
            return R7Json.Object(
                "artifact_type", "R7_BUILD_TIME_RUNTIME_MODULE_SNAPSHOT",
                "framework_references", managedRows.ToArray(),
                "runtime_allowlist", nativeRows.ToArray(),
                "schema_version", "1.0.0");
        }

        private static SortedDictionary<string, object> DirectoryManifest(string requestedRoot)
        {
            string root = Path.GetFullPath(requestedRoot).TrimEnd(Path.DirectorySeparatorChar);
            List<string> paths = new List<string>();
            CollectDirectory(root, paths);
            paths.Sort(StringComparer.Ordinal);
            List<object> rows = new List<object>();
            foreach (string path in paths) rows.Add(Row(path));
            return R7Json.Object(
                "artifact_type", "R7_RECURSIVE_BUILD_INPUT_CLOSURE",
                "file_count", (long)rows.Count,
                "files", rows.ToArray(),
                "root", root,
                "schema_version", "1.0.0");
        }

        private static void CollectDirectory(string directory, List<string> files)
        {
            using (R7VerifiedDirectory heldDirectory = R7SafeFile.HoldDirectory(directory, directory, null, null, null))
            {
                DirectoryInfo current = new DirectoryInfo(directory);
                FileSystemInfo[] entries = current.GetFileSystemInfos();
                Array.Sort(entries, delegate(FileSystemInfo left, FileSystemInfo right) { return StringComparer.Ordinal.Compare(left.FullName, right.FullName); });
                foreach (FileSystemInfo entry in entries)
                {
                    if ((entry.Attributes & FileAttributes.ReparsePoint) != 0) throw new IOException("BUILD_INPUT_REPARSE_ENTRY|" + entry.FullName);
                    DirectoryInfo child = entry as DirectoryInfo;
                    if (child != null) CollectDirectory(child.FullName, files);
                    else files.Add(Path.GetFullPath(entry.FullName));
                }
            }
        }

        private static SortedDictionary<string, object> Row(string path)
        {
            using (R7VerifiedFile file = R7SafeFile.OpenMeasuredCanonical(path))
                return R7Json.Object(
                    "file_identity", file.Measurement.FileIdentity,
                    "hard_link_count", (long)file.Measurement.LinkCount,
                    "owner_sid", file.Measurement.OwnerSid,
                    "path", file.Measurement.CanonicalPath,
                    "security_descriptor_sha256", file.Measurement.SecurityDescriptorSha256,
                    "sha256", file.Measurement.Sha256,
                    "size", file.Measurement.Size,
                    "volume_identity", file.Measurement.VolumeIdentity);
        }

        private static List<object> Values(Dictionary<string, object> values)
        {
            List<string> keys = new List<string>(values.Keys);
            keys.Sort(StringComparer.OrdinalIgnoreCase);
            List<object> result = new List<object>();
            foreach (string key in keys) result.Add(values[key]);
            return result;
        }

        private static void WriteNew(string path, byte[] bytes)
        {
            string full = Path.GetFullPath(path);
            string parent = Path.GetDirectoryName(full);
            R7SafeFile.MeasureDirectory(parent, parent, null, null, null);
            R7SafeFile.AssertAbsent(full, full, parent);
            R7DurableFile.CreateNew(full, bytes);
        }

        private static byte[] ReadInput(string requestedPath)
        {
            string full = Path.GetFullPath(requestedPath);
            using (R7VerifiedFile file = R7SafeFile.OpenMeasured(full, full, Path.GetDirectoryName(full))) return file.Bytes;
        }
    }
}
