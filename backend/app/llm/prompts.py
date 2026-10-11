"""Prompts are files in app/llm/prompts/. The first line is `version: N`."""

from dataclasses import dataclass
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


@dataclass(frozen=True)
class Prompt:
    name: str
    version: int
    text: str


def load_prompt(name: str) -> Prompt:
    """Read `<name>.md`: a `version: N` line, a `---` line, then the text."""
    header, separator, text = (
        (PROMPTS_DIR / f"{name}.md").read_text().partition("\n---\n")
    )
    if not separator or not header.startswith("version: "):
        raise ValueError(f"prompt {name} needs a 'version: N' line, then '---'")
    return Prompt(
        name=name, version=int(header.removeprefix("version: ")), text=text.strip()
    )
