import frappe
import json
import requests
from frappe.integrations.utils import make_post_request
from frappe_whatsapp.providers.base import WhatsAppProvider

class EvolutionProvider(WhatsAppProvider):
    def get_headers(self):
        api_key = self.account.get_password("evolution_api_key")
        return {
            "apikey": api_key,
            "content-type": "application/json",
        }

    def get_base_url(self):
        url = self.account.evolution_api_url.rstrip("/")
        instance = self.account.evolution_instance_name
        return f"{url}/message/sendText/{instance}"

    def send_text(self, to_number, message, **kwargs):
        url = f"{self.account.evolution_api_url.rstrip('/')}/message/sendText/{self.account.evolution_instance_name}"
        data = {
            "number": self.format_number(to_number),
            "text": message
        }
        
        reply_to_message_id = kwargs.get("reply_to_message_id")
        if reply_to_message_id:
            data["quoted"] = {
                "key": {
                    "id": reply_to_message_id
                }
            }

        return self._make_request(url, data)

    def send_media(self, to_number, media_url, media_type, caption=None, **kwargs):
        if media_url and not media_url.startswith("http"):
            media_url = frappe.utils.get_url() + "/" + media_url

        url = f"{self.account.evolution_api_url.rstrip('/')}/message/sendMedia/{self.account.evolution_instance_name}"
        
        # Convert to base64 if it's a Frappe PDF URL or any local URL
        media_data, mimetype, filename = self.get_base64_from_url(media_url)

        data = {
            "number": self.format_number(to_number),
            "mediatype": media_type,
            "media": media_data,
            "delay": 1200
        }
        
        if mimetype:
            data["mimetype"] = mimetype
            
        if kwargs.get("fileName") or filename:
            data["fileName"] = kwargs.get("fileName") or filename

        if caption:
            data["caption"] = caption

        reply_to_message_id = kwargs.get("reply_to_message_id")
        if reply_to_message_id:
            data["quoted"] = {
                "key": {
                    "id": reply_to_message_id
                }
            }

        return self._make_request(url, data)

    def send_template(self, to_number, template_name, language_code, components, **kwargs):
        if self.account.instance_type == "Baileys":
            return self._send_template_local(to_number, template_name, components, **kwargs)
            

        # Business integration for templates
        url = f"{self.account.evolution_api_url.rstrip('/')}/message/sendTemplate/{self.account.evolution_instance_name}"
        data = {
            "number": self.format_number(to_number),
            "name": template_name,
            "language": language_code,
            "components": components
        }
        return self._make_request(url, data)

    def _send_template_local(self, to_number, template_name, components, **kwargs):
        # Local Baileys Simulation
        template_doc = frappe.get_doc("WhatsApp Templates", {"actual_name": template_name})
        
        body_params = []
        header_url = None
        header_type = None
        filename = None
        
        for comp in components:
            if comp.get("type") == "body":
                body_params = [p.get("text", "") for p in comp.get("parameters", [])]
            elif comp.get("type") == "header":
                for p in comp.get("parameters", []):
                    if p.get("type") == "image":
                        header_url = p.get("image", {}).get("link")
                        header_type = "image"
                    elif p.get("type") == "document":
                        header_url = p.get("document", {}).get("link")
                        header_type = "document"
                        filename = p.get("document", {}).get("filename", "document.pdf")

        text = template_doc.template
        for i, val in enumerate(body_params, start=1):
            text = text.replace(f"{{{{{i}}}}}", str(val))
            
        if template_doc.footer:
            text += f"\n\n{template_doc.footer}"

        if template_doc.buttons:
            text += "\n"
            for btn in template_doc.buttons:
                if btn.button_type == "Visit Website":
                    text += f"\n* {btn.button_label}: {btn.website_url}"
                else:
                    text += f"\n* {btn.button_label}"

        if header_url:
            return self.send_media(to_number, header_url, header_type, caption=text, fileName=filename, **kwargs)
        else:
            return self.send_text(to_number, text, **kwargs)

    def send_reaction(self, to_number, message_id, emoji):
        url = f"{self.account.evolution_api_url.rstrip('/')}/message/sendReaction/{self.account.evolution_instance_name}"
        data = {
            "key": {
                "id": message_id,
                "remoteJid": self.format_number(to_number) + "@s.whatsapp.net" # Approximation
            },
            "reaction": emoji
        }
        return self._make_request(url, data)

    def send_read_receipt(self, message_id, sender_number=None):
        # Evolution has mark as read
        url = f"{self.account.evolution_api_url.rstrip('/')}/chat/markMessageAsRead/{self.account.evolution_instance_name}"
        
        # Build remoteJid
        remote_jid = ""
        if sender_number:
            from frappe_whatsapp.utils import format_number
            clean_number = format_number(sender_number)
            remote_jid = f"{clean_number}@s.whatsapp.net"
            
        data = {
            "readMessages": [
                {
                    "id": message_id,
                    "fromMe": False,
                    "remoteJid": remote_jid
                }
            ]
        }
        return self._make_request(url, data)

    def upload_media(self, file_url):
        # Evolution can handle URLs directly, or base64. 
        # We can just return the URL for now as it downloads it on the server side.
        return file_url

    def get_base64_from_url(self, url):
        """Helper to convert local Frappe print format URLs to base64"""
        import base64
        import requests
        from urllib.parse import urlparse, parse_qs
        
        try:
            # 1. Check if it's a Frappe print format PDF
            if "frappe.utils.print_format.download_pdf" in url:
                parsed = urlparse(url)
                params = parse_qs(parsed.query)
                doctype = params.get('doctype', [''])[0]
                name = params.get('name', [''])[0]
                print_format = params.get('format', ['Standard'])[0]
                no_letterhead = params.get('no_letterhead', ['0'])[0]
                
                if doctype and name:
                    pdf_generator = frappe.db.get_single_value("Print Settings", "pdf_generator") or "wkhtmltopdf"
                    pdf_content = frappe.get_print(
                        doctype,
                        name,
                        print_format,
                        as_pdf=True,
                        no_letterhead=int(no_letterhead),
                        pdf_generator=pdf_generator.lower()
                    )
                    b64 = base64.b64encode(pdf_content).decode('utf-8')
                    return b64, "application/pdf", f"{name}.pdf"
            
            # 2. Check if it's another local file
            full_url = url if url.startswith("http") else frappe.utils.get_url(url)
            resp = requests.get(full_url, timeout=10)
            if resp.status_code == 200:
                b64 = base64.b64encode(resp.content).decode('utf-8')
                content_type = resp.headers.get("Content-Type", "application/octet-stream")
                filename = full_url.split("/")[-1].split("?")[0]
                return b64, content_type, filename
                
        except Exception as e:
            frappe.log_error("Evolution API Base64 Conversion Error", str(e))
            
        return url, None, None

    def register_webhook(self, webhook_url):
        url = f"{self.account.evolution_api_url.rstrip('/')}/webhook/set/{self.account.evolution_instance_name}"
        data = {
            "webhook": {
                "enabled": True,
                "url": webhook_url,
                "webhookByEvents": False,
                "webhookBase64": False,
                "events": [
                    "APPLICATION_STARTUP",
                    "QRCODE_UPDATED",
                    "MESSAGES_UPSERT",
                    "MESSAGES_UPDATE",
                    "MESSAGES_DELETE",
                    "SEND_MESSAGE",
                    "CONNECTION_UPDATE",
                    "CALL"
                ]
            }
        }
        try:
            res = self._make_request(url, data)
            return True
        except Exception as e:
            frappe.log_error("Evolution Webhook Set Error", str(e))
            return False

    def get_qrcode(self):
        url = f"{self.account.evolution_api_url.rstrip('/')}/instance/connect/{self.account.evolution_instance_name}"
        try:
            response = requests.get(url, headers=self.get_headers())
            if response.status_code == 200:
                data = response.json()
                return data.get("base64")
        except Exception:
            pass
        return None

    def get_status(self):
        url = f"{self.account.evolution_api_url.rstrip('/')}/instance/connectionState/{self.account.evolution_instance_name}"
        try:
            response = requests.get(url, headers=self.get_headers())
            if response.status_code == 200:
                data = response.json()
                state = data.get("instance", {}).get("state", "Disconnected")
                # Map state to unified statuses
                status_map = {
                    "open": "Connected",
                    "connecting": "Waiting QR",
                    "close": "Disconnected"
                }
                return status_map.get(state, "Disconnected")
        except Exception as e:
            return "Disconnected"

    def disconnect(self):
        url = f"{self.account.evolution_api_url.rstrip('/')}/instance/logout/{self.account.evolution_instance_name}"
        try:
            requests.delete(url, headers=self.get_headers())
        except Exception:
            pass
            
    def supports_templates(self):
        return self.account.instance_type == "Business"

    def supports_qrcode(self):
        return self.account.instance_type == "Baileys"

    def create_template(self, data):
        if self.account.instance_type == "Baileys":
            return {"id": f"LOCAL-{frappe.generate_hash(length=10)}", "status": "APPROVED"}
        
        url = f"{self.account.evolution_api_url.rstrip('/')}/template/create/{self.account.evolution_instance_name}"
        res = self._make_request(url, data)
        return {"id": res.get("id", f"EVO-{frappe.generate_hash(length=8)}"), "status": "APPROVED"}

    def update_template(self, template_id, data):
        if self.account.instance_type == "Baileys":
            return True
        # Evolution does not explicitly document an update endpoint, fallback to create/overwrite
        url = f"{self.account.evolution_api_url.rstrip('/')}/template/create/{self.account.evolution_instance_name}"
        try:
            self._make_request(url, data)
        except Exception:
            pass
        return True

    def delete_template(self, name):
        if self.account.instance_type == "Baileys":
            return True
        # Evolution might not support direct deletion via API, but we return True to allow local deletion
        return True

    def fetch_templates(self):
        if self.account.instance_type == "Baileys":
            return []
        url = f"{self.account.evolution_api_url.rstrip('/')}/template/find/{self.account.evolution_instance_name}"
        try:
            response = requests.get(url, headers=self.get_headers())
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        return []

    def upload_template_media(self, file_url):
        return file_url

    def _make_request(self, url, data):
        try:
            response = requests.post(url, headers=self.get_headers(), json=data)
            response.raise_for_status()
            
            res_json = response.json()
            if "key" in res_json and "id" in res_json["key"]:
                return {
                    "messages": [
                        {"id": res_json["key"]["id"]}
                    ],
                    "raw_response": res_json
                }
            return res_json
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            if e.response is not None:
                try:
                    error_msg = e.response.json()
                except Exception:
                    error_msg = e.response.text
            
            if frappe.db.exists("DocType", "WhatsApp Event Log"):
                frappe.get_doc({
                    "doctype": "WhatsApp Event Log",
                    "provider": "Evolution API",
                    "event_type": "OUTGOING_ERROR",
                    "payload": json.dumps(error_msg),
                    "status": "Failed",
                    "error": str(e)
                }).insert(ignore_permissions=True)
                
            frappe.throw(f"Evolution API Error: {error_msg}")
