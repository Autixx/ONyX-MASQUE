from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.schemas.lust_routing import LustGatewayRouteMapCreate, LustGatewayRouteMapRead, LustGatewayRouteMapUpdate
from onx.services.lust_routing_service import lust_routing_service


router = APIRouter(prefix="/lust-route-maps", tags=["lust-route-maps"])


@router.get("", response_model=list[LustGatewayRouteMapRead], status_code=status.HTTP_200_OK)
def list_lust_route_maps(gateway_service_id: str | None = None, db: Session = Depends(get_database_session)):
    return [
        lust_routing_service.serialize_route_map(db, item)
        for item in lust_routing_service.list_route_maps(db, gateway_service_id=gateway_service_id)
    ]


@router.post("", response_model=LustGatewayRouteMapRead, status_code=status.HTTP_201_CREATED)
def create_lust_route_map(payload: LustGatewayRouteMapCreate, db: Session = Depends(get_database_session)):
    try:
        route_map = lust_routing_service.create_route_map(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return lust_routing_service.serialize_route_map(db, route_map)


@router.get("/{route_map_id}", response_model=LustGatewayRouteMapRead, status_code=status.HTTP_200_OK)
def get_lust_route_map(route_map_id: str, db: Session = Depends(get_database_session)):
    route_map = lust_routing_service.get_route_map(db, route_map_id)
    if route_map is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LuST route map not found.")
    return lust_routing_service.serialize_route_map(db, route_map)


@router.patch("/{route_map_id}", response_model=LustGatewayRouteMapRead, status_code=status.HTTP_200_OK)
def update_lust_route_map(route_map_id: str, payload: LustGatewayRouteMapUpdate, db: Session = Depends(get_database_session)):
    route_map = lust_routing_service.get_route_map(db, route_map_id)
    if route_map is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LuST route map not found.")
    try:
        route_map = lust_routing_service.update_route_map(db, route_map, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return lust_routing_service.serialize_route_map(db, route_map)


@router.delete("/{route_map_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lust_route_map(route_map_id: str, db: Session = Depends(get_database_session)):
    route_map = lust_routing_service.get_route_map(db, route_map_id)
    if route_map is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LuST route map not found.")
    lust_routing_service.delete_route_map(db, route_map)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
