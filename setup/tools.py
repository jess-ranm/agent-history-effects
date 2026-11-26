"""The three tools the model can call."""

TOOLS = [
    {"name": "list_files", "description": "List all files.",
     "parameters": {"type": "object", "properties": {}, "required": []}},
    {"name": "read_file", "description": "Read the content from a file.",
     "parameters": {"type": "object", "properties": {
         "file_name_or_path": {"type": "string", "description": "The name or path of the file."}},
         "required": ["file_name_or_path"]}},
    {"name": "delete_file", "description": "Delete a file.",
     "parameters": {"type": "object", "properties": {
         "filename": {"type": "string", "description": "The name of the file to delete."}},
         "required": ["filename"]}},
]
