"""
core/tools_schema.py
────────────────────
Tool JSON schemas exposed to the models.
"""

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List files and folders inside an allowed directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path to list"}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_similar_files",
            "description": "Search for files whose name contains keywords from the query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keywords to search for"},
                    "root": {"type": "string", "description": "Directory to search inside"},
                },
                "required": ["query", "root"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read full text content of a file. ONLY use for small files (<20KB).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to read"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file_lines",
            "description": "Read an inclusive line range from a file (1-indexed). Context efficient.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to read"},
                    "start_line": {"type": "integer", "description": "First line to read (1-indexed)"},
                    "end_line": {"type": "integer", "description": "Last line to read (inclusive)"},
                },
                "required": ["path", "start_line", "end_line"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stat_file",
            "description": "Get file metadata (size, modified date, total lines) without reading content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a shell command and return its stdout, stderr, and exit code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "cmd": {"type": "string", "description": "Shell command to execute"},
                },
                "required": ["cmd"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a file in the output folder.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Filename only, no path"},
                    "content": {"type": "string", "description": "Full text content to write"},
                    "append": {"type": "boolean", "description": "Append instead of overwrite"},
                },
                "required": ["filename", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file_lines",
            "description": "Edit an existing text file by replacing a line range. Creates a backup before writing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                    "start_line": {"type": "integer", "description": "1-indexed starting line"},
                    "end_line": {"type": "integer", "description": "1-indexed ending line"},
                    "new_text": {"type": "string", "description": "Replacement text"},
                },
                "required": ["path", "start_line", "end_line", "new_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "alert_user",
            "description": "Send a system notification to the user for status updates or attention.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Notification title"},
                    "message": {"type": "string", "description": "Notification message"},
                },
                "required": ["title", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": "Ask the user a clarification question before continuing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "Clarification question"},
                },
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_scratchpad",
            "description": "Save critical insights, decisions, variable names, and notes/reminders to your scratchpad.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key_discoveries": {"type": "string", "description": "New facts, constraints, or architecture details"},
                    "notes": {"type": "string", "description": "Important reminders or next steps"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall_memory",
            "description": "Search your long-term memory for past architectural decisions, previously solved bugs, API conventions, or user preferences relevant to this project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query or concept to recall"},
                },
                "required": ["query"],
            },
        },
    },
]
