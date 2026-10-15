import * as React from "react";

/** Loading / error / empty wrapper shared by the Atlas Desk pages. */
export function PageState({ loading, error, empty, emptyText, children }) {
	if (loading) return <div className="atlas-state">{__("Loading…")}</div>;
	if (error) return <div className="atlas-state atlas-state--error">{error}</div>;
	if (empty) return <div className="atlas-state">{emptyText}</div>;
	return children;
}
