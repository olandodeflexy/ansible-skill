# CI/CD Workflows

Detail for the `CI/CD` section in SKILL.md and the `Blast radius` routing-table category (gate side).

## Pipeline Stages

| Stage | Runs | Fails if |
|-------|------|----------|
| 1. Lint | `ansible-lint`, `yamllint` | Any rule violation |
| 2. Syntax check | `ansible-playbook --syntax-check site.yml` | Parse or module-name error |
| 3. Unit / scenario tests | Molecule (roles) or `ansible-test units/sanity` (collections) | Any failure on any matrix leg |
| 4. Staged `--check --diff` | `ansible-playbook --check --diff --limit=staging` | Any unexpected diff; artifact uploaded for review |
| 5. Manual approval | GitHub / GitLab environment gate | Reviewer rejects the staged diff |
| 6. Apply | Re-runs the *same reviewed plan* — does **not** re-plan | Any task fails at apply |

Rules:

- ❌ Skip lint on `main`-branch-only CI → ✅ Run on every PR; lint catches regressions before review time is spent.
- ❌ Let stage 6 re-plan instead of applying the reviewed diff → ✅ Store the `--check --diff` artifact from stage 4 and use it as the source of truth; re-planning means the human approved one diff and a different one ran.
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
      - run: pip install ansible-core==2.17.5 ansible-lint==24.7.0 yamllint==1.35.1
      - run: ansible-galaxy collection install -r requirements.yml
      - run: ansible-lint
      - run: yamllint .

  molecule:
    needs: lint
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        role: [nginx-site, postgresql-replica]
        platform: [rockylinux9, ubuntu2204]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install ansible-core==2.17.5 molecule[docker]==24.7.0 ansible-lint==24.7.0
      - run: molecule test -s ${{ matrix.platform }}
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
      - run: pip install ansible-core==2.17.5
      - run: ansible-galaxy collection install -r requirements.yml
      - name: Run --check --diff against staging
        env:
          ANSIBLE_VAULT_PASSWORD_FILE: /tmp/vp
        run: |
          echo "${{ secrets.VAULT_PASSWORD_STAGING }}" > /tmp/vp
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
  - staging-check
  - apply

default:
  image: registry.gitlab.com/ansible/creator-ee:v24.7.0
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
  parallel:
    matrix:
      - ROLE: [nginx-site, postgresql-replica]
        PLATFORM: [rockylinux9, ubuntu2204]
  script:
    - cd roles/$ROLE
    - molecule test -s $PLATFORM
  services:
    - name: docker:dind
      alias: docker

staging-check:
  stage: staging-check
  needs: [molecule]
  environment:
    name: staging
    action: verify
  rules:
    - if: $CI_MERGE_REQUEST_TARGET_BRANCH_NAME == "main"
  script:
    - echo "$VAULT_PASSWORD_STAGING" > /tmp/vp
    - ANSIBLE_VAULT_PASSWORD_FILE=/tmp/vp
      ansible-playbook -i inventories/staging playbooks/site.yml
      --check --diff --limit staging | tee staging-diff.txt
  artifacts:
    paths: [staging-diff.txt]
    expire_in: 30 days

apply-prod:
  stage: apply
  needs: [staging-check]
  environment:
    name: production
    action: start
  when: manual
  rules:
    - if: $CI_COMMIT_BRANCH == "main"
  script:
    - echo "$VAULT_PASSWORD_PROD" > /tmp/vp
    - ANSIBLE_VAULT_PASSWORD_FILE=/tmp/vp
      ansible-playbook -i inventories/prod playbooks/site.yml --limit prod
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
| Approved-diff hash matches apply | Store diff SHA in staging-check, compare at apply | Plan drift between approval and apply |
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
- ❌ Compare apply-time plan to the approved diff only by visual inspection → ✅ Compute a hash of the diff and compare programmatically.

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
- ❌ Re-plan at apply time → ✅ Apply the approved diff; drift detection lives elsewhere.
