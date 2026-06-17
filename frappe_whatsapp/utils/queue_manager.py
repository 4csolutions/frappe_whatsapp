import frappe
import json
from frappe_whatsapp.providers.factory import get_provider

def send_queued_message(message_id):
    """Background worker to send a queued WhatsApp Message."""
    try:
        msg_doc = frappe.get_doc("WhatsApp Message", message_id)
        if msg_doc.status != "Queued":
            return

        provider = get_provider(msg_doc.whatsapp_account)

        # Handle Template messages
        if msg_doc.message_type == "Template" or msg_doc.template:
            _send_template_message(msg_doc, provider)
        else:
            _send_standard_message(msg_doc, provider)

    except Exception as e:
        frappe.log_error("WhatsApp Send Failed", str(e))
        frappe.db.set_value("WhatsApp Message", message_id, "status", "Failed")


def _send_standard_message(msg_doc, provider):
    kwargs = {}
    if msg_doc.is_reply and msg_doc.reply_to_message_id:
        kwargs["reply_to_message_id"] = msg_doc.reply_to_message_id

    try:
        if msg_doc.content_type == "text":
            res = provider.send_text(msg_doc.to, msg_doc.message, **kwargs)
            _handle_response(msg_doc, res)

        elif msg_doc.content_type in ["image", "video", "document", "audio"]:
            res = provider.send_media(msg_doc.to, msg_doc.attach, msg_doc.content_type, caption=msg_doc.message, **kwargs)
            _handle_response(msg_doc, res)

        elif msg_doc.content_type == "reaction":
            res = provider.send_reaction(msg_doc.to, msg_doc.reply_to_message_id, msg_doc.message)
            _handle_response(msg_doc, res)
            
        elif msg_doc.content_type == "interactive":
            if hasattr(provider, "send_interactive"):
                buttons_data = json.loads(msg_doc.buttons) if isinstance(msg_doc.buttons, str) else msg_doc.buttons
                interactive_payload = {
                    "type": "button",
                    "body": {"text": msg_doc.message},
                    "action": {
                        "buttons": [
                            {
                                "type": "reply",
                                "reply": {"id": btn["id"], "title": btn["title"]}
                            }
                            for btn in buttons_data[:3]
                        ]
                    }
                }
                res = provider.send_interactive(msg_doc.to, interactive_payload, **kwargs)
                _handle_response(msg_doc, res)
            else:
                raise NotImplementedError("Interactive messages not supported by this provider yet.")
                
        else:
            raise NotImplementedError(f"Content type {msg_doc.content_type} not supported yet.")
            
    except Exception as e:
        msg_doc.db_set("status", "Failed")
        raise e


def _send_template_message(msg_doc, provider):
    try:
        template = frappe.get_doc("WhatsApp Templates", msg_doc.template)
        template_name = template.actual_name or template.template_name
        
        components = []
        parameters = []
        
        # Load body parameters
        if template.sample_values:
            field_names = template.field_names.split(",") if template.field_names else template.sample_values.split(",")

            if msg_doc.body_param is not None:
                params = list(json.loads(msg_doc.body_param).values())
                for param in params:
                    parameters.append({"type": "text", "text": param})
            elif msg_doc.reference_doctype and msg_doc.reference_name:
                ref_doc = frappe.get_doc(msg_doc.reference_doctype, msg_doc.reference_name)
                for field_name in field_names:
                    value = ref_doc.get_formatted(field_name.strip())
                    parameters.append({"type": "text", "text": value})

        if parameters:
            components.append({
                "type": "body",
                "parameters": parameters,
            })

        # Load header
        if template.header_type:
            if msg_doc.attach:
                if msg_doc.attach.startswith("http"):
                    url = msg_doc.attach
                else:
                    url = f'{frappe.utils.get_url()}{msg_doc.attach}'
                    
                if template.header_type == 'IMAGE':
                    components.append({
                        "type": "header",
                        "parameters": [{"type": "image", "image": {"link": url}}]
                    })
                elif template.header_type == 'DOCUMENT':
                    components.append({
                        "type": "header",
                        "parameters": [{"type": "document", "document": {"link": url, "filename": "document.pdf"}}]
                    })

        # Load buttons
        if template.buttons:
            button_parameters = []
            for idx, btn in enumerate(template.buttons):
                if btn.button_type == "Quick Reply":
                    button_parameters.append({
                        "type": "button",
                        "sub_type": "quick_reply",
                        "index": str(idx),
                        "parameters": [{"type": "payload", "payload": btn.button_label}]
                    })
                elif btn.button_type == "Visit Website" and btn.url_type == "Dynamic":
                    ref_doc = frappe.get_doc(msg_doc.reference_doctype, msg_doc.reference_name)
                    url = ref_doc.get_formatted(btn.website_url)
                    button_parameters.append({
                        "type": "button",
                        "sub_type": "url",
                        "index": str(idx),
                        "parameters": [{"type": "text", "text": url}]
                    })

            if button_parameters:
                components.extend(button_parameters)
                
        res = provider.send_template(msg_doc.to, template_name, template.language_code, components)
        _handle_response(msg_doc, res)
        
    except Exception as e:
        msg_doc.db_set("status", "Failed")
        raise e


def _handle_response(msg_doc, res):
    if "messages" in res and res["messages"]:
        msg_doc.db_set("message_id", res["messages"][0].get("id"))
    msg_doc.db_set("status", "Sent")
