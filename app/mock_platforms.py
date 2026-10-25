
import hashlib
import hmac
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

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
        "rename_id": False,
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

    if "rename_id" in body:
        STATE["rename_id"] = bool(body["rename_id"])

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

    body = {
        "id": post_id,
        "topic_id": post_id,
        "topic_slug": "mock-topic",
    }

    if STATE["rename_id"]:
        body["post_id"] = body.pop("id")

    return body


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

    if post.get("published") is False:
        post["deleted"] = True

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


# ---------- Lemmy ----------
@mock_app.post("/lemmy/api/v3/user/login")
async def l_login(request: Request):
    body = await request.json()

    if body.get("password") == "expired":
        return JSONResponse(
            {"error": "incorrect_login"},
            status_code=400,
        )

    return {"jwt": "mock-jwt"}


@mock_app.get("/lemmy/api/v3/community")
def l_community(name: str):
    return {
        "community_view": {
            "community": {
                "id": 1,
                "name": name,
            }
        }
    }


@mock_app.post("/lemmy/api/v3/post")
async def l_create(request: Request):
    if request.headers.get("Authorization") != "Bearer mock-jwt":
        return JSONResponse(
            {"error": "not_logged_in"},
            status_code=400,
        )

    data = await request.json()

    if not data.get("name") or len(data["name"]) > 200:
        return JSONResponse(
            {"error": "invalid_post_title"},
            status_code=400,
        )

    post_id = _new_id()
    STATE["posts"][f"lemmy:{post_id}"] = {
        **data,
        "deleted": False,
        "removed": False,
    }

    return {
        "post_view": {
            "post": {
                "id": post_id,
                "name": data["name"],
                "deleted": False,
                "removed": False,
            }
        }
    }


@mock_app.get("/lemmy/api/v3/post")
def l_get(id: int):
    post = STATE["posts"].get(f"lemmy:{id}")

    if not post:
        return JSONResponse(
            {"error": "couldnt_find_post"},
            status_code=400,
        )

    return {
        "post_view": {
            "post": {
                "id": id,
                "deleted": post["deleted"],
                "removed": post.get("removed", False),
            }
        }
    }


@mock_app.post("/lemmy/api/v3/post/delete")
async def l_delete(request: Request):
    data = await request.json()
    post_id = data["post_id"]
    post = STATE["posts"].get(f"lemmy:{post_id}")

    if post:
        post["deleted"] = True

    return {
        "post_view": {
            "post": {
                "id": post_id,
                "deleted": True,
            }
        }
    }


# ---------- Ghost ----------
def _ghost_ok(request: Request):
    return request.headers.get("Authorization", "").startswith("Ghost ")


@mock_app.post("/ghost/ghost/api/admin/posts/")
async def g_create(request: Request):
    if not _ghost_ok(request):
        return JSONResponse(
            {"errors": [{"message": "Authorization failed"}]},
            status_code=401,
        )

    post = (await request.json())["posts"][0]

    if not post.get("title") or len(post["title"]) > 255:
        return JSONResponse(
            {"errors": [{"message": "invalid"}]},
            status_code=422,
        )

    post_id = str(_new_id())
    STATE["posts"][f"ghost:{post_id}"] = post

    return JSONResponse(
        {
            "posts": [{
                "id": post_id,
                "url": f"http://mock/ghost/{post_id}/",
                "status": "published",
            }]
        },
        status_code=201,
    )


@mock_app.get("/ghost/ghost/api/admin/posts/{pid}/")
def g_get(pid: str, request: Request):
    if not _ghost_ok(request):
        return JSONResponse({}, status_code=401)

    if f"ghost:{pid}" not in STATE["posts"]:
        return JSONResponse({}, status_code=404)

    post = STATE["posts"][f"ghost:{pid}"]

    return {
        "posts": [{
            "id": pid,
            "url": f"http://mock/ghost/{pid}/",
            "status": post.get("status", "published"),
        }]
    }


@mock_app.delete("/ghost/ghost/api/admin/posts/{pid}/")
def g_delete(pid: str, request: Request):
    if not _ghost_ok(request):
        return JSONResponse({}, status_code=401)

    STATE["posts"].pop(f"ghost:{pid}", None)
    return Response(status_code=204)
