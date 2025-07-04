import typing as t

import annotated_types as a
import pydantic as p

from kube_custom_resource import custom_resource as crd
from kube_custom_resource import schema as s

ModelsList = t.Annotated[t.List[s.constr(pattern=r"^[a-z0-9]+$")], a.Len(min_length=1)]


class ManufacturerSpec(s.BaseModel):
    """Spec for a car manufacturer."""

    founded: s.IntOrString = p.Field(
        ..., description="The year the company was founded."
    )
    website: s.AnyHttpUrl = p.Field(..., description="The company website.")
    models: ModelsList = p.Field(
        ..., description="The models supported by this manufacturer."
    )


class Manufacturer(
    crd.CustomResource,
    scope=crd.Scope.CLUSTER,
    subresources={"status": {}},
    printer_columns=[
        {
            "name": "Founded",
            "type": "string",
            "jsonPath": ".spec.founded",
        },
    ],
):
    """Represents a car manufacturer."""

    spec: ManufacturerSpec
