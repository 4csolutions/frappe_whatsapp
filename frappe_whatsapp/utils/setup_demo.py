import frappe

def run():
    frappe.flags.in_test = True
    
    # 1. Get an active WhatsApp Account
    account = frappe.db.get_value("WhatsApp Account", {"status": "Active"}, "name")
    if not account:
        frappe.throw("No active WhatsApp Account found. Please configure one first.")

    # 2. Create WhatsApp Template
    template_name = "Invoice Notification"
    actual_name = "invoice_notification"

    if not frappe.db.exists("WhatsApp Templates", {"actual_name": actual_name}):
        template = frappe.get_doc({
            "doctype": "WhatsApp Templates",
            "template_name": template_name,
            "actual_name": actual_name,
            "category": "UTILITY",
            "language": "en",
            "language_code": "en_US",
            "header_type": "DOCUMENT",
            "template": "Hello {{1}},\n\nYour invoice {{2}} for the amount of {{3}} {{4}} has been generated. Please find the document attached.\n\nThank you for your business!",
            "sample_values": "John Doe, INV-2023-0001, USD, 1500",
            "whatsapp_account": account,
            "status": "APPROVED" # Simulate approved for local baileys
        }).insert(ignore_permissions=True)
        frappe.db.commit()
        print(f"Created WhatsApp Template: {template.name}")
    else:
        template = frappe.get_doc("WhatsApp Templates", {"actual_name": actual_name})
        print(f"Template already exists: {template.name}")

    # 3. Create WhatsApp Notification
    if not frappe.db.exists("WhatsApp Notification", {"reference_doctype": "Sales Invoice", "template": template.name}):
        notification = frappe.get_doc({
            "doctype": "WhatsApp Notification",
            "notification_name": "Sales Invoice Notification",
            "notification_type": "DocType Event",
            "reference_doctype": "Sales Invoice",
            "doctype_event": "After Submit",
            "template": template.name,
            "field_name": "contact_mobile",
            "attach_document_print": 1,
            "whatsapp_account": account,
            "fields": [
                {"field_name": "customer_name"},
                {"field_name": "name"},
                {"field_name": "currency"},
                {"field_name": "grand_total"}
            ]
        }).insert(ignore_permissions=True)
        frappe.db.commit()
        print(f"Created WhatsApp Notification: {notification.name}")
    else:
        print("WhatsApp Notification for Sales Invoice already exists.")

