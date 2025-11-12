from fastapi import FastAPI
import httpx
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_BASE = "https://cloud-trader-880429861698.us-central1.run.app"

@app.get("/healthz")
async def healthz():
    return {"status": "ok", "service": "cloud-trader"}

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def proxy(path: str, request: httpx.Request):
    async with httpx.AsyncClient() as client:
        url = f"{API_BASE}/{path}"
        response = await client.request(
            request.method,
            url,
            headers=dict(request.headers),
            params=request.query_params,
            content=await request.body()
        )
        return response.json()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
