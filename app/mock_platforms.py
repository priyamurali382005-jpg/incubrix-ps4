import hashlib
import hmac
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

mock_app = FastAPI(title="Mock platforms")
STATE: dict = {}


def reset_state():
    STATE.clear()
    STATE.update({
        "posts": {},
        "next_id": 1,
        "fail_next": [],
        "create_then_fail": False,
        "idem": {},
    })


reset_state()


def _new_id():
    post_id = STATE["next_id"]
    STATE["next_id"] += 1
    return post_id


@mock_app.middleware("http")
async def failure_injection(request: Request, call_next):
    if request.url.path.startswith("/_control"):
        return await call_next(request)

    if STATE["fail_next"]:
        status = STATE["fail_next"].pop(0)
        headers = {"Retry-After": "30"} if status == 429 else {}
        return JSONResponse(
            {"message": f"injected {status}"},
            status_code=status,
            headers=headers,
        )

    response = await call_next(request)

    if STATE["create_then_fail"] and request.method == "POST":
        STATE["create_then_fail"] = False
        return JSONResponse(
            {"message": "gateway timeout"},
            status_code=504,
        )

    return response


@mock_app.post("/_control")
async def control(request: Request):
    body = await request.json()

    if body.get("reset"):
        reset_state()

    if "fail_next" in body:
        STATE["fail_next"] = list(body["fail_next"])

    if "create_then_fail" in body:
        STATE["create_then_fail"] = bool(body["create_then_fail"])

    return {"ok": True}


@mock_app.get("/_control/posts")
def all_posts():
    return STATE["posts"]


def _key_ok(key):
    return bool(key) and key != "expired"


# ---------- Discourse ----------
@mock_app.post("/discourse/posts.json")
async def d_create(request: Request):
    if not _key_ok(request.headers.get("Api-Key")):
        return JSONResponse({"errors": ["bad key"]}, status_code=401)

    data = await request.json()

    if len(data.get("title", "")) > 255 or not data.get("raw"):
        return JSONResponse({"errors": ["invalid"]}, status_code=422)

    post_id = _new_id()
    STATE["posts"][f"discourse:{post_id}"] = data

    return {
        "id": post_id,
        "topic_id": post_id,
        "topic_slug": "mock-topic",
    }


@mock_app.get("/discourse/posts/{pid}.json")
def d_get(pid: int):
    if f"discourse:{pid}" not in STATE["posts"]:
        return JSONResponse({}, status_code=404)

    return {
        "id": pid,
        "topic_id": pid,
        "topic_slug": "mock-topic",
    }


@mock_app.delete("/discourse/posts/{pid}.json")
def d_delete(pid: int):
    STATE["posts"].pop(f"discourse:{pid}", None)
    return {"ok": True}


# ---------- Dev.to ----------
@mock_app.post("/devto/api/articles")
async def dv_create(request: Request):
    if not _key_ok(request.headers.get("api-key")):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    article = (await request.json()).get("article", {})

    if len(article.get("title", "")) > 128 or not article.get("title"):
        return JSONResponse({"error": "invalid"}, status_code=422)

    post_id = _new_id()
    STATE["posts"][f"devto:{post_id}"] = {
        **article,
        "published": True,
    }

    return {
        "id": post_id,
        "url": f"http://mock/devto/mock-user/article-{post_id}",
    }


@mock_app.get("/devto/api/articles/{pid}")
def dv_get(pid: int):
    post = STATE["posts"].get(f"devto:{pid}")

    if not post:
        return JSONResponse({}, status_code=404)

    return {
        "id": pid,
        "url": f"http://mock/devto/mock-user/article-{pid}",
        "published": post["published"],
    }


@mock_app.put("/devto/api/articles/{pid}")
async def dv_update(pid: int, request: Request):
    post = STATE["posts"].get(f"devto:{pid}")

    if not post:
        return JSONResponse({}, status_code=404)

    post.update((await request.json()).get("article", {}))
    return {"id": pid}


# ---------- Signed webhook ----------
async def _verify(request: Request):
    body = await request.body()
    secret = os.environ.get("MOCK_WEBHOOK_SECRET", "demo-secret")

    expected = "sha256=" + hmac.new(
        secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(
        request.headers.get("X-IncuBrix-Signature", ""),
        expected,
    )


@mock_app.post("/webhook/receive")
async def w_create(request: Request):
    if not await _verify(request):
        return JSONResponse({"error": "bad signature"}, status_code=401)

    key = request.headers.get("Idempotency-Key")

    if key and key in STATE["idem"]:
        return STATE["idem"][key]

    post_id = _new_id()
    STATE["posts"][f"webhook:{post_id}"] = {"received": True}

    result = {
        "id": post_id,
        "url": f"http://mock/webhook/view/{post_id}",
    }

    if key:
        STATE["idem"][key] = result

    return result


@mock_app.get("/webhook/receive/{pid}")
async def w_get(pid: int, request: Request):
    if not await _verify(request):
        return JSONResponse({"error": "bad signature"}, status_code=401)

    if f"webhook:{pid}" not in STATE["posts"]:
        return JSONResponse({}, status_code=404)

    return {
        "id": pid,
        "url": f"http://mock/webhook/view/{pid}",
    }


@mock_app.delete("/webhook/receive/{pid}")
async def w_delete(pid: int, request: Request):
    if not await _verify(request):
        return JSONResponse({"error": "bad signature"}, status_code=401)

    STATE["posts"].pop(f"webhook:{pid}", None)
    return {"ok": True}
