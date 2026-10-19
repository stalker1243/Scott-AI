from fastapi import FastAPI, APIRouter, Depends
from route_inventory import api_routes
import pytest

pytestmark = pytest.mark.unit


def test_nested_prefixes_repeated_include_and_inherited_guards():
    def guard(): pass
    child = APIRouter()
    @child.get('/item')
    def endpoint(): return {}
    parent = APIRouter()
    parent.include_router(child, prefix='/nested', dependencies=[Depends(guard)])
    app = FastAPI()
    app.include_router(parent, prefix='/first')
    app.include_router(parent, prefix='/second')
    routes = list(api_routes(app))
    assert [route.path for route in routes] == ['/first/nested/item', '/second/nested/item']
    assert all(route.endpoint is endpoint for route in routes)
    assert all(guard in [item.call for item in route.dependant.dependencies] for route in routes)
