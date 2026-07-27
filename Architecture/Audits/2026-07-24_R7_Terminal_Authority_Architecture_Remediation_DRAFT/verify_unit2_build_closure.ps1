[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$SourceCommit,
    [Parameter(Mandatory=$true)][string]$BuildRoot,
    [Parameter(Mandatory=$true)][string]$OutputPath,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedScriptSha256,
    [switch]$CandidateWorktree
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$packageRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $packageRoot '..\..\..'))
$packageRelativeRoot = 'Architecture/Audits/2026-07-24_R7_Terminal_Authority_Architecture_Remediation_DRAFT'
$build = [IO.Path]::GetFullPath($BuildRoot)
$output = [IO.Path]::GetFullPath($OutputPath)
$receiptPath = Join-Path $build 'Generated\unit2_build_receipt.json'
$determinismPath = Join-Path $build 'Generated\unit2_build_determinism_receipt.json'
$manifestPath = Join-Path $build 'unit2_build_manifest.json'
$negativePath = Join-Path $packageRoot 'unit2_build_closure_negative_cases.json'
$contractPath = Join-Path $packageRoot 'BuildInputs\R7BuildIdentityContract.cs'
$requiredSwitches = @('/nologo','/noconfig','/target:exe','/platform:x64','/optimize+','/checked+','/debug-','/warn:4','/warnaserror+','/nostdlib+','/langversion:5','/filealign:512')
$requiredRoles = @('BUILD_BOOTSTRAP_ARTIFACT_TOOL','BUILD_BOOTSTRAP_PROTECTED_METADATA_TOOL','PACKAGED_ARTIFACT_TOOL','PACKAGED_PROTECTED_METADATA_TOOL','UPGRADE_AUTHORITY','UPGRADE_CLIENT','UPGRADE_PROTOCOL_PROBE','UPGRADE_PUBLIC_VERIFIER')

function Hash([string]$Path) { return (Get-FileHash -LiteralPath ([IO.Path]::GetFullPath($Path)) -Algorithm SHA256).Hash.ToLowerInvariant() }
function BytesHash([byte[]]$Bytes) {
    $sha=[Security.Cryptography.SHA256]::Create()
    try{return ([BitConverter]::ToString($sha.ComputeHash($Bytes))).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()}
}
function TextHash([string]$Value){return BytesHash ([Text.UTF8Encoding]::new($false).GetBytes($Value))}
function CrLfFixtureBytes([byte[]]$Bytes) {
    $stream=[IO.MemoryStream]::new();try{for($index=0;$index-lt$Bytes.Length;$index++){if($Bytes[$index]-eq10-and($index-eq0-or$Bytes[$index-1]-ne13)){$stream.WriteByte(13)};$stream.WriteByte($Bytes[$index])};return $stream.ToArray()}finally{$stream.Dispose()}
}
function UntrustedFixtureBlobIdentity([byte[]]$Bytes) {
    $header=[Text.Encoding]::ASCII.GetBytes(('blob '+$Bytes.Length+[char]0));$all=New-Object byte[] ($header.Length+$Bytes.Length);[Buffer]::BlockCopy($header,0,$all,0,$header.Length);[Buffer]::BlockCopy($Bytes,0,$all,$header.Length,$Bytes.Length);$sha=[Security.Cryptography.SHA1]::Create();try{return ([BitConverter]::ToString($sha.ComputeHash($all))).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()}
}
function ReadJson([string]$Path) { return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json }
function Clone([object]$Value) { return ($Value | ConvertTo-Json -Depth 100 | ConvertFrom-Json) }
function Relative([string]$Base,[string]$Path) {
    $baseFull = [IO.Path]::GetFullPath($Base).TrimEnd('\') + '\'
    return [Uri]::UnescapeDataString(([Uri]$baseFull).MakeRelativeUri([Uri][IO.Path]::GetFullPath($Path)).ToString()).Replace('\','/')
}
function GitArgs([string[]]$Arguments) {
    $safe=$repositoryRoot.Replace('\','/');$result=@(& $git --no-pager -c "safe.directory=$safe" -c core.fsmonitor=false -c core.hooksPath=NUL -C $repositoryRoot @Arguments)
    if($LASTEXITCODE-ne0){Fail 'GIT_OBJECT_AUTHORITY_FAILURE' ($Arguments-join' ')}
    return $result
}
function GitBlobIdentity([byte[]]$Bytes) {
    $lengthText=$Bytes.Length.ToString([Globalization.CultureInfo]::InvariantCulture)
    $prefix=[Text.Encoding]::ASCII.GetBytes(('blob '+$lengthText+[char]0))
    $sha=[Security.Cryptography.SHA1]::Create()
    try{
        $stream=[IO.MemoryStream]::new()
        try{$stream.Write($prefix,0,$prefix.Length);$stream.Write($Bytes,0,$Bytes.Length);$stream.Position=0;return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-','').ToLowerInvariant()}finally{$stream.Dispose()}
    }finally{$sha.Dispose()}
}
function InitializeGitBatchProcessRuntime {
    if('R7GitBatchProcessRunner'-as[type]){return}
    Add-Type -Language CSharp -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Win32.SafeHandles;

public sealed class R7GitExpectedObject {
    public string Oid;
    public string Path;
    public long Size;
}
public sealed class R7GitAuthenticatedObject {
    public byte[] Bytes;
    public string ComputedOid;
    public string Path;
    public long Size;
}
public sealed class R7GitProcessResult {
    public R7GitAuthenticatedObject[] Objects;
    public int ParentPid;
    public int[] ObservedProcessIds;
    public long AggregateBudget;
    public long ObservedStdoutBytes;
    public long MaximumPayloadBytes;
    public int MaximumRetainedStderrBytes;
    public long ElapsedMilliseconds;
    public long CleanupMilliseconds;
    public bool StdoutCompleted;
    public bool StderrCompleted;
    public bool InputCompleted;
    public bool ProcessExited;
    public bool ProcessTreeTerminated;
    public int ThreadId;
    public bool JobAtCreationContained;
    public bool ChildExecuted;
    public string InputTaskState;
    public string StdoutTaskState;
    public string StderrTaskState;
}
public sealed class R7GitResourceCounters {
    public long AttributeAllocations,AttributeFrees,AttributeInitializations,AttributeDeletes;
    public long HandleListAllocations,HandleListFrees,JobListAllocations,JobListFrees,EnvironmentAllocations,EnvironmentFrees;
}
public static class R7GitBatchProcessRunner {
    const uint CREATE_SUSPENDED=0x00000004, CREATE_UNICODE_ENVIRONMENT=0x00000400, EXTENDED_STARTUPINFO_PRESENT=0x00080000, CREATE_NO_WINDOW=0x08000000, STARTF_USESTDHANDLES=0x00000100;
    const uint HANDLE_FLAG_INHERIT=0x00000001, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE=0x00002000;
    const uint WAIT_OBJECT_0=0, WAIT_TIMEOUT=258, WAIT_FAILED=0xffffffff, STILL_ACTIVE=259;
    const int JobObjectBasicAccountingInformation=1, JobObjectExtendedLimitInformation=9;
    const long MaximumObjectBytes=67108864L, MaximumAggregateBytes=268435456L;
    static readonly IntPtr PROC_THREAD_ATTRIBUTE_HANDLE_LIST=new IntPtr(0x00020002);
    static readonly IntPtr PROC_THREAD_ATTRIBUTE_JOB_LIST=new IntPtr(0x0002000d);
    static readonly object ConcurrentTestLock=new object();static Barrier ConcurrentLaunchBarrier;
    static long AttributeAllocations,AttributeFrees,AttributeInitializations,AttributeDeletes,HandleListAllocations,HandleListFrees,JobListAllocations,JobListFrees,EnvironmentAllocations,EnvironmentFrees;

    sealed class TaskObservation {
        public readonly string State;public readonly bool Created,CompletionMeasured,Canceled;public readonly string FaultType,Phase;public readonly long ElapsedMilliseconds;
        public TaskObservation(string state,bool created,bool completionMeasured,bool canceled,string faultType,string phase,long elapsed){State=state;Created=created;CompletionMeasured=completionMeasured;Canceled=canceled;FaultType=faultType;Phase=phase;ElapsedMilliseconds=elapsed;}
        public bool IsTerminal { get { return State!="Running"; } }
        public bool IsSuccessful { get { return State=="Completed"; } }
    }
    sealed class CleanupSnapshot {
        public readonly bool ParentSignaled,ZeroProcessAuthority,Unknown,PrimaryEligible,DiagnosticOnly,ExternalPidsAbsent,TerminalReturnCriteria;public readonly string JobQueryStatus;public readonly uint ActiveProcesses;public readonly TaskObservation Input,Stdout,Stderr;public readonly long ElapsedMilliseconds,RemainingMilliseconds,ObservationStartedMilliseconds,ObservationCompletedMilliseconds,ObservationDeadlineMilliseconds;
        public CleanupSnapshot(bool parent,string query,uint active,TaskObservation input,TaskObservation stdout,TaskObservation stderr,long elapsed,long remaining,long observationStarted,long observationCompleted,long observationDeadline,bool eligible,bool diagnosticOnly,bool externalPidsAbsent,bool terminalReturn){ParentSignaled=parent;JobQueryStatus=query;ActiveProcesses=active;Input=input;Stdout=stdout;Stderr=stderr;ElapsedMilliseconds=elapsed;RemainingMilliseconds=remaining;ObservationStartedMilliseconds=observationStarted;ObservationCompletedMilliseconds=observationCompleted;ObservationDeadlineMilliseconds=observationDeadline;PrimaryEligible=eligible;DiagnosticOnly=diagnosticOnly;ExternalPidsAbsent=externalPidsAbsent;TerminalReturnCriteria=terminalReturn;ZeroProcessAuthority=parent&&query=="Succeeded"&&active==0;Unknown=query!="Succeeded"||!parent||!input.IsTerminal||!stdout.IsTerminal||!stderr.IsTerminal;}
        public bool CleanupTerminal { get { return ZeroProcessAuthority&&Input.IsTerminal&&Stdout.IsTerminal&&Stderr.IsTerminal; } }
    }

    [StructLayout(LayoutKind.Sequential)] struct SECURITY_ATTRIBUTES { public int nLength; public IntPtr lpSecurityDescriptor; [MarshalAs(UnmanagedType.Bool)] public bool bInheritHandle; }
    [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] struct STARTUPINFO { public int cb; public string lpReserved; public string lpDesktop; public string lpTitle; public int dwX; public int dwY; public int dwXSize; public int dwYSize; public int dwXCountChars; public int dwYCountChars; public int dwFillAttribute; public uint dwFlags; public short wShowWindow; public short cbReserved2; public IntPtr lpReserved2; public IntPtr hStdInput; public IntPtr hStdOutput; public IntPtr hStdError; }
    [StructLayout(LayoutKind.Sequential)] struct STARTUPINFOEX { public STARTUPINFO StartupInfo; public IntPtr lpAttributeList; }
    [StructLayout(LayoutKind.Sequential)] struct PROCESS_INFORMATION { public IntPtr hProcess; public IntPtr hThread; public int dwProcessId; public int dwThreadId; }
    [StructLayout(LayoutKind.Sequential)] struct IO_COUNTERS { public ulong ReadOperationCount,WriteOperationCount,OtherOperationCount,ReadTransferCount,WriteTransferCount,OtherTransferCount; }
    [StructLayout(LayoutKind.Sequential)] struct JOBOBJECT_BASIC_LIMIT_INFORMATION { public long PerProcessUserTimeLimit,PerJobUserTimeLimit; public uint LimitFlags; public UIntPtr MinimumWorkingSetSize,MaximumWorkingSetSize; public uint ActiveProcessLimit; public UIntPtr Affinity; public uint PriorityClass,SchedulingClass; }
    [StructLayout(LayoutKind.Sequential)] struct JOBOBJECT_EXTENDED_LIMIT_INFORMATION { public JOBOBJECT_BASIC_LIMIT_INFORMATION BasicLimitInformation; public IO_COUNTERS IoInfo; public UIntPtr ProcessMemoryLimit,JobMemoryLimit,PeakProcessMemoryUsed,PeakJobMemoryUsed; }
    [StructLayout(LayoutKind.Sequential)] struct JOBOBJECT_BASIC_ACCOUNTING_INFORMATION { public long TotalUserTime,TotalKernelTime,ThisPeriodTotalUserTime,ThisPeriodTotalKernelTime; public uint TotalPageFaultCount,TotalProcesses,ActiveProcesses,TotalTerminatedProcesses; }

    [DllImport("kernel32.dll",SetLastError=true)] static extern bool CreatePipe(out IntPtr read,out IntPtr write,ref SECURITY_ATTRIBUTES sa,int size);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool SetHandleInformation(IntPtr handle,uint mask,uint flags);
    [DllImport("kernel32.dll",SetLastError=true,CharSet=CharSet.Unicode)] static extern bool CreateProcessW(string app,StringBuilder command,IntPtr processAttributes,IntPtr threadAttributes,bool inherit,uint flags,IntPtr environment,string currentDirectory,ref STARTUPINFOEX startup,out PROCESS_INFORMATION process);
    [DllImport("kernel32.dll",SetLastError=true)] static extern IntPtr CreateJobObject(IntPtr attributes,string name);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool SetInformationJobObject(IntPtr job,int infoClass,IntPtr info,int length);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool TerminateJobObject(IntPtr job,uint exitCode);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool QueryInformationJobObject(IntPtr job,int infoClass,IntPtr info,int length,out int returnedLength);
    [DllImport("kernel32.dll",SetLastError=true)] static extern uint ResumeThread(IntPtr thread);
    [DllImport("kernel32.dll",SetLastError=true)] static extern uint SuspendThread(IntPtr thread);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool TerminateProcess(IntPtr process,uint exitCode);
    [DllImport("kernel32.dll",SetLastError=true)] static extern uint WaitForSingleObject(IntPtr handle,uint milliseconds);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool GetExitCodeProcess(IntPtr process,out uint exitCode);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool GetHandleInformation(IntPtr handle,out uint flags);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool CloseHandle(IntPtr handle);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool InitializeProcThreadAttributeList(IntPtr list,int count,int flags,ref UIntPtr size);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool UpdateProcThreadAttribute(IntPtr list,uint flags,IntPtr attribute,IntPtr value,UIntPtr size,IntPtr previous,IntPtr returned);
    [DllImport("kernel32.dll")] static extern void DeleteProcThreadAttributeList(IntPtr list);

    static void Fail(string code,string detail){throw new InvalidDataException(code+"|"+detail);}
    static void Native(string operation){Fail("GIT_BATCH_PROCESS_FAILURE","operation="+operation+";win32="+Marshal.GetLastWin32Error().ToString(CultureInfo.InvariantCulture));}
    static string Quote(string value){return "\""+value.Replace("\"","\\\"")+"\"";}
    static string Oid(byte[] payload){
        byte[] prefix=Encoding.ASCII.GetBytes("blob "+payload.LongLength.ToString(CultureInfo.InvariantCulture)+"\0");
        using(SHA1 sha=SHA1.Create()){
            sha.TransformBlock(prefix,0,prefix.Length,null,0);
            if(payload.Length!=0)sha.TransformBlock(payload,0,payload.Length,null,0);
            sha.TransformFinalBlock(new byte[0],0,0);
            return BitConverter.ToString(sha.Hash).Replace("-","").ToLowerInvariant();
        }
    }
    static long Budget(R7GitExpectedObject[] expected){
        long total=0;
        try{checked{foreach(R7GitExpectedObject row in expected){if(row==null||row.Size<0||row.Size>MaximumObjectBytes)Fail("GIT_BATCH_DECLARED_SIZE_INVALID","context=request;size="+(row==null?"<null>":row.Size.ToString(CultureInfo.InvariantCulture)));string size=row.Size.ToString(CultureInfo.InvariantCulture);total+=40+1+4+1+size.Length+1;total+=row.Size;total+=1;if(total>MaximumAggregateBytes)Fail("GIT_BATCH_AGGREGATE_OUTPUT_OVERFLOW","context=request-budget;observed="+total.ToString(CultureInfo.InvariantCulture)+";limit="+MaximumAggregateBytes.ToString(CultureInfo.InvariantCulture));}}}
        catch(OverflowException){Fail("GIT_BATCH_AGGREGATE_OUTPUT_OVERFLOW","context=request-budget");}
        return total;
    }
    static int ReadByte(Stream stream,ref long observed,long budget){int value=stream.ReadByte();if(value>=0){observed++;if(observed>budget)Fail("GIT_BATCH_AGGREGATE_OUTPUT_EXCEEDED","observed="+observed.ToString(CultureInfo.InvariantCulture)+";budget="+budget.ToString(CultureInfo.InvariantCulture));}return value;}
    static Tuple<string,long> Header(Stream stream,int index,R7GitExpectedObject expected,ref long observed,long budget){
        List<byte> bytes=new List<byte>(96);
        while(true){int value=stream.ReadByte();if(value>=0)observed++;if(value<0)Fail("GIT_BATCH_HEADER_INVALID","index="+index+";requested="+expected.Oid+";reason="+(bytes.Count==0?"missing-header":"partial-header"));if(value==10)break;if(value==13||value==0||value>127)Fail("GIT_BATCH_HEADER_INVALID","index="+index+";requested="+expected.Oid+";reason=forbidden-header-byte;byte="+value);if(bytes.Count>=128)Fail("GIT_BATCH_HEADER_INVALID","index="+index+";requested="+expected.Oid+";reason=header-too-long");bytes.Add((byte)value);}
        string header=Encoding.ASCII.GetString(bytes.ToArray());string[] fields=header.Split(' ');if(fields.Length!=3||fields[0].Length!=40||!LowerHex(fields[0])||fields[2].Length==0||(fields[2].Length>1&&fields[2][0]=='0'))Fail("GIT_BATCH_HEADER_INVALID","index="+index+";requested="+expected.Oid+";reason=grammar");if(fields[1]!="blob")Fail("GIT_BATCH_OBJECT_TYPE_MISMATCH","index="+index+";requested="+expected.Oid+";observed="+fields[0]+";type="+fields[1]);ulong size; if(!UInt64.TryParse(fields[2],NumberStyles.None,CultureInfo.InvariantCulture,out size)||size>MaximumObjectBytes)Fail("GIT_BATCH_DECLARED_SIZE_INVALID","index="+index+";requested="+expected.Oid+";observed="+fields[0]+";size="+fields[2]);if(fields[0]!=expected.Oid)Fail("GIT_BATCH_OBJECT_ORDER_MISMATCH","index="+index+";requested="+expected.Oid+";observed="+fields[0]);if((long)size!=expected.Size)Fail("GIT_BATCH_EXPECTED_SIZE_MISMATCH","index="+index+";requested="+expected.Oid+";expected="+expected.Size.ToString(CultureInfo.InvariantCulture)+";observed="+size.ToString(CultureInfo.InvariantCulture));if(observed>budget)Fail("GIT_BATCH_AGGREGATE_OUTPUT_EXCEEDED","observed="+observed.ToString(CultureInfo.InvariantCulture)+";budget="+budget.ToString(CultureInfo.InvariantCulture));return Tuple.Create(fields[0],(long)size);
    }
    static bool LowerHex(string value){for(int i=0;i<value.Length;i++){char c=value[i];if(!((c>='0'&&c<='9')||(c>='a'&&c<='f')))return false;}return true;}
    static R7GitAuthenticatedObject[] Parse(Stream stream,R7GitExpectedObject[] expected,long budget,Action<long> observedSetter){
        List<R7GitAuthenticatedObject> rows=new List<R7GitAuthenticatedObject>();long observed=0;
        for(int index=0;index<expected.Length;index++){R7GitExpectedObject want=expected[index];if(want.Oid==null||want.Oid.Length!=40||!LowerHex(want.Oid))Fail("GIT_BATCH_OBJECT_ORDER_MISMATCH","index="+index+";reason=invalid-request-oid");Tuple<string,long> header=Header(stream,index,want,ref observed,budget);int size=checked((int)header.Item2);byte[] payload=new byte[size];int offset=0;while(offset<size){int take=Math.Min(65536,size-offset);int read=stream.Read(payload,offset,take);if(read<=0)Fail("GIT_BATCH_PAYLOAD_TRUNCATED","index="+index+";requested="+want.Oid+";declared="+size+";actual="+offset);offset+=read;observed+=read;if(observed>budget)Fail("GIT_BATCH_AGGREGATE_OUTPUT_EXCEEDED","observed="+observed+";budget="+budget);}int delimiter=ReadByte(stream,ref observed,budget);if(delimiter!=10)Fail("GIT_BATCH_PAYLOAD_DELIMITER_INVALID","index="+index+";requested="+want.Oid+";observed="+delimiter);string computed=Oid(payload);if(computed!=header.Item1||computed!=want.Oid)Fail("GIT_BATCH_BLOB_IDENTITY_MISMATCH","index="+index+";requested="+want.Oid+";observed="+header.Item1+";computed="+computed);rows.Add(new R7GitAuthenticatedObject{Bytes=payload,ComputedOid=computed,Path=want.Path,Size=payload.LongLength});}
        int trailing=stream.ReadByte();if(trailing!=-1)Fail("GIT_BATCH_TRAILING_OUTPUT","index="+expected.Length+";observed_byte="+trailing);observedSetter(observed);return rows.ToArray();
    }
    sealed class StderrState { public byte[] Bytes; public long Total; }
    static StderrState DrainStderr(Stream stream,int limit){using(MemoryStream kept=new MemoryStream(Math.Min(limit,4096))){byte[] buffer=new byte[4096];long total=0;while(true){int read=stream.Read(buffer,0,buffer.Length);if(read<=0)break;total+=read;if(total>limit)Fail("GIT_BATCH_STDERR_LIMIT_EXCEEDED","limit="+limit.ToString(CultureInfo.InvariantCulture)+";observed="+total.ToString(CultureInfo.InvariantCulture));kept.Write(buffer,0,read);}return new StderrState{Bytes=kept.ToArray(),Total=total};}}
    static bool TryActive(IntPtr job,bool injectFailure,out uint active,out int error){
        int size=Marshal.SizeOf(typeof(JOBOBJECT_BASIC_ACCOUNTING_INFORMATION));IntPtr ptr=Marshal.AllocHGlobal(size);
        try{
            int returned;IntPtr queried=injectFailure?IntPtr.Zero:job;
            bool ok=QueryInformationJobObject(queried,JobObjectBasicAccountingInformation,ptr,size,out returned);error=ok?0:Marshal.GetLastWin32Error();
            if(!ok){active=UInt32.MaxValue;return false;}
            active=((JOBOBJECT_BASIC_ACCOUNTING_INFORMATION)Marshal.PtrToStructure(ptr,typeof(JOBOBJECT_BASIC_ACCOUNTING_INFORMATION))).ActiveProcesses;return true;
        }finally{Marshal.FreeHGlobal(ptr);}
    }
    static uint Active(IntPtr job){uint active;int error;if(!TryActive(job,false,out active,out error))Fail("GIT_BATCH_PROCESS_FAILURE","operation=QueryInformationJobObject;win32="+error.ToString(CultureInfo.InvariantCulture));return active;}
    static Exception Failure(Task task){if(task==null||!task.IsFaulted)return null;AggregateException aggregate=task.Exception.Flatten();return aggregate.InnerExceptions.Count==0?aggregate:aggregate.InnerExceptions[0];}
    static TaskObservation ObserveTask(Task task,Stopwatch clock,string phase){
        if(task==null)return new TaskObservation("NotStarted",false,false,false,"<none>",phase,clock.ElapsedMilliseconds);
        if(task.IsCanceled)return new TaskObservation("Canceled",true,true,true,"<none>",phase,clock.ElapsedMilliseconds);
        if(task.IsFaulted){Exception failure=Failure(task);return new TaskObservation("Faulted",true,true,false,failure==null?"<unknown>":failure.GetType().Name,phase,clock.ElapsedMilliseconds);}
        if(task.Status==TaskStatus.RanToCompletion)return new TaskObservation("Completed",true,true,false,"<none>",phase,clock.ElapsedMilliseconds);
        return new TaskObservation("Running",true,false,false,"<none>",phase,clock.ElapsedMilliseconds);
    }
    static CleanupSnapshot CaptureSnapshot(IntPtr process,IntPtr job,Stopwatch clock,int totalDeadline,int observationDeadline,Task inputTask,Task stdoutTask,Task stderrTask,string phase,long phaseStart,bool diagnosticOnly,bool injectWaitFailure,bool injectQueryFailure,out int waitError,out int queryError){
        long observationStarted=clock.ElapsedMilliseconds;
        bool parent=false;waitError=0;uint wait=WaitForSingleObject(injectWaitFailure?IntPtr.Zero:process,0);if(wait==WAIT_OBJECT_0)parent=true;else if(wait==WAIT_FAILED)waitError=Marshal.GetLastWin32Error();
        uint active=UInt32.MaxValue;int observedError;bool queryOk=TryActive(job,injectQueryFailure,out active,out observedError);queryError=queryOk?0:observedError;string query=queryOk?"Succeeded":"Failed";
        TaskObservation input=ObserveTask(inputTask,clock,phase),stdout=ObserveTask(stdoutTask,clock,phase),stderr=ObserveTask(stderrTask,clock,phase);long completed=clock.ElapsedMilliseconds;bool zero=parent&&query=="Succeeded"&&active==0;bool unknown=query!="Succeeded"||!parent||!input.IsTerminal||!stdout.IsTerminal||!stderr.IsTerminal;bool terminal=zero&&input.IsTerminal&&stdout.IsTerminal&&stderr.IsTerminal;bool eligible=!diagnosticOnly&&completed<=observationDeadline&&terminal&&!unknown&&waitError==0&&queryError==0;
        return new CleanupSnapshot(parent,query,active,input,stdout,stderr,Math.Max(0,completed-phaseStart),Math.Max(0,totalDeadline-completed),observationStarted,completed,observationDeadline,eligible,diagnosticOnly,false,false);
    }
    static CleanupSnapshot UnmeasuredSnapshot(Stopwatch clock,int totalDeadline,int observationDeadline,Task inputTask,Task stdoutTask,Task stderrTask,string phase,long phaseStart,bool diagnosticOnly){long observed=clock.ElapsedMilliseconds;return new CleanupSnapshot(false,"NotAttempted",UInt32.MaxValue,ObserveTask(inputTask,clock,phase),ObserveTask(stdoutTask,clock,phase),ObserveTask(stderrTask,clock,phase),Math.Max(0,observed-phaseStart),Math.Max(0,totalDeadline-observed),observed,observed,observationDeadline,false,diagnosticOnly,false,false);}
    static CleanupSnapshot AsDiagnostic(CleanupSnapshot source){return new CleanupSnapshot(source.ParentSignaled,source.JobQueryStatus,source.ActiveProcesses,source.Input,source.Stdout,source.Stderr,source.ElapsedMilliseconds,source.RemainingMilliseconds,source.ObservationStartedMilliseconds,source.ObservationCompletedMilliseconds,source.ObservationDeadlineMilliseconds,false,true,source.ExternalPidsAbsent,false);}
    static CleanupSnapshot WithExternalDisposition(CleanupSnapshot source,Stopwatch clock,int totalDeadline,bool absent){long completed=clock.ElapsedMilliseconds;bool terminal=source.CleanupTerminal&&source.Input.IsTerminal&&source.Stdout.IsTerminal&&source.Stderr.IsTerminal&&absent;return new CleanupSnapshot(source.ParentSignaled,source.JobQueryStatus,source.ActiveProcesses,source.Input,source.Stdout,source.Stderr,source.ElapsedMilliseconds,Math.Max(0,totalDeadline-completed),source.ObservationStartedMilliseconds,completed,totalDeadline,source.PrimaryEligible,source.DiagnosticOnly,absent,terminal&&completed<=totalDeadline);}
    static string TaskDetail(string prefix,TaskObservation task){return prefix+"_state="+task.State+";"+prefix+"_created="+task.Created+";"+prefix+"_completion_measured="+task.CompletionMeasured+";"+prefix+"_fault="+task.FaultType+";"+prefix+"_canceled="+task.Canceled+";"+prefix+"_observed_ms="+task.ElapsedMilliseconds.ToString(CultureInfo.InvariantCulture)+";"+prefix+"_phase="+task.Phase;}
    static string SnapshotDetail(string prefix,CleanupSnapshot snapshot){return prefix+"_parent_signaled="+snapshot.ParentSignaled+";"+prefix+"_job_query="+snapshot.JobQueryStatus+";"+prefix+"_active="+(snapshot.JobQueryStatus=="Succeeded"?snapshot.ActiveProcesses.ToString(CultureInfo.InvariantCulture):"<unknown>")+";"+prefix+"_zero_authority="+snapshot.ZeroProcessAuthority+";"+prefix+"_unknown="+snapshot.Unknown+";"+prefix+"_eligible="+snapshot.PrimaryEligible+";"+prefix+"_diagnostic_only="+snapshot.DiagnosticOnly+";"+prefix+"_external_pids_absent="+snapshot.ExternalPidsAbsent+";"+prefix+"_terminal_return="+snapshot.TerminalReturnCriteria+";"+prefix+"_observation_start_ms="+snapshot.ObservationStartedMilliseconds.ToString(CultureInfo.InvariantCulture)+";"+prefix+"_observation_complete_ms="+snapshot.ObservationCompletedMilliseconds.ToString(CultureInfo.InvariantCulture)+";"+prefix+"_observation_deadline_ms="+snapshot.ObservationDeadlineMilliseconds.ToString(CultureInfo.InvariantCulture)+";"+prefix+"_elapsed_ms="+snapshot.ElapsedMilliseconds.ToString(CultureInfo.InvariantCulture)+";"+prefix+"_remaining_ms="+snapshot.RemainingMilliseconds.ToString(CultureInfo.InvariantCulture)+";"+TaskDetail(prefix+"_input",snapshot.Input)+";"+TaskDetail(prefix+"_stdout",snapshot.Stdout)+";"+TaskDetail(prefix+"_stderr",snapshot.Stderr);}
    public static R7GitResourceCounters GetResourceCounters(){return new R7GitResourceCounters{AttributeAllocations=Interlocked.Read(ref AttributeAllocations),AttributeFrees=Interlocked.Read(ref AttributeFrees),AttributeInitializations=Interlocked.Read(ref AttributeInitializations),AttributeDeletes=Interlocked.Read(ref AttributeDeletes),HandleListAllocations=Interlocked.Read(ref HandleListAllocations),HandleListFrees=Interlocked.Read(ref HandleListFrees),JobListAllocations=Interlocked.Read(ref JobListAllocations),JobListFrees=Interlocked.Read(ref JobListFrees),EnvironmentAllocations=Interlocked.Read(ref EnvironmentAllocations),EnvironmentFrees=Interlocked.Read(ref EnvironmentFrees)};}
    static void ConfigureJob(IntPtr job){JOBOBJECT_EXTENDED_LIMIT_INFORMATION info=new JOBOBJECT_EXTENDED_LIMIT_INFORMATION();info.BasicLimitInformation.LimitFlags=JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;int size=Marshal.SizeOf(info);IntPtr ptr=Marshal.AllocHGlobal(size);try{Marshal.StructureToPtr(info,ptr,false);if(!SetInformationJobObject(job,JobObjectExtendedLimitInformation,ptr,size))Native("SetInformationJobObject");}finally{Marshal.FreeHGlobal(ptr);}}
    static string SafeStderr(byte[] bytes){if(bytes==null||bytes.Length==0)return "";string value=Encoding.UTF8.GetString(bytes);StringBuilder safe=new StringBuilder();foreach(char c in value){if(c>=32&&c!=127)safe.Append(c);else safe.Append(' ');if(safe.Length>=256)break;}return safe.ToString().Trim();}
    static void Close(ref IntPtr handle){if(handle!=IntPtr.Zero){CloseHandle(handle);handle=IntPtr.Zero;}}
    static bool TryReadiness(string path,int required,out int[] pids){
        pids=new int[0];if(String.IsNullOrEmpty(path)||required<1||!File.Exists(path))return false;FileInfo info=new FileInfo(path);if(info.Length<8||info.Length>4096)return false;string raw;
        try{using(FileStream stream=new FileStream(path,FileMode.Open,FileAccess.Read,FileShare.ReadWrite|FileShare.Delete)){byte[] bytes=new byte[checked((int)stream.Length)];int offset=0;while(offset<bytes.Length){int read=stream.Read(bytes,offset,bytes.Length-offset);if(read<=0)return false;offset+=read;}raw=Encoding.ASCII.GetString(bytes);}}catch{return false;}
        string[] fields=raw.Split('|');if(fields.Length!=7||fields[0]!="READY"||fields[1]!=required.ToString(CultureInfo.InvariantCulture)||fields[3]!="stdout=True"||fields[4]!="stderr=True"||fields[5]!="hold=True"||fields[6]!="marker=False")return false;string[] values=fields[2].Split(',');if(values.Length!=required)return false;HashSet<int> unique=new HashSet<int>();List<int> observed=new List<int>();foreach(string value in values){int pid;if(!Int32.TryParse(value,NumberStyles.None,CultureInfo.InvariantCulture,out pid)||pid<=0||!unique.Add(pid))return false;try{using(Process process=Process.GetProcessById(pid)){if(process.HasExited)return false;}}catch{return false;}observed.Add(pid);}pids=observed.ToArray();return true;
    }
    static bool PidsAbsent(int[] pids){if(pids==null)return true;HashSet<int> unique=new HashSet<int>();foreach(int pid in pids){if(pid<=0||!unique.Add(pid))continue;try{using(Process process=Process.GetProcessById(pid)){return false;}}catch(ArgumentException){}catch{return false;}}return true;}

    static void ValidateExecutable(string executable){
        if(String.IsNullOrEmpty(executable)||!Path.IsPathRooted(executable)||!File.Exists(executable))Fail("GIT_BATCH_EXECUTABLE_AUTHORITY_MISMATCH","path="+(executable??"<null>"));
        string full=Path.GetFullPath(executable);if(full!=executable)Fail("GIT_BATCH_EXECUTABLE_AUTHORITY_MISMATCH","reason=noncanonical;path="+executable);
        if((File.GetAttributes(full)&FileAttributes.ReparsePoint)!=0)Fail("GIT_BATCH_EXECUTABLE_AUTHORITY_MISMATCH","reason=reparse;path="+full);
    }
    static IntPtr BuildEnvironment(string fault,out string names){
        string windows=Environment.GetFolderPath(Environment.SpecialFolder.Windows);string local=Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);string temp=Path.Combine(local,"Temp");
        List<KeyValuePair<string,string>> rows=new List<KeyValuePair<string,string>>();
        rows.Add(new KeyValuePair<string,string>("COMSPEC",Path.Combine(windows,"System32","cmd.exe")));rows.Add(new KeyValuePair<string,string>("SystemRoot",windows));rows.Add(new KeyValuePair<string,string>("TEMP",temp));rows.Add(new KeyValuePair<string,string>("TMP",temp));rows.Add(new KeyValuePair<string,string>("WINDIR",windows));
        if(fault=="ENV_DUPLICATE")rows.Add(new KeyValuePair<string,string>("temp",temp));if(fault=="ENV_NUL")rows.Add(new KeyValuePair<string,string>("R7_BAD","x\0y"));
        HashSet<string> seen=new HashSet<string>(StringComparer.OrdinalIgnoreCase);foreach(KeyValuePair<string,string> row in rows){if(String.IsNullOrEmpty(row.Key)||row.Key.IndexOf('\0')>=0||row.Key.IndexOf('=')>=0||row.Value==null||row.Value.IndexOf('\0')>=0)Fail("GIT_BATCH_ENVIRONMENT_INVALID","reason=embedded-nul-or-name;name="+row.Key);if(!seen.Add(row.Key))Fail("GIT_BATCH_ENVIRONMENT_INVALID","reason=duplicate;name="+row.Key);}
        rows.Sort(delegate(KeyValuePair<string,string> a,KeyValuePair<string,string> b){return StringComparer.OrdinalIgnoreCase.Compare(a.Key,b.Key);});StringBuilder block=new StringBuilder();StringBuilder listed=new StringBuilder();foreach(KeyValuePair<string,string> row in rows){if(listed.Length!=0)listed.Append(',');listed.Append(row.Key);block.Append(row.Key).Append('=').Append(row.Value).Append('\0');}names=listed.ToString();IntPtr result=Marshal.StringToHGlobalUni(block.ToString());Interlocked.Increment(ref EnvironmentAllocations);return result;
    }
    static void RequireAllowedHandle(IntPtr handle,string role,HashSet<long> unique){uint flags;if(handle==IntPtr.Zero||handle==new IntPtr(-1)||!GetHandleInformation(handle,out flags)||(flags&HANDLE_FLAG_INHERIT)==0)Fail("GIT_BATCH_HANDLE_LIST_INVALID","role="+role+";reason=invalid-or-not-inheritable");if(!unique.Add(handle.ToInt64()))Fail("GIT_BATCH_HANDLE_LIST_INVALID","role="+role+";reason=duplicate");}
    static IntPtr BuildAttributeList(IntPtr stdinRead,IntPtr stdoutWrite,IntPtr stderrWrite,IntPtr job,string fault,out IntPtr handleValues,out IntPtr jobValue){
        HashSet<long> unique=new HashSet<long>();RequireAllowedHandle(stdinRead,"stdin",unique);RequireAllowedHandle(stdoutWrite,"stdout",unique);RequireAllowedHandle(stderrWrite,"stderr",unique);
        UIntPtr bytes=UIntPtr.Zero;int count=fault=="JOB_LIST_SIZE_FAIL"?Int32.MaxValue:2;bool sized=InitializeProcThreadAttributeList(IntPtr.Zero,count,0,ref bytes);int sizeError=Marshal.GetLastWin32Error();
        if(fault=="JOB_LIST_SIZE_FAIL")Fail("GIT_BATCH_JOB_LIST_ATTRIBUTE_FAILED","stage=size;win32="+sizeError.ToString(CultureInfo.InvariantCulture));
        if(sized||bytes==UIntPtr.Zero||sizeError!=122)Fail("GIT_BATCH_ATTRIBUTE_LIST_INITIALIZATION_FAILED","stage=size;win32="+sizeError.ToString(CultureInfo.InvariantCulture));
        if(bytes.ToUInt64()>Int32.MaxValue)Fail("GIT_BATCH_ATTRIBUTE_LIST_INITIALIZATION_FAILED","stage=size;reason=overflow");IntPtr list=Marshal.AllocHGlobal((int)bytes.ToUInt64());Interlocked.Increment(ref AttributeAllocations);handleValues=IntPtr.Zero;jobValue=IntPtr.Zero;
        bool initialized=false;
        try{
            bool injectInit=fault=="JOB_LIST_INIT_FAIL"||fault=="ATTRIBUTE_INIT_FAIL";IntPtr initializeTarget=injectInit?IntPtr.Zero:list;
            if(!InitializeProcThreadAttributeList(initializeTarget,2,0,ref bytes)){int error=Marshal.GetLastWin32Error();Fail(fault=="JOB_LIST_INIT_FAIL"?"GIT_BATCH_JOB_LIST_ATTRIBUTE_FAILED":"GIT_BATCH_ATTRIBUTE_LIST_INITIALIZATION_FAILED","stage=initialize;win32="+error.ToString(CultureInfo.InvariantCulture));}
            initialized=true;Interlocked.Increment(ref AttributeInitializations);handleValues=Marshal.AllocHGlobal(IntPtr.Size*3);Interlocked.Increment(ref HandleListAllocations);Marshal.WriteIntPtr(handleValues,0,stdinRead);Marshal.WriteIntPtr(handleValues,IntPtr.Size,stdoutWrite);Marshal.WriteIntPtr(handleValues,IntPtr.Size*2,stderrWrite);
            if(fault=="HANDLE_UPDATE_FAIL"||!UpdateProcThreadAttribute(list,0,PROC_THREAD_ATTRIBUTE_HANDLE_LIST,handleValues,new UIntPtr((uint)(IntPtr.Size*3)),IntPtr.Zero,IntPtr.Zero)){int error=fault=="HANDLE_UPDATE_FAIL"?5:Marshal.GetLastWin32Error();Fail("GIT_BATCH_HANDLE_LIST_UPDATE_FAILED","win32="+error.ToString(CultureInfo.InvariantCulture));}
            jobValue=Marshal.AllocHGlobal(IntPtr.Size);Interlocked.Increment(ref JobListAllocations);Marshal.WriteIntPtr(jobValue,job);
            UIntPtr jobValueSize=fault=="JOB_LIST_UPDATE_FAIL"?UIntPtr.Zero:new UIntPtr((uint)IntPtr.Size);
            if(!UpdateProcThreadAttribute(list,0,PROC_THREAD_ATTRIBUTE_JOB_LIST,jobValue,jobValueSize,IntPtr.Zero,IntPtr.Zero)){int error=Marshal.GetLastWin32Error();Fail("GIT_BATCH_JOB_LIST_ATTRIBUTE_FAILED","stage=update;win32="+error.ToString(CultureInfo.InvariantCulture));}
            return list;
        }catch{
            if(jobValue!=IntPtr.Zero){Marshal.FreeHGlobal(jobValue);Interlocked.Increment(ref JobListFrees);jobValue=IntPtr.Zero;}if(handleValues!=IntPtr.Zero){Marshal.FreeHGlobal(handleValues);Interlocked.Increment(ref HandleListFrees);handleValues=IntPtr.Zero;}if(initialized){DeleteProcThreadAttributeList(list);Interlocked.Increment(ref AttributeDeletes);}Marshal.FreeHGlobal(list);Interlocked.Increment(ref AttributeFrees);throw;
        }
    }
    static bool WaitSignaled(IntPtr process,Stopwatch clock,int deadline){while(clock.ElapsedMilliseconds<deadline){uint wait=WaitForSingleObject(process,10);if(wait==WAIT_OBJECT_0)return true;if(wait!=WAIT_TIMEOUT)break;}return WaitForSingleObject(process,0)==WAIT_OBJECT_0;}
    static string LaunchDetail(PROCESS_INFORMATION pi,Stopwatch clock,bool assigned,bool executed,bool signaled,uint active){return "parent_pid="+pi.dwProcessId+";child_executed="+executed+";job_contained="+assigned+";parent_signaled="+signaled+";active="+active+";elapsed_ms="+clock.ElapsedMilliseconds.ToString(CultureInfo.InvariantCulture)+";stdout_complete=True;stderr_complete=True;input_complete=True;survivor="+(!signaled);}

    static void CleanupCreatedProcessAndFail(string primaryCode,string primaryDetail,string fault,ref PROCESS_INFORMATION pi,IntPtr job,Stopwatch clock,int deadline,int confirmationMilliseconds,
        ref IntPtr stdinRead,ref IntPtr stdinWrite,ref IntPtr stdoutRead,ref IntPtr stdoutWrite,ref IntPtr stderrRead,ref IntPtr stderrWrite,
        FileStream stdin,FileStream stdout,FileStream stderr,Task inputTask,Task stdoutTask,Task stderrTask,bool resumed,int[] observedFixturePids){
        Stopwatch cleanup=Stopwatch.StartNew();long primaryStart=clock.ElapsedMilliseconds;long primaryEnd=Math.Min((long)deadline,primaryStart+(long)confirmationMilliseconds);bool jobTerminated=false,processTerminated=false;int jobError=0,processError=0,primaryWaitError=0,primaryQueryError=0,finalWaitError=0,finalQueryError=0;int parentPid=pi.dwProcessId,threadId=pi.dwThreadId;
        bool injectJobTerminate=fault!=null&&fault.IndexOf("TERMINATE_JOB_FAIL",StringComparison.Ordinal)>=0;bool injectProcessTerminate=fault!=null&&fault.IndexOf("TERMINATE_PROCESS_FAIL",StringComparison.Ordinal)>=0;bool injectBoth=fault!=null&&fault.IndexOf("BOTH_TERMINATION_FAIL",StringComparison.Ordinal)>=0;
        bool deferTermination=fault!=null&&fault.IndexOf("PRIMARY_LATE_PROCESS_TRANSITION",StringComparison.Ordinal)>=0;
        if(!deferTermination){IntPtr jobTerminationHandle=(injectJobTerminate||injectBoth)?IntPtr.Zero:job;jobTerminated=TerminateJobObject(jobTerminationHandle,230);jobError=jobTerminated?0:Marshal.GetLastWin32Error();uint initialWait=WaitForSingleObject(pi.hProcess,0);bool forceProcess=injectProcessTerminate||injectBoth;if(initialWait!=WAIT_OBJECT_0||forceProcess){IntPtr processTerminationHandle=forceProcess?IntPtr.Zero:pi.hProcess;processTerminated=TerminateProcess(processTerminationHandle,231);processError=processTerminated?0:Marshal.GetLastWin32Error();}if(injectBoth){bool retry=TerminateJobObject(job,232);int retryError=retry?0:Marshal.GetLastWin32Error();jobTerminated=retry;primaryDetail+=";job_retry="+retry+";job_retry_win32="+retryError.ToString(CultureInfo.InvariantCulture);}}
        Close(ref pi.hThread);Close(ref stdinRead);Close(ref stdoutWrite);Close(ref stderrWrite);try{if(stdin!=null)stdin.Dispose();}catch{}Close(ref stdinWrite);
        try{if(stdout!=null)stdout.Dispose();}catch{}try{if(stderr!=null)stderr.Dispose();}catch{}
        bool injectParentWait=fault!=null&&fault.IndexOf("PARENT_WAIT_FAIL",StringComparison.Ordinal)>=0;bool injectFinalQuery=fault!=null&&(fault.IndexOf("FINAL_QUERY_FAIL",StringComparison.Ordinal)>=0||fault.IndexOf("CONFIRM_FAIL",StringComparison.Ordinal)>=0);CleanupSnapshot primary=null,primaryDiagnostic=null,final=null;
        while(clock.ElapsedMilliseconds<=primaryEnd){int waitError,queryError;CleanupSnapshot candidate=CaptureSnapshot(pi.hProcess,job,clock,deadline,(int)primaryEnd,inputTask,stdoutTask,stderrTask,"Primary",primaryStart,false,injectParentWait,injectFinalQuery,out waitError,out queryError);if(candidate.ObservationCompletedMilliseconds>primaryEnd){primaryDiagnostic=AsDiagnostic(candidate);break;}primary=candidate;if(primaryWaitError==0)primaryWaitError=waitError;if(primaryQueryError==0)primaryQueryError=queryError;if(candidate.PrimaryEligible)break;if(clock.ElapsedMilliseconds<primaryEnd)Thread.Sleep(1);}
        if(primary==null)primary=UnmeasuredSnapshot(clock,deadline,(int)primaryEnd,inputTask,stdoutTask,stderrTask,"Primary",primaryStart,false);bool primaryConfirmed=primary.PrimaryEligible;
        if(deferTermination){jobTerminated=TerminateJobObject(job,230);jobError=jobTerminated?0:Marshal.GetLastWin32Error();uint initialWait=WaitForSingleObject(pi.hProcess,0);if(initialWait!=WAIT_OBJECT_0){processTerminated=TerminateProcess(pi.hProcess,231);processError=processTerminated?0:Marshal.GetLastWin32Error();}}
        if(!primaryConfirmed){int boundaryWait,boundaryQuery;primaryDiagnostic=CaptureSnapshot(pi.hProcess,job,clock,deadline,(int)primaryEnd,inputTask,stdoutTask,stderrTask,"PrimaryDiagnostic",primaryStart,true,injectParentWait,injectFinalQuery,out boundaryWait,out boundaryQuery);if(primaryWaitError==0)primaryWaitError=boundaryWait;if(primaryQueryError==0)primaryQueryError=boundaryQuery;}
        long finalStart=clock.ElapsedMilliseconds;while(clock.ElapsedMilliseconds<=deadline){int waitError,queryError;CleanupSnapshot candidate=CaptureSnapshot(pi.hProcess,job,clock,deadline,deadline,inputTask,stdoutTask,stderrTask,"Final",finalStart,false,false,injectFinalQuery,out waitError,out queryError);if(finalWaitError==0)finalWaitError=waitError;if(finalQueryError==0)finalQueryError=queryError;final=candidate;if(candidate.PrimaryEligible)break;if(clock.ElapsedMilliseconds<deadline)Thread.Sleep(1);}
        if(final==null)final=UnmeasuredSnapshot(clock,deadline,deadline,inputTask,stdoutTask,stderrTask,"Final",finalStart,true);else if(!final.PrimaryEligible)final=AsDiagnostic(final);
        if(final.ParentSignaled)Close(ref pi.hProcess);List<int> pidList=new List<int>();pidList.Add(parentPid);if(observedFixturePids!=null)pidList.AddRange(observedFixturePids);bool externalAbsent=PidsAbsent(pidList.ToArray());while(!externalAbsent&&clock.ElapsedMilliseconds<deadline){Thread.Sleep(1);externalAbsent=PidsAbsent(pidList.ToArray());}final=WithExternalDisposition(final,clock,deadline,externalAbsent);
        bool finalConfirmed=final.TerminalReturnCriteria&&finalWaitError==0&&finalQueryError==0;bool treeConfirmed=final.ZeroProcessAuthority&&externalAbsent;bool survivor=!externalAbsent;
        bool primaryLate=primaryDiagnostic!=null&&primaryDiagnostic.ObservationCompletedMilliseconds>primaryEnd;string detail=primaryDetail+";parent_pid="+parentPid+";thread_id="+threadId+";job_at_creation=True;job_contained=True;resumed="+resumed+";child_executed="+resumed+";job_terminated="+jobTerminated+";job_win32="+jobError.ToString(CultureInfo.InvariantCulture)+";process_terminated="+processTerminated+";process_win32="+processError.ToString(CultureInfo.InvariantCulture)+";primary_wait_win32="+primaryWaitError.ToString(CultureInfo.InvariantCulture)+";primary_query_win32="+primaryQueryError.ToString(CultureInfo.InvariantCulture)+";final_wait_win32="+finalWaitError.ToString(CultureInfo.InvariantCulture)+";final_query_win32="+finalQueryError.ToString(CultureInfo.InvariantCulture)+";parent_wait_win32="+primaryWaitError.ToString(CultureInfo.InvariantCulture)+";parent_signaled="+final.ParentSignaled+";job_query_ok="+(final.JobQueryStatus=="Succeeded")+";job_query_win32="+finalQueryError.ToString(CultureInfo.InvariantCulture)+";active="+(final.JobQueryStatus=="Succeeded"?final.ActiveProcesses.ToString(CultureInfo.InvariantCulture):"<unknown>")+";tree_terminated="+treeConfirmed+";stdout_complete="+final.Stdout.IsSuccessful+";stderr_complete="+final.Stderr.IsSuccessful+";input_complete="+final.Input.IsSuccessful+";external_pid_count="+pidList.Count.ToString(CultureInfo.InvariantCulture)+";external_pids_absent="+externalAbsent+";primary_late_observation="+primaryLate+";elapsed_ms="+clock.ElapsedMilliseconds.ToString(CultureInfo.InvariantCulture)+";cleanup_ms="+cleanup.ElapsedMilliseconds.ToString(CultureInfo.InvariantCulture)+";survivor="+survivor+";"+SnapshotDetail("primary",primary)+";"+(primaryDiagnostic==null?"primary_diagnostic=<none>":SnapshotDetail("primary_diagnostic",primaryDiagnostic))+";"+SnapshotDetail("final",final);
        if(final.Input.State=="Running"||final.Stdout.State=="Running"||final.Stderr.State=="Running")Fail("GIT_BATCH_PROCESS_TREE_TERMINATION_FAILED","reason=nonterminal-task-at-deadline;"+detail);
        if(!finalConfirmed)Fail("GIT_BATCH_PROCESS_TREE_TERMINATION_FAILED",detail);if(!primaryConfirmed)Fail("GIT_BATCH_PROCESS_TREE_TERMINATION_FAILED","reason=primary-confirmation-deadline;"+detail);Fail(primaryCode,detail);
    }

    public static R7GitProcessResult Run(string executable,string arguments,string workingDirectory,byte[] standardInput,R7GitExpectedObject[] expected,int totalDeadlineMilliseconds,int cleanupReserveMilliseconds,int terminationConfirmationMilliseconds,int stderrLimit){return RunCore(executable,arguments,workingDirectory,standardInput,expected,totalDeadlineMilliseconds,cleanupReserveMilliseconds,terminationConfirmationMilliseconds,stderrLimit,null,null,0);}
    public static R7GitProcessResult RunForLaunchTest(string executable,string arguments,string workingDirectory,byte[] standardInput,R7GitExpectedObject[] expected,int totalDeadlineMilliseconds,int cleanupReserveMilliseconds,int terminationConfirmationMilliseconds,int stderrLimit,string testFault,string readinessPath,int readinessCount){if(String.IsNullOrEmpty(testFault))Fail("GIT_BATCH_PROCESS_FAILURE","reason=missing-explicit-test-fault");return RunCore(executable,arguments,workingDirectory,standardInput,expected,totalDeadlineMilliseconds,cleanupReserveMilliseconds,terminationConfirmationMilliseconds,stderrLimit,testFault,readinessPath,readinessCount);}
    public static R7GitProcessResult[] RunConcurrentLaunchTest(string executable,string slowArguments,string fastArguments,string workingDirectory,int totalDeadlineMilliseconds,int cleanupReserveMilliseconds,int stderrLimit){
        lock(ConcurrentTestLock){using(Barrier barrier=new Barrier(2)){ConcurrentLaunchBarrier=barrier;try{R7GitExpectedObject[] none=new R7GitExpectedObject[0];Task<R7GitProcessResult> slow=Task.Factory.StartNew<R7GitProcessResult>(delegate{return RunCore(executable,slowArguments,workingDirectory,new byte[0],none,totalDeadlineMilliseconds,cleanupReserveMilliseconds,cleanupReserveMilliseconds,stderrLimit,"CONCURRENT_GATE",null,0);},CancellationToken.None,TaskCreationOptions.LongRunning,TaskScheduler.Default);Task<R7GitProcessResult> fast=Task.Factory.StartNew<R7GitProcessResult>(delegate{return RunCore(executable,fastArguments,workingDirectory,new byte[0],none,totalDeadlineMilliseconds,cleanupReserveMilliseconds,cleanupReserveMilliseconds,stderrLimit,"CONCURRENT_GATE",null,0);},CancellationToken.None,TaskCreationOptions.LongRunning,TaskScheduler.Default);Task.WaitAll(slow,fast);return new R7GitProcessResult[]{slow.Result,fast.Result};}finally{ConcurrentLaunchBarrier=null;}}}
    }
    static R7GitProcessResult RunCore(string executable,string arguments,string workingDirectory,byte[] standardInput,R7GitExpectedObject[] expected,int totalDeadlineMilliseconds,int cleanupReserveMilliseconds,int terminationConfirmationMilliseconds,int stderrLimit,string testFault,string readinessPath,int readinessCount){
        if(expected==null)throw new ArgumentNullException("expected");if(totalDeadlineMilliseconds<500||cleanupReserveMilliseconds<100||cleanupReserveMilliseconds>=totalDeadlineMilliseconds||terminationConfirmationMilliseconds<1||terminationConfirmationMilliseconds>cleanupReserveMilliseconds)Fail("GIT_BATCH_PROCESS_FAILURE","reason=invalid-deadline");if(stderrLimit<1||stderrLimit>1048576)Fail("GIT_BATCH_PROCESS_FAILURE","reason=invalid-stderr-limit");ValidateExecutable(executable);
        long aggregate=Budget(expected),observedStdout=0,maximumPayload=0;foreach(R7GitExpectedObject row in expected)maximumPayload=Math.Max(maximumPayload,row.Size);
        Stopwatch clock=Stopwatch.StartNew();long executionCutoff=totalDeadlineMilliseconds-cleanupReserveMilliseconds;IntPtr job=IntPtr.Zero,stdoutRead=IntPtr.Zero,stdoutWrite=IntPtr.Zero,stderrRead=IntPtr.Zero,stderrWrite=IntPtr.Zero,stdinRead=IntPtr.Zero,stdinWrite=IntPtr.Zero,attributes=IntPtr.Zero,attributeHandles=IntPtr.Zero,attributeJob=IntPtr.Zero,environment=IntPtr.Zero;PROCESS_INFORMATION pi=new PROCESS_INFORMATION();FileStream stdout=null,stderr=null,stdin=null;Task<R7GitAuthenticatedObject[]> stdoutTask=null;Task<StderrState> stderrTask=null;Task inputTask=null;CancellationTokenSource inputCancellation=null;Exception failure=null;long cleanupMs=0;bool processExited=false,treeTerminated=false,cleanupStarted=false,resumed=false;string environmentNames="";int[] observedFixturePids=new int[0];bool readinessEstablished=false;
        try{
            SECURITY_ATTRIBUTES sa=new SECURITY_ATTRIBUTES{nLength=Marshal.SizeOf(typeof(SECURITY_ATTRIBUTES)),bInheritHandle=true};if(!CreatePipe(out stdoutRead,out stdoutWrite,ref sa,0))Native("CreatePipe/stdout");if(!SetHandleInformation(stdoutRead,HANDLE_FLAG_INHERIT,0))Native("SetHandleInformation/stdout");if(!CreatePipe(out stderrRead,out stderrWrite,ref sa,0))Native("CreatePipe/stderr");if(!SetHandleInformation(stderrRead,HANDLE_FLAG_INHERIT,0))Native("SetHandleInformation/stderr");if(!CreatePipe(out stdinRead,out stdinWrite,ref sa,0))Native("CreatePipe/stdin");if(!SetHandleInformation(stdinWrite,HANDLE_FLAG_INHERIT,0))Native("SetHandleInformation/stdin");if(testFault=="CONCURRENT_GATE"){Barrier barrier=ConcurrentLaunchBarrier;if(barrier==null||!barrier.SignalAndWait(1000))Fail("GIT_BATCH_PROCESS_FAILURE","reason=concurrent-launch-gate");}
            environment=BuildEnvironment(testFault,out environmentNames);if(environmentNames!="COMSPEC,SystemRoot,TEMP,TMP,WINDIR")Fail("GIT_BATCH_ENVIRONMENT_INVALID","reason=contract-order;observed="+environmentNames);
            job=CreateJobObject(IntPtr.Zero,null);if(job==IntPtr.Zero)Native("CreateJobObject");ConfigureJob(job);IntPtr jobAttribute=job;string jobAuthorityStimulus="valid-job";
            if(testFault=="JOB_LIST_CLOSED_HANDLE"||testFault=="JOB_AT_CREATION_REJECT"||testFault=="JOB_AT_CREATION_REJECT_REPEAT"||testFault=="JOB_AT_CREATION_REJECT_NO_CHILD"){IntPtr closedJob=CreateJobObject(IntPtr.Zero,null);if(closedJob==IntPtr.Zero)Native("CreateJobObject/closed-stimulus");ConfigureJob(closedJob);jobAttribute=closedJob;if(!CloseHandle(closedJob))Native("CloseHandle/closed-job-stimulus");jobAuthorityStimulus="closed-job-handle";}
            else if(testFault=="JOB_LIST_NONJOB_HANDLE") { jobAttribute=stdinRead;jobAuthorityStimulus="nonjob-handle"; }
            attributes=BuildAttributeList(stdinRead,stdoutWrite,stderrWrite,jobAttribute,testFault,out attributeHandles,out attributeJob);
            STARTUPINFOEX si=new STARTUPINFOEX();si.StartupInfo.cb=Marshal.SizeOf(typeof(STARTUPINFOEX));si.StartupInfo.dwFlags=STARTF_USESTDHANDLES;si.StartupInfo.hStdInput=stdinRead;si.StartupInfo.hStdOutput=stdoutWrite;si.StartupInfo.hStdError=stderrWrite;si.lpAttributeList=attributes;StringBuilder command=new StringBuilder(Quote(executable)+(String.IsNullOrEmpty(arguments)?"":" "+arguments));bool injectCreateRejection=jobAuthorityStimulus!="valid-job";string launchDirectory=workingDirectory;bool validWorkingDirectory=Directory.Exists(launchDirectory);bool created=CreateProcessW(executable,command,IntPtr.Zero,IntPtr.Zero,true,CREATE_SUSPENDED|CREATE_NO_WINDOW|CREATE_UNICODE_ENVIRONMENT|EXTENDED_STARTUPINFO_PRESENT,environment,launchDirectory,ref si,out pi);int createError=created?0:Marshal.GetLastWin32Error();if(!created){if(pi.hProcess!=IntPtr.Zero||pi.hThread!=IntPtr.Zero||pi.dwProcessId!=0)Fail("GIT_BATCH_PROCESS_TREE_TERMINATION_FAILED","stage=job-at-creation-rejection;unexpected_child=True;win32="+createError.ToString(CultureInfo.InvariantCulture));Fail(injectCreateRejection?"GIT_BATCH_JOB_AT_CREATION_FAILED":"GIT_BATCH_CREATE_PROCESS_FAILED","stage=create;stimulus="+jobAuthorityStimulus+";valid_working_directory="+validWorkingDirectory+";child_created=False;process_id=0;input_state=NotStarted;stdout_state=NotStarted;stderr_state=NotStarted;win32="+createError.ToString(CultureInfo.InvariantCulture));}
            uint assignedActive;int queryError;bool injectPreQuery=testFault!=null&&testFault.IndexOf("PRE_RESUME_QUERY_FAIL",StringComparison.Ordinal)>=0;bool queryOk=TryActive(job,injectPreQuery,out assignedActive,out queryError);if(!queryOk){cleanupStarted=true;CleanupCreatedProcessAndFail("GIT_BATCH_JOB_CONTAINMENT_QUERY_FAILED","stage=pre-resume;native_query=False;win32="+queryError.ToString(CultureInfo.InvariantCulture),testFault,ref pi,job,clock,totalDeadlineMilliseconds,terminationConfirmationMilliseconds,ref stdinRead,ref stdinWrite,ref stdoutRead,ref stdoutWrite,ref stderrRead,ref stderrWrite,stdin,stdout,stderr,inputTask,stdoutTask,stderrTask,false,observedFixturePids);}
            bool legacyAssignmentFault=testFault=="JOB_ASSIGN_FAIL"||testFault=="JOB_ASSIGN_TERMINATE_FAIL"||testFault=="JOB_ASSIGN_CONFIRM_FAIL";bool injectUnexpectedActive=testFault!=null&&testFault.IndexOf("PRE_RESUME_ACTIVE_UNEXPECTED",StringComparison.Ordinal)>=0;uint requiredActive=injectUnexpectedActive||legacyAssignmentFault?2u:1u;if(assignedActive!=requiredActive){cleanupStarted=true;string containmentCode=legacyAssignmentFault?"GIT_BATCH_JOB_ASSIGNMENT_FAILED":"GIT_BATCH_JOB_CONTAINMENT_STATE_MISMATCH";CleanupCreatedProcessAndFail(containmentCode,"stage=pre-resume;native_query=True;expected="+requiredActive.ToString(CultureInfo.InvariantCulture)+";observed="+assignedActive.ToString(CultureInfo.InvariantCulture),testFault,ref pi,job,clock,totalDeadlineMilliseconds,terminationConfirmationMilliseconds,ref stdinRead,ref stdinWrite,ref stdoutRead,ref stdoutWrite,ref stderrRead,ref stderrWrite,stdin,stdout,stderr,inputTask,stdoutTask,stderrTask,false,observedFixturePids);}
            IntPtr resumeHandle=pi.hThread;bool injectResumeFailure=testFault!=null&&(testFault.IndexOf("RESUME_ACTUAL_FAIL",StringComparison.Ordinal)>=0||testFault=="RESUME_FAIL"||testFault=="RESUME_TERMINATE_JOB_FAIL"||testFault=="RESUME_CONFIRM_FAIL");if(injectResumeFailure){if(!CloseHandle(resumeHandle)){int closeError=Marshal.GetLastWin32Error();cleanupStarted=true;CleanupCreatedProcessAndFail("GIT_BATCH_PROCESS_RESUME_FAILED","stage=resume-fault-handle-close;win32="+closeError.ToString(CultureInfo.InvariantCulture),testFault,ref pi,job,clock,totalDeadlineMilliseconds,terminationConfirmationMilliseconds,ref stdinRead,ref stdinWrite,ref stdoutRead,ref stdoutWrite,ref stderrRead,ref stderrWrite,stdin,stdout,stderr,inputTask,stdoutTask,stderrTask,false,observedFixturePids);}pi.hThread=IntPtr.Zero;}if(testFault=="RESUME_SUSPEND_COUNT"){uint suspended=SuspendThread(pi.hThread);if(suspended==UInt32.MaxValue){int suspendError=Marshal.GetLastWin32Error();cleanupStarted=true;CleanupCreatedProcessAndFail("GIT_BATCH_PROCESS_RESUME_FAILED","stage=additional-suspend;win32="+suspendError.ToString(CultureInfo.InvariantCulture),testFault,ref pi,job,clock,totalDeadlineMilliseconds,terminationConfirmationMilliseconds,ref stdinRead,ref stdinWrite,ref stdoutRead,ref stdoutWrite,ref stderrRead,ref stderrWrite,stdin,stdout,stderr,inputTask,stdoutTask,stderrTask,false,observedFixturePids);}}
            uint resume=ResumeThread(resumeHandle);int resumeError=resume==UInt32.MaxValue?Marshal.GetLastWin32Error():0;if(resume!=1){cleanupStarted=true;CleanupCreatedProcessAndFail("GIT_BATCH_PROCESS_RESUME_FAILED","stage=resume;native_return="+resume.ToString(CultureInfo.InvariantCulture)+";win32="+resumeError.ToString(CultureInfo.InvariantCulture),testFault,ref pi,job,clock,totalDeadlineMilliseconds,terminationConfirmationMilliseconds,ref stdinRead,ref stdinWrite,ref stdoutRead,ref stdoutWrite,ref stderrRead,ref stderrWrite,stdin,stdout,stderr,inputTask,stdoutTask,stderrTask,false,observedFixturePids);}resumed=true;
            Close(ref pi.hThread);Close(ref stdoutWrite);Close(ref stderrWrite);Close(ref stdinRead);
            stdout=new FileStream(new SafeFileHandle(stdoutRead,true),FileAccess.Read,4096,false);stdoutRead=IntPtr.Zero;stderr=new FileStream(new SafeFileHandle(stderrRead,true),FileAccess.Read,4096,false);stderrRead=IntPtr.Zero;stdin=new FileStream(new SafeFileHandle(stdinWrite,true),FileAccess.Write,4096,false);stdinWrite=IntPtr.Zero;
            Stream outLocal=stdout,errLocal=stderr,inLocal=stdin;stdoutTask=Task.Factory.StartNew<R7GitAuthenticatedObject[]>(delegate{return Parse(outLocal,expected,aggregate,delegate(long value){Interlocked.Exchange(ref observedStdout,value);});},CancellationToken.None,TaskCreationOptions.LongRunning,TaskScheduler.Default);stderrTask=Task.Factory.StartNew<StderrState>(delegate{return DrainStderr(errLocal,stderrLimit);},CancellationToken.None,TaskCreationOptions.LongRunning,TaskScheduler.Default);inputCancellation=new CancellationTokenSource();if(testFault=="POST_TASK_INPUT_CANCELED")inputCancellation.Cancel();CancellationToken inputToken=inputCancellation.Token;inputTask=Task.Factory.StartNew(delegate{if(testFault=="POST_TASK_INPUT_FAULT")throw new InvalidDataException("GIT_BATCH_INPUT_TASK_FAULT|stage=input-task");if(standardInput!=null&&standardInput.Length!=0)inLocal.Write(standardInput,0,standardInput.Length);inLocal.Flush();inLocal.Dispose();},inputToken,TaskCreationOptions.LongRunning,TaskScheduler.Default);if(testFault=="POST_TASK_INPUT_CANCELED")failure=new InvalidDataException("GIT_BATCH_INPUT_TASK_CANCELED|stage=input-task");if(testFault=="POST_TASK_FORCED_CLEANUP")failure=new InvalidDataException("GIT_BATCH_POST_RESUME_CLEANUP_FAILED|stage=post-task-distinct");if(testFault=="PRIMARY_LATE_PROCESS_TRANSITION")failure=new InvalidDataException("GIT_BATCH_PROCESS_TIMEOUT|stage=late-primary-transition");
            bool readinessGated=testFault!=null&&testFault.IndexOf("READINESS_GATED_TIMEOUT",StringComparison.Ordinal)>=0;while(clock.ElapsedMilliseconds<executionCutoff){if(readinessGated&&!readinessEstablished){int[] readyPids;if(TryReadiness(readinessPath,readinessCount,out readyPids)){observedFixturePids=readyPids;bool readinessParentAlive=WaitForSingleObject(pi.hProcess,0)==WAIT_TIMEOUT;if(!readinessParentAlive)failure=new InvalidDataException("GIT_BATCH_STIMULUS_NOT_READY|stage=readiness;reason=parent-not-alive;observed_descendants="+readyPids.Length.ToString(CultureInfo.InvariantCulture));else{readinessEstablished=true;failure=new InvalidDataException("GIT_BATCH_PROCESS_TIMEOUT|stage=stimulus-ready;readiness_established=True;readiness_parent_alive=True;readiness_count="+readyPids.Length.ToString(CultureInfo.InvariantCulture)+";readiness_stdout_held=True;readiness_stderr_held=True;readiness_hold=True;readiness_marker=False");}}}if(failure==null)failure=Failure(stdoutTask)??Failure(stderrTask)??Failure(inputTask);if(failure!=null)break;processExited=WaitForSingleObject(pi.hProcess,0)==WAIT_OBJECT_0;uint active=Active(job);if(stdoutTask.Status==TaskStatus.RanToCompletion&&stderrTask.Status==TaskStatus.RanToCompletion&&inputTask.Status==TaskStatus.RanToCompletion&&processExited&&active==0)break;Thread.Sleep(2);}
            if(readinessGated&&!readinessEstablished&&failure==null)failure=new InvalidDataException("GIT_BATCH_STIMULUS_NOT_READY|stage=readiness;required="+readinessCount.ToString(CultureInfo.InvariantCulture));processExited=WaitForSingleObject(pi.hProcess,0)==WAIT_OBJECT_0;bool complete=stdoutTask.Status==TaskStatus.RanToCompletion&&stderrTask.Status==TaskStatus.RanToCompletion&&inputTask.Status==TaskStatus.RanToCompletion&&processExited&&Active(job)==0;if(failure==null&&!complete){TaskObservation preInput=ObserveTask(inputTask,clock,"PreCleanup"),preStdout=ObserveTask(stdoutTask,clock,"PreCleanup"),preStderr=ObserveTask(stderrTask,clock,"PreCleanup");failure=new InvalidDataException("GIT_BATCH_PROCESS_TIMEOUT|stage=lifecycle;elapsed_ms="+clock.ElapsedMilliseconds.ToString(CultureInfo.InvariantCulture)+";precleanup_input_state="+preInput.State+";precleanup_stdout_state="+preStdout.State+";precleanup_stderr_state="+preStderr.State);}
            if(failure==null){uint exitCode;if(!GetExitCodeProcess(pi.hProcess,out exitCode))Native("GetExitCodeProcess");if(exitCode!=0)failure=new InvalidDataException("GIT_BATCH_PROCESS_FAILURE|context=process;exited=True;exit_code="+exitCode.ToString(CultureInfo.InvariantCulture)+";stderr="+SafeStderr(stderrTask.Result.Bytes));}
            if(failure!=null){cleanupStarted=true;int separator=failure.Message.IndexOf('|');string primaryCode=separator>=0?failure.Message.Substring(0,separator):"GIT_BATCH_PROCESS_FAILURE";string primaryDetail=separator>=0?failure.Message.Substring(separator+1):"stage=execution;failure="+failure.Message;CleanupCreatedProcessAndFail(primaryCode,primaryDetail,testFault,ref pi,job,clock,totalDeadlineMilliseconds,terminationConfirmationMilliseconds,ref stdinRead,ref stdinWrite,ref stdoutRead,ref stdoutWrite,ref stderrRead,ref stderrWrite,stdin,stdout,stderr,inputTask,stdoutTask,stderrTask,true,observedFixturePids);}
            treeTerminated=true;StderrState stderrState=stderrTask.Result;R7GitAuthenticatedObject[] objects=stdoutTask.Result;int successfulPid=pi.dwProcessId,successfulThread=pi.dwThreadId;Close(ref pi.hProcess);int[] successfulPids=new int[]{successfulPid};bool successfulAbsent=PidsAbsent(successfulPids);while(!successfulAbsent&&clock.ElapsedMilliseconds<totalDeadlineMilliseconds){Thread.Sleep(1);successfulAbsent=PidsAbsent(successfulPids);}if(!successfulAbsent)Fail("GIT_BATCH_PROCESS_TREE_TERMINATION_FAILED","reason=success-process-observable;parent_pid="+successfulPid.ToString(CultureInfo.InvariantCulture));return new R7GitProcessResult{Objects=objects,ParentPid=successfulPid,ThreadId=successfulThread,ObservedProcessIds=successfulPids,AggregateBudget=aggregate,ObservedStdoutBytes=observedStdout,MaximumPayloadBytes=maximumPayload,MaximumRetainedStderrBytes=stderrState.Bytes.Length,ElapsedMilliseconds=clock.ElapsedMilliseconds,CleanupMilliseconds=cleanupMs,StdoutCompleted=true,StderrCompleted=true,InputCompleted=true,ProcessExited=true,ProcessTreeTerminated=treeTerminated,JobAtCreationContained=true,ChildExecuted=true,InputTaskState="Completed",StdoutTaskState="Completed",StderrTaskState="Completed"};
        }catch(Exception unexpected){if(pi.hProcess!=IntPtr.Zero&&!cleanupStarted){cleanupStarted=true;CleanupCreatedProcessAndFail("GIT_BATCH_PROCESS_FAILURE","stage=unhandled;failure="+unexpected.Message,testFault,ref pi,job,clock,totalDeadlineMilliseconds,terminationConfirmationMilliseconds,ref stdinRead,ref stdinWrite,ref stdoutRead,ref stdoutWrite,ref stderrRead,ref stderrWrite,stdin,stdout,stderr,inputTask,stdoutTask,stderrTask,resumed,observedFixturePids);}throw;}finally{try{if(inputCancellation!=null)inputCancellation.Dispose();}catch{};try{if(stdin!=null)stdin.Dispose();}catch{};try{if(stdout!=null)stdout.Dispose();}catch{};try{if(stderr!=null)stderr.Dispose();}catch{};Close(ref stdinRead);Close(ref stdinWrite);Close(ref stdoutRead);Close(ref stdoutWrite);Close(ref stderrRead);Close(ref stderrWrite);Close(ref pi.hThread);Close(ref pi.hProcess);Close(ref job);if(attributes!=IntPtr.Zero){DeleteProcThreadAttributeList(attributes);Interlocked.Increment(ref AttributeDeletes);Marshal.FreeHGlobal(attributes);Interlocked.Increment(ref AttributeFrees);}if(attributeHandles!=IntPtr.Zero){Marshal.FreeHGlobal(attributeHandles);Interlocked.Increment(ref HandleListFrees);}if(attributeJob!=IntPtr.Zero){Marshal.FreeHGlobal(attributeJob);Interlocked.Increment(ref JobListFrees);}if(environment!=IntPtr.Zero){Marshal.FreeHGlobal(environment);Interlocked.Increment(ref EnvironmentFrees);}}
    }
}
'@
}
function NewGitExpectedObject([string]$Oid,[string]$Path,[long]$Size) {
    InitializeGitBatchProcessRuntime
    $row=[R7GitExpectedObject]::new();$row.Oid=$Oid;$row.Path=$Path;$row.Size=$Size;return $row
}
function InvokeBoundedGitBatchProcess([string]$Executable,[string]$Arguments,[string]$WorkingDirectory,[byte[]]$StandardInput,[object[]]$ExpectedObjects,[int]$TotalDeadlineMilliseconds=30000,[int]$CleanupReserveMilliseconds=5000,[int]$StderrLimit=65536,[int]$TerminationConfirmationMilliseconds=$CleanupReserveMilliseconds) {
    InitializeGitBatchProcessRuntime
    try{return [R7GitBatchProcessRunner]::Run($Executable,$Arguments,$WorkingDirectory,$StandardInput,[R7GitExpectedObject[]]$ExpectedObjects,$TotalDeadlineMilliseconds,$CleanupReserveMilliseconds,$TerminationConfirmationMilliseconds,$StderrLimit)}catch{if($_.Exception.InnerException){throw $_.Exception.InnerException};throw}
}
function InvokeBoundedGitBatchProcessLaunchTest([string]$Executable,[string]$Arguments,[string]$WorkingDirectory,[byte[]]$StandardInput,[object[]]$ExpectedObjects,[string]$LaunchTestFault,[int]$TotalDeadlineMilliseconds=3000,[int]$CleanupReserveMilliseconds=800,[int]$StderrLimit=65536,[int]$TerminationConfirmationMilliseconds=$CleanupReserveMilliseconds,[string]$ReadinessPath='',[int]$ReadinessCount=0) {
    InitializeGitBatchProcessRuntime
    if([string]::IsNullOrEmpty($LaunchTestFault)){throw 'Launch test fault is required'}
    try{return [R7GitBatchProcessRunner]::RunForLaunchTest($Executable,$Arguments,$WorkingDirectory,$StandardInput,[R7GitExpectedObject[]]$ExpectedObjects,$TotalDeadlineMilliseconds,$CleanupReserveMilliseconds,$TerminationConfirmationMilliseconds,$StderrLimit,$LaunchTestFault,$ReadinessPath,$ReadinessCount)}catch{if($_.Exception.InnerException){throw $_.Exception.InnerException};throw}
}
function InvokeConcurrentGitLaunchIsolationTest([string]$Executable,[string]$SlowArguments,[string]$FastArguments,[string]$WorkingDirectory,[int]$TotalDeadlineMilliseconds=3000,[int]$CleanupReserveMilliseconds=800,[int]$StderrLimit=65536) {
    InitializeGitBatchProcessRuntime
    try{return [R7GitBatchProcessRunner]::RunConcurrentLaunchTest($Executable,$SlowArguments,$FastArguments,$WorkingDirectory,$TotalDeadlineMilliseconds,$CleanupReserveMilliseconds,$StderrLimit)}catch{if($_.Exception.InnerException){throw $_.Exception.InnerException};throw}
}
function SafeGitBatchStderr([string]$Value) {
    if($null-eq$Value){return ''};$safe=($Value-replace'[\r\n\x00-\x1f]',' ').Trim();if($safe.Length-gt256){return $safe.Substring(0,256)};return $safe
}
function AssertGitBatchProcessResult([bool]$Exited,[int]$ExitCode,[string]$Stderr,[string]$Context) {
    if(-not$Exited-or$ExitCode-ne0){Fail 'GIT_BATCH_PROCESS_FAILURE' (('context={0};exited={1};exit_code={2};stderr={3}'-f$Context,$Exited,$ExitCode,(SafeGitBatchStderr $Stderr)))}
}
function ReadStrictGitBatchHeader([IO.Stream]$Stream,[int]$Index,[string]$RequestedOid) {
    $headerBytes=[Collections.Generic.List[byte]]::new();$maximumHeaderBytes=128
    while($true){
        $value=$Stream.ReadByte()
        if($value-lt0){Fail 'GIT_BATCH_HEADER_INVALID' (('index={0};requested={1};reason={2}'-f$Index,$RequestedOid,$(if($headerBytes.Count-eq0){'missing-header'}else{'partial-header'})))}
        if($value-eq10){break}
        if($value-eq13-or$value-eq0-or$value-gt127){Fail 'GIT_BATCH_HEADER_INVALID' (('index={0};requested={1};reason=forbidden-header-byte;byte={2}'-f$Index,$RequestedOid,$value))}
        if($headerBytes.Count-ge$maximumHeaderBytes){Fail 'GIT_BATCH_HEADER_INVALID' (('index={0};requested={1};reason=header-too-long'-f$Index,$RequestedOid))}
        $headerBytes.Add([byte]$value)
    }
    if($headerBytes.Count-eq0){Fail 'GIT_BATCH_HEADER_INVALID' (('index={0};requested={1};reason=empty-header'-f$Index,$RequestedOid))}
    $header=[Text.Encoding]::ASCII.GetString($headerBytes.ToArray())
    if($header-cnotmatch'^([0-9a-f]{40}) ([^ ]+) ([^ ]+)$'){Fail 'GIT_BATCH_HEADER_INVALID' (('index={0};requested={1};reason=grammar'-f$Index,$RequestedOid))}
    $observedOid=[string]$Matches[1];$objectType=[string]$Matches[2];$sizeText=[string]$Matches[3]
    if($objectType-cne'blob'){Fail 'GIT_BATCH_OBJECT_TYPE_MISMATCH' (('index={0};requested={1};observed={2};type={3}'-f$Index,$RequestedOid,$observedOid,$objectType))}
    if($sizeText-cnotmatch'^(0|[1-9][0-9]*)$'){Fail 'GIT_BATCH_DECLARED_SIZE_INVALID' (('index={0};requested={1};observed={2};size={3}'-f$Index,$RequestedOid,$observedOid,$sizeText))}
    $size=[uint64]0
    if(-not[uint64]::TryParse($sizeText,[Globalization.NumberStyles]::None,[Globalization.CultureInfo]::InvariantCulture,[ref]$size)-or$size-gt[uint64]67108864){Fail 'GIT_BATCH_DECLARED_SIZE_INVALID' (('index={0};requested={1};observed={2};size={3}'-f$Index,$RequestedOid,$observedOid,$sizeText))}
    if($observedOid-cne$RequestedOid){Fail 'GIT_BATCH_OBJECT_ORDER_MISMATCH' (('index={0};requested={1};observed={2}'-f$Index,$RequestedOid,$observedOid))}
    return [ordered]@{observed_oid=$observedOid;size=[long]$size}
}
function ReadAuthenticatedGitBatch([IO.Stream]$Stream,[object[]]$ExpectedObjects) {
    $results=[Collections.Generic.List[object]]::new()
    for($index=0;$index-lt$ExpectedObjects.Count;$index++){
        $expected=$ExpectedObjects[$index];$requestedOid=[string]$expected.oid
        if($requestedOid-cnotmatch'^[0-9a-f]{40}$'){Fail 'GIT_BATCH_OBJECT_ORDER_MISMATCH' (('index={0};requested={1};reason=invalid-request-oid'-f$index,$requestedOid))}
        $header=ReadStrictGitBatchHeader $Stream $index $requestedOid;if(HasField $expected 'size' -and [long]$header.size-ne[long]$expected.size){Fail 'GIT_BATCH_EXPECTED_SIZE_MISMATCH' (('index={0};requested={1};expected={2};observed={3}'-f$index,$requestedOid,[long]$expected.size,[long]$header.size))};$size=[int][long]$header.size;$payload=New-Object byte[] $size;$offset=0
        while($offset-lt$size){$read=$Stream.Read($payload,$offset,$size-$offset);if($read-le0){Fail 'GIT_BATCH_PAYLOAD_TRUNCATED' (('index={0};requested={1};declared={2};actual={3}'-f$index,$requestedOid,$size,$offset))};$offset+=$read}
        $delimiter=$Stream.ReadByte();if($delimiter-ne10){Fail 'GIT_BATCH_PAYLOAD_DELIMITER_INVALID' (('index={0};requested={1};observed={2}'-f$index,$requestedOid,$delimiter))}
        $computedOid=GitBlobIdentity $payload
        if($computedOid-cne[string]$header.observed_oid-or$computedOid-cne$requestedOid){Fail 'GIT_BATCH_BLOB_IDENTITY_MISMATCH' (('index={0};requested={1};observed={2};computed={3}'-f$index,$requestedOid,[string]$header.observed_oid,$computedOid))}
        $results.Add([ordered]@{bytes=$payload;computed_oid=$computedOid;path=[string]$expected.path;size=[long]$payload.Length})
    }
    $trailing=$Stream.ReadByte();if($trailing-ne-1){Fail 'GIT_BATCH_TRAILING_OUTPUT' (('index={0};observed_byte={1}'-f$ExpectedObjects.Count,$trailing))}
    return $results.ToArray()
}
function ReadGitBlobBytes([string]$Blob) {
    if($Blob-cnotmatch'^[0-9a-f]{40}$'){Fail 'GIT_OBJECT_AUTHORITY_FAILURE' 'invalid-blob-id'}
    InitializeTreeAuthorityCache
    if($script:gitBlobByteCache.ContainsKey($Blob)){return [byte[]]$script:gitBlobByteCache[$Blob]}
    Fail 'GIT_OBJECT_AUTHORITY_FAILURE' ('unauthorized-or-uncached-blob='+$Blob)
}
function InitializeTreeAuthorityCache {
    if($null-eq(Get-Variable -Name treeAuthorityCacheKey -Scope Script -ErrorAction SilentlyContinue)){$script:treeAuthorityCacheKey='';$script:treeAuthorityCache=@{};$script:gitBlobByteCache=@{}}
    $cacheKey=$repositoryRoot+'|'+$SourceCommit;if($script:treeAuthorityCacheKey-ceq$cacheKey){return}
    $auditRoot=Join-Path $repositoryRoot $packageRelativeRoot.Replace('/','\');$paths=[Collections.Generic.List[string]]::new()
    foreach($path in @(Get-ChildItem -LiteralPath (Join-Path $auditRoot 'Source') -Filter '*.cs' -File|Sort-Object Name|ForEach-Object FullName)+@(Join-Path $auditRoot 'BuildInputs\R7BuildIdentityContract.cs')){$paths.Add((Relative $repositoryRoot $path))}
    $paths.Add($packageRelativeRoot+'/build_unit2_upgrade_authority.ps1');foreach($contract in @(ConfigurationContract)){if([string]$contract.class-ceq'COMMITTED'){$paths.Add([string]$contract.relative)}}
    $required=@($paths|Sort-Object -Unique);$rows=@(GitArgs (@('ls-tree','-l','--full-tree',$SourceCommit,'--')+$required));$tree=@{}
    foreach($row in $rows){if([string]$row-notmatch'^(100644|100755) blob ([0-9a-f]{40})\s+([0-9]+)\t(.+)$'){Fail 'GIT_TREE_OBJECT_MISMATCH' 'unexpected-tree-row'};$tree[[string]$Matches[4]]=[ordered]@{blob=[string]$Matches[2];mode=[string]$Matches[1];size=[long]$Matches[3]}}
    foreach($path in $required){if(-not$tree.ContainsKey($path)){Fail 'GIT_TREE_OBJECT_MISMATCH' ($path+'/missing-or-nonblob')}}
    $safe=$repositoryRoot.Replace('\','/');$quotedRepository='"'+$repositoryRoot.Replace('"','\"')+'"';$quotedSafe='"safe.directory='+$safe.Replace('"','\"')+'"';$arguments='--no-pager -c '+$quotedSafe+' -c core.fsmonitor=false -c core.hooksPath=NUL -C '+$quotedRepository+' cat-file --batch';$authority=@{};$blobBytes=@{};$expected=[Collections.Generic.List[object]]::new();$request=[Text.StringBuilder]::new()
    foreach($path in $required){$blob=[string]$tree[$path].blob;$expected.Add((NewGitExpectedObject $blob $path ([long]$tree[$path].size)));[void]$request.Append($blob).Append("`n")}
    $execution=InvokeBoundedGitBatchProcess $git $arguments $repositoryRoot ([Text.Encoding]::ASCII.GetBytes($request.ToString())) $expected.ToArray()
    $frames=@($execution.Objects);for($index=0;$index-lt$required.Count;$index++){$path=[string]$required[$index];$expectedBlob=[string]$tree[$path].blob;$bytes=[byte[]]$frames[$index].Bytes;$authority[$path]=[ordered]@{git_blob_identity=$expectedBlob;mode=[string]$tree[$path].mode;path=$path;raw_sha256=(BytesHash $bytes);size=[long]$bytes.Length};$blobBytes[$expectedBlob]=$bytes}
    $script:treeAuthorityCacheKey=$cacheKey;$script:treeAuthorityCache=$authority;$script:gitBlobByteCache=$blobBytes
}
function ExactTreeBlobAuthority([string]$RelativePath) {
    $path=AssertCanonicalInputPath $RelativePath 'git-tree';InitializeTreeAuthorityCache;if(-not$script:treeAuthorityCache.ContainsKey($path)){Fail 'GIT_TREE_OBJECT_MISMATCH' ($path+'/unauthorized')};return $script:treeAuthorityCache[$path]
}
function Fail([string]$Code,[string]$Detail) { throw ([IO.InvalidDataException]::new($Code + '|' + $Detail)) }
function HasField([object]$Value,[string]$Name) {
    if($null-eq$Value){return $false}
    if($Value -is [Collections.IDictionary]){return $Value.Contains($Name)}
    return $null-ne($Value.PSObject.Properties[$Name])
}
function FieldValue([object]$Value,[string]$Name) {
    if(-not(HasField $Value $Name)){return $null}
    if($Value -is [Collections.IDictionary]){return $Value[$Name]}
    return ($Value.PSObject.Properties[$Name]).Value
}
function FieldNames([object]$Value) {
    if($null-eq$Value){return @()}
    if($Value -is [Collections.IDictionary]){return @($Value.Keys|ForEach-Object{[string]$_})}
    return @($Value.PSObject.Properties|ForEach-Object{[string]$_.Name})
}
function JsonKind([object]$Value) {
    if($null-eq$Value){return 'NULL'}
    if($Value-is[string]){return 'STRING'}
    if($Value-is[bool]){return 'BOOLEAN'}
    if($Value-is[byte]-or$Value-is[sbyte]-or$Value-is[int16]-or$Value-is[uint16]-or$Value-is[int32]-or$Value-is[uint32]-or$Value-is[int64]-or$Value-is[uint64]){return 'INTEGER'}
    if($Value-is[decimal]){if([decimal]::Truncate([decimal]$Value)-eq[decimal]$Value){return 'INTEGER'};return 'NUMBER_NONINTEGER'}
    if($Value-is[Array]){return 'ARRAY'}
    if($Value-is[Collections.IDictionary]-or$Value-is[PSCustomObject]){return 'OBJECT'}
    return 'OTHER'
}
function ExactJsonEqual([object]$Expected,[object]$Observed) {
    $expectedKind=JsonKind $Expected;$observedKind=JsonKind $Observed
    if($expectedKind-cne$observedKind){return $false}
    switch($expectedKind){
        'NULL'{return $true}
        'STRING'{return [string]$Expected-ceq[string]$Observed}
        'BOOLEAN'{return [bool]$Expected-eq[bool]$Observed}
        'INTEGER'{return [decimal]$Expected-eq[decimal]$Observed}
        'ARRAY'{
            $expectedItems=@($Expected);$observedItems=@($Observed);if($expectedItems.Count-ne$observedItems.Count){return $false}
            for($index=0;$index-lt$expectedItems.Count;$index++){if(-not(ExactJsonEqual $expectedItems[$index] $observedItems[$index])){return $false}}
            return $true
        }
        'OBJECT'{
            $expectedNames=@(FieldNames $Expected);$observedNames=@(FieldNames $Observed)
            if($expectedNames.Count-ne$observedNames.Count){return $false}
            foreach($name in $expectedNames){if($observedNames-cnotcontains$name-or-not(ExactJsonEqual (FieldValue $Expected $name) (FieldValue $Observed $name))){return $false}}
            return $true
        }
        default{return $false}
    }
}
function DiagnosticValue([object]$Value) {
    $kind=JsonKind $Value
    if($kind-ceq'NULL'){return 'NULL:<null>'}
    return ($kind+':'+($Value|ConvertTo-Json -Depth 20 -Compress))
}
function FailInputField([string]$Role,[string]$InputPath,[string]$Field,[object]$Expected,[object]$Observed) {
    Fail 'COMPILER_INPUT_IDENTITY_MISMATCH' (('role={0};input={1};field={2};expected={3};observed={4}' -f $Role,$InputPath,$Field,(DiagnosticValue $Expected),(DiagnosticValue $Observed)))
}
function FailInputType([string]$Role,[string]$InputPath,[string]$Field,[string]$ExpectedKind,[object]$Observed) {
    Fail 'COMPILER_INPUT_TYPE_MISMATCH' (('role={0};input={1};field={2};expected_type={3};observed={4}' -f $Role,$InputPath,$Field,$ExpectedKind,(DiagnosticValue $Observed)))
}
function AssertKind([string]$Role,[string]$InputPath,[string]$Field,[object]$Value,[string]$ExpectedKind) {
    if((JsonKind $Value)-cne$ExpectedKind){FailInputType $Role $InputPath $Field $ExpectedKind $Value}
}
function AssertSha256([string]$Role,[string]$InputPath,[string]$Field,[object]$Value) {
    AssertKind $Role $InputPath $Field $Value 'STRING';if([string]$Value-cnotmatch'^[0-9a-f]{64}$'){FailInputField $Role $InputPath $Field '<lowercase-sha256>' $Value}
}
function AssertGitBlob([string]$Role,[string]$InputPath,[string]$Field,[object]$Value) {
    AssertKind $Role $InputPath $Field $Value 'STRING';if([string]$Value-cnotmatch'^[0-9a-f]{40}$'){FailInputField $Role $InputPath $Field '<lowercase-git-blob>' $Value}
}
function AssertCanonicalInputPath([string]$Path,[string]$Context) {
    if([string]::IsNullOrWhiteSpace($Path)-or[IO.Path]::IsPathRooted($Path)){Fail 'COMPILER_INPUT_PATH_INVALID' ($Context+'/'+$Path)}
    $normalized=$Path.Replace('\','/')
    $segments=@($normalized.Split('/'))
    if($normalized-cne$Path-or@($segments|Where-Object{$_-ceq''-or$_-ceq'.'-or$_-ceq'..'}).Count-ne0){Fail 'COMPILER_INPUT_PATH_INVALID' ($Context+'/'+$Path)}
    return $normalized
}
function AssertExactObject([string]$Role,[string]$InputPath,[string]$Field,[object]$Expected,[object]$Observed) {
    if(-not(ExactJsonEqual $Expected $Observed)){FailInputField $Role $InputPath $Field $Expected $Observed}
}
function AssertCompilerInputSchema([string]$Role,[object]$InputRecord) {
    if((JsonKind $InputRecord)-cne'OBJECT'){FailInputType $Role '<unknown>' 'compiler_input' 'OBJECT' $InputRecord}
    $path=if(HasField $InputRecord 'path'){DiagnosticValue (FieldValue $InputRecord 'path')}else{'<missing>'}
    $required=@('generation_rule','generator','git_blob_identity','mode','path','raw_sha256','size')
    $observed=@(FieldNames $InputRecord)
    foreach($field in $required){if($observed-cnotcontains$field){Fail 'COMPILER_INPUT_SCHEMA_MISMATCH' (('role={0};input={1};missing={2}'-f$Role,$path,$field))}}
    foreach($field in $observed){if($required-cnotcontains$field){Fail 'COMPILER_INPUT_SCHEMA_MISMATCH' (('role={0};input={1};unknown={2}'-f$Role,$path,$field))}}
}
function Derive([string]$Domain,[string[]]$Values) {
    $builder=[Text.StringBuilder]::new();[void]$builder.Append($Domain.Length).Append(':').Append($Domain)
    foreach($value in $Values){$item=if($null-eq$value){''}else{[string]$value};[void]$builder.Append('|').Append($item.Length).Append(':').Append($item)}
    return TextHash $builder.ToString()
}
function MeasuredFileRow([string]$Path) {
    $full=[IO.Path]::GetFullPath($Path);if(-not(Test-Path -LiteralPath $full -PathType Leaf)){Fail 'CONFIGURATION_INPUT_AUTHORITY_MISMATCH' ($full+'/missing')}
    if(((Get-Item -LiteralPath $full -Force).Attributes-band[IO.FileAttributes]::ReparsePoint)-ne0){Fail 'CONFIGURATION_INPUT_AUTHORITY_MISMATCH' ($full+'/reparse')}
    return [ordered]@{path=$full;raw_sha256=(Hash $full);size=[long](Get-Item -LiteralPath $full).Length}
}
function CommittedAuthorityRows([hashtable]$Overrides) {
    $auditRoot=Join-Path $repositoryRoot $packageRelativeRoot.Replace('/','\');$sourceRoot=Join-Path $auditRoot 'Source';$identityContract=Join-Path $auditRoot 'BuildInputs\R7BuildIdentityContract.cs'
    $paths=@(Get-ChildItem -LiteralPath $sourceRoot -Filter '*.cs' -File|Sort-Object Name|ForEach-Object FullName)+$identityContract
    return @($paths|ForEach-Object{
        $relative=Relative $repositoryRoot $_;$committed=ExactTreeBlobAuthority $relative
        $compilerSha=if($Overrides.ContainsKey('compiler_sha256:'+ $relative)){[string]$Overrides['compiler_sha256:'+ $relative]}else{Hash $_}
        $compilerSize=if($Overrides.ContainsKey('compiler_size:'+ $relative)){[long]$Overrides['compiler_size:'+ $relative]}else{[long](Get-Item -LiteralPath $_).Length}
        if($compilerSha-cne[string]$committed.raw_sha256-or$compilerSize-ne[long]$committed.size){Fail 'COMPILER_SOURCE_MATERIALIZATION_MISMATCH' ($relative+'/EXACT_GIT_BLOB_BYTES_REQUIRED')}
        $committed
    })
}
function GeneratedSourceContract {
    return @(
        [ordered]@{path='Generated/R7Unit2BuildBootstrap.g.cs';generation_rule='R7_UNIT2_BUILD_BOOTSTRAP_IDENTITY_V2';policy_input=$false;roles=@('BUILD_BOOTSTRAP_ARTIFACT_TOOL','BUILD_BOOTSTRAP_PROTECTED_METADATA_TOOL')},
        [ordered]@{path='Generated/R7Unit2ClientShared.g.cs';generation_rule='R7_UNIT2_CLIENT_SHARED_IDENTITY_V2';policy_input=$false;roles=@('UPGRADE_CLIENT','UPGRADE_PROTOCOL_PROBE','UPGRADE_PUBLIC_VERIFIER')},
        [ordered]@{path='Generated/R7Unit2Service.g.cs';generation_rule='R7_UNIT2_SERVICE_IDENTITY_V2';policy_input=$true;roles=@('UPGRADE_AUTHORITY')},
        [ordered]@{path='Generated/R7PackagedTools.g.cs';generation_rule='R7_UNIT2_PACKAGED_TOOLS_IDENTITY_V2';policy_input=$true;roles=@('PACKAGED_ARTIFACT_TOOL','PACKAGED_PROTECTED_METADATA_TOOL')}
    )
}
function GroundedGeneratorAuthority([hashtable]$Overrides) {
    $relative=$packageRelativeRoot+'/build_unit2_upgrade_authority.ps1';$path=Join-Path $repositoryRoot $relative.Replace('/','\')
    if(-not(Test-Path -LiteralPath $path -PathType Leaf)){Fail 'GENERATED_SOURCE_AUTHORITY_MISMATCH' ($relative+'/missing')}
    $committed=ExactTreeBlobAuthority $relative
    $materializedSha=if($Overrides.ContainsKey('generator_sha256')){[string]$Overrides.generator_sha256}else{Hash $path};$materializedSize=if($Overrides.ContainsKey('generator_size')){[long]$Overrides.generator_size}else{[long](Get-Item -LiteralPath $path).Length}
    if($materializedSha-cne[string]$committed.raw_sha256-or$materializedSize-ne[long]$committed.size){Fail 'GENERATOR_MATERIALIZATION_MISMATCH' ($relative+'/EXACT_GIT_BLOB_BYTES_REQUIRED')}
    return [ordered]@{git_blob_identity=$committed.git_blob_identity;path=$relative;raw_sha256=$committed.raw_sha256}
}
function ConfigurationContract {
    return @(
        [ordered]@{role='AUTHORITY_SOURCE_MANIFEST';class='COMMITTED';relative=$packageRelativeRoot+'/AuthoritySources/authority_source_manifest.json'},
        [ordered]@{role='BOOTSTRAP_RECORD';class='BOOTSTRAP';leaf='upgrade_authority_bootstrap_record.json'},
        [ordered]@{role='CASE_DEFINITIONS';class='COMMITTED';relative=$packageRelativeRoot+'/immutable_case_definitions.json'},
        [ordered]@{role='COVERAGE_PROOF';class='COMMITTED';relative=$packageRelativeRoot+'/exact_byte_coverage_proof.json'},
        [ordered]@{role='DEPENDENCY_MANIFEST';class='TARGET';suffix='Generated/dependency_manifest.json'},
        [ordered]@{role='EXPECTATIONS';class='COMMITTED';relative=$packageRelativeRoot+'/immutable_expectations.json'},
        [ordered]@{role='HISTORICAL_CLASSIFICATION_REGISTRY';class='COMMITTED';relative=$packageRelativeRoot+'/historical_classification_registry.json'},
        [ordered]@{role='NEGATIVE_CASE_REGISTRY';class='COMMITTED';relative=$packageRelativeRoot+'/unit2_build_closure_negative_cases.json'},
        [ordered]@{role='PREFLIGHT_HOST_STATE';class='PREFLIGHT';leaf='host-state.json'},
        [ordered]@{role='PRINCIPAL_REGISTRY';class='COMMITTED';relative=$packageRelativeRoot+'/service_principal_registry.json'},
        [ordered]@{role='REQUIREMENT_REGISTRY';class='COMMITTED';relative=$packageRelativeRoot+'/governed_requirement_registry.json'},
        [ordered]@{role='SCRIPT_REGISTRY';class='COMMITTED';relative=$packageRelativeRoot+'/governed_script_registry.json'},
        [ordered]@{role='TARGET_AUTHORITY_PACKAGE_MANIFEST';class='TARGET';suffix='Generated/authority_package_manifest.json'},
        [ordered]@{role='TARGET_BUILD_ORCHESTRATOR_RECEIPT';class='TARGET';suffix='Generated/build_orchestrator_receipt.json'},
        [ordered]@{role='TARGET_BUILD_RECEIPT';class='TARGET';suffix='Generated/build_receipt.json'},
        [ordered]@{role='TARGET_BUILD_SUMMARY';class='TARGET';suffix='build_summary.json'},
        [ordered]@{role='TARGET_POLICY';class='TARGET';suffix='Generated/terminal_authority_v4_policy.json'},
        [ordered]@{role='TARGET_TRANSITION_TEMPLATE';class='TARGET';suffix='Generated/transition_request_template.json'},
        [ordered]@{role='TERMINAL_KEY_METADATA';class='TARGET';suffix='Generated/terminal_key_file_metadata.json'},
        [ordered]@{role='UNIT2_AUTHORIZATION_SCOPE';class='COMMITTED';relative=$packageRelativeRoot+'/unit2_authorization_scope.json'},
        [ordered]@{role='UNIT2_COMPLETION_SCRIPT';class='COMMITTED';relative=$packageRelativeRoot+'/complete_unit2_upgrade_authority.ps1'},
        [ordered]@{role='UNIT2_STOPPED_INSTALL_CONTRACT';class='COMMITTED';relative=$packageRelativeRoot+'/unit2_stopped_install_contract.json'},
        [ordered]@{role='UPGRADE_KEY_METADATA';class='TARGET';suffix='Generated/upgrade_key_file_metadata.json'},
        [ordered]@{role='UPGRADE_PUBLIC_CERTIFICATE';class='BOOTSTRAP';leaf='upgrade_authority_public_from_store.cer'},
        [ordered]@{role='UTILITY_REGISTRY';class='COMMITTED';relative=$packageRelativeRoot+'/external_utility_registry.json'}
    )
}
function AssertConfigurationSchema([object]$Row,[string]$Context) {
    if((JsonKind $Row)-cne'OBJECT'){Fail 'CONFIGURATION_INPUT_AUTHORITY_MISMATCH' ($Context+'/not-object')};$required=@('path','raw_sha256','role','size');$names=@(FieldNames $Row)
    if($names.Count-ne$required.Count-or@($required|Where-Object{$names-cnotcontains$_}).Count-ne0){Fail 'CONFIGURATION_INPUT_AUTHORITY_MISMATCH' ($Context+'/schema')}
    AssertKind 'CONFIGURATION_AUTHORITY' $Context 'path' $Row.path 'STRING';AssertSha256 'CONFIGURATION_AUTHORITY' $Context 'raw_sha256' $Row.raw_sha256;AssertKind 'CONFIGURATION_AUTHORITY' $Context 'role' $Row.role 'STRING';AssertKind 'CONFIGURATION_AUTHORITY' $Context 'size' $Row.size 'INTEGER'
}
function GroundedConfigurationInventory([object]$Receipt) {
    if((JsonKind $Receipt.configuration_inputs)-cne'ARRAY'){Fail 'CONFIGURATION_INPUT_AUTHORITY_MISMATCH' 'inventory/not-array'}
    $contracts=@(ConfigurationContract);$observed=@($Receipt.configuration_inputs);if($observed.Count-ne$contracts.Count){Fail 'CONFIGURATION_INPUT_AUTHORITY_MISMATCH' 'inventory/count'}
    $summaryRows=@($observed|Where-Object{(JsonKind $_.role)-ceq'STRING'-and[string]$_.role-ceq'TARGET_BUILD_SUMMARY'});if($summaryRows.Count-ne1-or(JsonKind $summaryRows[0].path)-cne'STRING'){Fail 'CONFIGURATION_INPUT_AUTHORITY_MISMATCH' 'TARGET_BUILD_SUMMARY/locator'}
    $targetRoot=[IO.Path]::GetFullPath((Split-Path -Parent ([string]$summaryRows[0].path)));$temp=[IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')+'\';if(-not$targetRoot.StartsWith($temp,[StringComparison]::OrdinalIgnoreCase)){Fail 'CONFIGURATION_INPUT_AUTHORITY_MISMATCH' 'target-root/not-temp'}
    $bootstrapRows=@($observed|Where-Object{(JsonKind $_.role)-ceq'STRING'-and[string]$_.role-ceq'BOOTSTRAP_RECORD'});if($bootstrapRows.Count-ne1-or(JsonKind $bootstrapRows[0].path)-cne'STRING'){Fail 'CONFIGURATION_INPUT_AUTHORITY_MISMATCH' 'BOOTSTRAP_RECORD/locator'};$bootstrapRoot=[IO.Path]::GetFullPath((Split-Path -Parent ([string]$bootstrapRows[0].path)))
    $grounded=[Collections.Generic.List[object]]::new()
    for($index=0;$index-lt$contracts.Count;$index++){
        $contract=$contracts[$index];$row=$observed[$index];$role=[string]$contract.role;AssertConfigurationSchema $row $role
        if([string]$row.role-cne$role){Fail 'CONFIGURATION_INPUT_AUTHORITY_MISMATCH' ($role+'/order')}
        switch([string]$contract.class){
            'COMMITTED'{$tree=ExactTreeBlobAuthority ([string]$contract.relative);$expectedPath=[IO.Path]::GetFullPath((Join-Path $repositoryRoot ([string]$contract.relative).Replace('/','\')));$measured=MeasuredFileRow $expectedPath;if([string]$measured.raw_sha256-cne[string]$tree.raw_sha256-or[long]$measured.size-ne[long]$tree.size){Fail 'CONFIGURATION_INPUT_MATERIALIZATION_MISMATCH' ($role+'/EXACT_GIT_BLOB_BYTES_REQUIRED')}}
            'TARGET'{$expectedPath=[IO.Path]::GetFullPath((Join-Path $targetRoot ([string]$contract.suffix).Replace('/','\')));$measured=MeasuredFileRow $expectedPath}
            'BOOTSTRAP'{$expectedPath=[IO.Path]::GetFullPath((Join-Path $bootstrapRoot ([string]$contract.leaf)));$measured=MeasuredFileRow $expectedPath}
            'PREFLIGHT'{$actualPath=[IO.Path]::GetFullPath([string]$row.path);if([IO.Path]::GetFileName($actualPath)-cne[string]$contract.leaf-or-not$actualPath.StartsWith($temp,[StringComparison]::OrdinalIgnoreCase)){Fail 'CONFIGURATION_INPUT_AUTHORITY_MISMATCH' ($role+'/path')};$expectedPath=$actualPath;$measured=MeasuredFileRow $expectedPath}
            default{Fail 'CONFIGURATION_INPUT_AUTHORITY_MISMATCH' ($role+'/classification')}
        }
        $expected=[ordered]@{path=$expectedPath;raw_sha256=$measured.raw_sha256;role=$role;size=$measured.size};if(-not(ExactJsonEqual $expected $row)){Fail 'CONFIGURATION_INPUT_AUTHORITY_MISMATCH' $role};$grounded.Add($expected)
    }
    $byRole=@{};foreach($row in $grounded){$byRole[[string]$row.role]=$row}
    if([string]$byRole.UPGRADE_PUBLIC_CERTIFICATE.raw_sha256-cne'2ef057a2c09d53da7096d92a09774b68986cf26c5d44000e1ec804d8ce837d7b'){Fail 'CONFIGURATION_INPUT_AUTHORITY_MISMATCH' 'UPGRADE_PUBLIC_CERTIFICATE/fixed-identity'}
    $summary=ReadJson ([string]$byRole.TARGET_BUILD_SUMMARY.path);if([string]$summary.source_commit-cne'd22610e96496f7a9209edff36442be843f06fed4'-or[string]$summary.source_tree-cne'8a627b54537e4c26835345907fc5181205ce496f'){Fail 'CONFIGURATION_INPUT_AUTHORITY_MISMATCH' 'TARGET_BUILD_SUMMARY/source'}
    $bootstrap=ReadJson ([string]$byRole.BOOTSTRAP_RECORD.path);if([string]$bootstrap.source_commit-cne'b07fd42a20ed612d53070aa1d1ae1bda6ace1e93'-or[string]$bootstrap.source_tree-cne'7d0d92000192b913f9ff3fba6e57ce7308d2f3be'-or[string]$bootstrap.public_certificate_sha256-cne[string]$byRole.UPGRADE_PUBLIC_CERTIFICATE.raw_sha256){Fail 'CONFIGURATION_INPUT_AUTHORITY_MISMATCH' 'BOOTSTRAP_RECORD/source'}
    $preflight=ReadJson ([string]$byRole.PREFLIGHT_HOST_STATE.path);if([string]$preflight.artifact_type-cne'R7_REMEDIATION_HOST_STATE_CAPTURE'-or[string]$preflight.phase-cne'PRECHANGE'-or[int64]$preflight.ledger_entry_file_count-ne678){Fail 'CONFIGURATION_INPUT_AUTHORITY_MISMATCH' 'PREFLIGHT_HOST_STATE/semantics'}
    return $grounded.ToArray()
}
function GroundedUtility([string]$Role,[object]$Registry) {
    $rows=@($Registry.utilities|Where-Object{[string]$_.role-ceq$Role});if($rows.Count-ne1){Fail 'BUILD_INPUT_CLOSURE_MISMATCH' ('utility/'+$Role+'/authority')};$row=$rows[0];$path=[IO.Path]::GetFullPath([string]$row.path)
    if(-not(Test-Path -LiteralPath $path -PathType Leaf)-or(Hash $path)-cne[string]$row.measurement.sha256-or[long](Get-Item -LiteralPath $path).Length-ne[long]$row.measurement.size){Fail 'BUILD_INPUT_CLOSURE_MISMATCH' ('utility/'+$Role+'/measurement')};return $row
}
function RecomputeBuildInputClosure([object[]]$CommittedRows,[object[]]$ConfigurationRows,[hashtable]$Overrides) {
    $sourceParts=@($CommittedRows|ForEach-Object{[string]$_.path+'|'+[string]$_.git_blob_identity+'|'+[string]$_.raw_sha256+'|'+[string]$_.size+'|'+[string]$_.mode})
    $configurationParts=@($ConfigurationRows|ForEach-Object{[string]$_.role+'|'+[string]$_.raw_sha256+'|'+[string]$_.size})
    $registry=ReadJson (Join-Path $repositoryRoot ($packageRelativeRoot+'/external_utility_registry.json').Replace('/','\'));$toolchainParts=[Collections.Generic.List[string]]::new()
    foreach($tool in @(@('CSC','CSC_COMPILER'),@('ILDASM','ILDASM_TOOL'),@('GIT','GIT_BUILD_AND_VERIFICATION'),@('POWERSHELL','POWERSHELL_ORCHESTRATOR'))){$row=GroundedUtility $tool[1] $registry;$toolchainParts.Add(([string]$tool[0]+'|'+[string]$row.measurement.sha256+'|'+[string]$row.measurement.size))}
    foreach($role in @('COMPILER_REFERENCE_mscorlib.dll','COMPILER_REFERENCE_System.dll','COMPILER_REFERENCE_System.Core.dll','COMPILER_REFERENCE_System.Security.dll','COMPILER_REFERENCE_System.ServiceProcess.dll')){$row=GroundedUtility $role $registry;$toolchainParts.Add('REFERENCE|'+[string]$row.measurement.sha256+'|'+[string]$row.measurement.size)}
    $roleDefinitions=@(
        @('BUILD_BOOTSTRAP_ARTIFACT_TOOL','RandleAI.R7Remediation.R7ArtifactToolProgram','UNIT2_BUILD_BOOTSTRAP_ARTIFACT_TOOL','R7ArtifactTool.build-bootstrap.exe','DISPOSABLE_BUILD_ONLY'),@('BUILD_BOOTSTRAP_PROTECTED_METADATA_TOOL','RandleAI.R7Remediation.R7ArtifactToolProgram','UNIT2_BUILD_BOOTSTRAP_PROTECTED_METADATA_TOOL','R7ProtectedMetadataTool.build-bootstrap.exe','DISPOSABLE_BUILD_ONLY'),@('UPGRADE_CLIENT','RandleAI.R7Remediation.R7Unit2UpgradeClientProgram','UNIT2_CLIENT','RandleTerminalUpgradeClient.exe','C:\Program Files\RandleAI\TerminalUpgradeAuthority\RandleTerminalUpgradeClient.exe'),@('UPGRADE_PUBLIC_VERIFIER','RandleAI.R7Remediation.R7Unit2UpgradePublicVerifierProgram','UNIT2_PUBLIC_VERIFIER','RandleTerminalUpgradePublicVerifier.exe','C:\Program Files\RandleAI\TerminalUpgradeAuthority\RandleTerminalUpgradePublicVerifier.exe'),@('UPGRADE_PROTOCOL_PROBE','RandleAI.R7Remediation.R7Unit2UpgradeProbeProgram','UNIT2_PROTOCOL_PROBE','RandleTerminalUpgradeProtocolProbe.exe','C:\Program Files\RandleAI\TerminalUpgradeAuthority\RandleTerminalUpgradeProtocolProbe.exe'),@('UPGRADE_AUTHORITY','RandleAI.R7Remediation.R7Unit2UpgradeServiceProgram','UNIT2_SERVICE','RandleTerminalUpgradeAuthority.exe','C:\Program Files\RandleAI\TerminalUpgradeAuthority\RandleTerminalUpgradeAuthority.exe'),@('PACKAGED_ARTIFACT_TOOL','RandleAI.R7Remediation.R7ArtifactToolProgram','UNIT2_PACKAGED_ARTIFACT_TOOL','R7ArtifactTool.exe','C:\ProgramData\RandleAI\TerminalUpgradeAuthority\BuildTools\R7ArtifactTool.exe'),@('PACKAGED_PROTECTED_METADATA_TOOL','RandleAI.R7Remediation.R7ArtifactToolProgram','UNIT2_PACKAGED_PROTECTED_METADATA_TOOL','R7ProtectedMetadataTool.exe','C:\ProgramData\RandleAI\TerminalUpgradeAuthority\BuildTools\R7ProtectedMetadataTool.exe'))
    $roleParts=@($roleDefinitions|ForEach-Object{$_[0]+'|'+$_[1]+'|'+$_[2]+'|'+$_[3]+'|'+$_[4]})
    $configByRole=@{};foreach($row in $ConfigurationRows){$configByRole[[string]$row.role]=$row};$template=ReadJson ([string]$configByRole.TARGET_TRANSITION_TEMPLATE.path);$targetManifest=ReadJson ([string]$configByRole.TARGET_AUTHORITY_PACKAGE_MANIFEST.path);$components=[Collections.Generic.List[object]]::new();$paths=[Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    foreach($component in @($template.components)){$components.Add([ordered]@{final_path=[string]$component.final_path;role=[string]$component.role;sha256=[string]$component.sha256;staging_relative_path=[string]$component.staging_relative_path});[void]$paths.Add([string]$component.staging_relative_path)}
    $extra=0;foreach($file in @($targetManifest.files|Sort-Object staging_relative_path)){if($paths.Contains([string]$file.staging_relative_path)){continue};$components.Add([ordered]@{final_path=[string]$file.final_path;role=('PACKAGE_FILE_'+$extra.ToString('D4')+'_'+([string]$file.raw_sha256).Substring(0,16));sha256=[string]$file.raw_sha256;staging_relative_path=[string]$file.staging_relative_path});[void]$paths.Add([string]$file.staging_relative_path);$extra++}
    $componentParts=@($components|Sort-Object role|ForEach-Object{[string]$_.role+'|'+[string]$_.staging_relative_path+'|'+[string]$_.sha256+'|'+[string]$_.final_path})
    $closureInputs=@($sourceParts+$configurationParts+$toolchainParts.ToArray()+$requiredSwitches+$roleParts+$componentParts)
    if($Overrides.ContainsKey('closure_reorder')-and$closureInputs.Count-gt1){$value=$closureInputs[0];$closureInputs[0]=$closureInputs[1];$closureInputs[1]=$value}
    return Derive 'R7_UNIT2_BUILD_INPUT_CLOSURE_V2' $closureInputs
}
function GroundedPolicyAuthority([object]$Receipt,[string]$Closure,[hashtable]$Overrides) {
    $path=if($Overrides.ContainsKey('policy_path')){[string]$Overrides.policy_path}else{Join-Path $build 'Generated\unit2_upgrade_policy.json'}
    if(-not(Test-Path -LiteralPath $path -PathType Leaf)){Fail 'POLICY_INPUT_AUTHORITY_MISMATCH' 'artifact/missing'};$measured=MeasuredFileRow $path;$policy=ReadJson $path
    if([string]$policy.artifact_type-cne'R7_UNIT2_SEPARATE_UPGRADE_AUTHORITY_POLICY'-or[string]$policy.source_bindings.provisioning_commit-cne[string]$Receipt.source_commit-or[string]$policy.source_bindings.provisioning_tree-cne[string]$Receipt.source_tree-or[string]$policy.source_bindings.target_commit-cne'd22610e96496f7a9209edff36442be843f06fed4'-or[string]$policy.source_bindings.target_tree-cne'8a627b54537e4c26835345907fc5181205ce496f'){Fail 'POLICY_INPUT_AUTHORITY_MISMATCH' 'source-binding'}
    $manifest=ReadJson (Join-Path $build 'unit2_build_manifest.json');$installPath=Join-Path $build 'Install\unit2_upgrade_policy.json'
    if([string]$Receipt.policy_sha256-cne[string]$measured.raw_sha256-or[string]$manifest.policy_sha256-cne[string]$measured.raw_sha256-or-not(Test-Path -LiteralPath $installPath -PathType Leaf)-or(Hash $installPath)-cne[string]$measured.raw_sha256-or[long](Get-Item -LiteralPath $installPath).Length-ne[long]$measured.size){Fail 'POLICY_INPUT_AUTHORITY_MISMATCH' 'receipt/hash'}
    return [ordered]@{path=$measured.path;raw_sha256=$measured.raw_sha256;size=$measured.size}
}
function ExpectedGeneratedSourceInputs([object[]]$ConfigurationRows,[object[]]$CommittedRows,[object]$Generator,[string]$Closure,[object]$Policy,[bool]$PolicyInput) {
    $inputs=[Collections.Generic.List[object]]::new()
    foreach($row in $ConfigurationRows){
        $inputs.Add([ordered]@{identity=[string]$row.raw_sha256;role=[string]$row.role})
    }
    foreach($row in $CommittedRows){$inputs.Add([ordered]@{identity=[string]$row.raw_sha256;role=('COMPILER_SOURCE:'+[string]$row.path)})}
    $inputs.Add([ordered]@{identity=$Closure;role='BUILD_INPUT_CLOSURE'});$inputs.Add([ordered]@{identity=[string]$Generator.raw_sha256;role='GENERATOR_SCRIPT'})
    if($PolicyInput){$inputs.Add([ordered]@{identity=[string]$Policy.raw_sha256;role='COMPLETED_UNIT2_POLICY'})}
    return $inputs.ToArray()
}
function AssertSourceAuthority([object]$Observed,[object]$Expected,[string]$Context) {
    if((JsonKind $Observed)-cne'OBJECT'){Fail 'COMMITTED_SOURCE_AUTHORITY_MISMATCH' ($Context+'/not-object')}
    $fields=@('git_blob_identity','mode','path','raw_sha256','size');$names=@(FieldNames $Observed)
    if($names.Count-ne$fields.Count-or@($fields|Where-Object{$names-cnotcontains$_}).Count-ne0){Fail 'COMMITTED_SOURCE_AUTHORITY_MISMATCH' ($Context+'/schema')}
    AssertGitBlob 'COMMITTED_AUTHORITY' $Context 'git_blob_identity' $Observed.git_blob_identity;AssertKind 'COMMITTED_AUTHORITY' $Context 'mode' $Observed.mode 'STRING';AssertKind 'COMMITTED_AUTHORITY' $Context 'path' $Observed.path 'STRING';AssertSha256 'COMMITTED_AUTHORITY' $Context 'raw_sha256' $Observed.raw_sha256;AssertKind 'COMMITTED_AUTHORITY' $Context 'size' $Observed.size 'INTEGER'
    if(-not(ExactJsonEqual $Expected $Observed)){Fail 'COMMITTED_SOURCE_AUTHORITY_MISMATCH' $Context}
}
function AssertGeneratedOutputAuthority([string]$Path,[string]$Closure,[object]$Policy,[bool]$PolicyInput,[string]$SourceCommitValue,[string]$SourceTreeValue) {
    $text=[IO.File]::ReadAllText($Path)
    foreach($binding in @([ordered]@{field='BuildInputClosureSha256';value=$Closure},[ordered]@{field='SourceCommit';value=$SourceCommitValue},[ordered]@{field='SourceTree';value=$SourceTreeValue})){
        $matches=[regex]::Matches($text,('internal const string '+[regex]::Escape([string]$binding.field)+' = "([0-9a-f]+)";'))
        if($matches.Count-eq0-or@($matches|Where-Object{$_.Groups[1].Value-cne[string]$binding.value}).Count-ne0){Fail 'GENERATED_OUTPUT_AUTHORITY_MISMATCH' ((Split-Path -Leaf $Path)+'/'+[string]$binding.field)}
    }
    if($PolicyInput){foreach($field in @('UpgradePolicySha256','PolicySha256')){$matches=[regex]::Matches($text,('internal const string '+$field+' = "([0-9a-f]{64})";'));if($matches.Count-eq0-or@($matches|Where-Object{$_.Groups[1].Value-cne[string]$Policy.raw_sha256}).Count-ne0){Fail 'GENERATED_OUTPUT_AUTHORITY_MISMATCH' ((Split-Path -Leaf $Path)+'/'+$field)}}}
}
function CanonicalCompilerInputIndex([object]$Receipt,[object]$Determinism,[hashtable]$Overrides) {
    $index=@{}
    $committed=@(CommittedAuthorityRows $Overrides);$observedSources=@($Receipt.source_files)
    if((JsonKind $Receipt.source_files)-cne'ARRAY'-or$observedSources.Count-ne$committed.Count){Fail 'COMMITTED_SOURCE_AUTHORITY_MISMATCH' 'inventory'}
    for($sourceIndex=0;$sourceIndex-lt$committed.Count;$sourceIndex++){
        AssertSourceAuthority $observedSources[$sourceIndex] $committed[$sourceIndex] ([string]$committed[$sourceIndex].path);$source=$committed[$sourceIndex]
        $path=AssertCanonicalInputPath ([string]$source.path) 'committed-authority'
        if($index.ContainsKey($path)){Fail 'COMPILER_INPUT_AUTHORITY_AMBIGUOUS' $path}
        $index[$path]=[ordered]@{classification='COMMITTED';record=[ordered]@{generation_rule=$null;generator=$null;git_blob_identity=$source.git_blob_identity;mode=$source.mode;path=$path;raw_sha256=$source.raw_sha256;size=$source.size}}
    }
    $configuration=@(GroundedConfigurationInventory $Receipt);$closure=RecomputeBuildInputClosure $committed $configuration $Overrides
    if([string]$Receipt.build_input_closure_sha256-cne$closure-or[string]$Determinism.build_input_closure_sha256-cne$closure){Fail 'BUILD_INPUT_CLOSURE_MISMATCH' ('expected='+$closure+';receipt='+[string]$Receipt.build_input_closure_sha256+';determinism='+[string]$Determinism.build_input_closure_sha256)}
    $policy=GroundedPolicyAuthority $Receipt $closure $Overrides;$generator=GroundedGeneratorAuthority $Overrides;$contracts=@(GeneratedSourceContract);$observedGenerated=@($Receipt.generated_sources)
    if((JsonKind $Receipt.generated_sources)-cne'ARRAY'-or$observedGenerated.Count-ne$contracts.Count){Fail 'GENERATED_SOURCE_AUTHORITY_MISMATCH' 'inventory'}
    for($generatedIndex=0;$generatedIndex-lt$contracts.Count;$generatedIndex++){
        $contract=$contracts[$generatedIndex];$generated=$observedGenerated[$generatedIndex];$path=[string]$contract.path;$actualPath=Join-Path $build $path.Replace('/','\')
        if(-not(Test-Path -LiteralPath $actualPath -PathType Leaf)){Fail 'GENERATED_SOURCE_AUTHORITY_MISMATCH' ($path+'/missing-output')}
        AssertGeneratedOutputAuthority $actualPath $closure $policy ([bool]$contract.policy_input) ([string]$Receipt.source_commit) ([string]$Receipt.source_tree)
        $expected=[ordered]@{generation_rule=[string]$contract.generation_rule;generator=$generator;output_identity=(Hash $actualPath);path=$path;raw_sha256=(Hash $actualPath);size=[long](Get-Item -LiteralPath $actualPath).Length;source_inputs=(ExpectedGeneratedSourceInputs $configuration $committed $generator $closure $policy ([bool]$contract.policy_input))}
        if((JsonKind $generated)-cne'OBJECT'-or-not(ExactJsonEqual $expected $generated)){Fail 'GENERATED_SOURCE_AUTHORITY_MISMATCH' $path}
        $path=AssertCanonicalInputPath $path 'generated-authority'
        if($index.ContainsKey($path)){Fail 'COMPILER_INPUT_AUTHORITY_AMBIGUOUS' $path}
        $index[$path]=[ordered]@{classification='GENERATED';record=[ordered]@{generation_rule=$expected.generation_rule;generator=$generator;git_blob_identity=$null;mode=$null;path=$path;raw_sha256=$expected.raw_sha256;size=$expected.size}}
    }
    return [ordered]@{build_input_closure_sha256=$closure;configuration_inputs=$configuration;index=$index;policy=$policy}
}
function AssertCompilerInputBinding([string]$Role,[object]$InputRecord,[hashtable]$CanonicalIndex) {
    AssertCompilerInputSchema $Role $InputRecord
    AssertKind $Role '<unknown>' 'path' (FieldValue $InputRecord 'path') 'STRING';$path=AssertCanonicalInputPath ([string]$InputRecord.path) ($Role+'/role-input')
    if(-not$CanonicalIndex.ContainsKey($path)){Fail 'COMPILER_INPUT_AUTHORITY_MISSING' ($Role+'/'+$path)}
    $authority=$CanonicalIndex[$path];$canonical=$authority.record;$classification=[string]$authority.classification
    AssertSha256 $Role $path 'raw_sha256' $InputRecord.raw_sha256;AssertKind $Role $path 'size' $InputRecord.size 'INTEGER'
    if([decimal]$InputRecord.size-lt0-or[decimal]$InputRecord.size-gt[decimal][long]::MaxValue){FailInputField $Role $path 'size' '<integer-0-through-int64-max>' $InputRecord.size}
    if($classification-ceq'COMMITTED'){
        AssertGitBlob $Role $path 'git_blob_identity' $InputRecord.git_blob_identity;AssertKind $Role $path 'mode' $InputRecord.mode 'STRING';AssertKind $Role $path 'generation_rule' $InputRecord.generation_rule 'NULL';AssertKind $Role $path 'generator' $InputRecord.generator 'NULL'
    }else{
        AssertKind $Role $path 'git_blob_identity' $InputRecord.git_blob_identity 'NULL';AssertKind $Role $path 'mode' $InputRecord.mode 'NULL';AssertKind $Role $path 'generation_rule' $InputRecord.generation_rule 'STRING';AssertKind $Role $path 'generator' $InputRecord.generator 'OBJECT'
    }
    foreach($field in @('generation_rule','generator','git_blob_identity','mode','path','raw_sha256','size')){if(-not(ExactJsonEqual (FieldValue $canonical $field) (FieldValue $InputRecord $field))){FailInputField $Role $path $field (FieldValue $canonical $field) (FieldValue $InputRecord $field)}}
    return $classification
}
function ForbiddenIdentity([object]$Value) {
    $text = [string]$Value
    if ([string]::IsNullOrWhiteSpace($text)) { return $true }
    if ($text -match '^(?:0{40}|0{64}|0{8}|0{8}:0{16})$') { return $true }
    return $text -match '(?i)(?:BOOTSTRAP_PENDING|DEVELOPMENT|PLACEHOLDER|\bTBD\b|\bUNKNOWN\b)'
}
function SourceTokenInvalid([string]$Text) {
    return $Text -match '(?i)(?:UNIT2_GENERATED_|BOOTSTRAP_PENDING|STATIC_PLACEHOLDER|R7DevelopmentIdentity)' -or $Text -match '"0{40}"' -or $Text -match '"0{64}"'
}
function ExtractIdentity([string]$Binary) {
    $assembly=[Reflection.Assembly]::ReflectionOnlyLoadFrom([IO.Path]::GetFullPath($Binary));$result=[ordered]@{}
    foreach($typeName in @('RandleAI.R7Remediation.R7BuildIdentity','RandleAI.R7Remediation.R7Unit2BuildIdentity')){$type=$assembly.GetType($typeName,$true,$false);foreach($field in @($type.GetFields([Reflection.BindingFlags]'Static,NonPublic,Public')|Sort-Object Name)){if($field.IsLiteral){$result[($type.Name+'.'+$field.Name)]=$field.GetRawConstantValue()}}}
    return $result
}
function ExtractPackagedIdentity([string]$Binary) {
    $assembly=[Reflection.Assembly]::ReflectionOnlyLoadFrom([IO.Path]::GetFullPath($Binary));$result=[ordered]@{}
    foreach($typeName in @('RandleAI.R7Remediation.R7BuildIdentity','RandleAI.R7Remediation.R7Unit2BuildIdentity')){$type=$assembly.GetType($typeName,$false,$false);if($null-eq$type){continue};foreach($field in @($type.GetFields([Reflection.BindingFlags]'Static,NonPublic,Public')|Sort-Object Name)){if($field.IsLiteral){$result[($type.Name+'.'+$field.Name)]=$field.GetRawConstantValue()}}}
    return $result
}
function AssertStringArray([string]$Code,[string]$Context,[object]$Value) {
    if((JsonKind $Value)-cne'ARRAY'-or@($Value|Where-Object{(JsonKind $_)-cne'STRING'}).Count-ne0){Fail $Code ($Context+'/string-array')}
}
function AssertDeterminismCompilerInputs([object]$Receipt,[object]$Determinism,[hashtable]$CanonicalInputs) {
    if((JsonKind $Determinism.role_determinism)-cne'ARRAY'){Fail 'DETERMINISM_COMPILER_INPUT_MISMATCH' 'roles/not-array'}
    $receiptRoles=@($Receipt.roles);$determinismRoles=@($Determinism.role_determinism)
    if($receiptRoles.Count-ne$determinismRoles.Count){Fail 'DETERMINISM_COMPILER_INPUT_MISMATCH' 'role-count'}
    foreach($receiptRole in $receiptRoles){
        $roleName=[string]$receiptRole.role;$matches=@($determinismRoles|Where-Object{(JsonKind $_.role)-ceq'STRING'-and[string]$_.role-ceq$roleName})
        if($matches.Count-ne1){Fail 'DETERMINISM_COMPILER_INPUT_MISMATCH' ($roleName+'/role-authority')};$detRole=$matches[0]
        if((JsonKind $detRole.compiler_inputs)-cne'ARRAY'){Fail 'DETERMINISM_COMPILER_INPUT_MISMATCH' ($roleName+'/inputs-not-array')}
        $expectedInputs=@($receiptRole.compiler_inputs);$observedInputs=@($detRole.compiler_inputs)
        if($expectedInputs.Count-ne$observedInputs.Count){Fail 'DETERMINISM_COMPILER_INPUT_MISMATCH' ($roleName+'/input-count')}
        for($inputIndex=0;$inputIndex-lt$expectedInputs.Count;$inputIndex++){
            [void](AssertCompilerInputBinding ('DETERMINISM:'+$roleName) $observedInputs[$inputIndex] $CanonicalInputs)
            if(-not(ExactJsonEqual $expectedInputs[$inputIndex] $observedInputs[$inputIndex])){Fail 'DETERMINISM_COMPILER_INPUT_MISMATCH' ($roleName+'/input/'+$inputIndex)}
        }
        AssertStringArray 'DETERMINISM_COMPILER_ARGUMENT_MISMATCH' ($roleName+'/pass_a') $detRole.compiler_arguments.pass_a;AssertStringArray 'DETERMINISM_COMPILER_ARGUMENT_MISMATCH' ($roleName+'/pass_b') $detRole.compiler_arguments.pass_b
        if(-not(ExactJsonEqual $receiptRole.compiler_arguments.pass_a $detRole.compiler_arguments.pass_a)-or-not(ExactJsonEqual $receiptRole.compiler_arguments.pass_b $detRole.compiler_arguments.pass_b)){Fail 'DETERMINISM_COMPILER_ARGUMENT_MISMATCH' $roleName}
    }
}
function ValidateModel([object]$Receipt,[object]$Determinism,[hashtable]$GeneratedTextOverrides,[hashtable]$ProvenanceOverrides=@{}) {
    $actualTree=[string](@(GitArgs @('show','-s','--format=%T',$SourceCommit))[0])
    if([string]$Receipt.source_commit-cne$SourceCommit-or[string]$Determinism.source_commit-cne$SourceCommit-or[string]$Receipt.source_tree-cne$actualTree-or[string]$Determinism.source_tree-cne$actualTree){Fail 'SOURCE_COMMIT_TREE_AUTHORITY_MISMATCH' 'receipt-or-determinism'}
    $authority=CanonicalCompilerInputIndex $Receipt $Determinism $ProvenanceOverrides;$canonicalInputs=$authority.index
    $declaredSourcePaths=@($Receipt.source_files|ForEach-Object{[string]$_.path})
    foreach($generated in @($Receipt.generated_sources)){
        $generatedPath=Join-Path $build ([string]$generated.path).Replace('/','\')
        $text=if($GeneratedTextOverrides.ContainsKey([string]$generated.path)){[string]$GeneratedTextOverrides[[string]$generated.path]}else{[IO.File]::ReadAllText($generatedPath)}
        if(SourceTokenInvalid $text){Fail 'GENERATED_SOURCE_TOKEN_INVALID' ([string]$generated.path)}
    }
    if((JsonKind $Receipt.roles)-cne'ARRAY'){Fail 'COMPILER_INPUT_SET_MISMATCH' 'roles-not-array'}
    $roleNames=@($Receipt.roles|ForEach-Object{if((JsonKind $_.role)-cne'STRING'){Fail 'COMPILER_INPUT_SET_MISMATCH' 'role-name-type'};[string]$_.role})
    if($roleNames.Count-ne$requiredRoles.Count-or@($roleNames|Sort-Object -Unique).Count-ne$requiredRoles.Count-or(@($roleNames|Sort-Object)-join"`n")-cne(@($requiredRoles|Sort-Object)-join"`n")){Fail 'COMPILER_INPUT_SET_MISMATCH' 'role-authority'}
    $roleGeneratedMap=@{};foreach($contract in @(GeneratedSourceContract)){foreach($allowedRole in @($contract.roles)){$roleGeneratedMap[[string]$allowedRole]=[string]$contract.path}}
    foreach($role in @($Receipt.roles)){
        if((JsonKind $role.compiler_inputs)-cne'ARRAY'){Fail 'COMPILER_INPUT_SET_MISMATCH' (([string]$role.role)+'/inputs-not-array')}
        $seenRoleInputs=@{};$committedInputCount=0;$generatedInputCount=0
        foreach($roleInput in @($role.compiler_inputs)){
            $classification=AssertCompilerInputBinding ([string]$role.role) $roleInput $canonicalInputs
            $inputPath=[string]$roleInput.path
            if($seenRoleInputs.ContainsKey($inputPath)){Fail 'COMPILER_INPUT_SET_MISMATCH' (([string]$role.role)+'/duplicate/'+$inputPath)}
            $seenRoleInputs[$inputPath]=$true
            if($classification-ceq'COMMITTED'){$committedInputCount++}elseif($classification-ceq'GENERATED'){$generatedInputCount++}
        }
        $inputPaths=@($role.compiler_inputs|ForEach-Object{[string]$_.path})
        $generatedInput=@($role.compiler_inputs|Where-Object{[string]$_.path-like'Generated/*'})
        if($generatedInput.Count-ne1-or$generatedInputCount-ne1-or$committedInputCount-ne$declaredSourcePaths.Count){Fail 'COMPILER_INPUT_SET_MISMATCH' ([string]$role.role)}
        $expectedGeneratedPath=[string]$roleGeneratedMap[[string]$role.role];if([string]$generatedInput[0].path-cne$expectedGeneratedPath){Fail 'ROLE_GENERATED_SOURCE_MISMATCH' (([string]$role.role)+'/'+[string]$generatedInput[0].path+'/'+$expectedGeneratedPath)}
        $generatedForRole=@($Receipt.generated_sources|Where-Object{[string]$_.path-ceq[string]$generatedInput[0].path})
        if($generatedForRole.Count -ne 1 -or [string]$generatedForRole[0].raw_sha256-cne[string]$role.generated_source_sha256){Fail 'COMPILER_INPUT_SET_MISMATCH' ([string]$role.role)}
        $expectedInputs=@($declaredSourcePaths)+[string]$generatedForRole[0].path
        if(($inputPaths-join "`n") -cne ($expectedInputs-join "`n")){Fail 'COMPILER_INPUT_SET_MISMATCH' (([string]$role.role)+'/ordered-inputs')}
        foreach($phase in @('pass_a','pass_b')){
            $arguments=@($role.compiler_arguments.$phase)
            AssertStringArray 'COMPILER_ARGUMENT_VECTOR_MISMATCH' (([string]$role.role)+'/'+$phase) $role.compiler_arguments.$phase
            foreach($switch in $requiredSwitches){if($arguments -cnotcontains $switch){Fail 'COMPILER_ARGUMENT_VECTOR_MISMATCH' (([string]$role.role)+'/'+$phase+'/'+$switch)}}
            if(@($arguments|Where-Object{[string]$_ -like '/main:*'}).Count -ne 1 -or @($arguments|Where-Object{[string]$_ -like '/out:*'}).Count -ne 1 -or @($arguments|Where-Object{[string]$_ -like '/define:*'}).Count -ne 1){Fail 'COMPILER_ARGUMENT_VECTOR_MISMATCH' (([string]$role.role)+'/'+$phase+'/role-switches')}
            $sourceArguments=@($arguments|Where-Object{[string]$_ -notlike '/*'}|ForEach-Object{[IO.Path]::GetFullPath([string]$_)})
            $inputActual=@($role.compiler_inputs|ForEach-Object{if([string]$_.path -like 'Generated/*'){Join-Path $build ([string]$_.path).Replace('/','\')}else{Join-Path $repositoryRoot ([string]$_.path).Replace('/','\')}}|ForEach-Object{[IO.Path]::GetFullPath($_)})
            if((@($sourceArguments|Sort-Object)-join "`n") -cne (@($inputActual|Sort-Object)-join "`n")){Fail 'COMPILER_INPUT_SET_MISMATCH' (([string]$role.role)+'/'+$phase+'/arguments')}
            $expected=@($requiredSwitches)
            $expected+=('/main:'+[string]$role.main)
            $expected+=('/out:'+$(if($phase-ceq'pass_a'){[IO.Path]::GetFullPath([string]$role.pass_a_path)}else{[IO.Path]::GetFullPath([string]$role.pass_b_path)}))
            $expected+=('/define:'+[string]$role.define)
            foreach($reference in @($Receipt.framework_references)){$expected+=('/reference:'+[IO.Path]::GetFullPath([string]$reference.path))}
            $expected+=@($inputActual)
            if(($arguments-join "`n")-cne($expected-join "`n")){Fail 'COMPILER_ARGUMENT_VECTOR_MISMATCH' (([string]$role.role)+'/'+$phase+'/ordered')}
        }
        $invalidIdentities=@($role.embedded_identity.PSObject.Properties|Where-Object{ForbiddenIdentity $_.Value})
        if([string]$role.role -like 'PACKAGED_*' -and $invalidIdentities.Count -ne 0){Fail 'PACKAGED_TOOL_IDENTITY_INVALID' ([string]$role.role)}
        if($invalidIdentities.Count-ne 0){Fail 'EMBEDDED_IDENTITY_INVALID' (([string]$role.role)+'/'+[string]$invalidIdentities[0].Name)}
    }
    foreach($packaged in @($Receipt.target_packaged_executables)){
        $invalid=@($packaged.embedded_identity.PSObject.Properties|Where-Object{ForbiddenIdentity $_.Value})
        if($invalid.Count-ne0){Fail 'PACKAGED_TOOL_IDENTITY_INVALID' (([string]$packaged.path)+'/'+[string]$invalid[0].Name)}
    }
    AssertDeterminismCompilerInputs $Receipt $Determinism $canonicalInputs
}

function JoinFixtureBytes([object[]]$Parts) {
    $stream=[IO.MemoryStream]::new()
    try{foreach($part in $Parts){if($null-ne$part){$bytes=[byte[]]$part;$stream.Write($bytes,0,$bytes.Length)}};return $stream.ToArray()}finally{$stream.Dispose()}
}
function AsciiFixtureBytes([string]$Value){return [Text.Encoding]::ASCII.GetBytes($Value)}
function GitBatchFixtureFrame([string]$Header,[byte[]]$Payload,[byte[]]$HeaderDelimiter,[byte[]]$PayloadDelimiter) {
    return JoinFixtureBytes @((AsciiFixtureBytes $Header),$HeaderDelimiter,$Payload,$PayloadDelimiter)
}
function InvokeGitBatchParserFixture([string]$Mutation) {
    $paths=@(($packageRelativeRoot+'/Source/R7AdversarialHarness.cs'),($packageRelativeRoot+'/Source/R7ArtifactTool.cs'));$descriptors=[Collections.Generic.List[object]]::new();$payloads=[Collections.Generic.List[byte[]]]::new()
    foreach($path in $paths){$authority=ExactTreeBlobAuthority $path;$descriptors.Add([ordered]@{oid=[string]$authority.git_blob_identity;path=$path});$payloads.Add([byte[]](ReadGitBlobBytes ([string]$authority.git_blob_identity)))}
    $d0=$descriptors[0];$d1=$descriptors[1];$p0=[byte[]]$payloads[0];$p1=[byte[]]$payloads[1];$lf=[byte[]](10);$crlf=[byte[]](13,10);$none=[byte[]]@()
    $h0=[string]$d0.oid+' blob '+$p0.Length.ToString([Globalization.CultureInfo]::InvariantCulture);$h1=[string]$d1.oid+' blob '+$p1.Length.ToString([Globalization.CultureInfo]::InvariantCulture)
    $expected=@($d0);$streamBytes=$null;$runProcessCheck=$false
    switch($Mutation){
        'VALID'{$streamBytes=GitBatchFixtureFrame $h0 $p0 $lf $lf}
        'BATCH_HEADER_EMBEDDED_CR'{$header=[string]$d0.oid.Substring(0,8)+[char]13+[string]$d0.oid.Substring(8)+' blob '+$p0.Length;$streamBytes=GitBatchFixtureFrame $header $p0 $lf $lf}
        'BATCH_HEADER_CRLF_TERMINATOR'{$streamBytes=GitBatchFixtureFrame $h0 $p0 $crlf $lf}
        'BATCH_HEADER_UPPERCASE_OID'{$streamBytes=GitBatchFixtureFrame ([string]$d0.oid.ToUpperInvariant()+' blob '+$p0.Length) $p0 $lf $lf}
        'BATCH_HEADER_SHORT_OID'{$streamBytes=GitBatchFixtureFrame ([string]$d0.oid.Substring(1)+' blob '+$p0.Length) $p0 $lf $lf}
        'BATCH_HEADER_LONG_OID'{$streamBytes=GitBatchFixtureFrame ('0'+[string]$d0.oid+' blob '+$p0.Length) $p0 $lf $lf}
        'BATCH_HEADER_NONHEX_OID'{$streamBytes=GitBatchFixtureFrame ('g'+[string]$d0.oid.Substring(1)+' blob '+$p0.Length) $p0 $lf $lf}
        'BATCH_PAYLOAD_FROM_OTHER_BLOB'{$streamBytes=GitBatchFixtureFrame ([string]$d0.oid+' blob '+$p1.Length) $p1 $lf $lf}
        'BATCH_FALSE_HEADER_OID_CORRECT_PAYLOAD'{$streamBytes=GitBatchFixtureFrame ([string]$d1.oid+' blob '+$p0.Length) $p0 $lf $lf}
        'BATCH_ARBITRARY_PAYLOAD'{$payload=[byte[]](1,2,3,4,5,6,7);$streamBytes=GitBatchFixtureFrame ([string]$d0.oid+' blob '+$payload.Length) $payload $lf $lf}
        'BATCH_DECLARED_SIZE_INCORRECT'{$payload=JoinFixtureBytes @($p0,[byte[]](0));$streamBytes=GitBatchFixtureFrame ([string]$d0.oid+' blob '+$payload.Length) $payload $lf $lf}
        'BATCH_DECLARED_SIZE_SMALLER'{$streamBytes=GitBatchFixtureFrame ([string]$d0.oid+' blob '+($p0.Length-1)) $p0 $lf $lf}
        'BATCH_DECLARED_SIZE_LARGER'{$streamBytes=GitBatchFixtureFrame ([string]$d0.oid+' blob '+($p0.Length+2)) $p0 $lf $lf}
        'BATCH_PAYLOAD_TRUNCATED'{$truncated=New-Object byte[] ($p0.Length-1);[Buffer]::BlockCopy($p0,0,$truncated,0,$truncated.Length);$streamBytes=GitBatchFixtureFrame $h0 $truncated $lf $none}
        'BATCH_PAYLOAD_DELIMITER_MISSING'{$streamBytes=GitBatchFixtureFrame $h0 $p0 $lf $none}
        'BATCH_PAYLOAD_DELIMITER_CRLF'{$streamBytes=GitBatchFixtureFrame $h0 $p0 $lf $crlf}
        'BATCH_OBJECT_TYPE_WRONG'{$streamBytes=GitBatchFixtureFrame ([string]$d0.oid+' tree '+$p0.Length) $p0 $lf $lf}
        'BATCH_RESPONSE_REORDERED'{$expected=@($d0,$d1);$streamBytes=JoinFixtureBytes @((GitBatchFixtureFrame $h1 $p1 $lf $lf),(GitBatchFixtureFrame $h0 $p0 $lf $lf))}
        'BATCH_RESPONSE_DUPLICATE'{$expected=@($d0,$d1);$streamBytes=JoinFixtureBytes @((GitBatchFixtureFrame $h0 $p0 $lf $lf),(GitBatchFixtureFrame $h0 $p0 $lf $lf))}
        'BATCH_RESPONSE_MISSING'{$expected=@($d0,$d1);$streamBytes=GitBatchFixtureFrame $h0 $p0 $lf $lf}
        'BATCH_TRAILING_JUNK'{$streamBytes=JoinFixtureBytes @((GitBatchFixtureFrame $h0 $p0 $lf $lf),(AsciiFixtureBytes 'JUNK'))}
        'BATCH_TRAILING_LF'{$streamBytes=JoinFixtureBytes @((GitBatchFixtureFrame $h0 $p0 $lf $lf),$lf)}
        'BATCH_EXTRA_VALID_FRAME'{$streamBytes=JoinFixtureBytes @((GitBatchFixtureFrame $h0 $p0 $lf $lf),(GitBatchFixtureFrame $h1 $p1 $lf $lf))}
        'BATCH_DECLARED_SIZE_OVERFLOW'{$streamBytes=GitBatchFixtureFrame ([string]$d0.oid+' blob 18446744073709551616') $none $lf $none}
        'BATCH_HEADER_PARTIAL_EOF'{$streamBytes=AsciiFixtureBytes ([string]$d0.oid+' blob')}
        'BATCH_PROCESS_NONZERO'{$streamBytes=GitBatchFixtureFrame $h0 $p0 $lf $lf;$runProcessCheck=$true}
        default{throw 'Unknown Git batch fixture mutation: '+$Mutation}
    }
    $stream=[IO.MemoryStream]::new([byte[]]$streamBytes,$false)
    try{$result=@(ReadAuthenticatedGitBatch $stream $expected);if($runProcessCheck){AssertGitBatchProcessResult $true 17 'fixture nonzero process' 'fixture'};return $result}finally{$stream.Dispose()}
}

function EncodeLifecycleCommand([string]$Value){return [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($Value))}
function NewGitHeldPipeReadinessCommand([string]$FixtureExecutable,[string]$ReadinessDirectory,[string]$AggregatePath,[int]$Count) {
    $escapedDirectory=$ReadinessDirectory.Replace("'","''");$escapedAggregate=$AggregatePath.Replace("'","''");$escapedExecutable=$FixtureExecutable.Replace("'","''")
    $child='$d='''+$escapedDirectory+''';$o=[Console]::OpenStandardOutput();$e=[Console]::OpenStandardError();if(-not$o.CanWrite-or-not$e.CanWrite){Start-Sleep -Seconds 30;exit};$tmp=[IO.Path]::Combine($d,$PID.ToString()+''.tmp'');$ready=[IO.Path]::Combine($d,$PID.ToString()+''.ready'');[IO.File]::WriteAllText($tmp,$PID.ToString());[IO.File]::Move($tmp,$ready);Start-Sleep -Seconds 30'
    $encoded=EncodeLifecycleCommand $child
    return '$d='''+$escapedDirectory+''';$aggregate='''+$escapedAggregate+''';$children=[Collections.Generic.List[Diagnostics.Process]]::new();foreach($i in 1..'+$Count+'){$p=[Diagnostics.ProcessStartInfo]::new();$p.FileName='''+$escapedExecutable+''';$p.Arguments=''-NoProfile -NonInteractive -EncodedCommand '+$encoded+''';$p.UseShellExecute=$false;$p.CreateNoWindow=$true;$children.Add([Diagnostics.Process]::Start($p))};$clock=[Diagnostics.Stopwatch]::StartNew();do{$files=@([IO.Directory]::GetFiles($d,''*.ready''));if($files.Count-eq'+$Count+'){break};Start-Sleep -Milliseconds 5}while($clock.ElapsedMilliseconds-lt4000);$files=@([IO.Directory]::GetFiles($d,''*.ready''));if($files.Count-eq'+$Count+'){$pids=@($files|Sort-Object|ForEach-Object{[IO.File]::ReadAllText($_).Trim()});$value=''READY|'+$Count+'|''+($pids-join'','')+''|stdout=True|stderr=True|hold=True|marker=False'';$tmp=$aggregate+''.tmp'';[IO.File]::WriteAllText($tmp,$value);[IO.File]::Move($tmp,$aggregate)};Start-Sleep -Seconds 30'
}
function InvokeGitBatchLifecycleFixture([string]$Mutation) {
    if($null-eq(Get-Variable -Name gitLifecycleFixtureEvidence -Scope Script -ErrorAction SilentlyContinue)){$script:gitLifecycleFixtureEvidence=[Collections.Generic.List[object]]::new()}
    $fixtureExe=(Get-Process -Id $PID).Path;$payload=[byte[]](65,66,67);$oid=GitBlobIdentity $payload;$frame=JoinFixtureBytes @((AsciiFixtureBytes ($oid+' blob 3'+"`n")),$payload,[byte[]](10));$frame64=[Convert]::ToBase64String($frame);$writeFrame='$b=[Convert]::FromBase64String("'+$frame64+'");$o=[Console]::OpenStandardOutput();$o.Write($b,0,$b.Length);$o.Flush();'
    $expected=@(NewGitExpectedObject $oid 'fixture/object' 3);$deadline=1800;$reserve=600;$terminationConfirmation=$reserve;$stderrLimit=1024;$pidFile=Join-Path ([IO.Path]::GetTempPath()) ('r7_u2b3o_'+[Guid]::NewGuid().ToString('N')+'.pid');$childPid=0;$childPids=@();$readinessPath='';$readinessCount=0;$readinessEstablished=$false;$launchFault=''
    $readinessDir=''
    $childCode='Start-Sleep -Seconds 30';$childEncoded=EncodeLifecycleCommand $childCode;$escapedExe=$fixtureExe.Replace("'","''");$escapedPid=$pidFile.Replace("'","''")
    $spawnPrefix='$p=[Diagnostics.ProcessStartInfo]::new();$p.FileName='''+$escapedExe+''';$p.Arguments=''-NoProfile -NonInteractive -EncodedCommand '+$childEncoded+''';$p.UseShellExecute=$false;$p.CreateNoWindow=$true;'
    $code='';$arguments='';$input=[byte[]]@()
    switch($Mutation){
        'LIFECYCLE_OVERSIZED_DECLARED_PAYLOAD'{$code='$o=[Console]::OpenStandardOutput();$b=[Text.Encoding]::ASCII.GetBytes("'+$oid+' blob 67108865`n");$o.Write($b,0,$b.Length);$o.Flush();Start-Sleep -Seconds 30'}
        'LIFECYCLE_AGGREGATE_BUDGET_EXCEEDED'{$expected=@();foreach($index in 1..5){$expected+=NewGitExpectedObject $oid ('fixture/'+$index) 67108864};$code='exit 0'}
        'LIFECYCLE_SUSTAINED_STDOUT'{$code=$writeFrame+'$o=[Console]::OpenStandardOutput();$b=New-Object byte[] 4096;while($true){$o.Write($b,0,$b.Length);$o.Flush()}'}
        'LIFECYCLE_STDERR_LIMIT_EXCEEDED'{$code='$e=[Console]::OpenStandardError();$b=New-Object byte[] 2048;$e.Write($b,0,$b.Length);$e.Flush();Start-Sleep -Seconds 30'}
        'LIFECYCLE_CONCURRENT_STREAMS_NONZERO'{$code='$e=[Console]::OpenStandardError();$b=New-Object byte[] 512;$e.Write($b,0,$b.Length);$e.Flush();'+$writeFrame+'exit 7'}
        'LIFECYCLE_CHILD_HOLDS_STDOUT'{$expected=@();$code=$spawnPrefix+'$p.RedirectStandardError=$true;$c=[Diagnostics.Process]::Start($p);[IO.File]::WriteAllText('''+$escapedPid+''',$c.Id.ToString());exit 0'}
        'LIFECYCLE_CHILD_HOLDS_STDERR'{$expected=@();$code=$spawnPrefix+'$p.RedirectStandardOutput=$true;$c=[Diagnostics.Process]::Start($p);[IO.File]::WriteAllText('''+$escapedPid+''',$c.Id.ToString());exit 0'}
        'LIFECYCLE_CHILD_HOLDS_BOTH_PIPES'{$expected=@();$code=$spawnPrefix+'$c=[Diagnostics.Process]::Start($p);[IO.File]::WriteAllText('''+$escapedPid+''',$c.Id.ToString());exit 0'}
        'LIFECYCLE_PARENT_HANGS_AFTER_FRAMES'{$code=$writeFrame+'Start-Sleep -Seconds 30'}
        'LIFECYCLE_CHILD_ALIVE_AFTER_PARENT_EXIT'{$expected=@();$code=$spawnPrefix+'$p.RedirectStandardOutput=$true;$p.RedirectStandardError=$true;$c=[Diagnostics.Process]::Start($p);[IO.File]::WriteAllText('''+$escapedPid+''',$c.Id.ToString());exit 0'}
        'LIFECYCLE_CHILD_ALIVE_AFTER_PARENT_TIMEOUT'{$expected=@();$code=$spawnPrefix+'$p.RedirectStandardOutput=$true;$p.RedirectStandardError=$true;$c=[Diagnostics.Process]::Start($p);[IO.File]::WriteAllText('''+$escapedPid+''',$c.Id.ToString());Start-Sleep -Seconds 30'}
        'LIFECYCLE_DELAYED_TRAILING_STDOUT'{$code=$writeFrame+'Start-Sleep -Milliseconds 200;$o=[Console]::OpenStandardOutput();$o.WriteByte(88);$o.Flush()'}
        'LIFECYCLE_VALID_FRAMES_NONZERO_EXIT'{$code=$writeFrame+'exit 17'}
        'LIFECYCLE_EXIT_BEFORE_REQUIRED_FRAMES'{$code='exit 0'}
        'LIFECYCLE_TIMEOUT_HEADER_READ'{$code='Start-Sleep -Seconds 30'}
        'LIFECYCLE_TIMEOUT_PAYLOAD_READ'{$code='$o=[Console]::OpenStandardOutput();$b=[Text.Encoding]::ASCII.GetBytes("'+$oid+' blob 3`nA");$o.Write($b,0,$b.Length);$o.Flush();Start-Sleep -Seconds 30'}
        'LIFECYCLE_TIMEOUT_EXACT_EOF'{$code=$writeFrame+'Start-Sleep -Seconds 30'}
        'LIFECYCLE_TIMEOUT_STDERR_COMPLETION'{$code=$writeFrame+$spawnPrefix+'$p.RedirectStandardOutput=$true;$c=[Diagnostics.Process]::Start($p);[IO.File]::WriteAllText('''+$escapedPid+''',$c.Id.ToString());exit 0'}
        'LIFECYCLE_CLEANUP_DEADLINE_EXCEEDED'{$expected=@();$deadline=5000;$reserve=1500;$terminationConfirmation=1;$readinessCount=4;$readinessPath=$pidFile;$launchFault='READINESS_GATED_TIMEOUT_PRIMARY_LATE_PROCESS_TRANSITION';$readinessDir=Join-Path ([IO.Path]::GetTempPath()) ('r7_u2b3w_ready_'+[Guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($readinessDir)|Out-Null;$code=NewGitHeldPipeReadinessCommand $fixtureExe $readinessDir $pidFile $readinessCount}
        'LIFECYCLE_TREE_TERMINATION_UNCONFIRMED'{$expected=@();$deadline=5000;$reserve=1500;$terminationConfirmation=1;$readinessCount=2;$readinessPath=$pidFile;$launchFault='READINESS_GATED_TIMEOUT_PRIMARY_LATE_PROCESS_TRANSITION';$readinessDir=Join-Path ([IO.Path]::GetTempPath()) ('r7_u2b3w_ready_'+[Guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($readinessDir)|Out-Null;$code=NewGitHeldPipeReadinessCommand $fixtureExe $readinessDir $pidFile $readinessCount}
        'LIFECYCLE_EXPECTED_SIZE_MISMATCH'{$expected=@(NewGitExpectedObject $oid 'fixture/object' 4);$code=$writeFrame+'Start-Sleep -Seconds 30'}
        'LIFECYCLE_AGGREGATE_ARITHMETIC_OVERFLOW'{$expected=@();foreach($index in 1..5){$expected+=NewGitExpectedObject $oid ('fixture/overflow/'+$index) 67108864};$code='exit 0'}
        default{throw 'Unknown Git lifecycle fixture mutation: '+$Mutation}
    }
    $arguments='-NoProfile -NonInteractive -EncodedCommand '+(EncodeLifecycleCommand $code);$clock=[Diagnostics.Stopwatch]::StartNew();$observed='PASS';$detail='';$result=$null
    try{$result=$(if($launchFault){InvokeBoundedGitBatchProcessLaunchTest $fixtureExe $arguments ([IO.Path]::GetTempPath()) $input $expected $launchFault $deadline $reserve $stderrLimit $terminationConfirmation $readinessPath $readinessCount}else{InvokeBoundedGitBatchProcess $fixtureExe $arguments ([IO.Path]::GetTempPath()) $input $expected $deadline $reserve $stderrLimit $terminationConfirmation});return $result}catch{$message=$(if($_.Exception.InnerException){$_.Exception.InnerException.Message}else{$_.Exception.Message});$parts=$message-split'\|',2;$observed=$parts[0];if($parts.Count-gt1){$detail=$parts[1]};throw ([IO.InvalidDataException]::new($message))}finally{
        if(Test-Path -LiteralPath $pidFile){$raw=(Get-Content -LiteralPath $pidFile -Raw).Trim();if($raw-match'^READY\|([0-9]+)\|([0-9]+(?:,[0-9]+)*)\|stdout=True\|stderr=True\|hold=True\|marker=False$'){$readinessEstablished=([int]$Matches[1]-eq$readinessCount);$childPids=@($Matches[2]-split','|ForEach-Object{[int]$_});if($childPids.Count){$childPid=$childPids[-1]}}elseif($raw-match'^[0-9]+$'){$childPid=[int]$raw;$childPids=@($childPid)};Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue}
        if($readinessDir-and(Test-Path -LiteralPath $readinessDir)){foreach($readyFile in @(Get-ChildItem -LiteralPath $readinessDir -File -ErrorAction SilentlyContinue)){if($readyFile.Name-match'^[0-9]+\.ready$'){try{$candidate=[int](Get-Content -LiteralPath $readyFile.FullName -Raw);if($candidate-gt0-and$candidate-notin$childPids){$childPids+=@($candidate)}}catch{}};Remove-Item -LiteralPath $readyFile.FullName -Force -ErrorAction SilentlyContinue};[IO.Directory]::Delete($readinessDir,$false)}
        $survivors=@($childPids|Where-Object{$null-ne(Get-Process -Id $_ -ErrorAction SilentlyContinue)});if($survivors.Count){$survivors|ForEach-Object{Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue}}
        $survivor=$survivors.Count-gt0;$script:gitLifecycleFixtureEvidence.Add([ordered]@{mutation=$Mutation;observed=$observed;detail=$detail;elapsed_ms=$clock.ElapsedMilliseconds;child_pid=$childPid;child_pids=@($childPids);readiness_established=$readinessEstablished;readiness_count=$readinessCount;child_survived_return=$survivor;maximum_payload_bytes=$(if($result){[long]$result.MaximumPayloadBytes}else{0});maximum_stderr_bytes=$(if($result){[int]$result.MaximumRetainedStderrBytes}else{$stderrLimit});stdout_complete=$(if($result){[bool]$result.StdoutCompleted}else{$detail-match'stdout_complete=True'});stderr_complete=$(if($result){[bool]$result.StderrCompleted}else{$detail-match'stderr_complete=True'});tree_terminated=$(if($result){[bool]$result.ProcessTreeTerminated}else{$detail-match'tree_terminated=True'})})
        if($survivor){throw ([IO.InvalidDataException]::new('GIT_BATCH_PROCESS_TREE_TERMINATION_FAILED|fixture-survivors='+($survivors-join',')))}
        if($clock.ElapsedMilliseconds-gt($deadline+1500)){throw ([IO.InvalidDataException]::new('GIT_BATCH_PROCESS_TIMEOUT|fixture-return-bound-exceeded='+$clock.ElapsedMilliseconds))}
    }
}
function InvokeGitBatchLifecyclePositiveCases([object]$Registry) {
    $results=[Collections.Generic.List[object]]::new();$fixtureExe=(Get-Process -Id $PID).Path;$stderrLimit=1024
    foreach($case in @($Registry.lifecycle_positive_cases)){
        $p0=[byte[]](65,66,67);$o0=GitBlobIdentity $p0;$f0=JoinFixtureBytes @((AsciiFixtureBytes ($o0+' blob 3'+"`n")),$p0,[byte[]](10));$expected=@(NewGitExpectedObject $o0 'fixture/positive-0' 3);$code=''
        if([string]$case.mutation-ceq'LIFECYCLE_VALID_BOUNDED_STDERR'){$f64=[Convert]::ToBase64String($f0);$code='$e=[Console]::OpenStandardError();$d=New-Object byte[] 512;$e.Write($d,0,$d.Length);$e.Flush();$b=[Convert]::FromBase64String("'+$f64+'");$o=[Console]::OpenStandardOutput();$o.Write($b,0,$b.Length);$o.Flush()'}
        elseif([string]$case.mutation-ceq'LIFECYCLE_VALID_AUTHENTIC_MULTI_OBJECT'){$p1=[byte[]](88,10,0,89);$o1=GitBlobIdentity $p1;$f1=JoinFixtureBytes @((AsciiFixtureBytes ($o1+' blob 4'+"`n")),$p1,[byte[]](10));$expected+=NewGitExpectedObject $o1 'fixture/positive-1' 4;$all=[Convert]::ToBase64String((JoinFixtureBytes @($f0,$f1)));$code='$b=[Convert]::FromBase64String("'+$all+'");$o=[Console]::OpenStandardOutput();$o.Write($b,0,$b.Length);$o.Flush()'}
        else{throw 'Unknown lifecycle positive mutation: '+[string]$case.mutation}
        $arguments='-NoProfile -NonInteractive -EncodedCommand '+(EncodeLifecycleCommand $code);if([string]$case.mutation-ceq'LIFECYCLE_VALID_BOUNDED_STDERR'){$measurement=InvokeBoundedGitBatchProcess $fixtureExe $arguments ([IO.Path]::GetTempPath()) ([byte[]]@()) $expected 3000 800 4096;$stderrLimit=[int]$measurement.MaximumRetainedStderrBytes};$clock=[Diagnostics.Stopwatch]::StartNew();$result=InvokeBoundedGitBatchProcess $fixtureExe $arguments ([IO.Path]::GetTempPath()) ([byte[]]@()) $expected 3000 800 $stderrLimit
        $results.Add([ordered]@{case_id=[string]$case.case_id;mutation=[string]$case.mutation;status='PASS';elapsed_ms=$clock.ElapsedMilliseconds;aggregate_budget=[long]$result.AggregateBudget;maximum_payload_bytes=[long]$result.MaximumPayloadBytes;maximum_stderr_bytes=[int]$result.MaximumRetainedStderrBytes;tree_terminated=[bool]$result.ProcessTreeTerminated})
    }
    return $results.ToArray()
}

function InitializeGitLaunchProbeRuntime {
    if('R7GitLaunchProbeNative'-as[type]){return}
    Add-Type -Language CSharp -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class R7GitLaunchProbeNative {
    const uint GENERIC_READ=0x80000000,GENERIC_WRITE=0x40000000,CREATE_ALWAYS=2,FILE_ATTRIBUTE_TEMPORARY=0x100,FILE_FLAG_DELETE_ON_CLOSE=0x04000000,PIPE_ACCESS_DUPLEX=3,PIPE_TYPE_BYTE=0,PIPE_WAIT=0;
    [StructLayout(LayoutKind.Sequential)] struct SA { public int n; public IntPtr sd; [MarshalAs(UnmanagedType.Bool)] public bool inherit; }
    [DllImport("kernel32.dll",SetLastError=true,CharSet=CharSet.Unicode)] static extern IntPtr CreateFileW(string path,uint access,uint share,ref SA sa,uint creation,uint flags,IntPtr template);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool CreatePipe(out IntPtr read,out IntPtr write,ref SA sa,int size);
    [DllImport("kernel32.dll",SetLastError=true,CharSet=CharSet.Unicode)] static extern IntPtr CreateNamedPipeW(string name,uint openMode,uint pipeMode,uint maxInstances,uint outSize,uint inSize,uint timeout,ref SA sa);
    [DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr handle);
    static SA Inheritable(){return new SA{n=Marshal.SizeOf(typeof(SA)),inherit=true};}
    public static long[] Create(string kind,string path){SA sa=Inheritable();if(kind=="FILE"){IntPtr h=CreateFileW(path,GENERIC_READ|GENERIC_WRITE,3,ref sa,CREATE_ALWAYS,FILE_ATTRIBUTE_TEMPORARY|FILE_FLAG_DELETE_ON_CLOSE,IntPtr.Zero);if(h==new IntPtr(-1))throw new InvalidOperationException("CreateFileW:"+Marshal.GetLastWin32Error());return new long[]{h.ToInt64()};}if(kind=="ANONYMOUS_PIPE"){IntPtr r,w;if(!CreatePipe(out r,out w,ref sa,0))throw new InvalidOperationException("CreatePipe:"+Marshal.GetLastWin32Error());return new long[]{r.ToInt64(),w.ToInt64()};}if(kind=="NAMED_PIPE"){IntPtr h=CreateNamedPipeW(path,PIPE_ACCESS_DUPLEX,PIPE_TYPE_BYTE|PIPE_WAIT,1,512,512,0,ref sa);if(h==new IntPtr(-1))throw new InvalidOperationException("CreateNamedPipeW:"+Marshal.GetLastWin32Error());return new long[]{h.ToInt64()};}throw new ArgumentOutOfRangeException("kind");}
}
'@
}
function InvokeGitLaunchAuthorityFixture([string]$Mutation) {
    InitializeGitLaunchProbeRuntime;$fixtureExe=(Get-Process -Id $PID).Path;$deadline=3000;$reserve=800;$fault='';$concurrent=$false;$handles=@();$path=Join-Path ([IO.Path]::GetTempPath()) ('r7_q_'+[Guid]::NewGuid().ToString('N'));$old=@{};$code='exit 0';$expected=@();$clock=[Diagnostics.Stopwatch]::StartNew()
    try{
        switch($Mutation){
            'LAUNCH_UNLISTED_FILE_HANDLE'{$handles=@([R7GitLaunchProbeNative]::Create('FILE',$path));$code='$m='''+([string]$handles[0])+''';[void](Add-Type -Name N -Namespace R7Q -MemberDefinition ''[System.Runtime.InteropServices.DllImport("kernel32.dll")] public static extern bool GetHandleInformation(System.IntPtr h,out uint f);'');$f=0;if([R7Q.N]::GetHandleInformation([IntPtr][long]$m,[ref]$f)){exit 42}else{exit 90}'}
            {$_ -in @('LAUNCH_UNLISTED_ANONYMOUS_PIPE','LAUNCH_ONLY_THREE_STD_HANDLES')}{$handles=@([R7GitLaunchProbeNative]::Create('ANONYMOUS_PIPE',$path));$code='$m='''+([string]$handles[-1])+''';[void](Add-Type -Name N -Namespace R7Q -MemberDefinition ''[System.Runtime.InteropServices.DllImport("kernel32.dll")] public static extern bool GetHandleInformation(System.IntPtr h,out uint f);'');$f=0;if([R7Q.N]::GetHandleInformation([IntPtr][long]$m,[ref]$f)){exit 42}else{exit 90}';break}
            {$_ -in @('LAUNCH_CROSS_RUN_STDOUT','LAUNCH_CROSS_RUN_STDERR','LAUNCH_CROSS_RUN_STDIN','LAUNCH_CONCURRENT_HANDLE_ISOLATION')}{$concurrent=$true;break}
            'LAUNCH_UNLISTED_NAMED_PIPE'{$pipe='\\.\pipe\r7_q_'+[Guid]::NewGuid().ToString('N');$handles=@([R7GitLaunchProbeNative]::Create('NAMED_PIPE',$pipe));$code='$m='''+([string]$handles[0])+''';[void](Add-Type -Name N -Namespace R7Q -MemberDefinition ''[System.Runtime.InteropServices.DllImport("kernel32.dll")] public static extern bool GetHandleInformation(System.IntPtr h,out uint f);'');$f=0;if([R7Q.N]::GetHandleInformation([IntPtr][long]$m,[ref]$f)){exit 42}else{exit 90}'}
            'LAUNCH_ENV_SENTINEL_ABSENT'{$old['R7_Q_SENTINEL']=$env:R7_Q_SENTINEL;$env:R7_Q_SENTINEL='injected';$code='if($env:R7_Q_SENTINEL){exit 42}else{exit 90}'}
            'LAUNCH_GIT_TRACE_ABSENT'{$old['GIT_TRACE']=$env:GIT_TRACE;$env:GIT_TRACE='1';$code='if($env:GIT_TRACE){exit 42}else{exit 90}'}
            'LAUNCH_GIT_CONFIG_COUNT_ABSENT'{$old['GIT_CONFIG_COUNT']=$env:GIT_CONFIG_COUNT;$env:GIT_CONFIG_COUNT='1';$code='if($env:GIT_CONFIG_COUNT){exit 42}else{exit 90}'}
            'LAUNCH_GIT_DIR_ABSENT'{$old['GIT_DIR']=$env:GIT_DIR;$env:GIT_DIR=$path;$code='if($env:GIT_DIR){exit 42}else{exit 90}'}
            'LAUNCH_GIT_WORK_TREE_ABSENT'{$old['GIT_WORK_TREE']=$env:GIT_WORK_TREE;$env:GIT_WORK_TREE=$path;$code='if($env:GIT_WORK_TREE){exit 42}else{exit 90}'}
            'LAUNCH_GIT_OBJECT_DIRECTORY_ABSENT'{$old['GIT_OBJECT_DIRECTORY']=$env:GIT_OBJECT_DIRECTORY;$env:GIT_OBJECT_DIRECTORY=$path;$code='if($env:GIT_OBJECT_DIRECTORY){exit 42}else{exit 90}'}
            'LAUNCH_HOME_PROFILE_ABSENT'{$old['HOME']=$env:HOME;$old['USERPROFILE']=$env:USERPROFILE;$env:HOME=$path;$env:USERPROFILE=$path;$code='if($env:HOME-or$env:USERPROFILE){exit 42}else{exit 90}'}
            'LAUNCH_ENV_DUPLICATE_REJECTED'{$fault='ENV_DUPLICATE'}
            'LAUNCH_ENV_NUL_REJECTED'{$fault='ENV_NUL'}
            'LAUNCH_ATTRIBUTE_INIT_FAILURE'{$fault='ATTRIBUTE_INIT_FAIL'}
            'LAUNCH_HANDLE_LIST_UPDATE_FAILURE'{$fault='HANDLE_UPDATE_FAIL'}
            {$_ -in @('LAUNCH_JOB_ASSIGNMENT_FAILURE','LAUNCH_JOB_ASSIGNMENT_CHILD_TERMINATED','LAUNCH_NO_FAULT_SURVIVOR','LAUNCH_NO_PENDING_TASKS','LAUNCH_FAULT_DEADLINE_BOUNDED')}{$fault='JOB_ASSIGN_FAIL';$code='Start-Sleep -Seconds 30';break}
            'LAUNCH_JOB_ASSIGNMENT_CONFIRMATION_FAILURE'{$fault='JOB_ASSIGN_CONFIRM_FAIL';$code='Start-Sleep -Seconds 30'}
            {$_ -in @('LAUNCH_RESUME_FAILURE','LAUNCH_RESUME_JOB_CLEANUP')}{$fault='RESUME_FAIL';$code='Start-Sleep -Seconds 30';break}
            'LAUNCH_RESUME_CONFIRMATION_FAILURE'{$fault='RESUME_CONFIRM_FAIL';$code='Start-Sleep -Seconds 30'}
            'LAUNCH_HOSTILE_PATH_IGNORED'{$old['PATH']=$env:PATH;$env:PATH=$path;$code='if($env:PATH){exit 42}else{exit 90}'}
            default{throw 'Unknown launch-authority fixture mutation: '+$Mutation}
        }
        if($concurrent){$slow='-NoProfile -NonInteractive -EncodedCommand '+(EncodeLifecycleCommand 'Start-Sleep -Milliseconds 1200;exit 0');$fast='-NoProfile -NonInteractive -EncodedCommand '+(EncodeLifecycleCommand 'exit 0');$pair=@(InvokeConcurrentGitLaunchIsolationTest $fixtureExe $slow $fast ([IO.Path]::GetTempPath()) $deadline $reserve 65536);if($pair.Count-ne2-or[long]$pair[1].ElapsedMilliseconds-ge800){throw ([IO.InvalidDataException]::new('GIT_BATCH_CROSS_RUN_HANDLE_ISOLATION_FAILED|fast_elapsed_ms='+$pair[1].ElapsedMilliseconds))};throw ([IO.InvalidDataException]::new('GIT_BATCH_CROSS_RUN_HANDLE_ISOLATION_CONFIRMED|slow_pid='+$pair[0].ParentPid+';fast_pid='+$pair[1].ParentPid+';fast_elapsed_ms='+$pair[1].ElapsedMilliseconds+';tree_terminated=True'))}
        $arguments='-NoProfile -NonInteractive -EncodedCommand '+(EncodeLifecycleCommand $code)
        if($fault){return InvokeBoundedGitBatchProcessLaunchTest $fixtureExe $arguments ([IO.Path]::GetTempPath()) ([byte[]]@()) $expected $fault $deadline $reserve 65536}
        return InvokeBoundedGitBatchProcess $fixtureExe $arguments ([IO.Path]::GetTempPath()) ([byte[]]@()) $expected $deadline $reserve 65536
    } finally {
        foreach($entry in $old.GetEnumerator()){[Environment]::SetEnvironmentVariable([string]$entry.Key,$entry.Value,'Process')}
        foreach($handle in $handles){if([long]$handle-ne0){[void][R7GitLaunchProbeNative]::CloseHandle([IntPtr][long]$handle)}}
        if(Test-Path -LiteralPath $path){Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue}
        if($clock.ElapsedMilliseconds-gt4500){throw ([IO.InvalidDataException]::new('GIT_BATCH_PROCESS_TIMEOUT|launch-fixture-bound-exceeded='+$clock.ElapsedMilliseconds))}
    }
}

function InvokeGitP03AFixture([string]$Mutation) {
    InitializeGitBatchProcessRuntime
    $exe=(Get-Process -Id $PID).Path;$deadline=3000;$reserve=800;$marker=Join-Path ([IO.Path]::GetTempPath()) ('r7_p03a_'+[Guid]::NewGuid().ToString('N')+'.marker')
    $childCode='[IO.File]::WriteAllText('''+$marker.Replace("'","''")+''',''executed'');Start-Sleep -Seconds 20'
    $arguments='-NoProfile -NonInteractive -EncodedCommand '+(EncodeLifecycleCommand $childCode)
    $invokeFault={param([string]$SelectedFault,[int]$Confirmation=$reserve) InvokeBoundedGitBatchProcessLaunchTest $exe $arguments ([IO.Path]::GetTempPath()) ([byte[]]@()) @() $SelectedFault $deadline $reserve 65536 $Confirmation}
    try{
        $confirmation=$reserve
        switch($Mutation){
            'P03A_JOB_LIST_SIZE_FAILURE'{$fault='JOB_LIST_SIZE_FAIL'}
            'P03A_JOB_LIST_INIT_FAILURE'{$fault='JOB_LIST_INIT_FAIL'}
            'P03A_JOB_LIST_UPDATE_FAILURE'{$fault='JOB_LIST_UPDATE_FAIL'}
            'P03A_JOB_AT_CREATION_REJECTION'{$fault='JOB_LIST_CLOSED_HANDLE'}
            'P03A_NO_CHILD_ON_CREATION_REJECTION'{$fault='JOB_LIST_NONJOB_HANDLE'}
            'P03A_PRE_RESUME_QUERY_FAILURE'{$fault='PRE_RESUME_QUERY_FAIL'}
            'P03A_PRE_RESUME_ACTIVE_UNEXPECTED'{$fault='PRE_RESUME_ACTIVE_UNEXPECTED'}
            'P03A_ACTUAL_RESUME_FAILURE'{$fault='RESUME_ACTUAL_FAIL'}
            'P03A_UNEXPECTED_SUSPEND_COUNT'{$fault='RESUME_SUSPEND_COUNT'}
            'P03A_RESUME_JOB_CLEANUP'{$fault='POST_TASK_FORCED_CLEANUP'}
            'P03A_JOB_TERMINATION_FAILURE'{$fault='RESUME_ACTUAL_FAIL_TERMINATE_JOB_FAIL'}
            'P03A_PROCESS_TERMINATION_FAILURE'{$fault='RESUME_ACTUAL_FAIL_TERMINATE_PROCESS_FAIL'}
            'P03A_BOTH_TERMINATIONS_FAIL_FINAL_ZERO'{$fault='RESUME_ACTUAL_FAIL_BOTH_TERMINATION_FAIL_FINAL_ZERO'}
            'P03A_FINAL_QUERY_FAILURE'{$fault='RESUME_ACTUAL_FAIL_FINAL_QUERY_FAIL'}
            'P03A_PARENT_WAIT_FAILURE'{$fault='RESUME_ACTUAL_FAIL_PARENT_WAIT_FAIL'}
            'P03A_CLEANUP_DEADLINE_EXHAUSTION'{$fault='POST_TASK_TOTAL_DEADLINE'}
            'P03A_PREQUERY_AND_FINAL_QUERY_FAILURE'{$fault='PRE_RESUME_QUERY_FAIL_FINAL_QUERY_FAIL'}
            'P03A_PRE_RESUME_MARKER_ABSENT'{$fault='PRE_RESUME_ACTIVE_UNEXPECTED_MARKER'}
            'P03A_TASKS_TERMINAL'{$fault='RESUME_ACTUAL_FAIL_TASK_NOT_STARTED'}
            'P03A_ORIGINAL_DEADLINE_BOUND'{$fault='PRIMARY_LATE_PROCESS_TRANSITION';$confirmation=1}
            'P03A_NO_CHILD_REPEATED_CREATE_FAILURE'{for($i=0;$i-lt50;$i++){try{&$invokeFault 'JOB_LIST_CLOSED_HANDLE';throw 'P03A_UNEXPECTED_PASS'}catch{if($_.Exception.Message-notmatch'^GIT_BATCH_JOB_AT_CREATION_FAILED\|'){throw}}};throw ([IO.InvalidDataException]::new('P03A_REPEATED_CREATE_FAILURE_CONFIRMED|count=50;child_created=False;external_survivor=False'))}
            'P03A_REPEATED_JOB_AT_CREATION_FAILURES'{for($i=0;$i-lt50;$i++){try{&$invokeFault 'JOB_LIST_NONJOB_HANDLE';throw 'P03A_UNEXPECTED_PASS'}catch{if($_.Exception.Message-notmatch'^GIT_BATCH_JOB_AT_CREATION_FAILED\|'){throw}}};throw ([IO.InvalidDataException]::new('P03A_REPEATED_CREATE_FAILURE_CONFIRMED|count=50;child_created=False;external_survivor=False'))}
            'P03A_ATTRIBUTE_ALLOCATION_CLEANUP'{$before=[R7GitBatchProcessRunner]::GetResourceCounters();$processBefore=Get-Process -Id $PID;foreach($selected in @('JOB_LIST_INIT_FAIL','JOB_LIST_UPDATE_FAIL')){for($i=0;$i-lt25;$i++){try{&$invokeFault $selected;throw 'P03A_UNEXPECTED_PASS'}catch{if($_.Exception.Message-notmatch'^GIT_BATCH_(JOB_LIST_ATTRIBUTE_FAILED|CREATE_PROCESS_FAILED)\|'){throw}}}};[GC]::Collect();[GC]::WaitForPendingFinalizers();$after=[R7GitBatchProcessRunner]::GetResourceCounters();$processAfter=Get-Process -Id $PID;$attributeAlloc=$after.AttributeAllocations-$before.AttributeAllocations;$attributeFree=$after.AttributeFrees-$before.AttributeFrees;$attributeInit=$after.AttributeInitializations-$before.AttributeInitializations;$attributeDelete=$after.AttributeDeletes-$before.AttributeDeletes;$environmentAlloc=$after.EnvironmentAllocations-$before.EnvironmentAllocations;$environmentFree=$after.EnvironmentFrees-$before.EnvironmentFrees;if($attributeAlloc-ne$attributeFree-or$attributeInit-ne$attributeDelete-or$environmentAlloc-ne$environmentFree){throw 'P03A_RESOURCE_RECONCILIATION_FAILED'};throw ([IO.InvalidDataException]::new('P03A_ATTRIBUTE_CLEANUP_CONFIRMED|count=50;attribute_alloc='+$attributeAlloc+';attribute_free='+$attributeFree+';attribute_init='+$attributeInit+';attribute_delete='+$attributeDelete+';environment_alloc='+$environmentAlloc+';environment_free='+$environmentFree+';handle_delta='+($processAfter.HandleCount-$processBefore.HandleCount)+';thread_delta='+($processAfter.Threads.Count-$processBefore.Threads.Count)))}
            'P03A_REPEATED_RESUME_FAILURE'{$externalChecks=0;for($i=0;$i-lt50;$i++){try{&$invokeFault 'RESUME_ACTUAL_FAIL';throw 'P03A_UNEXPECTED_PASS'}catch{if($_.Exception.Message-notmatch'^GIT_BATCH_PROCESS_RESUME_FAILED\|' -or $_.Exception.Message-notmatch'survivor=False'){throw};if($_.Exception.Message-match'parent_pid=([1-9][0-9]*)'){$externalChecks++;if(Get-Process -Id ([int]$Matches[1]) -ErrorAction SilentlyContinue){throw 'P03A_EXTERNAL_SURVIVOR_DETECTED'}}}};throw ([IO.InvalidDataException]::new('P03A_REPEATED_RESUME_FAILURE_CONFIRMED|count=50;external_pid_checks='+$externalChecks+';child_executed=False;external_survivor=False'))}
            'P03A_AUTHENTIC_CONTAINED_LAUNCH'{$script:treeAuthorityCacheKey='';$script:treeAuthorityCache=@{};$script:gitBlobByteCache=@{};InitializeTreeAuthorityCache;if($script:treeAuthorityCache.Count-ne44){throw 'P03A_AUTHENTIC_GIT_ROW_COUNT'};$generator=$script:treeAuthorityCache['Architecture/Audits/2026-07-24_R7_Terminal_Authority_Architecture_Remediation_DRAFT/build_unit2_upgrade_authority.ps1'];if($null-eq$generator-or[string]$generator.git_blob_identity-cne'abe763a9517a87f89c0db3a9b7a176b26cb9ec67'){throw 'P03A_AUTHENTIC_GIT_IDENTITY'};throw ([IO.InvalidDataException]::new('P03A_AUTHENTIC_CONTAINED_LAUNCH_CONFIRMED|authenticated_git=True;tree_rows=44;generator_oid='+$generator.git_blob_identity+';exact_eof=True;zero_exit=True;tree_terminated=True;input_state=Completed;stdout_state=Completed;stderr_state=Completed'))}
            'P03A_TASK_COMPLETED'{$clean='-NoProfile -NonInteractive -EncodedCommand '+(EncodeLifecycleCommand 'exit 0');$result=InvokeBoundedGitBatchProcess $exe $clean ([IO.Path]::GetTempPath()) ([byte[]]@()) @() $deadline $reserve 65536;if($result.InputTaskState-cne'Completed'-or$result.StdoutTaskState-cne'Completed'-or$result.StderrTaskState-cne'Completed'){throw 'P03A_TASK_COMPLETED_MISMATCH'};throw ([IO.InvalidDataException]::new('P03A_TASK_STATE_CONFIRMED|input_state=Completed;stdout_state=Completed;stderr_state=Completed'))}
            'P03A_TASK_FAULTED'{$fault='POST_TASK_INPUT_FAULT'}
            'P03A_TASK_CANCELED'{$fault='POST_TASK_INPUT_CANCELED'}
            default{throw 'Unknown P-03A fixture mutation: '+$Mutation}
        }
        $clock=[Diagnostics.Stopwatch]::StartNew();try{&$invokeFault $fault $confirmation;throw 'P03A_UNEXPECTED_PASS'}catch{if($_.Exception.Message-ceq'P03A_UNEXPECTED_PASS'){throw};$message=$_.Exception.Message;$markerPresent=Test-Path -LiteralPath $marker;$allowMarker=$Mutation-in@('P03A_RESUME_JOB_CLEANUP','P03A_TASK_FAULTED','P03A_TASK_CANCELED','P03A_CLEANUP_DEADLINE_EXHAUSTION','P03A_ORIGINAL_DEADLINE_BOUND');if($markerPresent-and-not$allowMarker){throw ([IO.InvalidDataException]::new('P03A_CHILD_EXECUTION_DETECTED|mutation='+$Mutation))};$externalPid=0;$externalSurvivor=$false;if($message-match'parent_pid=([1-9][0-9]*)'){$externalPid=[int]$Matches[1];$externalSurvivor=$null-ne(Get-Process -Id $externalPid -ErrorAction SilentlyContinue)};if($externalSurvivor){throw ([IO.InvalidDataException]::new('P03A_EXTERNAL_SURVIVOR_DETECTED|pid='+$externalPid))};if($clock.ElapsedMilliseconds-gt($deadline+500)){throw ([IO.InvalidDataException]::new('P03A_DEADLINE_BOUND_EXCEEDED|elapsed_ms='+$clock.ElapsedMilliseconds))};throw ([IO.InvalidDataException]::new($message+';marker_absent='+(-not$markerPresent)+';marker_present='+$markerPresent+';external_pid_checked='+($externalPid-gt0)+';external_survivor=False;fixture_elapsed_ms='+$clock.ElapsedMilliseconds))}
    } finally {if(Test-Path -LiteralPath $marker){Remove-Item -LiteralPath $marker -Force -ErrorAction SilentlyContinue}}
}

function InvokeNegativeCases([object]$Receipt,[object]$Determinism,[object]$NegativeRegistry) {
    $negativeResults=[Collections.Generic.List[object]]::new()
    foreach($case in @($NegativeRegistry.cases)){
        $mutated=Clone $Receipt;$detMutated=Clone $Determinism;$overrides=@{};$provenance=@{};$role=$mutated.roles[0];$directParserMutation=$null;$directLifecycleMutation=$null;$directLaunchMutation=$null;$directP03AMutation=$null
        switch([string]$case.mutation){
            'OMIT_COMMITTED_COMPILER_INPUT'{$role.compiler_inputs=@($role.compiler_inputs|Select-Object -Skip 1)}
            'OMIT_GENERATED_COMPILER_INPUT'{$role.compiler_inputs=@($role.compiler_inputs|Where-Object{[string]$_.path-notlike'Generated/*'})}
            'REMOVE_REQUIRED_COMPILER_ARGUMENT'{$role.compiler_arguments.pass_a=@($role.compiler_arguments.pass_a|Where-Object{[string]$_-cne'/warnaserror+'})}
            'ZERO_EMBEDDED_IDENTITY'{$role.embedded_identity.'R7BuildIdentity.SourceCommit'=('0'*40)}
            'DIAGNOSTIC_EMBEDDED_IDENTITY'{$role.embedded_identity.'R7BuildIdentity.IdentityBindingKind'='DEVELOPMENT'}
            'TOKEN_IN_NONCOMPILED_SOURCE_REGION'{$path=[string]$mutated.generated_sources[0].path;$overrides[$path]=([IO.File]::ReadAllText((Join-Path $build $path.Replace('/','\')))+"`r`n#if NEVER`r`n// UNIT2_GENERATED_FORBIDDEN`r`n#endif`r`n")}
            'PACKAGED_TOOL_DIAGNOSTIC_IDENTITY'{$role=@($mutated.roles|Where-Object{[string]$_.role-ceq'PACKAGED_ARTIFACT_TOOL'})[0];$role.embedded_identity.'R7BuildIdentity.IdentityBindingKind'='PLACEHOLDER'}
            'RECEIPT_SOURCE_NOT_IN_ARGUMENT_VECTOR'{$role.compiler_arguments.pass_a=@($role.compiler_arguments.pass_a|Where-Object{[string]$_-cne(Join-Path $repositoryRoot ([string]$mutated.source_files[0].path).Replace('/','\'))})}
            'ARGUMENT_SOURCE_NOT_IN_RECEIPT'{$role.compiler_arguments.pass_a+=('C:\Temp\unrecorded-input.cs')}
            'REORDER_COMPILER_ARGUMENTS'{$arguments=@($role.compiler_arguments.pass_a);$left=[Array]::IndexOf([string[]]$arguments,'/target:exe');$right=[Array]::IndexOf([string[]]$arguments,'/platform:x64');if($left-lt0-or$right-lt0){throw 'Negative reorder fixture invalid'};$value=$arguments[$left];$arguments[$left]=$arguments[$right];$arguments[$right]=$value;$role.compiler_arguments.pass_a=$arguments}
            'SUBSTITUTE_COMPILER_ARGUMENT'{$arguments=@($role.compiler_arguments.pass_a);$index=[Array]::IndexOf([string[]]$arguments,'/optimize+');if($index-lt0){throw 'Negative argument-substitution fixture invalid'};$arguments[$index]='/optimize-';$role.compiler_arguments.pass_a=$arguments}
            'DUPLICATE_COMPILER_ARGUMENT'{$arguments=[Collections.Generic.List[string]]::new();foreach($argument in @($role.compiler_arguments.pass_a)){$arguments.Add([string]$argument)};$index=$arguments.IndexOf('/checked+');if($index-lt0){throw 'Negative argument-duplicate fixture invalid'};$arguments.Insert($index+1,'/checked+');$role.compiler_arguments.pass_a=$arguments.ToArray()}
            'SUBSTITUTE_COMPILER_INPUT_RAW_SHA256'{$inputRecord=@($role.compiler_inputs|Where-Object{[string]$_.path-notlike'Generated/*'})[0];$inputRecord.raw_sha256=('a'*64-join'')}
            'SUBSTITUTE_COMPILER_INPUT_SIZE'{$inputRecord=@($role.compiler_inputs|Where-Object{[string]$_.path-notlike'Generated/*'})[0];$inputRecord.size=[long]$inputRecord.size+1}
            'SUBSTITUTE_COMMITTED_GIT_BLOB'{$inputRecord=@($role.compiler_inputs|Where-Object{[string]$_.path-notlike'Generated/*'})[0];$inputRecord.git_blob_identity=('b'*40-join'')}
            'SUBSTITUTE_COMPILER_INPUT_MODE'{$inputRecord=@($role.compiler_inputs|Where-Object{[string]$_.path-notlike'Generated/*'})[0];$inputRecord.mode='100755'}
            'SUBSTITUTE_GENERATED_INPUT_AUTHORITY'{$inputRecord=@($role.compiler_inputs|Where-Object{[string]$_.path-like'Generated/*'})[0];$inputRecord.generator.raw_sha256=('c'*64-join'')}
            'COMPILER_INPUT_SIZE_NUMBER_TO_STRING'{$inputRecord=@($role.compiler_inputs|Where-Object{[string]$_.path-notlike'Generated/*'})[0];$inputRecord.size=[string]$inputRecord.size}
            'COMPILER_INPUT_MODE_STRING_TO_NUMBER'{$inputRecord=@($role.compiler_inputs|Where-Object{[string]$_.path-notlike'Generated/*'})[0];$inputRecord.mode=[int]$inputRecord.mode}
            'COMMITTED_NULL_GENERATION_RULE_TO_SENTINEL'{$inputRecord=@($role.compiler_inputs|Where-Object{[string]$_.path-notlike'Generated/*'})[0];$inputRecord.generation_rule='<null>'}
            'COMMITTED_NULL_GENERATOR_TO_SENTINEL'{$inputRecord=@($role.compiler_inputs|Where-Object{[string]$_.path-notlike'Generated/*'})[0];$inputRecord.generator='<null>'}
            'GENERATED_NULL_GIT_BLOB_TO_SENTINEL'{$inputRecord=@($role.compiler_inputs|Where-Object{[string]$_.path-like'Generated/*'})[0];$inputRecord.git_blob_identity='<null>'}
            'GENERATED_NULL_MODE_TO_SENTINEL'{$inputRecord=@($role.compiler_inputs|Where-Object{[string]$_.path-like'Generated/*'})[0];$inputRecord.mode='<null>'}
            'DETERMINISM_COMPILER_INPUT_HASH_CHANGED'{$detMutated.role_determinism[0].compiler_inputs[0].raw_sha256=('d'*64-join'')}
            'DETERMINISM_COMPILER_INPUT_REMOVED'{$detMutated.role_determinism[0].compiler_inputs=@($detMutated.role_determinism[0].compiler_inputs|Select-Object -Skip 1)}
            'DETERMINISM_COMPILER_INPUT_ADDED'{$detMutated.role_determinism[0].compiler_inputs=@($detMutated.role_determinism[0].compiler_inputs)+@(Clone $detMutated.role_determinism[0].compiler_inputs[0])}
            'DETERMINISM_COMPILER_INPUTS_REORDERED'{$inputs=@($detMutated.role_determinism[0].compiler_inputs);$value=$inputs[0];$inputs[0]=$inputs[1];$inputs[1]=$value;$detMutated.role_determinism[0].compiler_inputs=$inputs}
            'DETERMINISM_COMPILER_INPUT_SIZE_NUMBER_TO_STRING'{$detMutated.role_determinism[0].compiler_inputs[0].size=[string]$detMutated.role_determinism[0].compiler_inputs[0].size}
            'COORDINATED_GENERATED_PRODUCER_AUTHORITY_AND_ROLE'{$generated=$mutated.generated_sources[0];$source=$mutated.source_files[1];$fake=[ordered]@{git_blob_identity=[string]$source.git_blob_identity;path=[string]$source.path;raw_sha256=[string]$source.raw_sha256};$generated.generator=Clone $fake;foreach($consumer in @($mutated.roles)){foreach($inputRecord in @($consumer.compiler_inputs|Where-Object{[string]$_.path-ceq[string]$generated.path})){$inputRecord.generator=Clone $fake}}}
            'COORDINATED_GENERATED_PRODUCER_ALL_RECEIPTS'{$generated=$mutated.generated_sources[0];$source=$mutated.source_files[1];$fake=[ordered]@{git_blob_identity=[string]$source.git_blob_identity;path=[string]$source.path;raw_sha256=[string]$source.raw_sha256};$generated.generator=Clone $fake;foreach($consumer in @($mutated.roles)){foreach($inputRecord in @($consumer.compiler_inputs|Where-Object{[string]$_.path-ceq[string]$generated.path})){$inputRecord.generator=Clone $fake}};foreach($consumer in @($detMutated.role_determinism)){foreach($inputRecord in @($consumer.compiler_inputs|Where-Object{[string]$_.path-ceq[string]$generated.path})){$inputRecord.generator=Clone $fake}}}
            'UNAUTHORIZED_GENERATED_SOURCE_ROLE_ASSIGNMENT'{$donor=@($mutated.roles|Where-Object{[string]$_.role-ceq'PACKAGED_ARTIFACT_TOOL'})[0];$donorInput=Clone @($donor.compiler_inputs|Where-Object{[string]$_.path-like'Generated/*'})[0];$inputIndex=0;for(;$inputIndex-lt$role.compiler_inputs.Count;$inputIndex++){if([string]$role.compiler_inputs[$inputIndex].path-like'Generated/*'){break}};$role.compiler_inputs[$inputIndex]=$donorInput}
            'MISSING_FIELD_REPLACES_EXPLICIT_NULL'{$inputRecord=@($role.compiler_inputs|Where-Object{[string]$_.path-notlike'Generated/*'})[0];$inputRecord.PSObject.Properties.Remove('generation_rule')}
            'UNKNOWN_COMPILER_INPUT_FIELD'{$inputRecord=@($role.compiler_inputs|Where-Object{[string]$_.path-notlike'Generated/*'})[0];$inputRecord|Add-Member -NotePropertyName ungoverned_identity -NotePropertyValue 'forbidden'}
            'CRLF_COMPILER_MATERIALIZATION'{$source=$mutated.source_files[0];$authority=ExactTreeBlobAuthority ([string]$source.path);$crlf=CrLfFixtureBytes (ReadGitBlobBytes ([string]$authority.git_blob_identity));$provenance['compiler_sha256:'+[string]$source.path]=BytesHash $crlf;$provenance['compiler_size:'+[string]$source.path]=[long]$crlf.Length}
            'WORKTREE_PSEUDO_BLOB_FOR_TREE_BLOB'{$source=$mutated.source_files[0];$authority=ExactTreeBlobAuthority ([string]$source.path);$crlf=CrLfFixtureBytes (ReadGitBlobBytes ([string]$authority.git_blob_identity));$source.git_blob_identity=UntrustedFixtureBlobIdentity $crlf;foreach($consumer in @($mutated.roles)+@($detMutated.role_determinism)){foreach($inputRecord in @($consumer.compiler_inputs|Where-Object{[string]$_.path-ceq[string]$source.path})){$inputRecord.git_blob_identity=$source.git_blob_identity}}}
            'WORKTREE_SHA_FOR_COMMITTED_SHA'{$source=$mutated.source_files[0];$authority=ExactTreeBlobAuthority ([string]$source.path);$crlf=CrLfFixtureBytes (ReadGitBlobBytes ([string]$authority.git_blob_identity));$source.raw_sha256=BytesHash $crlf;$source.size=[long]$crlf.Length;foreach($consumer in @($mutated.roles)+@($detMutated.role_determinism)){foreach($inputRecord in @($consumer.compiler_inputs|Where-Object{[string]$_.path-ceq[string]$source.path})){$inputRecord.raw_sha256=$source.raw_sha256;$inputRecord.size=$source.size}}}
            'WORKTREE_SIZE_FOR_COMMITTED_SIZE'{$source=$mutated.source_files[0];$source.size=[long]$source.size+1;foreach($consumer in @($mutated.roles)+@($detMutated.role_determinism)){foreach($inputRecord in @($consumer.compiler_inputs|Where-Object{[string]$_.path-ceq[string]$source.path})){$inputRecord.size=$source.size}}}
            'UNGOVERNED_COMPILER_BYTE_MUTATION'{$source=$mutated.source_files[0];$provenance['compiler_sha256:'+[string]$source.path]='e'*64}
            'COORDINATED_CONFIGURATION_HASH_AND_CONSUMERS'{$config=$mutated.configuration_inputs[0];$old=[string]$config.raw_sha256;$config.raw_sha256='e'*64;foreach($generated in @($mutated.generated_sources)){foreach($inputRecord in @($generated.source_inputs)){if([string]$inputRecord.role-ceq[string]$config.role-and[string]$inputRecord.identity-ceq$old){$inputRecord.identity=$config.raw_sha256}}}}
            'COORDINATED_CONFIGURATION_PATH_SIZE_AND_CONSUMERS'{$config=$mutated.configuration_inputs[0];$old=[string]$config.raw_sha256;$config.path='C:\Temp\forged-authority-source-manifest.json';$config.raw_sha256='d'*64;$config.size=[long]$config.size+17;foreach($generated in @($mutated.generated_sources)){foreach($inputRecord in @($generated.source_inputs)){if([string]$inputRecord.role-ceq[string]$config.role-and[string]$inputRecord.identity-ceq$old){$inputRecord.identity=$config.raw_sha256}}}}
            'CONFIGURATION_INPUT_REMOVED'{$mutated.configuration_inputs=@($mutated.configuration_inputs|Select-Object -Skip 1)}
            'CONFIGURATION_INPUT_INSERTED'{$mutated.configuration_inputs=@(Clone $mutated.configuration_inputs[0])+@($mutated.configuration_inputs)}
            'CONFIGURATION_INPUTS_REORDERED'{$rows=@($mutated.configuration_inputs);$value=$rows[0];$rows[0]=$rows[1];$rows[1]=$value;$mutated.configuration_inputs=$rows}
            'COORDINATED_CLOSURE_AND_CONSUMERS'{$old=[string]$mutated.build_input_closure_sha256;$mutated.build_input_closure_sha256='f'*64;$detMutated.build_input_closure_sha256=$mutated.build_input_closure_sha256;foreach($generated in @($mutated.generated_sources)){foreach($inputRecord in @($generated.source_inputs)){if([string]$inputRecord.role-ceq'BUILD_INPUT_CLOSURE'-and[string]$inputRecord.identity-ceq$old){$inputRecord.identity=$mutated.build_input_closure_sha256}}}}
            'COORDINATED_POLICY_AND_CONSUMERS'{$old=[string]$mutated.policy_sha256;$mutated.policy_sha256='9'*64;foreach($generated in @($mutated.generated_sources)){foreach($inputRecord in @($generated.source_inputs)){if([string]$inputRecord.role-ceq'COMPLETED_UNIT2_POLICY'-and[string]$inputRecord.identity-ceq$old){$inputRecord.identity=$mutated.policy_sha256}}}}
            'POLICY_ARTIFACT_PATH_SUBSTITUTED'{$provenance.policy_path=Join-Path $build 'Generated\forged_unit2_upgrade_policy.json'}
            'COORDINATED_GENERATED_SOURCE_INPUTS_ALL_RECEIPTS'{$config=$mutated.configuration_inputs[0];$old=[string]$config.raw_sha256;$config.raw_sha256='8'*64;foreach($container in @($mutated.generated_sources)+@($detMutated.generated_sources)){foreach($inputRecord in @($container.source_inputs)){if([string]$inputRecord.role-ceq[string]$config.role-and[string]$inputRecord.identity-ceq$old){$inputRecord.identity=$config.raw_sha256}}}}
            'SOURCE_COMMIT_RETAINING_CONSUMERS'{$mutated.source_commit='a'*40;$detMutated.source_commit=$mutated.source_commit}
            'TREE_BLOB_CHANGED_WITH_ALL_CONSUMERS'{$source=$mutated.source_files[0];$source.git_blob_identity='c'*40;foreach($consumer in @($mutated.roles)+@($detMutated.role_determinism)){foreach($inputRecord in @($consumer.compiler_inputs|Where-Object{[string]$_.path-ceq[string]$source.path})){$inputRecord.git_blob_identity=$source.git_blob_identity}}}
            'CLOSURE_SERIALIZATION_ORDER_CHANGED'{$provenance.closure_reorder=$true}
            'FORGED_RECEIPTS_ORIGINAL_GENERATED_OUTPUT'{$oldClosure=[string]$mutated.build_input_closure_sha256;$oldPolicy=[string]$mutated.policy_sha256;$mutated.build_input_closure_sha256='7'*64;$detMutated.build_input_closure_sha256=$mutated.build_input_closure_sha256;$mutated.policy_sha256='6'*64;foreach($container in @($mutated.generated_sources)+@($detMutated.generated_sources)){foreach($inputRecord in @($container.source_inputs)){if([string]$inputRecord.role-ceq'BUILD_INPUT_CLOSURE'-and[string]$inputRecord.identity-ceq$oldClosure){$inputRecord.identity=$mutated.build_input_closure_sha256};if([string]$inputRecord.role-ceq'COMPLETED_UNIT2_POLICY'-and[string]$inputRecord.identity-ceq$oldPolicy){$inputRecord.identity=$mutated.policy_sha256}}}}
            {$_ -like 'BATCH_*'}{$directParserMutation=[string]$_}
            {$_ -like 'LIFECYCLE_*'}{$directLifecycleMutation=[string]$_}
            {$_ -like 'LAUNCH_*'}{$directLaunchMutation=[string]$_}
            {$_ -like 'P03A_*'}{$directP03AMutation=[string]$_}
            default{throw "Unknown negative mutation: $($case.mutation)"}
        }
        $observed=$null;$observedDetail=''
        try{if($null-ne$directParserMutation){[void](InvokeGitBatchParserFixture $directParserMutation)}elseif($null-ne$directLifecycleMutation){[void](InvokeGitBatchLifecycleFixture $directLifecycleMutation)}elseif($null-ne$directLaunchMutation){[void](InvokeGitLaunchAuthorityFixture $directLaunchMutation)}elseif($null-ne$directP03AMutation){[void](InvokeGitP03AFixture $directP03AMutation)}else{ValidateModel $mutated $detMutated $overrides $provenance};throw 'NEGATIVE_CASE_UNEXPECTED_PASS'}catch{if($_.Exception.Message-ceq'NEGATIVE_CASE_UNEXPECTED_PASS'){throw};$parts=$_.Exception.Message-split'\|',2;$observed=$parts[0];if($parts.Count-gt1){$observedDetail=$parts[1]}}
        if($observed-cne[string]$case.expected_error){throw "Negative case wrong rejection: $($case.case_id) expected $($case.expected_error) observed $observed"}
        if(HasField $case 'expected_detail_pattern'){if($observedDetail-cnotmatch[string]$case.expected_detail_pattern){throw "Negative case wrong detail: $($case.case_id) observed $observedDetail"}}
        $negativeResults.Add([ordered]@{case_id=[string]$case.case_id;expected_detail=$observedDetail;expected_error=[string]$case.expected_error;mutation=[string]$case.mutation;observed_error=$observed;status='PASS'})
    }
    return $negativeResults.ToArray()
}

if((Hash $PSCommandPath) -cne $ExpectedScriptSha256){throw 'Verifier script identity mismatch'}
foreach($required in @($receiptPath,$determinismPath,$manifestPath,$negativePath,$contractPath)){if(-not(Test-Path -LiteralPath $required -PathType Leaf)){throw "Required verification input missing: $required"}}
$receipt=ReadJson $receiptPath;$determinism=ReadJson $determinismPath;$manifest=ReadJson $manifestPath
if([string]$receipt.artifact_type -cne 'R7_UNIT2_UPGRADE_AUTHORITY_SOURCE_TO_BINARY_RECEIPT' -or [string]$receipt.schema_version -cne '2.0.0'){throw 'Source-to-binary receipt header invalid'}
if([string]$determinism.artifact_type -cne 'R7_UNIT2B_BUILD_DETERMINISM_RECEIPT' -or [string]$determinism.status -cne 'PASS'){throw 'Determinism receipt header invalid'}
if([string]$manifest.status -cne 'PASS' -or [string]$manifest.build_receipt_sha256 -cne (Hash $receiptPath) -or [string]$manifest.build_determinism_receipt_sha256 -cne (Hash $determinismPath)){throw 'Build manifest receipt binding invalid'}
if([string]$receipt.source_commit -cne $SourceCommit -or [string]$determinism.source_commit -cne $SourceCommit -or [string]$manifest.source_commit -cne $SourceCommit){throw 'Source commit binding invalid'}

$utility=ReadJson (Join-Path $packageRoot 'external_utility_registry.json');$gitRow=@($utility.utilities|Where-Object{[string]$_.role -ceq 'GIT_BUILD_AND_VERIFICATION'});if($gitRow.Count-ne 1){throw 'Governed Git row invalid'};$git=[string]$gitRow[0].path;$safe=$repositoryRoot.Replace('\','/')
$head=(& $git --no-pager -c "safe.directory=$safe" -C $repositoryRoot rev-parse HEAD).Trim();if($head-cne $SourceCommit){throw 'Verification HEAD mismatch'}
$status=@(& $git --no-pager -c "safe.directory=$safe" -C $repositoryRoot status --porcelain=v1 --untracked-files=all);if(-not $CandidateWorktree -and $status.Count-ne 0){throw 'Exact verification checkout is not clean'}
if(-not $CandidateWorktree){$tree=(& $git --no-pager -c "safe.directory=$safe" -C $repositoryRoot show -s --format=%T $SourceCommit).Trim();if([string]$receipt.source_tree-cne $tree -or [string]$determinism.source_tree-cne $tree){throw 'Exact source tree binding invalid'}}

$actualSources=@(Get-ChildItem -LiteralPath (Join-Path $packageRoot 'Source') -Filter '*.cs' -File|Sort-Object Name|ForEach-Object FullName)+$contractPath
$expectedSourceRows=@(CommittedAuthorityRows @{})
$receiptSourceRows=@($receipt.source_files)
if($expectedSourceRows.Count-ne $receiptSourceRows.Count){throw 'Exact source inventory count mismatch'}
for($index=0;$index-lt $expectedSourceRows.Count;$index++){foreach($field in @('git_blob_identity','mode','path','raw_sha256','size')){$expectedValue=[string](FieldValue $expectedSourceRows[$index] $field);$actualValue=[string](FieldValue $receiptSourceRows[$index] $field);if($expectedValue-cne$actualValue){throw "Exact source inventory mismatch: $($expectedSourceRows[$index].path)/$field"}}}

$generatedNames=@($receipt.generated_sources|ForEach-Object{[string]$_.path}|Sort-Object);$expectedGenerated=@('Generated/R7PackagedTools.g.cs','Generated/R7Unit2BuildBootstrap.g.cs','Generated/R7Unit2ClientShared.g.cs','Generated/R7Unit2Service.g.cs')
if(($generatedNames-join "`n")-cne($expectedGenerated-join "`n")){throw 'Generated source inventory mismatch'}
foreach($row in @($receipt.generated_sources)){$path=Join-Path $build ([string]$row.path).Replace('/','\');if((Hash $path)-cne[string]$row.raw_sha256 -or (Get-Item -LiteralPath $path).Length-ne[long]$row.size -or [string]$row.output_identity-cne[string]$row.raw_sha256){throw "Generated source identity mismatch: $($row.path)"};if(SourceTokenInvalid ([IO.File]::ReadAllText($path))){throw "Generated source token invalid: $($row.path)"}}

$roleNames=@($receipt.roles|ForEach-Object{[string]$_.role}|Sort-Object);if(($roleNames-join "`n")-cne(($requiredRoles|Sort-Object)-join "`n")){throw 'Binary role set mismatch'}
ValidateModel $receipt $determinism @{}
foreach($role in @($receipt.roles)){
    $passA=[IO.Path]::GetFullPath([string]$role.pass_a_path);$passB=[IO.Path]::GetFullPath([string]$role.pass_b_path)
    if(-not $passA.StartsWith($build.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)-or-not $passB.StartsWith($build.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)){throw "Binary path escaped build root: $($role.role)"}
    if((Hash $passA)-cne[string]$role.pass_a_sha256 -or (Hash $passB)-cne[string]$role.pass_b_sha256 -or (Get-Item -LiteralPath $passA).Length-ne[long]$role.size -or $role.normalized_il_equal-ne$true){throw "Binary identity mismatch: $($role.role)"}
    $actualIdentity=ExtractIdentity $passA
    foreach($property in $role.embedded_identity.PSObject.Properties){if(-not $actualIdentity.Contains($property.Name)-or[string]$actualIdentity[$property.Name]-cne[string]$property.Value){throw "Extracted identity mismatch: $($role.role)/$($property.Name)"}}
}
$packagedArtifact=@($receipt.roles|Where-Object{[string]$_.role-ceq'PACKAGED_ARTIFACT_TOOL'})[0];$packagedProtected=@($receipt.roles|Where-Object{[string]$_.role-ceq'PACKAGED_PROTECTED_METADATA_TOOL'})[0]
if((Hash (Join-Path $build 'Tools\R7ArtifactTool.exe'))-cne[string]$packagedArtifact.pass_a_sha256 -or (Hash (Join-Path $build 'Tools\R7ProtectedMetadataTool.exe'))-cne[string]$packagedProtected.pass_a_sha256){throw 'Packaged tool copy identity mismatch'}
$targetRoot=Join-Path $build 'TargetStaging';$targetRows=@($receipt.target_packaged_executables|Sort-Object path);$actualTargetExecutables=@(Get-ChildItem -LiteralPath $targetRoot -Filter '*.exe' -File -Recurse|Sort-Object FullName)
if($targetRows.Count-ne$actualTargetExecutables.Count-or$targetRows.Count-eq0){throw 'Target packaged executable inventory mismatch'}
for($index=0;$index-lt$targetRows.Count;$index++){
    $actualPath='Staging/'+$actualTargetExecutables[$index].FullName.Substring($targetRoot.Length+1).Replace('\','/')
    if([string]$targetRows[$index].path-cne$actualPath-or[string]$targetRows[$index].raw_sha256-cne(Hash $actualTargetExecutables[$index].FullName)-or[long]$targetRows[$index].size-ne$actualTargetExecutables[$index].Length){throw "Target packaged executable identity mismatch: $actualPath"}
    $actualIdentity=ExtractPackagedIdentity $actualTargetExecutables[$index].FullName;if($actualIdentity.Count-eq0){throw "Target packaged executable omits identity: $actualPath"}
    foreach($property in $targetRows[$index].embedded_identity.PSObject.Properties){if(-not$actualIdentity.Contains($property.Name)-or[string]$actualIdentity[$property.Name]-cne[string]$property.Value-or(ForbiddenIdentity $property.Value)){throw "Target packaged executable embedded identity mismatch: $actualPath/$($property.Name)"}}
}
$detTargetRows=@($determinism.target_packaged_executables|Sort-Object path);if(($detTargetRows|ConvertTo-Json -Depth 20 -Compress)-cne($targetRows|ConvertTo-Json -Depth 20 -Compress)){throw 'Determinism target packaged executable inventory mismatch'}

$detRoles=@($determinism.role_determinism|Sort-Object role);$receiptRoles=@($receipt.roles|Sort-Object role);if($detRoles.Count-ne$receiptRoles.Count){throw 'Determinism role count mismatch'}
for($index=0;$index-lt$receiptRoles.Count;$index++){foreach($field in @('role','generated_source_sha256','normalized_il_sha256','pass_a_sha256','pass_b_sha256','size')){$detValue=[string](FieldValue $detRoles[$index] $field);$receiptValue=[string](FieldValue $receiptRoles[$index] $field);if($detValue-cne$receiptValue){throw "Determinism role mismatch: $($receiptRoles[$index].role)/$field"}};if((@($detRoles[$index].compiler_arguments.pass_a)-join "`n")-cne(@($receiptRoles[$index].compiler_arguments.pass_a)-join "`n")-or(@($detRoles[$index].compiler_arguments.pass_b)-join "`n")-cne(@($receiptRoles[$index].compiler_arguments.pass_b)-join "`n")){throw "Determinism compiler arguments mismatch: $($receiptRoles[$index].role)"}}

$manifestDeclared=@($manifest.files|Sort-Object path);$manifestActual=@(Get-ChildItem -LiteralPath $build -File -Recurse|Where-Object{$_.FullName-ne$manifestPath-and$_.FullName-notlike'*.raw'-and$_.FullName-notlike'*.raw.il'}|ForEach-Object{[ordered]@{path=$_.FullName.Substring($build.Length+1).Replace('\','/');raw_sha256=(Hash $_.FullName);size=$_.Length}})
$manifestActual=@($manifestActual|Sort-Object{[string](FieldValue $_ 'path')})
if($manifestDeclared.Count-ne$manifestActual.Count){throw 'Package manifest file count mismatch'}
for($index=0;$index-lt$manifestActual.Count;$index++){foreach($field in @('path','raw_sha256','size')){$declaredValue=[string](FieldValue $manifestDeclared[$index] $field);$actualValue=[string](FieldValue $manifestActual[$index] $field);if($declaredValue-cne$actualValue){throw "Package manifest mismatch: $($manifestActual[$index].path)/$field"}};if([string]$manifestActual[$index].path-match'(^|/)\.\.(/|$)'){throw 'Package manifest path escape'}}

$negativeRegistry=ReadJson $negativePath;$negativeResults=@(InvokeNegativeCases $receipt $determinism $negativeRegistry);$lifecyclePositiveResults=@(InvokeGitBatchLifecyclePositiveCases $negativeRegistry)

$result=[ordered]@{artifact_type='R7_UNIT2_BUILD_CLOSURE_VERIFICATION';build_manifest_sha256=(Hash $manifestPath);build_receipt_sha256=(Hash $receiptPath);determinism_receipt_sha256=(Hash $determinismPath);generated_source_count=$receipt.generated_sources.Count;lifecycle_fixture_evidence=@($script:gitLifecycleFixtureEvidence);lifecycle_positive_results=$lifecyclePositiveResults;negative_results=$negativeResults;negative_test_count=$negativeResults.Count;role_count=$receipt.roles.Count;schema_version='1.0.0';source_commit=$SourceCommit;source_identity_class=[string]$receipt.source_identity_class;source_tree=[string]$receipt.source_tree;status='PASS'}
if(Test-Path -LiteralPath $output){throw "Verification output exists: $output"};$parent=Split-Path -Parent $output;if(-not(Test-Path -LiteralPath $parent)){New-Item -ItemType Directory -Path $parent|Out-Null};[IO.File]::WriteAllText($output,($result|ConvertTo-Json -Depth 100),[Text.UTF8Encoding]::new($false))
[ordered]@{negative_test_count=$negativeResults.Count;output=$output;raw_sha256=(Hash $output);role_count=$receipt.roles.Count;status='PASS'}|ConvertTo-Json
