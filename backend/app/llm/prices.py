"""Cost of a call from a price table. USD per million tokens, by model.

Source: https://platform.claude.com/docs/en/about-claude/pricing, read on
2026-10-11. Update the table when a price or model changes. An unknown
model costs 0, and the log line shows it.
"""

from decimal import Decimal

PRICES_PER_MILLION: dict[str, tuple[Decimal, Decimal]] = {
    # model: (input, output)
    "claude-sonnet-5-5": (Decimal("2.00"), Decimal("10.00")),
    # Prompts up to 100,000 tokens. Longer prompts cost five times more.
    "claude-haiku-5-5": (Decimal("0.10"), Decimal("0.50")),
}

MILLION = Decimal(1_000_000)


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    input_price, output_price = PRICES_PER_MILLION.get(model, (Decimal(0), Decimal(0)))
    return (input_price * input_tokens + output_price * output_tokens) / MILLION
