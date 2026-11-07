#!/usr/bin/env python3
"""Create a Telethon StringSession interactively for the source-monitor service.

Run this only in a private, trusted terminal (for example, your own Codespace).
Never commit or share the printed session string.
"""
from getpass import getpass

from telethon.sync import TelegramClient
from telethon.sessions import StringSession


def main() -> None:
    raw_api_id = input("API ID: ").strip()
    if not raw_api_id.isdigit():
        raise SystemExit("API ID must contain digits only.")

    api_hash = getpass("API Hash (hidden): ").strip()
    if not api_hash:
        raise SystemExit("API Hash cannot be empty.")

    phone = input("Phone number in international format (e.g. +20...): ").strip()
    if not phone.startswith("+"):
        raise SystemExit("Enter the phone number in international format, starting with +.")

    print("\nConnecting to Telegram. Enter the login code when prompted.")
    print("If two-step verification is enabled, enter its password when prompted.\n")

    with TelegramClient(StringSession(), int(raw_api_id), api_hash) as client:
        client.start(phone=phone)
        session_string = client.session.save()

    print("\nLOGIN SUCCESSFUL")
    print("Copy the value below directly into the GitHub Actions secret named TELEGRAM_SESSION.")
    print("Do not send it in chat, commit it, or share a screenshot of it.\n")
    print(session_string)


if __name__ == "__main__":
    main()
