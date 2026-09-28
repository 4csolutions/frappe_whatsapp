// Copyright (c) 2022, Shridhar Patil and contributors
// For license information, please see license.txt
frappe.notification = {
	setup_fieldname_select: function (frm) {
		if (!frm.doc.reference_doctype) {
			return;
		}

		frappe.model.with_doctype(frm.doc.reference_doctype, function () {
			let get_select_options = function (df, parent_field, parent_label) {
				let select_value = parent_field ? parent_field + "." + df.fieldname : df.fieldname;
				let path = parent_label ? parent_label + " > " + __(df.label, null, df.parent) : __(df.label, null, df.parent);

				return {
					value: select_value,
					label: select_value + " (" + path + ")",
				};
			};

			let fields = frappe.get_doc("DocType", frm.doc.reference_doctype).fields || [];

			let get_date_change_options = function () {
				let date_options = $.map(fields, function (d) {
					return d.fieldtype == "Date" || d.fieldtype == "Datetime"
						? get_select_options(d)
						: null;
				});
				return date_options.concat([
					{ value: "creation", label: `creation (${__("Created On")})` },
					{ value: "modified", label: `modified (${__("Last Modified Date")})` },
				]);
			};

			let options = $.map(fields, function (d) {
				return frappe.model.no_value_type.includes(d.fieldtype)
					? null
					: get_select_options(d);
			});

			frm.set_df_property("date_changed", "options", get_date_change_options());
			frm.set_df_property("value_changed", "options", [""].concat(options));
			frm.set_df_property("set_property_after_alert", "options", [""].concat(options));

			// Fetch fields and linked doctype fields via server-side schema inspection
			frappe.call({
				method: "frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_notification.whatsapp_notification.get_doctype_fields",
				args: {
					doctype: frm.doc.reference_doctype,
				},
				callback: function (r) {
					if (!r || !r.message) return;

					// Convert object lists to plain string arrays for Autocomplete controls
					let phone_opts = (r.message.phone_options || []).map(o => o.value || o);
					let param_opts = (r.message.all_fields || []).map(o => o.value || o);

					frm._param_opts = param_opts;
					frm._phone_opts = phone_opts;

					// 1. Setup Awesomplete autocomplete on the main field_name input
					frm.set_df_property("field_name", "options", phone_opts);
					frm.refresh_field("field_name");
					frappe.notification.setup_field_awesomplete(frm, "field_name", phone_opts);

					// 2. Feed options to the child table Autocomplete field natively
					if (frm.fields_dict.fields && frm.fields_dict.fields.grid) {
						frm.fields_dict.fields.grid.update_docfield_property(
							"field_name",
							"options",
							param_opts
						);
					}
				},
			});
		});
	},
	setup_field_awesomplete: function (frm, fieldname, options) {
		let field = frm.fields_dict[fieldname];
		if (!field || !field.$input) return;

		// Convert list to Awesomplete compatible format
		let list = (options || []).filter(Boolean).map(function (opt) {
			if (typeof opt === "object") {
				return { label: opt.label || opt.value, value: opt.value };
			}
			return { label: opt, value: opt };
		});

		if (field.awesomplete) {
			field.awesomplete.list = list;
			return;
		}

		// Only bind Awesomplete if the input is a text input (not a native <select>)
		if (field.$input.is("input")) {
			let input_el = field.$input.get(0);
			field.awesomplete = new Awesomplete(input_el, {
				minChars: 0,
				maxItems: 99,
				autoFirst: true,
				list: list,
				data: function (item) {
					if (typeof item !== "object") {
						item = { value: item, label: item };
					}
					return {
						label: item.label || item.value,
						value: item.value,
					};
				},
				filter: function (item, input) {
					let d = this.get_item(item.value) || item;
					let hay = (d.label || "") + " " + (d.value || "");
					return Awesomplete.FILTER_CONTAINS(hay, input);
				},
				item: function (item) {
					let d = this.get_item(item.value) || item;
					return $("<li></li>")
						.data("item.autocomplete", d)
						.prop("aria-selected", "false")
						.html("<a><p><strong>" + (d.label || d.value) + "</strong></p></a>")
						.get(0);
				}
			});

			$(field.input_area).find(".awesomplete ul").css("min-width", "100%");

			let open_list = function () {
				if (field.awesomplete) {
					field.awesomplete.evaluate();
				}
			};

			field.$input.on("focus click", open_list);

			field.$input.on("awesomplete-selectcomplete", function () {
				field.$input.trigger("change");
			});
		}
	},

	setup_alerts_button: function (frm) {
		frm.add_custom_button(__('Get Alerts for Today'), function () {
			frappe.call({
				method: 'frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_notification.whatsapp_notification.call_trigger_notifications',
				args: {
					method: 'daily' 
				},
				callback: function (response) {
					if (response.message && response.message.length > 0) {
					} else {
						frappe.msgprint(__('No alerts for today'));
					}
				},
				error: function (error) {
					frappe.msgprint(__('Failed to trigger notifications'));
				}
			});
		});
	}
};


frappe.ui.form.on('WhatsApp Notification', {
	onload: function(frm) {
		if (frm.doc.reference_doctype) {
			frappe.notification.setup_fieldname_select(frm);
		}
	},
	refresh: function(frm) {
		frm.trigger("load_template");
		frappe.notification.setup_fieldname_select(frm);
		frappe.notification.setup_alerts_button(frm);
	},
	template: function(frm){
		frm.trigger("load_template");
	},
	load_template: function(frm){
		frappe.db.get_value(
			"WhatsApp Templates",
			frm.doc.template,
			["template", "header_type"],
			(r) => {
				if (r && r.template) {
					frm.set_value('header_type', r.header_type);
					frm.refresh_field("header_type");
					if (['DOCUMENT', "IMAGE"].includes(r.header_type)){
						frm.toggle_display("custom_attachment", true);
						frm.toggle_display("attach_document_print", true);
						if (!frm.doc.custom_attachment){
							frm.set_value("attach_document_print", 1);
						}
					}else{
						frm.toggle_display("custom_attachment", false);
						frm.toggle_display("attach_document_print", false);
						frm.set_value("attach_document_print", 0);
						frm.set_value("custom_attachment", 0);
					}

					frm.refresh_field("custom_attachment");

					frm.set_value("code", r.template);
					frm.refresh_field("code");
				}
			}
		);
	},
	custom_attachment: function(frm){
		if(frm.doc.custom_attachment == 1 &&  ['DOCUMENT', "IMAGE"].includes(frm.doc.header_type)){
			frm.set_df_property('file_name', 'reqd', frm.doc.custom_attachment);
		}else{
			frm.set_df_property('file_name', 'reqd', 0);
		}

		if(frm.doc.header_type){
			frm.set_value("attach_document_print", !frm.doc.custom_attachment);
		}
	},
	attach_document_print: function(frm){
		if(['DOCUMENT', "IMAGE"].includes(frm.doc.header_type)){
			frm.set_value("custom_attachment", !frm.doc.attach_document_print);
		}
	},
	reference_doctype: function (frm) {
		frappe.notification.setup_fieldname_select(frm);
	},
});

frappe.ui.form.on('WhatsApp Message Fields', {
	fields_add: function (frm) {
		// Re-apply options whenever a new row is added
		if (frm._param_opts && frm.fields_dict.fields && frm.fields_dict.fields.grid) {
			frm.fields_dict.fields.grid.update_docfield_property(
				"field_name",
				"options",
				frm._param_opts
			);
		}
	},
});

