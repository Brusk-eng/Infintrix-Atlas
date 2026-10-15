"""Number cards and chart data for the Infintrix Atlas workspace.

Counts go through `frappe.get_list`, so they respect the viewer's document permissions
(a project user only sees numbers for projects they can read).
"""

import json

import frappe
from frappe import _
from frappe.utils import add_days, cint, getdate, nowdate

DAYS = 30
CLOSED_TASK = ("Completed", "Cancelled", "Template")


def _card(value) -> dict:
	return {"value": cint(value), "fieldtype": "Int"}


def _count(doctype: str, filters) -> int:
	return len(frappe.get_list(doctype, filters=filters, pluck="name", limit_page_length=0))


def _open_tasks() -> list:
	return [["status", "not in", CLOSED_TASK]]


# --- number cards -----------------------------------------------------------


@frappe.whitelist()
def active_projects(filters=None) -> dict:
	return _card(_count("Project", {"status": "Open"}))


@frappe.whitelist()
def open_tasks(filters=None) -> dict:
	return _card(_count("Task", _open_tasks()))


@frappe.whitelist()
def my_open_tasks(filters=None) -> dict:
	me = frappe.session.user
	return _card(_count("Task", _open_tasks() + [["_assign", "like", f"%{me}%"]]))


@frappe.whitelist()
def overdue_tasks(filters=None) -> dict:
	return _card(_count("Task", _open_tasks() + [["exp_end_date", "<", nowdate()]]))


@frappe.whitelist()
def tasks_in_review(filters=None) -> dict:
	return _card(_count("Task", {"status": "Pending Review"}))


@frappe.whitelist()
def completed_this_week(filters=None) -> dict:
	return _card(_count("Task", {"status": "Completed", "modified": [">=", add_days(nowdate(), -7)]}))


@frappe.whitelist()
def active_cycles(filters=None) -> dict:
	return _card(_count("Cycle", {"status": "Active"}))


@frappe.whitelist()
def open_change_requests(filters=None) -> dict:
	return _card(_count("Change Request", {"status": ["in", ["Draft", "Under Review"]]}))


@frappe.whitelist()
def draft_requirements(filters=None) -> dict:
	return _card(_count("Requirement", {"status": "Draft"}))


# --- chart metrics ----------------------------------------------------------


def _chart(labels: list, datasets: list[tuple[str, list]]) -> dict:
	return {"labels": labels, "datasets": [{"name": name, "values": values} for name, values in datasets]}


def _grouped(doctype: str, field: str, name: str, filters=None, fallback="Not set", limit=0) -> dict:
	rows = frappe.get_list(
		doctype,
		filters=filters or {},
		fields=[field, {"COUNT": "name", "as": "count"}],
		group_by=field,
		order_by="count desc",
		limit_page_length=limit,
	)
	return _chart([str(r.get(field) or fallback) for r in rows], [(name, [r["count"] for r in rows])])


def tasks_by_status() -> dict:
	return _grouped("Task", "status", _("Tasks"))


def tasks_by_priority() -> dict:
	return _grouped("Task", "priority", _("Open tasks"), _open_tasks())


def open_tasks_by_project() -> dict:
	return _grouped("Task", "project", _("Open tasks"), _open_tasks(), _("No project"), limit=10)


def projects_by_status() -> dict:
	return _grouped("Project", "status", _("Projects"))


def requirements_by_status() -> dict:
	return _grouped("Requirement", "status", _("Requirements"))


def tasks_completed_by_day() -> dict:
	start = getdate(add_days(nowdate(), -(DAYS - 1)))
	days = [add_days(start, i) for i in range(DAYS)]
	modified = frappe.get_list(
		"Task",
		filters={"status": "Completed", "modified": [">=", f"{days[0]} 00:00:00"]},
		pluck="modified",
		limit_page_length=0,
	)
	by_day: dict[str, int] = {}
	for stamp in modified:
		key = str(getdate(stamp))
		by_day[key] = by_day.get(key, 0) + 1
	return _chart(
		[d.strftime("%d %b") for d in days],
		[(_("Completed"), [by_day.get(str(d), 0) for d in days])],
	)


METRICS = {
	"tasks_by_status": tasks_by_status,
	"tasks_by_priority": tasks_by_priority,
	"open_tasks_by_project": open_tasks_by_project,
	"projects_by_status": projects_by_status,
	"requirements_by_status": requirements_by_status,
	"tasks_completed_by_day": tasks_completed_by_day,
}


def get_chart(metric: str | None) -> dict:
	fn = METRICS.get(metric or "")
	if not fn:
		frappe.throw(_("Unknown Atlas chart metric: {0}").format(metric))
	return fn()
