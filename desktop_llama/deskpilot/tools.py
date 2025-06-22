# deskpilot/tools.py
"""
deskpilot.tools – JSON schema for Llama function-calling.
"""

TOOLS = [
    {
        "name": "open_file_explorer",
        "description": "Open Windows File Explorer to the user's home directory.",
        "parameters": {"type":"object","properties":{},"required":[]},
    },
    {
        "name": "open_application",
        "description": "Open or focus a desktop application by name or path.",
        "parameters": {
            "type":"object",
            "properties": {
                "app_name": {
                    "type":"string",
                    "description":"E.g. 'chrome', 'vscode', or full .exe path",
                }
            },
            "required":["app_name"],
        },
    },
    {
        "name": "send_email",
        "description": "Send an email via Outlook (silent, no UI).",
        "parameters": {
            "type":"object",
            "properties": {
                "to":      {"type":"string","description":"Recipient address"},
                "subject": {"type":"string","description":"Subject line"},
                "body":    {"type":"string","description":"Plain-text body"},
            },
            "required":["to","subject","body"],
        },
    },
]
