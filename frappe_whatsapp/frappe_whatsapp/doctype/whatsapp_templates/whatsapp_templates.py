"""Create whatsapp template."""

# Copyright (c) 2022, Shridhar Patil and contributors
# For license information, please see license.txt
import json
import frappe
from frappe.model.document import Document
from frappe.desk.form.utils import get_pdf_link

from frappe_whatsapp.utils import get_whatsapp_account
from frappe_whatsapp.providers.factory import get_provider

class WhatsAppTemplates(Document):
    """Create whatsapp template."""

    def validate(self):
        self.set_whatsapp_account()
        if not self.language_code or self.has_value_changed("language"):
            lang_code = frappe.db.get_value("Language", self.language) or "en"
            self.language_code = lang_code.replace("-", "_")

        if self.header_type in ["IMAGE", "DOCUMENT"] and self.sample:
            provider = get_provider(self.whatsapp_account)
            self._media_id = provider.upload_template_media(self.sample)

        if not self.is_new():
            self.update_template()

    def set_whatsapp_account(self):
        """Set whatsapp account to default if missing"""
        if not self.whatsapp_account:
            default_whatsapp_account = get_whatsapp_account()
            if not default_whatsapp_account:
                frappe.throw("Please set a default outgoing WhatsApp Account or Select available WhatsApp Account")
            else:
                self.whatsapp_account = default_whatsapp_account.name

    def after_insert(self):
        if self.template_name:
            self.actual_name = self.template_name.lower().replace(" ", "_")

        data = {
            "name": self.actual_name,
            "language": self.language_code,
            "category": self.category,
            "components": [],
        }

        body = {
            "type": "BODY",
            "text": self.template,
        }
        if self.sample_values:
            body.update({"example": {"body_text": [self.sample_values.split(",")]}})

        data["components"].append(body)
        if self.header_type:
            data["components"].append(self.get_header())

        # add footer
        if self.footer:
            data["components"].append({"type": "FOOTER", "text": self.footer})

        # add buttons
        if self.buttons:
            button_block = {"type": "BUTTONS", "buttons": []}
            for btn in self.buttons:
                b = {"type": btn.button_type, "text": btn.button_label}

                if btn.button_type == "Visit Website":
                    b["type"] = "URL"
                    b["url"] = btn.website_url
                    if btn.url_type == "Dynamic" and btn.example_url:
                        b["example"] = btn.example_url.split(",")
                elif btn.button_type == "Call Phone":
                    b["type"] = "PHONE_NUMBER"
                    b["phone_number"] = btn.phone_number
                elif btn.button_type == "Quick Reply":
                    b["type"] = "QUICK_REPLY"
                elif btn.button_type == "Multi-Product Message":
                    b["type"] = "MPM"
                elif btn.button_type == "Catalog":
                    b["type"] = "CATALOG"

                button_block["buttons"].append(b)

            data["components"].append(button_block)

        try:
            provider = get_provider(self.whatsapp_account)
            response = provider.create_template(data)
            self.id = response.get("id")
            self.status = response.get("status")
            self.db_update()
        except Exception as e:
            frappe.throw(str(e))

    def update_template(self):
        """Update template to meta."""
        data = {"components": []}

        body = {
            "type": "BODY",
            "text": self.template,
        }
        if self.sample_values:
            body.update({"example": {"body_text": [self.sample_values.split(",")]}})
        data["components"].append(body)
        if self.header_type:
            data["components"].append(self.get_header())
        if self.footer:
            data["components"].append({"type": "FOOTER", "text": self.footer})
        if self.buttons:
            button_block = {"type": "BUTTONS", "buttons": []}
            for btn in self.buttons:
                b = {"type": btn.button_type, "text": btn.button_label}

                if btn.button_type == "Visit Website":
                    b["type"] = "URL"
                    b["url"] = btn.website_url
                    if btn.url_type == "Dynamic" and btn.example_url:
                        b["example"] = btn.example_url.split(",")
                elif btn.button_type == "Call Phone":
                    b["type"] = "PHONE_NUMBER"
                    b["phone_number"] = btn.phone_number
                elif btn.button_type == "Quick Reply":
                    b["type"] = "QUICK_REPLY"
                elif btn.button_type == "Multi-Product Message":
                    b["type"] = "MPM"
                elif btn.button_type == "Catalog":
                    b["type"] = "CATALOG"

                button_block["buttons"].append(b)

            data["components"].append(button_block)

        try:
            provider = get_provider(self.whatsapp_account)
            provider.update_template(self.id, data)
        except Exception as e:
            raise e

    def on_trash(self):
        try:
            provider = get_provider(self.whatsapp_account)
            provider.delete_template(self.actual_name)
        except Exception as e:
            frappe.log_error("Template Delete Error", str(e))
            # Just log, allow local deletion even if remote fails

    def get_header(self):
        """Get header format."""
        header = {"type": "header", "format": self.header_type}
        if self.header_type == "TEXT":
            header["text"] = self.header
            if self.sample:
                samples = self.sample.split(", ")
                header.update({"example": {"header_text": samples}})
        else:
            if hasattr(self, "_media_id") and self._media_id:
                header.update({"example": {"header_handle": [self._media_id]}})

        return header

@frappe.whitelist()
def fetch():
    """Fetch templates from provider."""
    whatsapp_accounts = frappe.get_all('WhatsApp Account', filters={'status': 'Active'}, fields=['name'])

    for account in whatsapp_accounts:
        provider = get_provider(account.name)

        try:
            templates = provider.fetch_templates()

            for template in templates:
                # set flag to insert or update
                flags = 1
                if frappe.db.exists("WhatsApp Templates", {"actual_name": template["name"]}):
                    doc = frappe.get_doc("WhatsApp Templates", {"actual_name": template["name"]})
                else:
                    flags = 0
                    doc = frappe.new_doc("WhatsApp Templates")
                    doc.template_name = template["name"]
                    doc.actual_name = template["name"]

                doc.status = template["status"]
                doc.language_code = template["language"]
                doc.category = template["category"]
                doc.id = template["id"]
                doc.whatsapp_account = account.name

                # update components
                for component in template["components"]:

                    # update header
                    if component["type"] == "HEADER":
                        doc.header_type = component["format"]

                        # if format is text update sample text
                        if component["format"] == "TEXT":
                            doc.header = component["text"]
                    # Update footer text
                    elif component["type"] == "FOOTER":
                        doc.footer = component["text"]

                    # update template text
                    elif component["type"] == "BODY":
                        doc.template = component["text"]
                        if component.get("example"):
                            if component["example"].get("body_text"):
                                doc.sample_values = ",".join(
                                    component["example"]["body_text"][0]
                                )

                    # Update buttons
                    elif component["type"] == "BUTTONS":
                        doc.set("buttons", [])
                        frappe.db.delete("WhatsApp Button", {"parent": doc.name, "parenttype": "WhatsApp Templates"})
                        typeMap = {
                            "URL": "Visit Website",
                            "PHONE_NUMBER": "Call Phone",
                            "QUICK_REPLY": "Quick Reply",
                            "FLOW": "Flow",
                            "MPM": "Multi-Product Message",
                            "CATALOG": "Catalog"
                        }

                        for i, button in enumerate(component.get("buttons", []), start=1):
                            btn_type_raw = button.get("type")
                            if btn_type_raw not in typeMap:
                                continue

                            btn = {}
                            btn["button_type"] = typeMap[button["type"]]
                            btn["button_label"] = button.get("text")
                            btn["sequence"] = i

                            if button["type"] == "URL":
                                btn["website_url"] = button.get("url")
                                if "{{" in btn["website_url"]:
                                    btn["url_type"] = "Dynamic"
                                else:
                                    btn["url_type"] = "Static"

                                if button.get("example"):
                                    btn["example_url"] = ",".join(button["example"])
                            elif button["type"] == "PHONE_NUMBER":
                                btn["phone_number"] = button.get("phone_number")
                            elif button["type"] == "FLOW":
                                btn["flow"] = button.get("flow")

                            doc.append("buttons", btn)

                upsert_doc_without_hooks(doc, "WhatsApp Button", "buttons")

        except Exception as e:
            frappe.log_error(f"Error fetching templates for account {account.name}: {str(e)}")
            
    return "Successfully fetched templates"

def upsert_doc_without_hooks(doc, child_dt, child_field):
    """Insert or update a parent document and its children without hooks."""
    if frappe.db.exists(doc.doctype, doc.name):
        doc.db_update()
        frappe.db.delete(child_dt, {"parent": doc.name, "parenttype": doc.doctype})
    else:
        doc.db_insert()
    for d in doc.get(child_field):
        d.parent = doc.name
        d.parenttype = doc.doctype
        d.parentfield = child_field
        d.db_insert()
