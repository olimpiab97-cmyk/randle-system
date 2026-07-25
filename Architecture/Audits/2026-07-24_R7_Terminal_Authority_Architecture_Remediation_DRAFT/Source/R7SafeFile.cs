using Microsoft.Win32.SafeHandles;
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Text;

namespace RandleAI.R7Remediation
{
    internal sealed class R7FileMeasurement
    {
        internal string CanonicalPath;
        internal string FinalNtPath;
        internal string VolumeIdentity;
        internal string FileIdentity;
        internal string OwnerSid;
        internal string SecurityDescriptorSha256;
        internal uint LinkCount;
        internal long Size;
        internal string Sha256;
        internal string ShortPath;
        internal string[] Streams;
        internal string CreationTime;

        internal SortedDictionary<string, object> ToJson()
        {
            return R7Json.Object(
                "canonical_path", CanonicalPath,
                "creation_time", CreationTime,
                "file_identity", FileIdentity,
                "final_nt_path", FinalNtPath,
                "hard_link_count", (long)LinkCount,
                "owner_sid", OwnerSid,
                "security_descriptor_sha256", SecurityDescriptorSha256,
                "sha256", Sha256 ?? String.Empty,
                "short_path", ShortPath ?? String.Empty,
                "size", Size,
                "streams", Streams ?? new string[0],
                "volume_identity", VolumeIdentity);
        }
    }

    internal sealed class R7VerifiedFile : IDisposable
    {
        private SafeFileHandle handle;
        internal readonly R7FileMeasurement Measurement;
        internal readonly byte[] Bytes;

        internal R7VerifiedFile(SafeFileHandle heldHandle, R7FileMeasurement measurement, byte[] bytes)
        {
            handle = heldHandle;
            Measurement = measurement;
            Bytes = bytes;
        }

        public void Dispose()
        {
            if (handle != null) { handle.Dispose(); handle = null; }
        }
    }

    internal sealed class R7VerifiedDirectory : IDisposable
    {
        private SafeFileHandle handle;
        internal readonly R7FileMeasurement Measurement;

        internal R7VerifiedDirectory(SafeFileHandle heldHandle, R7FileMeasurement measurement) { handle = heldHandle; Measurement = measurement; }
        public void Dispose() { if (handle != null) { handle.Dispose(); handle = null; } }
    }

    internal sealed class R7VerifiedMetadataFile : IDisposable
    {
        private SafeFileHandle handle;
        internal readonly R7FileMeasurement Measurement;
        internal R7VerifiedMetadataFile(SafeFileHandle heldHandle, R7FileMeasurement measurement) { handle = heldHandle; Measurement = measurement; }
        public void Dispose() { if (handle != null) { handle.Dispose(); handle = null; } }
    }

    internal static class R7SafeFile
    {
        private const uint GenericRead = 0x80000000;
        private const uint FileReadAttributes = 0x00000080;
        private const uint ReadControl = 0x00020000;
        private const uint FileShareRead = 0x00000001;
        private const uint OpenExisting = 3;
        private const uint FileFlagBackupSemantics = 0x02000000;
        private const uint FileFlagOpenReparsePoint = 0x00200000;
        private const uint FileAttributeReparsePoint = 0x00000400;
        private const uint OwnerSecurityInformation = 0x00000001;
        private const uint GroupSecurityInformation = 0x00000002;
        private const uint DaclSecurityInformation = 0x00000004;
        private const int SeFileObject = 1;
        private const uint SddlRevision1 = 1;
        private const uint TokenAdjustPrivileges = 0x00000020;
        private const uint TokenQuery = 0x00000008;
        private const uint SePrivilegeEnabled = 0x00000002;
        private const int ErrorNotAllAssigned = 1300;
        private const int FileStreamInfo = 7;
        private static readonly IntPtr InvalidFindHandle = new IntPtr(-1);

        [StructLayout(LayoutKind.Sequential)]
        private struct FileTime { public uint Low; public uint High; }

        [StructLayout(LayoutKind.Sequential)]
        private struct ByHandleFileInformation
        {
            public uint FileAttributes;
            public FileTime CreationTime;
            public FileTime LastAccessTime;
            public FileTime LastWriteTime;
            public uint VolumeSerialNumber;
            public uint FileSizeHigh;
            public uint FileSizeLow;
            public uint NumberOfLinks;
            public uint FileIndexHigh;
            public uint FileIndexLow;
        }

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        private struct Win32FindStreamData
        {
            public long StreamSize;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 296)] public string StreamName;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct Luid
        {
            public uint LowPart;
            public int HighPart;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct TokenPrivileges
        {
            public uint PrivilegeCount;
            public Luid Luid;
            public uint Attributes;
        }

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern SafeFileHandle CreateFileW(string name, uint access, uint share, IntPtr security, uint creation, uint flags, IntPtr templateFile);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool GetFileInformationByHandle(SafeFileHandle handle, out ByHandleFileInformation information);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool GetFileInformationByHandleEx(SafeFileHandle handle, int informationClass, IntPtr information, uint informationSize);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern uint GetFinalPathNameByHandleW(SafeFileHandle handle, StringBuilder output, uint length, uint flags);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool ReadFile(SafeFileHandle handle, byte[] buffer, uint count, out uint read, IntPtr overlapped);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool SetFilePointerEx(SafeFileHandle handle, long distance, out long newPosition, uint method);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern uint GetLongPathNameW(string shortPath, StringBuilder longPath, uint length);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern uint GetShortPathNameW(string longPath, StringBuilder shortPath, uint length);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern IntPtr FindFirstStreamW(string fileName, int informationLevel, out Win32FindStreamData data, uint flags);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern bool FindNextStreamW(IntPtr findHandle, out Win32FindStreamData data);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool FindClose(IntPtr findHandle);

        [DllImport("advapi32.dll", SetLastError = true)]
        private static extern uint GetSecurityInfo(IntPtr handle, int objectType, uint securityInfo, out IntPtr owner, out IntPtr group, out IntPtr dacl, out IntPtr sacl, out IntPtr securityDescriptor);

        [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern bool ConvertSecurityDescriptorToStringSecurityDescriptorW(IntPtr securityDescriptor, uint revision, uint securityInfo, out IntPtr stringSecurityDescriptor, out uint stringLength);

        [DllImport("kernel32.dll")]
        private static extern IntPtr LocalFree(IntPtr memory);

        [DllImport("kernel32.dll")]
        private static extern IntPtr GetCurrentProcess();

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool CloseHandle(IntPtr handle);

        [DllImport("advapi32.dll", SetLastError = true)]
        private static extern bool OpenProcessToken(IntPtr process, uint desiredAccess, out IntPtr token);

        [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern bool LookupPrivilegeValue(string systemName, string name, out Luid luid);

        [DllImport("advapi32.dll", SetLastError = true)]
        private static extern bool AdjustTokenPrivileges(IntPtr token, bool disableAllPrivileges, ref TokenPrivileges newState, uint bufferLength, out TokenPrivileges previousState, out uint returnLength);

        [DllImport("advapi32.dll", EntryPoint = "AdjustTokenPrivileges", SetLastError = true)]
        private static extern bool RestoreTokenPrivileges(IntPtr token, bool disableAllPrivileges, ref TokenPrivileges newState, uint bufferLength, IntPtr previousState, IntPtr returnLength);

        private sealed class BackupPrivilegeScope : IDisposable
        {
            private IntPtr token;
            private TokenPrivileges previous;
            private bool restore;

            internal BackupPrivilegeScope()
            {
                if (!OpenProcessToken(GetCurrentProcess(), TokenAdjustPrivileges | TokenQuery, out token)) ThrowWin32("BACKUP_PRIVILEGE_TOKEN_OPEN_FAILED");
                try
                {
                    Luid luid;
                    if (!LookupPrivilegeValue(null, "SeBackupPrivilege", out luid)) ThrowWin32("BACKUP_PRIVILEGE_LOOKUP_FAILED");
                    TokenPrivileges desired = new TokenPrivileges { PrivilegeCount = 1, Luid = luid, Attributes = SePrivilegeEnabled };
                    uint returned;
                    if (!AdjustTokenPrivileges(token, false, ref desired, (uint)Marshal.SizeOf(typeof(TokenPrivileges)), out previous, out returned)) ThrowWin32("BACKUP_PRIVILEGE_ENABLE_FAILED");
                    int error = Marshal.GetLastWin32Error();
                    if (error == ErrorNotAllAssigned) throw new R7ProtocolException("BACKUP_PRIVILEGE_NOT_ASSIGNED");
                    if (error != 0) throw new R7ProtocolException("BACKUP_PRIVILEGE_ENABLE_FAILED", error.ToString(CultureInfo.InvariantCulture));
                    restore = true;
                }
                catch
                {
                    CloseHandle(token);
                    token = IntPtr.Zero;
                    throw;
                }
            }

            public void Dispose()
            {
                if (token == IntPtr.Zero) return;
                try
                {
                    if (restore && !RestoreTokenPrivileges(token, false, ref previous, 0, IntPtr.Zero, IntPtr.Zero)) ThrowWin32("BACKUP_PRIVILEGE_RESTORE_FAILED");
                }
                finally
                {
                    CloseHandle(token);
                    token = IntPtr.Zero;
                }
            }
        }

        internal static R7VerifiedFile Open(
            string path,
            string expectedCanonicalPath,
            string fixedRoot,
            string expectedSha256,
            string expectedOwnerSid,
            string expectedSecurityDescriptorSha256,
            string expectedVolumeIdentity)
        {
            return OpenBound(path, expectedCanonicalPath, fixedRoot, expectedSha256, expectedOwnerSid, expectedSecurityDescriptorSha256, expectedVolumeIdentity, 1);
        }

        internal static R7VerifiedFile OpenDependency(
            string path,
            string expectedCanonicalPath,
            string fixedRoot,
            string expectedSha256,
            string expectedOwnerSid,
            string expectedSecurityDescriptorSha256,
            string expectedVolumeIdentity,
            uint expectedLinkCount)
        {
            if (expectedLinkCount < 1) throw new R7ProtocolException("HARD_LINK_EXPECTATION_INVALID");
            return OpenBound(path, expectedCanonicalPath, fixedRoot, expectedSha256, expectedOwnerSid, expectedSecurityDescriptorSha256, expectedVolumeIdentity, expectedLinkCount);
        }

        internal static R7VerifiedFile OpenMeasured(string path, string expectedCanonicalPath, string fixedRoot)
        {
            return OpenBound(path, expectedCanonicalPath, fixedRoot, null, null, null, null, 0);
        }

        internal static R7VerifiedFile OpenMeasuredCanonical(string path)
        {
            string full = Path.GetFullPath(path);
            SafeFileHandle canonicalHandle = CreateFileW(full, GenericRead | FileReadAttributes | ReadControl, FileShareRead, IntPtr.Zero, OpenExisting, FileFlagOpenReparsePoint, IntPtr.Zero);
            if (canonicalHandle.IsInvalid) { int error = Marshal.GetLastWin32Error(); canonicalHandle.Dispose(); throw new R7ProtocolException("SAFE_OPEN_FAILED", error.ToString(CultureInfo.InvariantCulture)); }
            using (canonicalHandle)
            {
                ByHandleFileInformation information;
                if (!GetFileInformationByHandle(canonicalHandle, out information)) ThrowWin32("FILE_INFORMATION_FAILED");
                if ((information.FileAttributes & FileAttributeReparsePoint) != 0) throw new R7ProtocolException("REPARSE_POINT_REJECTED");
                string final = FinalPath(canonicalHandle);
                if (!final.StartsWith(@"\\?\", StringComparison.Ordinal)) throw new R7ProtocolException("FINAL_PATH_FORMAT_REJECTED", final);
                string canonical = final.Substring(4);
                if (!String.Equals(full, canonical, StringComparison.OrdinalIgnoreCase)) throw new R7ProtocolException("PATH_ALIAS_REJECTED", full);
                return OpenBound(canonical, canonical, Path.GetDirectoryName(canonical), null, null, null, null, 0);
            }
        }

        internal static bool TryOpen(
            string path,
            string expectedCanonicalPath,
            string fixedRoot,
            string expectedSha256,
            string expectedOwnerSid,
            string expectedSecurityDescriptorSha256,
            string expectedVolumeIdentity,
            out R7VerifiedFile file)
        {
            bool missing;
            file = OpenBound(path, expectedCanonicalPath, fixedRoot, expectedSha256, expectedOwnerSid, expectedSecurityDescriptorSha256, expectedVolumeIdentity, 1, true, out missing);
            return !missing;
        }

        private static R7VerifiedFile OpenBound(
            string path,
            string expectedCanonicalPath,
            string fixedRoot,
            string expectedSha256,
            string expectedOwnerSid,
            string expectedSecurityDescriptorSha256,
            string expectedVolumeIdentity,
            uint expectedLinkCount)
        {
            bool missing;
            return OpenBound(path, expectedCanonicalPath, fixedRoot, expectedSha256, expectedOwnerSid, expectedSecurityDescriptorSha256, expectedVolumeIdentity, expectedLinkCount, false, out missing);
        }

        private static R7VerifiedFile OpenBound(
            string path,
            string expectedCanonicalPath,
            string fixedRoot,
            string expectedSha256,
            string expectedOwnerSid,
            string expectedSecurityDescriptorSha256,
            string expectedVolumeIdentity,
            uint expectedLinkCount,
            bool allowMissing,
            out bool missing)
        {
            missing = false;
            if (path == null || expectedCanonicalPath == null || fixedRoot == null) throw new R7ProtocolException("PATH_REQUIRED");
            string full = Path.GetFullPath(path);
            string expected = Path.GetFullPath(expectedCanonicalPath);
            string root = Path.GetFullPath(fixedRoot).TrimEnd(Path.DirectorySeparatorChar);
            if (!String.Equals(full, expected, StringComparison.Ordinal)) throw new R7ProtocolException("CANONICAL_PATH_MISMATCH");
            if (!full.StartsWith(root + Path.DirectorySeparatorChar, StringComparison.Ordinal) && !String.Equals(full, root, StringComparison.Ordinal)) throw new R7ProtocolException("FIXED_ROOT_ESCAPE");
            VerifyDirectoryChain(Path.GetDirectoryName(full));

            SafeFileHandle handle = CreateFileW(full, GenericRead | FileReadAttributes | ReadControl, FileShareRead, IntPtr.Zero, OpenExisting, FileFlagOpenReparsePoint, IntPtr.Zero);
            if (handle.IsInvalid)
            {
                int error = Marshal.GetLastWin32Error();
                handle.Dispose();
                if (allowMissing && (error == 2 || error == 3)) { missing = true; return null; }
                throw new R7ProtocolException("SAFE_OPEN_FAILED", error.ToString(CultureInfo.InvariantCulture));
            }
            try
            {
                ByHandleFileInformation information;
                if (!GetFileInformationByHandle(handle, out information)) ThrowWin32("FILE_INFORMATION_FAILED");
                if ((information.FileAttributes & FileAttributeReparsePoint) != 0) throw new R7ProtocolException("REPARSE_POINT_REJECTED");
                if (information.NumberOfLinks < 1 || (expectedLinkCount != 0 && information.NumberOfLinks != expectedLinkCount)) throw new R7ProtocolException("HARD_LINK_COUNT_REJECTED", information.NumberOfLinks.ToString(CultureInfo.InvariantCulture));
                string final = FinalPath(handle);
                string expectedFinal = @"\\?\" + expected;
                if (!String.Equals(final, expectedFinal, StringComparison.Ordinal)) throw new R7ProtocolException("FINAL_PATH_MISMATCH", final);
                string longPath = LongPath(full);
                if (!String.Equals(longPath, expected, StringComparison.Ordinal)) throw new R7ProtocolException("PATH_ALIAS_REJECTED", longPath);
                string shortPath = ShortPath(full);
                string[] streams = Streams(final);
                if (streams.Length != 1 || !String.Equals(streams[0], "::$DATA", StringComparison.Ordinal)) throw new R7ProtocolException("ALTERNATE_DATA_STREAM_REJECTED");
                long size = ((long)information.FileSizeHigh << 32) | information.FileSizeLow;
                if (size < 0 || size > Int32.MaxValue) throw new R7ProtocolException("FILE_SIZE_UNSUPPORTED");
                byte[] bytes = ReadAll(handle, (int)size);
                string sha = R7Hash.Bytes(bytes);
                string owner;
                string sddl;
                ReadSecurity(handle, out owner, out sddl);
                string sddlSha = R7Hash.Bytes(new UTF8Encoding(false, true).GetBytes(sddl));
                string volume = information.VolumeSerialNumber.ToString("x8", CultureInfo.InvariantCulture);
                string fileId = volume + ":" + information.FileIndexHigh.ToString("x8", CultureInfo.InvariantCulture) + information.FileIndexLow.ToString("x8", CultureInfo.InvariantCulture);
                if (!String.IsNullOrEmpty(expectedSha256) && !R7Hash.FixedTimeEquals(sha, expectedSha256)) throw new R7ProtocolException("CONTENT_IDENTITY_MISMATCH");
                if (!String.IsNullOrEmpty(expectedOwnerSid) && !String.Equals(owner, expectedOwnerSid, StringComparison.Ordinal)) throw new R7ProtocolException("OWNER_IDENTITY_MISMATCH");
                if (!String.IsNullOrEmpty(expectedSecurityDescriptorSha256) && !R7Hash.FixedTimeEquals(sddlSha, expectedSecurityDescriptorSha256)) throw new R7ProtocolException("ACL_IDENTITY_MISMATCH");
                if (!String.IsNullOrEmpty(expectedVolumeIdentity) && !String.Equals(volume, expectedVolumeIdentity, StringComparison.Ordinal)) throw new R7ProtocolException("VOLUME_IDENTITY_MISMATCH");
                R7FileMeasurement measurement = new R7FileMeasurement
                {
                    CanonicalPath = expected,
                    FinalNtPath = final,
                    VolumeIdentity = volume,
                    FileIdentity = fileId,
                    OwnerSid = owner,
                    SecurityDescriptorSha256 = sddlSha,
                    LinkCount = information.NumberOfLinks,
                    Size = size,
                    Sha256 = sha,
                    ShortPath = shortPath,
                    Streams = streams,
                    CreationTime = FileTimeText(information.CreationTime)
                };
                return new R7VerifiedFile(handle, measurement, bytes);
            }
            catch { handle.Dispose(); throw; }
        }

        internal static R7FileMeasurement MeasureDirectory(string path, string expectedCanonicalPath, string expectedOwnerSid, string expectedSecurityDescriptorSha256, string expectedVolumeIdentity)
        {
            using (R7VerifiedDirectory directory = HoldDirectory(path, expectedCanonicalPath, expectedOwnerSid, expectedSecurityDescriptorSha256, expectedVolumeIdentity)) return directory.Measurement;
        }

        internal static void AssertAbsent(string path, string expectedCanonicalPath, string fixedExistingBoundaryRoot)
        {
            string full = Path.GetFullPath(path);
            string expected = Path.GetFullPath(expectedCanonicalPath);
            string boundary = Path.GetFullPath(fixedExistingBoundaryRoot).TrimEnd(Path.DirectorySeparatorChar);
            if (!String.Equals(full, expected, StringComparison.Ordinal)) throw new R7ProtocolException("CANONICAL_PATH_MISMATCH");
            if (!full.StartsWith(boundary + Path.DirectorySeparatorChar, StringComparison.Ordinal)) throw new R7ProtocolException("FIXED_ROOT_ESCAPE");
            VerifyDirectoryChain(boundary);
            string parent = Path.GetDirectoryName(full);
            string relativeParent = parent.Substring(boundary.Length).TrimStart(Path.DirectorySeparatorChar);
            string cursor = boundary;
            if (relativeParent.Length != 0)
            {
                foreach (string segment in relativeParent.Split(Path.DirectorySeparatorChar))
                {
                    if (segment.Length == 0 || segment == "." || segment == "..") throw new R7ProtocolException("PATH_SEGMENT_INVALID");
                    cursor = Path.Combine(cursor, segment);
                    if (!VerifyExistingDirectoryOrMissing(cursor)) return;
                }
            }
            R7VerifiedFile existing;
            if (TryOpen(full, expected, boundary, null, null, null, null, out existing))
            {
                existing.Dispose();
                throw new R7ProtocolException("PATH_EXPECTED_ABSENT");
            }
        }

        internal static R7VerifiedMetadataFile HoldMetadataFile(string path, string expectedCanonicalPath, string fixedRoot, string expectedOwnerSid, string expectedSecurityDescriptorSha256, string expectedVolumeIdentity, string expectedFileIdentity, uint expectedLinkCount)
        {
            string full = Path.GetFullPath(path);
            string expected = Path.GetFullPath(expectedCanonicalPath);
            string root = Path.GetFullPath(fixedRoot).TrimEnd(Path.DirectorySeparatorChar);
            if (!String.Equals(full, expected, StringComparison.Ordinal)) throw new R7ProtocolException("CANONICAL_PATH_MISMATCH");
            if (!full.StartsWith(root + Path.DirectorySeparatorChar, StringComparison.Ordinal)) throw new R7ProtocolException("FIXED_ROOT_ESCAPE");
            VerifyDirectoryChain(Path.GetDirectoryName(full));
            SafeFileHandle handle = CreateFileW(full, FileReadAttributes | ReadControl, FileShareRead, IntPtr.Zero, OpenExisting, FileFlagOpenReparsePoint, IntPtr.Zero);
            if (handle.IsInvalid) { int error = Marshal.GetLastWin32Error(); handle.Dispose(); throw new R7ProtocolException("METADATA_SAFE_OPEN_FAILED", error.ToString(CultureInfo.InvariantCulture)); }
            try
            {
                ByHandleFileInformation information;
                if (!GetFileInformationByHandle(handle, out information)) ThrowWin32("FILE_INFORMATION_FAILED");
                if ((information.FileAttributes & FileAttributeReparsePoint) != 0) throw new R7ProtocolException("REPARSE_POINT_REJECTED");
                if (expectedLinkCount < 1 || information.NumberOfLinks != expectedLinkCount) throw new R7ProtocolException("HARD_LINK_COUNT_REJECTED", information.NumberOfLinks.ToString(CultureInfo.InvariantCulture));
                string final = FinalPath(handle);
                if (!String.Equals(final, @"\\?\" + expected, StringComparison.Ordinal)) throw new R7ProtocolException("FINAL_PATH_MISMATCH", final);
                if (!String.Equals(LongPath(full), expected, StringComparison.Ordinal)) throw new R7ProtocolException("PATH_ALIAS_REJECTED");
                string[] streams = Streams(final);
                if (streams.Length != 1 || streams[0] != "::$DATA") throw new R7ProtocolException("ALTERNATE_DATA_STREAM_REJECTED");
                string owner;
                string sddl;
                ReadSecurity(handle, out owner, out sddl);
                string sddlSha = R7Hash.Bytes(new UTF8Encoding(false, true).GetBytes(sddl));
                string volume = information.VolumeSerialNumber.ToString("x8", CultureInfo.InvariantCulture);
                string fileIdentity = volume + ":" + information.FileIndexHigh.ToString("x8", CultureInfo.InvariantCulture) + information.FileIndexLow.ToString("x8", CultureInfo.InvariantCulture);
                if (!String.IsNullOrEmpty(expectedOwnerSid) && owner != expectedOwnerSid) throw new R7ProtocolException("OWNER_IDENTITY_MISMATCH");
                if (!String.IsNullOrEmpty(expectedSecurityDescriptorSha256) && !R7Hash.FixedTimeEquals(sddlSha, expectedSecurityDescriptorSha256)) throw new R7ProtocolException("ACL_IDENTITY_MISMATCH");
                if (!String.IsNullOrEmpty(expectedVolumeIdentity) && volume != expectedVolumeIdentity) throw new R7ProtocolException("VOLUME_IDENTITY_MISMATCH");
                if (!String.IsNullOrEmpty(expectedFileIdentity) && fileIdentity != expectedFileIdentity) throw new R7ProtocolException("FILE_IDENTITY_MISMATCH");
                long size = ((long)information.FileSizeHigh << 32) | information.FileSizeLow;
                return new R7VerifiedMetadataFile(handle, new R7FileMeasurement
                {
                    CanonicalPath = expected,
                    CreationTime = FileTimeText(information.CreationTime),
                    FileIdentity = fileIdentity,
                    FinalNtPath = final,
                    LinkCount = information.NumberOfLinks,
                    OwnerSid = owner,
                    SecurityDescriptorSha256 = sddlSha,
                    Sha256 = String.Empty,
                    ShortPath = ShortPath(full),
                    Size = size,
                    Streams = streams,
                    VolumeIdentity = volume
                });
            }
            catch { handle.Dispose(); throw; }
        }

        internal static R7VerifiedMetadataFile HoldProtectedMetadataFile(string path, string expectedCanonicalPath, string fixedRoot, string expectedOwnerSid, string expectedSecurityDescriptorSha256, string expectedVolumeIdentity, string expectedFileIdentity, uint expectedLinkCount)
        {
            string full = Path.GetFullPath(path);
            string expected = Path.GetFullPath(expectedCanonicalPath);
            string root = Path.GetFullPath(fixedRoot).TrimEnd(Path.DirectorySeparatorChar);
            if (!String.Equals(full, expected, StringComparison.Ordinal)) throw new R7ProtocolException("CANONICAL_PATH_MISMATCH");
            if (!full.StartsWith(root + Path.DirectorySeparatorChar, StringComparison.Ordinal)) throw new R7ProtocolException("FIXED_ROOT_ESCAPE");
            VerifyDirectoryChain(Path.GetDirectoryName(full));
            using (BackupPrivilegeScope privilege = new BackupPrivilegeScope())
            {
                SafeFileHandle handle = CreateFileW(full, FileReadAttributes | ReadControl, FileShareRead, IntPtr.Zero, OpenExisting, FileFlagBackupSemantics | FileFlagOpenReparsePoint, IntPtr.Zero);
                if (handle.IsInvalid) { int error = Marshal.GetLastWin32Error(); handle.Dispose(); throw new R7ProtocolException("PROTECTED_METADATA_SAFE_OPEN_FAILED", error.ToString(CultureInfo.InvariantCulture)); }
                try
                {
                    ByHandleFileInformation information;
                    if (!GetFileInformationByHandle(handle, out information)) ThrowWin32("FILE_INFORMATION_FAILED");
                    if ((information.FileAttributes & FileAttributeReparsePoint) != 0) throw new R7ProtocolException("REPARSE_POINT_REJECTED");
                    if (expectedLinkCount < 1 || information.NumberOfLinks != expectedLinkCount) throw new R7ProtocolException("HARD_LINK_COUNT_REJECTED", information.NumberOfLinks.ToString(CultureInfo.InvariantCulture));
                    string final = FinalPath(handle);
                    if (!String.Equals(final, @"\\?\" + expected, StringComparison.Ordinal)) throw new R7ProtocolException("FINAL_PATH_MISMATCH", final);
                    if (!String.Equals(LongPath(full), expected, StringComparison.Ordinal)) throw new R7ProtocolException("PATH_ALIAS_REJECTED", full);
                    string[] streams = StreamsByHandle(handle);
                    if (streams.Length != 1 || streams[0] != "::$DATA") throw new R7ProtocolException("ALTERNATE_DATA_STREAM_REJECTED");
                    string owner;
                    string sddl;
                    ReadSecurity(handle, out owner, out sddl);
                    string sddlSha = R7Hash.Bytes(new UTF8Encoding(false, true).GetBytes(sddl));
                    string volume = information.VolumeSerialNumber.ToString("x8", CultureInfo.InvariantCulture);
                    string fileIdentity = volume + ":" + information.FileIndexHigh.ToString("x8", CultureInfo.InvariantCulture) + information.FileIndexLow.ToString("x8", CultureInfo.InvariantCulture);
                    if (!String.IsNullOrEmpty(expectedOwnerSid) && owner != expectedOwnerSid) throw new R7ProtocolException("OWNER_IDENTITY_MISMATCH");
                    if (!String.IsNullOrEmpty(expectedSecurityDescriptorSha256) && !R7Hash.FixedTimeEquals(sddlSha, expectedSecurityDescriptorSha256)) throw new R7ProtocolException("ACL_IDENTITY_MISMATCH");
                    if (!String.IsNullOrEmpty(expectedVolumeIdentity) && volume != expectedVolumeIdentity) throw new R7ProtocolException("VOLUME_IDENTITY_MISMATCH");
                    if (!String.IsNullOrEmpty(expectedFileIdentity) && fileIdentity != expectedFileIdentity) throw new R7ProtocolException("FILE_IDENTITY_MISMATCH");
                    long size = ((long)information.FileSizeHigh << 32) | information.FileSizeLow;
                    return new R7VerifiedMetadataFile(handle, new R7FileMeasurement
                    {
                        CanonicalPath = expected,
                        CreationTime = FileTimeText(information.CreationTime),
                        FileIdentity = fileIdentity,
                        FinalNtPath = final,
                        LinkCount = information.NumberOfLinks,
                        OwnerSid = owner,
                        SecurityDescriptorSha256 = sddlSha,
                        Sha256 = String.Empty,
                        ShortPath = ShortPath(full),
                        Size = size,
                        Streams = streams,
                        VolumeIdentity = volume
                    });
                }
                catch { handle.Dispose(); throw; }
            }
        }

        internal static R7VerifiedDirectory HoldDirectory(string path, string expectedCanonicalPath, string expectedOwnerSid, string expectedSecurityDescriptorSha256, string expectedVolumeIdentity)
        {
            string full = Path.GetFullPath(path).TrimEnd(Path.DirectorySeparatorChar);
            string expected = Path.GetFullPath(expectedCanonicalPath).TrimEnd(Path.DirectorySeparatorChar);
            if (!String.Equals(full, expected, StringComparison.Ordinal)) throw new R7ProtocolException("CANONICAL_PATH_MISMATCH");
            VerifyDirectoryChain(expected);
            SafeFileHandle handle = OpenDirectory(expected);
            try
            {
                ByHandleFileInformation information;
                if (!GetFileInformationByHandle(handle, out information)) ThrowWin32("DIRECTORY_INFORMATION_FAILED");
                if ((information.FileAttributes & FileAttributeReparsePoint) != 0) throw new R7ProtocolException("DIRECTORY_REPARSE_REJECTED", expected);
                string final = FinalPath(handle).TrimEnd('\\');
                string expectedFinal = (@"\\?\" + expected).TrimEnd('\\');
                if (!String.Equals(final, expectedFinal, StringComparison.Ordinal)) throw new R7ProtocolException("FINAL_PATH_MISMATCH", final);
                string owner;
                string sddl;
                ReadSecurity(handle, out owner, out sddl);
                string sddlSha = R7Hash.Bytes(new UTF8Encoding(false, true).GetBytes(sddl));
                string volume = information.VolumeSerialNumber.ToString("x8", CultureInfo.InvariantCulture);
                string[] streams = Streams(final);
                if (streams.Length != 1 || !String.Equals(streams[0], "::$DATA", StringComparison.Ordinal)) throw new R7ProtocolException("DIRECTORY_ALTERNATE_DATA_STREAM_REJECTED");
                if (!String.IsNullOrEmpty(expectedOwnerSid) && !String.Equals(owner, expectedOwnerSid, StringComparison.Ordinal)) throw new R7ProtocolException("OWNER_IDENTITY_MISMATCH");
                if (!String.IsNullOrEmpty(expectedSecurityDescriptorSha256) && !R7Hash.FixedTimeEquals(sddlSha, expectedSecurityDescriptorSha256)) throw new R7ProtocolException("ACL_IDENTITY_MISMATCH");
                if (!String.IsNullOrEmpty(expectedVolumeIdentity) && !String.Equals(volume, expectedVolumeIdentity, StringComparison.Ordinal)) throw new R7ProtocolException("VOLUME_IDENTITY_MISMATCH");
                R7FileMeasurement measurement = new R7FileMeasurement
                {
                    CanonicalPath = expected,
                    FinalNtPath = final,
                    VolumeIdentity = volume,
                    FileIdentity = volume + ":" + information.FileIndexHigh.ToString("x8", CultureInfo.InvariantCulture) + information.FileIndexLow.ToString("x8", CultureInfo.InvariantCulture),
                    OwnerSid = owner,
                    SecurityDescriptorSha256 = sddlSha,
                    LinkCount = information.NumberOfLinks,
                    Size = 0,
                    Sha256 = String.Empty,
                    ShortPath = ShortPath(expected),
                    Streams = streams,
                    CreationTime = FileTimeText(information.CreationTime)
                };
                return new R7VerifiedDirectory(handle, measurement);
            }
            catch { handle.Dispose(); throw; }
        }

        internal static void VerifyDirectoryChain(string directory)
        {
            string full = Path.GetFullPath(directory).TrimEnd(Path.DirectorySeparatorChar);
            string root = Path.GetPathRoot(full).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            List<string> paths = new List<string>();
            string cursor = full;
            while (cursor.Length > root.Length)
            {
                paths.Add(cursor);
                DirectoryInfo parent = Directory.GetParent(cursor);
                if (parent == null) break;
                cursor = parent.FullName.TrimEnd(Path.DirectorySeparatorChar);
            }
            paths.Reverse();
            foreach (string candidate in paths)
            {
                using (SafeFileHandle handle = OpenDirectory(candidate))
                {
                    ByHandleFileInformation information;
                    if (!GetFileInformationByHandle(handle, out information)) ThrowWin32("DIRECTORY_INFORMATION_FAILED");
                    if ((information.FileAttributes & FileAttributeReparsePoint) != 0) throw new R7ProtocolException("DIRECTORY_REPARSE_REJECTED", candidate);
                    string final = FinalPath(handle).TrimEnd('\\');
                    string expected = (@"\\?\" + candidate).TrimEnd('\\');
                    if (!String.Equals(final, expected, StringComparison.Ordinal)) throw new R7ProtocolException("DIRECTORY_FINAL_PATH_MISMATCH", candidate);
                    string longPath = LongPath(candidate).TrimEnd('\\');
                    if (!String.Equals(longPath, candidate.TrimEnd('\\'), StringComparison.Ordinal)) throw new R7ProtocolException("DIRECTORY_ALIAS_REJECTED", candidate);
                }
            }
        }

        private static SafeFileHandle OpenDirectory(string path)
        {
            SafeFileHandle handle = CreateFileW(path, FileReadAttributes | ReadControl, FileShareRead, IntPtr.Zero, OpenExisting, FileFlagBackupSemantics | FileFlagOpenReparsePoint, IntPtr.Zero);
            if (handle.IsInvalid) { int error = Marshal.GetLastWin32Error(); handle.Dispose(); throw new R7ProtocolException("DIRECTORY_SAFE_OPEN_FAILED", path + "|" + error.ToString(CultureInfo.InvariantCulture)); }
            return handle;
        }

        private static bool VerifyExistingDirectoryOrMissing(string path)
        {
            SafeFileHandle handle = CreateFileW(path, FileReadAttributes | ReadControl, FileShareRead, IntPtr.Zero, OpenExisting, FileFlagBackupSemantics | FileFlagOpenReparsePoint, IntPtr.Zero);
            if (handle.IsInvalid)
            {
                int error = Marshal.GetLastWin32Error();
                handle.Dispose();
                if (error == 2 || error == 3) return false;
                throw new R7ProtocolException("DIRECTORY_SAFE_OPEN_FAILED", path + "|" + error.ToString(CultureInfo.InvariantCulture));
            }
            using (handle)
            {
                ByHandleFileInformation information;
                if (!GetFileInformationByHandle(handle, out information)) ThrowWin32("DIRECTORY_INFORMATION_FAILED");
                if ((information.FileAttributes & FileAttributeReparsePoint) != 0) throw new R7ProtocolException("DIRECTORY_REPARSE_REJECTED", path);
                string final = FinalPath(handle).TrimEnd('\\');
                string expected = (@"\\?\" + Path.GetFullPath(path)).TrimEnd('\\');
                if (!String.Equals(final, expected, StringComparison.Ordinal)) throw new R7ProtocolException("DIRECTORY_FINAL_PATH_MISMATCH", path);
                if (!String.Equals(LongPath(path).TrimEnd('\\'), Path.GetFullPath(path).TrimEnd('\\'), StringComparison.Ordinal)) throw new R7ProtocolException("DIRECTORY_ALIAS_REJECTED", path);
                return true;
            }
        }

        private static byte[] ReadAll(SafeFileHandle handle, int size)
        {
            long position;
            if (!SetFilePointerEx(handle, 0, out position, 0)) ThrowWin32("FILE_SEEK_FAILED");
            byte[] bytes = new byte[size];
            int offset = 0;
            while (offset < size)
            {
                int block = Math.Min(1024 * 1024, size - offset);
                byte[] temporary = new byte[block];
                uint read;
                if (!ReadFile(handle, temporary, (uint)block, out read, IntPtr.Zero)) ThrowWin32("FILE_READ_FAILED");
                if (read == 0) throw new R7ProtocolException("PARTIAL_FILE_READ");
                Buffer.BlockCopy(temporary, 0, bytes, offset, (int)read);
                offset += (int)read;
            }
            return bytes;
        }

        private static string FinalPath(SafeFileHandle handle)
        {
            StringBuilder output = new StringBuilder(32768);
            uint length = GetFinalPathNameByHandleW(handle, output, (uint)output.Capacity, 0);
            if (length == 0 || length >= output.Capacity) ThrowWin32("FINAL_PATH_FAILED");
            return output.ToString();
        }

        private static string LongPath(string path)
        {
            StringBuilder output = new StringBuilder(32768);
            uint length = GetLongPathNameW(path, output, (uint)output.Capacity);
            if (length == 0 || length >= output.Capacity) ThrowWin32("LONG_PATH_FAILED");
            return output.ToString();
        }

        private static string ShortPath(string path)
        {
            StringBuilder output = new StringBuilder(32768);
            uint length = GetShortPathNameW(path, output, (uint)output.Capacity);
            if (length == 0)
            {
                int error = Marshal.GetLastWin32Error();
                if (error == 0 || error == 2 || error == 3) return String.Empty;
                throw new R7ProtocolException("SHORT_PATH_QUERY_FAILED", error.ToString(CultureInfo.InvariantCulture));
            }
            if (length >= output.Capacity) throw new R7ProtocolException("SHORT_PATH_TOO_LONG");
            return output.ToString();
        }

        private static string[] Streams(string finalPath)
        {
            List<string> streams = new List<string>();
            Win32FindStreamData data;
            IntPtr find = FindFirstStreamW(finalPath, 0, out data, 0);
            if (find == InvalidFindHandle)
            {
                int error = Marshal.GetLastWin32Error();
                if (error == 38) return new string[] { "::$DATA" };
                throw new R7ProtocolException("STREAM_ENUMERATION_FAILED", error.ToString(CultureInfo.InvariantCulture));
            }
            try
            {
                streams.Add(data.StreamName);
                while (FindNextStreamW(find, out data)) streams.Add(data.StreamName);
                int error = Marshal.GetLastWin32Error();
                if (error != 38) throw new R7ProtocolException("STREAM_ENUMERATION_FAILED", error.ToString(CultureInfo.InvariantCulture));
            }
            finally { FindClose(find); }
            streams.Sort(StringComparer.Ordinal);
            return streams.ToArray();
        }

        private static string[] StreamsByHandle(SafeFileHandle handle)
        {
            const int capacity = 65536;
            IntPtr buffer = Marshal.AllocHGlobal(capacity);
            try
            {
                if (!GetFileInformationByHandleEx(handle, FileStreamInfo, buffer, capacity)) ThrowWin32("STREAM_ENUMERATION_FAILED");
                List<string> streams = new List<string>();
                int offset = 0;
                while (true)
                {
                    if (offset < 0 || offset > capacity - 24) throw new R7ProtocolException("STREAM_INFORMATION_BOUNDS_INVALID");
                    int next = Marshal.ReadInt32(buffer, offset);
                    int nameLength = Marshal.ReadInt32(buffer, offset + 4);
                    if (nameLength < 0 || (nameLength & 1) != 0 || nameLength > capacity - offset - 24) throw new R7ProtocolException("STREAM_NAME_LENGTH_INVALID");
                    string name = Marshal.PtrToStringUni(IntPtr.Add(buffer, offset + 24), nameLength / 2);
                    if (String.IsNullOrEmpty(name)) throw new R7ProtocolException("STREAM_NAME_INVALID");
                    streams.Add(name);
                    if (next == 0) break;
                    if (next < 24 || (next & 7) != 0 || offset > capacity - next) throw new R7ProtocolException("STREAM_INFORMATION_OFFSET_INVALID");
                    offset += next;
                }
                streams.Sort(StringComparer.Ordinal);
                return streams.ToArray();
            }
            finally { Marshal.FreeHGlobal(buffer); }
        }

        private static void ReadSecurity(SafeFileHandle handle, out string ownerSid, out string sddl)
        {
            IntPtr owner;
            IntPtr group;
            IntPtr dacl;
            IntPtr sacl;
            IntPtr descriptor;
            uint information = OwnerSecurityInformation | GroupSecurityInformation | DaclSecurityInformation;
            uint status = GetSecurityInfo(handle.DangerousGetHandle(), SeFileObject, information, out owner, out group, out dacl, out sacl, out descriptor);
            if (status != 0) throw new R7ProtocolException("SECURITY_DESCRIPTOR_FAILED", status.ToString(CultureInfo.InvariantCulture));
            try
            {
                ownerSid = new SecurityIdentifier(owner).Value;
                IntPtr text;
                uint length;
                if (!ConvertSecurityDescriptorToStringSecurityDescriptorW(descriptor, SddlRevision1, information, out text, out length)) ThrowWin32("SDDL_CONVERSION_FAILED");
                try { sddl = Marshal.PtrToStringUni(text); }
                finally { LocalFree(text); }
            }
            finally { LocalFree(descriptor); }
        }

        private static void ThrowWin32(string code)
        {
            int error = Marshal.GetLastWin32Error();
            throw new R7ProtocolException(code, error.ToString(CultureInfo.InvariantCulture) + "|" + new Win32Exception(error).Message);
        }

        private static string FileTimeText(FileTime value)
        {
            long raw = ((long)value.High << 32) | value.Low;
            return DateTime.FromFileTimeUtc(raw).ToString("yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture);
        }
    }
}
