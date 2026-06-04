"""Base62 short-code encoding (pure, testable)."""
ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
BASE = len(ALPHABET)


def encode(n: int) -> str:
    if n < 0:
        raise ValueError("n must be non-negative")
    if n == 0:
        return ALPHABET[0]
    out = []
    while n:
        n, rem = divmod(n, BASE)
        out.append(ALPHABET[rem])
    return "".join(reversed(out))


def decode(code: str) -> int:
    n = 0
    for ch in code:
        n = n * BASE + ALPHABET.index(ch)
    return n
