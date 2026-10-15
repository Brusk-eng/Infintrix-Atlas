import * as React from "react";
import { listProjects, listTasks, route } from "../api";
import { PageState } from "../components/PageState";

const COLUMNS = ["Open", "Working", "Pending Review", "Overdue", "Completed"];

function assignees(task) {
	try {
		return JSON.parse(task._assign || "[]");
	} catch (e) {
		return [];
	}
}

export function TasksPage() {
	const [project, set_project] = React.useState("");
	const [search, set_search] = React.useState("");
	const [mine, set_mine] = React.useState(false);
	const [projects, set_projects] = React.useState([]);
	const [state, set_state] = React.useState({ rows: [], loading: true, error: null });

	React.useEffect(() => {
		listProjects({ status: "Open" }, 200)
			.then((rows) => set_projects(rows || []))
			.catch(() => {});
	}, []);

	React.useEffect(() => {
		let alive = true;
		set_state((s) => ({ ...s, loading: true }));
		const timer = setTimeout(() => {
			listTasks({ project, search })
				.then((rows) => alive && set_state({ rows: rows || [], loading: false, error: null }))
				.catch((e) => alive && set_state({ rows: [], loading: false, error: e.message }));
		}, 200);
		return () => {
			alive = false;
			clearTimeout(timer);
		};
	}, [project, search]);

	const rows = mine ? state.rows.filter((t) => assignees(t).includes(frappe.session.user)) : state.rows;
	const by_status = (status) => rows.filter((t) => t.status === status);

	return (
		<div className="atlas-page">
			<div className="atlas-toolbar">
				<input
					className="form-control input-sm"
					placeholder={__("Search tasks…")}
					value={search}
					onChange={(e) => set_search(e.target.value)}
				/>
				<select className="form-control input-sm" value={project} onChange={(e) => set_project(e.target.value)}>
					<option value="">{__("All projects")}</option>
					{projects.map((p) => (
						<option key={p.name} value={p.name}>
							{p.project_name || p.name}
						</option>
					))}
				</select>
				<label className="atlas-check">
					<input type="checkbox" checked={mine} onChange={(e) => set_mine(e.target.checked)} /> {__("Assigned to me")}
				</label>
				<button className="btn btn-primary btn-sm" onClick={() => frappe.new_doc("Task", project ? { project } : {})}>
					{__("New Task")}
				</button>
			</div>
			<PageState loading={state.loading} error={state.error} empty={!rows.length} emptyText={__("No tasks found")}>
				<div className="atlas-board">
					{COLUMNS.map((status) => {
						const tasks = by_status(status);
						return (
							<section key={status} className="atlas-col">
								<header>
									{__(status)} <span className="atlas-count">{tasks.length}</span>
								</header>
								{tasks.map((t) => (
									<button key={t.name} className="atlas-task" onClick={() => route("Task", t.name)}>
										<div className="atlas-task__subject">{t.subject}</div>
										<div className="atlas-task__meta">
											<span>{t.priority}</span>
											{t.custom_story_points ? <span>{t.custom_story_points} pts</span> : null}
											{t.exp_end_date ? <span>{frappe.datetime.str_to_user(t.exp_end_date)}</span> : null}
										</div>
									</button>
								))}
							</section>
						);
					})}
				</div>
			</PageState>
		</div>
	);
}
