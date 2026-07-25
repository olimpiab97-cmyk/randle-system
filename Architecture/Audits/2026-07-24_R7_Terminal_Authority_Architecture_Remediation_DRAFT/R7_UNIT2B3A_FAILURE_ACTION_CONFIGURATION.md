# R7 Unit 2B-3A failure-action configuration

The stopped-boundary installer configures `RandleTerminalUpgradeAuthority` failure actions through the measured `R7ArtifactTool`; it does not marshal an empty `sc.exe failure` argument through PowerShell.

Before changing failure actions, the installer uses `QueryServiceConfig2W` at `SERVICE_CONFIG_FAILURE_ACTIONS` and `SERVICE_CONFIG_FAILURE_ACTIONS_FLAG` to capture the reset period, reboot-message and command pointer/value state, ordered `SC_ACTION` array, and non-crash flag. The canonical snapshot is the sole rollback input.

The target is explicit: reset period `0`, action count `0`, no restart, run-command, or reboot action, and `fFailureActionsOnNonCrashFailures = FALSE`. Win32 deletion semantics require `cActions = 0` with a non-null `lpsaActions` sentinel; the helper records that representation as `NON_NULL_SENTINEL_WITH_ZERO_COUNT`. Empty reboot-message and command values are independently applied before deleting the action array.

After `ChangeServiceConfig2W`, a separate `QueryServiceConfig2W` read-back must match the target native structure. Any mutation or verification failure causes the helper to restore and verify the captured state before returning failure. The installer also retains the snapshot and reconstructs it during its outer rollback path, including a prior `RESTART/5000` action and the captured non-crash flag.

Every helper invocation is bounded by stopped-service assertions. The offline regression command uses only in-memory native-structure fixtures and reports `native_api_invoked = false`. Unit 2B-3A does not invoke the installer or any live SCM mutation.
