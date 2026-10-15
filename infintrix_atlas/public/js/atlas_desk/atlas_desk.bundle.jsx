import * as React from "react";
import { createRoot } from "react-dom/client";
import { ProjectsPage } from "./pages/ProjectsPage";
import { TasksPage } from "./pages/TasksPage";

// Desk page name -> React page. Each Desk page in infintrix_atlas/page/ mounts one of these.
const PAGES = {
	"atlas-projects": ProjectsPage,
	"atlas-tasks": TasksPage,
};

/** Mount (idempotently) the React page for a Desk page wrapper. */
function mount_atlas_page(wrapper, name) {
	const el = $(wrapper).find(".layout-main-section").get(0);
	const Page = PAGES[name];
	if (!el || !Page) return;
	if (!el.__atlas_root) {
		el.innerHTML = "";
		el.__atlas_root = createRoot(el);
	}
	el.__atlas_root.render(<Page />);
}

frappe.provide("frappe.ui");
frappe.ui.mount_atlas_page = mount_atlas_page;
