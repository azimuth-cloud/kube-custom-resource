import copy

import models
import pydantic as p
import pytest
from models import v1alpha1 as api

import kube_custom_resource as kcr

API_GROUP = "test.kcr.azimuth-cloud.io"


registry = kcr.CustomResourceRegistry(API_GROUP)
registry.discover_models(models)


VALID_MANUFACTURER = {
    "apiVersion": f"{API_GROUP}/v1alpha1",
    "kind": "Manufacturer",
    "metadata": {
        "name": "ford",
    },
    "spec": {
        "founded": 1903,
        "website": "https://www.ford.co.uk",
        "models": [
            "escort",
            "sierra",
            "mondeo",
            "fiesta",
            "focus",
        ],
    },
}


def test_validate_valid_manufacturer():
    """
    Tests that a valid manufacturer resource can be loaded.
    """
    manufacturer: api.Manufacturer = registry.get_model_instance(VALID_MANUFACTURER)
    assert manufacturer.api_version == f"{API_GROUP}/v1alpha1"
    assert manufacturer.kind == "Manufacturer"
    assert manufacturer.metadata.name == "ford"
    assert manufacturer.spec.founded == "1903"
    assert manufacturer.spec.website == "https://www.ford.co.uk/"
    assert len(manufacturer.spec.models) == 5


VALID_CAR = {
    "apiVersion": f"{API_GROUP}/v1alpha1",
    "kind": "Car",
    "metadata": {
        "name": "john-doe-escort",
    },
    "spec": {
        "manufacturer": "ford",
        "model": "escort",
        "engine": {
            "petrol": {
                "capacity": 2,
            },
        },
        "colour": "Black",
        "extras": {
            "mats": True,
        },
    },
    "status": {
        "phase": "OnOrder",
    },
}


def test_validate_valid_car():
    """
    Tests that a valid car resource can be loaded.
    """
    car: api.Car = registry.get_model_instance(VALID_CAR)
    assert car.api_version == f"{API_GROUP}/v1alpha1"
    assert car.kind == "Car"
    assert car.metadata.name == "john-doe-escort"
    assert car.spec.manufacturer == "ford"
    assert car.spec.model == "escort"
    assert type(car.spec.engine) == api.PetrolEngine  # noqa: E721
    assert car.spec.engine.petrol.capacity == 2
    assert car.spec.colour == api.Colour.BLACK
    assert car.spec.owner is None
    assert car.spec.extras == {"mats": True}
    assert car.status.phase == api.Phase.ON_ORDER


def test_validate_invalid_car_raises_validationerror():
    """
    Tests that attempting to load an invalid resource results in a validation error.
    """
    with pytest.raises(p.ValidationError):
        invalid_car = copy.deepcopy(VALID_CAR)
        invalid_car["spec"]["colour"] = "Green"
        _ = registry.get_model_instance(invalid_car)
