# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

import resource
import sys


# Returns maximum memory usage of process
# From http://fa.bianp.net/blog/2013/different-ways-to-get-memory-consumption-or-lessons-learned-from-memory_profiler/
def procMaxMemUsage():
    rusage_denom = 1024.0
    if sys.platform == 'darwin':
        # ... it seems that in OSX the output is different units ...
        rusage_denom = rusage_denom * rusage_denom
    usage = resource.getrusage(resource.RUSAGE_SELF)
    mem = usage.ru_maxrss / rusage_denom
    return mem
