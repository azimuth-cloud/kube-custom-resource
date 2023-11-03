import copy
import enum
import typing

import annotated_types

from pydantic_core import CoreSchema, core_schema

from pydantic import (
    BaseModel as PydanticModel,
    StringConstraints,
    AllowInfNan,
    Strict,
    GetCoreSchemaHandler,
    GetJsonSchemaHandler
)
from pydantic.json_schema import JsonSchemaValue


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
            ref = schema.pop("$ref").removeprefix("#/$defs/")
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
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        json_schema.pop("title", None)
        return json_schema


class Any:
    """
    Type for a value that can be any type.
    """
    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source_type: typing.Any,
        handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        instance_schema = core_schema.is_instance_schema(cls)
        any_schema = handler.generate_schema(typing.Any)
        non_instance_schema = core_schema.no_info_after_validator_function(cls, any_schema)
        return core_schema.union_schema([instance_schema, non_instance_schema])

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        json_schema["x-kubernetes-preserve-unknown-fields"] = True
        return json_schema


KeyType = typing.TypeVar("KeyType")
ValueType = typing.TypeVar("ValueType")
class Dict(typing.Dict[KeyType, ValueType]):
    """
    Dict whose JSON-Schema includes the custom attribute to prevent Kubernetes
    pruning unknown properties.
    """
    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source_type: typing.Any,
        handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        instance_schema = core_schema.is_instance_schema(cls)
        args = typing.get_args(source_type)
        if args:
            dict_schema = handler.generate_schema(typing.Dict[args[0], args[1]])
        else:
            dict_schema = handler.generate_schema(typing.Dict)
        non_instance_schema = core_schema.no_info_after_validator_function(cls, dict_schema)
        return core_schema.union_schema([instance_schema, non_instance_schema])

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        json_schema["x-kubernetes-preserve-unknown-fields"] = True
        return json_schema


class IntOrString(str):
    """
    Type for a value that can be specified as an integer or a string.

    The value will resolve to a string and the generated schema will include the
    Kubernetes custom schema attribute 'x-kubernetes-int-or-string'.
    """
    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source_type: typing.Any,
        handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        return core_schema.union_schema(
            [
                core_schema.int_schema(),
                core_schema.str_schema(),
            ]
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        json_schema["x-kubernetes-int-or-string"] = True
        return json_schema


def constr(**kwargs):
    return typing.Annotated[str, StringConstraints(**kwargs)]


class _ConvertExclusiveMinMax:
    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        exclusive_min = json_schema.pop("exclusiveMinimum", None)
        if exclusive_min is not None:
            json_schema.update({
                "minimum": exclusive_min,
                "exclusiveMinimum": True,
            })
        exclusive_max = json_schema.pop("exclusiveMaximum", None)
        if exclusive_max is not None:
            json_schema.update({
                "maximum": exclusive_max,
                "exclusiveMaximum": True,
            })
        return json_schema


def conint(
    *,
    strict: typing.Optional[bool] = None,
    gt: typing.Optional[int] = None,
    ge: typing.Optional[int] = None,
    lt: typing.Optional[int] = None,
    le: typing.Optional[int] = None,
    multiple_of: typing.Optional[int] = None
) -> typing.Type[int]:
    return typing.Annotated[
        int,
        Strict(strict) if strict is not None else None,
        annotated_types.Interval(gt = gt, ge = ge, lt = lt, le = le),
        annotated_types.MultipleOf(multiple_of) if multiple_of is not None else None,
        _ConvertExclusiveMinMax,
    ]


def confloat(
    *,
    strict: typing.Optional[bool] = None,
    gt: typing.Optional[float] = None,
    ge: typing.Optional[float] = None,
    lt: typing.Optional[float] = None,
    le: typing.Optional[float] = None,
    multiple_of: typing.Optional[float] = None,
    allow_inf_nan: typing.Optional[bool] = None,
) -> typing.Type[float]:
    return typing.Annotated[
        float,
        Strict(strict) if strict is not None else None,
        annotated_types.Interval(gt = gt, ge = ge, lt = lt, le = le),
        annotated_types.MultipleOf(multiple_of) if multiple_of is not None else None,
        AllowInfNan(allow_inf_nan) if allow_inf_nan is not None else None,
        _ConvertExclusiveMinMax,
    ]


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
    def __get_pydantic_core_schema__(
        cls,
        source_type: typing.Any,
        handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        return core_schema.union_schema(
            [
                handler.generate_schema(t)
                for t in source_type.__types__
            ]
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        any_of = []
        properties = {}
        for union_type in cls.__types__:
            union_type_schema = copy.deepcopy(union_type.model_json_schema())
            # In order to qualify as a structural schema, the schema of the union itself
            # must include all the possible properties
            properties.update(copy.deepcopy(union_type_schema["properties"]))
            # Schemas in anyOf are not permitted to contain particular keys
            remove_fields(
                union_type_schema,
                "description",
                "type",
                "default",
                "additionalProperties",
                "nullable",
                "x-kubernetes-preserve-unknown-fields",
            )
            any_of.append(union_type_schema)
        json_schema = {
            "type": "object",
            "properties": properties,
            "anyOf": any_of,
        }
        if cls.__doc__:
            json_schema["description"] = cls.__doc__
        return json_schema


class BaseModel(
    PydanticModel,
    alias_generator = snake_to_pascal,
    populate_by_name = True,
    # Validate any mutations to the model
    frozen = False,
    validate_assignment = True
):
    """
    Base model for use within CRD definitions.
    """
    def model_dump(self, **kwargs):
        # Unless otherwise specified, we want by_alias = True
        kwargs.setdefault("by_alias", True)
        return super().model_dump(**kwargs)

    def model_dump_json(self, **kwargs):
        # Unless otherwise specified, we want by_alias = True
        kwargs.setdefault("by_alias", True)
        return super().model_dump_json(**kwargs)

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        json_schema = super().__get_pydantic_json_schema__(core_schema, handler)
        # Post-process the generated schema to make it compatible with a Kubernetes CRD
        # Remove the titles
        json_schema.pop("title", None)
        for prop in json_schema.get("properties", {}).values():
            prop.pop("title", None)
        # When extra fields are allowed, stop Kubernetes pruning them
        if cls.model_config.get("extra") == "allow":
            json_schema["x-kubernetes-preserve-unknown-fields"] = True
        return json_schema

    @classmethod
    def model_json_schema(cls, *args, include_defaults = False, **kwargs):
        schema = super().model_json_schema(*args, **kwargs)
        # If the schema has definitions defined, resolve $refs and remove them
        if "$defs" in schema:
            resolve_refs(schema, schema.pop("$defs"))
        # Unless explicitly included, we remove defaults from the schema as they cause
        # Kubernetes to rewrite the schema
        # In most cases, it is better that defaults are applied at model instantiation time
        # as rewriting the Kubernetes objects themselves can have unintended side-effects
        # However in some cases it is more appropriate for the defaults to be "locked in" at
        # creation time
        if not include_defaults:
            remove_fields(schema, "default")
        return schema
