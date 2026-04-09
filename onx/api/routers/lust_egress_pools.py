from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.schemas.lust_routing import LustEgressPoolCreate, LustEgressPoolRead, LustEgressPoolUpdate
from onx.services.lust_routing_service import lust_routing_service


router = APIRouter(prefix="/lust-egress-pools", tags=["lust-egress-pools"])


@router.get("", response_model=list[LustEgressPoolRead], status_code=status.HTTP_200_OK)
def list_lust_egress_pools(db: Session = Depends(get_database_session)):
    return [lust_routing_service.serialize_egress_pool(db, item) for item in lust_routing_service.list_egress_pools(db)]


@router.post("", response_model=LustEgressPoolRead, status_code=status.HTTP_201_CREATED)
def create_lust_egress_pool(payload: LustEgressPoolCreate, db: Session = Depends(get_database_session)):
    try:
        pool = lust_routing_service.create_egress_pool(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return lust_routing_service.serialize_egress_pool(db, pool)


@router.get("/{pool_id}", response_model=LustEgressPoolRead, status_code=status.HTTP_200_OK)
def get_lust_egress_pool(pool_id: str, db: Session = Depends(get_database_session)):
    pool = lust_routing_service.get_egress_pool(db, pool_id)
    if pool is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LuST egress pool not found.")
    return lust_routing_service.serialize_egress_pool(db, pool)


@router.patch("/{pool_id}", response_model=LustEgressPoolRead, status_code=status.HTTP_200_OK)
def update_lust_egress_pool(pool_id: str, payload: LustEgressPoolUpdate, db: Session = Depends(get_database_session)):
    pool = lust_routing_service.get_egress_pool(db, pool_id)
    if pool is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LuST egress pool not found.")
    try:
        pool = lust_routing_service.update_egress_pool(db, pool, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return lust_routing_service.serialize_egress_pool(db, pool)


@router.delete("/{pool_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lust_egress_pool(pool_id: str, db: Session = Depends(get_database_session)):
    pool = lust_routing_service.get_egress_pool(db, pool_id)
    if pool is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LuST egress pool not found.")
    lust_routing_service.delete_egress_pool(db, pool)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
