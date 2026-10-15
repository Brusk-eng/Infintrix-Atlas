// Thin promise wrapper over frappe.call for the Atlas Desk pages.
export function call(method, args = {}) {
	return new Promise((resolve, reject) => {
		frappe.call({
			method,
			args,
			freeze: false,
			callback: (r) => resolve(r ? r.message : null),
			error: () => reject(new Error(__("Request failed"))),
		});
	});
}

export const listProjects = (filters = {}, limit = 100) =>
	call("infintrix_atlas.api.projects.list_projects", { filters, limit, offset: 0 });

export const listTasks = ({ project, status, search } = {}) => {
	const filters = [["status", "!=", "Template"]];
	if (project) filters.push(["project", "=", project]);
	if (status) filters.push(["status", "=", status]);
	if (search) filters.push(["subject", "like", `%${search}%`]);
	return call("frappe.client.get_list", {
		doctype: "Task",
		fields: ["name", "subject", "status", "priority", "project", "exp_end_date", "_assign", "custom_story_points"],
		filters,
		order_by: "modified desc",
		limit_page_length: 300,
	});
};

export const route = (doctype, name) => frappe.set_route("Form", doctype, name);
