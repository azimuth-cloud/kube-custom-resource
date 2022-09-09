import copy
import enum
import typing

from pydantic import (
    BaseModel as PydanticModel,
    Extra,
    ValidationError,
    ConstrainedInt,
    ConstrainedFloat,
)


def resolve_refs(schema, definitions):
    """
    Recursively resolve $refs in the given schema using the definitions.
    """
    if isinstance(schema, dict):
        if "allOf" in schema and len(schema["allOf"]) == 1:
            # Where the schema has an allOf with a single item, just put the
            # fields from the item onto the schema
            items = schema.pop("allOf")[0]
            resolve_refs(items, definitions)
            schema.update(items)
        elif "$ref" in schema:
            ref = schema.pop("$ref").removeprefix("#/definitions/")
            referenced = definitions[ref]
            resolve_refs(referenced, definitions)
            schema.update(definitions[ref])
        else:
            for value in schema.values():
                resolve_refs(value, definitions)
    elif isinstance(schema, list):
        for item in schema:
            resolve_refs(item, definitions)


def remove_fields(schema, *fields):
    """
    Recursively remove the specified fields from all the types in the schema.
    """
    if isinstance(schema, dict):
        if "type" in schema:
            for field in fields:
                schema.pop(field, None)
        for item in schema.values():
            remove_fields(item, *fields)
    elif isinstance(schema, list):
        for item in schema:
            remove_fields(item, *fields)


def snake_to_pascal(name):
    """
    Converts a snake case name to pascalCase.
    """
    first, *rest = name.split("_")
    return "".join([first] + [part.capitalize() for part in rest])


class Enum(enum.Enum):
    """
    Enum that does not include a title in the JSON-Schema.
    """
    def __str__(self):
        return str(self.value)

    @classmethod
    def __modify_schema__(cls, field_schema):
        field_schema.pop("title", None)


class Any:
    """
    Type for a value that can be any type.
    """
    @classmethod
    def __modify_schema__(cls, field_schema):
        field_schema["x-kubernetes-preserve-unknown-fields"] = True

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        return v


class Dict(typing.Dict):
    """
    Dict whose JSON-Schema includes the custom attribute to prevent Kubernetes
    pruning unknown properties.
    """
    @classmethod
    def __modify_schema__(cls, field_schema):
        field_schema["x-kubernetes-preserve-unknown-fields"] = True


class IntOrString(str):
    """
    Type for a value that can be specified as an integer or a string.

    The value will resolve to a string and the generated schema will include the
    Kubernetes custom schema attribute 'x-kubernetes-int-or-string'.
    """
    @classmethod
    def __modify_schema__(cls, field_schema):
        field_schema.pop("type", None)
        field_schema.update({
            "x-kubernetes-int-or-string": True,
            "anyOf": [
                { "type": "integer" },
                { "type": "string" },
            ],
        })

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not isinstance(v, (str, int)):
            raise TypeError("int or string required")
        return str(v)


class ConstrainedNumberMixin:
    @classmethod
    def __modify_schema__(cls, field_schema: typing.Dict[str, typing.Any]) -> None:
        super().__modify_schema__(field_schema)
        exclusive_min = field_schema.pop("exclusiveMinimum", None)
        if exclusive_min is not None:
            field_schema.update({
                "minimum": exclusive_min,
                "exclusiveMinimum": True,
            })
        exclusive_max = field_schema.pop("exclusiveMaximum", None)
        if exclusive_max is not None:
            field_schema.update({
                "maximum": exclusive_max,
                "exclusiveMaximum": True,
            })


def conint(
    *,
    strict: bool = False,
    gt: int = None,
    ge: int = None,
    lt: int = None,
    le: int = None,
    multiple_of: int = None
) -> typing.Type[int]:
    return type(
        "ConstrainedIntValue",
        (ConstrainedNumberMixin, ConstrainedInt),
        dict(
            strict = strict,
            gt = gt,
            ge = ge,
            lt = lt,
            le = le,
            multiple_of = multiple_of
        )
    )


def confloat(
    *,
    strict: bool = False,
    gt: float = None,
    ge: float = None,
    lt: float = None,
    le: float = None,
    multiple_of: float = None,
    allow_inf_nan: typing.Optional[bool] = None,
) -> typing.Type[float]:
    # use kwargs then define conf in a dict to aid with IDE type hinting
    return type(
        "ConstrainedFloatValue",
        (ConstrainedNumberMixin, ConstrainedFloat),
        dict(
            strict = strict,
            gt = gt,
            ge = ge,
            lt = lt,
            le = le,
            multiple_of = multiple_of,
            allow_inf_nan = allow_inf_nan
        )
    )


class StructuralUnion:
    """
    Type for a structural union, i.e. a union with a structural schema.

    See https://kubernetes.io/docs/tasks/extend-kubernetes/custom-resources/custom-resource-definitions/#specifying-a-structural-schema.
    """
    def __class_getitem__(cls, types):
        name = f"{cls.__name__}[{','.join(t.__name__ for t in types)}]"
        return type(name, (cls, ), {}, __types__ = types)

    def __init_subclass__(cls, /, __types__, **kwargs):
        # Structural unions are only supported for schema models
        if not all(issubclass(t, BaseModel) for t in __types__):
            raise TypeError("structural unions are only supported between schema models")
        super().__init_subclass__(**kwargs)
        cls.__types__ = __types__
    
    @classmethod
    def __modify_schema__(cls, field_schema):
        field_schema["type"] = "object"
        field_schema["properties"] = {}
        if cls.__doc__:
            field_schema["description"] = cls.__doc__
        field_schema["anyOf"] = []
        for type in cls.__types__:
            schema = type.schema()
            # In order to qualify as a structural schema, the schema of the union itself
            # must include all the possible properties
            field_schema["properties"].update(copy.deepcopy(schema["properties"]))
            # Schemas in anyOf are not permitted to contain particular keys
            remove_fields(
                schema,
                "description",
                "type",
                "default",
                "additionalProperties",
                "nullable",
                "x-kubernetes-preserve-unknown-fields",
            )
            field_schema["anyOf"].append(schema)

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        # Try to instantiate each of the types in the union
        # The first one to succeed is used
        for type in cls.__types__:
            if isinstance(v, type):
                return v
            elif isinstance(v, typing.Mapping):
                try:
                    return type(**v)
                except (ValueError, TypeError, ValidationError):
                    pass
        raise TypeError("failed to select a type from the union")


class BaseModel(PydanticModel):
    """
    Base model for use within CRD definitions.
    """
    class Config:
        # Allow pascalCase names as well as snake_case
        alias_generator = snake_to_pascal
        allow_population_by_field_name = True
        # Validate any mutations to the model
        allow_mutation = True
        validate_assignment = True

        @classmethod
        def schema_extra(cls, schema, model):
            """
            Post-process the generated schema to make it compatible with a Kubernetes CRD.
            """
            # Remove the titles
            schema.pop("title", None)
            for prop in schema.get("properties", {}).values():
                prop.pop("title", None)
            # When extra fields are allowed, stop Kubernetes pruning them
            if model.__config__.extra == Extra.allow:
                schema["x-kubernetes-preserve-unknown-fields"] = True

    def dict(self, **kwargs):
        # Unless otherwise specified, we want by_alias = True
        kwargs.setdefault("by_alias", True)
        return super().dict(**kwargs)

    def json(self, **kwargs):
        # Unless otherwise specified, we want by_alias = True
        kwargs.setdefault("by_alias", True)
        return super().json(**kwargs)

    @classmethod
    def schema(cls, *args, include_defaults = False, **kwargs):
        schema = super().schema(*args, **kwargs)
        # If the schema has definitions defined, resolve $refs and remove them
        if "definitions" in schema:
            resolve_refs(schema, schema.pop("definitions"))
        # Unless explicitly included, we remove defaults from the schema as they cause
        # Kubernetes to rewrite the schema
        # In most cases, it is better that defaults are applied at model instantiation time
        # as rewriting the Kubernetes objects themselves can have unintended side-effects
        # However in some cases it is more appropriate for the defaults to be "locked in" at
        # creation time
        if not include_defaults:
            remove_fields(schema, "default")
        return schema
