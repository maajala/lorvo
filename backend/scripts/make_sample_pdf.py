"""Regenerate samples/it-security-policy.pdf (a fictional policy for demos).

Usage (from backend/): uv run python scripts/make_sample_pdf.py
"""

import textwrap
from pathlib import Path
from typing import Any

import pymupdf

_fitz: Any = pymupdf
OUT = Path(__file__).resolve().parents[2] / "samples" / "it-security-policy.pdf"

# (kind, text): kind is "h1", "h2" or "p"
CONTENT: list[tuple[str, str]] = [
    ("h1", "IT Security Policy"),
    ("p", "Fernhill Labs (fictional sample data). Applies to all employees and contractors."),
    ("h2", "Passwords and Authentication"),
    (
        "p",
        "Use the company password manager, 1Pass, for every work account. Passwords must be "
        "at least 14 characters and unique per service. Multi-factor authentication is "
        "required for email, GitHub, AWS and PeopleHub; use a hardware key or an "
        "authenticator app, not SMS.",
    ),
    ("h2", "Lost or Stolen Devices"),
    (
        "p",
        "Report a lost or stolen laptop or phone to security@fernhill.example within one "
        "hour, even outside working hours. IT will remotely lock and wipe the device. You "
        "will not be blamed for reporting quickly; late reports make incidents worse.",
    ),
    ("h2", "Data Classification"),
    (
        "p",
        "Data is Public, Internal, Confidential or Restricted. Customer personal data is "
        "Restricted: it must stay in production systems and must never be copied to "
        "laptops, spreadsheets, or AI tools that are not approved by the security team.",
    ),
    ("h2", "Approved Software"),
    (
        "p",
        "Install software from the Self Service app. Anything else needs approval in the "
        "#it-requests channel. Browser extensions that can read page content require "
        "security review before installation.",
    ),
    ("h2", "Phishing"),
    (
        "p",
        "Forward suspicious emails to phishing@fernhill.example and then delete them. IT "
        "will never ask for your password or an MFA code by email, chat or phone.",
    ),
]

STYLE = {"h1": (20.0, "hebo"), "h2": (14.0, "hebo"), "p": (11.0, "helv")}


def main() -> None:
    doc = _fitz.open()
    page = doc.new_page()
    y = 72.0
    for kind, text in CONTENT:
        size, font = STYLE[kind]
        lines = textwrap.wrap(text, 85) if kind == "p" else [text]
        if kind != "p":
            y += size * 0.6
        for line in lines:
            if y > 760:
                page = doc.new_page()
                y = 72.0
            page.insert_text((72, y), line, fontsize=size, fontname=font)
            y += size * 1.5
        y += 6
        if kind == "h2" and text == "Data Classification":
            page = doc.new_page()  # spread across pages so citations show page numbers
            y = 72.0
    doc.set_metadata({"title": "IT Security Policy"})
    doc.save(OUT)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
