using Microsoft.Win32.SafeHandles;
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Text;
using System.Text.RegularExpressions;

namespace RandleAI.TerminalAuthority
{
    // The measured execution subject uses PowerShell only to construct the
    // reparse-point fixture exercised by R7-12-M019.  The restricted service
    // token intentionally has no SeCreateSymbolicLinkPrivilege, so this closed
    // helper creates an NTFS mount-point reparse buffer directly.  It is not a
    // generic shell and rejects every operation outside this one fixture.
    internal static class R7MeasuredJunctionFixtureHost
    {
        private const string ServiceSid = "S-1-5-80-1950096479-1020125124-2173088643-1633316353-879035948";
        private const string PythonSha256 = "624bbc0586d8855633b875e911883bbef8a0e8b8711e11126df480dd86f54181";
        private const string SubjectTemporaryRoot = @"C:\ProgramData\RandleAI\TerminalAuthority\Evidence\R7ExecutionSubjectTemp";
        private const string FixtureReceiptRoot = @"C:\ProgramData\RandleAI\TerminalAuthority\Evidence\R7FixtureProcessReceipts";
        private const uint IoReparseTagMountPoint = 0xA0000003;
        private const uint FsctlSetReparsePoint = 0x000900A4;
        private const uint GenericWrite = 0x40000000;
        private const uint FileShareRead = 0x00000001;
        private const uint FileShareWrite = 0x00000002;
        private const uint FileShareDelete = 0x00000004;
        private const uint OpenExisting = 3;
        private const uint FileFlagOpenReparsePoint = 0x00200000;
        private const uint FileFlagBackupSemantics = 0x02000000;
        private static readonly Regex CommandPattern = new Regex(
            @"\ANew-Item -ItemType Junction -Path '(?<junction>[^']+)' -Target '(?<target>[^']+)' \| Out-Null\z",
            RegexOptions.CultureInvariant | RegexOptions.ExplicitCapture);

        private static int Main(string[] args)
        {
            DateTimeOffset started = DateTimeOffset.UtcNow;
            try
            {
                ValidateArguments(args);
                string outerRunId = Environment.GetEnvironmentVariable("RANDLE_R7_OUTER_RUN_ID") ?? String.Empty;
                if (!IsLowerHex(outerRunId, 64)) throw new InvalidDataException("FIXTURE_OUTER_RUN_ID_REJECTED");
                string configuredReceiptRoot = Environment.GetEnvironmentVariable("RANDLE_R7_FIXTURE_RECEIPT_ROOT") ?? String.Empty;
                if (!String.Equals(Path.GetFullPath(configuredReceiptRoot), Path.GetFullPath(FixtureReceiptRoot), StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException("FIXTURE_RECEIPT_ROOT_REJECTED");

                WindowsIdentity identity = WindowsIdentity.GetCurrent();
                try
                {
                    WindowsPrincipal principal = new WindowsPrincipal(identity);
                    string userSid = identity.User == null ? String.Empty : identity.User.Value;
                    if (!String.Equals(userSid, ServiceSid, StringComparison.Ordinal) || principal.IsInRole(WindowsBuiltInRole.Administrator))
                        throw new UnauthorizedAccessException("FIXTURE_CALLER_PRINCIPAL_REJECTED");

                    int parentPid = GetParentProcessId(Process.GetCurrentProcess().Id);
                    string parentBinaryPath;
                    DateTime parentStart;
                    using (Process parent = Process.GetProcessById(parentPid))
                    {
                        parentBinaryPath = parent.MainModule.FileName;
                        parentStart = parent.StartTime.ToUniversalTime();
                    }
                    string parentSha256 = CryptoUtil.Sha256File(parentBinaryPath);
                    if (!String.Equals(parentSha256, PythonSha256, StringComparison.Ordinal))
                        throw new UnauthorizedAccessException("FIXTURE_PARENT_BINARY_REJECTED");

                    Match match = CommandPattern.Match(args[3]);
                    if (!match.Success) throw new InvalidDataException("FIXTURE_COMMAND_REJECTED");
                    string junctionPath = Path.GetFullPath(match.Groups["junction"].Value);
                    string targetPath = Path.GetFullPath(match.Groups["target"].Value);
                    ValidateFixturePaths(junctionPath, targetPath);
                    CreateDirectoryJunction(junctionPath, targetPath);
                    FileAttributes attributes = File.GetAttributes(junctionPath);
                    if ((attributes & FileAttributes.ReparsePoint) == 0 || (attributes & FileAttributes.Directory) == 0)
                        throw new InvalidDataException("FIXTURE_REPARSE_RESULT_REJECTED");

                    DateTimeOffset ended = DateTimeOffset.UtcNow;
                    string executablePath = Assembly.GetExecutingAssembly().Location;
                    List<object> groups = new List<object>();
                    if (identity.Groups != null)
                    {
                        foreach (IdentityReference reference in identity.Groups)
                        {
                            SecurityIdentifier sid = reference.Translate(typeof(SecurityIdentifier)) as SecurityIdentifier;
                            if (sid != null) groups.Add(sid.Value);
                        }
                    }
                    groups.Sort(delegate(object left, object right) { return StringComparer.Ordinal.Compare((string)left, (string)right); });

                    SortedDictionary<string, object> body = new SortedDictionary<string, object>(StringComparer.Ordinal);
                    body["artifact_type"] = "R7_MEASURED_JUNCTION_FIXTURE_PROCESS";
                    body["authentication_type"] = identity.AuthenticationType ?? String.Empty;
                    body["command"] = args[3];
                    body["command_sha256"] = CryptoUtil.Sha256Hex(new UTF8Encoding(false, true).GetBytes(args[3]));
                    body["end_time"] = Timestamp(ended);
                    body["exit_code"] = 0;
                    body["fixture_nonce"] = RandomHex(32);
                    body["group_sids"] = groups.ToArray();
                    body["helper_binary_file_identity"] = FileIdentity(executablePath);
                    body["helper_binary_sha256"] = CryptoUtil.Sha256File(executablePath);
                    body["helper_process_id"] = Process.GetCurrentProcess().Id;
                    body["is_administrator"] = false;
                    body["junction_path"] = junctionPath;
                    body["junction_path_sha256"] = PathIdentity(junctionPath);
                    body["operation"] = "CREATE_DIRECTORY_JUNCTION_FIXTURE";
                    body["outer_run_id"] = outerRunId;
                    body["parent_binary_file_identity"] = FileIdentity(parentBinaryPath);
                    body["parent_binary_sha256"] = parentSha256;
                    body["parent_process_id"] = parentPid;
                    body["parent_start_time"] = parentStart.ToString("yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture);
                    body["reparse_tag"] = "a0000003";
                    body["schema_version"] = "7.1.0-DRAFT";
                    body["start_time"] = Timestamp(started);
                    body["target_path"] = targetPath;
                    body["target_path_sha256"] = PathIdentity(targetPath);
                    body["token_inheritance"] = "CREATEPROCESS_DEFAULT_CALLER_TOKEN";
                    body["user_sid"] = userSid;
                    string bodyIdentity = CryptoUtil.Sha256Hex(CanonicalJson.SerializeBytes(body));

                    SortedDictionary<string, object> receipt = new SortedDictionary<string, object>(body, StringComparer.Ordinal);
                    receipt["body_identity"] = bodyIdentity;
                    byte[] bytes = CanonicalJson.SerializeBytes(receipt);
                    string receiptIdentity = CryptoUtil.Sha256Hex(bytes);
                    string runRoot = Path.Combine(FixtureReceiptRoot, outerRunId);
                    if (!Directory.Exists(runRoot)) throw new DirectoryNotFoundException("FIXTURE_RUN_RECEIPT_ROOT_MISSING");
                    string finalPath = Path.Combine(runRoot, receiptIdentity + ".json");
                    string temporaryPath = Path.Combine(runRoot, "." + receiptIdentity + "." + RandomHex(8) + ".tmp");
                    using (FileStream stream = new FileStream(temporaryPath, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                    {
                        stream.Write(bytes, 0, bytes.Length);
                        stream.Flush(true);
                    }
                    File.Move(temporaryPath, finalPath);
                    return 0;
                }
                finally
                {
                    identity.Dispose();
                }
            }
            catch (Exception exception)
            {
                Console.Error.WriteLine(exception.GetType().Name + ": " + exception.Message);
                return 1;
            }
        }

        private static void ValidateArguments(string[] args)
        {
            if (args.Length != 4 ||
                !String.Equals(args[0], "-NoProfile", StringComparison.Ordinal) ||
                !String.Equals(args[1], "-NonInteractive", StringComparison.Ordinal) ||
                !String.Equals(args[2], "-Command", StringComparison.Ordinal))
                throw new InvalidDataException("FIXTURE_ARGUMENTS_REJECTED");
        }

        private static void ValidateFixturePaths(string junctionPath, string targetPath)
        {
            string root = Path.GetFullPath(SubjectTemporaryRoot).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            if (!junctionPath.StartsWith(root, StringComparison.OrdinalIgnoreCase) || !targetPath.StartsWith(root, StringComparison.OrdinalIgnoreCase))
                throw new UnauthorizedAccessException("FIXTURE_PATH_ROOT_REJECTED");
            if (!String.Equals(Path.GetFileName(junctionPath), "reparse-parent", StringComparison.Ordinal) ||
                !String.Equals(Path.GetFileName(targetPath), "reparse-target", StringComparison.Ordinal) ||
                !String.Equals(Path.GetDirectoryName(junctionPath), Path.GetDirectoryName(targetPath), StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("FIXTURE_PATH_SHAPE_REJECTED");
            string caseDirectory = Path.GetFileName(Path.GetDirectoryName(junctionPath));
            if (caseDirectory == null || !Regex.IsMatch(caseDirectory, @"\Afilename-[0-9a-f]{12}\z", RegexOptions.CultureInvariant))
                throw new InvalidDataException("FIXTURE_CASE_DIRECTORY_REJECTED");
            if (!Directory.Exists(targetPath) || Directory.Exists(junctionPath) || File.Exists(junctionPath))
                throw new InvalidDataException("FIXTURE_INITIAL_STATE_REJECTED");
            FileAttributes targetAttributes = File.GetAttributes(targetPath);
            if ((targetAttributes & FileAttributes.ReparsePoint) != 0 || (targetAttributes & FileAttributes.Directory) == 0)
                throw new InvalidDataException("FIXTURE_TARGET_REJECTED");
        }

        private static void CreateDirectoryJunction(string junctionPath, string targetPath)
        {
            Directory.CreateDirectory(junctionPath);
            string substituteName = @"\??\" + targetPath;
            byte[] substituteBytes = Encoding.Unicode.GetBytes(substituteName);
            byte[] printBytes = Encoding.Unicode.GetBytes(targetPath);
            ushort printOffset = checked((ushort)(substituteBytes.Length + 2));
            ushort dataLength = checked((ushort)(8 + substituteBytes.Length + 2 + printBytes.Length + 2));
            byte[] buffer = new byte[8 + dataLength];
            WriteUInt32(buffer, 0, IoReparseTagMountPoint);
            WriteUInt16(buffer, 4, dataLength);
            WriteUInt16(buffer, 6, 0);
            WriteUInt16(buffer, 8, 0);
            WriteUInt16(buffer, 10, checked((ushort)substituteBytes.Length));
            WriteUInt16(buffer, 12, printOffset);
            WriteUInt16(buffer, 14, checked((ushort)printBytes.Length));
            Buffer.BlockCopy(substituteBytes, 0, buffer, 16, substituteBytes.Length);
            Buffer.BlockCopy(printBytes, 0, buffer, 16 + printOffset, printBytes.Length);

            using (SafeFileHandle handle = CreateFile(
                junctionPath,
                GenericWrite,
                FileShareRead | FileShareWrite | FileShareDelete,
                IntPtr.Zero,
                OpenExisting,
                FileFlagOpenReparsePoint | FileFlagBackupSemantics,
                IntPtr.Zero))
            {
                if (handle.IsInvalid) throw new Win32Exception(Marshal.GetLastWin32Error(), "FIXTURE_JUNCTION_OPEN_FAILED");
                uint returned;
                if (!DeviceIoControl(handle, FsctlSetReparsePoint, buffer, (uint)buffer.Length, IntPtr.Zero, 0, out returned, IntPtr.Zero))
                    throw new Win32Exception(Marshal.GetLastWin32Error(), "FIXTURE_JUNCTION_SET_REPARSE_FAILED");
            }
        }

        private static string FileIdentity(string path)
        {
            using (FileStream stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read | FileShare.Delete))
            {
                ByHandleFileInformation information;
                if (!GetFileInformationByHandle(stream.SafeFileHandle, out information))
                    throw new Win32Exception(Marshal.GetLastWin32Error(), "FIXTURE_FILE_IDENTITY_FAILED");
                return information.VolumeSerialNumber.ToString("x8", CultureInfo.InvariantCulture) + ":" +
                    information.FileIndexHigh.ToString("x8", CultureInfo.InvariantCulture) + ":" +
                    information.FileIndexLow.ToString("x8", CultureInfo.InvariantCulture);
            }
        }

        private static int GetParentProcessId(int processId)
        {
            using (SafeSnapshotHandle snapshot = CreateToolhelp32Snapshot(0x00000002, 0))
            {
                if (snapshot.IsInvalid) throw new Win32Exception(Marshal.GetLastWin32Error(), "FIXTURE_PROCESS_SNAPSHOT_FAILED");
                ProcessEntry32 entry = new ProcessEntry32();
                entry.Size = (uint)Marshal.SizeOf(typeof(ProcessEntry32));
                if (!Process32First(snapshot, ref entry)) throw new Win32Exception(Marshal.GetLastWin32Error(), "FIXTURE_PROCESS_ENUMERATION_FAILED");
                do
                {
                    if (entry.ProcessId == (uint)processId) return checked((int)entry.ParentProcessId);
                }
                while (Process32Next(snapshot, ref entry));
            }
            throw new InvalidDataException("FIXTURE_PARENT_PROCESS_UNRESOLVED");
        }

        private static string PathIdentity(string path)
        {
            return CryptoUtil.Sha256Hex(new UTF8Encoding(false, true).GetBytes(Path.GetFullPath(path)));
        }

        private static string Timestamp(DateTimeOffset value)
        {
            return value.ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture);
        }

        private static string RandomHex(int bytes)
        {
            byte[] value = new byte[bytes];
            using (System.Security.Cryptography.RandomNumberGenerator generator = System.Security.Cryptography.RandomNumberGenerator.Create()) generator.GetBytes(value);
            return CryptoUtil.ToHex(value);
        }

        private static bool IsLowerHex(string value, int length)
        {
            if (value == null || value.Length != length) return false;
            foreach (char character in value)
                if (!((character >= '0' && character <= '9') || (character >= 'a' && character <= 'f'))) return false;
            return true;
        }

        private static void WriteUInt16(byte[] buffer, int offset, ushort value)
        {
            byte[] bytes = BitConverter.GetBytes(value);
            Buffer.BlockCopy(bytes, 0, buffer, offset, bytes.Length);
        }

        private static void WriteUInt32(byte[] buffer, int offset, uint value)
        {
            byte[] bytes = BitConverter.GetBytes(value);
            Buffer.BlockCopy(bytes, 0, buffer, offset, bytes.Length);
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct FileTime
        {
            internal uint Low;
            internal uint High;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct ByHandleFileInformation
        {
            internal uint FileAttributes;
            internal FileTime CreationTime;
            internal FileTime LastAccessTime;
            internal FileTime LastWriteTime;
            internal uint VolumeSerialNumber;
            internal uint FileSizeHigh;
            internal uint FileSizeLow;
            internal uint NumberOfLinks;
            internal uint FileIndexHigh;
            internal uint FileIndexLow;
        }

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Auto)]
        private struct ProcessEntry32
        {
            internal uint Size;
            internal uint Usage;
            internal uint ProcessId;
            internal IntPtr DefaultHeapId;
            internal uint ModuleId;
            internal uint Threads;
            internal uint ParentProcessId;
            internal int BasePriority;
            internal uint Flags;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 260)]
            internal string ExecutableFile;
        }

        private sealed class SafeSnapshotHandle : SafeHandleZeroOrMinusOneIsInvalid
        {
            private SafeSnapshotHandle() : base(true) { }
            protected override bool ReleaseHandle() { return CloseHandle(handle); }
        }

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern SafeFileHandle CreateFile(string fileName, uint desiredAccess, uint shareMode, IntPtr securityAttributes,
            uint creationDisposition, uint flagsAndAttributes, IntPtr templateFile);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool DeviceIoControl(SafeFileHandle device, uint controlCode, byte[] input, uint inputSize,
            IntPtr output, uint outputSize, out uint bytesReturned, IntPtr overlapped);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool GetFileInformationByHandle(SafeFileHandle file, out ByHandleFileInformation information);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern SafeSnapshotHandle CreateToolhelp32Snapshot(uint flags, uint processId);

        [DllImport("kernel32.dll", CharSet = CharSet.Auto, SetLastError = true)]
        private static extern bool Process32First(SafeSnapshotHandle snapshot, ref ProcessEntry32 entry);

        [DllImport("kernel32.dll", CharSet = CharSet.Auto, SetLastError = true)]
        private static extern bool Process32Next(SafeSnapshotHandle snapshot, ref ProcessEntry32 entry);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool CloseHandle(IntPtr handle);
    }
}
