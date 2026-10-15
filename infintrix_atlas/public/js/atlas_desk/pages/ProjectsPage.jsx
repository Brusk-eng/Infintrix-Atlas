import * as React from "react";
import { listProjects, route } from "../api";
import { PageState } from "../components/PageState";

const STATUSES = ["Open", "Completed", "Cancelled"];

export function ProjectsPage() {
	const [status, set_status] = React.useState("Open");
	const [search, set_search] = React.useState("");
	const [state, set_state] = React.useState({ rows: [], loading: true, error: null });

	React.useEffect(() => {
		let alive = true;
		set_state((s) => ({ ...s, loading: true }));
		listProjects(status ? { status } : {})
			.then((rows) => alive && set_state({ rows: rows || [], loading: false, error: null }))
			.catch((e) => alive && set_state({ rows: [], loading: false, error: e.message }));
		return () => {
			alive = false;
		};
	}, [status]);

	const rows = state.rows.filter((p) =>
		(p.project_name || p.name).toLowerCase().includes(search.trim().toLowerCase())
	);

	return (
		<div className="atlas-page">
			<div className="atlas-toolbar">
				<input
					className="form-control input-sm"
					placeholder={__("Search projects…")}
					value={search}
					onChange={(e) => set_search(e.target.value)}
				/>
				<select className="form-control input-sm" value={status} onChange={(e) => set_status(e.target.value)}>
					<option value="">{__("All statuses")}</option>
					{STATUSES.map((s) => (
						<option key={s} value={s}>
							{__(s)}
						</option>
					))}
				</select>
				<button className="btn btn-primary btn-sm" onClick={() => frappe.new_doc("Project")}>
					{__("New Project")}
				</button>
			</div>
			<PageState loading={state.loading} error={state.error} empty={!rows.length} emptyText={__("No projects found")}>
				<div className="atlas-grid">
					{rows.map((p) => {
						const pct = Math.round(p.percent_complete || 0);
						return (
							<button key={p.name} className="atlas-card" onClick={() => route("Project", p.name)}>
								<div className="atlas-card__title">{p.project_name || p.name}</div>
								<div className="atlas-card__sub">
									{p.project_type || __("No type")} · {__(p.status)}
								</div>
								<div className="atlas-progress" aria-label={`${pct}%`}>
									<span style={{ width: `${pct}%` }} />
								</div>
								<div className="atlas-card__meta">
									<span>{pct}%</span>
									<span>{frappe.datetime.prettyDate(p.modified)}</span>
								</div>
							</button>
						);
					})}
				</div>
			</PageState>
		</div>
	);
}
