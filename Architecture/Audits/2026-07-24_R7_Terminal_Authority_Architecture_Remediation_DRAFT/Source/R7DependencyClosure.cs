using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security;

namespace RandleAI.R7Remediation
{
    internal sealed class R7DependencyIdentity
    {
        internal string Path;
        internal string Sha256;
        internal string OwnerSid;
        internal string SecurityDescriptorSha256;
        internal string VolumeIdentity;
        internal string FileIdentity;
        internal long Size;
        internal uint LinkCount;
    }

    internal sealed class R7DependencyClosure : IDisposable
    {
        private readonly object sync = new object();
        private readonly Dictionary<string, R7DependencyIdentity> allowed = new Dictionary<string, R7DependencyIdentity>(StringComparer.OrdinalIgnoreCase);
        private readonly Dictionary<string, R7VerifiedFile> held = new Dictionary<string, R7VerifiedFile>(StringComparer.OrdinalIgnoreCase);
        private readonly string roleRoot;
        private readonly string executableConfigurationPath;

        internal R7DependencyClosure(string manifestPath, string expectedManifestSha256, string installedRoleRoot)
        {
            roleRoot = Path.GetFullPath(installedRoleRoot).TrimEnd(Path.DirectorySeparatorChar);
            executableConfigurationPath = Path.GetFullPath(Assembly.GetExecutingAssembly().Location) + ".config";
            string fullManifest = Path.GetFullPath(manifestPath);
            using (R7VerifiedFile file = R7SafeFile.Open(fullManifest, fullManifest, Path.GetDirectoryName(fullManifest), expectedManifestSha256, R7Fixed.SystemSid, null, null))
            {
                SortedDictionary<string, object> manifest = RequireObject(R7Json.ParseCanonicalObject(file.Bytes));
                R7Json.ExactKeys(manifest, "artifact_type", "build_host_architecture", "build_tools", "closed_search_policy", "framework_references", "runtime_allowlist", "runtime_configuration", "schema_version");
                if (!String.Equals(R7Json.String(manifest, "artifact_type", 1, 256), "R7_CLOSED_EXECUTABLE_DEPENDENCY_MANIFEST", StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(manifest, "build_host_architecture", 1, 32), "x64", StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(manifest, "schema_version", 1, 32), "1.0.0", StringComparison.Ordinal)) throw new R7ProtocolException("DEPENDENCY_MANIFEST_TYPE");
                ValidateBuildTools(R7Json.Array(manifest, "build_tools"));
                LoadRows(R7Json.Array(manifest, "framework_references"));
                LoadRows(R7Json.Array(manifest, "runtime_allowlist"));
                object[] runtimeConfiguration = R7Json.Array(manifest, "runtime_configuration");
                LoadRows(runtimeConfiguration);
                HoldRows(runtimeConfiguration);
                RequireRuntimeClosure();
                SortedDictionary<string, object> search = R7Json.Child(manifest, "closed_search_policy");
                R7Json.ExactKeys(search, "application_configuration", "current_directory_imports", "environment_imports", "git_runtime", "machine_configuration", "native_dll_search", "python_runtime", "runtime_profiler", "unmanifested_modules", "user_site");
                foreach (string field in new string[] { "application_configuration", "current_directory_imports", "environment_imports", "git_runtime", "python_runtime", "runtime_profiler", "unmanifested_modules", "user_site" }) if (!String.Equals(R7Json.String(search, field, 1, 32), "DENIED", StringComparison.Ordinal)) throw new R7ProtocolException("DEPENDENCY_SEARCH_POLICY_OPEN", field);
                if (!String.Equals(R7Json.String(search, "machine_configuration", 1, 64), "MANIFESTED_AND_HELD", StringComparison.Ordinal) ||
                    !String.Equals(R7Json.String(search, "native_dll_search", 1, 64), "SYSTEM32_ONLY", StringComparison.Ordinal)) throw new R7ProtocolException("DEPENDENCY_SEARCH_POLICY_OPEN");
            }
            VerifyNoNewModules();
        }

        internal void VerifyNoNewModules()
        {
            lock (sync)
            {
                string executable = Path.GetFullPath(Assembly.GetExecutingAssembly().Location);
                R7SafeFile.AssertAbsent(executableConfigurationPath, executableConfigurationPath, roleRoot);
                foreach (ProcessModule module in Process.GetCurrentProcess().Modules) VerifyPath(module.FileName, executable);
                foreach (Assembly assembly in AppDomain.CurrentDomain.GetAssemblies())
                {
                    string location;
                    try { location = assembly.Location; } catch (NotSupportedException) { continue; }
                    if (!String.IsNullOrEmpty(location)) VerifyPath(location, executable);
                }
            }
        }

        internal R7DependencyIdentity ResolveManifestedIdentity(string path)
        {
            string full = Path.GetFullPath(path);
            R7DependencyIdentity value;
            if (!allowed.TryGetValue(full, out value)) throw new R7ProtocolException("DEPENDENCY_IDENTITY_UNRESOLVED", full);
            return value;
        }

        public void Dispose()
        {
            lock (sync)
            {
                foreach (R7VerifiedFile file in held.Values) file.Dispose();
                held.Clear();
            }
        }

        private void VerifyPath(string path, string executable)
        {
            string full = Path.GetFullPath(path);
            if (String.Equals(full, executable, StringComparison.OrdinalIgnoreCase))
            {
                if (!String.Equals(full, executable, StringComparison.Ordinal)) throw new SecurityException("ROLE_EXECUTABLE_CASE_ALIAS");
                if (!full.StartsWith(roleRoot + Path.DirectorySeparatorChar, StringComparison.Ordinal)) throw new SecurityException("ROLE_EXECUTABLE_ROOT_MISMATCH");
                return;
            }
            if (held.ContainsKey(full)) return;
            R7DependencyIdentity expected;
            if (!allowed.TryGetValue(full, out expected)) throw new SecurityException("UNMANIFESTED_RUNTIME_MODULE|" + full);
            if (!String.Equals(full, expected.Path, StringComparison.OrdinalIgnoreCase)) throw new SecurityException("DEPENDENCY_IDENTIFIER_NORMALIZATION_FAILED|" + full);
            R7VerifiedFile verified = R7SafeFile.OpenDependency(expected.Path, expected.Path, Path.GetDirectoryName(expected.Path), expected.Sha256, expected.OwnerSid, expected.SecurityDescriptorSha256, expected.VolumeIdentity, expected.LinkCount);
            if (!String.Equals(verified.Measurement.FileIdentity, expected.FileIdentity, StringComparison.Ordinal) || verified.Measurement.Size != expected.Size) { verified.Dispose(); throw new SecurityException("DEPENDENCY_FILE_IDENTITY_MISMATCH|" + full); }
            held.Add(full, verified);
        }

        private void LoadRows(object[] rows)
        {
            foreach (object raw in rows)
            {
                SortedDictionary<string, object> row = RequireObject(raw);
                R7Json.ExactKeys(row, "file_identity", "hard_link_count", "owner_sid", "path", "security_descriptor_sha256", "sha256", "size", "volume_identity");
                string path = Path.GetFullPath(R7Json.String(row, "path", 3, 4096));
                string hash = R7Json.String(row, "sha256", 64, 64);
                string acl = R7Json.String(row, "security_descriptor_sha256", 64, 64);
                long links = R7Json.Integer(row, "hard_link_count", 1, UInt32.MaxValue);
                if (!R7Hash.IsLowerSha256(hash) || !R7Hash.IsLowerSha256(acl) || allowed.ContainsKey(path)) throw new R7ProtocolException("DEPENDENCY_ROW_INVALID");
                allowed.Add(path, new R7DependencyIdentity
                {
                    FileIdentity = R7Json.String(row, "file_identity", 1, 128),
                    LinkCount = (uint)links,
                    OwnerSid = R7Json.String(row, "owner_sid", 1, 256),
                    Path = path,
                    SecurityDescriptorSha256 = acl,
                    Sha256 = hash,
                    Size = R7Json.Integer(row, "size", 0, Int64.MaxValue),
                    VolumeIdentity = R7Json.String(row, "volume_identity", 8, 64)
                });
            }
        }

        private void HoldRows(object[] rows)
        {
            foreach (object raw in rows)
            {
                SortedDictionary<string, object> row = RequireObject(raw);
                string path = Path.GetFullPath(R7Json.String(row, "path", 3, 4096));
                VerifyPath(path, Path.GetFullPath(Assembly.GetExecutingAssembly().Location));
            }
        }

        private void RequireRuntimeClosure()
        {
            HashSet<string> names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            bool machineConfig = false;
            foreach (R7DependencyIdentity identity in allowed.Values)
            {
                names.Add(Path.GetFileName(identity.Path));
                if (identity.Path.EndsWith(Path.DirectorySeparatorChar + "Config" + Path.DirectorySeparatorChar + "machine.config", StringComparison.OrdinalIgnoreCase)) machineConfig = true;
            }
            foreach (string required in new string[] { "clr.dll", "clrjit.dll", "mscorlib.dll", "System.dll", "System.Core.dll", "System.ServiceProcess.dll" }) if (!names.Contains(required)) throw new R7ProtocolException("REQUIRED_RUNTIME_DEPENDENCY_MISSING", required);
            if (!machineConfig) throw new R7ProtocolException("MACHINE_CONFIGURATION_MISSING");
        }

        private static void ValidateBuildTools(object[] rows)
        {
            HashSet<string> roles = new HashSet<string>(StringComparer.Ordinal);
            foreach (object raw in rows)
            {
                SortedDictionary<string, object> row = RequireObject(raw);
                R7Json.ExactKeys(row, "measurement", "role");
                string role = R7Json.String(row, "role", 1, 256);
                if (!roles.Add(role)) throw new R7ProtocolException("BUILD_TOOL_ROLE_DUPLICATE", role);
                SortedDictionary<string, object> measurement = R7Json.Child(row, "measurement");
                R7Json.ExactKeys(measurement, "file_identity", "hard_link_count", "owner_sid", "path", "security_descriptor_sha256", "sha256", "size", "volume_identity");
                if (!R7Hash.IsLowerSha256(R7Json.String(measurement, "sha256", 64, 64)) || !R7Hash.IsLowerSha256(R7Json.String(measurement, "security_descriptor_sha256", 64, 64)) ||
                    R7Json.Integer(measurement, "hard_link_count", 1, UInt32.MaxValue) < 1 || R7Json.Integer(measurement, "size", 1, Int64.MaxValue) < 1) throw new R7ProtocolException("BUILD_TOOL_MEASUREMENT_INVALID", role);
                Path.GetFullPath(R7Json.String(measurement, "path", 3, 4096));
            }
            foreach (string required in new string[] { "BOOTSTRAP_ARTIFACT_TOOL", "CSC", "GIT_BUILD_TIME_ONLY", "ILDASM", "POWERSHELL_NONAUTHORITATIVE_ORCHESTRATOR", "COMPILER_REFERENCE_mscorlib.dll", "COMPILER_REFERENCE_System.dll", "COMPILER_REFERENCE_System.Core.dll", "COMPILER_REFERENCE_System.Security.dll", "COMPILER_REFERENCE_System.ServiceProcess.dll", "RUNTIME_MACHINE_CONFIG" }) if (!roles.Contains(required)) throw new R7ProtocolException("BUILD_TOOL_ROLE_MISSING", required);
        }

        private static SortedDictionary<string, object> RequireObject(object value)
        {
            SortedDictionary<string, object> result = value as SortedDictionary<string, object>;
            if (result == null) throw new R7ProtocolException("OBJECT_REQUIRED");
            return result;
        }
    }

    internal static class R7RuntimeBoundary
    {
        private const uint LoadLibrarySearchSystem32 = 0x00000800;
        private static readonly object Sync = new object();
        private static bool enforced;

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool SetDefaultDllDirectories(uint directoryFlags);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern bool SetDllDirectoryW(string pathName);

        internal static void Enforce(string governedWorkingRoot)
        {
            Enforce(governedWorkingRoot, R7Fixed.SystemSid);
        }

        internal static void Enforce(string governedWorkingRoot, string expectedOwnerSid)
        {
            lock (Sync)
            {
                if (enforced) return;
                RejectRuntimeEnvironmentInjection();
                if (!SetDefaultDllDirectories(LoadLibrarySearchSystem32)) throw new SecurityException("DEFAULT_DLL_DIRECTORY_CLOSURE_FAILED|" + Marshal.GetLastWin32Error().ToString(System.Globalization.CultureInfo.InvariantCulture));
                if (!SetDllDirectoryW(String.Empty)) throw new SecurityException("CURRENT_DIRECTORY_DLL_SEARCH_REMOVAL_FAILED|" + Marshal.GetLastWin32Error().ToString(System.Globalization.CultureInfo.InvariantCulture));
                string root = Path.GetFullPath(governedWorkingRoot).TrimEnd(Path.DirectorySeparatorChar);
                R7SafeFile.MeasureDirectory(root, root, expectedOwnerSid, null, null);
                Environment.CurrentDirectory = root;
                string executable = Path.GetFullPath(Assembly.GetExecutingAssembly().Location);
                string configuration = executable + ".config";
                R7SafeFile.AssertAbsent(configuration, configuration, root);
                enforced = true;
            }
        }

        internal static void EnforceUninstalledTool()
        {
            lock (Sync)
            {
                if (enforced) return;
                RejectRuntimeEnvironmentInjection();
                if (!SetDefaultDllDirectories(LoadLibrarySearchSystem32)) throw new SecurityException("DEFAULT_DLL_DIRECTORY_CLOSURE_FAILED|" + Marshal.GetLastWin32Error().ToString(System.Globalization.CultureInfo.InvariantCulture));
                if (!SetDllDirectoryW(String.Empty)) throw new SecurityException("CURRENT_DIRECTORY_DLL_SEARCH_REMOVAL_FAILED|" + Marshal.GetLastWin32Error().ToString(System.Globalization.CultureInfo.InvariantCulture));
                string executable = Path.GetFullPath(Assembly.GetExecutingAssembly().Location);
                string root = Path.GetDirectoryName(executable);
                R7SafeFile.MeasureDirectory(root, root, null, null, null);
                R7SafeFile.AssertAbsent(executable + ".config", executable + ".config", root);
                enforced = true;
            }
        }

        private static void RejectRuntimeEnvironmentInjection()
        {
            foreach (System.Collections.DictionaryEntry entry in Environment.GetEnvironmentVariables())
            {
                string name = entry.Key as string;
                if (String.IsNullOrEmpty(name)) continue;
                string upper = name.ToUpperInvariant();
                bool prohibited = upper == "COR_ENABLE_PROFILING" || upper == "COR_PROFILER" || upper == "COR_PROFILER_PATH" ||
                    upper == "COR_PROFILER_PATH_32" || upper == "COR_PROFILER_PATH_64" || upper == "DEVPATH" ||
                    upper == "DOTNET_STARTUP_HOOKS" || upper == "DOTNET_ADDITIONAL_DEPS" || upper == "DOTNET_SHARED_STORE" ||
                    upper == "COREHOST_TRACE" || upper == "COREHOST_TRACEFILE" || upper.StartsWith("COMPLUS_", StringComparison.Ordinal);
                if (prohibited && !String.IsNullOrEmpty(Convert.ToString(entry.Value, System.Globalization.CultureInfo.InvariantCulture))) throw new SecurityException("RUNTIME_ENVIRONMENT_INJECTION_FORBIDDEN|" + name);
            }
        }
    }
}
