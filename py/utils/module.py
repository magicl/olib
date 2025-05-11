# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import importlib.util
import sys
from types import ModuleType

def importModuleFromPath(path: str) -> ModuleType:
    # Extract module name from the path
    module_name = path.split('/')[-1].rstrip('.py')

    # Add the directory containing the file to sys.path
    file_directory = '/'.join(path.split('/')[:-1])
    sys.path.append(file_directory)

    # Load the module
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise Exception(f"Unable to load module {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module
