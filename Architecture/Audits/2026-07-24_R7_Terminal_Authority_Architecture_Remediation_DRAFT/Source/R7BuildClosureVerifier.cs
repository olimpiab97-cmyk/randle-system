using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Security.Cryptography;
using System.Text;

namespace RandleAI.R7Remediation
{
    internal static class R7BuildClosureVerifier
    {
        internal static string VerifyUpgradeAuthorityBuildReceipt(string expectedBinarySha256, string expectedPolicySha256, string expectedDependencyManifestSha256, string expectedUpgradeClientSha256, string expectedInstallerScriptSha256, string expectedSourceCommit, string expectedSourceTree, string expectedVolumeIdentity)
        {
            SortedDictionary<string, object> receipt;
            string identity;
            using (R7VerifiedFile file = R7SafeFile.Open(R7Fixed.UpgradeBuildReceiptPath, R7Fixed.UpgradeBuildReceiptPath, R7Fixed.UpgradeConfigRoot, null, R7Fixed.SystemSid, null, expectedVolumeIdentity))
            {
                identity = file.Measurement.Sha256;
                receipt = R7Json.ParseCanonicalObject(file.Bytes);
            }
            R7Json.ExactKeys(receipt, "artifact_type", "binary", "compiler_options", "dependency_manifest_sha256", "final_build_input_closures", "generated_identity_sha256", "governed_scripts", "schema_version", "source_commit", "source_files", "source_tree", "toolchain", "upgrade_policy_sha256");
            if (R7Json.String(receipt, "artifact_type", 1, 256) != "R7_UPGRADE_AUTHORITY_SOURCE_TO_BINARY_BUILD_RECEIPT" ||
                R7Json.String(receipt, "schema_version", 1, 64) != "1.0.0" ||
                R7Json.String(receipt, "source_commit", 40, 40) != expectedSourceCommit ||
                R7Json.String(receipt, "source_tree", 40, 40) != expectedSourceTree ||
                R7Json.String(receipt, "dependency_manifest_sha256", 64, 64) != expectedDependencyManifestSha256 ||
                R7Json.String(receipt, "upgrade_policy_sha256", 64, 64) != expectedPolicySha256 ||
                !R7Hash.IsLowerSha256(R7Json.String(receipt, "generated_identity_sha256", 64, 64))) throw new InvalidDataException("UPGRADE_BUILD_RECEIPT_BINDING_INVALID");
            VerifyCompilerOptions(R7Json.Array(receipt, "compiler_options"));
            VerifyBinaryReceipt(RequireObject(receipt["binary"]), "UPGRADE_AUTHORITY", "RandleTerminalUpgradeAuthority.exe", expectedBinarySha256);
            HashSet<string> sourceInputPaths = new HashSet<string>(StringComparer.Ordinal);
            string generatedIdentity = VerifySourceFiles(R7Json.Array(receipt, "source_files"), expectedSourceCommit, "GENERATED/R7UpgradeBuildIdentity.g.cs", R7Fixed.UpgradeSourceInputRoot, expectedVolumeIdentity, sourceInputPaths);
            if (generatedIdentity != R7Json.String(receipt, "generated_identity_sha256", 64, 64)) throw new InvalidDataException("UPGRADE_GENERATED_IDENTITY_SOURCE_MISMATCH");
            VerifyGovernedScripts(R7Json.Array(receipt, "governed_scripts"), expectedInstallerScriptSha256, R7Fixed.UpgradeSourceInputRoot, expectedVolumeIdentity, sourceInputPaths);
            VerifyExactFileInventory(R7Fixed.UpgradeSourceInputRoot, sourceInputPaths, "UPGRADE_SOURCE_INPUT");
            HashSet<string> closurePaths = new HashSet<string>(StringComparer.Ordinal);
            VerifyUpgradeBuildInputClosures(R7Json.Array(receipt, "final_build_input_closures"), expectedVolumeIdentity, closurePaths);
            VerifyExactFileInventory(R7Fixed.UpgradeBuildClosureRoot, closurePaths, "UPGRADE_BUILD_CLOSURE");
            VerifyToolchain(R7Json.Array(receipt, "toolchain"));
            VerifyUpgradeImmutableInventory(identity, expectedBinarySha256, expectedPolicySha256, expectedDependencyManifestSha256, expectedUpgradeClientSha256, expectedVolumeIdentity, sourceInputPaths, closurePaths);
            return identity;
        }

        internal static SortedDictionary<string, object> VerifyTerminalBuildAndInstalledInventory(R7TerminalPolicy terminalPolicy, R7UpgradeVersionBinding activeVersion, string upgradeClientSha256, string installerScriptSha256, string expectedVolumeIdentity)
        {
            if (activeVersion == null || activeVersion.AuthorizationIdentity == null) throw new InvalidDataException("ACTIVE_BUILD_VERSION_MISSING");
            SortedDictionary<string, object> dependencyManifest;
            using (R7VerifiedFile file = R7SafeFile.Open(R7Fixed.DependencyManifestPath, R7Fixed.DependencyManifestPath, R7Fixed.RemediationConfigRoot, terminalPolicy.DependencyManifestSha256, R7Fixed.SystemSid, null, expectedVolumeIdentity)) dependencyManifest = R7Json.ParseCanonicalObject(file.Bytes);
            ValidateDependencyManifest(dependencyManifest);

            SortedDictionary<string, object> buildReceipt;
            using (R7VerifiedFile file = R7SafeFile.Open(R7Fixed.BuildReceiptPath, R7Fixed.BuildReceiptPath, R7Fixed.RemediationBuildRoot, terminalPolicy.BuildReceiptSha256, R7Fixed.SystemSid, null, expectedVolumeIdentity)) buildReceipt = R7Json.ParseCanonicalObject(file.Bytes);
            R7Json.ExactKeys(buildReceipt, "architecture", "artifact_type", "binaries", "bootstrap_artifact_tool_sha256", "build_input_closures", "compiler_options", "dependency_manifest_sha256", "framework_reference_paths", "governed_git", "governed_scripts", "key_file_metadata", "schema_version", "source_commit", "source_files", "source_tree", "toolchain");
            if (R7Json.String(buildReceipt, "artifact_type", 1, 256) != "R7_SOURCE_TO_BINARY_BUILD_RECEIPT" ||
                R7Json.String(buildReceipt, "architecture", 1, 32) != "x64" || R7Json.String(buildReceipt, "schema_version", 1, 64) != "1.0.0" ||
                R7Json.String(buildReceipt, "source_commit", 40, 40) != activeVersion.SourceCommit || R7Json.String(buildReceipt, "source_tree", 40, 40) != activeVersion.SourceTree ||
                R7Json.String(buildReceipt, "dependency_manifest_sha256", 64, 64) != terminalPolicy.DependencyManifestSha256) throw new InvalidDataException("TERMINAL_BUILD_RECEIPT_BINDING_INVALID");
            VerifyCompilerOptions(R7Json.Array(buildReceipt, "compiler_options"));
            VerifyFrameworkReferencePaths(R7Json.Array(buildReceipt, "framework_reference_paths"));
            HashSet<string> terminalSourceInputPaths = new HashSet<string>(StringComparer.Ordinal);
            VerifySourceFiles(R7Json.Array(buildReceipt, "source_files"), activeVersion.SourceCommit, "GENERATED/R7BuildIdentity.g.cs", R7Fixed.BuildSourceInputRoot, expectedVolumeIdentity, terminalSourceInputPaths);
            VerifyGovernedScripts(R7Json.Array(buildReceipt, "governed_scripts"), installerScriptSha256, R7Fixed.BuildSourceInputRoot, expectedVolumeIdentity, terminalSourceInputPaths);
            VerifyExactFileInventory(R7Fixed.BuildSourceInputRoot, terminalSourceInputPaths, "TERMINAL_SOURCE_INPUT");
            VerifyKeyMetadata(R7Json.Array(buildReceipt, "key_file_metadata"), expectedVolumeIdentity);
            VerifyToolchain(R7Json.Array(buildReceipt, "toolchain"));
            if (R7Hash.Bytes(R7Json.Encode(R7Json.Array(buildReceipt, "toolchain"))) != R7Hash.Bytes(R7Json.Encode(R7Json.Array(dependencyManifest, "build_tools")))) throw new InvalidDataException("BUILD_TOOLCHAIN_DEPENDENCY_MANIFEST_MISMATCH");
            VerifyGovernedGit(R7Json.Child(buildReceipt, "governed_git"), R7Json.Array(buildReceipt, "toolchain"));

            Dictionary<string, string> expectedBinaries = new Dictionary<string, string>(StringComparer.Ordinal);
            expectedBinaries.Add("BOOTSTRAP_ARTIFACT_TOOL", Component(activeVersion, "INSTALLER_TOOL"));
            expectedBinaries.Add("UPGRADE_CLIENT", upgradeClientSha256);
            foreach (string role in new string[] { "TERMINAL_SIGNER", "EXECUTION", "OBSERVATION", "COMPARATOR", "PUBLIC_VERIFIER", "AUTHORITY_VERIFIER", "ADVERSARIAL_HARNESS", "STATIC_VERIFIER" }) expectedBinaries.Add(role, Component(activeVersion, role));
            Dictionary<string, string> expectedNames = new Dictionary<string, string>(StringComparer.Ordinal)
            {
                { "BOOTSTRAP_ARTIFACT_TOOL", "R7ArtifactTool.bootstrap.exe" }, { "UPGRADE_CLIENT", "RandleTerminalUpgradeClient.exe" },
                { "TERMINAL_SIGNER", "RandleTerminalAuthority.exe" }, { "EXECUTION", "RandleTerminalExecution.exe" }, { "OBSERVATION", "RandleTerminalObservation.exe" },
                { "COMPARATOR", "RandleTerminalComparator.exe" }, { "PUBLIC_VERIFIER", "RandleTerminalPublicVerifier.exe" }, { "AUTHORITY_VERIFIER", "RandleTerminalAuthorityVerifier.exe" },
                { "ADVERSARIAL_HARNESS", "RandleTerminalAdversarialHarness.exe" }, { "STATIC_VERIFIER", "RandleTerminalStaticVerifier.exe" }
            };
            HashSet<string> binaryRoles = new HashSet<string>(StringComparer.Ordinal);
            foreach (object raw in R7Json.Array(buildReceipt, "binaries"))
            {
                SortedDictionary<string, object> binary = RequireObject(raw);
                string role = R7Json.String(binary, "role", 1, 256);
                string expectedHash;
                string expectedName;
                if (!expectedBinaries.TryGetValue(role, out expectedHash) || !expectedNames.TryGetValue(role, out expectedName) || !binaryRoles.Add(role)) throw new InvalidDataException("BUILD_BINARY_ROLE_INVALID:" + role);
                VerifyBinaryReceipt(binary, role, expectedName, expectedHash);
            }
            if (binaryRoles.Count != expectedBinaries.Count || R7Json.String(buildReceipt, "bootstrap_artifact_tool_sha256", 64, 64) != expectedBinaries["BOOTSTRAP_ARTIFACT_TOOL"]) throw new InvalidDataException("BUILD_BINARY_SET_INCOMPLETE");

            int closureCount = VerifyBuildInputClosures(R7Json.Array(buildReceipt, "build_input_closures"), expectedVolumeIdentity);
            int installedFileCount = VerifyAuthorityPackageAndInventory(activeVersion, expectedVolumeIdentity);
            string upgradeBuildReceiptIdentity = VerifyUpgradeAuthorityBuildReceipt(
                CurrentUpgradeBinarySha256(expectedVolumeIdentity),
                R7BuildIdentity.UpgradePolicySha256,
                terminalPolicy.DependencyManifestSha256,
                upgradeClientSha256,
                installerScriptSha256,
                activeVersion.SourceCommit,
                activeVersion.SourceTree,
                expectedVolumeIdentity);
            return R7Json.Object(
                "authority_package_identity", Component(activeVersion, "AUTHORITY_PACKAGE_MANIFEST"),
                "binary_role_count", (long)binaryRoles.Count,
                "build_input_closure_count", (long)closureCount,
                "build_receipt_identity", terminalPolicy.BuildReceiptSha256,
                "dependency_manifest_identity", terminalPolicy.DependencyManifestSha256,
                "installed_immutable_file_count", (long)installedFileCount,
                "source_commit", activeVersion.SourceCommit,
                "source_tree", activeVersion.SourceTree,
                "status", "PASS",
                "upgrade_build_receipt_identity", upgradeBuildReceiptIdentity);
        }

        private static string CurrentUpgradeBinarySha256(string volumeIdentity)
        {
            string path = Path.Combine(R7Fixed.UpgradeInstallRoot, "RandleTerminalUpgradeAuthority.exe");
            using (R7VerifiedFile file = R7SafeFile.Open(path, path, R7Fixed.UpgradeInstallRoot, null, R7Fixed.SystemSid, null, volumeIdentity)) return file.Measurement.Sha256;
        }

        private static void VerifyUpgradeImmutableInventory(string buildReceiptIdentity, string binarySha256, string policySha256, string dependencyManifestSha256, string upgradeClientSha256, string volumeIdentity, HashSet<string> sourceInputPaths, HashSet<string> closurePaths)
        {
            HashSet<string> expected = new HashSet<string>(StringComparer.Ordinal);
            foreach (string path in sourceInputPaths) expected.Add(path);
            foreach (string path in closurePaths) expected.Add(path);
            string binaryPath = Path.Combine(R7Fixed.UpgradeInstallRoot, "RandleTerminalUpgradeAuthority.exe");
            string clientPath = Path.Combine(R7Fixed.UpgradeInstallRoot, "RandleTerminalUpgradeClient.exe");
            expected.Add(binaryPath);
            expected.Add(clientPath);
            expected.Add(R7Fixed.UpgradePolicyPath);
            expected.Add(R7Fixed.UpgradeDependencyManifestPath);
            expected.Add(R7Fixed.UpgradeBuildReceiptPath);
            expected.Add(R7Fixed.UpgradePublicCertificatePath);
            using (R7VerifiedFile file = R7SafeFile.Open(binaryPath, binaryPath, R7Fixed.UpgradeInstallRoot, binarySha256, R7Fixed.SystemSid, null, volumeIdentity)) { }
            using (R7VerifiedFile file = R7SafeFile.Open(clientPath, clientPath, R7Fixed.UpgradeInstallRoot, upgradeClientSha256, R7Fixed.SystemSid, null, volumeIdentity)) { }
            using (R7VerifiedFile file = R7SafeFile.Open(R7Fixed.UpgradePolicyPath, R7Fixed.UpgradePolicyPath, R7Fixed.UpgradeConfigRoot, policySha256, R7Fixed.SystemSid, null, volumeIdentity)) { }
            using (R7VerifiedFile file = R7SafeFile.Open(R7Fixed.UpgradeDependencyManifestPath, R7Fixed.UpgradeDependencyManifestPath, R7Fixed.UpgradeConfigRoot, dependencyManifestSha256, R7Fixed.SystemSid, null, volumeIdentity)) { }
            using (R7VerifiedFile file = R7SafeFile.Open(R7Fixed.UpgradeBuildReceiptPath, R7Fixed.UpgradeBuildReceiptPath, R7Fixed.UpgradeConfigRoot, buildReceiptIdentity, R7Fixed.SystemSid, null, volumeIdentity)) { }
            using (R7VerifiedFile file = R7SafeFile.Open(R7Fixed.UpgradePublicCertificatePath, R7Fixed.UpgradePublicCertificatePath, R7Fixed.UpgradeTrustRoot, R7BuildIdentity.UpgradePublicCertificateSha256, R7Fixed.SystemSid, null, volumeIdentity)) { }
            List<string> actual = new List<string>();
            foreach (string root in new string[] { R7Fixed.UpgradeInstallRoot, R7Fixed.UpgradeConfigRoot, R7Fixed.UpgradeTrustRoot }) CollectFiles(root, actual);
            foreach (string path in actual) if (!expected.Contains(path)) throw new InvalidDataException("UNMANIFESTED_UPGRADE_IMMUTABLE_FILE:" + path);
            if (actual.Count != expected.Count) throw new InvalidDataException("UPGRADE_IMMUTABLE_FILE_MISSING");
        }

        private static void VerifyExactFileInventory(string root, HashSet<string> expected, string label)
        {
            List<string> actual = new List<string>();
            CollectFiles(root, actual);
            foreach (string path in actual) if (!expected.Contains(path)) throw new InvalidDataException("UNMANIFESTED_" + label + "_FILE:" + path);
            if (actual.Count != expected.Count) throw new InvalidDataException(label + "_FILE_MISSING");
        }

        private static int VerifyAuthorityPackageAndInventory(R7UpgradeVersionBinding activeVersion, string volumeIdentity)
        {
            string manifestIdentity = Component(activeVersion, "AUTHORITY_PACKAGE_MANIFEST");
            SortedDictionary<string, object> manifest;
            using (R7VerifiedFile file = R7SafeFile.Open(R7Fixed.AuthorityPackageManifestPath, R7Fixed.AuthorityPackageManifestPath, R7Fixed.RemediationAuthorityRoot, manifestIdentity, R7Fixed.SystemSid, null, volumeIdentity)) manifest = R7Json.ParseCanonicalObject(file.Bytes);
            R7Json.ExactKeys(manifest, "artifact_type", "files", "prohibited_source_commit", "prohibited_source_dependency_count", "schema_version", "source_commit", "source_tree");
            if (R7Json.String(manifest, "artifact_type", 1, 256) != "R7_CONTENT_ADDRESSED_AUTHORITY_PACKAGE_MANIFEST" || R7Json.String(manifest, "schema_version", 1, 64) != "1.0.0" ||
                R7Json.String(manifest, "source_commit", 40, 40) != activeVersion.SourceCommit || R7Json.String(manifest, "source_tree", 40, 40) != activeVersion.SourceTree ||
                R7Json.String(manifest, "prohibited_source_commit", 40, 40) != "f0cfbce97e913a133530dd66a70326b1e03a0fb6" || R7Json.Integer(manifest, "prohibited_source_dependency_count", 0, 0) != 0) throw new InvalidDataException("AUTHORITY_PACKAGE_MANIFEST_INVALID");
            HashSet<string> paths = new HashSet<string>(StringComparer.Ordinal);
            HashSet<string> caseFoldedPaths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            HashSet<string> relativePaths = new HashSet<string>(StringComparer.Ordinal);
            foreach (object raw in R7Json.Array(manifest, "files"))
            {
                SortedDictionary<string, object> row = RequireObject(raw);
                R7Json.ExactKeys(row, "final_path", "raw_sha256", "size", "staging_relative_path");
                string finalPath = R7Json.String(row, "final_path", 3, 4096);
                string relative = R7Json.String(row, "staging_relative_path", 1, 2048);
                string sha = R7Json.String(row, "raw_sha256", 64, 64);
                if (!R7Hash.IsLowerSha256(sha) || !paths.Add(finalPath) || !caseFoldedPaths.Add(finalPath) || !relativePaths.Add(relative) ||
                    relative.IndexOf('\\') >= 0 || relative.StartsWith("/", StringComparison.Ordinal) || relative.IndexOf("..", StringComparison.Ordinal) >= 0 ||
                    !(relative.StartsWith("bin/", StringComparison.Ordinal) || relative.StartsWith("config/", StringComparison.Ordinal) || relative.StartsWith("build/", StringComparison.Ordinal) || relative.StartsWith("authority/", StringComparison.Ordinal))) throw new InvalidDataException("AUTHORITY_PACKAGE_ROW_INVALID:" + relative);
                string extension = Path.GetExtension(finalPath).ToLowerInvariant();
                if (extension == ".pfx" || extension == ".p12" || extension == ".p8" || extension == ".key" || extension == ".pem") throw new InvalidDataException("PRIVATE_KEY_FIXTURE_IN_AUTHORITY_PACKAGE");
                string root = finalPath.StartsWith(R7Fixed.TerminalInstallRoot + Path.DirectorySeparatorChar, StringComparison.Ordinal) ? R7Fixed.TerminalInstallRoot : R7Fixed.RemediationRoot;
                using (R7VerifiedFile installed = R7SafeFile.Open(finalPath, finalPath, root, sha, R7Fixed.SystemSid, null, volumeIdentity))
                {
                    if (installed.Measurement.Size != R7Json.Integer(row, "size", 0, Int64.MaxValue)) throw new InvalidDataException("AUTHORITY_PACKAGE_FILE_SIZE_INVALID:" + relative);
                }
            }
            paths.Add(R7Fixed.AuthorityPackageManifestPath);
            paths.Add(R7Fixed.ActiveTransitionPath);
            using (R7VerifiedFile active = R7SafeFile.Open(R7Fixed.ActiveTransitionPath, R7Fixed.ActiveTransitionPath, R7Fixed.RemediationTrustRoot, activeVersion.AuthorizationIdentity, R7Fixed.SystemSid, null, volumeIdentity)) { }
            List<string> actual = new List<string>();
            foreach (string root in new string[] { R7Fixed.TerminalInstallRoot, R7Fixed.RemediationAuthorityRoot, R7Fixed.RemediationBuildRoot, R7Fixed.RemediationConfigRoot, R7Fixed.RemediationTrustRoot }) CollectFiles(root, actual);
            foreach (string file in actual) if (!paths.Contains(file)) throw new InvalidDataException("UNMANIFESTED_IMMUTABLE_INSTALLED_FILE:" + file);
            if (actual.Count != paths.Count) throw new InvalidDataException("IMMUTABLE_INSTALLED_FILE_MISSING");
            return actual.Count;
        }

        private static void CollectFiles(string root, List<string> files)
        {
            using (R7VerifiedDirectory held = R7SafeFile.HoldDirectory(root, root, R7Fixed.SystemSid, null, null))
            {
                FileSystemInfo[] entries = new DirectoryInfo(root).GetFileSystemInfos();
                Array.Sort(entries, delegate(FileSystemInfo left, FileSystemInfo right) { return StringComparer.Ordinal.Compare(left.FullName, right.FullName); });
                foreach (FileSystemInfo entry in entries)
                {
                    if ((entry.Attributes & FileAttributes.ReparsePoint) != 0) throw new InvalidDataException("IMMUTABLE_INSTALL_REPARSE_ENTRY:" + entry.FullName);
                    DirectoryInfo directory = entry as DirectoryInfo;
                    if (directory != null) CollectFiles(directory.FullName, files);
                    else files.Add(Path.GetFullPath(entry.FullName));
                }
            }
        }

        private static int VerifyBuildInputClosures(object[] rows, string volumeIdentity)
        {
            HashSet<string> roles = new HashSet<string>(StringComparer.Ordinal);
            foreach (object raw in rows)
            {
                SortedDictionary<string, object> row = RequireObject(raw);
                R7Json.ExactKeys(row, "file_count", "manifest_raw_sha256", "manifest_relative_path", "post_use_manifest_relative_path", "post_use_raw_sha256", "role", "root", "stable_during_use");
                string role = R7Json.String(row, "role", 1, 256);
                string manifestIdentity = R7Json.String(row, "manifest_raw_sha256", 64, 64);
                string postIdentity = R7Json.String(row, "post_use_raw_sha256", 64, 64);
                if (!roles.Add(role) || !R7Json.Boolean(row, "stable_during_use") || manifestIdentity != postIdentity || !R7Hash.IsLowerSha256(manifestIdentity)) throw new InvalidDataException("BUILD_INPUT_CLOSURE_INVALID:" + role);
                VerifyClosureManifest(row, "manifest_relative_path", manifestIdentity, volumeIdentity);
                VerifyClosureManifest(row, "post_use_manifest_relative_path", postIdentity, volumeIdentity);
            }
            foreach (string required in new string[] { "GIT_INSTALLATION", "DOTNET_COMPILER_FRAMEWORK", "DOTNET_REFERENCE_ASSEMBLIES", "ILDASM_TOOL_DIRECTORY", "POWERSHELL_ORCHESTRATOR_DIRECTORY" }) if (!roles.Contains(required)) throw new InvalidDataException("BUILD_INPUT_CLOSURE_MISSING:" + required);
            if (roles.Count != 5) throw new InvalidDataException("UNAUTHORIZED_BUILD_INPUT_CLOSURE");
            return roles.Count;
        }

        private static void VerifyClosureManifest(SortedDictionary<string, object> row, string field, string identity, string volumeIdentity)
        {
            string relative = R7Json.String(row, field, 1, 512);
            if (!relative.StartsWith("BuildInputClosures/", StringComparison.Ordinal) || relative.IndexOf("..", StringComparison.Ordinal) >= 0 || relative.IndexOf('\\') >= 0) throw new InvalidDataException("BUILD_CLOSURE_PATH_INVALID");
            string path = Path.Combine(R7Fixed.RemediationBuildRoot, relative.Replace('/', Path.DirectorySeparatorChar));
            VerifyClosureDocument(path, R7Fixed.BuildClosureRoot, identity, R7Json.Integer(row, "file_count", 1, Int64.MaxValue), volumeIdentity);
        }

        private static void VerifyClosureDocument(string path, string fixedRoot, string identity, long expectedFileCount, string volumeIdentity)
        {
            SortedDictionary<string, object> manifest;
            using (R7VerifiedFile file = R7SafeFile.Open(path, path, fixedRoot, identity, R7Fixed.SystemSid, null, volumeIdentity)) manifest = R7Json.ParseCanonicalObject(file.Bytes);
            R7Json.ExactKeys(manifest, "artifact_type", "file_count", "files", "root", "schema_version");
            object[] files = R7Json.Array(manifest, "files");
            if (R7Json.String(manifest, "artifact_type", 1, 256) != "R7_RECURSIVE_BUILD_INPUT_CLOSURE" || R7Json.String(manifest, "schema_version", 1, 64) != "1.0.0" ||
                R7Json.Integer(manifest, "file_count", 1, Int64.MaxValue) != files.Length || expectedFileCount != files.Length || Path.GetFullPath(R7Json.String(manifest, "root", 3, 4096)).Length < 3) throw new InvalidDataException("BUILD_CLOSURE_MANIFEST_INVALID");
            HashSet<string> paths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (object rawFile in files)
            {
                SortedDictionary<string, object> measurement = RequireObject(rawFile);
                ValidateMeasurement(measurement, true);
                if (!paths.Add(R7Json.String(measurement, "path", 3, 4096))) throw new InvalidDataException("BUILD_CLOSURE_FILE_DUPLICATE");
            }
        }

        private static int VerifyUpgradeBuildInputClosures(object[] rows, string volumeIdentity, HashSet<string> expectedPaths)
        {
            Dictionary<string, string> expectedNames = new Dictionary<string, string>(StringComparer.Ordinal)
            {
                { "DOTNET_COMPILER_FRAMEWORK", "dotnet_compiler_framework.upgrade-final.json" },
                { "DOTNET_REFERENCE_ASSEMBLIES", "dotnet_reference_assemblies.upgrade-final.json" },
                { "ILDASM_TOOL_DIRECTORY", "ildasm_tool_directory.upgrade-final.json" },
                { "POWERSHELL_ORCHESTRATOR_DIRECTORY", "powershell_orchestrator_directory.upgrade-final.json" }
            };
            HashSet<string> roles = new HashSet<string>(StringComparer.Ordinal);
            foreach (object raw in rows)
            {
                SortedDictionary<string, object> row = RequireObject(raw);
                R7Json.ExactKeys(row, "file_count", "final_manifest_raw_sha256", "initial_manifest_raw_sha256", "manifest_relative_path", "role", "stable_during_use");
                string role = R7Json.String(row, "role", 1, 256);
                string expectedName;
                if (!expectedNames.TryGetValue(role, out expectedName) || !roles.Add(role) || !R7Json.Boolean(row, "stable_during_use")) throw new InvalidDataException("UPGRADE_BUILD_CLOSURE_ROLE_INVALID:" + role);
                string initial = R7Json.String(row, "initial_manifest_raw_sha256", 64, 64);
                string final = R7Json.String(row, "final_manifest_raw_sha256", 64, 64);
                string relative = R7Json.String(row, "manifest_relative_path", 1, 512);
                if (!R7Hash.IsLowerSha256(initial) || initial != final || relative != "BuildInputClosures/" + expectedName) throw new InvalidDataException("UPGRADE_BUILD_CLOSURE_IDENTITY_INVALID:" + role);
                string path = Path.Combine(R7Fixed.UpgradeConfigRoot, relative.Replace('/', Path.DirectorySeparatorChar));
                if (!expectedPaths.Add(path)) throw new InvalidDataException("UPGRADE_BUILD_CLOSURE_PATH_DUPLICATE");
                VerifyClosureDocument(path, R7Fixed.UpgradeBuildClosureRoot, final, R7Json.Integer(row, "file_count", 1, Int64.MaxValue), volumeIdentity);
            }
            if (roles.Count != expectedNames.Count) throw new InvalidDataException("UPGRADE_BUILD_CLOSURE_SET_INCOMPLETE");
            return roles.Count;
        }

        private static void ValidateDependencyManifest(SortedDictionary<string, object> manifest)
        {
            R7Json.ExactKeys(manifest, "artifact_type", "build_host_architecture", "build_tools", "closed_search_policy", "framework_references", "runtime_allowlist", "runtime_configuration", "schema_version");
            if (R7Json.String(manifest, "artifact_type", 1, 256) != "R7_CLOSED_EXECUTABLE_DEPENDENCY_MANIFEST" || R7Json.String(manifest, "build_host_architecture", 1, 32) != "x64" || R7Json.String(manifest, "schema_version", 1, 64) != "1.0.0") throw new InvalidDataException("DEPENDENCY_MANIFEST_PUBLIC_INVALID");
            VerifyToolchain(R7Json.Array(manifest, "build_tools"));
            foreach (string field in new string[] { "framework_references", "runtime_allowlist", "runtime_configuration" })
            {
                object[] rows = R7Json.Array(manifest, field);
                if (rows.Length == 0) throw new InvalidDataException("DEPENDENCY_MANIFEST_EMPTY:" + field);
                foreach (object raw in rows) ValidateMeasurement(RequireObject(raw), true);
            }
            SortedDictionary<string, object> search = R7Json.Child(manifest, "closed_search_policy");
            R7Json.ExactKeys(search, "application_configuration", "current_directory_imports", "environment_imports", "git_runtime", "machine_configuration", "native_dll_search", "python_runtime", "runtime_profiler", "unmanifested_modules", "user_site");
            if (R7Json.String(search, "application_configuration", 1, 32) != "DENIED" || R7Json.String(search, "git_runtime", 1, 32) != "DENIED" || R7Json.String(search, "python_runtime", 1, 32) != "DENIED" ||
                R7Json.String(search, "machine_configuration", 1, 64) != "MANIFESTED_AND_HELD" || R7Json.String(search, "native_dll_search", 1, 64) != "SYSTEM32_ONLY") throw new InvalidDataException("DEPENDENCY_SEARCH_POLICY_PUBLIC_INVALID");
        }

        private static void VerifyBinaryReceipt(SortedDictionary<string, object> binary, string expectedRole, string expectedFileName, string expectedPassASha256)
        {
            R7Json.ExactKeys(binary, "file_name", "normalized_il_equal", "normalized_il_sha256", "pass_a_sha256", "pass_b_sha256", "raw_difference", "role", "size");
            string passA = R7Json.String(binary, "pass_a_sha256", 64, 64);
            string passB = R7Json.String(binary, "pass_b_sha256", 64, 64);
            if (R7Json.String(binary, "role", 1, 256) != expectedRole || R7Json.String(binary, "file_name", 1, 256) != expectedFileName || passA != expectedPassASha256 ||
                !R7Hash.IsLowerSha256(passA) || !R7Hash.IsLowerSha256(passB) || !R7Hash.IsLowerSha256(R7Json.String(binary, "normalized_il_sha256", 64, 64)) || !R7Json.Boolean(binary, "normalized_il_equal") || R7Json.Integer(binary, "size", 1, Int64.MaxValue) < 1) throw new InvalidDataException("BINARY_BUILD_RECEIPT_INVALID:" + expectedRole);
            SortedDictionary<string, object> difference = R7Json.Child(binary, "raw_difference");
            R7Json.ExactKeys(difference, "differing_byte_count", "explanation", "first_differing_offsets", "left_size", "right_size");
            long differing = R7Json.Integer(difference, "differing_byte_count", 0, Int64.MaxValue);
            if ((passA == passB && differing != 0) || (passA != passB && differing == 0) || R7Json.Integer(difference, "left_size", 1, Int64.MaxValue) != R7Json.Integer(binary, "size", 1, Int64.MaxValue) || R7Json.Integer(difference, "right_size", 1, Int64.MaxValue) < 1 || R7Json.String(difference, "explanation", 1, 1024).Length == 0) throw new InvalidDataException("BINARY_RAW_DIFFERENCE_INVALID:" + expectedRole);
            foreach (object offset in R7Json.Array(difference, "first_differing_offsets")) if (!(offset is long) || (long)offset < 0) throw new InvalidDataException("BINARY_RAW_OFFSET_INVALID:" + expectedRole);
        }

        private static void VerifyCompilerOptions(object[] values)
        {
            string[] expected = new string[] { "/noconfig", "/target:exe", "/platform:x64", "/optimize+", "/checked+", "/debug-", "/warn:4", "/nostdlib+", "/langversion:5", "/filealign:512" };
            if (values.Length != expected.Length) throw new InvalidDataException("COMPILER_OPTIONS_INCOMPLETE");
            for (int index = 0; index < expected.Length; index++) if (!String.Equals(values[index] as string, expected[index], StringComparison.Ordinal)) throw new InvalidDataException("COMPILER_OPTION_INVALID");
        }

        private static void VerifyFrameworkReferencePaths(object[] values)
        {
            HashSet<string> names = new HashSet<string>(StringComparer.Ordinal);
            foreach (object raw in values)
            {
                string path = raw as string;
                if (path == null || !Path.IsPathRooted(path) || !names.Add(Path.GetFileName(path))) throw new InvalidDataException("FRAMEWORK_REFERENCE_PATH_INVALID");
            }
            foreach (string required in new string[] { "mscorlib.dll", "System.dll", "System.Core.dll", "System.Security.dll", "System.ServiceProcess.dll" }) if (!names.Contains(required)) throw new InvalidDataException("FRAMEWORK_REFERENCE_PATH_MISSING:" + required);
            if (names.Count != 5) throw new InvalidDataException("FRAMEWORK_REFERENCE_PATH_EXTRA");
        }

        private static string VerifySourceFiles(object[] values, string expectedCommit, string expectedGeneratedPath, string sourceInputRoot, string volumeIdentity, HashSet<string> expectedInstalledPaths)
        {
            HashSet<string> paths = new HashSet<string>(StringComparer.Ordinal);
            int committed = 0;
            int generated = 0;
            string generatedSha256 = null;
            foreach (object raw in values)
            {
                SortedDictionary<string, object> row = RequireObject(raw);
                R7Json.ExactKeys(row, "blob", "path", "raw_sha256", "size");
                string path = R7Json.String(row, "path", 1, 4096);
                string blob = R7Json.String(row, "blob", 1, 64);
                string rawSha256 = R7Json.String(row, "raw_sha256", 64, 64);
                long size = R7Json.Integer(row, "size", 1, Int64.MaxValue);
                if (!paths.Add(path) || !R7Hash.IsLowerSha256(rawSha256) || path.IndexOf('\\') >= 0 || path.IndexOf("..", StringComparison.Ordinal) >= 0 || path.StartsWith("/", StringComparison.Ordinal)) throw new InvalidDataException("SOURCE_FILE_RECEIPT_INVALID");
                string installedPath = Path.Combine(sourceInputRoot, path.Replace('/', Path.DirectorySeparatorChar));
                if (!expectedInstalledPaths.Add(installedPath)) throw new InvalidDataException("SOURCE_INPUT_INSTALLED_PATH_DUPLICATE");
                byte[] bytes;
                using (R7VerifiedFile file = R7SafeFile.Open(installedPath, installedPath, sourceInputRoot, rawSha256, R7Fixed.SystemSid, null, volumeIdentity))
                {
                    if (file.Measurement.Size != size) throw new InvalidDataException("SOURCE_INPUT_SIZE_INVALID:" + path);
                    bytes = file.Bytes;
                }
                if (blob == "GENERATED_BUILD_INPUT")
                {
                    generated++;
                    if (path != expectedGeneratedPath) throw new InvalidDataException("GENERATED_SOURCE_PATH_INVALID");
                    generatedSha256 = rawSha256;
                }
                else
                {
                    committed++;
                    if (blob.Length != 40 || !IsLowerHex(blob) || path.IndexOf("/Source/", StringComparison.Ordinal) < 0 && !path.EndsWith("/BuildInputs/R7BuildIdentityContract.cs", StringComparison.Ordinal) || GitBlobIdentity(bytes) != blob) throw new InvalidDataException("COMMITTED_SOURCE_BLOB_INVALID");
                }
            }
            if (committed < 10 || generated != 1 || expectedCommit == null || expectedCommit.Length != 40 || !IsLowerHex(expectedCommit)) throw new InvalidDataException("SOURCE_FILE_RECEIPT_INCOMPLETE");
            return generatedSha256;
        }

        private static void VerifyGovernedScripts(object[] rows, string installerScriptSha256, string sourceInputRoot, string volumeIdentity, HashSet<string> expectedInstalledPaths)
        {
            HashSet<string> names = new HashSet<string>(StringComparer.Ordinal);
            HashSet<string> expected = new HashSet<string>(new string[] {
                "author_cases.ps1", "author_expectations.ps1", "build_remediation_package.ps1", "build_static_closure.ps1", "capture_remediation_host_state.ps1",
                "extract_immutable_authority.ps1", "generate_requirement_registry.ps1", "generate_static_closure_registries.ps1", "generate_traceability.ps1",
                "install_authorized_transition.ps1", "provision_upgrade_authority.ps1", "run_fresh_matrix.ps1", "scan_secrets_and_contamination.ps1",
                "verify_authority_coverage.ps1", "verify_static_architecture.ps1" }, StringComparer.Ordinal);
            foreach (object raw in rows)
            {
                SortedDictionary<string, object> row = RequireObject(raw);
                R7Json.ExactKeys(row, "allowed_invocation_stages", "authority_classification", "dependencies", "execution_class", "git_blob_identity", "mode", "path", "raw_sha256", "role", "size");
                string path = R7Json.String(row, "path", 1, 4096);
                string name = Path.GetFileName(path);
                string sha = R7Json.String(row, "raw_sha256", 64, 64);
                string blob = R7Json.String(row, "git_blob_identity", 40, 40);
                string mode = R7Json.String(row, "mode", 6, 6);
                string authorityClassification = R7Json.String(row, "authority_classification", 1, 256);
                string executionClass = R7Json.String(row, "execution_class", 1, 64);
                string role = R7Json.String(row, "role", 1, 256);
                long size = R7Json.Integer(row, "size", 1, Int64.MaxValue);
                object[] stages = R7Json.Array(row, "allowed_invocation_stages");
                object[] dependencies = R7Json.Array(row, "dependencies");
                if (!names.Add(name) || !expected.Contains(name) || !R7Hash.IsLowerSha256(sha) || !IsLowerHex(blob) || mode != "100644" || stages.Length == 0 || dependencies.Length == 0 || authorityClassification.Length == 0 || executionClass.Length == 0 || role.Length == 0 || path.IndexOf('\\') >= 0 || path.IndexOf("..", StringComparison.Ordinal) >= 0 || !path.StartsWith("Architecture/Audits/2026-07-24_R7_Terminal_Authority_Architecture_Remediation_DRAFT/", StringComparison.Ordinal)) throw new InvalidDataException("GOVERNED_SCRIPT_INVALID");
                foreach (object stage in stages) if (!(stage is string) || ((string)stage).Length == 0) throw new InvalidDataException("GOVERNED_SCRIPT_STAGE_INVALID");
                foreach (object dependency in dependencies) if (!(dependency is string) || ((string)dependency).Length == 0) throw new InvalidDataException("GOVERNED_SCRIPT_DEPENDENCY_INVALID");
                string installedPath = Path.Combine(sourceInputRoot, path.Replace('/', Path.DirectorySeparatorChar));
                if (!expectedInstalledPaths.Add(installedPath)) throw new InvalidDataException("GOVERNED_SCRIPT_INSTALLED_PATH_DUPLICATE");
                using (R7VerifiedFile file = R7SafeFile.Open(installedPath, installedPath, sourceInputRoot, sha, R7Fixed.SystemSid, null, volumeIdentity))
                {
                    if (file.Measurement.Size != size || GitBlobIdentity(file.Bytes) != blob) throw new InvalidDataException("GOVERNED_SCRIPT_BLOB_INVALID:" + name);
                }
                if (name == "install_authorized_transition.ps1" && sha != installerScriptSha256) throw new InvalidDataException("INSTALLER_SCRIPT_BUILD_BINDING_INVALID");
            }
            if (names.Count != expected.Count) throw new InvalidDataException("GOVERNED_SCRIPT_SET_INCOMPLETE");
        }

        private static string GitBlobIdentity(byte[] bytes)
        {
            byte[] header = Encoding.ASCII.GetBytes("blob " + bytes.Length.ToString(CultureInfo.InvariantCulture) + "\0");
            byte[] input = new byte[header.Length + bytes.Length];
            Buffer.BlockCopy(header, 0, input, 0, header.Length);
            Buffer.BlockCopy(bytes, 0, input, header.Length, bytes.Length);
            using (SHA1 algorithm = SHA1.Create()) return BitConverter.ToString(algorithm.ComputeHash(input)).Replace("-", String.Empty).ToLowerInvariant();
        }

        private static void VerifyKeyMetadata(object[] rows, string volumeIdentity)
        {
            HashSet<string> roles = new HashSet<string>(StringComparer.Ordinal);
            foreach (object raw in rows)
            {
                SortedDictionary<string, object> row = RequireObject(raw);
                R7Json.ExactKeys(row, "measurement", "private_bytes_read", "role");
                string role = R7Json.String(row, "role", 1, 256);
                if (!roles.Add(role) || R7Json.Boolean(row, "private_bytes_read")) throw new InvalidDataException("KEY_METADATA_DISCLOSURE_INVALID");
                SortedDictionary<string, object> measurement = R7Json.Child(row, "measurement");
                R7Json.ExactKeys(measurement, "canonical_path", "creation_time", "file_identity", "final_nt_path", "hard_link_count", "owner_sid", "security_descriptor_sha256", "sha256", "short_path", "size", "streams", "volume_identity");
                if (R7Json.String(measurement, "owner_sid", 1, 256) != R7Fixed.SystemSid || R7Json.Integer(measurement, "hard_link_count", 1, 1) != 1 || R7Json.String(measurement, "volume_identity", 8, 64) != volumeIdentity || R7Json.String(measurement, "sha256", 0, 0).Length != 0 || !R7Hash.IsLowerSha256(R7Json.String(measurement, "security_descriptor_sha256", 64, 64))) throw new InvalidDataException("KEY_METADATA_MEASUREMENT_INVALID");
            }
            if (roles.Count != 2 || !roles.Contains("TERMINAL_SIGNING_KEY") || !roles.Contains("UPGRADE_SIGNING_KEY")) throw new InvalidDataException("KEY_METADATA_SET_INCOMPLETE");
        }

        private static void VerifyGovernedGit(SortedDictionary<string, object> git, object[] toolchain)
        {
            R7Json.ExactKeys(git, "environment", "executable_path", "executable_sha256", "invocations", "runtime_authority", "source_bytes");
            string executableSha = R7Json.String(git, "executable_sha256", 64, 64);
            if (!R7Hash.IsLowerSha256(executableSha) || R7Json.String(git, "runtime_authority", 1, 64) != "DENIED" || R7Json.String(git, "source_bytes", 1, 64) != "RAW_CAT_FILE_BLOB_BYTES" || !Path.IsPathRooted(R7Json.String(git, "executable_path", 3, 4096))) throw new InvalidDataException("GOVERNED_GIT_IDENTITY_INVALID");
            bool toolchainMatch = false;
            foreach (object rawTool in toolchain)
            {
                SortedDictionary<string, object> tool = RequireObject(rawTool);
                if (R7Json.String(tool, "role", 1, 256) == "GIT_BUILD_TIME_ONLY" && R7Json.String(R7Json.Child(tool, "measurement"), "sha256", 64, 64) == executableSha) toolchainMatch = true;
            }
            if (!toolchainMatch) throw new InvalidDataException("GOVERNED_GIT_TOOLCHAIN_MISMATCH");
            SortedDictionary<string, object> environment = R7Json.Child(git, "environment");
            R7Json.ExactKeys(environment, "GIT_ATTR_NOSYSTEM", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_SYSTEM", "GIT_LITERAL_PATHSPECS", "GIT_OPTIONAL_LOCKS", "GIT_PAGER", "GIT_TERMINAL_PROMPT", "LANG", "LC_ALL", "path_resolution");
            if (R7Json.String(environment, "GIT_CONFIG_NOSYSTEM", 1, 8) != "1" || R7Json.String(environment, "GIT_CONFIG_GLOBAL", 1, 8) != "NUL" || R7Json.String(environment, "GIT_CONFIG_SYSTEM", 1, 8) != "NUL" || R7Json.String(environment, "path_resolution", 1, 64) != "RESOLVED_ONCE_THEN_EXACT_EXECUTABLE") throw new InvalidDataException("GOVERNED_GIT_ENVIRONMENT_INVALID");
            object[] invocations = R7Json.Array(git, "invocations");
            if (invocations.Length < 8) throw new InvalidDataException("GOVERNED_GIT_INVOCATION_SET_INCOMPLETE");
            foreach (object rawInvocation in invocations)
            {
                SortedDictionary<string, object> invocation = RequireObject(rawInvocation);
                R7Json.ExactKeys(invocation, "arguments", "exit_code", "fixed_options", "stderr_sha256", "stdout_raw_sha256", "stdout_size");
                if (R7Json.Integer(invocation, "exit_code", 0, 0) != 0 || !R7Hash.IsLowerSha256(R7Json.String(invocation, "stderr_sha256", 64, 64)) || !R7Hash.IsLowerSha256(R7Json.String(invocation, "stdout_raw_sha256", 64, 64)) || R7Json.Integer(invocation, "stdout_size", 0, Int64.MaxValue) < 0) throw new InvalidDataException("GOVERNED_GIT_INVOCATION_INVALID");
                object[] arguments = R7Json.Array(invocation, "arguments");
                if (arguments.Length == 0) throw new InvalidDataException("GOVERNED_GIT_ARGUMENTS_EMPTY");
                string operation = arguments[0] as string;
                if (operation != "rev-parse" && operation != "status" && operation != "show" && operation != "ls-tree" && operation != "cat-file") throw new InvalidDataException("GOVERNED_GIT_OPERATION_UNAUTHORIZED");
                if (operation == "cat-file" && (arguments.Length != 3 || !String.Equals(arguments[1] as string, "blob", StringComparison.Ordinal) || !IsLowerHex(arguments[2] as string))) throw new InvalidDataException("GOVERNED_GIT_CAT_FILE_INVALID");
                bool hasNoPager = false, hasNoAutocrlf = false, hasNoFsMonitor = false, hasUtf8 = false;
                foreach (object rawOption in R7Json.Array(invocation, "fixed_options"))
                {
                    string option = rawOption as string;
                    if (option == "--no-pager") hasNoPager = true;
                    if (option == "core.autocrlf=false") hasNoAutocrlf = true;
                    if (option == "core.fsmonitor=false") hasNoFsMonitor = true;
                    if (option == "i18n.logOutputEncoding=utf-8") hasUtf8 = true;
                }
                if (!hasNoPager || !hasNoAutocrlf || !hasNoFsMonitor || !hasUtf8) throw new InvalidDataException("GOVERNED_GIT_FIXED_OPTIONS_INCOMPLETE");
            }
        }

        private static void VerifyToolchain(object[] rows)
        {
            HashSet<string> roles = new HashSet<string>(StringComparer.Ordinal);
            foreach (object raw in rows)
            {
                SortedDictionary<string, object> row = RequireObject(raw);
                R7Json.ExactKeys(row, "measurement", "role");
                string role = R7Json.String(row, "role", 1, 256);
                if (!roles.Add(role)) throw new InvalidDataException("TOOLCHAIN_ROLE_DUPLICATE");
                ValidateMeasurement(R7Json.Child(row, "measurement"), true);
            }
            foreach (string required in new string[] { "BOOTSTRAP_ARTIFACT_TOOL", "CSC", "GIT_BUILD_TIME_ONLY", "HOST_ACL_TOOL", "HOST_SERVICE_CONTROL_TOOL", "ILDASM", "POWERSHELL_NONAUTHORITATIVE_ORCHESTRATOR", "RUNTIME_MACHINE_CONFIG", "COMPILER_REFERENCE_mscorlib.dll", "COMPILER_REFERENCE_System.dll", "COMPILER_REFERENCE_System.Core.dll", "COMPILER_REFERENCE_System.Security.dll", "COMPILER_REFERENCE_System.ServiceProcess.dll" }) if (!roles.Contains(required)) throw new InvalidDataException("TOOLCHAIN_ROLE_MISSING:" + required);
            if (roles.Count != 13) throw new InvalidDataException("TOOLCHAIN_ROLE_EXTRA");
        }

        private static void ValidateMeasurement(SortedDictionary<string, object> measurement, bool requireContent)
        {
            R7Json.ExactKeys(measurement, "file_identity", "hard_link_count", "owner_sid", "path", "security_descriptor_sha256", "sha256", "size", "volume_identity");
            if (!Path.IsPathRooted(R7Json.String(measurement, "path", 3, 4096)) || !R7Hash.IsLowerSha256(R7Json.String(measurement, "security_descriptor_sha256", 64, 64)) ||
                (requireContent && !R7Hash.IsLowerSha256(R7Json.String(measurement, "sha256", 64, 64))) || R7Json.Integer(measurement, "hard_link_count", 1, UInt32.MaxValue) < 1 || R7Json.Integer(measurement, "size", 1, Int64.MaxValue) < 1 || R7Json.String(measurement, "file_identity", 1, 128).Length < 1 || R7Json.String(measurement, "owner_sid", 1, 256).Length < 1 || R7Json.String(measurement, "volume_identity", 8, 64).Length < 8) throw new InvalidDataException("FILE_MEASUREMENT_INVALID");
        }

        private static string Component(R7UpgradeVersionBinding version, string role)
        {
            string value;
            if (!version.ComponentSha256.TryGetValue(role, out value) || !R7Hash.IsLowerSha256(value)) throw new InvalidDataException("ACTIVE_COMPONENT_BUILD_BINDING_MISSING:" + role);
            return value;
        }

        private static bool IsLowerHex(string value)
        {
            if (String.IsNullOrEmpty(value)) return false;
            foreach (char character in value) if (!((character >= '0' && character <= '9') || (character >= 'a' && character <= 'f'))) return false;
            return true;
        }

        private static SortedDictionary<string, object> RequireObject(object value)
        {
            SortedDictionary<string, object> result = value as SortedDictionary<string, object>;
            if (result == null) throw new InvalidDataException("OBJECT_REQUIRED");
            return result;
        }
    }
}
