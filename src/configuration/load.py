import logging
import os
import tomllib
from typing import List, Dict

from src.components import ComponentClass
from src.configuration.model import ComponentsConfiguration, ComponentConfiguration

logger = logging.getLogger("Load")

def class_from_path(path: str) -> ComponentClass:
    """
    Import a class from a path.
    :param path: The path to the class
    :return: The python class corresponding to the path
    """

    module_name, class_name = path.rsplit(".", 1)
    module_name = "components." + module_name

    module = __import__(module_name, fromlist=[class_name])
    return getattr(module, class_name)


def load_all_components(config_path: str = "configuration") -> ComponentsConfiguration:
    """
    Load components configuration from the configuration folder.
    Reads every .toml file in the configuration folder and returns a dictionary with the configuration.
    :param config_path: The path to the configuration folder

    """

    collectors = {}
    harvesters = {}
    handlers = {}

    source_hydration = {}
    dependencies_hydration = {}

    for folder, _, files in os.walk(config_path):
        for file in files:
            if file.endswith(".toml"):
                with open(os.path.join(folder, file), "rb") as f:
                    config = tomllib.load(f)

                    file_name = file.split(".")[0]

                    extract_components(
                        collectors,
                        config,
                        file_name,
                        "collectors",
                        source_hydration,
                        dependencies_hydration,
                    )
                    extract_components(
                        harvesters,
                        config,
                        file_name,
                        "harvesters",
                        source_hydration,
                        dependencies_hydration,
                    )
                    extract_components(
                        handlers,
                        config,
                        file_name,
                        "handlers",
                        source_hydration,
                        dependencies_hydration,
                    )

    for component_configuration, source in source_hydration.items():
        component_configuration.source = collectors.get(
            source, harvesters.get(source, handlers.get(source, None))
        )

    for component_configuration, dependencies in dependencies_hydration.items():
        for dependency in dependencies:
            component_configuration.dependencies.append(
                collectors.get(
                    dependency,
                    harvesters.get(dependency, handlers.get(dependency, None)),
                )
            )

    return ComponentsConfiguration(
        collectors=collectors,
        harvesters=harvesters,
        handlers=handlers,
    )


def extract_components(
    target_list: dict,
    config: dict,
    file_name: str,
    key: str,
    source_hydration: dict,
    dependencies_hydration: dict,
):
    for component_name, component in config.get(key, {}).items():
        name = f"{file_name}_{component_name}"
        component_configuration = ComponentConfiguration(
            name=name,
            data_type=component["DATA_TYPE"],
            data_format=component["DATA_FORMAT"],
            component=class_from_path(component["PATH"]),
            schedule=component.get("SCHEDULE", None),
            source_range=component.get("SOURCE_RANGE", None),
            source=None,
            dependencies=[],
            dependencies_limit=component.get(
                "DEPENDENCIES_LIMIT",
                [1 for _ in range(len(component.get("DEPENDENCIES", [])))],
            ),
            source_range_strict=component.get("SOURCE_RANGE_STRICT", True),
            multiple_results=component.get("MULTIPLE_RESULTS", False),
            query_parameters=component.get("QUERY_PARAMETERS", None),
            storage_date = component.get("STORAGE_DATE", False),
        )

        target_list[name] = component_configuration

        source = component.get("SOURCE", None)
        if source is not None:
            source = _treat_name(file_name, source)
            source_hydration[component_configuration] = source

        dependencies = component.get("DEPENDENCIES", None)
        if dependencies is not None:
            dependencies_hydration[component_configuration] = list(
                map(lambda x: _treat_name(file_name, x), dependencies)
            )


def get_optimal_dependencies_wise_order(
    harvesters: Dict[str, ComponentConfiguration]
) -> List[ComponentConfiguration]:
    """
    Get the optimal order to run the harvesters in.
    :param harvesters:  The harvesters to order
    :return:  The optimal order to run the harvesters in
    """

    harvesters = list(harvesters.values())

    order = []

    MAX_ITERATIONS = 1000
    iterations = 0

    while harvesters:
        for harvester in harvesters:
            for dependency in harvester.dependencies:
                if dependency.source is None:
                    continue
            if all(dependency in order for dependency in harvester.dependencies if dependency.source is not None):
                order.append(harvester)
                harvesters.remove(harvester)
                break

        iterations += 1

        if iterations > MAX_ITERATIONS:
            # Add the remaining harvesters in any order
            order.extend(harvesters)
            logger.warning(
                f"Could not find optimal order for harvesters: {' '.join([harvester.name for harvester in harvesters])}"
            )
            break

    return order


def _treat_name(file_name, source):
    if "." not in source:
        source = f"{file_name}.{source}"
    source = source.replace(".", "_")
    return source
