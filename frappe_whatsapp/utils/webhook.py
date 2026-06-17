"""Webhook."""
import frappe
import json
from werkzeug.wrappers import Response

@frappe.whitelist(allow_guest=True)
def webhook():
    """Main Webhook Endpoint (Meta & Evolution)"""
    if frappe.request.method == "GET":
        return handle_get_verification()
    return handle_post_event()

def handle_get_verification():
    """Meta Webhook Verification"""
    hub_challenge = frappe.form_dict.get("hub.challenge")
    verify_token = frappe.form_dict.get("hub.verify_token")
    webhook_verify_token = frappe.db.get_value(
        'WhatsApp Account',
        {"webhook_verify_token": verify_token},
        'webhook_verify_token'
    )
    if not webhook_verify_token:
        frappe.throw("No matching WhatsApp account")

    if frappe.form_dict.get("hub.verify_token") != webhook_verify_token:
        frappe.throw("Verify token does not match")

    return Response(hub_challenge, status=200)

def handle_post_event():
    """Receive event, save to log, and enqueue processing."""
    try:
        # data might be form_dict or request data
        if hasattr(frappe.request, "get_data"):
            raw_data = frappe.request.get_data(as_text=True)
            data = json.loads(raw_data) if raw_data else frappe.local.form_dict
        else:
            data = frappe.local.form_dict
    except Exception:
        data = frappe.local.form_dict
        
    provider = "Unknown"
    event_type = "Unknown"

    # Identify Provider
    if "entry" in data and "object" in data and data["object"] == "whatsapp_business_account":
        provider = "Meta"
        try:
            changes = data["entry"][0]["changes"][0]
            event_type = changes.get("field", "Unknown")
        except (KeyError, IndexError):
            pass
    elif "event" in data and "instance" in data:
        provider = "Evolution API"
        event_type = data.get("event", "Unknown")

    # Insert into WhatsApp Event Log
    try:
        event_log = frappe.get_doc({
            "doctype": "WhatsApp Event Log",
            "provider": provider,
            "event_type": event_type,
            "payload": json.dumps(data),
            "status": "Pending"
        }).insert(ignore_permissions=True)
        
        # Enqueue the processing job
        frappe.enqueue(
            "frappe_whatsapp.utils.event_processor.process_incoming_event",
            queue="short",
            event_log_name=event_log.name
        )
    except Exception as e:
        frappe.log_error("Failed to insert WhatsApp Event Log", str(e))

    # Respond immediately
    return Response("OK", status=200)
