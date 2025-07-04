import typing as t

import pydantic as p

from kube_custom_resource import custom_resource as crd
from kube_custom_resource import schema as s


class CombustionEngineSpec(s.BaseModel):
    """Spec for a combustion engine."""

    capacity: s.conint(gt=0) = p.Field(
        ..., description="The capacity of the engine in litres."
    )


class ElectricEngineSpec(s.BaseModel):
    """Spec for an electric engine."""

    max_power_output: s.conint(gt=0) = p.Field(
        ..., description="The maximum power output of the engine in kW."
    )


class PetrolEngine(s.BaseModel):
    """Union member for a petrol engine."""

    petrol: CombustionEngineSpec


class DieselEngine(s.BaseModel):
    """Union member for a diesel engine."""

    diesel: CombustionEngineSpec


class ElectricEngine(s.BaseModel):
    """Union member for an electric engine."""

    electric: ElectricEngineSpec


Engine = t.Annotated[
    t.Union[PetrolEngine, DieselEngine, ElectricEngine], s.StructuralUnion
]


class Colour(str, s.Enum):
    """Enum of possible colours for a car."""

    WHITE = "White"
    SILVER = "Silver"
    RED = "Red"
    BLACK = "Black"


class CarSpec(s.BaseModel):
    """Spec for a car."""

    manufacturer: s.constr(pattern=r"^[a-zA-Z0-9-]+$") = p.Field(
        ..., description="The manufacturer of the car."
    )
    model: s.constr(pattern=r"^[a-zA-Z0-9-]+$") = p.Field(
        ..., description="The model of the car."
    )
    engine: Engine = p.Field(..., description="The engine for the car.")
    colour: Colour = p.Field(..., description="The colour of the car.")
    owner: s.Optional[
        s.constr(pattern=r"^[a-zA-Z0-9 ]*$", strip_whitespace=True, min_length=1)
    ] = p.Field(None, description="The owner of the car.")
    extras: s.Dict[str, s.Any] = p.Field(
        default_factory=dict, description="Any extras for the car."
    )


class Phase(str, s.Enum):
    """Enum of possible phases for the car."""

    UNKNOWN = "Unknown"
    ON_ORDER = "OnOrder"
    BUILDING = "Building"
    READY = "Ready"
    DELAYED = "Delayed"


class CarStatus(s.BaseModel, extra="allow"):
    """Status for a car."""

    phase: Phase = p.Field(Phase.UNKNOWN, description="The phase of the car.")


class Car(
    crd.CustomResource,
    scope=crd.Scope.NAMESPACED,
    subresources={"status": {}},
    printer_columns=[
        {
            "name": "Manufacturer",
            "type": "string",
            "jsonPath": ".spec.manufacturer",
        },
        {
            "name": "Model",
            "type": "string",
            "jsonPath": ".spec.model",
        },
        {
            "name": "Phase",
            "type": "string",
            "jsonPath": ".status.phase",
        },
    ],
):
    """Represents a car."""

    spec: CarSpec
    status: CarStatus = p.Field(default_factory=CarStatus)
