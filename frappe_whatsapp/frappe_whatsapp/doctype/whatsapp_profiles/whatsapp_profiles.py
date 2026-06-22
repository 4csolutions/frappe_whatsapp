# Copyright (c) 2025, Shridhar Patil and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.query_builder.functions import Replace
from frappe_whatsapp.utils import format_number

def get_clean_phone_field(field):
    cleaned = Replace(field, '+', '')
    cleaned = Replace(cleaned, '-', '')
    cleaned = Replace(cleaned, ' ', '')
    cleaned = Replace(cleaned, '(', '')
    cleaned = Replace(cleaned, ')', '')
    return cleaned

class WhatsAppProfiles(Document):
    def validate(self):
        self.format_whatsapp_number()
        self.set_title()

    def before_insert(self):
        self.set_contact_and_name()

    def set_contact_and_name(self):
        if not self.number:
            return

        base_number = self.number[-10:] if len(self.number) >= 10 else self.number
        
        ContactPhone = frappe.qb.DocType("Contact Phone")
        contact_phones = (
            frappe.qb.from_(ContactPhone)
            .select(ContactPhone.parent.as_("contact_name"))
            .where(get_clean_phone_field(ContactPhone.phone).like(f"%{base_number}"))
            .orderby(ContactPhone.is_primary_phone, order=frappe.qb.desc)
            .orderby(ContactPhone.is_primary_mobile_no, order=frappe.qb.desc)
            .limit(1)
            .run(as_dict=True)
        )

        if contact_phones:
            contact_name = contact_phones[0].contact_name
        else:
            # Fallback to Contact directly
            Contact = frappe.qb.DocType("Contact")
            contacts = (
                frappe.qb.from_(Contact)
                .select(Contact.name)
                .where(
                    get_clean_phone_field(Contact.mobile_no).like(f"%{base_number}") |
                    get_clean_phone_field(Contact.phone).like(f"%{base_number}")
                )
                .limit(1)
                .run(as_dict=True)
            )
            
            if contacts:
                contact_name = contacts[0].name

        if contact_name:
            self.contact = contact_name
            full_name = frappe.db.get_value("Contact", contact_name, "full_name")
            if full_name:
                self.profile_name = full_name

    def format_whatsapp_number(self):
        if self.number:
            self.number = format_number(self.number)

    def set_title(self):
        self.title = " - ".join(p for p in (self.profile_name, self.number) if p) or "Unnamed Profile"

