"""Model Context Protocol server for Infintrix Atlas (streamable HTTP, stateless JSON responses).

Endpoint:  POST /api/method/infintrix_atlas.mcp.server.handle

Authentication is Frappe's own: `Authorization: token <api_key>:<api_secret>` or an OAuth bearer token
(Frappe publishes the OAuth discovery documents, so MCP clients such as Claude and ChatGPT connectors can
run the OAuth flow). Every tool runs as the authenticated user, so document permissions, the task
permission query and the review workflow apply exactly as they do on Desk.
"""

import json

import frappe
from frappe import _
from werkzeug.wrappers import Response

from infintrix_atlas.mcp import tools

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
SERVER_INFO = {"name": "infintrix-atlas", "title": "Infintrix Atlas", "version": "1.0.0"}
INSTRUCTIONS = (
	"Work with Infintrix Atlas projects and tasks. Use list_projects / list_tasks to find work, "
	"create_task and update_task to change it, assign_task to set the assignee, and task_workflow "
	"for status changes (start, submit for review, approve, ...). Status cannot be edited directly."
)


def _json(payload, status=200, extra_headers=None) -> Response:
	response = Response(json.dumps(payload, default=str), status=status, mimetype="application/json")
	for key, value in (extra_headers or {}).items():
		response.headers[key] = value
	return response


def _error(request_id, code, message, status=200) -> Response:
	return _json({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}, status)


def _unauthorized() -> Response:
	from frappe.app import set_authenticate_headers

	response = _json({"error": "unauthorized", "message": _("Authentication required")}, 401)
	set_authenticate_headers(response)
	return response


def _dispatch(message: dict):
	"""Return a JSON-RPC response dict, or None for notifications."""
	request_id = message.get("id")
	method = message.get("method")
	params = message.get("params") or {}

	if request_id is None:  # notification (e.g. notifications/initialized)
		return None

	if method == "initialize":
		wanted = params.get("protocolVersion")
		version = wanted if wanted in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
		result = {
			"protocolVersion": version,
			"capabilities": {"tools": {"listChanged": False}},
			"serverInfo": SERVER_INFO,
			"instructions": INSTRUCTIONS,
		}
	elif method == "ping":
		result = {}
	elif method == "tools/list":
		result = {"tools": tools.definitions()}
	elif method == "tools/call":
		result = _call_tool(params.get("name"), params.get("arguments") or {})
	else:
		return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}

	return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _call_tool(name: str, arguments: dict) -> dict:
	tool = tools.TOOLS.get(name)
	if not tool:
		return {"isError": True, "content": [{"type": "text", "text": f"Unknown tool: {name}"}]}
	try:
		data = tool["fn"](**arguments)
		frappe.db.commit()  # nosemgrep -- tool writes must persist; the response is not a normal /api/method write
	except TypeError as e:
		frappe.db.rollback()
		return {"isError": True, "content": [{"type": "text", "text": f"Invalid arguments: {e}"}]}
	except Exception as e:
		frappe.db.rollback()
		if not isinstance(e, frappe.ValidationError | frappe.PermissionError | frappe.DoesNotExistError):
			frappe.log_error(title="Atlas MCP tool error")
		message = frappe.local.message_log[-1] if frappe.local.message_log else None
		text = _plain_error(message) or str(e)
		frappe.local.message_log = []
		return {"isError": True, "content": [{"type": "text", "text": text}]}
	return {
		"content": [{"type": "text", "text": json.dumps(data, default=str, indent=1)}],
		"structuredContent": data if isinstance(data, dict) else {"result": data},
	}


def _plain_error(message) -> str | None:
	if not message:
		return None
	try:
		parsed = json.loads(message) if isinstance(message, str) else message
		return frappe.utils.strip_html_tags(parsed.get("message", "")) or None
	except Exception:
		return None


@frappe.whitelist(allow_guest=True, methods=["POST", "GET", "DELETE"])
def handle():
	request = frappe.request
	if frappe.session.user == "Guest":
		return _unauthorized()
	if request.method != "POST":
		# No server-initiated stream and no sessions to terminate.
		return Response(status=405, headers={"Allow": "POST"})

	try:
		body = json.loads(request.get_data(as_text=True) or "null")
	except ValueError:
		return _error(None, -32700, "Parse error")

	batch = isinstance(body, list)
	messages = body if batch else [body]
	if not messages or not all(isinstance(m, dict) for m in messages):
		return _error(None, -32600, "Invalid request")

	responses = [r for r in (_dispatch(m) for m in messages) if r is not None]
	if not responses:
		return Response(status=202)
	return _json(responses if batch else responses[0])
