*# 🚀 Infintrix Atlas

> AI-Augmented Project Management built on top of ERPNext  
> Inspired by Jira. Designed for execution clarity. Built Open-Source.

Atlas is a next-generation project execution layer built on top of ERPNext, with a modern React UI and intelligent workflow design.

It separates **execution from planning**, enforces **clean hierarchy rules**, and introduces an AI-powered task intelligence layer.

---

# 🧠 Core Philosophy

Most tools mix planning and execution.

Atlas doesn’t.

- **Status ≠ Cycle**
- **Hierarchy ≠ Planning**
- **Execution Mode changes behavior, not schema**
- **Backlog is derived, not stored**

This keeps the system predictable, scalable, and analyzable.

---

# ✅ Available Features

## 📦 Project Management

- Create Projects (Scrum or Kanban mode)
- Execution mode controls UI behavior
- Derived project completion metrics
- Clean project → task → cycle separation

---

## 🧩 Task Engine (Work Item System)

- Atomic work item model
- Parent / child hierarchy
- Task Types with hierarchy validation
- Status lifecycle:
  - Open
  - Working
  - Pending Review
  - Completed
  - Cancelled
- Priority management
- Assignee support
- Independent task creation (cycle optional)

---

## 🔁 Cycle (Sprint) Management

- Timeboxed planning container
- Planned / Active / Completed / Archived
- One active cycle per project (enforced)
- Tasks reference cycles (cycles don’t own tasks)

---

## 🧱 Task Type System

- Custom task classifications
- Container vs atomic type
- Allowed child type rules
- Prevents invalid hierarchies (e.g., Bug under Bug)

---

## 📊 Derived Concepts

No unnecessary doctypes. Everything computed.

### Backlog

- Scrum → Open + No Cycle
- Kanban → Open

### Efficiency Metric

In Progress / (Open + In Progress)

### Backlog Health

Based on:
- Backlog size
- Task staleness
- Efficiency threshold

---

## 🔔 Realtime System

- Task assignment notifications
- Status change notifications
- Watcher-based alerts
- Socket-based event system
- Live “Who is working on what” visibility

---

## 🎨 Custom React UI

- Built on top of ERPNext backend
- Clean execution dashboard
- Cycle board (Scrum)
- Status board (Kanban)
- Assignee avatars
- Hierarchical task view

---

## 🤖 AI Layer (Early Version)

- Task clarity suggestions
- Scope drift detection
- Backlog health insights
- Execution bottleneck hints

---

# 🖥 Desk Workspace

Clicking **Infintrix Atlas** on the apps screen opens `/desk/infintrix-atlas`, a Desk workspace with a pinned sidebar
(Atlas, Work, Planning, Setup). It has number cards (open/overdue/in-review tasks, active cycles, ...), charts, and
React-powered **Projects** and **Tasks** pages. The old `/atlas` SPA is deprecated.

After pulling changes: `bench build --app infintrix_atlas && bench --site <site> migrate`.

---

# 🔌 MCP Server (use Atlas from Claude, ChatGPT or any MCP client)

Atlas exposes a [Model Context Protocol](https://modelcontextprotocol.io) server so an AI assistant can manage
projects, tasks, cycles, requirements and more as a real Atlas user.

- **Endpoint:** `POST https://<your-site>/api/method/infintrix_atlas.mcp.server.handle`
  (streamable HTTP, JSON responses; the site must be reachable over HTTPS from the client)
- **Permissions:** every tool runs as the authenticated user. Frappe permissions, project membership and the task
  review workflow apply exactly as on Desk. Task status can only change through `task_workflow`.

## Authentication

**Option 1 - API key (Claude Code, scripts, most MCP clients)**

1. Desk -> *User* -> your user -> *API Access* -> **Generate Keys**. Copy the key and secret.
2. Send `Authorization: token <api_key>:<api_secret>` with every request.

**Option 2 - OAuth (Claude.ai / ChatGPT custom connectors)**

Frappe publishes its OAuth discovery documents (`/.well-known/oauth-protected-resource`,
`/.well-known/oauth-authorization-server`). Create an *OAuth Client* in Desk (enable the discovery metadata in
*OAuth Settings*), then add the endpoint above as a custom connector; the client runs the OAuth flow and signs in as you.

## Connect a client

Claude Code:

```bash
claude mcp add --transport http atlas https://<your-site>/api/method/infintrix_atlas.mcp.server.handle \
  --header "Authorization: token <api_key>:<api_secret>"
```

Generic JSON config (clients that accept HTTP MCP servers):

```json
{
  "mcpServers": {
    "atlas": {
      "type": "http",
      "url": "https://<your-site>/api/method/infintrix_atlas.mcp.server.handle",
      "headers": { "Authorization": "token <api_key>:<api_secret>" }
    }
  }
}
```

Quick check with curl:

```bash
curl -s -X POST https://<your-site>/api/method/infintrix_atlas.mcp.server.handle \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

## Tools

| Area | Tools |
|---|---|
| Discovery | `whoami`, `describe_doctype`, `list_link_fields`, `find_link_options` |
| Projects | `list_projects`, `get_project`, `project_links`, `project_metrics`, `archive_project`, `list_team`, `add_team_member`, `remove_team_member` |
| Companies | `list_companies`, `get_company` |
| Tasks | `list_tasks`, `get_task`, `create_task`, `update_task`, `assign_task`, `bulk_assign_tasks`, `add_comment`, `list_subtasks`, `task_activity`, `delete_task`, `add_watcher`, `remove_watcher`, `list_watchers` |
| Task lifecycle | `task_workflow` - actions: `start`, `submit_for_review`, `approve`, `request_changes`, `reopen`, `block`, `unblock`, `cancel` |
| Cycles | `list_cycles`, `cycle_summary`, `start_cycle`, `complete_cycle`, `move_tasks_to_cycle` |
| Requirements and scope | `set_requirement_status`, `create_task_from_requirement`, `change_request_action` (submit/approve/reject/implement), `create_scope_snapshot`, `action_request` |
| Generic CRUD | `list_records`, `get_record`, `create_record`, `update_record`, `delete_record`, `submit_record` on Project, Task, Task Type, Cycle, Requirement, Change Request, Scope Snapshot, Project Resource, Project Action Request, Work Item Relationship, AI Task Session, AI Task Draft, Atlas Settings, Timesheet |

Example prompts: *"Create a task 'Fix login bug' in project PROJ-0001, high priority, assign to me"*,
*"Start the task, then submit it for review by alice@example.com"*, *"Show all projects for company Infintrix with overdue tasks"*,
*"Create a cycle for next week and move the open bugs into it"*.

Secrets (password fields such as the AI API key in Atlas Settings) are never returned to MCP clients.

Code: `infintrix_atlas/mcp/` (`server.py` protocol, `tools.py` + `tools_extra.py` tools).

---

# 🏗 Architecture

- Backend: Frappe / ERPNext
- Custom module with custom fields
- React frontend (decoupled UI layer)
- Derived metrics (no redundant storage)

### Core Invariants

- Task can exist without Cycle
- Cycle can exist without Tasks
- Status is execution
- Cycle is planning

---

# 🚧 Upcoming Features

## 🔐 Responsibility & Ownership Model

- Single-owner strict mode
- Accountability scoring
- Delayed task penalty logic
- Assignee performance insights

## 📈 Advanced Metrics

- Lead time
- Cycle time
- Throughput tracking
- Staleness heatmap
- Project execution risk score

## 🧠 AI Copilot (Full Version)

- Auto task breakdown suggestions
- Smart subtask generation
- Scope change impact estimation
- Automatic backlog prioritization
- Sprint load balancing

## 🔗 Integrations

- Slack notifications
- GitHub issue sync
- Git commit linking
- Push notifications (PWA)

## 📊 Executive Dashboard

- Portfolio-level metrics
- Team efficiency comparison
- Execution drag detection

---

# 🎯 Why Atlas?

Because:

- Jira is powerful but rigid.
- ERPNext projects are flexible but shallow.
- Most tools mix planning and execution.
- AI in PM tools is mostly marketing fluff.

Atlas focuses on execution clarity first. Intelligence second. UI third.

---

# 📌 Current Status

- 🟡 Active Development
- 🧪 Early production usage
- 🔓 Open for contributors

---

# 🤝 Contributing

Contributions are welcome.

Areas that need help:

- React UI refinement
- AI workflow logic
- Metrics optimization
- Real-time architecture improvements
- Documentation

Open an issue. Challenge assumptions. Propose better invariants.

---

# 📜 License

MIT
*