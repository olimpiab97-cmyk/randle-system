# R7 Unit 2 build-identity closure

The Unit 2 build has two deliberate identity phases. Neither phase uses a diagnostic identity or a sentinel value.

The client, public-verifier, and protocol-probe binaries are inputs to the policy: their raw SHA-256 values appear in that policy. Embedding the completed policy SHA-256 in those same binaries would therefore be circular. Those three binaries bind `client_policy_binding_derivation_sha256`, computed with `SHA256_UTF8_LENGTH_PREFIXED_FIELDS_V1` over the exact source, generated-source rule, compiler, ordered compiler switches, framework references, governed registries, public certificate, host-state record, bootstrap record, target receipts, target components, dependency manifest, and key-metadata records. The receipt labels that binding `NONCIRCULAR_INPUT_CLOSURE_DERIVATION_V1`.

After the three client-side binary identities are fixed, the policy is canonicalized. The upgrade-authority service and both packaged build tools are then compiled with the completed policy SHA-256 and the same full input-closure identity. Their binding is labeled `EXACT_POLICY_SHA256`.

The source-to-binary and determinism receipts contain the final raw binary hashes, so a binary cannot embed either receipt's final raw hash without another cycle. Each binary instead embeds domain-separated derivations from the complete pre-binary input closure. The receipts record both derivations and independently verify them against the same inventory.

Every compiler role records two complete ordered argument vectors, every committed and generated compiler input, every preprocessor symbol, explicit framework references, compiler identity, empty response/resource sets, normalized IL identity, raw pass identities, file identities, architecture, and intended future path. `verify_unit2_build_closure.ps1` reconstructs these sets and vectors from disk and the exact Git tree. It also executes the committed negative-case registry, including mutations in source text after preprocessing boundaries.

The build never reads private-key bytes, opens a signing provider, signs data, installs files, modifies service state, or writes outside its disposable Temp output root.
