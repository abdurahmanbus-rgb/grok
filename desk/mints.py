# mints.py
# Solana mint shape only. this is not a security check and it is not a pass.
_ALPHABET = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")


def is_valid_mint(value) -> bool:
    """Full mint string, case-sensitive. 32 to 44 base58 characters. No shortening."""
    if not isinstance(value, str) or value != value.strip():
        return False
    if not 32 <= len(value) <= 44:
        return False
    return all(ch in _ALPHABET for ch in value)
