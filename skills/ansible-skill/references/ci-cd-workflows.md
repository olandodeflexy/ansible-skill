# CI/CD Workflows

Detail for the `CI/CD` section in SKILL.md and the `Blast radius` routing-table category (gate side).

## Pipeline Stages

| Stage | Runs | Fails if |
|-------|------|----------|
| 1. Lint | `ansible-lint`, `yamllint` | Any rule violation |
| 2. Syntax check | `ansible-playbook --syntax-check site.yml` | Parse or module-name error |
| 3. Unit / scenario tests | Molecule (roles) or `ansible-test units/sanity` (collections) | Any failure on any matrix leg |
| 4. Staged `--check --diff` | `ansible-playbook --check --diff --limit=staging` | Any unexpected diff; artifact uploaded for review |
| 5. Manual approval | GitHub / GitLab environment gate | Reviewer rejects the staged `--check --diff` output |
| 6. Apply | Checks out the **same commit + inventory** approved in stage 5, optionally re-runs `--check --diff` against live state to detect drift since approval, then runs `ansible-playbook` (without `--check`) | Any task fails at apply, or the pre-apply drift check diverges from the approved diff |

**Important:** unlike Terraform's `plan`/`apply`, Ansible has no reusable plan artifact. `--check --diff` output is **review evidence**, not an executable plan. The apply stage must re-evaluate current state against the playbook; the controls below keep staging approval meaningful despite that.

Rules:

- ❌ Skip lint on `main`-branch-only CI → ✅ Run on every PR; lint catches regressions before review time is spent.
- ❌ Treat the stage-4 `--check --diff` output as a reusable "plan" that stage 6 can replay → ✅ Pin the reviewed commit SHA + inventory revision, and optionally re-run `--check --diff` as the first step of stage 6 and compare its hash/content to the approved artifact; diverge → abort.
- ❌ Conflate staging and prod into one pipeline → ✅ Separate environments, separate approval gates.
- ❌ Auto-approve prod on successful staging → ✅ Human review the staging diff before any prod stage.

## GitHub Actions Template

```yaml
# .github/workflows/ansible.yml
name: Ansible CI

on:
  pull_request:
    paths:
      - "playbooks/**"
      - "roles/**"
      - "inventories/**"
      - "requirements.yml"

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install 'ansible-core>=2.20,<2.21' ansible-lint==24.7.0 yamllint==1.35.1
      - run: ansible-galaxy collection install -r requirements.yml --collections-path ./collections
      - run: echo "ANSIBLE_COLLECTIONS_PATH=./collections" >> $GITHUB_ENV
      - run: ansible-lint
      - run: yamllint .

  molecule:
    needs: lint
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      # `molecule test -s <NAME>` selects a SCENARIO directory under molecule/<NAME>/.
      # If you need per-distro coverage, create one scenario per distro
      # (molecule/rockylinux9/, molecule/ubuntu2204/, …) and matrix over the
      # scenario names — `-s` does not select a platform inside a scenario.
      matrix:
        role: [nginx_site, postgresql_replica]
        scenario: [rockylinux9, ubuntu2204]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install 'ansible-core>=2.20,<2.21' molecule[docker]==24.7.0 ansible-lint==24.7.0
      - run: molecule test -s ${{ matrix.scenario }}
        working-directory: roles/${{ matrix.role }}

  staging-check:
    needs: molecule
    if: github.event.pull_request.base.ref == 'main'
    runs-on: ubuntu-latest
    environment: staging-check
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install 'ansible-core>=2.20,<2.21'
      - run: ansible-galaxy collection install -r requirements.yml --collections-path ./collections
      - run: echo "ANSIBLE_COLLECTIONS_PATH=./collections" >> $GITHUB_ENV
      - name: Run --check --diff against staging
        shell: bash
        run: |
          set -eo pipefail            # `tee` would otherwise mask a non-zero ansible-playbook exit
          umask 077                   # any tmpfiles below default to mode 0600
          vp="$(mktemp)"
          trap 'shred -u "$vp" 2>/dev/null || rm -f "$vp"' EXIT
          printf '%s' "${{ secrets.VAULT_PASSWORD_STAGING }}" > "$vp"
          export ANSIBLE_VAULT_PASSWORD_FILE="$vp"
          ansible-playbook -i inventories/staging playbooks/site.yml \
            --check --diff --limit staging \
            | tee staging-diff.txt
      - uses: actions/upload-artifact@v4
        with:
          name: staging-diff
          path: staging-diff.txt
          retention-days: 30
```

Rules:

- ❌ Pin `actions/checkout@main` or any floating ref → ✅ Pin by tag (`@v4`) or SHA; supply-chain risk.
- ❌ Run everything in one monster job → ✅ Split by stage so a lint failure aborts before expensive Molecule runs.
- ❌ Put vault passwords in `env:` directly → ✅ Write to a tmpfile and reference via `ANSIBLE_VAULT_PASSWORD_FILE`; env vars show up in job inspection.
- ❌ Skip artifact upload of the `--check --diff` output → ✅ Required evidence for the approval gate reviewer.

## GitLab CI Template

```yaml
# .gitlab-ci.yml
stages:
  - lint
  - test
  - staging-check    # runs on MR pipelines targeting main — gate before merge
  - prod-check       # runs on main-branch pipelines after merge — pre-apply drift check
  - apply

default:
  # Pin by digest for reproducibility/supply-chain safety.
  image: quay.io/ansible/creator-ee@sha256:<approved-digest>
  cache:
    key: "$CI_COMMIT_REF_SLUG-venv"
    paths:
      - .venv/

variables:
  ANSIBLE_FORCE_COLOR: "1"

lint:
  stage: lint
  script:
    - ansible-lint
    - yamllint .

molecule:
  stage: test
  needs: [lint]
  # `molecule test -s <NAME>` selects a SCENARIO directory (molecule/<NAME>/),
  # not a platform inside one scenario; matrix over scenario names.
  parallel:
    matrix:
      - ROLE: [nginx_site, postgresql_replica]
        SCENARIO: [rockylinux9, ubuntu2204]
  variables:
    # docker:dind needs an explicit endpoint + TLS certs path; without these
    # Molecule defaults to /var/run/docker.sock and fails on shared runners.
    DOCKER_HOST: tcp://docker:2376
    DOCKER_TLS_CERTDIR: "/certs"
    DOCKER_TLS_VERIFY: "1"
    DOCKER_CERT_PATH: "/certs/client"
  services:
    - name: docker:dind
      alias: docker
  # The runner must be configured with `privileged = true` in config.toml for
  # the docker:dind service to start. Document this requirement in your runner
  # provisioning; many shared / managed GitLab runners disallow privileged.
  script:
    - cd roles/$ROLE
    - molecule test -s $SCENARIO

staging-check:
  stage: staging-check
  needs: [molecule]
  environment:
    name: staging
    action: verify
  rules:
    - if: $CI_MERGE_REQUEST_TARGET_BRANCH_NAME == "main"   # MR gate before merge
  script:
    - set -eo pipefail
    - umask 077
    - vp="$(mktemp)"; trap 'shred -u "$vp" 2>/dev/null || rm -f "$vp"' EXIT
    - printf '%s' "$VAULT_PASSWORD_STAGING" > "$vp"
    - export ANSIBLE_VAULT_PASSWORD_FILE="$vp"
    - export ANSIBLE_COLLECTIONS_PATH=./collections
    - ansible-galaxy collection install -r requirements.yml --collections-path ./collections
    - ansible-playbook -i inventories/staging playbooks/site.yml --check --diff --limit staging | tee staging-diff.txt
  artifacts:
    paths: [staging-diff.txt]
    expire_in: 30 days

prod-check:
  stage: prod-check
  needs: [molecule]
  environment:
    name: production
    action: verify
  rules:
    - if: $CI_COMMIT_BRANCH == "main"                     # post-merge, pre-apply drift check
  script:
    - set -eo pipefail
    - umask 077
    - vp="$(mktemp)"; trap 'shred -u "$vp" 2>/dev/null || rm -f "$vp"' EXIT
    - printf '%s' "$VAULT_PASSWORD_PROD" > "$vp"
    - export ANSIBLE_VAULT_PASSWORD_FILE="$vp"
    - export ANSIBLE_COLLECTIONS_PATH=./collections
    - ansible-galaxy collection install -r requirements.yml --collections-path ./collections
    - ansible-playbook -i inventories/prod playbooks/site.yml --check --diff --limit prod | tee prod-diff.txt
  artifacts:
    paths: [prod-diff.txt]
    expire_in: 30 days

apply-prod:
  stage: apply
  needs:
    - job: prod-check
      artifacts: true                                     # pulls prod-diff.txt from the approved run
  environment:
    name: production
    action: start
  when: manual                                            # human approval gate after reviewing prod-diff.txt
  rules:
    - if: $CI_COMMIT_BRANCH == "main"
  script:
    - set -eo pipefail
    - umask 077
    - vp="$(mktemp)"; trap 'shred -u "$vp" 2>/dev/null || rm -f "$vp"' EXIT
    - printf '%s' "$VAULT_PASSWORD_PROD" > "$vp"
    - export ANSIBLE_VAULT_PASSWORD_FILE="$vp"
    - export ANSIBLE_COLLECTIONS_PATH=./collections
    - ansible-galaxy collection install -r requirements.yml --collections-path ./collections
    # Pre-apply drift check: re-run --check --diff against live state and abort
    # if it diverges from the artifact a human approved at prod-check time.
    - ansible-playbook -i inventories/prod playbooks/site.yml --check --diff --limit prod | tee prod-diff-now.txt
    - |
      if ! diff -q prod-diff.txt prod-diff-now.txt >/dev/null; then
        echo "::error:: live diff diverges from approved prod-check artifact; aborting apply"
        diff -u prod-diff.txt prod-diff-now.txt || true
        exit 1
      fi
    # Approved diff still matches live state — apply.
    - ansible-playbook -i inventories/prod playbooks/site.yml --limit prod
```

Rules:

- ❌ Share a single runner for staging and prod stages → ✅ Separate tagged runners or isolated projects; blast-radius containment.
- ❌ `when: manual` without a protected environment → ✅ Any user can trigger; use `environment:` with protected rules.

## Blast Radius Gates

Controls that make a production play safer — enforce in CI, not just convention.

| Gate | Enforcement | What it catches |
|------|-------------|-----------------|
| `--limit` required | Linter step `grep -q -- '--limit' ci/playbook-wrappers/*.sh` | Unbounded play against whole inventory |
| `serial:` mandatory for `hosts: all` | YAML check in CI | Whole-fleet synchronous rollout |
| Pre-apply drift check | At stage 6, re-run `--check --diff` against live state and fail if the new diff diverges from the approved stage-4 artifact (compare by hash or content) | Infrastructure changes that landed between staging approval and apply |
| Pinned commit + inventory at apply | Apply job checks out the exact commit SHA approved in stage 5; inventory plugin snapshots pinned | Prevents apply from picking up later main-branch commits or inventory mutations |
| Fleet size threshold | If `--list-hosts` output > N, require extra reviewer | Catches mis-scoped limits |
| `check_mode: no` audit | Grep codebase for `check_mode: no`; block PR if added without justification comment | Silent mutations on dry-run |

```yaml
# .github/workflows/blast-radius-gate.yml (excerpt)
- name: Enforce --limit in prod wrappers
  run: |
    for f in ci/playbook-wrappers/prod/*.sh; do
      grep -q -- '--limit' "$f" || {
        echo "::error file=$f::missing --limit"; exit 1; }
    done

- name: Enforce serial on fleet-wide plays
  run: |
    python3 ci/checks/require_serial.py playbooks/site.yml
```

Rules:

- ❌ Rely on "the reviewer will check" for `--limit` → ✅ Automate; reviewers drift, CI doesn't.
- ❌ Allow `check_mode: no` without a justification comment → ✅ PR comment required: why this task bypasses dry-run.
- ❌ Assume the apply run will reproduce the stage-4 `--check --diff` exactly → ✅ Re-run `--check --diff` at the start of the apply job against live state, compare hash/content to the approved stage-4 artifact; diverge → abort and request re-review.

## Secret Handling in CI

| Method | Use | Caveat |
|--------|-----|--------|
| OIDC → cloud secret store | Preferred for AWS/GCP/Azure — ephemeral creds per job | Requires trust relationship setup; one-time per provider |
| Encrypted secrets (GH / GL) | Fallback when OIDC not available | Rotation is manual; long-lived |
| Vault-password-file injection | `ANSIBLE_VAULT_PASSWORD_FILE` pointing at tmpfile written from a secret | Never via `env:`; env vars leak in job inspection |
| External-secret lookup plugins | HashiCorp Vault, 1Password, etc. via `lookup()` | Controller needs network access + auth to backend |
| Masked logs | Provider-specific masking of known secret values | Last line of defense; don't rely on it alone |

Rules:

- ❌ Put raw secrets in `env:` → ✅ Write to a tmpfile outside logs, reference by path.
- ❌ Use long-lived cloud creds in CI → ✅ OIDC federation gives per-job short-lived creds.
- ❌ Rotate secrets only on incident → ✅ Scheduled rotation, alert on staleness.
- ❌ Echo `$SECRET` for debugging → ✅ Use mask checkers; `echo "***"` at best.
- ❌ Store the vault password in the repo for CI "convenience" → ✅ Always pull from the provider's secret store at runtime.

### LLM Mistake Checklist

- ❌ Suggest a pipeline that applies without a separate staging `--check --diff` stage → ✅ Always stage 4 before stage 6.
- ❌ Pin GitHub Actions by branch (`@main`) → ✅ Pin by tag or SHA.
- ❌ Put vault passwords in `env:` blocks → ✅ Tmpfile + `ANSIBLE_VAULT_PASSWORD_FILE`.
- ❌ Combine lint + tests in one job → ✅ Fail fast; lint is seconds, Molecule is minutes.
- ❌ Allow prod apply without a protected environment → ✅ `environment:` + required reviewers.
- ❌ Skip artifact upload of the staged diff → ✅ Required evidence for the reviewer.
- ❌ Promise that Ansible can replay a stored `--check --diff` like Terraform's plan artifact → ✅ Pin the approved commit + inventory, re-run `--check --diff` at the start of apply against live state, compare to the approved artifact before proceeding.
