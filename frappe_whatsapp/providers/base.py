import frappe

class WhatsAppProvider:
    def __init__(self, account_doc):
        self.account = account_doc

    def send_text(self, to_number, message, **kwargs):
        raise NotImplementedError

    def send_media(self, to_number, media_url, media_type, caption=None, **kwargs):
        raise NotImplementedError

    def send_template(self, to_number, template_name, language_code, components, **kwargs):
        raise NotImplementedError

    def upload_media(self, file_url):
        raise NotImplementedError

    def register_webhook(self, webhook_url):
        raise NotImplementedError

    def get_qrcode(self):
        raise NotImplementedError

    def get_status(self):
        raise NotImplementedError

    def supports_templates(self):
        return False

    def supports_qrcode(self):
        return False

    def send_read_receipt(self, message_id, sender_number=None):
        raise NotImplementedError

    def save_base64_media(self, base64_data, message_type, sender):
        """Save base64 media to Frappe and return the file URL"""
        import base64
        from frappe.utils.file_manager import save_file
        
        if not base64_data:
            return None
            
        media_ext_map = {
            "imageMessage": "jpeg",
            "videoMessage": "mp4",
            "documentMessage": "pdf",
            "audioMessage": "ogg"
        }
        ext = media_ext_map.get(message_type, "bin")
        
        # Handle prefix if any
        if "," in base64_data:
            base64_data = base64_data.split(",")[1]
            
        try:
            file_content = base64.b64decode(base64_data)
            file_name = f"WA-{sender}-{frappe.generate_hash()[:8]}.{ext}"
            
            # Save file to Frappe (is_private=0 so it's accessible via web)
            file_doc = save_file(file_name, file_content, "WhatsApp Message", None, is_private=0)
            return file_doc.file_url
        except Exception as e:
            frappe.log_error("WhatsApp Media Save Error", str(e))
            return None

    def format_number(self, number):
        if number.startswith("+"):
            number = number[1:]
        return number

    def create_template(self, data):
        raise NotImplementedError

    def update_template(self, template_id, data):
        raise NotImplementedError

    def delete_template(self, name):
        raise NotImplementedError

    def fetch_templates(self):
        raise NotImplementedError

    def upload_template_media(self, file_url):
        raise NotImplementedError
