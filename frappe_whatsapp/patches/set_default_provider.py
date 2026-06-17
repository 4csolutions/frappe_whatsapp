import frappe

def execute():
    """Migrate existing WhatsApp Accounts to explicitly use the Meta provider."""
    
    frappe.reload_doc("frappe_whatsapp", "doctype", "whatsapp_account")
    frappe.reload_doc("frappe_whatsapp", "doctype", "whatsapp_message")
    
    accounts = frappe.get_all("WhatsApp Account", filters={"provider": ("is", "not set")})
    for account in accounts:
        doc = frappe.get_doc("WhatsApp Account", account.name)
        doc.db_set("provider", "Meta")
        doc.db_set("instance_type", "Business")
        doc.db_set("connection_status", "Connected")

    # Map existing statuses to Unified Statuses
    # The previous Meta status updates were lowercase "sent", "delivered", "read", "failed"
    status_map = {
        "sent": "Sent",
        "delivered": "Delivered",
        "read": "Read",
        "failed": "Failed"
    }

    for old_status, new_status in status_map.items():
        frappe.db.sql(
            """
            UPDATE `tabWhatsApp Message` 
            SET status = %s 
            WHERE status = %s
            """,
            (new_status, old_status)
        )
        
    frappe.db.commit()
