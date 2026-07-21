"""SoloLedger REST API — convenience re-export from modular package.

For new imports, use `from app.api import app` directly.
This file exists only for backward compatibility.
"""
import sys
import warnings

warnings.warn(
    "Import from 'app.api' directly instead of 'app.api' module — "
    "the package at app/api/ is now the canonical source.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export the app from the modular package
from app.api import app  # noqa: F401

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("API_PORT", 8100))
    uvicorn.run("app.api:app", host="0.0.0.0", port=port, reload=True)
