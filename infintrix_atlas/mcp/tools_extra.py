"""Atlas MCP tools, part 2: full CRUD over every Atlas doctype plus lifecycle actions.

Generic CRUD runs through Frappe documents as the session user, so permissions, validations and the
Task review workflow (status is never directly editable) apply. Only doctypes in ATLAS_DOCTYPES are reachable.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint

from infintrix_atlas.api import cycles as cycles_api
from infintrix_atlas.api import lifecycle, projects as projects_api, tasks as tasks_api, watchers as watchers_api
from infintrix_atlas.mcp.tools import MAX_LIMIT, _limit, _s, tool

# doctype -> access mode. "single" doctypes have no list; "no_delete" blocks deletion.
ATLAS_DOCTYPES = {
	"Project": {},
	"Task": {},
	"Task Type": {},
	"Cycle": {},
	"Requirement": {},
	"Change Request": {},
	"Scope Snapshot": {"submittable": True},
	"Project Resource": {},
	"Project Action Request": {},
	"Work Item Relationship": {},
	"AI Task Session": {},
	"AI Task Draft": {},
	"Atlas Settings": {"single": True, "no_delete": True},
	"Timesheet": {},
}
READONLY_FIELDS = {"name", "owner", "creation", "modified", "modified_by", "docstatus", "idx", "doctype"}
DOCTYPE_ENUM = list(ATLAS_DOCTYPES)


def _check_doctype(doctype: str) -> dict:
	if doctype not in ATLAS_DOCTYPES:
		frappe.throw(_("Doctype {0} is not available. Choose one of: {1}").format(doctype, ", ".join(ATLAS_DOCTYPES)))
	return ATLAS_DOCTYPES[doctype]


def _values(values) -> dict:
	if isinstance(values, str):
		values = json.loads(values or "{}")
	if not isinstance(values, dict):
		frappe.throw(_("values must be an object of fieldname: value"))
	return values


def _record(doc) -> dict:
	data = doc.as_dict(no_nulls=True)
	# Never hand secrets (API keys, tokens) to an MCP client.
	for df in doc.meta.get("fields", {"fieldtype": "Password"}):
		data.pop(df.fieldname, None)
	for key in ("owner", "modified_by", "_user_tags", "_comments", "_assign", "_liked_by", "doctype"):
		data.pop(key, None)
	return json.loads(frappe.as_json(data))


# --- discovery --------------------------------------------------------------


@tool("describe_doctype", "Show the fields (name, type, options, required) of an Atlas doctype, so create_record/update_record can be used correctly.", {"doctype": _s("Atlas doctype", enum=DOCTYPE_ENUM)}, ["doctype"], True)
def describe_doctype(doctype):
	_check_doctype(doctype)
	meta = frappe.get_meta(doctype)
	skip = {"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Heading", "Fold"}
	return {
		"doctype": doctype,
		"title_field": meta.title_field,
		"is_submittable": bool(meta.is_submittable),
		"fields": [
			{k: v for k, v in {"fieldname": f.fieldname, "label": f.label, "type": f.fieldtype, "options": f.options, "required": bool(f.reqd), "read_only": bool(f.read_only)}.items() if v not in (None, "", False)}
			for f in meta.fields
			if f.fieldtype not in skip
		],
	}


# --- generic CRUD -----------------------------------------------------------


@tool(
	"list_records",
	"List records of any Atlas doctype. filters is an object like {\"project\": \"PROJ-0001\", \"status\": \"Open\"}.",
	{
		"doctype": _s("Atlas doctype", enum=DOCTYPE_ENUM), "filters": {"type": "object"},
		"fields": {"type": "array", "items": {"type": "string"}}, "search": _s("Match on the title field / name"),
		"order_by": _s("e.g. 'modified desc'"), "limit": {"type": "integer"}, "offset": {"type": "integer"},
	},
	["doctype"],
	True,
)
def list_records(doctype, filters=None, fields=None, search=None, order_by=None, limit=20, offset=0):
	_check_doctype(doctype)
	meta = frappe.get_meta(doctype)
	if isinstance(filters, str):
		filters = json.loads(filters or "{}")
	or_filters = None
	if search:
		columns = {"name", meta.title_field} - {None}
		or_filters = [[doctype, c, "like", f"%{search}%"] for c in columns]
	return frappe.get_list(
		doctype, filters=filters or {}, or_filters=or_filters,
		fields=fields or ["name", *([meta.title_field] if meta.title_field else []), "modified"],
		order_by=order_by or "modified desc", limit_start=cint(offset), limit_page_length=_limit(limit),
	)


@tool("get_record", "Get one full record (including child tables) of any Atlas doctype.", {"doctype": _s("Atlas doctype", enum=DOCTYPE_ENUM), "name": _s("Record id (omit for Atlas Settings)")}, ["doctype"], True)
def get_record(doctype, name=None):
	mode = _check_doctype(doctype)
	doc = frappe.get_doc(doctype, doctype if mode.get("single") else name)
	doc.check_permission("read")
	return _record(doc)


@tool(
	"create_record",
	"Create a record in any Atlas doctype (project, cycle, requirement, change request, project resource, task type, ...). values is {fieldname: value}; child tables are lists of row objects. Use describe_doctype first.",
	{"doctype": _s("Atlas doctype", enum=DOCTYPE_ENUM), "values": {"type": "object"}},
	["doctype", "values"],
)
def create_record(doctype, values):
	mode = _check_doctype(doctype)
	if mode.get("single"):
		frappe.throw(_("{0} is a single doctype; use update_record").format(doctype))
	doc = frappe.get_doc({"doctype": doctype, **_values(values)})
	doc.insert()
	return _record(doc)


@tool(
	"update_record",
	"Update fields on any Atlas record. Task status is changed only via task_workflow; child tables passed here replace the existing rows.",
	{"doctype": _s("Atlas doctype", enum=DOCTYPE_ENUM), "name": _s("Record id (omit for Atlas Settings)"), "values": {"type": "object"}},
	["doctype", "values"],
)
def update_record(doctype, values, name=None):
	mode = _check_doctype(doctype)
	values = _values(values)
	bad = READONLY_FIELDS & set(values)
	if bad:
		frappe.throw(_("Cannot set: {0}").format(", ".join(sorted(bad))))
	doc = frappe.get_doc(doctype, doctype if mode.get("single") else name)
	doc.check_permission("write")
	doc.update(values)
	doc.save()
	return _record(doc)


@tool("delete_record", "Delete a record of an Atlas doctype (subject to Frappe link checks and permissions). Irreversible.", {"doctype": _s("Atlas doctype", enum=DOCTYPE_ENUM), "name": _s("Record id")}, ["doctype", "name"])
def delete_record(doctype, name):
	mode = _check_doctype(doctype)
	if mode.get("no_delete"):
		frappe.throw(_("{0} cannot be deleted").format(doctype))
	frappe.delete_doc(doctype, name)
	return {"deleted": name, "doctype": doctype}


@tool("submit_record", "Submit (docstatus 1) or cancel (docstatus 2) a submittable Atlas record such as a Scope Snapshot.", {"doctype": _s("Atlas doctype", enum=DOCTYPE_ENUM), "name": _s("Record id"), "action": _s("submit or cancel", enum=["submit", "cancel"])}, ["doctype", "name", "action"])
def submit_record(doctype, name, action):
	if not _check_doctype(doctype).get("submittable"):
		frappe.throw(_("{0} is not submittable").format(doctype))
	doc = frappe.get_doc(doctype, name)
	getattr(doc, action)() if action in ("submit", "cancel") else frappe.throw(_("action must be submit or cancel"))
	return _record(doc)


# --- project lifecycle --------------------------------------------------------


def _outcome(result):
	if isinstance(result, dict) and result.get("success") is False:
		frappe.throw(result.get("message") or _("Action failed"))
	return result


@tool("archive_project", "Archive or unarchive a project (toggles).", {"project": _s("Project id")}, ["project"])
def archive_project(project):
	frappe.get_doc("Project", project).check_permission("write")
	return _outcome(projects_api.toggle_archive_project(project))


@tool("add_team_member", "Add a user to a project's team.", {"project": _s("Project id"), "user": _s("User id/email")}, ["project", "user"])
def add_team_member(project, user):
	frappe.get_doc("Project", project).check_permission("write")
	if not frappe.db.exists("User", {"name": user, "enabled": 1}):
		frappe.throw(_("User {0} does not exist or is disabled").format(user))
	return _outcome(projects_api.add_team_member(project, user))


@tool("remove_team_member", "Remove a user from a project's team.", {"project": _s("Project id"), "user": _s("User id/email")}, ["project", "user"])
def remove_team_member(project, user):
	frappe.get_doc("Project", project).check_permission("write")
	return _outcome(projects_api.remove_team_member(project, user))


@tool("project_metrics", "Flow metrics for a project: execution efficiency and backlog health.", {"project": _s("Project id")}, ["project"], True)
def project_metrics(project):
	frappe.get_doc("Project", project).check_permission("read")
	return projects_api.get_project_flow_metrics(project)


# --- cycles -----------------------------------------------------------------


@tool("start_cycle", "Start a planned cycle. Needs start_date and end_date; only one cycle per project can be active.", {"cycle": _s("Cycle id"), "start_date": _s("YYYY-MM-DD"), "end_date": _s("YYYY-MM-DD"), "cycle_name": _s("Optional new name")}, ["cycle", "start_date", "end_date"])
def start_cycle(cycle, start_date, end_date, cycle_name=None):
	frappe.get_doc("Cycle", cycle).check_permission("write")
	return _outcome(cycles_api.start_cycle(cycle, cycle_name=cycle_name, start_date=start_date, end_date=end_date))


@tool("complete_cycle", "Complete an active cycle; unfinished tasks move to move_tasks_to (another cycle) or back to the backlog.", {"cycle": _s("Cycle id"), "move_tasks_to": _s("Cycle id to receive unfinished tasks")}, ["cycle"])
def complete_cycle(cycle, move_tasks_to=None):
	frappe.get_doc("Cycle", cycle).check_permission("write")
	return _outcome(cycles_api.complete_cycle(cycle, move_tasks_to=move_tasks_to))


@tool("cycle_summary", "Cycles of a project with total/completed task counts.", {"project": _s("Project id")}, ["project"], True)
def cycle_summary(project):
	frappe.get_doc("Project", project).check_permission("read")
	return cycles_api.list_project_cycles(project)


@tool("move_tasks_to_cycle", "Move tasks into a cycle, or back to the backlog when cycle is empty.", {"tasks": {"type": "array", "items": {"type": "string"}}, "cycle": _s("Cycle id; omit for backlog")}, ["tasks"])
def move_tasks_to_cycle(tasks, cycle=None):
	moved = []
	for name in tasks:
		doc = frappe.get_doc("Task", name)
		doc.check_permission("write")
		doc.custom_cycle = cycle or None
		doc.save()
		moved.append(name)
	return {"moved": moved, "cycle": cycle}


# --- tasks ------------------------------------------------------------------


@tool("list_subtasks", "List the subtasks of a task.", {"task": _s("Parent task id")}, ["task"], True)
def list_subtasks(task):
	frappe.get_doc("Task", task).check_permission("read")
	return tasks_api.list_subtasks(task)


@tool("task_activity", "Change history (versions) of a task.", {"task": _s("Task id")}, ["task"], True)
def task_activity(task):
	return tasks_api.get_task_activity(task)


@tool("delete_task", "Delete a task.", {"task": _s("Task id")}, ["task"])
def delete_task(task):
	frappe.delete_doc("Task", task)
	return {"deleted": task}


@tool("bulk_assign_tasks", "Assign many tasks to one user (or 'unassigned').", {"tasks": {"type": "array", "items": {"type": "string"}}, "assignee": _s("User id, 'me' or 'unassigned'")}, ["tasks", "assignee"])
def bulk_assign_tasks(tasks, assignee):
	from infintrix_atlas.mcp.tools import assign_task

	return [{"task": t, "assignees": assign_task(t, assignee)["assignees"]} for t in tasks[:MAX_LIMIT]]


@tool("add_watcher", "Add a user as watcher of a task or project.", {"doctype": _s("Task or Project", enum=["Task", "Project"]), "name": _s("Record id"), "user": _s("User id/email")}, ["doctype", "name", "user"])
def add_watcher(doctype, name, user):
	return _outcome(watchers_api.add_watcher(doctype, name, user))


@tool("remove_watcher", "Remove a watcher from a task or project.", {"doctype": _s("Task or Project", enum=["Task", "Project"]), "name": _s("Record id"), "user": _s("User id/email")}, ["doctype", "name", "user"])
def remove_watcher(doctype, name, user):
	return _outcome(watchers_api.remove_watcher(doctype, name, user))


@tool("list_watchers", "List watchers of a task or project.", {"doctype": _s("Task or Project", enum=["Task", "Project"]), "name": _s("Record id")}, ["doctype", "name"], True)
def list_watchers(doctype, name):
	return watchers_api.get_watchers(doctype, name)


# --- requirements / change requests / scope / action requests ------------------


@tool("set_requirement_status", "Set a requirement's status: Draft, Approved, Rejected or Implemented.", {"requirement": _s("Requirement id"), "status": _s("Status", enum=["Draft", "Approved", "Rejected", "Implemented"])}, ["requirement", "status"])
def set_requirement_status(requirement, status):
	return lifecycle.update_requirement_status(requirement, status)


@tool("create_task_from_requirement", "Create a task from a requirement.", {"requirement": _s("Requirement id"), "subject": _s("Defaults to the requirement title"), "task_type": _s("Task Type id"), "priority": _s("Low, Medium, High, Urgent")}, ["requirement"])
def create_task_from_requirement(requirement, subject=None, task_type=None, priority="Medium"):
	return lifecycle.create_task_from_requirement(requirement, subject=subject, type=task_type, priority=priority)


@tool("change_request_action", "Move a change request: submit (for review), approve (also creates a requirement), reject or implement.", {"change_request": _s("Change Request id"), "action": _s("Action", enum=["submit", "approve", "reject", "implement"])}, ["change_request", "action"])
def change_request_action(change_request, action):
	if action == "submit":
		doc = frappe.get_doc("Change Request", change_request)
		doc.check_permission("write")
		if doc.status != "Draft":
			frappe.throw(_("Only draft change requests can be submitted for review"))
		doc.status = "Under Review"
		doc.save()
		return {"change_request": doc.name, "status": doc.status}
	handlers = {"approve": lifecycle.approve_change_request, "reject": lifecycle.reject_change_request, "implement": lifecycle.implement_change_request}
	if action not in handlers:
		frappe.throw(_("Unknown action {0}").format(action))
	return handlers[action](change_request)


@tool("create_scope_snapshot", "Freeze the project's approved/implemented requirements (or a chosen list) as a scope baseline.", {"project": _s("Project id"), "version": _s("Version label"), "requirements": {"type": "array", "items": {"type": "string"}}}, ["project"])
def create_scope_snapshot(project, version=None, requirements=None):
	return lifecycle.create_scope_snapshot(project, version=version, requirement_names=requirements)


@tool("action_request", "Project Action Request lifecycle: create, complete, reject or expire.", {
	"action": _s("Action", enum=["create", "complete", "reject", "expire"]), "request": _s("Action request id (complete/reject/expire)"),
	"project": _s("Project id (create)"), "title": _s("Title (create)"), "description": _s("Description (create)"),
	"action_type": _s("e.g. Approval (create)"), "due_date": _s("YYYY-MM-DD (create)"), "related_task": _s("Task id (create)"),
}, ["action"])
def action_request(action, request=None, project=None, title=None, description=None, action_type="Approval", due_date=None, related_task=None):
	if action == "create":
		if not (project and title and description):
			frappe.throw(_("project, title and description are required to create an action request"))
		return lifecycle.create_action_request(project, title, description, action_type=action_type, due_date=due_date, related_task=related_task)
	handlers = {"complete": lifecycle.complete_action_request, "reject": lifecycle.reject_action_request, "expire": lifecycle.expire_action_request}
	if action not in handlers or not request:
		frappe.throw(_("A valid action and request id are required"))
	return handlers[action](request)


# --- companies and linked records ----------------------------------------------

COMPANY_FIELDS = ["name", "company_name", "abbr", "default_currency", "country", "domain", "parent_company", "is_group"]


@tool("list_companies", "List companies (the Company a project and its tasks belong to), with the number of projects in each.", {"search": _s("Match on company name"), "limit": {"type": "integer"}}, read_only=True)
def list_companies(search=None, limit=50):
	or_filters = [["name", "like", f"%{search}%"], ["abbr", "like", f"%{search}%"]] if search else None
	companies = frappe.get_list("Company", or_filters=or_filters, fields=COMPANY_FIELDS, order_by="name asc", limit_page_length=_limit(limit))
	counts = {
		r["company"]: r["count"]
		for r in frappe.get_list("Project", fields=["company", {"COUNT": "name", "as": "count"}], group_by="company", limit_page_length=0)
	}
	for company in companies:
		company["projects"] = counts.get(company["name"], 0)
	return companies


@tool("get_company", "Get a company with its projects and open task count.", {"company": _s("Company name")}, ["company"], True)
def get_company(company):
	doc = frappe.get_doc("Company", company)
	doc.check_permission("read")
	return {
		**{f: doc.get(f) for f in COMPANY_FIELDS},
		"projects": frappe.get_list("Project", {"company": company}, ["name", "project_name", "status", "percent_complete"], order_by="modified desc", limit_page_length=100),
		"open_tasks": len(frappe.get_list("Task", {"company": company, "status": ["not in", ["Completed", "Cancelled", "Template"]]}, pluck="name", limit_page_length=0)),
	}


@tool("project_links", "Show every linked record of a project: company, customer, cost center, department, plus counts of tasks, cycles, requirements, change requests, resources and action requests.", {"project": _s("Project id")}, ["project"], True)
def project_links(project):
	doc = frappe.get_doc("Project", project)
	doc.check_permission("read")
	link_fields = [df for df in doc.meta.fields if df.fieldtype == "Link" and doc.get(df.fieldname)]
	linked = {df.fieldname: {"doctype": df.options, "name": doc.get(df.fieldname)} for df in link_fields}
	for key, value in linked.items():
		title = frappe.get_cached_value(value["doctype"], value["name"], frappe.get_meta(value["doctype"]).title_field or "name") if frappe.db.exists(value["doctype"], value["name"]) else None
		value["title"] = title
	counts = {}
	for dt in ("Task", "Cycle", "Requirement", "Change Request", "Scope Snapshot", "Project Resource", "Project Action Request"):
		try:
			counts[dt] = len(frappe.get_list(dt, {"project": project}, pluck="name", limit_page_length=0))
		except frappe.PermissionError:
			counts[dt] = None
	return {"project": project, "links": linked, "counts": counts, "team": [u.user for u in doc.get("users") or []]}


@tool(
	"find_link_options",
	"Look up valid values for any link field of an Atlas doctype (e.g. Project.company, Project.customer, Task.type, Task.department), so a record can be created or updated with a correct id. Respects permissions.",
	{"doctype": _s("Atlas doctype", enum=DOCTYPE_ENUM), "fieldname": _s("Link field, e.g. company"), "search": _s("Text to match"), "limit": {"type": "integer"}},
	["doctype", "fieldname"],
	True,
)
def find_link_options(doctype, fieldname, search="", limit=20):
	_check_doctype(doctype)
	field = frappe.get_meta(doctype).get_field(fieldname)
	if not field or field.fieldtype not in ("Link", "Dynamic Link"):
		frappe.throw(_("{0}.{1} is not a link field").format(doctype, fieldname))
	if field.fieldtype == "Dynamic Link":
		frappe.throw(_("{0}.{1} is a dynamic link; set its type field first").format(doctype, fieldname))
	from frappe.desk.search import search_link

	rows = search_link(field.options, search or "", page_length=_limit(limit), reference_doctype=doctype)
	return {"links_to": field.options, "options": [{"name": r.get("value"), "description": r.get("description")} for r in rows]}


@tool("list_link_fields", "List the link fields of an Atlas doctype and what each links to (company, customer, project, user, ...).", {"doctype": _s("Atlas doctype", enum=DOCTYPE_ENUM)}, ["doctype"], True)
def list_link_fields(doctype):
	_check_doctype(doctype)
	return [
		{"fieldname": f.fieldname, "label": f.label, "links_to": f.options, "required": bool(f.reqd)}
		for f in frappe.get_meta(doctype).fields
		if f.fieldtype == "Link"
	]
