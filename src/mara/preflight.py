"""Pre-flight checks to run *before* starting a protocol on Capy.

Right now there's one check: snap a still from the onboard camera, save it
locally, and ask the human to eyeball the deck before play. Designed to be
called from a CLI or example; the prompt is injectable for tests.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from src.mara.runtime import CapyClient

Prompt = Callable[[str], bool]


def _stdin_prompt(message: str) -> bool:
    answer = input(message).strip().lower()
    return answer in ("y", "yes")


def confirm_deck_state(
    client: CapyClient,
    *,
    image_path: Path = Path("preflight.jpg"),
    prompt: Prompt = _stdin_prompt,
    out: object = sys.stderr,
) -> bool:
    """Snap a picture, save it, ask the user to confirm. Returns True if confirmed."""
    image_bytes = client.take_picture()
    image_path.write_bytes(image_bytes)
    print(
        f"Saved deck snapshot to {image_path.resolve()}. "
        "Open it and check that the deck matches the protocol's expected initial state.",
        file=out,
    )
    return prompt("Proceed with run? [y/N] ")
