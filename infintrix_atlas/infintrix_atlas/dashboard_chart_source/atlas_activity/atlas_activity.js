frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Atlas Activity"] = {
	method: "infintrix_atlas.infintrix_atlas.dashboard_chart_source.atlas_activity.atlas_activity.get",
	filters: [
		{
			fieldname: "metric",
			label: __("Metric"),
			fieldtype: "Select",
			options: [
				"tasks_by_status",
				"tasks_by_priority",
				"open_tasks_by_project",
				"projects_by_status",
				"requirements_by_status",
				"tasks_completed_by_day",
			],
			default: "tasks_by_status",
			reqd: 1,
		},
	],
};
