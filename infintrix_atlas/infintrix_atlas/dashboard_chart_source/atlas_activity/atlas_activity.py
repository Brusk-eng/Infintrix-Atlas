"""Chart source behind every chart on the Infintrix Atlas workspace; the `metric` filter picks the series."""

import frappe

from infintrix_atlas.api.dashboard import get_chart


@frappe.whitelist()
def get(
	chart_name: str | None = None,
	chart: str | dict | None = None,
	no_cache: bool | int | None = None,
	filters: str | dict | list | None = None,
	from_date: str | None = None,
	to_date: str | None = None,
	timespan: str | None = None,
	time_interval: str | None = None,
	heatmap_year: str | int | None = None,
) -> dict:
	if chart_name:
		chart = frappe.get_doc("Dashboard Chart", chart_name)
	else:
		chart = frappe._dict(frappe.parse_json(chart or {}))
	filters = frappe.parse_json(filters) or frappe.parse_json(chart.get("filters_json")) or {}
	return get_chart(filters.get("metric") if isinstance(filters, dict) else None)
