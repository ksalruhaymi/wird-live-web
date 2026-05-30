from identity.accounts.models import SystemAuthSettings


def get_auth_settings():
    return SystemAuthSettings.get_settings()


def is_db_login_allowed() -> bool:
    settings_obj = get_auth_settings()
    return settings_obj.allow_db_login
