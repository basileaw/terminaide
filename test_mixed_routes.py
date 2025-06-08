#!/usr/bin/env python3
"""Test script to verify mixed function/script routes work in serve_apps"""

from fastapi import FastAPI
from terminaide import serve_apps, HtmlIndex
import tempfile
import os
from pathlib import Path

# Create a test function
def test_function():
    print("Hello from test function!")
    input("Press Enter to continue...")

# Create a temporary script file for testing
def create_test_script():
    script_content = '''#!/usr/bin/env python3
print("Hello from test script!")
input("Press Enter to continue...")
'''
    
    # Create temp script
    temp_dir = Path(tempfile.gettempdir()) / "terminaide_test"
    temp_dir.mkdir(exist_ok=True)
    script_path = temp_dir / "test_script.py"
    script_path.write_text(script_content)
    return script_path

def main():
    app = FastAPI()
    
    # Create test script
    script_path = create_test_script()
    
    print("Testing mixed function/script routes...")
    print(f"Script created at: {script_path}")
    
    # This should work without recursion errors
    serve_apps(
        app,
        terminal_routes={
            "/": HtmlIndex(
                title="Mixed Route Test",
                menu=[{
                    "label": "Choose a test:",
                    "options": [
                        {"path": "/function", "title": "Function Route"},
                        {"path": "/script", "title": "Script Route"}
                    ]
                }]
            ),
            "/function": test_function,  # Function route
            "/script": str(script_path),  # Script route
        },
        port=8001
    )

if __name__ == "__main__":
    main()