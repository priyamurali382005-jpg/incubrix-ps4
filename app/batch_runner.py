import argparse
import json
import os
import pathlib
import sys
import time
import uuid

import httpx

TERMINAL = {"succeeded", "failed"}


def _auth(token):
    return {"X-API-Key": token} if token else {}


def _resolve(client, token, ref):
    for d in client.get("/api/v1/destinations", headers=_auth(token)).json()["items"]:
        if d["name"] == ref.get("name") or d["id"] == ref.get("id"):
            return d["id"]
    raise ValueError(f"destination not found: {ref}")


def run_case(client, case, base_dir, token, poll_s, timeout_s):
    key = case.get("idempotency_key") or uuid.uuid4().hex
    headers = {**_auth(token), "Idempotency-Key": key}
    kind = case["type"]
    if kind == "import_csv":
        text = (base_dir / case["csv_file"]).read_text(encoding="utf-8-sig")
        r = client.post("/api/v1/destinations/import", content=text.encode(),
                        headers={**headers, "Content-Type": "text/csv"})
        return {"http_status": r.status_code, "response": r.json()}
    if kind in ("publication", "certification"):
        body = dict(case["body"])
        if "destination" in body:
            body["destination_id"] = _resolve(client, token, body.pop("destination"))
        path = "/api/v1/publications" if kind == "publication" else "/api/v1/certifications"
        r = client.post(path, json=body, headers=headers)
        out = {"http_status": r.status_code, "submit": r.json()}
        if r.status_code != 202:
            return out
        deadline = time.monotonic() + timeout_s
        while True:
            job = client.get(f"/api/v1/jobs/{r.json()['job_id']}", headers=_auth(token)).json()
            if job["status"] in TERMINAL or time.monotonic() > deadline:
                break
            time.sleep(poll_s)
        out["job"] = job
        return out
    raise ValueError(f"unknown case type: {kind}")


def _problems(expect, out):
    job = out.get("job") or {}
    got = {"http_status": out.get("http_status"), "job_status": job.get("status"),
           "error_code": (job.get("error") or {}).get("code"),
           "outcome": (job.get("result") or {}).get("outcome"),
           "cert_result": (job.get("result") or {}).get("result")}
    return [f"{k}: expected {v!r}, got {got.get(k)!r}" for k, v in expect.items() if got.get(k) != v]


def run_folder(client, inputs: pathlib.Path, out_dir: pathlib.Path, token=None, poll_s=1.0, timeout_s=120):
    out_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(inputs.glob("*.json")) if inputs.is_dir() else [inputs]
    summary = {"total": 0, "passed": 0, "failed": 0, "cases": []}
    for f in files:
        case = json.loads(f.read_text(encoding="utf-8-sig"))
        try:
            out = run_case(client, case, f.parent, token, poll_s, timeout_s)
            problems = _problems(case.get("expect", {}), out)
        except Exception as exc:
            out, problems = {"error": f"{type(exc).__name__}: {exc}"}, [f"crashed: {type(exc).__name__}"]
        (out_dir / f"{f.stem}.result.json").write_text(json.dumps(out, indent=2, default=str))
        ok = not problems
        summary["total"] += 1
        summary["passed" if ok else "failed"] += 1
        summary["cases"].append({"case": f.name, "ok": ok, "problems": problems})
        print(f"{'PASS' if ok else 'FAIL'}  {f.name}  {'; '.join(problems)}")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\n{summary['passed']}/{summary['total']} passed -> {out_dir}")
    return 0 if summary["failed"] == 0 else 1


def main():
    p = argparse.ArgumentParser(description="Run a folder of JSON test cases against the API.")
    p.add_argument("--url", default=os.environ.get("INCUBRIX_URL", "http://localhost:8000"))
    p.add_argument("--token", default=os.environ.get("INCUBRIX_TOKEN"))
    p.add_argument("--inputs", default="batch_inputs")
    p.add_argument("--out", default="batch_results")
    p.add_argument("--poll", type=float, default=1.0)
    args = p.parse_args()
    with httpx.Client(base_url=args.url, timeout=60) as client:
        sys.exit(run_folder(client, pathlib.Path(args.inputs), pathlib.Path(args.out), args.token, args.poll))


if __name__ == "__main__":
    main()

