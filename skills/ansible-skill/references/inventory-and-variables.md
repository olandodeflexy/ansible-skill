# Inventory & Variables

Detail for the `Variable precedence bugs` and `Inventory correctness` routing-table categories.

## Variable Precedence Ladder

Canonical Ansible precedence order (lowest → highest). 22 levels per the official `ansible-core` docs. Later entries always override earlier ones.

| Level | Source | Example path / syntax | Common collision |
|-------|--------|----------------------|------------------|
| 1 | Command line connection/become flags | `-u myuser` → `ansible_user`; `-b`/`-K` → `ansible_become`/prompt | Sets connection/become magic vars only (not arbitrary variables). For variables, use `-e` at level 22 |
| 2 | Role defaults | `roles/<role>/defaults/main.yml` | Role author's default silently lost the moment anyone sets a group_var |
| 3 | Inventory file / script group vars (inline) | `[web:vars]` section in `hosts.ini` | Beaten by every file-based group_vars entry |
| 4 | Inventory `group_vars/all` | `inventories/prod/group_vars/all.yml` | Assumed "global" but overridden by any narrower group |
| 5 | Playbook `group_vars/all` | Repo-root `group_vars/all.yml` | Two `all` files (inventory vs playbook) — confusing |
| 6 | Inventory `group_vars/<group>` | `inventories/prod/group_vars/web.yml` | Host in 2 groups: alphabetical merge order is undefined without `ansible_group_priority` |
| 7 | Playbook `group_vars/<group>` | Repo-root `group_vars/web.yml` | Shadows inventory group_vars for the same group |
| 8 | Inventory file / script host vars (inline) | `web01 ansible_host=1.2.3.4 myvar=x` | Beaten by every file-based host_vars entry |
| 9 | Inventory `host_vars/<host>` | `inventories/prod/host_vars/web01.yml` | Always beats group_vars for that host |
| 10 | Playbook `host_vars/<host>` | Repo-root `host_vars/web01.yml` | Silent override of inventory host_vars |
| 11 | Host facts (auto-gathered) + fact-cached `set_fact` from **prior** runs | `ansible_facts.*`, values cached to disk/redis | Stale cache returns yesterday's value. Note: runtime `set_fact` in **this** run is level 19, not here |
| 12 | Play `vars` | `vars:` block on a play | Scoped to the play only, forgotten cross-play |
| 13 | Play `vars_prompt` | Interactive prompts | CI can't answer — task hangs |
| 14 | Play `vars_files` | `vars_files: [secrets.yml]` | Merge order is list-order, last file wins |
| 15 | Role vars | `roles/<role>/vars/main.yml` | Usually wins over `vars_files` inside the role's tasks |
| 16 | Block vars | `vars:` on a `block:` | Only visible inside that block |
| 17 | Task vars | `vars:` on a single task | Highest lexical scope, still beaten by extra-vars |
| 18 | `include_vars` | `ansible.builtin.include_vars: secrets.yml` | Runs at task time, not play start — timing surprises |
| 19 | Runtime `set_fact` / registered vars (this run) | `register: out` / `set_fact: k=v` | Persists across every later play **in this playbook run** regardless of `cacheable`. `cacheable: true` additionally writes the value to the fact cache so it becomes a level-11 fact in future runs |
| 20 | Role params (include_role) | `include_role: name=foo vars={k: v}` | Inline role call, overrides role defaults + vars |
| 21 | Include params | `include_tasks: foo.yml vars={k: v}` | Wins over most things except extra-vars |
| 22 | `--extra-vars` / `-e` | `-e @secrets.yml`, `-e k=v` | **Always wins** — a stray CI flag silently overrides protected config |

**Merge vs override:** for dicts, Ansible by default *replaces* on conflict. Set `hash_behaviour = merge` in `ansible.cfg` to merge (rarely recommended — global side effect).

**Group priority:** when a host is in multiple groups at the same precedence level (e.g. both `web` and `prod`), resolution order is alphabetical unless you set `ansible_group_priority` on the group (higher wins).

## Inventory Layout

| Pattern | Structure | When to use |
|---------|-----------|-------------|
| Static INI | `inventories/prod/hosts` (ini) + `group_vars/`, `host_vars/` | <50 hosts, hand-maintained, no cloud |
| Static YAML | `inventories/prod/hosts.yml` + vars dirs | Same as INI, but with typed group hierarchies |
| Dynamic plugin | `inventories/prod.aws_ec2.yml` | Cloud-authoritative truth; avoid drift |
| Hybrid | `inventories/prod/{dynamic.aws_ec2.yml, static.yml, group_vars/, host_vars/}` | Dynamic hosts + hand-tagged exceptions |

```text
inventories/
  prod/
    hosts                 # static INI or YAML
    aws_ec2.yml           # dynamic plugin config (in same dir = merged)
    group_vars/
      all.yml             # beats inventory-inline but loses to host_vars
      web.yml
    host_vars/
      web01.yml
```

Minimal dynamic inventory plugin (AWS EC2):

```yaml
# inventories/prod/aws_ec2.yml
plugin: amazon.aws.aws_ec2
regions:
  - us-east-1
keyed_groups:
  - key: tags.Role
    prefix: role
  - key: tags.Env
    prefix: env
hostnames:
  - tag:Name
  - private-ip-address
compose:
  ansible_host: private_ip_address
```

Rules:

- ❌ Putting `group_vars/` at the repo root *and* inside `inventories/prod/` → two sources collide by precedence, hard to debug.
- ✅ Keep `group_vars/` / `host_vars/` inside each `inventories/<env>/` directory; never at repo root.
- ❌ Mixing static `hosts` with a dynamic plugin in *different* directories; Ansible won't merge them.
- ✅ Put static + dynamic files in the same `inventories/<env>/` dir — Ansible merges them automatically.

## Dynamic Inventory Pitfalls

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| Unbounded re-query | Inventory plugin hits cloud API on every `ansible-playbook` run | `cache: true` + `cache_plugin: jsonfile` in plugin config |
| Cache staleness | Host added to cloud not visible until cache expiry | Short `cache_timeout` or `ansible-inventory --refresh-cache` in CI |
| `ansible_host` vs `inventory_hostname` divergence | `inventory_hostname` is a tag, but ssh needs IP | Use `compose: { ansible_host: private_ip_address }` |
| `--limit` against dynamic group | Group empty at play start → play silently runs against 0 hosts | `ansible-inventory --graph --limit=foo` to confirm non-empty |
| Plugin auth ambient vs explicit | Works locally, fails in CI when IAM role absent | Assume an explicit IAM role in CI job; never rely on developer creds |
| Plugin version drift | New tag schema causes groupings to disappear | Pin plugin's collection version in `requirements.yml` |

Rules:

- ❌ Rely on `inventory_hostname` as the ssh target → ✅ Set `ansible_host` via `compose:` in the plugin config.
- ❌ Skip `cache: true` on a plugin that hits a rate-limited API → ✅ Always cache; tune `cache_timeout` per environment.
- ❌ Trust `--limit foo` when `foo` is a dynamic group → ✅ Run `ansible-inventory --graph --limit=foo` first to confirm the group is non-empty.
- ❌ Commit cloud credentials alongside inventory config → ✅ Rely on instance IAM role (CI) or `aws configure sso` (local); never inline creds.

## set_fact vs vars

| Goal | Use | Persistence scope | `cacheable:` needed? |
|------|-----|-------------------|---------------------|
| One-shot per play | Play/task `vars` | That play only | n/a |
| Value derived from module output | `register:` | Task run lifetime | n/a |
| Cross-play persistence **in same playbook run** | `set_fact:` | Rest of the run | **No** — plain `set_fact` already persists across later plays in the same run |
| Cross-run persistence (survive `ansible-playbook` exit) | `set_fact:` + `cacheable: true` + a fact-caching plugin | Until cache expires | Yes, mandatory; configure `fact_caching` in `ansible.cfg` |
| Loop item transformation | Task-level `vars:` with `lookup` / filter | That task only | n/a |
| Computed constant used many times | `set_fact` early in play | Rest of run | No |

```yaml
- name: Fetch version once, reuse across tasks
  ansible.builtin.command: /opt/app/bin/app --version
  register: version_cmd
  changed_when: false

- name: Store as fact for other plays
  ansible.builtin.set_fact:
    app_version: "{{ version_cmd.stdout | trim }}"
    cacheable: true
```

Rules:

- ❌ `set_fact` in a loop with the same fact name, different item values → ✅ Use `set_fact` outside the loop with a list comprehension: `my_list: "{{ items | map('regex_replace', ...) | list }}"`.
- ❌ `register:` on a loop and then reading `.stdout` (it's a list of items, each with its own result) → ✅ `register: r` then iterate `r.results[]`.
- ❌ Assume `set_fact` persists across `ansible-playbook` invocations without fact caching → ✅ Set `cacheable: true` and configure `fact_caching` in `ansible.cfg`.
- ❌ `set_fact: cacheable: true` with a secret value → ✅ Facts cached to disk/redis; treat as sensitive storage and don't cache secrets.
- ❌ Use `vars:` for a value computed from a module → ✅ That's what `register` is for; `vars:` is static at compile time.

### LLM Mistake Checklist

- ❌ Declare "`group_vars/all` always wins over `host_vars`" → ✅ `host_vars/<host>` (level 9) beats inventory `group_vars/all` (level 4) for that host.
- ❌ Place `group_vars/` at the repo root for an inventory-per-env layout → ✅ Nest under each `inventories/<env>/` to prevent cross-env leakage.
- ❌ Use `vars:` to capture a computed value → ✅ Use `register:` or `set_fact`.
- ❌ Omit `cache: true` on a dynamic inventory plugin → ✅ Always cache; pair with `ansible-inventory --refresh-cache` in CI.
- ❌ Trust `--limit` against a dynamic group without checking membership → ✅ `ansible-inventory --graph --limit=foo` before any run.
- ❌ Call `inventory_hostname` the ssh target on a cloud inventory → ✅ Set `ansible_host` via `compose:` to the private/public IP.
- ❌ Ship `--extra-vars` as a CI default without scoping → ✅ Use only when explicitly required; extra-vars beats every other precedence level.
