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

    def send_read_receipt(self, message_id):
        raise NotImplementedError

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
