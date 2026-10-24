from fastapi import APIRouter, Body, Header
from pydantic import BaseModel, Field

from app import catalogue
from app.errors import AppError
from app.rules import evaluate

router = APIRouter()


class PostIn(BaseModel):
    title: str
    body: str = ""
    links: list[str] = Field(default_factory=list)
    is_promotional: bool = False
    ai_generated: bool = False
    ai_disclosure_included: bool = False
    canonical_url: str | None = None
    tags: list[str] = Field(default_factory=list)

class RuleCheckIn(BaseModel):
    destination_id: int
    post: PostIn


@router.post("/destinations", status_code=201)
def create_destination(payload: dict = Body(...)):
    status, result = catalogue.add_destination(payload)
    if status == "invalid":
        raise AppError("DEST_SPEC_VIOLATION", "Destination is invalid.", 422, details={"errors": result})
    if status == "duplicate":
        raise AppError("DESTINATION_DUPLICATE", "This destination already exists.", 409)
    return {"id": result}


@router.get("/destinations")
def get_destinations():
    return {"items": catalogue.list_destinations()}


@router.post("/destinations/import")
def import_destinations(csv_text: str = Body(..., media_type="text/csv")):
    return catalogue.import_csv(csv_text)


@router.post("/rules/check")
def check_rules(payload: RuleCheckIn):
    dest = catalogue.get_destination(payload.destination_id)
    if not dest:
        raise AppError("DESTINATION_NOT_FOUND", "No such destination.", 404)
    history = catalogue.recent_post_times(payload.destination_id)
    decision = evaluate(dest, payload.post.model_dump(), history)
    return decision.to_dict()

from app import jobs, workflow
from app.logging_utils import correlation_id


class PublicationIn(BaseModel):
    destination_id: int
    post: PostIn
    callback_url: str | None = None


@router.post("/publications", status_code=202)
def create_publication(
    payload: PublicationIn,
    idempotency_key: str | None = Header(default=None),
):
    if not idempotency_key:
        raise AppError(
            "IDEMPOTENCY_KEY_REQUIRED",
            "Send an Idempotency-Key header.",
            400,
        )

    if not catalogue.get_destination(payload.destination_id):
        raise AppError(
            "DESTINATION_NOT_FOUND",
            "No such destination.",
            404,
        )

    job_id, created = jobs.submit(
        idempotency_key,
        payload.model_dump(),
        correlation_id.get(),
    )

    if created:
        workflow.dispatch(job_id)

    return {
        "job_id": job_id,
        "status_url": f"/api/v1/jobs/{job_id}",
        "reused": not created,
    }


@router.get("/jobs/{job_id}")
def get_job_status(job_id: str):
    job = jobs.get_job(job_id)

    if not job:
        raise AppError(
            "JOB_NOT_FOUND",
            "No such job.",
            404,
        )

    return jobs.public_view(job)
