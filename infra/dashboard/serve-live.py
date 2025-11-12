#!/usr/bin/env python3
"""
Live Dashboard Static File Server
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from starlette.exceptions import HTTPException
import os
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Sapphire AI Live Dashboard")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load index.html from static directory
def load_index_html():
    """Load index.html from static directory"""
    static_path = os.getenv("STATIC_PATH", "/app/static")
    index_path = os.path.join(static_path, "index.html")
    if os.path.exists(index_path):
        with open(index_path, 'r', encoding='utf-8') as f:
            return f.read()
    # Fallback HTML if index.html not found
    return """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Sapphire AI - Live Trading Dashboard</title>
  </head>
  <body class="bg-gray-100">
    <div id="root"></div>
  </body>
</html>"""

LIVE_HTML = load_index_html()

@app.exception_handler(404)
async def custom_404_handler(request: Request, exc: HTTPException):
    """Serve index.html for all non-asset routes (SPA support)"""
    if not request.url.path.startswith("/assets/") and not request.url.path.startswith("/api/"):
        return HTMLResponse(content=LIVE_HTML, headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY"
        })
    return HTMLResponse(content="Not Found", status_code=404)

@app.get("/")
async def serve_root():
    """Serve the main index.html"""
    return HTMLResponse(content=LIVE_HTML, headers={
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY"
    })

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "sapphire-dashboard-live",
        "mode": "production"
    }

# Mount static files with proper cache headers
static_path = os.getenv("STATIC_PATH", "/app/static")
if os.path.exists(static_path):
    @app.middleware("http")
    async def add_cache_headers(request: Request, call_next):
        response = await call_next(request)
        
        # Add cache headers based on file type
        if request.url.path.startswith("/assets/"):
            if any(pattern in request.url.path for pattern in ["-D_", "-C9", "-OC", "-P-"]):
                # Hashed assets can be cached for a year
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            else:
                # Other assets get moderate caching
                response.headers["Cache-Control"] = "public, max-age=3600"
        else:
            # HTML and other content should not be cached
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        
        return response
    
    # Mount assets directory
    assets_path = os.path.join(static_path, "assets")
    if os.path.exists(assets_path):
        app.mount("/assets", StaticFiles(directory=assets_path), name="assets")
        logger.info(f"Mounted assets from {assets_path}")
    else:
        logger.warning(f"Assets directory not found at {assets_path}")
else:
    logger.warning(f"Static path {static_path} does not exist")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
