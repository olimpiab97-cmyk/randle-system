using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;

namespace RandleAI.R7Remediation
{
    internal static class R7ServiceFailureActions
    {
        private const uint ScManagerConnect = 0x0001;
        private const uint ServiceQueryConfig = 0x0001;
        private const uint ServiceChangeConfig = 0x0002;
        private const int ServiceConfigFailureActions = 2;
        private const int ServiceConfigFailureActionsFlag = 4;
        private const int ErrorInsufficientBuffer = 122;
        private const uint ActionNone = 0;
        private const uint ActionRestart = 1;
        private const uint ActionReboot = 2;
        private const uint ActionRunCommand = 3;
        private const int MaximumActions = 64;

        internal static SortedDictionary<string, object> Capture(string serviceName)
        {
            FailureActionState state = Read(serviceName, false);
            return StateRecord("R7_SCM_FAILURE_ACTIONS_SNAPSHOT", serviceName, state);
        }

        internal static SortedDictionary<string, object> ConfigureNone(string serviceName, uint resetPeriodSeconds, byte[] priorSnapshot)
        {
            if (resetPeriodSeconds != 0) throw new ArgumentException("ZERO_ACTION_RESET_PERIOD_MUST_BE_ZERO");
            FailureActionState prior = ParseSnapshot(priorSnapshot, serviceName);
            FailureActionState observedBefore = Read(serviceName, false);
            AssertEqual(prior, observedBefore, "FAILURE_ACTION_PRIOR_STATE_CHANGED");
            FailureActionState target = EmptyTarget(resetPeriodSeconds);
            try
            {
                Write(serviceName, target);
                FailureActionState observedAfter = Read(serviceName, false);
                VerifyNone(observedAfter, resetPeriodSeconds);
                return R7Json.Object(
                    "after", StateRecord("R7_SCM_FAILURE_ACTIONS_STATE", serviceName, observedAfter),
                    "artifact_type", "R7_SCM_FAILURE_ACTIONS_CONFIGURATION",
                    "before", StateRecord("R7_SCM_FAILURE_ACTIONS_STATE", serviceName, observedBefore),
                    "native_actions_pointer_mode", "NON_NULL_SENTINEL_WITH_ZERO_COUNT",
                    "schema_version", "1.0.0",
                    "service_name", serviceName,
                    "status", "PASS");
            }
            catch (Exception failure)
            {
                try
                {
                    Write(serviceName, prior);
                    AssertEqual(prior, Read(serviceName, false), "FAILURE_ACTION_INTERNAL_ROLLBACK_MISMATCH");
                }
                catch (Exception rollbackFailure)
                {
                    throw new InvalidOperationException("FAILURE_ACTION_HELPER_FAILED_CLOSED_ROLLBACK_FAILED|" + failure.Message + "|" + rollbackFailure.Message, rollbackFailure);
                }
                throw new InvalidOperationException("FAILURE_ACTION_HELPER_FAILED_CLOSED_ROLLBACK_COMPLETE|" + failure.Message, failure);
            }
        }

        internal static SortedDictionary<string, object> VerifyNone(string serviceName, uint resetPeriodSeconds)
        {
            FailureActionState observed = Read(serviceName, false);
            VerifyNone(observed, resetPeriodSeconds);
            return R7Json.Object(
                "artifact_type", "R7_SCM_FAILURE_ACTIONS_VERIFICATION",
                "native_query", "QueryServiceConfig2W",
                "schema_version", "1.0.0",
                "service_name", serviceName,
                "state", StateRecord("R7_SCM_FAILURE_ACTIONS_STATE", serviceName, observed),
                "status", "PASS");
        }

        internal static SortedDictionary<string, object> Restore(string serviceName, byte[] priorSnapshot)
        {
            FailureActionState prior = ParseSnapshot(priorSnapshot, serviceName);
            Write(serviceName, prior);
            FailureActionState restored = Read(serviceName, false);
            AssertEqual(prior, restored, "FAILURE_ACTION_ROLLBACK_MISMATCH");
            return R7Json.Object(
                "artifact_type", "R7_SCM_FAILURE_ACTIONS_RESTORATION",
                "restored", StateRecord("R7_SCM_FAILURE_ACTIONS_STATE", serviceName, restored),
                "schema_version", "1.0.0",
                "service_name", serviceName,
                "status", "PASS");
        }

        internal static SortedDictionary<string, object> RunOfflineRegression()
        {
            List<object> cases = new List<object>();
            FailureActionState restart = State(86400, false, null, false, null, false, Entry(ActionRestart, 5000));
            FailureActionState empty = EmptyTarget(0);
            AddCase(cases, "EMPTY_ACTION_SET_REPRESENTED", delegate
            {
                SortedDictionary<string, object> record = StateRecord("R7_SCM_FAILURE_ACTIONS_SNAPSHOT", "FixtureService", empty);
                FailureActionState parsed = ParseSnapshot(R7Json.Encode(record), "FixtureService");
                VerifyNone(parsed, 0);
                if (parsed.Actions.Count != 0) throw new InvalidOperationException("EMPTY_ACTION_COUNT_NOT_ZERO");
            });
            AddCase(cases, "PRIOR_RESTART_5000_CAPTURED", delegate
            {
                FailureActionState parsed = ParseSnapshot(R7Json.Encode(StateRecord("R7_SCM_FAILURE_ACTIONS_SNAPSHOT", "FixtureService", restart)), "FixtureService");
                AssertEqual(restart, parsed, "RESTART_5000_CAPTURE_MISMATCH");
            });
            AddCase(cases, "TARGET_CONTAINS_ZERO_ACTIONS", delegate { VerifyNone(empty, 0); });
            AddCase(cases, "NONZERO_ACTION_READBACK_REJECTED", delegate { ExpectRejected(delegate { VerifyNone(State(0, false, null, false, null, false, Entry(ActionNone, 0)), 0); }, "FAILURE_ACTION_NONZERO_COUNT"); });
            AddCase(cases, "RESTART_READBACK_REJECTED", delegate { ExpectRejected(delegate { VerifyNone(State(0, false, null, false, null, false, Entry(ActionRestart, 5000)), 0); }, "FAILURE_ACTION_RESTART_PRESENT"); });
            AddCase(cases, "RUN_COMMAND_READBACK_REJECTED", delegate { ExpectRejected(delegate { VerifyNone(State(0, false, null, false, null, false, Entry(ActionRunCommand, 0)), 0); }, "FAILURE_ACTION_RUN_COMMAND_PRESENT"); });
            AddCase(cases, "REBOOT_READBACK_REJECTED", delegate { ExpectRejected(delegate { VerifyNone(State(0, false, null, false, null, false, Entry(ActionReboot, 0)), 0); }, "FAILURE_ACTION_REBOOT_PRESENT"); });
            AddCase(cases, "ROLLBACK_RECONSTRUCTS_RESTART_5000", delegate
            {
                FailureActionState restored = Clone(restart);
                AssertEqual(restart, restored, "ROLLBACK_RECONSTRUCTION_MISMATCH");
            });
            AddCase(cases, "EMPTY_ARGUMENT_OMISSION_DETECTED", delegate { ExpectRejected(delegate { ValidateLegacyArguments(new string[] { "failure", "FixtureService", "reset=", "0", "actions=" }); }, "EMPTY_ACTION_ARGUMENT_OMITTED"); });
            AddCase(cases, "LITERAL_QUOTE_CORRUPTION_DETECTED", delegate { ExpectRejected(delegate { ValidateLegacyArguments(new string[] { "failure", "FixtureService", "reset=", "0", "actions=", "\"\"" }); }, "EMPTY_ACTION_ARGUMENT_LITERAL_QUOTES"); });
            AddCase(cases, "EXTRA_ACTION_DETECTED", delegate { ExpectRejected(delegate { VerifyNone(State(0, false, null, false, null, false, Entry(99, 1)), 0); }, "FAILURE_ACTION_EXTRA_PRESENT"); });
            AddCase(cases, "HELPER_FAILURE_FAILS_CLOSED", delegate
            {
                FailureActionState current = Clone(restart);
                try { current = Clone(empty); throw new InvalidOperationException("SIMULATED_NATIVE_HELPER_FAILURE"); }
                catch { current = Clone(restart); }
                AssertEqual(restart, current, "FAIL_CLOSED_RESTORE_MISMATCH");
            });
            foreach (object item in cases)
            {
                SortedDictionary<string, object> row = (SortedDictionary<string, object>)item;
                if (!String.Equals((string)row["status"], "PASS", StringComparison.Ordinal)) throw new InvalidOperationException("FAILURE_ACTION_REGRESSION_FAILED|" + (string)row["case"] + "|" + (string)row["error"]);
            }
            return R7Json.Object(
                "artifact_type", "R7_SCM_FAILURE_ACTIONS_OFFLINE_REGRESSION",
                "case_count", (long)cases.Count,
                "cases", cases.ToArray(),
                "native_api_invoked", false,
                "schema_version", "1.0.0",
                "status", "PASS");
        }

        private static void AddCase(List<object> cases, string name, Action test)
        {
            try { test(); cases.Add(R7Json.Object("case", name, "error", "", "status", "PASS")); }
            catch (Exception exception) { cases.Add(R7Json.Object("case", name, "error", exception.GetType().FullName + "|" + exception.Message, "status", "FAIL")); }
        }

        private static void ExpectRejected(Action action, string token)
        {
            try { action(); }
            catch (Exception exception)
            {
                if (exception.Message.IndexOf(token, StringComparison.Ordinal) >= 0) return;
                throw new InvalidOperationException("UNEXPECTED_REJECTION|" + exception.Message);
            }
            throw new InvalidOperationException("EXPECTED_REJECTION_MISSING|" + token);
        }

        private static void ValidateLegacyArguments(string[] arguments)
        {
            if (arguments.Length != 6) throw new InvalidDataException("EMPTY_ACTION_ARGUMENT_OMITTED");
            if (String.Equals(arguments[5], "\"\"", StringComparison.Ordinal) || String.Equals(arguments[5], "''", StringComparison.Ordinal)) throw new InvalidDataException("EMPTY_ACTION_ARGUMENT_LITERAL_QUOTES");
            throw new InvalidDataException("AMBIGUOUS_SHELL_FAILURE_ACTIONS_FORBIDDEN");
        }

        private static FailureActionState EmptyTarget(uint resetPeriodSeconds)
        {
            return State(resetPeriodSeconds, true, String.Empty, true, String.Empty, false);
        }

        private static FailureActionState State(uint reset, bool rebootPresent, string reboot, bool commandPresent, string command, bool nonCrash, params FailureActionEntry[] actions)
        {
            FailureActionState state = new FailureActionState();
            state.ResetPeriodSeconds = reset;
            state.RebootMessagePresent = rebootPresent;
            state.RebootMessage = reboot ?? String.Empty;
            state.CommandPresent = commandPresent;
            state.Command = command ?? String.Empty;
            state.FailureActionsOnNonCrash = nonCrash;
            state.Actions = new List<FailureActionEntry>(actions);
            return state;
        }

        private static FailureActionEntry Entry(uint type, uint delay)
        {
            FailureActionEntry entry = new FailureActionEntry();
            entry.Type = type;
            entry.DelayMilliseconds = delay;
            return entry;
        }

        private static FailureActionState Clone(FailureActionState state)
        {
            List<FailureActionEntry> actions = new List<FailureActionEntry>();
            foreach (FailureActionEntry entry in state.Actions) actions.Add(Entry(entry.Type, entry.DelayMilliseconds));
            return State(state.ResetPeriodSeconds, state.RebootMessagePresent, state.RebootMessage, state.CommandPresent, state.Command, state.FailureActionsOnNonCrash, actions.ToArray());
        }

        private static void VerifyNone(FailureActionState state, uint expectedReset)
        {
            if (state.Actions.Count != 0)
            {
                foreach (FailureActionEntry action in state.Actions)
                {
                    if (action.Type == ActionRestart) throw new InvalidOperationException("FAILURE_ACTION_RESTART_PRESENT");
                    if (action.Type == ActionRunCommand) throw new InvalidOperationException("FAILURE_ACTION_RUN_COMMAND_PRESENT");
                    if (action.Type == ActionReboot) throw new InvalidOperationException("FAILURE_ACTION_REBOOT_PRESENT");
                    if (action.Type != ActionNone) throw new InvalidOperationException("FAILURE_ACTION_EXTRA_PRESENT");
                }
                throw new InvalidOperationException("FAILURE_ACTION_NONZERO_COUNT");
            }
            if (state.ResetPeriodSeconds != expectedReset) throw new InvalidOperationException("FAILURE_ACTION_RESET_PERIOD_MISMATCH");
            if (state.CommandPresent && state.Command.Length != 0) throw new InvalidOperationException("FAILURE_ACTION_COMMAND_REMAINS");
            if (state.RebootMessagePresent && state.RebootMessage.Length != 0) throw new InvalidOperationException("FAILURE_ACTION_REBOOT_MESSAGE_REMAINS");
            if (state.FailureActionsOnNonCrash) throw new InvalidOperationException("FAILURE_ACTION_NONCRASH_FLAG_ENABLED");
        }

        private static void AssertEqual(FailureActionState expected, FailureActionState actual, string token)
        {
            if (expected.ResetPeriodSeconds != actual.ResetPeriodSeconds || expected.RebootMessagePresent != actual.RebootMessagePresent || expected.CommandPresent != actual.CommandPresent || expected.FailureActionsOnNonCrash != actual.FailureActionsOnNonCrash || !String.Equals(expected.RebootMessage, actual.RebootMessage, StringComparison.Ordinal) || !String.Equals(expected.Command, actual.Command, StringComparison.Ordinal) || expected.Actions.Count != actual.Actions.Count) throw new InvalidOperationException(token);
            for (int index = 0; index < expected.Actions.Count; index++) if (expected.Actions[index].Type != actual.Actions[index].Type || expected.Actions[index].DelayMilliseconds != actual.Actions[index].DelayMilliseconds) throw new InvalidOperationException(token);
        }

        private static SortedDictionary<string, object> StateRecord(string artifactType, string serviceName, FailureActionState state)
        {
            List<object> actions = new List<object>();
            foreach (FailureActionEntry entry in state.Actions) actions.Add(R7Json.Object("delay_ms", (long)entry.DelayMilliseconds, "type", ActionName(entry.Type), "type_code", (long)entry.Type));
            return R7Json.Object(
                "action_count", (long)state.Actions.Count,
                "actions", actions.ToArray(),
                "artifact_type", artifactType,
                "command", state.Command,
                "command_present", state.CommandPresent,
                "failure_actions_on_noncrash", state.FailureActionsOnNonCrash,
                "reboot_message", state.RebootMessage,
                "reboot_message_present", state.RebootMessagePresent,
                "reset_period_seconds", (long)state.ResetPeriodSeconds,
                "schema_version", "1.0.0",
                "service_name", serviceName);
        }

        private static string ActionName(uint type)
        {
            if (type == ActionNone) return "NONE";
            if (type == ActionRestart) return "RESTART";
            if (type == ActionReboot) return "REBOOT";
            if (type == ActionRunCommand) return "RUN_COMMAND";
            return "UNKNOWN_" + type.ToString(System.Globalization.CultureInfo.InvariantCulture);
        }

        private static FailureActionState ParseSnapshot(byte[] bytes, string expectedServiceName)
        {
            SortedDictionary<string, object> root = R7Json.ParseCanonicalObject(bytes);
            R7Json.ExactKeys(root, "action_count", "actions", "artifact_type", "command", "command_present", "failure_actions_on_noncrash", "reboot_message", "reboot_message_present", "reset_period_seconds", "schema_version", "service_name");
            if (!String.Equals(R7Json.String(root, "artifact_type", 1, 128), "R7_SCM_FAILURE_ACTIONS_SNAPSHOT", StringComparison.Ordinal)) throw new InvalidDataException("FAILURE_ACTION_SNAPSHOT_TYPE_INVALID");
            if (!String.Equals(R7Json.String(root, "schema_version", 1, 32), "1.0.0", StringComparison.Ordinal)) throw new InvalidDataException("FAILURE_ACTION_SNAPSHOT_VERSION_INVALID");
            if (!String.Equals(R7Json.String(root, "service_name", 1, 256), expectedServiceName, StringComparison.Ordinal)) throw new InvalidDataException("FAILURE_ACTION_SNAPSHOT_SERVICE_MISMATCH");
            object[] rawActions = R7Json.Array(root, "actions");
            long count = R7Json.Integer(root, "action_count", 0, MaximumActions);
            if (count != rawActions.Length) throw new InvalidDataException("FAILURE_ACTION_SNAPSHOT_COUNT_MISMATCH");
            List<FailureActionEntry> actions = new List<FailureActionEntry>();
            foreach (object raw in rawActions)
            {
                SortedDictionary<string, object> row = raw as SortedDictionary<string, object>;
                if (row == null) throw new InvalidDataException("FAILURE_ACTION_SNAPSHOT_ROW_INVALID");
                R7Json.ExactKeys(row, "delay_ms", "type", "type_code");
                uint type = checked((uint)R7Json.Integer(row, "type_code", 0, UInt32.MaxValue));
                uint delay = checked((uint)R7Json.Integer(row, "delay_ms", 0, UInt32.MaxValue));
                if (!String.Equals(R7Json.String(row, "type", 1, 64), ActionName(type), StringComparison.Ordinal)) throw new InvalidDataException("FAILURE_ACTION_SNAPSHOT_TYPE_NAME_MISMATCH");
                actions.Add(Entry(type, delay));
            }
            bool rebootPresent = R7Json.Boolean(root, "reboot_message_present");
            bool commandPresent = R7Json.Boolean(root, "command_present");
            string reboot = R7Json.String(root, "reboot_message", 0, 32767);
            string command = R7Json.String(root, "command", 0, 32767);
            if (!rebootPresent && reboot.Length != 0) throw new InvalidDataException("FAILURE_ACTION_REBOOT_POINTER_VALUE_MISMATCH");
            if (!commandPresent && command.Length != 0) throw new InvalidDataException("FAILURE_ACTION_COMMAND_POINTER_VALUE_MISMATCH");
            return State(checked((uint)R7Json.Integer(root, "reset_period_seconds", 0, UInt32.MaxValue)), rebootPresent, reboot, commandPresent, command, R7Json.Boolean(root, "failure_actions_on_noncrash"), actions.ToArray());
        }

        private static FailureActionState Read(string serviceName, bool changeAccess)
        {
            ValidateServiceName(serviceName);
            IntPtr manager = OpenSCManagerW(null, null, ScManagerConnect);
            if (manager == IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error(), "OpenSCManagerW");
            IntPtr service = IntPtr.Zero;
            try
            {
                service = OpenServiceW(manager, serviceName, ServiceQueryConfig | (changeAccess ? ServiceChangeConfig : 0));
                if (service == IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error(), "OpenServiceW");
                return Read(service);
            }
            finally
            {
                if (service != IntPtr.Zero) CloseServiceHandle(service);
                CloseServiceHandle(manager);
            }
        }

        private static FailureActionState Read(IntPtr service)
        {
            IntPtr actionsBuffer = ReadConfig2Buffer(service, ServiceConfigFailureActions);
            FailureActionState state = new FailureActionState();
            try
            {
                ServiceFailureActionsNative native = (ServiceFailureActionsNative)Marshal.PtrToStructure(actionsBuffer, typeof(ServiceFailureActionsNative));
                if (native.ActionsCount > MaximumActions) throw new InvalidOperationException("FAILURE_ACTION_COUNT_EXCEEDS_BOUND");
                if (native.ActionsCount != 0 && native.Actions == IntPtr.Zero) throw new InvalidOperationException("FAILURE_ACTION_ARRAY_POINTER_NULL");
                state.ResetPeriodSeconds = native.ResetPeriod;
                state.RebootMessagePresent = native.RebootMessage != IntPtr.Zero;
                state.RebootMessage = state.RebootMessagePresent ? Marshal.PtrToStringUni(native.RebootMessage) : String.Empty;
                state.CommandPresent = native.Command != IntPtr.Zero;
                state.Command = state.CommandPresent ? Marshal.PtrToStringUni(native.Command) : String.Empty;
                state.Actions = new List<FailureActionEntry>();
                int actionSize = Marshal.SizeOf(typeof(ScActionNative));
                for (uint index = 0; index < native.ActionsCount; index++)
                {
                    ScActionNative action = (ScActionNative)Marshal.PtrToStructure(IntPtr.Add(native.Actions, checked((int)index * actionSize)), typeof(ScActionNative));
                    state.Actions.Add(Entry(action.Type, action.Delay));
                }
            }
            finally { Marshal.FreeHGlobal(actionsBuffer); }
            IntPtr flagBuffer = ReadConfig2Buffer(service, ServiceConfigFailureActionsFlag);
            try { state.FailureActionsOnNonCrash = ((ServiceFailureActionsFlagNative)Marshal.PtrToStructure(flagBuffer, typeof(ServiceFailureActionsFlagNative))).FailureActionsOnNonCrash; }
            finally { Marshal.FreeHGlobal(flagBuffer); }
            return state;
        }

        private static void Write(string serviceName, FailureActionState state)
        {
            ValidateServiceName(serviceName);
            IntPtr manager = OpenSCManagerW(null, null, ScManagerConnect);
            if (manager == IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error(), "OpenSCManagerW");
            IntPtr service = IntPtr.Zero;
            try
            {
                service = OpenServiceW(manager, serviceName, ServiceQueryConfig | ServiceChangeConfig);
                if (service == IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error(), "OpenServiceW");
                WriteStrings(service, state);
                WriteActions(service, state);
                WriteNonCrashFlag(service, state.FailureActionsOnNonCrash);
            }
            finally
            {
                if (service != IntPtr.Zero) CloseServiceHandle(service);
                CloseServiceHandle(manager);
            }
        }

        private static void WriteStrings(IntPtr service, FailureActionState state)
        {
            IntPtr reboot = IntPtr.Zero;
            IntPtr command = IntPtr.Zero;
            try
            {
                if (state.RebootMessagePresent) reboot = Marshal.StringToHGlobalUni(state.RebootMessage);
                if (state.CommandPresent) command = Marshal.StringToHGlobalUni(state.Command);
                ServiceFailureActionsNative value = new ServiceFailureActionsNative();
                value.RebootMessage = reboot;
                value.Command = command;
                Change(service, ServiceConfigFailureActions, value);
            }
            finally
            {
                if (command != IntPtr.Zero) Marshal.FreeHGlobal(command);
                if (reboot != IntPtr.Zero) Marshal.FreeHGlobal(reboot);
            }
        }

        private static void WriteActions(IntPtr service, FailureActionState state)
        {
            IntPtr actions = IntPtr.Zero;
            try
            {
                int actionSize = Marshal.SizeOf(typeof(ScActionNative));
                if (state.Actions.Count == 0) actions = Marshal.AllocHGlobal(1);
                else
                {
                    actions = Marshal.AllocHGlobal(checked(actionSize * state.Actions.Count));
                    for (int index = 0; index < state.Actions.Count; index++)
                    {
                        ScActionNative nativeAction = new ScActionNative();
                        nativeAction.Type = state.Actions[index].Type;
                        nativeAction.Delay = state.Actions[index].DelayMilliseconds;
                        Marshal.StructureToPtr(nativeAction, IntPtr.Add(actions, checked(index * actionSize)), false);
                    }
                }
                ServiceFailureActionsNative value = new ServiceFailureActionsNative();
                value.ResetPeriod = state.ResetPeriodSeconds;
                value.ActionsCount = checked((uint)state.Actions.Count);
                value.Actions = actions;
                Change(service, ServiceConfigFailureActions, value);
            }
            finally { if (actions != IntPtr.Zero) Marshal.FreeHGlobal(actions); }
        }

        private static void WriteNonCrashFlag(IntPtr service, bool enabled)
        {
            ServiceFailureActionsFlagNative flag = new ServiceFailureActionsFlagNative();
            flag.FailureActionsOnNonCrash = enabled;
            Change(service, ServiceConfigFailureActionsFlag, flag);
        }

        private static void Change<T>(IntPtr service, int level, T value) where T : struct
        {
            IntPtr buffer = Marshal.AllocHGlobal(Marshal.SizeOf(typeof(T)));
            try
            {
                Marshal.StructureToPtr(value, buffer, false);
                if (!ChangeServiceConfig2W(service, level, buffer)) throw new Win32Exception(Marshal.GetLastWin32Error(), "ChangeServiceConfig2W(" + level.ToString(System.Globalization.CultureInfo.InvariantCulture) + ")");
            }
            finally { Marshal.FreeHGlobal(buffer); }
        }

        private static IntPtr ReadConfig2Buffer(IntPtr service, int level)
        {
            uint required;
            QueryServiceConfig2W(service, level, IntPtr.Zero, 0, out required);
            if (Marshal.GetLastWin32Error() != ErrorInsufficientBuffer || required == 0) throw new Win32Exception(Marshal.GetLastWin32Error(), "QueryServiceConfig2W(size," + level.ToString(System.Globalization.CultureInfo.InvariantCulture) + ")");
            IntPtr buffer = Marshal.AllocHGlobal(checked((int)required));
            try
            {
                if (!QueryServiceConfig2W(service, level, buffer, required, out required)) throw new Win32Exception(Marshal.GetLastWin32Error(), "QueryServiceConfig2W(" + level.ToString(System.Globalization.CultureInfo.InvariantCulture) + ")");
                return buffer;
            }
            catch { Marshal.FreeHGlobal(buffer); throw; }
        }

        private static void ValidateServiceName(string serviceName)
        {
            if (String.IsNullOrWhiteSpace(serviceName) || serviceName.Length > 256 || serviceName.IndexOfAny(new char[] { '\0', '\\', '/' }) >= 0) throw new ArgumentException("SERVICE_NAME_INVALID");
        }

        private sealed class FailureActionState
        {
            internal uint ResetPeriodSeconds;
            internal bool RebootMessagePresent;
            internal string RebootMessage;
            internal bool CommandPresent;
            internal string Command;
            internal bool FailureActionsOnNonCrash;
            internal List<FailureActionEntry> Actions;
        }

        private sealed class FailureActionEntry
        {
            internal uint Type;
            internal uint DelayMilliseconds;
        }

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        private struct ServiceFailureActionsNative
        {
            internal uint ResetPeriod;
            internal IntPtr RebootMessage;
            internal IntPtr Command;
            internal uint ActionsCount;
            internal IntPtr Actions;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct ScActionNative { internal uint Type; internal uint Delay; }

        [StructLayout(LayoutKind.Sequential)]
        private struct ServiceFailureActionsFlagNative
        {
            [MarshalAs(UnmanagedType.Bool)] internal bool FailureActionsOnNonCrash;
        }

        [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern IntPtr OpenSCManagerW(string machineName, string databaseName, uint desiredAccess);
        [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern IntPtr OpenServiceW(IntPtr scManager, string serviceName, uint desiredAccess);
        [DllImport("advapi32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool CloseServiceHandle(IntPtr serviceHandle);
        [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool QueryServiceConfig2W(IntPtr service, int infoLevel, IntPtr buffer, uint bufferSize, out uint bytesNeeded);
        [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool ChangeServiceConfig2W(IntPtr service, int infoLevel, IntPtr info);
    }
}
