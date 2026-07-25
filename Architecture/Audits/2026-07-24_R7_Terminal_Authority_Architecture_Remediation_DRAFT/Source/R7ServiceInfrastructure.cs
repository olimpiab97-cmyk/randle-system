using Microsoft.Win32.SafeHandles;
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.IO.Pipes;
using System.Runtime.ConstrainedExecution;
using System.Runtime.InteropServices;
using System.Security;
using System.Security.AccessControl;
using System.Security.Principal;
using System.ServiceProcess;
using System.Text;
using System.Threading;

namespace RandleAI.R7Remediation
{
    internal sealed class R7CallerIdentity
    {
        internal string UserSid = String.Empty;
        internal string[] GroupSids = new string[0];
        internal string[] Privileges = new string[0];
        internal long ProcessId;
        internal string ProcessPath = String.Empty;
        internal string ProcessSha256 = String.Empty;
        internal string ProcessFileIdentity = String.Empty;
        internal string ProcessStartTime = String.Empty;
        internal string TokenId = String.Empty;
        internal string AuthenticationId = String.Empty;
        internal string ElevationType = String.Empty;
        internal bool ContainsTerminalSignerSid;

        internal SortedDictionary<string, object> ToJson()
        {
            return R7Json.Object(
                "authentication_id", AuthenticationId,
                "contains_terminal_signer_sid", ContainsTerminalSignerSid,
                "elevation_type", ElevationType,
                "group_sids", GroupSids,
                "privileges", Privileges,
                "process_file_identity", ProcessFileIdentity,
                "process_id", ProcessId,
                "process_path", ProcessPath,
                "process_sha256", ProcessSha256,
                "process_start_time", ProcessStartTime,
                "token_id", TokenId,
                "user_sid", UserSid);
        }
    }

    internal sealed class R7RequestContext
    {
        internal R7CallerIdentity Caller;
        // This delegate exists only while the connected pipe is being processed.
        // It lets the server perform disposition-determinative access probes under
        // the kernel-authenticated client token instead of trusting child claims.
        internal Action<Action> RunAsCaller;
        internal SortedDictionary<string, object> ServerDerivedEvidence = R7Json.Object();
        internal byte[] RequestFrame;
        internal byte[] RequestPayload;
        internal string RequestFrameSha256;
        internal string RequestPayloadSha256;
        internal string ConnectionIdentity;
        internal DateTimeOffset ReceiveTime;
        internal int ConcurrentConnectionCountAtReceive;
        internal string ProtocolErrorCode;
        internal int ProtocolErrorOffset = -1;
    }

    internal abstract class R7PipeProcessor : IDisposable
    {
        internal abstract SortedDictionary<string, object> Process(R7RequestContext context, SortedDictionary<string, object> request);
        internal virtual void ProtocolRejected(R7RequestContext context, R7ProtocolException exception) { }
        public abstract void Dispose();
    }

    internal sealed class R7PipeWindowsService : ServiceBase
    {
        private readonly string pipeName;
        private readonly string[] allowedPipeSids;
        private readonly Func<R7PipeProcessor> processorFactory;
        private readonly string responseInterfaceVersion;
        private volatile bool stopping;
        private Thread serverThread;
        private R7PipeProcessor processor;
        private readonly List<Thread> workers = new List<Thread>();
        private readonly List<NamedPipeServerStream> activePipes = new List<NamedPipeServerStream>();
        private readonly object workerLock = new object();
        private int activeConnections;

        internal R7PipeWindowsService(string serviceName, string fixedPipeName, string[] pipeSids, Func<R7PipeProcessor> factory)
            : this(serviceName, fixedPipeName, pipeSids, factory, R7Fixed.InterfaceVersion)
        {
        }

        internal R7PipeWindowsService(string serviceName, string fixedPipeName, string[] pipeSids, Func<R7PipeProcessor> factory, string fixedResponseInterfaceVersion)
        {
            ServiceName = serviceName;
            CanStop = true;
            CanShutdown = true;
            AutoLog = true;
            pipeName = fixedPipeName;
            allowedPipeSids = pipeSids;
            processorFactory = factory;
            responseInterfaceVersion = fixedResponseInterfaceVersion;
        }

        protected override void OnStart(string[] args)
        {
            processor = processorFactory();
            PipeSecurity security = CreatePipeSecurity(allowedPipeSids);
            stopping = false;
            serverThread = new Thread(delegate() { ServerLoop(security); });
            serverThread.IsBackground = true;
            serverThread.Name = ServiceName + "-accept";
            serverThread.Start();
        }

        protected override void OnStop()
        {
            try { RequestAdditionalTime(30000); } catch (InvalidOperationException) { }
            stopping = true;
            try
            {
                using (NamedPipeClientStream wake = new NamedPipeClientStream(".", pipeName, PipeDirection.Out))
                {
                    wake.Connect(1000);
                    wake.WriteByte(0);
                    wake.Flush();
                }
            }
            catch { }
            if (serverThread != null && !serverThread.Join(5000)) Environment.FailFast("SERVICE_ACCEPT_LOOP_DRAIN_TIMEOUT|" + ServiceName);
            NamedPipeServerStream[] pipeSnapshot;
            lock (workerLock) pipeSnapshot = activePipes.ToArray();
            foreach (NamedPipeServerStream activePipe in pipeSnapshot)
            {
                try { activePipe.Dispose(); } catch { }
            }
            Thread[] snapshot;
            lock (workerLock) snapshot = workers.ToArray();
            DateTime deadline = DateTime.UtcNow.AddSeconds(20);
            foreach (Thread worker in snapshot)
            {
                if (worker == Thread.CurrentThread) continue;
                TimeSpan remaining = deadline - DateTime.UtcNow;
                if (remaining <= TimeSpan.Zero || !worker.Join(remaining)) Environment.FailFast("SERVICE_WORKER_DRAIN_TIMEOUT|" + ServiceName);
            }
            if (processor != null) { processor.Dispose(); processor = null; }
        }

        protected override void OnShutdown() { OnStop(); base.OnShutdown(); }

        private void ServerLoop(PipeSecurity security)
        {
            while (!stopping)
            {
                NamedPipeServerStream pipe = new NamedPipeServerStream(
                    pipeName,
                    PipeDirection.InOut,
                    32,
                    PipeTransmissionMode.Message,
                    PipeOptions.WriteThrough,
                    R7Fixed.MaximumFrameBytes,
                    R7Fixed.MaximumFrameBytes,
                    security);
                try { pipe.WaitForConnection(); }
                catch { pipe.Dispose(); if (stopping) return; throw; }
                if (stopping) { pipe.Dispose(); return; }
                Thread worker = new Thread(delegate() { HandleConnection(pipe); });
                worker.IsBackground = true;
                lock (workerLock) { workers.Add(worker); activePipes.Add(pipe); }
                worker.Start();
            }
        }

        private void HandleConnection(NamedPipeServerStream pipe)
        {
            int observedConnections = Interlocked.Increment(ref activeConnections);
            R7RequestContext context = new R7RequestContext
            {
                ConnectionIdentity = Guid.NewGuid().ToString("D"),
                ReceiveTime = DateTimeOffset.UtcNow,
                ConcurrentConnectionCountAtReceive = observedConnections
            };
            try
            {
                context.Caller = R7NativeCaller.Capture(pipe);
                context.RunAsCaller = delegate(Action action)
                {
                    if (action == null) throw new ArgumentNullException("action");
                    pipe.RunAsClient(delegate() { action(); });
                };
                R7Frame frame = R7Framing.Read(pipe);
                context.RequestFrame = frame.Raw;
                context.RequestPayload = frame.Payload;
                context.RequestFrameSha256 = R7Hash.Bytes(frame.Raw);
                context.RequestPayloadSha256 = R7Hash.Bytes(frame.Payload);
                SortedDictionary<string, object> response = processor.Process(context, frame.Message);
                R7Framing.Write(pipe, response);
            }
            catch (R7ProtocolException exception)
            {
                context.ProtocolErrorCode = exception.Code;
                context.ProtocolErrorOffset = exception.Offset;
                if (exception.RawEvidence != null)
                {
                    context.RequestFrame = exception.RawEvidence;
                    context.RequestFrameSha256 = R7Hash.Bytes(exception.RawEvidence);
                }
                try { processor.ProtocolRejected(context, exception); }
                catch
                {
                    TryWrite(pipe, RejectionFor(responseInterfaceVersion, "PROTOCOL_REJECTION_EVIDENCE_FAILURE"));
                    return;
                }
                TryWrite(pipe, RejectionFor(responseInterfaceVersion, exception.Code));
            }
            catch (R7DurabilityUncertainException exception) { TryWrite(pipe, OutcomeUncertainFor(responseInterfaceVersion, exception.Message)); }
            catch (SecurityException exception) { TryWrite(pipe, RejectionFor(responseInterfaceVersion, exception.Message)); }
            catch (Exception) { TryWrite(pipe, RejectionFor(responseInterfaceVersion, "REQUEST_REJECTED")); }
            finally
            {
                try { pipe.Dispose(); } catch { }
                Interlocked.Decrement(ref activeConnections);
                lock (workerLock) { activePipes.Remove(pipe); workers.Remove(Thread.CurrentThread); }
            }
        }

        internal static SortedDictionary<string, object> Rejection(string code)
        {
            return RejectionFor(R7Fixed.InterfaceVersion, code);
        }

        internal static SortedDictionary<string, object> RejectionFor(string interfaceVersion, string code)
        {
            return R7Json.Object(
                "authority_effect", false,
                "error_code", String.IsNullOrEmpty(code) ? "REQUEST_REJECTED" : code,
                "interface_version", interfaceVersion,
                "protocol_version", R7Fixed.ProtocolVersion,
                "status", "REJECTED");
        }

        internal static SortedDictionary<string, object> Success(string code)
        {
            return R7Json.Object(
                "interface_version", R7Fixed.InterfaceVersion,
                "protocol_version", R7Fixed.ProtocolVersion,
                "result_code", code,
                "status", "COMPLETE");
        }

        internal static SortedDictionary<string, object> Unavailable(string code)
        {
            return R7Json.Object(
                "authority_effect", false,
                "error_code", String.IsNullOrEmpty(code) ? "SERVICE_UNAVAILABLE" : code,
                "interface_version", R7Fixed.InterfaceVersion,
                "protocol_version", R7Fixed.ProtocolVersion,
                "status", "UNAVAILABLE");
        }

        internal static SortedDictionary<string, object> OutcomeUncertain(string code)
        {
            return OutcomeUncertainFor(R7Fixed.InterfaceVersion, code);
        }

        internal static SortedDictionary<string, object> OutcomeUncertainFor(string interfaceVersion, string code)
        {
            return R7Json.Object(
                "authority_effect", "RESOLVE_BY_SAME_REQUEST_IDENTITY",
                "error_code", String.IsNullOrEmpty(code) ? "DURABILITY_OUTCOME_UNCERTAIN" : code,
                "interface_version", interfaceVersion,
                "protocol_version", R7Fixed.ProtocolVersion,
                "status", "OUTCOME_UNCERTAIN");
        }

        private static void TryWrite(Stream pipe, IDictionary<string, object> value)
        {
            try { R7Framing.Write(pipe, value); } catch { }
        }

        private static PipeSecurity CreatePipeSecurity(string[] allowedSids)
        {
            PipeSecurity security = new PipeSecurity();
            security.SetAccessRuleProtection(true, false);
            HashSet<string> unique = new HashSet<string>(allowedSids, StringComparer.Ordinal);
            foreach (string sid in unique)
            {
                PipeAccessRights rights = String.Equals(sid, R7Fixed.SystemSid, StringComparison.Ordinal) ? PipeAccessRights.FullControl : PipeAccessRights.ReadWrite;
                security.AddAccessRule(new PipeAccessRule(new SecurityIdentifier(sid), rights, AccessControlType.Allow));
            }
            return security;
        }
    }

    internal static class R7NativeCaller
    {
        private const uint CreateToolhelpSnapshotProcess = 0x00000002;
        private const uint ProcessQueryLimitedInformation = 0x1000;
        private const uint TokenQuery = 0x0008;
        private const int TokenUser = 1;
        private const int TokenGroups = 2;
        private const int TokenPrivileges = 3;
        private const int TokenStatistics = 10;
        private const int TokenElevationType = 18;
        private const int ErrorInsufficientBuffer = 122;

        [StructLayout(LayoutKind.Sequential)]
        private struct Luid { public uint LowPart; public int HighPart; }

        [StructLayout(LayoutKind.Sequential)]
        private struct LuidAndAttributes { public Luid Luid; public uint Attributes; }

        [StructLayout(LayoutKind.Sequential)]
        private struct SidAndAttributes { public IntPtr Sid; public uint Attributes; }

        [StructLayout(LayoutKind.Sequential)]
        private struct TokenStatisticsData
        {
            public Luid TokenId;
            public Luid AuthenticationId;
            public long ExpirationTime;
            public int TokenType;
            public int ImpersonationLevel;
            public uint DynamicCharged;
            public uint DynamicAvailable;
            public uint GroupCount;
            public uint PrivilegeCount;
            public Luid ModifiedId;
        }

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        private struct ProcessEntry32
        {
            public uint Size;
            public uint Usage;
            public uint ProcessId;
            public IntPtr DefaultHeapId;
            public uint ModuleId;
            public uint ThreadCount;
            public uint ParentProcessId;
            public int BasePriority;
            public uint Flags;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 260)] public string ExeFile;
        }

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool GetNamedPipeClientProcessId(SafePipeHandle pipe, out uint clientProcessId);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern SafeSnapshotHandle CreateToolhelp32Snapshot(uint flags, uint processId);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern bool Process32FirstW(SafeSnapshotHandle snapshot, ref ProcessEntry32 entry);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern bool Process32NextW(SafeSnapshotHandle snapshot, ref ProcessEntry32 entry);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern SafeProcessHandle OpenProcess(uint access, bool inherit, uint processId);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern bool QueryFullProcessImageNameW(SafeProcessHandle process, uint flags, StringBuilder path, ref uint length);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool GetProcessTimes(SafeProcessHandle process, out long creation, out long exit, out long kernel, out long user);

        [DllImport("advapi32.dll", SetLastError = true)]
        private static extern bool OpenProcessToken(SafeProcessHandle process, uint access, out SafeTokenHandle token);

        [DllImport("advapi32.dll", SetLastError = true)]
        private static extern bool GetTokenInformation(SafeTokenHandle token, int tokenInformationClass, IntPtr information, int informationLength, out int returnLength);

        [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern bool LookupPrivilegeNameW(string systemName, ref Luid luid, StringBuilder name, ref int length);

        internal static R7CallerIdentity Capture(NamedPipeServerStream pipe)
        {
            R7CallerIdentity result = new R7CallerIdentity();
            pipe.RunAsClient(delegate()
            {
                using (WindowsIdentity identity = WindowsIdentity.GetCurrent(true))
                {
                    result.UserSid = identity.User == null ? String.Empty : identity.User.Value;
                    List<string> groups = new List<string>();
                    if (identity.Groups != null) foreach (IdentityReference group in identity.Groups) groups.Add(group.Value);
                    groups.Sort(StringComparer.Ordinal);
                    result.GroupSids = groups.ToArray();
                    result.ContainsTerminalSignerSid = String.Equals(result.UserSid, R7Fixed.TerminalSid, StringComparison.Ordinal) || groups.Contains(R7Fixed.TerminalSid);
                }
            });

            uint processId;
            if (!GetNamedPipeClientProcessId(pipe.SafePipeHandle, out processId)) throw new SecurityException("CALLER_PROCESS_ID_UNAVAILABLE");
            result.ProcessId = processId;
            CaptureProcess(processId, result);
            return result;
        }

        internal static R7CallerIdentity CaptureProcess(uint processId, out uint parentProcessId)
        {
            R7CallerIdentity result = new R7CallerIdentity();
            result.ProcessId = processId;
            parentProcessId = ParentProcessId(processId);
            CaptureProcess(processId, result);
            return result;
        }

        internal static uint[] DirectChildProcessIds(uint parentProcessId)
        {
            List<uint> children = new List<uint>();
            using (SafeSnapshotHandle snapshot = CreateToolhelp32Snapshot(CreateToolhelpSnapshotProcess, 0))
            {
                if (snapshot.IsInvalid) throw new SecurityException("PROCESS_SNAPSHOT_UNAVAILABLE");
                ProcessEntry32 entry = new ProcessEntry32();
                entry.Size = (uint)Marshal.SizeOf(typeof(ProcessEntry32));
                if (Process32FirstW(snapshot, ref entry))
                {
                    do
                    {
                        if (entry.ParentProcessId == parentProcessId) children.Add(entry.ProcessId);
                        entry.Size = (uint)Marshal.SizeOf(typeof(ProcessEntry32));
                    }
                    while (Process32NextW(snapshot, ref entry));
                }
            }
            children.Sort();
            return children.ToArray();
        }

        private static uint ParentProcessId(uint processId)
        {
            using (SafeSnapshotHandle snapshot = CreateToolhelp32Snapshot(CreateToolhelpSnapshotProcess, 0))
            {
                if (snapshot.IsInvalid) throw new SecurityException("PROCESS_SNAPSHOT_UNAVAILABLE");
                ProcessEntry32 entry = new ProcessEntry32();
                entry.Size = (uint)Marshal.SizeOf(typeof(ProcessEntry32));
                if (Process32FirstW(snapshot, ref entry))
                {
                    do
                    {
                        if (entry.ProcessId == processId) return entry.ParentProcessId;
                        entry.Size = (uint)Marshal.SizeOf(typeof(ProcessEntry32));
                    }
                    while (Process32NextW(snapshot, ref entry));
                }
            }
            throw new SecurityException("PROCESS_PARENT_UNAVAILABLE");
        }

        private static void CaptureProcess(uint processId, R7CallerIdentity result)
        {
            using (SafeProcessHandle process = OpenProcess(ProcessQueryLimitedInformation, false, processId))
            {
                if (process.IsInvalid) throw new SecurityException("CALLER_PROCESS_UNAVAILABLE");
                StringBuilder path = new StringBuilder(32768);
                uint length = (uint)path.Capacity;
                if (!QueryFullProcessImageNameW(process, 0, path, ref length)) throw new SecurityException("CALLER_IMAGE_UNAVAILABLE");
                result.ProcessPath = path.ToString();
                string fixedRoot = Path.GetDirectoryName(result.ProcessPath);
                using (R7VerifiedFile image = R7SafeFile.Open(result.ProcessPath, result.ProcessPath, fixedRoot, null, null, null, null))
                {
                    result.ProcessSha256 = image.Measurement.Sha256;
                    result.ProcessFileIdentity = image.Measurement.FileIdentity;
                }
                long creation;
                long exit;
                long kernel;
                long user;
                if (GetProcessTimes(process, out creation, out exit, out kernel, out user)) result.ProcessStartTime = DateTime.FromFileTimeUtc(creation).ToString("yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture);
                SafeTokenHandle token;
                if (!OpenProcessToken(process, TokenQuery, out token)) throw new SecurityException("CALLER_TOKEN_UNAVAILABLE");
                using (token) CaptureToken(token, result);
            }
        }

        private static void CaptureToken(SafeTokenHandle token, R7CallerIdentity result)
        {
            SidAndAttributes tokenUser = ReadStruct<SidAndAttributes>(token, TokenUser);
            string processUserSid = new SecurityIdentifier(tokenUser.Sid).Value;
            if (String.IsNullOrEmpty(result.UserSid)) result.UserSid = processUserSid;
            else if (!String.Equals(processUserSid, result.UserSid, StringComparison.Ordinal)) throw new SecurityException("PIPE_AND_PROCESS_TOKEN_USER_MISMATCH");
            TokenStatisticsData statistics = ReadStruct<TokenStatisticsData>(token, TokenStatistics);
            result.TokenId = LuidText(statistics.TokenId);
            result.AuthenticationId = LuidText(statistics.AuthenticationId);
            int elevation = ReadStruct<int>(token, TokenElevationType);
            result.ElevationType = elevation.ToString(CultureInfo.InvariantCulture);

            IntPtr buffer;
            int length;
            ReadBuffer(token, TokenPrivileges, out buffer, out length);
            try
            {
                int count = Marshal.ReadInt32(buffer);
                int offset = sizeof(uint);
                int size = Marshal.SizeOf(typeof(LuidAndAttributes));
                List<string> privileges = new List<string>();
                for (int i = 0; i < count; i++)
                {
                    LuidAndAttributes item = (LuidAndAttributes)Marshal.PtrToStructure(IntPtr.Add(buffer, offset + i * size), typeof(LuidAndAttributes));
                    StringBuilder name = new StringBuilder(256);
                    int nameLength = name.Capacity;
                    Luid luid = item.Luid;
                    if (LookupPrivilegeNameW(null, ref luid, name, ref nameLength)) privileges.Add(name.ToString() + ":" + item.Attributes.ToString("x8", CultureInfo.InvariantCulture));
                    else privileges.Add(LuidText(luid) + ":" + item.Attributes.ToString("x8", CultureInfo.InvariantCulture));
                }
                privileges.Sort(StringComparer.Ordinal);
                result.Privileges = privileges.ToArray();
            }
            finally { Marshal.FreeHGlobal(buffer); }

            ReadBuffer(token, TokenGroups, out buffer, out length);
            try
            {
                int count = Marshal.ReadInt32(buffer);
                int offset = IntPtr.Size == 8 ? 8 : 4;
                int size = Marshal.SizeOf(typeof(SidAndAttributes));
                List<string> groups = new List<string>();
                for (int i = 0; i < count; i++)
                {
                    SidAndAttributes item = (SidAndAttributes)Marshal.PtrToStructure(IntPtr.Add(buffer, offset + i * size), typeof(SidAndAttributes));
                    groups.Add(new SecurityIdentifier(item.Sid).Value);
                }
                groups.Sort(StringComparer.Ordinal);
                result.GroupSids = groups.ToArray();
                result.ContainsTerminalSignerSid = String.Equals(result.UserSid, R7Fixed.TerminalSid, StringComparison.Ordinal) || groups.Contains(R7Fixed.TerminalSid);
            }
            finally { Marshal.FreeHGlobal(buffer); }
        }

        private static T ReadStruct<T>(SafeTokenHandle token, int informationClass) where T : struct
        {
            IntPtr buffer;
            int length;
            ReadBuffer(token, informationClass, out buffer, out length);
            try { return (T)Marshal.PtrToStructure(buffer, typeof(T)); }
            finally { Marshal.FreeHGlobal(buffer); }
        }

        private static void ReadBuffer(SafeTokenHandle token, int informationClass, out IntPtr buffer, out int length)
        {
            length = 0;
            GetTokenInformation(token, informationClass, IntPtr.Zero, 0, out length);
            if (length <= 0 || Marshal.GetLastWin32Error() != ErrorInsufficientBuffer) throw new SecurityException("TOKEN_INFORMATION_SIZE_UNAVAILABLE");
            buffer = Marshal.AllocHGlobal(length);
            if (!GetTokenInformation(token, informationClass, buffer, length, out length))
            {
                Marshal.FreeHGlobal(buffer);
                throw new SecurityException("TOKEN_INFORMATION_UNAVAILABLE");
            }
        }

        private static string LuidText(Luid value)
        {
            return value.HighPart.ToString("x8", CultureInfo.InvariantCulture) + value.LowPart.ToString("x8", CultureInfo.InvariantCulture);
        }
    }

    internal sealed class SafeTokenHandle : SafeHandleZeroOrMinusOneIsInvalid
    {
        private SafeTokenHandle() : base(true) { }
        [DllImport("kernel32.dll", SetLastError = true)] private static extern bool CloseHandle(IntPtr handle);
        protected override bool ReleaseHandle() { return CloseHandle(handle); }
    }

    internal sealed class SafeSnapshotHandle : SafeHandleZeroOrMinusOneIsInvalid
    {
        private SafeSnapshotHandle() : base(true) { }
        [DllImport("kernel32.dll", SetLastError = true)] private static extern bool CloseHandle(IntPtr handle);
        protected override bool ReleaseHandle() { return CloseHandle(handle); }
    }
}
