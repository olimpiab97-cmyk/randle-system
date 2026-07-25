using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Principal;

namespace RandleAI.R7Remediation
{
    internal static class R7ServiceBoundary
    {
        private const uint PolicyLookupNames = 0x00000800;
        private const uint PolicyCreateAccount = 0x00000010;
        private const uint ScManagerConnect = 0x0001;
        private const uint ServiceQueryConfig = 0x0001;
        private const uint ServiceSidTypeRestricted = 3;
        private const int ServiceConfigServiceSidInfo = 5;
        private const int ServiceConfigRequiredPrivilegesInfo = 6;
        private const int ErrorInsufficientBuffer = 122;
        private const int MaxPreferredLength = -1;
        private const int NerrSuccess = 0;

        private static readonly string[] RequiredDenyRights = new string[]
        {
            "SeDenyInteractiveLogonRight",
            "SeDenyRemoteInteractiveLogonRight"
        };

        internal static void ProbeNativeDependencies()
        {
            IntPtr policy = OpenPolicy(PolicyLookupNames);
            LsaClose(policy);
            IntPtr manager = OpenSCManagerW(null, null, ScManagerConnect);
            if (manager == IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error(), "OpenSCManager(probe)");
            CloseServiceHandle(manager);
            if (LocalGroupMemberSids(new SecurityIdentifier(WellKnownSidType.BuiltinAdministratorsSid, null)).Count < 1) throw new InvalidOperationException("ADMINISTRATOR_GROUP_UNEXPECTEDLY_EMPTY");
        }

        internal static SortedDictionary<string, object> EnforceAndMeasure(string serviceName, string expectedSid, string expectedBinary)
        {
            if (String.IsNullOrWhiteSpace(serviceName) || serviceName.IndexOfAny(new char[] { '\0', '\\', '/' }) >= 0) throw new ArgumentException("SERVICE_NAME_INVALID");
            SecurityIdentifier sid = ResolveServiceSid(serviceName, expectedSid);
            ServiceConfiguration configuration = ReadServiceConfiguration(serviceName);
            string normalizedExpectedBinary = NormalizeBinary(expectedBinary);
            if (!String.Equals(configuration.BinaryPath, normalizedExpectedBinary, StringComparison.Ordinal)) throw new InvalidOperationException("SERVICE_BINARY_MISMATCH|" + configuration.BinaryPath);
            string expectedAccount = "NT SERVICE\\" + serviceName;
            if (!String.Equals(configuration.Account, expectedAccount, StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("SERVICE_ACCOUNT_MISMATCH|" + configuration.Account);
            if (configuration.SidType != ServiceSidTypeRestricted) throw new InvalidOperationException("SERVICE_SID_TYPE_NOT_RESTRICTED");
            if (configuration.RequiredPrivileges.Length != 1 || !String.Equals(configuration.RequiredPrivileges[0], "SeChangeNotifyPrivilege", StringComparison.Ordinal)) throw new InvalidOperationException("SERVICE_PRIVILEGE_SET_NOT_MINIMAL|" + String.Join(",", configuration.RequiredPrivileges));

            List<string> administrators = LocalGroupMemberSids(new SecurityIdentifier(WellKnownSidType.BuiltinAdministratorsSid, null));
            if (administrators.Contains(expectedSid)) throw new InvalidOperationException("SERVICE_SID_IS_ADMINISTRATOR");

            List<string> before = EnumerateRights(sid);
            AddRights(sid, RequiredDenyRights);
            List<string> after = EnumerateRights(sid);
            List<object> added = new List<object>();
            foreach (string right in RequiredDenyRights)
            {
                if (!after.Contains(right)) throw new InvalidOperationException("SERVICE_DENY_RIGHT_MISSING|" + right);
                if (!before.Contains(right)) added.Add(right);
            }

            return R7Json.Object(
                "account_rights_after", Objects(after),
                "account_rights_before", Objects(before),
                "added_account_rights", added.ToArray(),
                "administrator_member_sids", Objects(administrators),
                "artifact_type", "R7_OS_ENFORCED_SERVICE_BOUNDARY_MEASUREMENT",
                "binary_path", configuration.BinaryPath,
                "interactive_logon_denied", true,
                "remote_interactive_logon_denied", true,
                "required_privileges", Objects(configuration.RequiredPrivileges),
                "schema_version", "1.0.0",
                "service_account", configuration.Account,
                "service_name", serviceName,
                "service_sid", expectedSid,
                "service_sid_type", "RESTRICTED");
        }

        internal static SortedDictionary<string, object> RestoreAddedRights(byte[] measurementBytes)
        {
            SortedDictionary<string, object> measurement = R7Json.ParseCanonicalObject(measurementBytes);
            R7Json.ExactKeys(measurement, "account_rights_after", "account_rights_before", "added_account_rights", "administrator_member_sids", "artifact_type", "binary_path", "interactive_logon_denied", "remote_interactive_logon_denied", "required_privileges", "schema_version", "service_account", "service_name", "service_sid", "service_sid_type");
            if (!String.Equals(R7Json.String(measurement, "artifact_type", 1, 128), "R7_OS_ENFORCED_SERVICE_BOUNDARY_MEASUREMENT", StringComparison.Ordinal)) throw new InvalidDataException("SERVICE_BOUNDARY_MEASUREMENT_TYPE_INVALID");
            string sidText = R7Json.String(measurement, "service_sid", 1, 256);
            SecurityIdentifier sid = new SecurityIdentifier(sidText);
            object[] addedRaw = R7Json.Array(measurement, "added_account_rights");
            if (addedRaw.Length > 2) throw new InvalidDataException("SERVICE_BOUNDARY_ADDED_RIGHT_COUNT_INVALID");
            List<string> added = new List<string>();
            foreach (object value in addedRaw)
            {
                string right = value as string;
                if (right == null || Array.IndexOf(RequiredDenyRights, right) < 0 || added.Contains(right)) throw new InvalidDataException("SERVICE_BOUNDARY_ADDED_RIGHT_INVALID");
                added.Add(right);
            }
            if (added.Count != 0) RemoveRights(sid, added.ToArray());
            List<string> restored = EnumerateRights(sid);
            foreach (string right in added) if (restored.Contains(right)) throw new InvalidOperationException("SERVICE_RIGHT_RESTORE_FAILED|" + right);
            return R7Json.Object(
                "artifact_type", "R7_SERVICE_BOUNDARY_RIGHTS_RESTORATION",
                "removed_account_rights", Objects(added),
                "restored_account_rights", Objects(restored),
                "schema_version", "1.0.0",
                "service_sid", sidText);
        }

        private static SecurityIdentifier ResolveServiceSid(string serviceName, string expectedSid)
        {
            SecurityIdentifier sid = (SecurityIdentifier)new NTAccount("NT SERVICE", serviceName).Translate(typeof(SecurityIdentifier));
            if (!String.Equals(sid.Value, expectedSid, StringComparison.Ordinal)) throw new InvalidOperationException("SERVICE_SID_MISMATCH|" + sid.Value);
            return sid;
        }

        private static string NormalizeBinary(string binary)
        {
            string value = binary.Trim();
            if (value.Length >= 2 && value[0] == '"' && value[value.Length - 1] == '"') value = value.Substring(1, value.Length - 2);
            return Path.GetFullPath(value);
        }

        private static List<string> EnumerateRights(SecurityIdentifier sid)
        {
            IntPtr policy = OpenPolicy(PolicyLookupNames);
            IntPtr sidMemory = CopySid(sid);
            IntPtr rights = IntPtr.Zero;
            try
            {
                uint count;
                uint status = LsaEnumerateAccountRights(policy, sidMemory, out rights, out count);
                if (status == 0xC0000034 || status == 0xC000003A) return new List<string>();
                ThrowLsa(status, "LsaEnumerateAccountRights");
                List<string> result = new List<string>();
                int size = Marshal.SizeOf(typeof(LsaUnicodeString));
                for (uint index = 0; index < count; index++)
                {
                    LsaUnicodeString value = (LsaUnicodeString)Marshal.PtrToStructure(IntPtr.Add(rights, checked((int)index * size)), typeof(LsaUnicodeString));
                    string text = value.Length == 0 ? String.Empty : Marshal.PtrToStringUni(value.Buffer, value.Length / 2);
                    if (String.IsNullOrEmpty(text) || result.Contains(text)) throw new InvalidOperationException("ACCOUNT_RIGHT_ENUMERATION_INVALID");
                    result.Add(text);
                }
                result.Sort(StringComparer.Ordinal);
                return result;
            }
            finally
            {
                if (rights != IntPtr.Zero) LsaFreeMemory(rights);
                Marshal.FreeHGlobal(sidMemory);
                LsaClose(policy);
            }
        }

        private static void AddRights(SecurityIdentifier sid, string[] rights)
        {
            ChangeRights(sid, rights, true);
        }

        private static void RemoveRights(SecurityIdentifier sid, string[] rights)
        {
            ChangeRights(sid, rights, false);
        }

        private static void ChangeRights(SecurityIdentifier sid, string[] rights, bool add)
        {
            IntPtr policy = OpenPolicy(PolicyLookupNames | PolicyCreateAccount);
            IntPtr sidMemory = CopySid(sid);
            LsaUnicodeString[] values = new LsaUnicodeString[rights.Length];
            try
            {
                for (int index = 0; index < rights.Length; index++) values[index] = AllocateUnicodeString(rights[index]);
                uint status = add ? LsaAddAccountRights(policy, sidMemory, values, (uint)values.Length) : LsaRemoveAccountRights(policy, sidMemory, false, values, (uint)values.Length);
                ThrowLsa(status, add ? "LsaAddAccountRights" : "LsaRemoveAccountRights");
            }
            finally
            {
                foreach (LsaUnicodeString value in values) if (value.Buffer != IntPtr.Zero) Marshal.FreeHGlobal(value.Buffer);
                Marshal.FreeHGlobal(sidMemory);
                LsaClose(policy);
            }
        }

        private static IntPtr OpenPolicy(uint access)
        {
            LsaObjectAttributes attributes = new LsaObjectAttributes();
            attributes.Length = (uint)Marshal.SizeOf(typeof(LsaObjectAttributes));
            IntPtr policy;
            ThrowLsa(LsaOpenPolicy(IntPtr.Zero, ref attributes, access, out policy), "LsaOpenPolicy");
            return policy;
        }

        private static IntPtr CopySid(SecurityIdentifier sid)
        {
            byte[] bytes = new byte[sid.BinaryLength];
            sid.GetBinaryForm(bytes, 0);
            IntPtr memory = Marshal.AllocHGlobal(bytes.Length);
            Marshal.Copy(bytes, 0, memory, bytes.Length);
            return memory;
        }

        private static LsaUnicodeString AllocateUnicodeString(string value)
        {
            LsaUnicodeString result = new LsaUnicodeString();
            result.Buffer = Marshal.StringToHGlobalUni(value);
            result.Length = checked((ushort)(value.Length * 2));
            result.MaximumLength = checked((ushort)((value.Length + 1) * 2));
            return result;
        }

        private static void ThrowLsa(uint status, string operation)
        {
            if (status == 0) return;
            throw new Win32Exception((int)LsaNtStatusToWinError(status), operation);
        }

        private static ServiceConfiguration ReadServiceConfiguration(string serviceName)
        {
            IntPtr manager = OpenSCManagerW(null, null, ScManagerConnect);
            if (manager == IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error(), "OpenSCManager");
            IntPtr service = IntPtr.Zero;
            try
            {
                service = OpenServiceW(manager, serviceName, ServiceQueryConfig);
                if (service == IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error(), "OpenService");
                ServiceConfiguration configuration = ReadQueryServiceConfig(service);
                configuration.SidType = ReadServiceSidType(service);
                string[] privileges = ReadRequiredPrivileges(service);
                Array.Sort(privileges, StringComparer.Ordinal);
                configuration.RequiredPrivileges = privileges;
                return configuration;
            }
            finally
            {
                if (service != IntPtr.Zero) CloseServiceHandle(service);
                CloseServiceHandle(manager);
            }
        }

        private static ServiceConfiguration ReadQueryServiceConfig(IntPtr service)
        {
            uint required;
            QueryServiceConfigW(service, IntPtr.Zero, 0, out required);
            if (Marshal.GetLastWin32Error() != ErrorInsufficientBuffer || required == 0) throw new Win32Exception(Marshal.GetLastWin32Error(), "QueryServiceConfig(size)");
            IntPtr buffer = Marshal.AllocHGlobal(checked((int)required));
            try
            {
                if (!QueryServiceConfigW(service, buffer, required, out required)) throw new Win32Exception(Marshal.GetLastWin32Error(), "QueryServiceConfig");
                QueryServiceConfigNative value = (QueryServiceConfigNative)Marshal.PtrToStructure(buffer, typeof(QueryServiceConfigNative));
                return new ServiceConfiguration
                {
                    Account = Marshal.PtrToStringUni(value.ServiceStartName),
                    BinaryPath = NormalizeBinary(Marshal.PtrToStringUni(value.BinaryPathName))
                };
            }
            finally { Marshal.FreeHGlobal(buffer); }
        }

        private static uint ReadServiceSidType(IntPtr service)
        {
            IntPtr buffer = ReadConfig2Buffer(service, ServiceConfigServiceSidInfo);
            try { return ((ServiceSidInfo)Marshal.PtrToStructure(buffer, typeof(ServiceSidInfo))).ServiceSidType; }
            finally { Marshal.FreeHGlobal(buffer); }
        }

        private static string[] ReadRequiredPrivileges(IntPtr service)
        {
            IntPtr buffer = ReadConfig2Buffer(service, ServiceConfigRequiredPrivilegesInfo);
            try
            {
                ServiceRequiredPrivilegesInfo value = (ServiceRequiredPrivilegesInfo)Marshal.PtrToStructure(buffer, typeof(ServiceRequiredPrivilegesInfo));
                return ReadMultiString(value.RequiredPrivileges);
            }
            finally { Marshal.FreeHGlobal(buffer); }
        }

        private static IntPtr ReadConfig2Buffer(IntPtr service, int level)
        {
            uint required;
            QueryServiceConfig2W(service, level, IntPtr.Zero, 0, out required);
            if (Marshal.GetLastWin32Error() != ErrorInsufficientBuffer || required == 0) throw new Win32Exception(Marshal.GetLastWin32Error(), "QueryServiceConfig2(size)");
            IntPtr buffer = Marshal.AllocHGlobal(checked((int)required));
            try
            {
                if (!QueryServiceConfig2W(service, level, buffer, required, out required)) throw new Win32Exception(Marshal.GetLastWin32Error(), "QueryServiceConfig2");
                return buffer;
            }
            catch { Marshal.FreeHGlobal(buffer); throw; }
        }

        private static string[] ReadMultiString(IntPtr value)
        {
            if (value == IntPtr.Zero) return new string[0];
            List<string> values = new List<string>();
            int offset = 0;
            while (true)
            {
                string current = Marshal.PtrToStringUni(IntPtr.Add(value, offset));
                if (String.IsNullOrEmpty(current)) break;
                if (values.Contains(current)) throw new InvalidOperationException("SERVICE_PRIVILEGE_DUPLICATE");
                values.Add(current);
                offset = checked(offset + ((current.Length + 1) * 2));
            }
            return values.ToArray();
        }

        private static List<string> LocalGroupMemberSids(SecurityIdentifier groupSid)
        {
            string translated = ((NTAccount)groupSid.Translate(typeof(NTAccount))).Value;
            int slash = translated.IndexOf('\\');
            string groupName = slash < 0 ? translated : translated.Substring(slash + 1);
            IntPtr buffer;
            int entriesRead;
            int totalEntries;
            IntPtr resume = IntPtr.Zero;
            int status = NetLocalGroupGetMembers(null, groupName, 0, out buffer, MaxPreferredLength, out entriesRead, out totalEntries, ref resume);
            if (status != NerrSuccess) throw new Win32Exception(status, "NetLocalGroupGetMembers");
            try
            {
                List<string> result = new List<string>();
                int size = Marshal.SizeOf(typeof(LocalGroupMembersInfo0));
                for (int index = 0; index < entriesRead; index++)
                {
                    LocalGroupMembersInfo0 row = (LocalGroupMembersInfo0)Marshal.PtrToStructure(IntPtr.Add(buffer, checked(index * size)), typeof(LocalGroupMembersInfo0));
                    string sid = new SecurityIdentifier(row.Sid).Value;
                    if (!result.Contains(sid)) result.Add(sid);
                }
                if (entriesRead != totalEntries) throw new InvalidOperationException("ADMINISTRATOR_MEMBERSHIP_ENUMERATION_INCOMPLETE");
                result.Sort(StringComparer.Ordinal);
                return result;
            }
            finally { if (buffer != IntPtr.Zero) NetApiBufferFree(buffer); }
        }

        private static object[] Objects(IEnumerable<string> values)
        {
            List<object> result = new List<object>();
            foreach (string value in values) result.Add(value);
            return result.ToArray();
        }

        private sealed class ServiceConfiguration
        {
            internal string Account;
            internal string BinaryPath;
            internal string[] RequiredPrivileges;
            internal uint SidType;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct LsaUnicodeString { internal ushort Length; internal ushort MaximumLength; internal IntPtr Buffer; }

        [StructLayout(LayoutKind.Sequential)]
        private struct LsaObjectAttributes
        {
            internal uint Length;
            internal IntPtr RootDirectory;
            internal IntPtr ObjectName;
            internal uint Attributes;
            internal IntPtr SecurityDescriptor;
            internal IntPtr SecurityQualityOfService;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct QueryServiceConfigNative
        {
            internal uint ServiceType;
            internal uint StartType;
            internal uint ErrorControl;
            internal IntPtr BinaryPathName;
            internal IntPtr LoadOrderGroup;
            internal uint TagId;
            internal IntPtr Dependencies;
            internal IntPtr ServiceStartName;
            internal IntPtr DisplayName;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct ServiceSidInfo { internal uint ServiceSidType; }

        [StructLayout(LayoutKind.Sequential)]
        private struct ServiceRequiredPrivilegesInfo { internal IntPtr RequiredPrivileges; }

        [StructLayout(LayoutKind.Sequential)]
        private struct LocalGroupMembersInfo0 { internal IntPtr Sid; }

        [DllImport("advapi32.dll", CharSet = CharSet.Unicode)]
        private static extern uint LsaOpenPolicy(IntPtr systemName, ref LsaObjectAttributes objectAttributes, uint desiredAccess, out IntPtr policyHandle);
        [DllImport("advapi32.dll")]
        private static extern uint LsaClose(IntPtr policyHandle);
        [DllImport("advapi32.dll")]
        private static extern uint LsaFreeMemory(IntPtr buffer);
        [DllImport("advapi32.dll")]
        private static extern uint LsaNtStatusToWinError(uint status);
        [DllImport("advapi32.dll")]
        private static extern uint LsaAddAccountRights(IntPtr policyHandle, IntPtr accountSid, [In] LsaUnicodeString[] userRights, uint countOfRights);
        [DllImport("advapi32.dll")]
        private static extern uint LsaRemoveAccountRights(IntPtr policyHandle, IntPtr accountSid, [MarshalAs(UnmanagedType.Bool)] bool allRights, [In] LsaUnicodeString[] userRights, uint countOfRights);
        [DllImport("advapi32.dll")]
        private static extern uint LsaEnumerateAccountRights(IntPtr policyHandle, IntPtr accountSid, out IntPtr userRights, out uint countOfRights);

        [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern IntPtr OpenSCManagerW(string machineName, string databaseName, uint desiredAccess);
        [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern IntPtr OpenServiceW(IntPtr scManager, string serviceName, uint desiredAccess);
        [DllImport("advapi32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool CloseServiceHandle(IntPtr serviceHandle);
        [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool QueryServiceConfigW(IntPtr service, IntPtr queryServiceConfig, uint bufferSize, out uint bytesNeeded);
        [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool QueryServiceConfig2W(IntPtr service, int infoLevel, IntPtr buffer, uint bufferSize, out uint bytesNeeded);

        [DllImport("netapi32.dll", CharSet = CharSet.Unicode)]
        private static extern int NetLocalGroupGetMembers(string serverName, string localGroupName, int level, out IntPtr buffer, int preferredMaximumLength, out int entriesRead, out int totalEntries, ref IntPtr resumeHandle);
        [DllImport("netapi32.dll")]
        private static extern int NetApiBufferFree(IntPtr buffer);
    }
}
