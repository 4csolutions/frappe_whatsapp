import frappe

def get_provider(whatsapp_account_name):
    account = frappe.get_doc("WhatsApp Account", whatsapp_account_name)
    provider_name = account.provider or "Meta"

    if provider_name == "Meta":
        from frappe_whatsapp.providers.meta import MetaProvider
        return MetaProvider(account)
    elif provider_name == "Evolution API":
        from frappe_whatsapp.providers.evolution import EvolutionProvider
        return EvolutionProvider(account)
    else:
        frappe.throw(f"Unsupported WhatsApp Provider: {provider_name}")
