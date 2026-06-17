// Copyright (c) 2025, Shridhar Patil and contributors
// For license information, please see license.txt

frappe.ui.form.on("WhatsApp Account", {
	refresh(frm) {
		if (!frm.is_new()) {
            if (frm.doc.provider === "Meta") {
                frm.add_custom_button(__("Subscribe App to Webhooks"), () => {
                    frappe.confirm(
                        __("Subscribe this app to webhooks for WhatsApp Business Account {0}?", [
                            frm.doc.business_id || frm.doc.account_name,
                        ]),
                        () => {
                            frm.call({
                                doc: frm.doc,
                                method: "subscribe_app",
                                freeze: true,
                                freeze_message: __("Subscribing app to webhooks..."),
                                callback: (r) => {
                                    if (!r.exc) {
                                        frappe.show_alert({
                                            message: __("App subscribed to webhooks"),
                                            indicator: "green",
                                        });
                                    }
                                },
                            });
                        }
                    );
                });
            } else if (frm.doc.provider === "Evolution API") {
                frm.add_custom_button(__("Register Webhook"), () => {
                    frm.call({
                        doc: frm.doc,
                        method: "register_webhook",
                        freeze: true,
                        freeze_message: __("Registering Webhook..."),
                        callback: (r) => {
                            if (!r.exc) {
                                frm.reload_doc();
                                frappe.show_alert({
                                    message: __("Webhook registered successfully"),
                                    indicator: "green",
                                });
                            }
                        }
                    });
                }, __("Evolution"));

                if (frm.doc.instance_type === "Baileys") {
                    if (frm.doc.connection_status === "Disconnected" || frm.doc.connection_status === "Waiting QR") {
                        frm.add_custom_button(__("Generate QR"), () => {
                            frm.call({
                                doc: frm.doc,
                                method: "generate_qr",
                                freeze: true,
                                freeze_message: __("Fetching QR Code..."),
                                callback: (r) => {
                                    if (r.message) {
                                        let qr_html = `<div class="text-center"><img src="${r.message}" style="max-width: 300px;"></div>`;
                                        frappe.msgprint({
                                            title: __("Scan QR Code"),
                                            message: qr_html,
                                            indicator: "blue"
                                        });
                                    }
                                }
                            });
                        }, __("Evolution"));
                    }

                    if (frm.doc.connection_status === "Connected") {
                        frm.add_custom_button(__("Disconnect"), () => {
                            frappe.confirm(__("Are you sure you want to disconnect this instance?"), () => {
                                frm.call({
                                    doc: frm.doc,
                                    method: "disconnect_instance",
                                    freeze: true,
                                    freeze_message: __("Disconnecting..."),
                                    callback: (r) => {
                                        if (!r.exc) {
                                            frm.reload_doc();
                                        }
                                    }
                                });
                            });
                        }, __("Evolution"));
                    }
                    
                    frm.add_custom_button(__("Check Status"), () => {
                        frm.call({
                            doc: frm.doc,
                            method: "check_connection_status",
                            freeze: true,
                            freeze_message: __("Checking Status..."),
                            callback: (r) => {
                                if (!r.exc) {
                                    frm.reload_doc();
                                }
                            }
                        });
                    }, __("Evolution"));
                }
            }
		}
	},
    provider(frm) {
        if (frm.doc.provider === "Meta" && !frm.doc.url) {
            frm.set_value("url", "https://graph.facebook.com");
            frm.set_value("version", "v21.0");
        }
    }
});
