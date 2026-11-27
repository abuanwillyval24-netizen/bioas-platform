from django.apps import AppConfig


class GovernanceConfig(AppConfig):
    name = 'governance'


from django.core.checks import Warning, register

@register()
def check_sidebar_template_integrity(app_configs, **kwargs):
    import re
    from pathlib import Path
    tpl = Path(__file__).resolve().parent.parent / "bioas_core" / "templates" / "governance" / "dashboard.html"
    if not tpl.exists():
        return []
    txt = tpl.read_text(encoding="utf-8")
    links = set(re.findall("tier=BARANGAY&module=([A-Z0-9_]+)", txt))
    handlers = set(re.findall(r'module == [\x22\x27]([A-Z0-9_]+)[\x22\x27]', txt))
    missing = sorted(links - handlers)
    return [Warning(f"Sidebar module links missing template handlers: {missing}", id="governance.W001")] if missing else []
