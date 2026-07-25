namespace RandleAI.R7Remediation
{
    // Committed compiler input that defines the identity-generation contract.
    // Concrete identity values are generated from the exact source, toolchain,
    // configuration, policy, trust, key-metadata, and target-package inputs.
    internal static class R7BuildIdentityContract
    {
        internal const string SchemaVersion = "2.0.0";
        internal const string DerivationAlgorithm = "SHA256_UTF8_LENGTH_PREFIXED_FIELDS_V1";
        internal const string ReceiptBindingAlgorithm = "NONCIRCULAR_INPUT_CLOSURE_DERIVATION_V1";

        internal static readonly string[] RequiredFields = new string[]
        {
            "AuthoritySourceManifestSha256",
            "BuildInputClosureSha256",
            "CaseDefinitionsSha256",
            "ComparatorBinaryPath",
            "CoverageProofSha256",
            "DependencyManifestSha256",
            "DeterminismReceiptDerivationSha256",
            "ExecutionBinaryPath",
            "ExpectationsSha256",
            "FixedRootsSha256",
            "HistoricalClassificationRegistrySha256",
            "HostIdentitySha256",
            "InterfaceIdentity",
            "ObservationBinaryPath",
            "PipeIdentity",
            "ProtocolIdentity",
            "RequirementRegistrySha256",
            "ScriptRegistrySha256",
            "SourceCommit",
            "SourceToBinaryReceiptDerivationSha256",
            "SourceTree",
            "TargetBuildReceiptSha256",
            "TargetComponentSetSha256",
            "TargetOrchestratorReceiptSha256",
            "TerminalBinarySha256",
            "TerminalCheckpointSha256",
            "TerminalLedgerIdentity",
            "TerminalLedgerRoot",
            "TerminalPolicySha256",
            "TerminalPublicTrustSha256",
            "TerminalServiceSid",
            "UpgradeCertificateSha256",
            "UpgradeKeyFileIdentity",
            "UpgradeKeyFileOwnerSid",
            "UpgradeKeyFilePath",
            "UpgradeKeyFileSecurityDescriptorSha256",
            "UpgradeKeyFileVolumeIdentity",
            "UpgradePolicySha256",
            "UpgradePublicCertificateSha256",
            "UpgradePublicKeyIdentity",
            "UpgradeServiceSid",
            "UtilityRegistrySha256"
        };
    }
}
