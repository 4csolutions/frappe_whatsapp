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

    def save_base64_media(self, base64_data, message_type, message_doc, mimetype=None):
        """Save base64 media to Frappe and return the file URL"""
        import base64
        import mimetypes
        
        if not base64_data:
            return None
            
        ext = ""
        if mimetype:
            ext = mimetype.split('/')[1] if '/' in mimetype else mimetypes.guess_extension(mimetype) or "bin"
            
        if not ext:
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
            sender = message_doc.get("from")
            file_name = f"WA-{sender}-{frappe.generate_hash()[:8]}.{ext}"
            
            # Save using standard frappe Document to explicitly link
            file_doc = frappe.get_doc({
                "doctype": "File",
                "file_name": file_name,
                "attached_to_doctype": "WhatsApp Message",
                "attached_to_name": message_doc.name,
                "content": file_content,
                "attached_to_field": "attach",
                "is_private": 0
            }).save(ignore_permissions=True)
            
            # Update the message document
            message_doc.attach = file_doc.file_url
            message_doc.save(ignore_permissions=True)
            
            return file_doc.file_url
        except Exception as e:
            frappe.log_error("WhatsApp Media Save Error", str(e))
            return None

    def download_media(self, media_data, message_doc):
        raise NotImplementedError

    def format_number(self, number):
        import re
        
        # Strip all non-numeric characters (e.g. '+', '-', spaces)
        clean_number = re.sub(r'\D', '', str(number))
        
        # Strip leading zeros
        while clean_number.startswith('0'):
            clean_number = clean_number[1:]
            
        default_code = self.account.get("default_country_code")
        if default_code:
            default_code = re.sub(r'\D', '', str(default_code))
            
            # If the number is 10 digits or less, assume it's a local number and prepend country code
            if len(clean_number) <= 10 and not clean_number.startswith(default_code):
                clean_number = f"{default_code}{clean_number}"
                
        return clean_number

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
