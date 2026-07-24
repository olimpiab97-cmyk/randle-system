using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Security.Principal;
using System.Threading.Tasks;

namespace RandleAI.TerminalAuthority
{
    internal static class R7MeasuredSubjectLauncher
    {
        private const string PythonPath = @"C:\Program Files\RandleAI\TerminalAuthority\PythonRuntime\python.exe";
        private const string SubjectPath = @"C:\Program Files\RandleAI\TerminalAuthority\R7ExecutionSubject\external_authority_service_R7_DRAFT.py";
        private const string RepositoryPath = @"C:\ProgramData\RandleAI\TerminalAuthority\Config\R7ExecutionSubjectRepository";
        private const string HistoricalLogPath = @"C:\ProgramData\RandleAI\TerminalAuthority\Config\R6Evidence\18_broad_captured_entry_agent_pytest.log";
        private const string AuthorityCommit = "f0cfbce97e913a133530dd66a70326b1e03a0fb6";
        private const string PythonSha256 = "624bbc0586d8855633b875e911883bbef8a0e8b8711e11126df480dd86f54181";
        private const string SubjectSha256 = "12fcf7209567e565b1314dd7ac0389bbb42da794fc08810ac0fe7d70f407cb57";

        private static int Main(string[] args)
        {
            Process subject = null;
            try
            {
                if (args.Length != 0) throw new InvalidDataException("SUBJECT_LAUNCHER_ARGUMENT_REJECTED");
                if (!String.Equals(CryptoUtil.Sha256File(PythonPath), PythonSha256, StringComparison.Ordinal) ||
                    !String.Equals(CryptoUtil.Sha256File(SubjectPath), SubjectSha256, StringComparison.Ordinal))
                    throw new InvalidDataException("SUBJECT_LAUNCHER_FIXED_BINARY_REJECTED");
                ProcessStartInfo start = new ProcessStartInfo();
                start.FileName = PythonPath;
                start.Arguments = "-I -B " + Quote(SubjectPath) + " --repository " + Quote(RepositoryPath) +
                    " --authority-ref " + AuthorityCommit + " --historical-log " + Quote(HistoricalLogPath);
                start.WorkingDirectory = Path.GetDirectoryName(SubjectPath);
                start.UseShellExecute = false;
                start.CreateNoWindow = true;
                start.RedirectStandardInput = true;
                start.RedirectStandardOutput = true;
                start.RedirectStandardError = true;
                subject = new Process();
                subject.StartInfo = start;
                DateTimeOffset launched = DateTimeOffset.UtcNow;
                if (!subject.Start()) throw new InvalidOperationException("SUBJECT_LAUNCHER_PROCESS_START_FAILED");

                using (WindowsIdentity identity = WindowsIdentity.GetCurrent())
                {
                    WindowsPrincipal principal = new WindowsPrincipal(identity);
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
                    SortedDictionary<string, object> receipt = new SortedDictionary<string, object>(StringComparer.Ordinal);
                    receipt["artifact_type"] = "R7_MEASURED_SUBJECT_LAUNCH";
                    receipt["authentication_type"] = identity.AuthenticationType ?? String.Empty;
                    receipt["group_sids"] = groups.ToArray();
                    receipt["is_administrator"] = principal.IsInRole(WindowsBuiltInRole.Administrator);
                    receipt["launch_time"] = launched.ToString("yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture);
                    receipt["launcher_binary_sha256"] = CryptoUtil.Sha256File(Assembly.GetExecutingAssembly().Location);
                    receipt["launcher_process_id"] = Process.GetCurrentProcess().Id;
                    receipt["python_binary_sha256"] = PythonSha256;
                    receipt["subject_process_id"] = subject.Id;
                    receipt["subject_source_sha256"] = SubjectSha256;
                    receipt["token_inheritance"] = "CREATEPROCESS_DEFAULT_CALLER_TOKEN";
                    receipt["user_sid"] = identity.User == null ? String.Empty : identity.User.Value;
                    Console.Out.WriteLine(CanonicalJson.Serialize(receipt));
                    Console.Out.Flush();
                }
                Task inputProxy = Task.Factory.StartNew(delegate()
                {
                    try
                    {
                        string line;
                        while ((line = Console.In.ReadLine()) != null)
                        {
                            subject.StandardInput.WriteLine(line);
                            subject.StandardInput.Flush();
                        }
                        subject.StandardInput.Close();
                    }
                    catch { }
                }, TaskCreationOptions.LongRunning);
                Task outputProxy = Task.Factory.StartNew(delegate()
                {
                    string line;
                    while ((line = subject.StandardOutput.ReadLine()) != null)
                    {
                        Console.Out.WriteLine(line);
                        Console.Out.Flush();
                    }
                }, TaskCreationOptions.LongRunning);
                Task errorProxy = Task.Factory.StartNew(delegate()
                {
                    string line;
                    while ((line = subject.StandardError.ReadLine()) != null)
                    {
                        Console.Error.WriteLine(line);
                        Console.Error.Flush();
                    }
                }, TaskCreationOptions.LongRunning);
                subject.WaitForExit();
                if (!Task.WaitAll(new Task[] { outputProxy, errorProxy }, 30000))
                    throw new InvalidOperationException("SUBJECT_LAUNCHER_PROXY_DRAIN_TIMEOUT");
                return subject.ExitCode;
            }
            catch (Exception exception)
            {
                Console.Error.WriteLine(exception.GetType().Name + ": " + exception.Message);
                if (subject != null)
                {
                    try { if (!subject.HasExited) subject.Kill(); } catch { }
                }
                return 1;
            }
            finally
            {
                if (subject != null) subject.Dispose();
            }
        }

        private static string Quote(string value)
        {
            if (value.IndexOf('"') >= 0) throw new InvalidDataException("SUBJECT_LAUNCHER_PATH_REJECTED");
            return "\"" + value + "\"";
        }
    }
}
