from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.schemas.lust_services import LustServiceCreate, LustServiceRead, LustServiceUpdate
from onx.services.lust_edge_deploy_service import lust_edge_deploy_service
from onx.services.lust_edge_node_service import lust_edge_node_service
from onx.services.realtime_service import realtime_service
from onx.services.lust_service_service import lust_service_manager


router = APIRouter(prefix="/lust-services", tags=["lust-services"])


@router.get("", response_model=list[LustServiceRead], status_code=status.HTTP_200_OK)
def list_lust_services(db: Session = Depends(get_database_session)):
    services = lust_service_manager.list_services(db)
    return [lust_service_manager.serialize_service(db, item) for item in services]


@router.post("", response_model=LustServiceRead, status_code=status.HTTP_201_CREATED)
def create_lust_service(payload: LustServiceCreate, db: Session = Depends(get_database_session)):
    try:
        service = lust_service_manager.create_service(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    realtime_service.publish("lust_service.created", {"id": service.id, "name": service.name, "node_id": service.node_id})
    return lust_service_manager.serialize_service(db, service)


@router.get("/{service_id}", response_model=LustServiceRead, status_code=status.HTTP_200_OK)
def get_lust_service(service_id: str, db: Session = Depends(get_database_session)):
    service = lust_service_manager.get_service(db, service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LuST service not found.")
    return lust_service_manager.serialize_service(db, service)


@router.get("/{service_id}/deployment", status_code=status.HTTP_200_OK)
def get_lust_service_deployment(service_id: str, db: Session = Depends(get_database_session)):
    service = lust_service_manager.get_service(db, service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LuST service not found.")
    payload = lust_edge_deploy_service.build_service_deployment(db, service)
    db.commit()
    service.desired_config_json = payload
    db.add(service)
    db.commit()
    return payload


@router.patch("/{service_id}", response_model=LustServiceRead, status_code=status.HTTP_200_OK)
def update_lust_service(service_id: str, payload: LustServiceUpdate, db: Session = Depends(get_database_session)):
    service = lust_service_manager.get_service(db, service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LuST service not found.")
    try:
        service = lust_service_manager.update_service(db, service, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    realtime_service.publish("lust_service.updated", {"id": service.id, "name": service.name, "node_id": service.node_id})
    return lust_service_manager.serialize_service(db, service)


@router.delete("/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lust_service(service_id: str, db: Session = Depends(get_database_session)):
    service = lust_service_manager.get_service(db, service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LuST service not found.")
    service_name = service.name
    service_node_id = service.node_id
    lust_service_manager.delete_service(db, service)
    realtime_service.publish("lust_service.deleted", {"id": service_id, "name": service_name, "node_id": service_node_id})


@router.post("/{service_id}/apply", response_model=LustServiceRead, status_code=status.HTTP_200_OK)
def apply_lust_service(service_id: str, db: Session = Depends(get_database_session)):
    service = lust_service_manager.get_service(db, service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LuST service not found.")
    try:
        service = lust_service_manager.apply_service(db, service)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    realtime_service.publish("lust_service.applied", {"id": service.id, "name": service.name, "node_id": service.node_id})
    return lust_service_manager.serialize_service(db, service)


@router.post("/{service_id}/deploy", status_code=status.HTTP_200_OK)
def deploy_lust_service(service_id: str, db: Session = Depends(get_database_session)):
    service = lust_service_manager.get_service(db, service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LuST service not found.")
    try:
        payload = lust_edge_node_service.deploy_service(db, service)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    realtime_service.publish("lust_service.deployed", {"id": service.id, "name": service.name, "node_id": service.node_id})
    return payload
