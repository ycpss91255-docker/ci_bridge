# CI bridge ecosystem research

Research date: 2026-09-20

## Question

What existing open-source projects are closest to a tool that keeps CI task execution portable between GitHub Actions and GitLab CI, while centrally managing `.ci_bridge/`, `.ci_action/`, `.github/`, and `.gitlab/` and invoking scripts that live in the downstream repository?

## Short answer

The design is feasible, but the useful abstraction is a **portable task runner behind thin platform adapters**, not a translator between GitHub Actions YAML and GitLab CI YAML.

`taskctl` is the closest implementation reference for the execution core: its official repository describes TOML/YAML/JSON task definitions, single tasks, DAG pipelines, concurrency, conditions, and local or remote imports. Dagger and Earthly independently validate the architectural boundary: platform YAML stays thin and invokes the same portable build logic locally and in CI. GitHub reusable workflows and GitLab CI/CD components are useful distribution mechanisms later, but neither provides a shared cross-platform task model.

The proposed directories can therefore have these responsibilities:

```text
.ci_bridge/   portable CLI, config discovery/merge, validation, dispatch
.ci_action/   centrally managed task definitions and templates
.github/      GitHub trigger, permissions, runner, cache/artifact adapter
.gitlab/      GitLab trigger, permissions, runner, cache/artifact adapter
repo root     downstream source, tests, and locally runnable project scripts
```

## Candidate comparison

| Candidate | What the primary source establishes | Fit | Main caution |
|---|---|---:|---|
| [taskctl](https://github.com/taskctl/taskctl) | A cross-platform task runner whose config can be YAML, JSON, or TOML; a pipeline builds a graph of tasks or other pipelines and can execute concurrently or as a cascade; imports may be local or remote. | **Closest execution-model reference.** It already covers much of the proposed future model: named tasks, pipelines, dependencies, parallelism, and TOML. | GPL-3.0 licensing matters if code is copied or linked. Treat it as an architectural reference unless the project intentionally accepts that license. It is a task runner, not a GitHub/GitLab adapter or managed-directory policy. |
| [go-task/Task](https://taskfile.dev/docs/reference/schema) | A mature task runner with named tasks, includes, namespaces, working directories, variables, environment variables, and remote Taskfiles with an expected checksum. | Strong reference for task composition, schema validation, namespaces, and pinned remote configuration. | YAML-first rather than TOML; it does not make GitHub and GitLab pipeline semantics identical. |
| [Dagger](https://docs.dagger.io/getting-started/ci-integrations/github) | Portable functions/modules are called from a thin GitHub workflow; the project has explicitly described the goal that platform workflow files contain little logic and call a portable plan. | Strong validation of the thin-adapter/portable-core boundary and local reproducibility. | Introduces a container engine and SDK/module programming model, substantially heavier than TOML plus repository scripts. |
| [Earthly](https://github.com/earthly/earthly/blob/main/README.md) | Earthfiles run locally and on GitHub Actions and GitLab CI/CD; targets form a DAG, independent work runs in parallel, and targets can be reused across repositories. Official integration examples show both platforms invoking the same target: [GitHub Actions](https://docs.earthly.dev/ci-integration/vendor-specific-guides/gh-actions-integration) and [GitLab CI/CD](https://docs.earthly.dev/ci-integration/vendor-specific-guides/gitlab-integration). | Very close conceptual proof that one task definition can sit below two thin CI adapters. | The repository now states that Earthly is no longer actively maintained. Its container-only execution model is also broader than the intended script dispatcher. Do not choose it as a new dependency. |
| [Popper](https://github.com/getpopper/popper) | Defines a container-native workflow once, runs it locally, and generates configuration for multiple CI services, including GitLab. | Useful historical reference for the alternative “generate platform YAML” approach. | Generation creates a synchronization/staleness problem and expands scope toward a CI compiler. It is not the recommended first architecture here. |
| [rios0rios0/pipelines](https://github.com/rios0rios0/pipelines) | Platform-specific templates delegate work to shared `global/scripts/.../run.sh` entrypoints. | Closest directory/ownership precedent found for platform adapters calling centrally curated scripts. | It is a curated YAML/environment template library, not a TOML task model or downstream-manifest contract. |
| [projen-pipelines](https://github.com/open-constructs/projen-pipelines) | Generates pipelines for GitHub and GitLab from a programmatic project definition. | Evidence that generation can target both platforms. | AWS CDK/TypeScript-oriented and much broader than script dispatch; generated platform files introduce drift and review concerns. |
| [GitHub reusable workflows](https://docs.github.com/en/actions/concepts/workflows-and-actions/reusing-workflow-configurations) | An organization can centrally maintain reusable workflows; callers can pin a commit SHA. Reusable workflows contain jobs, while composite actions contain steps. | Good future distribution mechanism for `.github/`; a caller checkout operates on the downstream/caller repository. | GitHub-only. Secrets are not implicitly shared, permissions need deliberate design, and a workflow call is not a common GitHub/GitLab task schema. |
| [GitLab CI/CD components](https://docs.gitlab.com/ci/components/) | Components are versioned reusable pipeline units with typed inputs; GitLab recommends pinning releases or SHAs and notes that component config merges into consumer config. | Good future distribution mechanism for `.gitlab/`, with validation and versioning. | GitLab-only. Name collisions can merge jobs unexpectedly; components should be self-contained and are only directly consumable on the same GitLab instance unless mirrored. |

### Key conclusion from the comparison

No reviewed project exactly combines all four desired properties:

1. TOML task configuration.
2. Centrally managed task definitions that downstream authors do not directly edit.
3. Dispatch to arbitrary, locally runnable scripts in the downstream repository.
4. Thin adapters for both GitHub Actions and GitLab CI.

`taskctl` comes closest to properties 1 and the execution part of 3; Dagger/Earthly validate 3 and 4; native reusable workflows/components cover central distribution but remain platform-specific. The proposed `ci_bridge` is therefore not duplicating a single existing tool wholesale. Its differentiator is the management and trust boundary around those familiar patterns.

## `config` plus `config.d`: useful precedent, wrong primary model

OpenSSH is a useful precedent for **explicit composition**, but it is not evidence that every Linux `config.d` directory requires an explicit include. Its official [`ssh_config(5)` manual](https://man.openbsd.com/ssh_config.5) says `Include` accepts multiple files and globs, expands wildcard matches in lexical order, and generally uses the **first obtained value** for each parameter. By contrast, many systemd-style `*.d` families are discovered automatically by the program. The directory suffix alone therefore establishes neither discovery nor merge semantics; each application defines both.

For a true overlay use case, the analogous layout would be:

```text
.ci_action/
├── config.toml
└── config.d/
    ├── 10-project.toml
    └── 20-local.toml
```

Possible semantics, if `ci_bridge` ever needs configuration overlays:

- `config.toml` is required, contains centrally managed defaults, and explicitly declares any include glob.
- `config.d/*.toml` is optional only when selected through that declaration.
- The bridge, not the TOML parser, sorts fragments lexically.
- Files are merged in displayed order; later scalar/table keys may override earlier keys, but duplicate task IDs should be an error in the first schema rather than silently replacing executable behavior.
- Arrays and arrays-of-tables are replaced wholesale, not appended.
- The CLI provides `config show` (resolved config) and `config validate` so precedence is observable.
- Symlinks, path traversal, ownership/trust, and whether a downstream repo may add fragments must be an explicit security policy rather than an accidental consequence of globbing.
- A missing wildcard match may be allowed, while an explicitly named missing file should fail; nested includes need cycle detection and a fixed depth limit.

For example, the authority remains visible in the root file:

```toml
[bridge]
includes = ["config.d/*.toml"]
```

OpenSSH's implementation confirms two additional details behind this recommendation: an unmatched glob is non-fatal and recursive includes are capped at 16 levels in [`readconf.c`](https://github.com/openssh/openssh-portable/blob/master/readconf.c). OpenSSH also enforces owner/write-permission checks on user config and included files. In a CI checkout, repository-root containment plus a pinned trusted revision is more portable than copying those Unix ownership checks exactly.

### Local feasibility check

This pattern was tested against the existing `ghcr.io/ycpss91255-docker/toml-bridge:v0.1.0 --merge` rather than assumed:

- A base `config.toml`, then lexically caller-sorted `10-project.toml` and `20-local.toml`, produced a later-wins key-level table merge.
- A task's inherited `script` remained while a later fragment changed only its `timeout`.
- An array-of-tables was replaced wholesale by the later fragment.
- A named missing optional layer was skipped without failure.
- `toml-bridge` merges paths in the order supplied; it does **not** own directory glob discovery or lexical sorting. That responsibility must remain in `.ci_bridge`.

This proves that ordered multi-file merging is implementable with the current parser image. It does not prove that ordering is useful for the task registry, nor settle whether discovery should be explicit or automatic.

## Lessons from OpenSSH and Linux configuration architecture

The mature Linux patterns are valuable because they separate three concerns that are easy to conflate: **where configuration comes from**, **which source has authority**, and **how multiple values combine**. They do not, however, share one universal merge rule. `ci_bridge` should copy the separation and the tooling, not copy any one parser's semantics blindly.

### OpenSSH: explicit composition and context-specific matching

The OpenSSH client reads command-line options, then the user's config, then the system config, and normally uses the **first specified value** for a directive. That makes specific rules belong before general defaults. `Host` and `Match` sections apply settings only in a selected context, while `Include` is explicit, accepts globs, processes wildcard matches in lexical order, and may itself appear inside a conditional section ([OpenBSD `ssh_config(5)`](https://man.openbsd.org/ssh_config)).

Advantages worth preserving:

- The root file is an auditable entry point: extra files do nothing until an `Include` selects them.
- A deterministic glob order makes a directory of small fragments reproducible.
- Conditional sections let one shared configuration serve different targets without duplicating whole files.
- `ssh -G host` prints the effective configuration after evaluation, giving users an answer to “what will actually run?” ([OpenBSD `ssh(1)`](https://man.openbsd.org/ssh)).

Failure modes and lessons:

- “First value wins” is compact but counterintuitive to users expecting later overrides. It also means moving one line can silently change authority. `ci_bridge` should define precedence and per-field merge behavior in its own schema rather than inherit OpenSSH's rule accidentally.
- Conditional parsing can be multi-pass: hostname canonicalization may re-read the configuration, and `Match final` explicitly requests a final pass. That power increases debugging cost. The first `ci_bridge` schema should avoid implicit re-evaluation and environment-dependent matching.
- OpenSSH permits executable `Match exec` conditions and environment/token expansion. Those are inappropriate in centrally managed CI configuration: validation would execute or depend on untrusted state. Conditions should be declarative and allowlisted.
- OpenSSH's own warning that local-network matching is not trustworthy for security-sensitive settings illustrates a general rule: convenience context must not become an authorization boundary.
- OpenSSH treats configuration as executable-adjacent security input: its user config may not be writable by others, token expansion is explicitly the user's escaping responsibility, and its parser caps recursive includes at 16 levels ([OpenBSD `ssh_config(5)` files and tokens](https://man.openbsd.org/ssh_config), [OpenSSH `readconf.c`](https://github.com/openssh/openssh-portable/blob/master/readconf.c)). A repository checkout cannot rely on Unix ownership in the same way, so `ci_bridge` needs revision pinning, trust-class field permissions, repository-root containment, include-cycle detection, and a lower depth limit such as 8.

### systemd: ownership layers, drop-ins, and reversible overrides

systemd repeatedly uses a vendor/runtime/administrator hierarchy. Packages place defaults under `/usr/lib`; volatile overrides live under `/run`; persistent local policy lives under `/etc`. A higher-priority directory wins when two files have the same name. For many `*.conf.d` families, surviving distinct files are then processed in one lexical order across all directories; later scalar values override earlier values, while list-valued settings may accumulate. The documentation recommends numbered filename ranges so vendors and administrators have separate ordering space ([systemd's shared `*.conf.d` specification](https://github.com/systemd/systemd/blob/main/man/standard-conf.xml), [`homed.conf(5)` “Configuration Directories and Precedence”](https://www.freedesktop.org/software/systemd/man/latest/homed.conf.html)). `udev` rules and systemd-networkd use the same broad pattern: collective lexical order, same-name replacement by the higher-priority directory, and `/dev/null` masking ([`udev(7)` source manual](https://cgit.freedesktop.org/systemd/systemd/tree/man/udev.xml), [`systemd.netdev(5)`](https://www.freedesktop.org/software/systemd/man/systemd.netdev.html)).

Unit files add a targeted overlay: a main unit may be extended by `unit.type.d/*.conf` snippets. Drop-ins can apply at type, dash-truncated prefix, template, instance, or exact-unit specificity; this is powerful inheritance, but it also creates multiple places capable of changing one unit. Moreover, unit directives have schema-specific behavior: many list settings can be reset with an empty assignment, while dependency relations cannot simply be removed by a drop-in ([`systemd.unit(5)` source specification](https://github.com/systemd/systemd/blob/main/man/systemd.unit.xml)). systemd can therefore update a vendor unit without copying and owning the whole file, but only because each directive defines its combination semantics.

Not every `*.d` family is later-wins. `tmpfiles.d` resolves two lines targeting the same path in favor of the lexically earliest line and reports later conflicts; it also applies path and glob operations in a defined operational order ([`tmpfiles.d(5)` source specification](https://github.com/systemd/systemd/blob/main/man/tmpfiles.d.xml)). This counterexample is decisive: the directory convention defines discovery and ordering, not a universal merge algorithm.

`systemctl cat` presents a base unit and its drop-ins together, `systemd-analyze cat-config` shows configuration files and drop-ins, `systemd-delta` classifies local differences as masked, redirected, overridden, equivalent, or extended, and `systemd-analyze verify` performs offline validation ([`systemd-delta(1)`](https://www.freedesktop.org/software/systemd/man/latest/systemd-delta.html), [`systemd-analyze(1)` source manual](https://github.com/systemd/systemd/blob/main/man/systemd-analyze.xml), [`systemd` NEWS describing `systemctl cat`](https://cgit.freedesktop.org/systemd/systemd/tree/NEWS)). Applying changed unit files also requires an explicit manager reload, which prevents an edited file from being mistaken for already-active runtime state.

The architecture's strongest properties are:

1. **Ownership is encoded by location.** Vendor defaults and local policy are not co-edited, so upgrading the vendor layer does not erase local intent.
2. **Small overrides reduce forks.** A drop-in changes one concern instead of copying an entire managed definition that will drift.
3. **Override, disable, and remove are distinct.** A same-name higher layer replaces; a drop-in augments; a mask explicitly suppresses. These intentions are reviewable and reversible.
4. **Runtime and persistent changes are different layers.** `/run` can test a temporary override; reboot removes it. This is a useful operational model, although a Git repository should express temporary local state outside committed managed directories.
5. **Introspection is part of the design.** Layering is viable because systemd supplies commands to show the effective composition and the delta from shipped defaults.

The main costs are equally important:

- Two dimensions of precedence—directory priority and lexical filename order—are easy to misunderstand. Same-name replacement is not the same operation as later-key override.
- Merge behavior is type-specific. Scalars, lists, dependency sets, and executable command lists may have different reset/append semantics. A generic TOML deep merge cannot infer user intent safely.
- A low-precedence fragment can still run later lexically unless the precise family rules are understood. Numeric prefixes are a convention, not an authorization mechanism.
- Drop-ins can create “configuration at a distance”: the visible base file is not the runtime truth. Without `show`, `origin`, and `diff` commands, support and review become guesswork.
- Masking is intentionally stronger than disabling and can surprise an operator. `systemctl mask` prevents all activation and the manual tells users to use it with care ([`systemctl(1)`](https://www.freedesktop.org/software/systemd/man/latest/systemctl.html)). A CI equivalent needs an explicit reason and visible diagnostic, never an empty file with unexplained magic semantics.

### What `ci_bridge` should adopt

Use a catalog/selection split instead of an override stack:

```text
.ci_action/
└── catalog/
    ├── test.toml               # managed approved action
    └── docker-build.toml       # managed approved action
ci-project.toml                 # downstream selection + constrained bindings
```

- **Auto-discover the managed catalog:** `.ci_action/catalog/*.toml` is a documented program-owned discovery path. Sorting is only for reproducible diagnostics; filenames have no precedence.
- **Do not turn filename order into task semantics:** action IDs are globally unique and duplicate IDs fail. The downstream manifest selects actions or pipelines explicitly; dependencies in the resolved plan determine order.
- **Typed merge rules:** define each field as replace, append/set-union, or non-overridable in the schema. Treat duplicate task IDs or executable definitions as errors unless an explicit override operation exists.
- **Immutable managed base:** record the bridge/config version or digest used by a run. Repository scripts may vary, but they cannot replace managed commands, images, permissions, or release policy through a generic merge.
- **Constrained conditions:** initially allow stable facts such as action name or declared project profile. Do not allow shell expressions, secret-dependent branches, arbitrary environment interpolation, or network-derived authorization.
- **Safe rollback:** prefer version rollback of the managed bundle. If task suppression is later required, add an explicit `disabled = true` with a reason and provenance; do not imitate `/dev/null` or zero-byte masks in TOML.

### Required observability and validation contract

Catalog selection should not ship before these commands or equivalent behavior exist:

```text
ci-bridge catalog list      # installed approved actions and source digests
ci-bridge plan show         # fully resolved selected tasks and dependencies
ci-bridge plan explain X    # why task X exists and where its binding came from
ci-bridge config diff       # resolved config versus managed defaults
ci-bridge config validate   # schema, paths, bindings, cycles, unsupported keys
```

Validation must happen before any task script executes. It should reject unknown keys, unknown actions, missing required bindings, duplicate action IDs, dependency cycles, absolute or escaping paths, symlink escapes after canonicalization, unsupported schema versions, and downstream fields outside the allowlist. Diagnostics should name the action, both conflicting catalog files when applicable, and the relevant key.

### Recommendation for the current design

Adopt the **Linux separation of installed capability from activation**, not its drop-in override machinery. `.ci_action/catalog/*.toml` is the centrally installed capability set; `ci-project.toml` activates approved actions and binds them to downstream-owned scripts. This is closer to systemd's distinction between installed units and enablement/presets than to `conf.d` overlays. Do not adopt OpenSSH's first-value-wins rule or systemd's lexical override precedence.

For the first demo, keep every `.ci_action/catalog` file centrally managed. The repo-root `ci-project.toml` is a typed, allowlisted selection and binding manifest. It may select an approved action and point a logical binding such as `test` to a repo-relative script; it may not supply raw commands, images, permissions, secrets, or release policy.

## Alignment with `ycpss91255-docker/base`

This section was checked against `base` commit [`669d2cf8`](https://github.com/ycpss91255-docker/base/tree/669d2cf8af227ca65d218c8b568ac1847cffed68). The important alignment target is not its current GitHub-only workflow syntax. It is the product contract and the boundary between shared machinery and downstream-owned content.

### Invariants that should carry over

1. **Never fail silently.** `base` requires missing or incompatible configuration to fail before real work, and treats a silently green shared foundation as a product failure ([PRD lines 124–136](https://github.com/ycpss91255-docker/base/blob/669d2cf8af227ca65d218c8b568ac1847cffed68/doc/PRD.md#L124-L136)). Its reusable-worker preflight implements this as a host-testable script while keeping workflow wiring thin, rejects unknown requirement kinds, and refuses an empty manifest rather than treating “nothing checked” as success ([`preflight.sh` lines 2–15](https://github.com/ycpss91255-docker/base/blob/669d2cf8af227ca65d218c8b568ac1847cffed68/script/ci/preflight.sh#L2-L15), [lines 98–161](https://github.com/ycpss91255-docker/base/blob/669d2cf8af227ca65d218c8b568ac1847cffed68/script/ci/preflight.sh#L98-L161)). For `ci_bridge`, config parsing, schema/version checking, task lookup, downstream-script existence, and capability checks must all finish before the first task executes.

2. **One source, propagated; downstream is a thin caller.** `base` fixes the property—one source for shared logic and thin downstream entrypoints—while explicitly treating subtree vendoring as a replaceable mechanism ([PRD lines 222–243](https://github.com/ycpss91255-docker/base/blob/669d2cf8af227ca65d218c8b568ac1847cffed68/doc/PRD.md#L222-L243)). This directly supports the intended ownership: `.ci_bridge/`, `.ci_action/`, `.github/`, and `.gitlab/` hold centrally managed machinery; the downstream selects tasks and owns its project scripts and test data. How the four directories are distributed should remain a separate decision.

3. **Fail-safe defaults and explicit escape hatches.** `base` defaults toward safety where convenience can silently break a deployment ([PRD lines 162–173](https://github.com/ycpss91255-docker/base/blob/669d2cf8af227ca65d218c8b568ac1847cffed68/doc/PRD.md#L162-L173)); it also requires every escape hatch to be explicit, named, and to record why it was taken ([PRD lines 702–719](https://github.com/ycpss91255-docker/base/blob/669d2cf8af227ca65d218c8b568ac1847cffed68/doc/PRD.md#L702-L719)). Applied here: unknown actions, unsupported matrix declarations, missing scripts, duplicate task owners, or invalid paths fail closed. A downstream override must use a named manifest field, never an implicit environment variable or silent fallback.

4. **One rule has one owner and many entry points.** `base` states that a rule is implemented once and all local/CI callers reach the same implementation; otherwise the copies will drift ([PRD lines 648–673](https://github.com/ycpss91255-docker/base/blob/669d2cf8af227ca65d218c8b568ac1847cffed68/doc/PRD.md#L648-L673)). GitHub and GitLab adapters should therefore invoke the same `.ci_bridge` command, and local validation should invoke it too. Platform YAML may supply platform facts, but must not reimplement task selection or validation.

5. **A zero-result check is not automatically success.** `base` distinguishes “zero violations” from “zero files examined” and makes an empty scan a refusal ([PRD lines 632–646](https://github.com/ycpss91255-docker/base/blob/669d2cf8af227ca65d218c8b568ac1847cffed68/doc/PRD.md#L632-L646)). `ci_bridge` needs the same convention: a requested pipeline that resolves to zero tasks, a task glob that matches nothing, or an adapter conformance scan that finds no adapters must fail unless an explicit empty operation exists in the schema.

When two good properties conflict, `base` ranks downstream correctness first, loud/early failure second, one owner per rule third, and convenience last ([PRD lines 770–801](https://github.com/ycpss91255-docker/base/blob/669d2cf8af227ca65d218c8b568ac1847cffed68/doc/PRD.md#L770-L801)). This is a useful decision rule for the bridge: a shorter manifest does not justify ambiguous task meaning, a silent skip, or logic duplicated into both adapters.

### Configuration rules to reuse

`base` has already settled the relevant TOML behavior. Human-edited infrastructure configuration is TOML; scalar keys merge by key, while arrays of tables replace as a whole rather than append or merge by index ([ADR-37 lines 66–76](https://github.com/ycpss91255-docker/base/blob/669d2cf8af227ca65d218c8b568ac1847cffed68/doc/adr/00000037-toml-config-format-unification.md#L66-L76), [lines 131–143](https://github.com/ycpss91255-docker/base/blob/669d2cf8af227ca65d218c8b568ac1847cffed68/doc/adr/00000037-toml-config-format-unification.md#L131-L143)). The parser runs in a pinned container because the host contract must not acquire an uncontrolled Python/binary dependency ([ADR-37 lines 154–169](https://github.com/ycpss91255-docker/base/blob/669d2cf8af227ca65d218c8b568ac1847cffed68/doc/adr/00000037-toml-config-format-unification.md#L154-L169)). `ci_bridge` should reuse `toml-bridge` rather than introduce a second TOML interpretation.

The existing layer convention is also useful but should be translated carefully: shipped default, committed repo configuration, then a gitignored operator-local override ([ADR-25 lines 52–71](https://github.com/ycpss91255-docker/base/blob/669d2cf8af227ca65d218c8b568ac1847cffed68/doc/adr/00000025-per-worktree-setup-conf-local-override.md#L52-L71)). In `ci_bridge`, centrally managed action definitions are not the same trust class as a downstream task-selection manifest. They should not be merged as unrestricted peers. The downstream file may select known tasks and, later, map an allowlisted action to a repo-relative script; it must not replace centrally owned executable definitions, images, permissions, or release policy.

This also resolves the `config.d` question: `base` gives no reason to make lexical filename order part of task planning. Action files should form a registry whose task IDs are unique; pipeline config explicitly selects tasks and expresses dependencies. File discovery may be automatic and deterministically sorted for reproducible diagnostics, but duplicate task IDs are an error rather than “later file wins.”

### Script, content, and CI boundaries

`base` explicitly separates generic tooling from per-repository content: the shared scripts have one source, while tests, configuration, Dockerfile, and Compose content remain owned by each repo ([ADR-11 lines 134–151](https://github.com/ycpss91255-docker/base/blob/669d2cf8af227ca65d218c8b568ac1847cffed68/doc/adr/00000011-just-command-model-full-namespace.md#L134-L151)). Its test runner is a dispatcher with one driver per tool, and selects work from content present in the repository ([ADR-11 lines 186–213](https://github.com/ycpss91255-docker/base/blob/669d2cf8af227ca65d218c8b568ac1847cffed68/doc/adr/00000011-just-command-model-full-namespace.md#L186-L213)). The corresponding `ci_bridge` boundary is:

```text
.ci_bridge/          shared dispatcher, validation, stable exit behavior
.ci_action/          shared action definitions and action-to-driver mapping
.github/, .gitlab/   thin platform adapters only
repo test/, scripts/ downstream-owned, locally runnable content
repo manifest        downstream-owned selection and constrained path mapping
```

The downstream test script must be runnable from the repository root without GitHub/GitLab variables. The adapter may normalize platform metadata into an explicit input contract, but `.ci_action` must not contain the downstream's test fixtures or project-specific assertions.

`base` also provides a concrete precedent for putting a shared CI decision in a script rather than duplicating it across jobs: every consuming job calls one image-provisioning script, and differences between callers are reduced to one explicit mode word ([ADR-33 lines 43–68](https://github.com/ycpss91255-docker/base/blob/669d2cf8af227ca65d218c8b568ac1847cffed68/doc/adr/00000033-ci-image-provisioning-is-a-script-not-a-job.md#L43-L68)). `ci_bridge` should follow this for task resolution, matrix expansion, config validation, and result normalization.

### Validation and portability conventions

The bridge should reuse these `base` conventions:

- **Guard clauses first:** validate, reject, return before task execution ([PRD lines 596–612](https://github.com/ycpss91255-docker/base/blob/669d2cf8af227ca65d218c8b568ac1847cffed68/doc/PRD.md#L596-L612)).
- **Derive, do not maintain rosters:** discover action definitions and adapter jobs from the tree, then assert the derived population; do not keep a second list that can go stale ([PRD lines 614–630](https://github.com/ycpss91255-docker/base/blob/669d2cf8af227ca65d218c8b568ac1847cffed68/doc/PRD.md#L614-L630)).
- **Fail closed on unknown platform state:** `base` classifies runner eligibility from `runs-on`, and anything it cannot prove safe remains guarded ([ADR-26 lines 50–86](https://github.com/ycpss91255-docker/base/blob/669d2cf8af227ca65d218c8b568ac1847cffed68/doc/adr/00000026-self-hosted-eligibility-is-a-static-property-of-runs-on.md#L50-L86)). The bridge should similarly reject an unknown platform capability instead of guessing.
- **Pin the execution toolchain:** `base` pins `just` so local, container, and CI invocation behave the same ([README lines 38–55](https://github.com/ycpss91255-docker/base/blob/669d2cf8af227ca65d218c8b568ac1847cffed68/README.md#L38-L55)). The bridge image/runtime and schema version need the same pinning discipline.
- **Pin managed source immutably:** `base` rejects a moving `latest` ref for build-time dependencies because the same downstream commit could otherwise execute different code with no audit trail ([ADR-2 lines 43–48](https://github.com/ycpss91255-docker/base/blob/669d2cf8af227ca65d218c8b568ac1847cffed68/doc/adr/00000002-no-latest-tag.md#L43-L48), [lines 69–77](https://github.com/ycpss91255-docker/base/blob/669d2cf8af227ca65d218c8b568ac1847cffed68/doc/adr/00000002-no-latest-tag.md#L69-L77)). A distributed bridge/catalog bundle should likewise record an immutable version or digest.
- **Keep derived documentation out of hand-maintained prose:** intent and rationale belong in docs; task/action inventories should be generated by `ci-bridge list` from the actual config ([PRD lines 352–377](https://github.com/ycpss91255-docker/base/blob/669d2cf8af227ca65d218c8b568ac1847cffed68/doc/PRD.md#L352-L377)).

### Terminology to reuse

Use the same semantic split as `base`: **shared tooling** versus **downstream repo content**, a **thin caller/adapter**, a **single source of truth**, a **caller contract**, and **managed** versus **repo-owned** paths. For this project, add precise terms rather than overloading “config”:

- **Action definition:** centrally owned description of one reusable capability.
- **Task selection manifest:** downstream-owned declaration of which approved actions this repo runs.
- **Project script:** downstream-owned, locally runnable implementation or hook invoked by an action.
- **Platform adapter:** `.github/` or `.gitlab/` wiring that supplies platform facts and calls the portable bridge.
- **Resolved plan:** validated task graph/matrix produced before execution; the equivalent of an effective-configuration view.

The resulting governing invariant for `ci_bridge` should be: **one validated resolved plan drives local, GitHub, and GitLab execution; adapters may differ in platform plumbing, but not in task meaning.**

## Implications for the intended trust model

The phrase “we manage all four directories” needs a machine-checkable definition. Merely placing files under dot-directories does not prevent a downstream maintainer from changing them. A later distribution design must choose among copied-and-reviewed files, pinned remote references, or generated files with a drift check.

Regardless of distribution mechanism:

- `.github/` and `.gitlab/` should own platform triggers, permissions, runner selection, cache, artifacts, and secrets.
- `.ci_bridge/` should own config discovery, schema validation, task selection, path safety, process execution, and stable exit codes.
- `.ci_action/` should describe approved task behavior; it should not contain downstream test data.
- Downstream scripts and test data should remain at repository-root-relative paths so the exact scripts can be run locally.
- Repository-provided paths must be resolved under the checked-out repository root, reject traversal and unsafe symlink escapes, and be passed as arguments rather than evaluated shell text.

The official platform mechanisms reinforce the need for version pinning. GitHub documents SHA pinning for reusable workflows, while GitLab recommends a commit SHA or released component version and warns against moving targets such as `latest` ([GitHub](https://docs.github.com/en/actions/concepts/workflows-and-actions/reusing-workflow-configurations), [GitLab](https://docs.gitlab.com/ci/components/)).

## Q6: configurable downstream script paths

The deferred “repo-root manifest can map an approved action name to a project-specific script path” should be a GitHub issue now because it is a concrete, independently deliverable feature with security and compatibility acceptance criteria. It should not be silently buried in the eventual config implementation.

Suggested issue:

> **Support a constrained downstream script-path manifest**
>
> Allow a repository-root manifest to map approved action IDs such as `test` to repo-relative executable paths. Keep `.ci_action` centrally managed. Validate the schema, reject absolute paths, `..`, and symlink escapes, never evaluate command strings, expose the resolved mapping, and preserve fixed default paths when no mapping exists.

An ADR is also appropriate **after** the grilling session settles precedence and trust ownership, because those are durable architectural decisions. The issue tracks implementation; the ADR records why downstream customization is constrained rather than arbitrary.

## Recommended next design decision

The ownership question is now sufficiently constrained: central maintainers author the action catalog; downstream maintainers author only `ci-project.toml` and project scripts. The next decision is the first manifest contract:

> **Which bindings does each approved action require, and which downstream fields are selectable?**

Recommended first slice: one `test` action with a required `script` binding to a repo-relative executable, plus a single sequential `ci` pipeline selecting it. Keep raw command text, images, permissions, secrets, arbitrary environment injection, and matrix definitions out of the downstream schema. This is small enough to validate locally while preserving the final architecture.
