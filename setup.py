"""
setup.py - type what you want in plain English, a local model turns it into config.json

Run:  python setup.py
"""
import json
from datetime import datetime
from typing import List

import ollama
from pydantic import BaseModel, Field, ValidationError

MODEL = "gemma4:e4b"
CONFIG_FILE = "config.json"


class Reminder(BaseModel):
    name: str                      # short title, e.g. "Water"
    every_min: int = Field(ge=1)   # how often, in minutes
    task: str                      # starts with a verb, e.g. "drink a glass of water"


class Config(BaseModel):
    # No defaults here on purpose: a default in the schema makes small models just copy it.
    personality: str = Field(description=(
        "The tone or voice the person asked for, copied from their words "
        "(e.g. 'sarcastic friend', 'pirate', 'calm coach'). Write 'none' only if they did not mention any tone."))
    active_from: str = Field(description="Earliest time for reminders, HH:MM 24-hour. '00:00' if no limit.")
    active_to: str = Field(description="Latest time for reminders, HH:MM 24-hour. '23:59' if no limit.")
    reminders: List[Reminder]


SYSTEM = """You convert a person's request into a JSON config for a break-reminder app.
Rules:
- every_min is always in MINUTES (1 hour = 60, 90 seconds is not allowed, round up to 1).
- name is one short word or two (Water, Eyes, Stretch).
- task is a phrase that starts with a verb and fits after "remind me to", e.g. "drink a glass of water".
- active_from / active_to use 24-hour HH:MM. "nothing before 9am or after 8pm" means active_from "09:00", active_to "20:00".
- If no time limits are mentioned, use active_from "00:00" and active_to "23:59".
- personality: copy the tone or voice the person asked for, in their own words. "sarcastic friend tone" becomes "sarcastic friend". "talk like a pirate" becomes "pirate". Use "none" only if no tone is mentioned at all.
- Only include reminders the person actually asked for.

Example request: "water every 30 min, pirate voice, only between 10am and 6pm"
Example result: personality "pirate", active_from "10:00", active_to "18:00", one reminder named Water with every_min 30 and task "drink a glass of water"."""


def check_times(cfg: Config) -> None:
    """Raise ValueError if the times are not valid HH:MM."""
    for t in (cfg.active_from, cfg.active_to):
        datetime.strptime(t, "%H:%M")


def parse_request(text: str) -> Config:
    last_error = None
    for attempt in range(3):
        try:
            r = ollama.chat(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": text},
                ],
                format=Config.model_json_schema(),  # forces JSON in this shape
                think=False,
                options={"temperature": 0},
            )
            cfg = Config.model_validate_json(r.message.content)
            check_times(cfg)
            if not cfg.reminders:
                raise ValueError("no reminders found")
            if cfg.personality.strip().lower() in ("", "none", "n/a", "null"):
                cfg.personality = "friendly"     # no tone requested
            return cfg
        except (ValidationError, ValueError) as e:
            last_error = e
            print(f"  (attempt {attempt + 1} gave a bad result, retrying...)")
    raise RuntimeError(f"Could not understand the request: {last_error}")


def show(cfg: Config) -> None:
    print("\nHere is what I understood:\n")
    print(f"  Personality : {cfg.personality}")
    print(f"  Active hours: {cfg.active_from} to {cfg.active_to}")
    for r in cfg.reminders:
        print(f"  - {r.name}: every {r.every_min} min -> {r.task}")
    print()


def main() -> None:
    print("Tell me what reminders you want, in plain English.")
    print('Example: remind me to drink water every 45 min, rest my eyes every 20,')
    print("         stretch every hour, nothing before 9am or after 8pm, sarcastic friend tone\n")
    text = input("> ").strip()
    if not text:
        print("Nothing typed, bye.")
        return

    print("\nThinking (the first run is slower while the model loads)...")
    try:
        cfg = parse_request(text)
    except RuntimeError as e:
        print(e)
        print("Try rephrasing, for example: 'water every 45 minutes, eyes every 20 minutes'.")
        return

    show(cfg)
    if input("Save this? (y/n) ").strip().lower() == "y":
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg.model_dump(), f, indent=2)
        print(f"Saved to {CONFIG_FILE}. Now run: python breakbuddy.py")
    else:
        print("Not saved. Run setup.py again to retry.")


if __name__ == "__main__":
    main()