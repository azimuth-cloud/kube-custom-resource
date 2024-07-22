import logging
import types
import typing

from easykube import AsyncClient, ApiError, Resource, runtime

from .custom_resource import CustomResource
from .registry import CustomResourceRegistry


async def register_crds(
    client: AsyncClient,
    api_group: str,
    models_module: types.ModuleType,
    *,
    categories: typing.Optional[typing.List[str]] = None
):
    """
    Discovers the models in the specified module and registers them with Kubernetes.
    """
    registry = CustomResourceRegistry(api_group, categories)
    registry.discover_models(models_module)
    for crd in registry:
        await client.apply_object(crd.kubernetes_resource())


def create_controller_for_model(
    manager: runtime.Manager,
    api_group: str,
    model: typing.Type[CustomResource],
    reconcile_func: runtime.ReconcileFunc,
    *,
    namespace: typing.Optional[str] = None,
    worker_count: typing.Optional[int] = None,
    requeue_max_backoff: typing.Optional[int] = None
):
    """
    Creates a controller from the specified model.
    """
    full_api_group = (
        f"{model._meta.api_subgroup}.{api_group}"
        if model._meta.api_subgroup
        else api_group
    )
    return manager.create_controller(
        f"{full_api_group}/{model._meta.version}",
        model._meta.kind,
        reconcile_func,
        namespace = namespace,
        worker_count = worker_count,
        requeue_max_backoff = requeue_max_backoff
    )


class AnnotatedLogger(logging.LoggerAdapter):
    """
    Logger with annotations for a custom resource model.
    """
    def __init__(
        self,
        logger: logging.Logger,
        api_group: str,
        model_or_instance: typing.Union[typing.Type[CustomResource], CustomResource]
    ) -> logging.Logger:
        if isinstance(model_or_instance, CustomResource):
            model = type(model_or_instance)
            instance = model_or_instance
        else:
            model = model_or_instance
            instance = None
        full_api_group = (
            f"{model._meta.api_subgroup}.{api_group}"
            if model._meta.api_subgroup
            else api_group
        )
        extra = {
            "api_version": f"{full_api_group}/{model._meta.version}",
            "kind": model._meta.kind,
        }
        if instance:
            extra.update({
                "instance": (
                    f"{instance.metadata.namespace}/{instance.metadata.name}"
                    if instance.metadata.namespace
                    else instance.metadata.name
                )
            })
        super().__init__(logger, extra)

    def process(self, msg, kwargs):
        kwargs["extra"] = {**self.extra, **kwargs.get("extra", {})}
        return msg, kwargs


TMapper = typing.TypeVar("TMapper", bound = CustomResource)


class Mapper(typing.Generic[TMapper]):
    """
    Maps between model instances and the objects in Kubernetes.
    """
    def __init__(
        self,
        client: AsyncClient,
        api_group: str,
        model: typing.Type[TMapper]
    ):
        self._client = client
        self._api_group = (
            f"{model._meta.api_subgroup}.{api_group}"
            if model._meta.api_subgroup
            else api_group
        )
        self._model = model

    async def ekresource(self, subresource: typing.Optional[str] = None) -> Resource:
        """
        Returns an easykube resource for the model.
        """
        api = self._client.api(f"{self._api_group}/{self._model._meta.version}")
        resource = self._model._meta.plural_name
        if subresource:
            resource = f"{resource}/{subresource}"
        return await api.resource(resource)

    async def fetch(self, request: runtime.Request) -> typing.Optional[TMapper]:
        """
        Returns the model instance corresponding to the given request.
        """
        resource = await self.ekresource()
        try:
            data = await resource.fetch(request.name, namespace = request.namespace)
        except ApiError as exc:
            if exc.status_code == 404:
                return None
            else:
                raise
        return self._model.model_validate(data)

    async def ensure_finalizer(self, instance: TMapper, finalizer: str) -> TMapper:
        """
        Ensures that the specified finalizer is present on the given instance.
        The updated instance is returned.
        """
        if finalizer not in instance.metadata.finalizers:
            instance.metadata.finalizers.append(finalizer)
            return await self.save_instance(instance)
        else:
            return instance

    async def remove_finalizer(self, instance: TMapper, finalizer: str) -> TMapper:
        """
        Ensures that the specified finalizer is not present on the given instance.
        The updated instance is returned.
        """
        try:
            idx = instance.metadata.finalizers.index(finalizer)
        except ValueError:
            return instance
        else:
            instance.metadata.finalizers.pop(idx)
            return await self.save_instance(instance)

    async def save_instance(self, instance: TMapper) -> TMapper:
        """
        Saves the specified instance and returns the updated instance.
        """
        resource = await self.ekresource()
        data = await resource.replace(
            instance.metadata.name,
            instance.model_dump(exclude_defaults = True),
            namespace = instance.metadata.namespace
        )
        # Store the new resource version on the instance
        instance.metadata.resource_version = data["metadata"]["resourceVersion"]
        return instance

    async def save_instance_status(self, instance: TMapper) -> TMapper:
        """
        Saves the status of the given instance and returns the updated instance.
        """
        resource = await self.ekresource("status")
        data = await resource.replace(
            instance.metadata.name,
            {
                # Include the resource version for optimistic concurrency
                "metadata": { "resourceVersion": instance.metadata.resource_version },
                "status": instance.status.model_dump(exclude_defaults = True),
            },
            namespace = instance.metadata.namespace
        )
        # Store the new resource version on the instance
        instance.metadata.resource_version = data["metadata"]["resourceVersion"]
        return instance
