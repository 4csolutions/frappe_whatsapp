# Copyright (c) 2025, Shridhar Patil and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.integrations.utils import make_post_request
from frappe.model.document import Document
from frappe.utils import get_url

from frappe_whatsapp.providers.factory import get_provider

class WhatsAppAccount(Document):
    def before_save(self):
        if self.provider == "Evolution API" and self.auto_register_webhook:
            # We must only auto-register if the API url is fully populated
            if self.evolution_api_url and self.evolution_instance_name:
                # We can't trigger an API call to a provider if it's new and doesn't have an API key saved yet in db, 
                # but if password is set in memory we can use it.
                if self.get_password("evolution_api_key"):
                    try:
                        self.register_webhook()
                    except Exception:
                        pass # Ignore errors during auto-registration on save to avoid blocking save

    def on_update(self):
        """Check there is only one default of each type."""
        self.there_must_be_only_one_default()

    def there_must_be_only_one_default(self):
        """If current WhatsApp Account is default, un-default all other accounts."""
        for field in ("is_default_incoming", "is_default_outgoing"):
            if not self.get(field):
                continue

            for whatsapp_account in frappe.get_all("WhatsApp Account", filters={field: 1}):
                if whatsapp_account.name == self.name:
                    continue

                whatsapp_account = frappe.get_doc("WhatsApp Account", whatsapp_account.name)
                whatsapp_account.set(field, 0)
                whatsapp_account.save()

    @frappe.whitelist()
    def subscribe_app(self):
        """Subscribe this app to webhooks for the WhatsApp Business Account. (Meta Only)"""
        if self.provider != "Meta":
            frappe.throw(_("This action is only for Meta provider."))
            
        for field in ("url", "version", "business_id"):
            if not self.get(field):
                frappe.throw(_("{0} is required to subscribe the app").format(
                    frappe.bold(self.meta.get_label(field))
                ))

        token = self.get_password("token")
        if not token:
            frappe.throw(_("Access token is required to subscribe the app"))

        endpoint = f"{self.url}/{self.version}/{self.business_id}/subscribed_apps"
        headers = {
            "authorization": f"Bearer {token}",
            "content-type": "application/json",
        }

        try:
            response = make_post_request(endpoint, headers=headers)
        except Exception as e:
            error_message = str(e)
            if frappe.flags.integration_request:
                err = frappe.flags.integration_request.json().get("error", {})
                if err:
                    error_message = err.get("message") or err.get("Error") or error_message
            frappe.throw(_("Failed to subscribe app to webhooks: {0}").format(error_message))

        if not response.get("success"):
            frappe.throw(_("Subscription was not successful: {0}").format(frappe.as_json(response)))

        frappe.logger().info(
            f"WhatsApp app subscribed to webhooks for business_id={self.business_id}"
        )
        return response

    @frappe.whitelist()
    def register_webhook(self):
        provider = get_provider(self.name)
        # Use existing meta webhook endpoint for evolution as well, which will dispatch
        webhook_url = f"{get_url()}/api/method/frappe_whatsapp.utils.webhook.webhook"
        
        success = provider.register_webhook(webhook_url)
        if success:
            self.db_set("webhook_registered", 1)
            self.db_set("webhook_url", webhook_url)
            return True
        else:
            frappe.throw(_("Failed to register webhook. Check Error Logs for details."))

    @frappe.whitelist()
    def generate_qr(self):
        provider = get_provider(self.name)
        if not provider.supports_qrcode():
            frappe.throw(_("This provider/instance type does not support QR Codes."))
            
        qr_code = provider.get_qrcode()
        if not qr_code:
            frappe.throw(_("Could not generate QR code. Ensure the instance is disconnected first."))
            
        self.check_connection_status()
        return qr_code

    @frappe.whitelist()
    def check_connection_status(self):
        provider = get_provider(self.name)
        status = provider.get_status()
        self.db_set("connection_status", status)
        self.db_set("last_sync_on", frappe.utils.now())
        if status == "Connected":
            self.db_set("last_connected_on", frappe.utils.now())
        return status

    @frappe.whitelist()
    def disconnect_instance(self):
        provider = get_provider(self.name)
        if hasattr(provider, "disconnect"):
            provider.disconnect()
        self.check_connection_status()
