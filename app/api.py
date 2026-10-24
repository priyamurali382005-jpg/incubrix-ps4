from fastapi import APIRouter, Body
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