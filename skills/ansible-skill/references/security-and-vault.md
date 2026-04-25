# Security & Vault

Detail for the `Secret exposure` routing-table category.

## Vault Key Management

| Scale | Strategy | Tool | When to pick |
|-------|----------|------|--------------|
| Single dev, single key | Vault password file | `--vault-password-file ~/.vault_pass` | Solo projects, never for teams |
| Per-environment keys | Vault-id with dev/stage/prod IDs | `--vault-id dev@prompt --vault-id prod@file` | Standard team setup |
| No vault files on disk | Vault-id + system keyring | `--vault-id prod@keychain.sh` (custom script) | Laptops where keyring is trusted |
| External KMS-backed | Vault-id + KMS lookup script | Script returns decrypted key from AWS KMS / Vault Transit / GCP KMS | Regulated environments |
| Pre-decrypted secrets | External secret backend (HashiCorp Vault, AWS SM, 1Password) via lookup | Backend-specific lookup, e.g. Vault KV v2: `lookup('community.hashi_vault.vault_kv2_get', ...)` | Secrets managed outside Ansible entirely |

```ini
# ansible.cfg
[defaults]
vault_identity_list = dev@~/.vault-dev, prod@~/.vault-prod-kms.sh
```

```yaml
# inventories/prod/group_vars/all.yml
db_password: !vault |
  $ANSIBLE_VAULT;1.2;AES256;prod
  66386439653...
```

Rules:

- ❌ Commit a vault password file to git → ✅ `.gitignore` the key files and mount them from secrets stores at run time.
- ❌ One shared vault key across dev/stage/prod → ✅ Separate vault-ids per env; a dev compromise shouldn't touch prod.
- ❌ `ansible-vault encrypt` the whole file when only one value is secret → ✅ `ansible-vault encrypt_string` to encrypt individual values inline; leaves the rest of the file diffable.
- ❌ Rotate vault keys by re-encrypting in place → ✅ `ansible-vault rekey --new-vault-id new@file` and update vault-id references in one coordinated commit.
- ❌ Use `--ask-vault-pass` in CI → ✅ Inject vault password via `ANSIBLE_VAULT_PASSWORD_FILE` pointing at a file written by the runner's secret-fetching step.

## no_log Patterns

| Situation | `no_log: true` needed? | Why |
|-----------|------------------------|-----|
| Module arg contains a secret string | Yes | Module invocation logged in default verbosity |
| `register:` on a task returning a secret | Yes on the register target, and on the debug task | Both the task and any later `debug: var=` print it |
| Loop over a list of secrets (`loop:`) | Yes | Each iteration logs the `item`; without `no_log`, loop leaks every value |
| Secret only in `environment:` block | Yes | Env vars logged at task start when `-vv` |
| Template pulling secrets in | Yes on the template task | Template result visible in diff mode |
| Informational task reading a public value | No | Don't overuse — `no_log` also hides failure details |

```yaml
- name: Create DB user
  community.postgresql.postgresql_user:
    name: appuser
    password: "{{ db_password }}"
  no_log: true

- name: Rotate API tokens
  ansible.builtin.uri:
    url: https://api.example.com/tokens/rotate
    method: POST
    headers:
      Authorization: "Bearer {{ api_token }}"
  register: rotation
  no_log: true
```

Rules:

- ❌ Set `no_log: true` on a play-wide level → ✅ Scope to specific tasks; play-level hides every failure.
- ❌ `loop:` over secrets with `no_log: false` → ✅ Every iteration logs the item; always `no_log: true` for secret loops.
- ❌ `register:` a secret-bearing task without `no_log: true`, then later `debug: var=result` → ✅ Mark the register target no_log *and* avoid debugging registered values that contain secrets.
- ❌ `no_log: "{{ debug_mode }}"` to "allow toggling" → ✅ Static `true`; someone will set `debug_mode: true` for a real debug session and leak secrets.

## External Secret Backends

| Backend | Lookup plugin | Collection | Auth |
|---------|---------------|------------|------|
| HashiCorp Vault (KV v2) | `community.hashi_vault.vault_kv2_get` (preferred for KV v2) or `community.hashi_vault.vault_read` (lower-level, returns the raw API envelope) | `community.hashi_vault` | `VAULT_ADDR`, `VAULT_TOKEN` / Kubernetes service account / AWS IAM |
| AWS Secrets Manager | `amazon.aws.secretsmanager_secret` | `amazon.aws` | IAM role on controller or EE |
| 1Password | `community.general.onepassword` | `community.general` | `op signin` session token |
| CyberArk Conjur | `cyberark.conjur.conjur_variable` | `cyberark.conjur` | Conjur host identity + api key |
| Azure Key Vault | `azure.azcollection.azure_keyvault_secret` | `azure.azcollection` | Azure AD service principal |
| GCP Secret Manager | `google.cloud.gcp_secret_manager` | `google.cloud` | Service account JSON / workload identity |

```yaml
# HashiCorp Vault (KV v2) — use the dedicated kv2 lookup so the return
# is already the inner `data` mapping. `vault_read` returns the raw API
# envelope and would require indexing with `.data.data`.
db_password: "{{ lookup('community.hashi_vault.vault_kv2_get',
                        'prod/db',
                        engine_mount_point='secret',
                        auth_method='token').secret.password }}"

# Equivalent with the lower-level vault_read lookup:
# db_password: "{{ (lookup('community.hashi_vault.vault_read',
#                          'secret/data/prod/db',
#                          auth_method='token')).data.data.password }}"

# AWS Secrets Manager
api_key: "{{ lookup('amazon.aws.secretsmanager_secret',
                    'prod/api-key',
                    region='us-east-1') }}"

# 1Password
ssh_passphrase: "{{ lookup('community.general.onepassword',
                           'SSH Key prod',
                           field='passphrase',
                           vault='Engineering') }}"
```

Rules:

- ❌ Mix vault-encrypted static values with external secret lookups for the same secret → ✅ Pick one source of truth per secret; document which.
- ❌ Pass backend creds via plaintext group_vars → ✅ The controller's env / IAM role is the root of trust, not another file.
- ❌ Cache backend responses with `cacheable: true` → ✅ Secrets shouldn't sit in Ansible fact cache; always fetch fresh.
- ❌ Use a lookup plugin for a secret inside a loop without `no_log: true` → ✅ Loop iteration still logs the rendered value.

## Secrets in Logs and State

| Leak path | Symptom | Fix |
|-----------|---------|-----|
| `-v`/`-vv`/`-vvv` in CI | Secrets in workflow logs | Use `no_log: true`; enforce `-v` max in CI runner env |
| `ansible-navigator` artifact | Full run stored as JSON, includes module results | Redact secrets via `no_log`; treat navigator artifacts as sensitive |
| Fact cache with secrets | `jsonfile` / `redis` cache contains decrypted secrets | Never `set_fact cacheable=true` with a secret |
| `--diff` mode on templates | Rendered secrets visible in diff output | `no_log: true` + diff disabled for that task |
| Registered vars printed via `debug` | Leaked in play output | Pair `register:` with `no_log: true`, avoid `debug: var=` on secret-bearing results |
| `callback_whitelist = profile_tasks` | Task names + durations posted; if task name contains secret, leaked | Never put secrets in task names |

Rules:

- ❌ Run `ansible-playbook -vvv` in a CI job that handles Vault → ✅ CI should run at default verbosity; use `-v` only for focused debugging with secrets scrubbed.
- ❌ Store `ansible-navigator` artifacts in S3 without access controls → ✅ Same access rules as production state; they contain decrypted results.
- ❌ Redact by post-processing logs → ✅ Redact at source with `no_log`; post-processing always misses cases.
- ❌ `debug: var=result` on a registered secret fetch → ✅ Mark `no_log: true` on the debug task too, or skip it.

### LLM Mistake Checklist

- ❌ Put vault password files in the repo or in a dotfile that's committed → ✅ `.gitignore` vault password files; inject at runtime.
- ❌ Use one vault-id for all environments → ✅ Per-env vault-ids (`dev`, `stage`, `prod`).
- ❌ Omit `no_log: true` on a task passing a secret → ✅ Mandatory; forgetting it leaks at `-v` verbosity.
- ❌ `no_log: true` at play level → ✅ Task level only; play-level hides every failure.
- ❌ Cache secret values with `set_fact: cacheable=true` → ✅ Never cache secrets to disk/redis.
- ❌ `register:` a secret fetch + later `debug: var=result` with no safeguard → ✅ Mark both no_log.
- ❌ Assume CI masked-secrets handles everything → ✅ Runner masking is a last line; `no_log` is the primary control.
- ❌ Suggest `ansible-vault encrypt <whole file>` when one value is secret → ✅ `encrypt_string` preserves diffability.
