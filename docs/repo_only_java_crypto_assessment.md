# Repo-Only Static Crypto Assessment for Java

## Purpose

Determine Java dependencies/classpaths and evaluate cryptography usage when only the source repository is available.

## 1) Scope and success criteria

### In scope

- Java/Kotlin source in Git repositories
- Build systems: Maven, Gradle, Ant/Ivy, unmanaged JARs
- Static discovery of crypto libraries, APIs, and misuse patterns

### Out of scope (must be explicitly reported)

- Runtime-only behavior (actual negotiated TLS ciphers, env-injected keys, dynamic provider selection)
- Secrets managed outside the repository (KMS/HSM/Vault/environment variables)
- Reachability certainty without execution traces

### Success criteria

- Per module: effective dependency graph and classpath candidates
- Crypto asset inventory with misuse findings and confidence
- Explicit limitations and unresolved items

## 2) Execution model (3 tiers)

Use the highest tier available and fall back gracefully.

### Tier A: zero-exec parsing (safest baseline)

No build-tool execution. Parse:

- `pom.xml`, parent references, BOM imports
- `settings.gradle(.kts)`, `build.gradle(.kts)`, `gradle/libs.versions.toml`
- `ivy.xml`, `build.xml`
- `lib/`, `libs/` JAR folders
- Lock/state files if present

Output: candidate dependency graph plus candidate classpaths (lower confidence).

### Tier B: dependency resolution without full compile (preferred)

Run build tool in sandbox/container; resolve dependencies only.

Maven:

- `./mvnw -q -DskipTests dependency:tree -DoutputType=text -DoutputFile=dep-tree.txt`
- `./mvnw -q -DskipTests dependency:build-classpath -Dmdep.outputFile=cp-compile.txt -DincludeScope=compile`
- Optional test coverage: same command with `-DincludeScope=test`

Gradle:

- `./gradlew -q dependencies --configuration compileClasspath`
- `./gradlew -q dependencies --configuration runtimeClasspath`
- Optional: `testCompileClasspath`, `testRuntimeClasspath`

Note: runtime-only classpaths are insufficient for many static analyses; include compile scope at minimum.

### Tier C: semantic static analysis

Run SAST/query rules using resolved context from Tier B (or Tier A fallback):

- API/symbol usage mapping
- Dataflow to crypto sinks
- Misuse checks
- Evidence extraction (file/line/symbol/path)

## 3) Build-system detection and module graph

For each repository:

1. Detect build tool at root and subdirectories.
2. Build module list (reactor/subprojects/composite builds).
3. Resolve effective versions:
   - Maven parent + dependencyManagement + imported BOMs
   - Gradle version catalogs + convention plugins + buildSrc
4. Record unresolved artifacts and private-repo auth failures as first-class output.

## 4) Crypto asset inventory model

Track both libraries/providers and usage points.

### Libraries/providers

- JCE/JCA standard APIs
- Bouncy Castle, Tink, Conscrypt, Apache Commons Crypto, and similar

### Usage points

- `Cipher`, `Mac`, `Signature`, `MessageDigest`, `KeyPairGenerator`, `KeyGenerator`, `SecretKeyFactory`, `SecureRandom`
- TLS config classes (`SSLContext`, `TrustManager`, `HostnameVerifier`, client-specific TLS builders)
- Keystore/truststore loading and handling

## 5) Required crypto misuse checks

Minimum ruleset should include:

1. Weak/deprecated algorithms or modes (DES/3DES/RC4/ECB/MD5/SHA-1 in risky contexts)
2. Insecure padding/protocol selections where applicable
3. Hardcoded keys, IVs, salts, seeds, passwords
4. Non-random or reused IV/nonce
5. Weak KDF settings (low iteration count, weak params)
6. Insecure randomness (`Random` used for security-sensitive material)
7. Trust-all certificates/permissive hostname verification
8. Disabled certificate validation/custom insecure trust managers
9. Short key sizes vs policy baseline
10. Config-driven algorithm strings that resolve to risky values

## 6) Confidence model (mandatory)

Every finding must include confidence and reason.

- High: resolved symbol + concrete callsite + deterministic literal/config evidence
- Medium: partial type resolution, inferred sink/source
- Low: pattern-only match without dependency/type resolution

Coverage section should include:

- Percentage of modules with resolved compile classpath
- Percentage of dependencies unresolved
- Files skipped/generated/binary-only
- Private repository/auth blockers

## 7) Output schema (recommended JSON)

Use this shape for machine and dashboard consumption:

- `project`
- `scan_metadata` (timestamp, tool versions, tier used)
- `modules[]`
  - `module_name`
  - `build_system`
  - `resolution_mode` (`zero_exec|resolved_no_compile|semantic`)
  - `classpath_compile[]`
  - `classpath_runtime[]`
  - `dependencies[]` (gav, scope, source, resolved/unresolved)
  - `crypto_assets[]` (library/provider/api/category)
  - `findings[]`
    - `id`, `title`, `severity`, `confidence`
    - `rule_id`, `cwe`, `policy_ref`
    - `location` (file, line, symbol)
    - `evidence` (literal/config/dataflow snippet)
    - `remediation`
  - `limitations[]`
- `global_limitations[]`
- `summary` (counts by severity/confidence, coverage metrics)

## 8) Operational safeguards

- Run dependency resolution in sandboxed containers (untrusted repository safety)
- Restrict credentials and use read-only artifact access
- Cache Maven/Gradle dependencies to improve repeatability
- Pin scanner and ruleset versions for reproducibility
- Persist raw evidence artifacts (dependency tree, classpath dumps, rule traces)

## 9) Stakeholder message

A repo-only static scan can provide high-value, auditable evidence of crypto usage and many misuse patterns, but it cannot fully prove production security posture without runtime/contextual validation.

Report findings in three buckets:

- Confirmed
- Probable
- Unknown due to missing runtime/build context
