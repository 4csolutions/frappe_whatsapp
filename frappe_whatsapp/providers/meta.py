import frappe
import json
from frappe.integrations.utils import make_post_request
from frappe_whatsapp.providers.base import WhatsAppProvider

class MetaProvider(WhatsAppProvider):
    def get_headers(self):
        token = self.account.get_password("token")
        return {
            "authorization": f"Bearer {token}",
            "content-type": "application/json",
        }

    def get_base_url(self):
        return f"{self.account.url}/{self.account.version}/{self.account.phone_id}/messages"

    def send_text(self, to_number, message, **kwargs):
        data = {
            "messaging_product": "whatsapp",
            "to": self.format_number(to_number),
            "type": "text",
            "text": {"preview_url": True, "body": message}
        }
        
        reply_to_message_id = kwargs.get("reply_to_message_id")
        if reply_to_message_id:
            data["context"] = {"message_id": reply_to_message_id}

        return self._make_request(data)

    def send_media(self, to_number, media_url, media_type, caption=None, **kwargs):
        if media_url and not media_url.startswith("http"):
            media_url = frappe.utils.get_url() + "/" + media_url

        data = {
            "messaging_product": "whatsapp",
            "to": self.format_number(to_number),
            "type": media_type,
        }
        
        media_data = {"link": media_url}
        if caption and media_type in ["image", "video", "document"]:
            media_data["caption"] = caption
            
        data[media_type] = media_data

        reply_to_message_id = kwargs.get("reply_to_message_id")
        if reply_to_message_id:
            data["context"] = {"message_id": reply_to_message_id}

        return self._make_request(data)

    def send_template(self, to_number, template_name, language_code, components, **kwargs):
        data = {
            "messaging_product": "whatsapp",
            "to": self.format_number(to_number),
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
                "components": components,
            },
        }
        return self._make_request(data)

    def send_interactive(self, to_number, interactive_data, **kwargs):
        data = {
            "messaging_product": "whatsapp",
            "to": self.format_number(to_number),
            "type": "interactive",
            "interactive": interactive_data
        }
        reply_to_message_id = kwargs.get("reply_to_message_id")
        if reply_to_message_id:
            data["context"] = {"message_id": reply_to_message_id}
            
        return self._make_request(data)

    def send_reaction(self, to_number, message_id, emoji):
        data = {
            "messaging_product": "whatsapp",
            "to": self.format_number(to_number),
            "type": "reaction",
            "reaction": {
                "message_id": message_id,
                "emoji": emoji,
            }
        }
        return self._make_request(data)

    def send_read_receipt(self, message_id):
        data = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id
        }
        return self._make_request(data)

    def upload_media(self, file_url):
        # Meta allows sending by URL, so we can just return the URL for now.
        # Alternatively, we could upload via Meta's Media API, but URL is standard.
        return file_url

    def register_webhook(self, webhook_url):
        # Meta webhooks are configured in the Facebook Developer App console.
        # It's not easily automatable via API for standard users.
        frappe.msgprint("Webhook registration for Meta must be done manually in the Facebook Developer Console.")
        return False

    def get_qrcode(self):
        return None

    def get_status(self):
        # Meta doesn't have a simple status endpoint for the phone number like Baileys.
        # We assume it's connected if we have tokens.
        return "Connected"

    def supports_templates(self):
        return True

    def supports_qrcode(self):
        return False

    def create_template(self, data):
        url = f"{self.account.url}/{self.account.version}/{self.account.business_id}/message_templates"
        return self._make_request(data, endpoint=url)

    def update_template(self, template_id, data):
        url = f"{self.account.url}/{self.account.version}/{template_id}"
        return self._make_request(data, endpoint=url)

    def delete_template(self, name):
        url = f"{self.account.url}/{self.account.version}/{self.account.business_id}/message_templates?name={name}"
        try:
            from frappe.integrations.utils import make_request
            return make_request("DELETE", url, headers=self.get_headers())
        except Exception as e:
            if hasattr(frappe.flags, "integration_request") and hasattr(frappe.flags.integration_request, "json"):
                res = frappe.flags.integration_request.json().get("error", {})
                if res.get("error_user_title") == "Message Template Not Found":
                    return True
            raise e

    def fetch_templates(self):
        url = f"{self.account.url}/{self.account.version}/{self.account.business_id}/message_templates"
        from frappe.integrations.utils import make_request
        try:
            response = make_request("GET", url, headers=self.get_headers())
            return response.get("data", [])
        except Exception as e:
            frappe.log_error("Meta fetch_templates Error", str(e))
            return []

    def upload_template_media(self, file_url):
        import mimetypes
        import requests

        # Read file
        if file_url.startswith(('http://', 'https://')):
            response = requests.get(file_url, timeout=30)
            response.raise_for_status()
            file_content = response.content
            file_size = len(file_content)
            content_type = response.headers.get('Content-Type', '').split(';')[0].strip()
            file_type = content_type or mimetypes.guess_type(file_url)[0] or 'application/octet-stream'
        else:
            file_doc = frappe.get_doc("File", {"file_url": file_url})
            file_content = file_doc.get_content()
            file_type, _ = mimetypes.guess_type(file_url)
            if not file_type:
                file_type = 'application/octet-stream'
            file_size = len(file_content)

        # 1. Get Session ID
        payload = {
            'file_length': file_size,
            'file_type': file_type,
            'messaging_product': 'whatsapp'
        }
        session_url = f"{self.account.url}/{self.account.version}/{self.account.app_id}/uploads"
        session_resp = self._make_request(payload, endpoint=session_url)
        session_id = session_resp.get('id')

        # 2. Upload Media
        upload_url = f"{self.account.url}/{self.account.version}/{session_id}"
        upload_headers = {"authorization": f"OAuth {self.account.get_password('token')}"}
        
        try:
            from frappe.integrations.utils import make_post_request
            upload_resp = make_post_request(upload_url, headers=upload_headers, data=file_content)
            return upload_resp.get('h')
        except Exception as e:
            frappe.log_error("Meta upload_template_media Error", str(e))
            raise e

    def _make_request(self, data, endpoint=None):
        try:
            url = endpoint or self.get_base_url()
            response = make_post_request(
                url,
                headers=self.get_headers(),
                data=json.dumps(data)
            )
            return response
        except Exception as e:
            res = frappe.flags.integration_request.json().get("error", {}) if hasattr(frappe.flags, "integration_request") and hasattr(frappe.flags.integration_request, "json") else {}
            error_message = res.get("error_user_msg", res.get("Error", res.get("message"))) or str(e)
            
            # Log to the new event log instead of old notification log
            if frappe.db.exists("DocType", "WhatsApp Event Log"):
                frappe.get_doc({
                    "doctype": "WhatsApp Event Log",
                    "provider": "Meta",
                    "event_type": "OUTGOING_ERROR",
                    "payload": json.dumps(frappe.flags.integration_request.json() if hasattr(frappe.flags, "integration_request") and hasattr(frappe.flags.integration_request, "json") else {}),
                    "status": "Failed",
                    "error": str(error_message)
                }).insert(ignore_permissions=True)
                
            frappe.throw(msg=error_message, title=res.get("error_user_title", "WhatsApp Meta API Error"))
