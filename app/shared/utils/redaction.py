def mask_email(email: str) -> str:
    if "@" not in email:
        return "***"

    local, domain = email.split("@", 1)
    if not local:
        return f"***@{domain}"

    if len(local) < 2:
        masked_local = local[0] + "***"
    else:
        masked_local = local[:2] + "***"
    return f"{masked_local}@{domain}"
