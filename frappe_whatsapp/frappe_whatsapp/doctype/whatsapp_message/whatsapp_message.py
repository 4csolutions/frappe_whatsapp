# Copyright (c) 2022, Shridhar Patil and contributors
# For license information, please see license.txt
import json
import frappe
from frappe import _, throw
from frappe.model.document import Document

from frappe_whatsapp.utils import get_whatsapp_account, format_number
from frappe_whatsapp.providers.factory import get_provider

class WhatsAppMessage(Document):
    def validate(self):
        self.set_whatsapp_account()
        if self.type == "Outgoing" and self.is_new():
            self.status = "Queued"

    def on_update(self):
        self.update_profile_name()

    def update_profile_name(self):
        number = self.get("from")
        if not number:
            return
        from_number = format_number(number)

        if (
            self.has_value_changed("profile_name")
            and self.profile_name
            and from_number
            and frappe.db.exists("WhatsApp Profiles", {"number": from_number})
        ):
            profile_id = frappe.get_value("WhatsApp Profiles", {"number": from_number}, "name")
            frappe.db.set_value("WhatsApp Profiles", profile_id, "profile_name", self.profile_name)

    def create_whatsapp_profile(self):
        number = format_number(self.get("from") or self.to)
        if not frappe.db.exists("WhatsApp Profiles", {"number": number}):
            frappe.get_doc({
                "doctype": "WhatsApp Profiles",
                "profile_name": self.profile_name,
                "number": number,
                "whatsapp_account": self.whatsapp_account
            }).insert(ignore_permissions=True)

    def set_whatsapp_account(self):
        """Set whatsapp account to default if missing"""
        if not self.whatsapp_account:
            account_type = 'outgoing' if self.type == 'Outgoing' else 'incoming'
            default_whatsapp_account = get_whatsapp_account(account_type=account_type)
            if not default_whatsapp_account:
                throw(_("Please set a default outgoing WhatsApp Account or Select available WhatsApp Account"))
            else:
                self.whatsapp_account = default_whatsapp_account.name

    def before_insert(self):
        """Setup message."""
        self.set_whatsapp_account()
        if self.template:
            self.message_type = "Template"
        self.create_whatsapp_profile()

    def after_insert(self):
        if self.type == "Outgoing":
            frappe.enqueue(
                "frappe_whatsapp.utils.queue_manager.send_queued_message",
                queue="short",
                message_id=self.name,
                enqueue_after_commit=True
            )

    @frappe.whitelist()
    def send_read_receipt(self):
        provider = get_provider(self.whatsapp_account)
        if hasattr(provider, "send_read_receipt") and self.message_id:
            try:
                sender_number = self.get("from")
                if not sender_number and self.type == "Outgoing":
                    sender_number = self.to
                    
                response = provider.send_read_receipt(self.message_id, sender_number=sender_number)
                self.db_set("status", "Read")
                return True
            except Exception as e:
                frappe.log_error("WhatsApp Read Receipt Error", str(e))
        return False

def on_doctype_update():
    frappe.db.add_index("WhatsApp Message", ["reference_doctype", "reference_name"])

@frappe.whitelist()
def send_template(to, reference_doctype, reference_name, template):
    try:
        doc = frappe.get_doc({
            "doctype": "WhatsApp Message",
            "to": to,
            "type": "Outgoing",
            "message_type": "Template",
            "reference_doctype": reference_doctype,
            "reference_name": reference_name,
            "content_type": "text",
            "template": template
        })
        doc.insert()
    except Exception as e:
        raise e
