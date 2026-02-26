"""Provenance display helpers."""


def mask_address(address: str) -> str:
    if len(address) <= 10:
        return address
    return address[:6] + "..." + address[-4:]


def resolve_display_name(
    user_id: int | None,
    display_names: dict[int, str | None],
    wallet_addresses: dict[int, str],
) -> str | None:
    if user_id is None:
        return None
    name = display_names.get(user_id)
    if name:
        return name
    address = wallet_addresses.get(user_id)
    if address:
        return mask_address(address)
    return f"user#{user_id}"
