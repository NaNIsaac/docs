# Agent orchestration (orc)

How the coding agents behind these projects are run: the roles, what each may and may not do, where state lives, and four flows. Each part is marked **core** (the reusable orc pattern and tools) or **overlay** (this setup's choices: access, services, accounts).

![Overview: owner, secretary, boss and lanes in herdr panes, the courier queue, the sentinel, guards, GitHub and model access](./orc-overview.svg)

![Three flows: order to deploy, question to answer, quota or health check to action](./orc-flows.svg)

## Roles

| Role | Kind | Does | Does not |
| --- | --- | --- | --- |
| owner | overlay | gives orders, answers numbered questions, merges or names the PRs secretary may merge, does logins, installs and physical steps | type into agent panes (except in an emergency, then logged with secretary) |
| secretary | core | the owner's only inbox; forwards orders to boss word for word, with its own notes kept apart and marked; answers status questions itself; asks owner questions; merges a PR the owner named | rewrite or extend an order; merge a PR the owner did not name |
| boss | core | plans, writes lane briefs, picks each lane's model, grants slots for runs over 2 minutes or 2 GB, deploys or restarts merged services | merge; talk to the owner except through secretary |
| lanes (up to 6) | core | one task each, in its own worktree and branch; runs CI's checks before pushing; opens a PR (at most 2 open) and reports one line | merge, force push, close panes, restart services |

Lanes run Claude Code or Codex. Each agent role has its own login store, so one role's sign-out or token refresh does not touch another.

## Parts

| Part | Kind | What it is |
| --- | --- | --- |
| herdr workspace | core | a terminal multiplexer; one named pane per agent, tabs ordered for the phone |
| courier queue | core | the only process that types into agent panes, and only when the input box is empty; raw pane typing is blocked by hook |
| lane-state tool | core | writes a lane's state file (task, PRs, waiting on, next, unverified) and sends its one-line report through courier |
| sentinel | core | read-only monitor: agents, panes, services, stalled jobs, abnormal reboot every 30 s; quota and usage checks; a daily list of stale board items. Alerts go through courier: quota and stale board items to secretary and boss; service, blocked agent and drift to boss; context limit to the agent's compact owner |
| permission guard | core | deny rules plus a pre-tool hook on every agent: no merge (secretary excepted), force push, visibility change, raw pane typing, Python from stdin |
| Q-AUTO | core | secretary's hooks: gives the next question number, registers new questions on the owner board, records answers like `12 a` |
| role-brief | core | session-start hook: injects the role's brief and checks login store, folder and model; reports drift |
| control center (ICC) | overlay | web app reachable only on the private network with the owner's login: to-do, questions, agents, PRs, CI, runs, tokens; its messages go through courier |
| phone and ssh access | overlay | a terminal mirror on the phone; ssh is used only to run the one restart tool |
| owner board | overlay | a GitHub project with orders, to-do and questions: one list for everything that waits on the owner |
| GitHub | overlay | repositories, PRs, CI, issues |
| model router and local models | overlay | a local router (OmniRoute) to cloud model providers with daily budgets, which routes to a small local fallback model when they fail; free models; local Ollama models for private jobs; a dispatcher moves a job to the next worker on quota, auth, timeout or empty output |

## Boundaries

- The owner merges, or secretary merges a PR the owner named; workers' settings deny `gh pr merge`.
- The sentinel and the read-only tools never restart, close panes, touch git or merge.
- Only courier types into agent panes.
- Runs over 2 minutes or 2 GB wait for a slot from boss.
- The owner's to-do holds only what a human must do: decisions, logins, installs, physical steps.
- Secrets never go into git, documents or to-do items.

## Data stores

| Store | Kind | Holds |
| --- | --- | --- |
| question ledger | core | every owner question: number, text, answer |
| decision table | core | each orc decision the owner made, with its source; old rows are superseded, not deleted |
| work queue | core | open items, edited only by its tool |
| lane state files | core | one per lane, written only by the lane-state tool |
| handoff and brief files | core | per-role briefs and handoffs, injected at session start |
| sentinel data | core | snapshot, state, roster, alerts and events logs |
| roles file | core | role to login store, model and effort; lanes' own models |
| owner board, issues, PRs | overlay | on GitHub |

## Flows

1. **Order to deploy.** owner gives an order → secretary forwards it word for word → boss writes a lane brief (and a slot for long runs) → lane works on a branch, runs CI's checks, opens a PR with a `local-ci` line → on green CI the lane reports `READY repo#N` to secretary → secretary reviews; the owner merges, or secretary merges a PR the owner named (fixes go back to the lane) → boss deploys or restarts the changed service.
2. **Question to answer.** an agent hits a choice only the owner can make and sends options with one recommendation to boss → secretary asks it as `Qn` with the next ledger number → Q-AUTO registers it on the owner board → owner answers `Qn a` on the web app or in secretary's pane → Q-AUTO records the answer and closes the item → the answer goes back to the lane; an orc decision also gets a row in the decision table.
3. **Quota or health to action.** sentinel reads state every 30 s, quota, usage and the board on their own timers → a threshold is crossed (GitHub API or CI minutes 80 %, router budget 80 %, model window 70 % or 90 %, service down, agent blocked or gone, board item stale 2+ days) → one alert line through courier, kept in the alert log: quota and stale board items to secretary and boss; service, blocked agent and drift to boss → boss holds or queues runs, moves work to another account or tool, asks a lane to compact or stop, or fixes the service → what only a human can do becomes an owner to-do.
4. **Context limit to compact.** sentinel sees an agent's context over the limit → it tells that agent's compact owner (boss for lanes, secretary for boss) → the compact owner asks the agent to update its state (lanes: the lane-state tool) → the agent answers `compact ready` → the compact owner sends `/compact` through courier. Secretary is not compacted at the 300k limit; it compacts automatically at 400k, or the owner or boss compacts it. An automatic compact at 400k tokens is the safety net for every agent.
