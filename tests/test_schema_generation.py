# ruff: noqa: E501
import models

import kube_custom_resource as kcr

API_GROUP = "test.kcr.azimuth-cloud.io"


registry = kcr.CustomResourceRegistry(API_GROUP)
registry.discover_models(models)


def test_model_discovery_found_two_models():
    assert len(registry) == 2


MANUFACTURER_CRD_EXPECTED = {
    "apiVersion": "apiextensions.k8s.io/v1",
    "kind": "CustomResourceDefinition",
    "metadata": {"name": "manufacturers.test.kcr.azimuth-cloud.io"},
    "spec": {
        "group": "test.kcr.azimuth-cloud.io",
        "scope": "Cluster",
        "names": {
            "kind": "Manufacturer",
            "singular": "manufacturer",
            "plural": "manufacturers",
            "shortNames": [],
            "categories": [],
        },
        "versions": [
            {
                "name": "v1alpha1",
                "served": True,
                "storage": True,
                "schema": {
                    "openAPIV3Schema": {
                        "description": "Represents a car manufacturer.",
                        "properties": {
                            "spec": {
                                "description": "Spec for a car manufacturer.",
                                "properties": {
                                    "founded": {
                                        "description": "The year the company was founded.",
                                        "x-kubernetes-int-or-string": True,
                                    },
                                    "website": {
                                        "description": "The company website.",
                                        "format": "uri",
                                        "minLength": 1,
                                        "type": "string",
                                    },
                                    "models": {
                                        "description": "The models supported by this manufacturer.",
                                        "items": {
                                            "pattern": "^[a-z0-9]+$",
                                            "type": "string",
                                        },
                                        "minItems": 1,
                                        "type": "array",
                                    },
                                },
                                "required": ["founded", "website", "models"],
                                "type": "object",
                            }
                        },
                        "required": ["spec"],
                        "type": "object",
                    }
                },
                "subresources": {"status": {}},
                "additionalPrinterColumns": [
                    {"name": "Founded", "type": "string", "jsonPath": ".spec.founded"},
                    {
                        "name": "Age",
                        "type": "date",
                        "jsonPath": ".metadata.creationTimestamp",
                    },
                ],
            }
        ],
    },
}


def test_manufacturer_crd():
    """
    Verifies that the manufacturer CRD resource is as expected.
    """
    crd = registry.get_crd(API_GROUP, "Manufacturer")
    assert crd.kubernetes_resource() == MANUFACTURER_CRD_EXPECTED


CAR_CRD_EXPECTED = {
    "apiVersion": "apiextensions.k8s.io/v1",
    "kind": "CustomResourceDefinition",
    "metadata": {"name": "cars.test.kcr.azimuth-cloud.io"},
    "spec": {
        "group": "test.kcr.azimuth-cloud.io",
        "scope": "Namespaced",
        "names": {
            "kind": "Car",
            "singular": "car",
            "plural": "cars",
            "shortNames": [],
            "categories": [],
        },
        "versions": [
            {
                "name": "v1alpha1",
                "served": True,
                "storage": True,
                "schema": {
                    "openAPIV3Schema": {
                        "description": "Represents a car.",
                        "properties": {
                            "spec": {
                                "description": "Spec for a car.",
                                "properties": {
                                    "manufacturer": {
                                        "description": "The manufacturer of the car.",
                                        "pattern": "^[a-zA-Z0-9-]+$",
                                        "type": "string",
                                    },
                                    "model": {
                                        "description": "The model of the car.",
                                        "pattern": "^[a-zA-Z0-9-]+$",
                                        "type": "string",
                                    },
                                    "engine": {
                                        "anyOf": [
                                            {
                                                "properties": {
                                                    "petrol": {
                                                        "properties": {
                                                            "capacity": {
                                                                "exclusiveMinimum": True,
                                                                "minimum": 0,
                                                            }
                                                        },
                                                        "required": ["capacity"],
                                                    }
                                                },
                                                "required": ["petrol"],
                                            },
                                            {
                                                "properties": {
                                                    "diesel": {
                                                        "properties": {
                                                            "capacity": {
                                                                "exclusiveMinimum": True,
                                                                "minimum": 0,
                                                            }
                                                        },
                                                        "required": ["capacity"],
                                                    }
                                                },
                                                "required": ["diesel"],
                                            },
                                            {
                                                "properties": {
                                                    "electric": {
                                                        "properties": {
                                                            "maxPowerOutput": {
                                                                "exclusiveMinimum": True,
                                                                "minimum": 0,
                                                            }
                                                        },
                                                        "required": ["maxPowerOutput"],
                                                    }
                                                },
                                                "required": ["electric"],
                                            },
                                        ],
                                        "description": "The engine for the car.",
                                        "properties": {
                                            "petrol": {
                                                "description": "Spec for a combustion engine.",
                                                "properties": {
                                                    "capacity": {
                                                        "description": "The capacity of the engine in litres.",
                                                        "exclusiveMinimum": True,
                                                        "minimum": 0,
                                                        "type": "integer",
                                                    }
                                                },
                                                "required": ["capacity"],
                                                "type": "object",
                                            },
                                            "diesel": {
                                                "description": "Spec for a combustion engine.",
                                                "properties": {
                                                    "capacity": {
                                                        "description": "The capacity of the engine in litres.",
                                                        "exclusiveMinimum": True,
                                                        "minimum": 0,
                                                        "type": "integer",
                                                    }
                                                },
                                                "required": ["capacity"],
                                                "type": "object",
                                            },
                                            "electric": {
                                                "description": "Spec for an electric engine.",
                                                "properties": {
                                                    "maxPowerOutput": {
                                                        "description": "The maximum power output of the engine in kW.",
                                                        "exclusiveMinimum": True,
                                                        "minimum": 0,
                                                        "type": "integer",
                                                    }
                                                },
                                                "required": ["maxPowerOutput"],
                                                "type": "object",
                                            },
                                        },
                                        "type": "object",
                                    },
                                    "colour": {
                                        "description": "Enum of possible colours for a car.",
                                        "enum": ["White", "Silver", "Red", "Black"],
                                        "type": "string",
                                    },
                                    "owner": {
                                        "description": "The owner of the car.",
                                        "minLength": 1,
                                        "nullable": True,
                                        "pattern": "^[a-zA-Z0-9 ]*$",
                                        "type": "string",
                                    },
                                    "extras": {
                                        "additionalProperties": {
                                            "x-kubernetes-preserve-unknown-fields": True
                                        },
                                        "description": "Any extras for the car.",
                                        "type": "object",
                                        "x-kubernetes-preserve-unknown-fields": True,
                                    },
                                },
                                "required": [
                                    "manufacturer",
                                    "model",
                                    "engine",
                                    "colour",
                                ],
                                "type": "object",
                            },
                            "status": {
                                "description": "Status for a car.",
                                "properties": {
                                    "phase": {
                                        "description": "Enum of possible phases for the car.",
                                        "enum": [
                                            "Unknown",
                                            "OnOrder",
                                            "Building",
                                            "Ready",
                                            "Delayed",
                                        ],
                                        "type": "string",
                                    }
                                },
                                "type": "object",
                                "x-kubernetes-preserve-unknown-fields": True,
                            },
                        },
                        "required": ["spec"],
                        "type": "object",
                    }
                },
                "subresources": {"status": {}},
                "additionalPrinterColumns": [
                    {
                        "name": "Manufacturer",
                        "type": "string",
                        "jsonPath": ".spec.manufacturer",
                    },
                    {"name": "Model", "type": "string", "jsonPath": ".spec.model"},
                    {"name": "Phase", "type": "string", "jsonPath": ".status.phase"},
                    {
                        "name": "Age",
                        "type": "date",
                        "jsonPath": ".metadata.creationTimestamp",
                    },
                ],
            }
        ],
    },
}


def test_car_crd():
    """
    Verifies that the car CRD resource is as expected.
    """
    crd = registry.get_crd(API_GROUP, "Car")
    assert crd.kubernetes_resource() == CAR_CRD_EXPECTED
