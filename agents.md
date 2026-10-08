# AI Security Corpus - Agent Instructions

## About This Repo

This is a personal corpus of AI security knowledge (the repo is `ai-security-corpus`), primarily focused on AI security, but also covering broader AI topics that are valuable to the maintainer. The primary audience is the repo owner. There is **no gatekeeping** on what gets added -- if the owner wants to add something, it gets added. Period.

## Repo Structure

```
ai-security/
  README.md                          # Top-level index with aggregators, system prompts, prompt design

  foundations/
    frameworks-and-standards/        # Risk frameworks, standards (NIST, OWASP, MITRE ATLAS)
    governance-and-policy/           # Compliance, AI policy, legal, trust
    threat-modeling/                 # Threat modeling frameworks, tools, methodologies
    architecture/                    # Secure AI design patterns and principles

  attacks/
    prompt-injection/                # Prompt injection taxonomy, techniques, datasets, defenses
    jailbreaking/                    # Jailbreaking techniques and research
    model-attacks/                   # Poisoning, backdoors, extraction, adversarial ML
    supply-chain/                    # Dependency attacks, model integrity, signing
    incidents/                       # Real-world breaches, exploits, case studies

  defense/
    guardrails-and-firewalls/        # Guardrails, firewalls, runtime protection
    sandboxing-and-isolation/        # Runtime containment, sandboxing, code execution security
    detection-and-monitoring/        # Vulnerability scanners, security platforms, threat detection
    secrets-management/              # Protecting secrets from AI agents
    honeypots-and-deception/         # Honeypots and adversary engagement

  agents/
    agent-security/                  # Agent-specific security concerns and threats
    agent-identity/                  # OAuth, NHI, authentication, authorization
    mcp/                             # MCP gateways, scanners, research, tooling
    agent-frameworks/                # General agent frameworks, platforms, tools

  coding/
    secure-coding/                   # Rules files, vibe coding security, secure prompt engineering
    code-analysis/                   # SAST, code review, vulnerability scanning
    coding-tools/                    # IDE integrations, copilots, assistants

  research/
    papers/                          # Academic papers and surveys
    benchmarks/                      # Evaluation frameworks and datasets
    safety-and-alignment/            # AI safety, alignment, privacy

  practice/
    red-teaming/                     # Offensive AI security, tools, methodologies
    engineering-patterns/            # Harness engineering, building patterns
    privacy/                         # Data leakage, PII protection, exfiltration

  general/                           # Blog posts, talks, opinion, commentary

  resources/                         # Local PDFs and other files
```

Each directory has a `README.md` with categorized links.

## Adding a New Link

When the user wants to add a link, the agent should:

1. **Fetch the URL** to get the proper page title (use WebFetch or similar). If the URL is unreachable, use whatever title the user provides or extract the best title from the URL itself.

2. **Format as a markdown hyperlink**: `- [Page Title](https://url.example.com)`
   - Strip trailing garbage from titles (e.g. extra whitespace, pipe-separated site names can be kept or trimmed based on readability)
   - For arXiv papers, use the paper title from the page, not the arXiv ID
   - For GitHub repos, use the repo description if the repo name alone isn't descriptive
   - For tweets/X posts, summarize the key content briefly as the link text

3. **Classify the link** into the appropriate category/section:
   - If it's clearly an academic paper (arXiv, conference proceedings) -> `research/papers/README.md`
   - If it's about MCP specifically -> `agents/mcp/README.md`
   - If it's about agent identity, NHI, OAuth for agents -> `agents/agent-identity/README.md`
   - If it's about agent security threats/tools -> `agents/agent-security/README.md`
   - If it's about general agent frameworks/platforms -> `agents/agent-frameworks/README.md`
   - If it's about prompt injection -> `attacks/prompt-injection/README.md`
   - If it's about jailbreaking -> `attacks/jailbreaking/README.md`
   - If it's about model poisoning, backdoors, extraction -> `attacks/model-attacks/README.md`
   - If it's about red teaming methodology or offensive tools -> `practice/red-teaming/README.md`
   - If it's about guardrails, firewalls -> `defense/guardrails-and-firewalls/README.md`
   - If it's about sandboxing, isolation -> `defense/sandboxing-and-isolation/README.md`
   - If it's about vulnerability scanning, detection -> `defense/detection-and-monitoring/README.md`
   - If it's about secrets management -> `defense/secrets-management/README.md`
   - If it's about supply chain risks -> `attacks/supply-chain/README.md`
   - If it's about benchmarks or evaluation -> `research/benchmarks/README.md`
   - If it's about secure coding, SAST, or code review -> `coding/code-analysis/README.md`
   - If it's about coding tools, IDEs, copilots -> `coding/coding-tools/README.md`
   - If it's about secure coding rules/practices -> `coding/secure-coding/README.md`
   - If it's about frameworks, governance, policy -> `foundations/governance-and-policy/README.md`
   - If it's about threat modeling -> `foundations/threat-modeling/README.md`
   - If it's about architecture or design patterns -> `foundations/architecture/README.md`
   - If it's about AI safety, alignment -> `research/safety-and-alignment/README.md`
   - If it's about privacy, data leakage -> `practice/privacy/README.md`
   - If it's about harness/context engineering -> `practice/engineering-patterns/README.md`
   - If it's a real-world incident or case study -> `attacks/incidents/README.md`
   - If it's a blog post, opinion piece, or general commentary -> `general/README.md`
   - **When in doubt, ask the user** which section fits best. Present the top 2-3 candidate sections.

4. **Append the link** to the appropriate section in the target file. Place it at the end of the relevant subsection.

5. **Handle ambiguous or cross-cutting topics**: Some links span multiple categories. Default to the more specific category, but if the user has a preference, follow it.

## Link Format Examples

Good:
```markdown
- [Defeating Prompt Injections by Design](https://arxiv.org/abs/2503.18813)
- [Agentic AI Red Teaming Playbook](https://www.pillar.security/agentic-ai-red-teaming-playbook)
- [Dark Visitors - A list of known AI agents on the internet](https://darkvisitors.com/)
```

Bad (bare URLs, no title):
```markdown
- https://arxiv.org/abs/2503.18813
- https://www.pillar.security/agentic-ai-red-teaming-playbook
```

If you encounter existing bare URLs in the repo, offer to convert them to proper hyperlinks when convenient.

## Bulk Additions

When the user provides multiple links at once:
- Process them in parallel where possible
- Group the results by target file/section
- Present the proposed additions for review before committing

## General Guidelines

- Don't argue about whether something belongs in this repo. If the user wants it added, add it.
- Don't restructure or reorganize existing content unless explicitly asked.
- Don't remove or modify existing links unless asked.
- When fetching titles, if a site blocks automated access, fall back gracefully -- use the URL path or ask the user for the title.
- PDFs stored locally go in the `resources/` directory and are linked with relative paths.

## Slash Command

The `/add-resource` command (defined in `.claude/commands/add-resource.md`; port it to your agent of choice) automates the full workflow:

```
/add-resource https://example.com/some-article
```

This will:
1. Fetch the page and extract a proper title
2. Classify the link into the correct repo section
3. **If classification is ambiguous** -- stop and ask the user rather than guessing
4. Append the formatted hyperlink to the right file and section
5. Confirm what was added and where


<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:46cd31e7 -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/core-concepts/sync-concepts.md for details and anti-patterns.

## Agent Context Profiles

The managed Beads block is task-tracking guidance, not permission to override repository, user, or orchestrator instructions.

- **Conservative (default)**: Use `bd` for task tracking. Do not run git commits, git pushes, or Dolt remote sync unless explicitly asked. At handoff, report changed files, validation, and suggested next commands.
- **Minimal**: Keep tool instruction files as pointers to `bd prime`; use the same conservative git policy unless active instructions say otherwise.
- **Team-maintainer**: Only when the repository explicitly opts in, agents may close beads, run quality gates, commit, and push as part of session close. A current "do not commit" or "do not push" instruction still wins.

## Session Completion

This protocol applies when ending a Beads implementation workflow. It is subordinate to explicit user, repository, and orchestrator instructions.

1. **File issues for remaining work** - Create beads for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **Handle git/sync by active profile**:
   ```bash
   # Conservative/minimal/default: report status and proposed commands; wait for approval.
   git status

   # Team-maintainer opt-in only, unless current instructions forbid it:
   git pull --rebase
   bd dolt push
   git push
   git status
   ```
5. **Hand off** - Summarize changes, validation, issue status, and any blocked sync/commit/push step

**Critical rules:**
- Explicit user or orchestrator instructions override this Beads block.
- Do not commit or push without clear authority from the active profile or the current user request.
- If a required sync or push is blocked, stop and report the exact command and error.
<!-- END BEADS INTEGRATION -->
