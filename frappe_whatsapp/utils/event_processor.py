import frappe
import json
from frappe_whatsapp.providers.factory import get_provider

def process_incoming_event(event_log_name):
    """Background worker to process raw webhook events."""
    event_log = frappe.get_doc("WhatsApp Event Log", event_log_name)
    
    if event_log.status != "Pending":
        return
        
    try:
        payload = json.loads(event_log.payload)
        
        if event_log.provider == "Meta":
            _process_meta_payload(payload)
        elif event_log.provider == "Evolution API":
            _process_evolution_payload(payload)
            
        event_log.db_set("status", "Processed")
    except Exception as e:
        frappe.log_error("WhatsApp Event Processing Failed", str(e))
        event_log.db_set("status", "Failed")
        event_log.db_set("error", str(e))

def _process_meta_payload(data):
    """Extracted from original webhook.py"""
    messages = []
    phone_id = None
    try:
        messages = data["entry"][0]["changes"][0]["value"].get("messages", [])
        phone_id = data.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {}).get("metadata", {}).get("phone_number_id")
    except KeyError:
        messages = data.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {}).get("messages", [])

    sender_profile_name = next(
        (
            contact.get("profile", {}).get("name")
            for entry in data.get("entry", [])
            for change in entry.get("changes", [])
            for contact in change.get("value", {}).get("contacts", [])
        ),
        None,
    )

    whatsapp_account = frappe.db.get_value("WhatsApp Account", {"phone_id": phone_id}) if phone_id else None

    if messages and not whatsapp_account:
        return

    if messages:
        for message in messages:
            # Route to original logic in message doctype or handle here
            # To keep things simple, we'll recreate the logic here but cleaner
            message_type = message.get('type')
            is_reply = True if message.get('context') and 'forwarded' not in message.get('context') else False
            reply_to_message_id = message['context']['id'] if is_reply else None
            
            # The original logic created WhatsApp Message docs and fetched media
            # Since this is now in a queue, we can just do that directly
            
            doc_data = {
                "doctype": "WhatsApp Message",
                "type": "Incoming",
                "from": message.get('from'),
                "message_id": message.get('id'),
                "reply_to_message_id": reply_to_message_id,
                "is_reply": is_reply,
                "content_type": message_type,
                "profile_name": sender_profile_name,
                "whatsapp_account": whatsapp_account
            }

            if message_type == 'text':
                doc_data["message"] = message['text']['body']
                
            elif message_type == 'reaction':
                doc_data["message"] = message['reaction']['emoji']
                doc_data["reply_to_message_id"] = message['reaction']['message_id']
                
            elif message_type == 'interactive':
                interactive_data = message['interactive']
                interactive_type = interactive_data.get('type')

                if interactive_type == 'button_reply':
                    doc_data["message"] = interactive_data['button_reply']['id']
                    doc_data["content_type"] = "button"
                elif interactive_type == 'list_reply':
                    doc_data["message"] = interactive_data['list_reply']['id']
                    doc_data["content_type"] = "button"
                elif interactive_type == 'nfm_reply':
                    nfm_reply = interactive_data['nfm_reply']
                    response_json_str = nfm_reply.get('response_json', '{}')
                    try:
                        flow_response = json.loads(response_json_str)
                    except json.JSONDecodeError:
                        flow_response = {}

                    summary_parts = [f"{k}: {v}" for k, v in flow_response.items() if v]
                    doc_data["message"] = ", ".join(summary_parts) if summary_parts else "Flow completed"
                    doc_data["content_type"] = "flow"
                    doc_data["flow_response"] = json.dumps(flow_response)

                    frappe.publish_realtime(
                        "whatsapp_flow_response",
                        {
                            "phone": message.get('from'),
                            "message_id": message.get('id'),
                            "flow_response": flow_response,
                            "whatsapp_account": whatsapp_account
                        }
                    )

            elif message_type == 'order':
                doc_data["message"] = frappe._("New Order Received via WhatsApp")
                doc_data["product_catalog_json"] = json.dumps(message['order'])

            elif message_type in ["image", "audio", "video", "document"]:
                doc_data["message"] = message[message_type].get("caption", "")
                
                # Fetch Media later via Provider abstraction instead of hardcoding requests here
                provider = get_provider(whatsapp_account)
                
                if provider:
                    # In meta, media needs to be downloaded.
                    media_id = message[message_type]["id"]
                    # We can define `download_media` on provider
                    file_url = provider.download_media(media_id, message.get('from'))
                    if file_url:
                        doc_data["attach"] = file_url

            elif message_type == "button":
                doc_data["message"] = message['button']['text']
            else:
                doc_data["message"] = message.get(message_type, {}).get(message_type, "")

            frappe.get_doc(doc_data).insert(ignore_permissions=True)

    else:
        # It's a status update
        try:
            changes = data["entry"][0]["changes"][0]
            _update_meta_status(changes)
        except (KeyError, IndexError):
            pass

def _update_meta_status(data):
    if data.get("field") == "message_template_status_update":
        frappe.db.sql(
            """UPDATE `tabWhatsApp Templates`
            SET status = %(event)s
            WHERE id = %(message_template_id)s""",
            data['value']
        )
    elif data.get("field") == "messages":
        try:
            status_data = data['value']['statuses'][0]
            msg_id = status_data['id']
            status = status_data['status'] # Meta statuses: sent, delivered, read, failed
            
            status_map = {
                "sent": "Sent",
                "delivered": "Delivered",
                "read": "Read",
                "failed": "Failed"
            }
            unified_status = status_map.get(status, status.capitalize())

            name = frappe.db.get_value("WhatsApp Message", filters={"message_id": msg_id})
            if name:
                doc = frappe.get_doc("WhatsApp Message", name)
                doc.status = unified_status
                if status_data.get('conversation'):
                    doc.conversation_id = status_data['conversation'].get('id')
                doc.save(ignore_permissions=True)
        except (KeyError, IndexError):
            pass

def _process_evolution_payload(data):
    """Process payload from Evolution API webhook"""
    event_name = data.get("event")
    instance = data.get("instance")
    
    if not instance:
        return
        
    whatsapp_account = frappe.db.get_value("WhatsApp Account", {"evolution_instance_name": instance})
    if not whatsapp_account:
        return
        
    if event_name == "messages.upsert":
        msg_data = data.get("data", {})
        if isinstance(msg_data, list):
            msg_data = msg_data[0]
            
        # Evolution message parsing (handles both flattened and nested 'message' structures)
        if "key" not in msg_data and "message" in msg_data:
            msg_data = msg_data["message"]

        key = msg_data.get("key", {})
        from_me = key.get("fromMe", False)
        
        if from_me: # We only care about incoming
            return
            
        message_id = key.get("id")
        remote_jid = key.get("remoteJid", "")
        sender = remote_jid.split("@")[0]
        
        if not sender:
            return
            
        push_name = msg_data.get("pushName", "")
        
        msg_content = msg_data.get("message", {})
        message_type = list(msg_content.keys())[0] if msg_content else "unknown"
        
        doc_data = {
            "doctype": "WhatsApp Message",
            "type": "Incoming",
            "from": sender,
            "message_id": message_id,
            "profile_name": push_name,
            "whatsapp_account": whatsapp_account,
            "content_type": message_type
        }
        
        if message_type == "conversation":
            doc_data["message"] = msg_content.get("conversation")
            doc_data["content_type"] = "text"
        elif message_type == "extendedTextMessage":
            doc_data["message"] = msg_content.get("extendedTextMessage", {}).get("text")
            doc_data["content_type"] = "text"
            
            context = msg_content.get("extendedTextMessage", {}).get("contextInfo", {})
            if context.get("stanzaId"):
                doc_data["reply_to_message_id"] = context.get("stanzaId")
                doc_data["is_reply"] = True
                
        elif message_type in ["imageMessage", "videoMessage", "documentMessage", "audioMessage"]:
            caption = msg_content.get(message_type, {}).get("caption", "")
            doc_data["message"] = caption or f"[{message_type}]"
            
            media_type_map = {
                "imageMessage": "image",
                "videoMessage": "video",
                "documentMessage": "document",
                "audioMessage": "audio"
            }
            doc_data["content_type"] = media_type_map.get(message_type, "document")
            
            # Evolution API provides base64 in the webhook sometimes, or requires fetching
            base64_data = msg_data.get("base64")
            
            provider = get_provider(whatsapp_account)
            
            if not base64_data and hasattr(provider, "download_media_from_message"):
                message_obj = {
                    "key": key,
                    "message": msg_content
                }
                base64_data = provider.download_media_from_message(message_obj)
                
            if base64_data:
                file_url = provider.save_base64_media(base64_data, message_type, sender)
                if file_url:
                    doc_data["attach"] = file_url
                    
        else:
            doc_data["message"] = str(msg_content)

        if doc_data.get("message") or doc_data.get("attach"):
            frappe.get_doc(doc_data).insert(ignore_permissions=True)
            
    elif event_name == "messages.update":
        # Status update
        update_data = data.get("data", [])
        
        # Evolution API may send a list of updates or a single dict update depending on the configuration
        updates = update_data if isinstance(update_data, list) else [update_data]
        
        for update in updates:
            if not isinstance(update, dict):
                continue
                
            # It may be nested as `{"key": {"id": ...}, "update": {"status": ...}}` or flattened as `{"messageId": ..., "status": ...}`
            msg_id = update.get("key", {}).get("id") or update.get("messageId")
            status = update.get("update", {}).get("status") or update.get("status")
            
            # Integer statuses: 1: PENDING, 2: SERVER_ACK, 3: DELIVERY_ACK, 4: READ, 5: PLAYED
            # String statuses: "SERVER_ACK", "DELIVERY_ACK", "READ", "PLAYED", "ERROR"
            status_map = {
                1: "Queued",
                "PENDING": "Queued",
                2: "Sent",
                "SERVER_ACK": "Sent",
                3: "Delivered",
                "DELIVERY_ACK": "Delivered",
                4: "Read",
                "READ": "Read",
                5: "Read",
                "PLAYED": "Read",
                "ERROR": "Failed"
            }
            
            unified_status = status_map.get(status)
            if unified_status and msg_id:
                name = frappe.db.get_value("WhatsApp Message", filters={"message_id": msg_id})
                if name:
                    doc = frappe.get_doc("WhatsApp Message", name)
                    doc.status = unified_status
                    doc.save(ignore_permissions=True)
