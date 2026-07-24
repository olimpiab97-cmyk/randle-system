# Independent source, binary and runtime review

## Candidate source authority

The 50-path candidate delta is exactly 49 added implementation/audit paths plus `.gitattributes`. The candidate properly contains the R6 provisioning source inherited through `bb04ac5`, but its real-execution subject is imported from `f0cfbce97e913a133530dd66a70326b1e03a0fb6`, a discarded sibling of R6. That commit is not an ancestor of, or ref-reachable from, the candidate. Hashing naked Git objects establishes byte identity, not normative authority or guaranteed availability in a clean clone. The installed subject repository is clean at f0/tree `02324c...`, confirming the unauthorized dependency rather than curing it.

## Fresh source rebuild

The review rebuilt all seven roles in a new Temp directory with compiler
`C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe`, SHA-256
`adeda78a951529462f9411e016c1a1b87ddfd94c55912cbd2957817f39929af1`, using the exact committed source. Six installed roles were available for comparison. Their normalized IL matched; raw PE hashes did not:

| Role | Installed SHA-256 | Fresh rebuild SHA-256 | Normalized IL SHA-256 | Raw differing bytes |
|---|---|---|---|---:|
| service | `9ea829416f37c94db2858586fa5e0042652f6caa4637a29fdbefb513577a7526` | `a3a6a5cc43ef3ad2ced27b6fedc7a8f572144720f7e19b8982bc542b291acb9c` | `ca7edf17a15a8798ad36185629201dc30151521f704007e5128bab1a83b58ea5` | 18 |
| worker/comparator | `b2971b85de73d999bfa801d047b22c2ec6fc3d6bc5cb5923ea4a9ab240ed4401` | `7d214fe23e8c04e49a8d044a2756db8b14f93957c48c3619b46a4e2452431aa5` | `aef1589dc610a5903dc259ac97752c7a4c33ee7877c4d97797033b0e7aed5c14` | 17 |
| client | `8d5a5e803c9b7c17f06a488ef815b138d9de1dcd666ab1d4c333414801d4b6e9` | `03bd8142c77c45c5ca9ae93b16686d28c279dc900a698fa23856a79692e019e2` | `116679b5f6deeba3ba743d3a9492fa2cb103a1fdf72fac7ff9cf14b6d8bf2cff` | 18 |
| public verifier | `88c4e631035af0c7ec366256c78f4d1f21994554a30201b30b4d6bf775314a3d` | `7c39be4910f6fb385d92f466162832cb35c76bcca603eea0a2aa18fb6c05847f` | `97076345c0452eb0c3a2483d657b8bd52718d8c425e6e888f5673e6dc493c214` | 17 |
| fixture host | `7a82bab5acfa36555d0e3b9cf29084101f8276b4ceba93cd48cc1e85fadf1454` | `b7d14929073fbef22a7bcc0b8506e9196d573e4b8602753e90d32fcfc2e10822` | `9db65647b46fb70388073eb30d5392ae56340223b0691ee3d4b89460d6b81529` | 18 |
| subject launcher | `3445e5effd6398b648afa6898391f4e2b5de34f696dd91bfedc2dc29be4e3877` | `d3a12ac15808ebd9e962acd0e4baf91190b000affc27ee8bced1f3ea7eddcf79` | `d978f43c296041f932ceadfe5b085ea4497f245377d56ad5199cfad7e1e513ce` | 18 |

Every raw difference was confined to the PE COFF timestamp bytes at offsets 136–137 and the 16-byte module MVID region (one or two MVID bytes happened to coincide in the 17-byte cases). File sizes were identical. This explains the observed legacy-compiler variation but does not solve the dependency and authority problems. The seventh adversarial-probe binary is intentionally not installed and could not be mapped to a running/installed role.

The build script binds the compiler executable but references `System.Core.dll`, `System.Security.dll`, `System.ServiceProcess.dll` and transitive framework assemblies by mutable display name without file hashes. The proof therefore does not bind all compiler/reference inputs.

## Runtime and dependency authority

- The committed 3,209-file Python runtime manifest has SHA-256 `35140cb03dad5984572fbccbb99fbfc20a5496440411c5ad21a690656a7471f2`, root identity `1e545dc3e7a1e63563674d5b0774329ab63d54bf61d44bcce7ea7dc5d26d1bc0`; a full live rehash found zero mismatches.
- The service verifies the full runtime only at initialization. Per governed run it hashes `python.exe` and selected subject files, not all 3,209 files or held immutable handles.
- The f0 Python subject appends `site.getusersitepackages()` after startup. The current service profile has no observed interactive-user injection, but the import graph is not closed by a measured allowlist.
- Source resolution runs `C:\Program Files\Git\cmd\git.exe` version `2.53.0.windows.2`, SHA-256 `37c5725818d602e951ba2563b870d62763322956b73373da4c33a0b566a80bc9`; neither policy nor runtime manifest binds that executable, its DLLs, config or search behavior.
- Process module inspection found the measured service image and Windows/.NET modules, but this snapshot is not a per-use dependency proof.

## Result

Source-to-IL correspondence for six roles is a positive fact. Complete source authority, reproducible binary input closure and per-use runtime dependency closure are not established. The unauthorized f0 dependency and mutable/unmeasured Git/Python/reference surfaces are blocking.
