using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;

namespace RandleAI.R7Remediation
{
    internal static class R7MeasuredUtility
    {
        internal static SortedDictionary<string, object> Run(string executablePath, string expectedSha256, string expectedOwnerSid, string expectedSecurityDescriptorSha256, string expectedVolumeIdentity, uint expectedLinkCount, byte[] canonicalArgumentBytes)
        {
            string executable = Path.GetFullPath(executablePath);
            object parsed = R7Json.ParseCanonical(canonicalArgumentBytes);
            object[] rawArguments = parsed as object[];
            if (rawArguments == null || rawArguments.Length > 128) throw new InvalidDataException("MEASURED_UTILITY_ARGUMENTS_INVALID");
            string[] arguments = new string[rawArguments.Length];
            for (int index = 0; index < rawArguments.Length; index++)
            {
                arguments[index] = rawArguments[index] as string;
                if (arguments[index] == null || arguments[index].IndexOf('\0') >= 0 || arguments[index].Length > 32767) throw new InvalidDataException("MEASURED_UTILITY_ARGUMENT_INVALID");
            }

            using (R7VerifiedFile held = R7SafeFile.OpenDependency(executable, executable, Path.GetDirectoryName(executable), expectedSha256, expectedOwnerSid, expectedSecurityDescriptorSha256, expectedVolumeIdentity, expectedLinkCount))
            {
                ProcessStartInfo start = new ProcessStartInfo();
                start.FileName = executable;
                start.Arguments = BuildCommandLine(arguments);
                start.CreateNoWindow = true;
                start.UseShellExecute = false;
                using (Process process = Process.Start(start))
                {
                    if (process == null) throw new InvalidOperationException("MEASURED_UTILITY_PROCESS_START_FAILED");
                    int processId = process.Id;
                    process.WaitForExit();
                    int exitCode = process.ExitCode;
                    SortedDictionary<string, object> evidence = R7Json.Object(
                        "arguments_sha256", R7Hash.Bytes(canonicalArgumentBytes),
                        "artifact_type", "R7_HELD_MEASURED_UTILITY_INVOCATION",
                        "executable_file_identity", held.Measurement.FileIdentity,
                        "executable_path", held.Measurement.CanonicalPath,
                        "executable_sha256", held.Measurement.Sha256,
                        "exit_code", (long)exitCode,
                        "process_id", (long)processId,
                        "schema_version", "1.0.0");
                    return evidence;
                }
            }
        }

        private static string BuildCommandLine(string[] arguments)
        {
            StringBuilder result = new StringBuilder();
            for (int index = 0; index < arguments.Length; index++)
            {
                if (index != 0) result.Append(' ');
                AppendQuoted(result, arguments[index]);
            }
            return result.ToString();
        }

        private static void AppendQuoted(StringBuilder result, string argument)
        {
            result.Append('"');
            int slashCount = 0;
            foreach (char value in argument)
            {
                if (value == '\\') { slashCount++; continue; }
                if (value == '"')
                {
                    result.Append('\\', checked((slashCount * 2) + 1));
                    result.Append('"');
                    slashCount = 0;
                    continue;
                }
                if (slashCount != 0) { result.Append('\\', slashCount); slashCount = 0; }
                result.Append(value);
            }
            if (slashCount != 0) result.Append('\\', checked(slashCount * 2));
            result.Append('"');
        }
    }
}
