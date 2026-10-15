frappe.pages["atlas-projects"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({ parent: wrapper, title: __("Projects"), single_column: true });
};

frappe.pages["atlas-projects"].on_page_show = function (wrapper) {
	frappe.require(["atlas_desk.bundle.css", "atlas_desk.bundle.jsx"]).then(() => {
		frappe.ui.mount_atlas_page(wrapper, "atlas-projects");
	});
};
