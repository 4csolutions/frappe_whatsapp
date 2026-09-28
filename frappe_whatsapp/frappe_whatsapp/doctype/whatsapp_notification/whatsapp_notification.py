"""Notification."""

import json
import frappe

from frappe import _dict, _
from frappe.model import NO_VALUE_FIELDS
from frappe.model.document import Document
from frappe.utils.safe_exec import get_safe_globals, safe_exec
from frappe.desk.form.utils import get_pdf_link
from frappe.utils import add_to_date, nowdate, datetime

from frappe_whatsapp.utils import get_whatsapp_account


def resolve_document_field_value(doc, field_path, formatted=False):
    """Resolve field value from doc or linked doc using dot notation (e.g. 'patient.mobile', 'customer.mobile_no', 'owner')."""
    if not doc or not field_path:
        return None

    field_path = field_path.strip()
    if field_path == "owner":
        owner = doc.get("owner") if hasattr(doc, "get") else getattr(doc, "owner", None)
        if owner:
            return frappe.db.get_value("User", owner, "mobile_no")
        return None

    parts = field_path.split(".")
    current = doc
    for idx, part in enumerate(parts):
        is_last = (idx == len(parts) - 1)
        if current is None:
            return None

        if is_last:
            if formatted and isinstance(current, Document):
                return current.get_formatted(part)
            if hasattr(current, "get"):
                val = current.get(part)
            else:
                val = getattr(current, part, None)
            return val
        else:
            # Traversal step
            if hasattr(current, "get"):
                link_val = current.get(part)
                doctype_name = current.get("doctype") if hasattr(current, "get") else getattr(current, "doctype", None)
            else:
                link_val = getattr(current, part, None)
                doctype_name = getattr(current, "doctype", None)

            if not link_val or not doctype_name:
                return None

            meta = frappe.get_meta(doctype_name)
            df = meta.get_field(part)
            if df and df.fieldtype == "Link" and df.options:
                current = frappe.get_cached_doc(df.options, link_val)
            else:
                return None

    return None


class WhatsAppNotification(Document):
    """Notification."""

    def validate(self):
        """Validate."""
        if self.notification_type == "DocType Event" and self.field_name:
            self.validate_field_path(self.reference_doctype, self.field_name)

        if self.custom_attachment:
            if not self.attach and not self.attach_from_field:
                frappe.throw(_("Either {0} a file or add a {1} to send attachemt").format(
                    frappe.bold(_("Attach")),
                    frappe.bold(_("Attach from field")),
                ))

        if self.set_property_after_alert:
            meta = frappe.get_meta(self.reference_doctype)
            if not meta.get_field(self.set_property_after_alert):
                frappe.throw(_("Field {0} not found on DocType {1}").format(
                    self.set_property_after_alert,
                    self.reference_doctype,
                ))

    def validate_field_path(self, doctype, field_path):
        """Validate field or linked dot-notation path exists."""
        if field_path == "owner":
            return

        parts = field_path.strip().split(".")
        current_dt = doctype
        for idx, part in enumerate(parts):
            if not frappe.db.exists("DocType", current_dt):
                frappe.throw(_("DocType {0} does not exist").format(current_dt))

            meta = frappe.get_meta(current_dt)
            df = meta.get_field(part)
            if not df:
                frappe.throw(_("Field name {0} does not exist on {1}").format(part, current_dt))

            is_last = (idx == len(parts) - 1)
            if not is_last:
                if df.fieldtype != "Link" or not df.options:
                    frappe.throw(_("Field {0} on {1} is not a Link field").format(part, current_dt))
                current_dt = df.options


    def send_scheduled_message(self) -> dict:
        """Specific to API endpoint Server Scripts."""
        safe_exec(
            self.condition, get_safe_globals(), dict(doc=self)
        )

        template = frappe.db.get_value(
            "WhatsApp Templates", self.template,
            fieldname='*'
        )

        if template and template.language_code:
            if self.get("_contact_list"):
                # send simple template without a doc to get field data.
                self.send_simple_template(template)
            elif self.get("_data_list"):
                # allow send a dynamic template using schedule event config
                # _doc_list shoud be [{"name": "xxx", "phone_no": "123"}]
                for data in self._data_list:
                    doc = frappe.get_doc(self.reference_doctype, data.get("name"))

                    self.send_template_message(doc, data.get("phone_no"), template, True)


    def send_simple_template(self, template):
        """ send simple template without a doc to get field data """
        for contact in self._contact_list:
            to_number = self.format_number(contact)
            self.notify(to_number, {}, None, None)


    def send_template_message(self, doc: Document, phone_no=None, default_template=None, ignore_condition=False):
        """Specific to Document Event triggered Server Scripts."""
        if self.disabled:
            return

        doc_data = doc.as_dict()
        if self.condition and not ignore_condition:
            # check if condition satisfies
            if not frappe.safe_eval(
                self.condition, get_safe_globals(), dict(doc=doc_data)
            ):
                return

        template = default_template or frappe.get_doc("WhatsApp Templates", self.template)

        if template:
            if self.field_name:
                phone_number = phone_no or resolve_document_field_value(doc, self.field_name)
            else:
                phone_number = phone_no

            if not phone_number:
                return

            to_number = self.format_number(phone_number)

            body_param = {}
            if self.fields:
                for i, field in enumerate(self.fields):
                    fn = field.field_name
                    if "." in fn or fn == "owner":
                        value = resolve_document_field_value(doc, fn, formatted=True)
                    elif isinstance(doc, Document):
                        value = doc.get_formatted(fn)
                    else: 
                        value = doc_data.get(fn)
                        if isinstance(value, (datetime.date, datetime.datetime)):
                            value = str(value)

                    if isinstance(value, (datetime.date, datetime.datetime)):
                        value = str(value)

                    body_param[str(i)] = value

            attach_url = None
            if self.attach_document_print:
                key = doc.get_document_share_key()  # noqa
                print_format = "Standard"
                doctype = frappe.get_doc("DocType", doc_data['doctype'])
                if doctype.custom:
                    if doctype.default_print_format:
                        print_format = doctype.default_print_format
                else:
                    default_print_format = frappe.db.get_value(
                        "Property Setter",
                        filters={
                            "doc_type": doc_data['doctype'],
                            "property": "default_print_format"
                        },
                        fieldname="value"
                    )
                    print_format = default_print_format if default_print_format else print_format
                link = get_pdf_link(
                    doc_data['doctype'],
                    doc_data['name'],
                    print_format=print_format
                )

                import urllib.parse
                link = urllib.parse.quote(link, safe="?&=/")
                
                pdf_generator = frappe.db.get_single_value("Print Settings", "pdf_generator")
                generator_param = f"&pdf_generator={pdf_generator.lower()}" if pdf_generator else ""

                attach_url = f'{frappe.utils.get_url()}{link}&key={key}{generator_param}'

            elif self.custom_attachment:
                if self.attach_from_field:
                    file_url = doc_data[self.attach_from_field]
                    if not file_url.startswith("http"):
                        # get share key so that private files can be sent
                        key = doc.get_document_share_key()
                        file_url = f'{frappe.utils.get_url()}{file_url}&key={key}'
                else:
                    file_url = self.attach

                if file_url.startswith("http"):
                    attach_url = f'{file_url}'
                else:
                    attach_url = f'{frappe.utils.get_url()}{file_url}'

            self.notify(to_number, body_param, attach_url, doc_data)

    def notify(self, to_number, body_param, attach_url, doc_data=None):
        """Notify."""
        # Use notification WhatsApp account if available, otherwise use a default outgoing account
        if self.whatsapp_account:
            whatsapp_account = frappe.get_doc("WhatsApp Account", self.whatsapp_account)
        else:
            whatsapp_account = get_whatsapp_account(account_type='outgoing')

        if not whatsapp_account:
            frappe.throw(_("Please set a default outgoing WhatsApp Account"))

        try:
            new_doc = {
                "doctype": "WhatsApp Message",
                "type": "Outgoing",
                "to": to_number,
                "message_type": "Template",
                "use_template": 1,
                "template": self.template,
                "body_param": json.dumps(body_param) if body_param else None,
                "attach": attach_url,
                "whatsapp_account": whatsapp_account.name,
                "status": "Queued"
            }

            if doc_data:
                new_doc.update({
                    "reference_doctype": doc_data.get("doctype"),
                    "reference_name": doc_data.get("name"),
                })

            msg_doc = frappe.get_doc(new_doc).insert(ignore_permissions=True)
            frappe.db.commit()

            if doc_data and self.set_property_after_alert and self.property_value:
                if doc_data.get("doctype") and doc_data.get("name"):
                    fieldname = self.set_property_after_alert
                    value = self.property_value
                    meta = frappe.get_meta(doc_data.get("doctype"))
                    df = meta.get_field(fieldname)
                    if df:
                        if df.fieldtype in frappe.model.numeric_fieldtypes:
                            value = frappe.utils.cint(value)

                        frappe.db.set_value(doc_data.get("doctype"), doc_data.get("name"), fieldname, value)

            frappe.msgprint("WhatsApp Message Queued for Delivery", indicator="green", alert=True)

        except Exception as e:
            frappe.log_error("WhatsApp Notification Enqueue Error", str(e))
            frappe.msgprint(
                f"Failed to queue whatsapp message: {str(e)}",
                indicator="red",
                alert=True
            )


    def on_trash(self):
        """On delete remove from schedule."""
        frappe.cache().delete_value("whatsapp_notification_map")


    def format_number(self, number):
        """Format number."""
        if not number:
            return number
        if (number.startswith("+")):
            number = number[1:len(number)]

        return number

    def get_documents_for_today(self):
        """get list of documents that will be triggered today"""
        docs = []

        diff_days = self.days_in_advance
        if self.doctype_event == "Days After":
            diff_days = -diff_days

        reference_date = add_to_date(nowdate(), days=diff_days)
        reference_date_start = reference_date + " 00:00:00.000000"
        reference_date_end = reference_date + " 23:59:59.000000"

        doc_list = frappe.get_all(
            self.reference_doctype,
            fields="name",
            filters=[
                {self.date_changed: (">=", reference_date_start)},
                {self.date_changed: ("<=", reference_date_end)},
            ],
        )

        for d in doc_list:
            doc = frappe.get_doc(self.reference_doctype, d.name)
            self.send_template_message(doc)


@frappe.whitelist()
def call_trigger_notifications():
    """Trigger notifications."""
    try:
        # Directly call the trigger_notifications function
        trigger_notifications()  
    except Exception as e:
        # Log the error but do not show any popup or alert
        frappe.log_error(frappe.get_traceback(), "Error in call_trigger_notifications")
        # Optionally, you could raise the exception to be handled elsewhere if needed
        raise e

def trigger_notifications(method="daily"):
    if frappe.flags.in_import or frappe.flags.in_patch:
        # don't send notifications while syncing or patching
        return

    if method == "daily":
        doc_list = frappe.get_all(
            "WhatsApp Notification", filters={"doctype_event": ("in", ("Days Before", "Days After")), "disabled": 0}
        )
        for d in doc_list:
            alert = frappe.get_doc("WhatsApp Notification", d.name)
            alert.get_documents_for_today()


@frappe.whitelist()
def get_doctype_fields(doctype):
    """Return mobile/phone field options and all parameter field options for a doctype and its linked doctypes."""
    if not doctype or not frappe.db.exists("DocType", doctype):
        return {"phone_options": [], "all_fields": []}

    meta = frappe.get_meta(doctype)
    phone_options = [
        {"value": "owner", "label": f"owner ({_('Owner')})"}
    ]
    all_fields = [
        {"value": "owner", "label": f"owner ({_('Owner')})"}
    ]

    def is_phone_field(df):
        fn = (df.fieldname or "").lower()
        opt = (df.options or "").lower()
        return (
            df.fieldtype == "Phone"
            or opt in ("phone", "mobile")
            or any(kw in fn for kw in ("mobile", "phone", "whatsapp", "contact_no"))
        )

    # 1. Direct fields
    for df in meta.fields:
        if df.fieldtype in NO_VALUE_FIELDS:
            continue

        label_desc = f"{df.fieldname} ({_(df.label or df.fieldname)})"
        all_fields.append({"value": df.fieldname, "label": label_desc})
        if is_phone_field(df) or df.fieldtype in ("Data", "Phone"):
            phone_options.append({"value": df.fieldname, "label": label_desc})

    # 2. Linked DocTypes
    for df in meta.fields:
        if df.fieldtype == "Link" and df.options and df.options != doctype:
            if not frappe.db.exists("DocType", df.options):
                continue
            linked_meta = frappe.get_meta(df.options)
            link_label = _(df.label or df.fieldname)
            for ldf in linked_meta.fields:
                if ldf.fieldtype in NO_VALUE_FIELDS:
                    continue
                path_val = f"{df.fieldname}.{ldf.fieldname}"
                path_label = f"{path_val} ({link_label} > {_(ldf.label or ldf.fieldname)})"
                all_fields.append({"value": path_val, "label": path_label})
                if is_phone_field(ldf) or ldf.fieldtype in ("Phone", "Data"):
                    phone_options.append({"value": path_val, "label": path_label})

    # Deduplicate
    unique_phone = []
    seen_phone = set()
    for o in phone_options:
        if o["value"] not in seen_phone:
            seen_phone.add(o["value"])
            unique_phone.append(o)

    unique_all = []
    seen_all = set()
    for o in all_fields:
        if o["value"] not in seen_all:
            seen_all.add(o["value"])
            unique_all.append(o)

    return {
        "phone_options": unique_phone,
        "all_fields": unique_all,
    }

