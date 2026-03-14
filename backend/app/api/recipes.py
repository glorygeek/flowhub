from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.common import RiskLevel, ReviewStatus
from app.models.recipe import Recipe
from app.schemas.recipe_schema import RecipeCreate, RecipeRead, RecipeUpdate

router = APIRouter(prefix="/recipes", tags=["recipes"])


@router.get("/", response_model=list[RecipeRead])
def list_recipes(
    db: Session = Depends(get_db),
    scenario: str | None = Query(default=None),
    risk_level: RiskLevel | None = Query(default=None),
    status_filter: ReviewStatus | None = Query(default=None, alias="status"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
):
    query = select(Recipe)
    if scenario:
        query = query.where(Recipe.scenario.ilike(f"%{scenario}%"))
    if risk_level:
        query = query.where(Recipe.risk_level == risk_level)
    if status_filter:
        query = query.where(Recipe.status == status_filter)
    query = query.offset(skip).limit(limit)
    return list(db.scalars(query).all())


@router.post("/", response_model=RecipeRead, status_code=status.HTTP_201_CREATED)
def create_recipe(payload: RecipeCreate, db: Session = Depends(get_db)):
    exists = db.scalar(select(Recipe).where(Recipe.name == payload.name))
    if exists:
        raise HTTPException(status_code=409, detail="Recipe name already exists.")
    recipe = Recipe(**payload.model_dump(mode="json"))
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return recipe


@router.get("/{recipe_id}", response_model=RecipeRead)
def get_recipe(recipe_id: int, db: Session = Depends(get_db)):
    recipe = db.get(Recipe, recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found.")
    return recipe


@router.put("/{recipe_id}", response_model=RecipeRead)
def update_recipe(recipe_id: int, payload: RecipeUpdate, db: Session = Depends(get_db)):
    recipe = db.get(Recipe, recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found.")

    if payload.name and payload.name != recipe.name:
        exists = db.scalar(select(Recipe).where(Recipe.name == payload.name))
        if exists:
            raise HTTPException(status_code=409, detail="Recipe name already exists.")

    for field, value in payload.model_dump(exclude_unset=True, mode="json").items():
        setattr(recipe, field, value)
    db.commit()
    db.refresh(recipe)
    return recipe


@router.delete("/{recipe_id}")
def delete_recipe(recipe_id: int, db: Session = Depends(get_db)):
    recipe = db.get(Recipe, recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found.")
    db.delete(recipe)
    db.commit()
    return {"deleted": True, "id": recipe_id}
