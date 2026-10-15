"""Atlas MCP tools. Each runs as the session user; permissions are enforced by Frappe, not here."""

import json

import frappe
from frappe import _
from frappe.utils import cint

from infintrix_atlas.api import task_review
from infintrix_atlas.api.tasks import switch_assignee_of_task

TASK_FIELDS = [
	"name", "subject", "status", "priority", "project", "type", "parent_task", "exp_start_date",
	"exp_end_date", "progress", "_assign", "custom_cycle", "custom_story_points", "custom_requirement",
	"custom_reviewer", "company", "modified",
]
PROJECT_FIELDS = ["name", "project_name", "status", "project_type", "percent_complete", "expected_end_date", "customer", "company"]
MAX_LIMIT = 100

TOOLS: dict[str, dict] = {}


def tool(name: str, description: str, properties: dict, required: list | None = None, read_only: bool = False):
	def register(fn):
		TOOLS[name] = {
			"fn": fn,
			"def": {
				"name": name,
				"description": description,
				"inputSchema": {"type": "object", "properties": properties, "required": required or []},
				"annotations": {"readOnlyHint": read_only},
			},
		}
		return fn

	return register


def definitions() -> list[dict]:
	return [t["def"] for t in TOOLS.values()]


def _s(description: str, **extra) -> dict:
	return {"type": "string", "description": description, **extra}


def _limit(value) -> int:
	return min(max(cint(value) or 20, 1), MAX_LIMIT)


def _task_view(task: dict) -> dict:
	try:
		assignees = json.loads(task.get("_assign") or "[]")
	except ValueError:
		assignees = []
	view = {k: v for k, v in task.items() if k != "_assign"}
	view["assignees"] = assignees
	return view


# --- read -------------------------------------------------------------------


@tool("whoami", "Return the Atlas user this connection acts as, with their roles.", {}, read_only=True)
def whoami():
	return {"user": frappe.session.user, "roles": frappe.get_roles()}


@tool(
	"list_projects",
	"List projects the user can access.",
	{"status": _s("Open, Completed or Cancelled"), "company": _s("Company name"), "customer": _s("Customer id"), "search": _s("Match on project name"), "limit": {"type": "integer"}},
	read_only=True,
)
def list_projects(status=None, company=None, customer=None, search=None, limit=20):
	filters = {k: v for k, v in {"status": status, "company": company, "customer": customer}.items() if v}
	or_filters = [["project_name", "like", f"%{search}%"], ["name", "like", f"%{search}%"]] if search else None
	return frappe.get_list(
		"Project", filters=filters, or_filters=or_filters, fields=PROJECT_FIELDS,
		order_by="modified desc", limit_page_length=_limit(limit),
	)


@tool("get_project", "Get a project with its team members and open task count.", {"project": _s("Project id")}, ["project"], True)
def get_project(project):
	doc = frappe.get_doc("Project", project)
	doc.check_permission("read")
	return {
		**{f: doc.get(f) for f in PROJECT_FIELDS},
		"team": [u.user for u in doc.get("users") or []],
		"open_tasks": len(frappe.get_list("Task", {"project": project, "status": ["not in", ["Completed", "Cancelled"]]}, pluck="name", limit_page_length=0)),
	}


@tool(
	"list_tasks",
	"List tasks. Filter by project, status, assignee (user id/email, or 'me'), cycle or text in the subject.",
	{
		"project": _s("Project id"), "status": _s("Open, Working, Pending Review, Overdue, Completed, Cancelled"),
		"assignee": _s("User id, or 'me'"), "cycle": _s("Cycle id"), "company": _s("Company name"), "search": _s("Text in the subject"),
		"limit": {"type": "integer"},
	},
	read_only=True,
)
def list_tasks(project=None, status=None, assignee=None, cycle=None, search=None, limit=20, company=None):
	filters = [["status", "!=", "Template"]]
	if project:
		filters.append(["project", "=", project])
	if status:
		filters.append(["status", "=", status])
	if cycle:
		filters.append(["custom_cycle", "=", cycle])
	if company:
		filters.append(["company", "=", company])
	if search:
		filters.append(["subject", "like", f"%{search}%"])
	if assignee:
		user = frappe.session.user if assignee == "me" else assignee
		filters.append(["_assign", "like", f"%{user}%"])
	rows = frappe.get_list("Task", filters=filters, fields=TASK_FIELDS, order_by="modified desc", limit_page_length=_limit(limit))
	return [_task_view(r) for r in rows]


@tool("get_task", "Get one task with description, assignees, comments and allowed workflow actions.", {"task": _s("Task id")}, ["task"], True)
def get_task(task):
	doc = frappe.get_doc("Task", task)
	doc.check_permission("read")
	view = _task_view({f: doc.get(f) for f in TASK_FIELDS if f != "_assign"} | {"_assign": doc.get("_assign")})
	view["description"] = frappe.utils.strip_html_tags(doc.description or "")
	view["comments"] = [
		{"by": c.owner, "on": c.creation, "text": frappe.utils.strip_html_tags(c.content or "")}
		for c in frappe.get_all(
			"Comment", {"reference_doctype": "Task", "reference_name": task, "comment_type": "Comment"},
			["owner", "creation", "content"], order_by="creation asc", limit_page_length=50,
		)
	]
	try:
		view["workflow_actions"] = task_review.get_review_actions(task)
	except Exception:
		view["workflow_actions"] = None
	return view


@tool("list_cycles", "List cycles (sprints), optionally for one project or status.", {"project": _s("Project id"), "status": _s("Planned, Active, Completed, Archived")}, read_only=True)
def list_cycles(project=None, status=None):
	filters = {k: v for k, v in {"project": project, "status": status}.items() if v}
	return frappe.get_list("Cycle", filters=filters, fields=["name", "cycle_name", "project", "status", "start_date", "end_date"], order_by="modified desc", limit_page_length=50)


@tool("list_team", "List the users on a project.", {"project": _s("Project id")}, ["project"], True)
def list_team(project):
	doc = frappe.get_doc("Project", project)
	doc.check_permission("read")
	return [{"user": u.user, "full_name": u.full_name, "email": u.email} for u in doc.get("users") or []]


# --- write ------------------------------------------------------------------


def _assign(task: str, user: str | None):
	if user == "me":
		user = frappe.session.user
	if user and not frappe.db.exists("User", {"name": user, "enabled": 1}):
		frappe.throw(_("User {0} does not exist or is disabled").format(user))
	switch_assignee_of_task(task, user or "unassigned")


@tool(
	"create_task",
	"Create a task, optionally assigning it. Needs a subject; a project is strongly recommended.",
	{
		"subject": _s("Task title"), "project": _s("Project id"), "description": _s("Task details (plain text or HTML)"),
		"priority": _s("Low, Medium, High or Urgent"), "assignee": _s("User id/email, or 'me'"),
		"due_date": _s("YYYY-MM-DD"), "start_date": _s("YYYY-MM-DD"), "story_points": {"type": "integer"},
		"cycle": _s("Cycle id"), "task_type": _s("Task Type id"), "parent_task": _s("Parent task id"),
		"requirement": _s("Requirement id"),
	},
	["subject"],
)
def create_task(subject, project=None, description=None, priority=None, assignee=None, due_date=None, start_date=None,
		story_points=None, cycle=None, task_type=None, parent_task=None, requirement=None):
	doc = frappe.get_doc({
		"doctype": "Task", "subject": subject, "project": project, "description": description, "priority": priority,
		"exp_end_date": due_date, "exp_start_date": start_date, "custom_story_points": story_points,
		"custom_cycle": cycle, "type": task_type, "parent_task": parent_task, "custom_requirement": requirement,
	})
	doc.insert()
	if assignee:
		_assign(doc.name, assignee)
	return get_task(doc.name)


UPDATABLE = {
	"subject": "subject", "description": "description", "priority": "priority", "due_date": "exp_end_date",
	"start_date": "exp_start_date", "story_points": "custom_story_points", "cycle": "custom_cycle",
	"task_type": "type", "reviewer": "custom_reviewer", "requirement": "custom_requirement",
}


@tool(
	"update_task",
	"Update task fields (not status or assignee: use task_workflow and assign_task).",
	{"task": _s("Task id"), **{k: _s(k.replace("_", " ")) for k in UPDATABLE}},
	["task"],
)
def update_task(task, **fields):
	unknown = set(fields) - set(UPDATABLE)
	if unknown:
		frappe.throw(_("Cannot update: {0}").format(", ".join(sorted(unknown))))
	doc = frappe.get_doc("Task", task)
	for key, value in fields.items():
		doc.set(UPDATABLE[key], value)
	doc.save()
	return get_task(task)


@tool("assign_task", "Set the single assignee of a task. Use assignee 'unassigned' to clear, 'me' for yourself.", {"task": _s("Task id"), "assignee": _s("User id/email, 'me' or 'unassigned'")}, ["task", "assignee"])
def assign_task(task, assignee):
	frappe.get_doc("Task", task).check_permission("write")
	_assign(task, None if assignee == "unassigned" else assignee)
	return get_task(task)


@tool("add_comment", "Add a comment to a task.", {"task": _s("Task id"), "text": _s("Comment text")}, ["task", "text"])
def add_comment(task, text):
	doc = frappe.get_doc("Task", task)
	doc.check_permission("read")
	comment = doc.add_comment("Comment", text)
	return {"comment": comment.name}


WORKFLOW = {
	"start": lambda task, a: task_review.start_work(task),
	"submit_for_review": lambda task, a: task_review.submit_for_review(task, a.get("reviewer")),
	"approve": lambda task, a: task_review.approve_task(task, a.get("comments")),
	"request_changes": lambda task, a: task_review.request_changes(task, a.get("comments")),
	"reopen": lambda task, a: task_review.reopen_task(task, a.get("reason"), a.get("reopen_type") or "Other"),
	"block": lambda task, a: task_review.block_task(task, a.get("reason")),
	"unblock": lambda task, a: task_review.unblock_task(task),
	"cancel": lambda task, a: task_review.cancel_task(task, a.get("reason")),
}


@tool(
	"task_workflow",
	"Move a task through the review workflow. Actions: " + ", ".join(WORKFLOW) + ". Allowed actions depend on status and role (see get_task.workflow_actions).",
	{
		"task": _s("Task id"), "action": _s("Workflow action", enum=list(WORKFLOW)),
		"reviewer": _s("Reviewer user (submit_for_review)"), "comments": _s("Comments (approve/request_changes)"),
		"reason": _s("Reason (reopen/block/cancel)"), "reopen_type": _s("Reopen type (reopen)"),
	},
	["task", "action"],
)
def task_workflow(task, action, **args):
	if action not in WORKFLOW:
		frappe.throw(_("Unknown action {0}").format(action))
	outcome = WORKFLOW[action](task, args)
	return {"outcome": outcome, "task": get_task(task)}


# Part 2 registers more tools on import (kept in its own module for size).
from infintrix_atlas.mcp import tools_extra  # noqa: E402,F401
