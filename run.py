"""
Development Server Runner
Safely launches Uvicorn without watching the virtual environment or database files.
Prevents infinite reload loops triggered by site-packages file access or OneDrive syncing.
"""
import sys
from pathlib import Path
import uvicorn

if __name__ == "__main__":
    backend_dir = Path(__file__).parent.resolve()
    sys.path.insert(0, str(backend_dir))

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=[
            str(backend_dir / "api"),
            str(backend_dir / "auth"),
            str(backend_dir / "core"),
            str(backend_dir / "db"),
            str(backend_dir / "models"),
            str(backend_dir / "services"),
        ],
        reload_includes=["app.py"],
        reload_excludes=["venv", "venv/*", "*.db*", "*sqlite*", "__pycache__*"],
    )
