# Run Manifest and Reproducibility Requirements v0.1

Identifier: `phase8-run-manifest.v0.1`

Every evaluated run must record:

- case and study identifiers;
- development or confirmatory cohort;
- run index and status;
- Git commit;
- input and case-manifest SHA-256 hashes;
- policy, policy hash, extraction configuration, prompt, and schema versions as
  applicable;
- baseline protocol and prompt hashes as applicable;
- requested and effective provider model;
- reasoning/configuration settings;
- start and completion timestamps;
- request identifiers, token usage, latency, attempts, and repairs;
- output artifact path and SHA-256 hash;
- error category when failed; and
- whether recommendations were frozen.

Generated metrics must identify their input run manifests and metric version.
Changing any frozen input creates a new run identity. Existing run artifacts
are never overwritten.

