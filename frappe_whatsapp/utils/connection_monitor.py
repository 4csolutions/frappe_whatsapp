import frappe

def check_all_connections():
    """Scheduled job to check the status of all active WhatsApp accounts."""
    accounts = frappe.get_all("WhatsApp Account", filters={"status": "Active"})
    for account in accounts:
        try:
            doc = frappe.get_doc("WhatsApp Account", account.name)
            doc.check_connection_status()
        except Exception as e:
            frappe.log_error("Connection Monitor Error", str(e))
