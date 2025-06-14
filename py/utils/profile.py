# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~


import time
from collections.abc import Generator
from contextlib import contextmanager


@contextmanager
def lineprofile(statistical: bool = False, enabledForTests: bool = False) -> Generator[None, None, None]:
    """
    Add to a function to perform line-by-line profiling of function, i.e.
     @lineprofile()
     def somefunction(...)
    """

    raise Exception('Use line-profile package instead')

    # try:
    #     import pprofile  # pylint: disable=import-error
    # except Exception as e:
    #     raise Exception('pprofile is not included by default due to GPL license. To make this code work, run "pip install pprofile", however this shall never be committed back into the repo') from e

    # start = time.time()
    # if statistical:
    #     prof = pprofile.StatisticalProfile()
    #     with prof(single=False):
    #         try:
    #             yield #Execute function
    #         except:
    #             logging.exception('Execution failed')
    # else:
    #     prof = pprofile.Profile()
    #     with prof():
    #         try:
    #             yield
    #         except:
    #             logging.exception('Execution failed')
    # end = time.time()

    # #Output data
    # filename = tempfile.mkstemp(prefix='olib_profile')[1]

    # #Dump data
    # prof.dump_stats(filename+'.dump')
    # print('profile output dumped to {}'.format(filename+'.dump'))

    # #Callgrind data
    # with open(filename+'.callgrind', 'w', encoding='utf-8') as f:
    #     prof.callgrind(f, relative_path=False)
    #     print('callgrind output dumped to {}'.format(filename+'.callgrind'))

    # print('profile ({}) total time: {} s'.format('statistical' if statistical else 'accurate', round(end-start, 2)))


@contextmanager
def functime(name: str = '') -> Generator[None, None, None]:
    """Determine how much time is spent in a function over the time of execution. Prints something every time the function is hit"""
    start = time.time()

    yield

    totTime = getattr(functime, f"{name}_totTime", 0)
    totCount = getattr(functime, f"{name}_totCount", 0)
    maxTime = getattr(functime, f"{name}_maxTime", 0)

    dTime = time.time() - start
    totTime += dTime
    maxTime = max(maxTime, dTime)
    totCount += 1

    setattr(functime, f"{name}_totTime", totTime)
    setattr(functime, f"{name}_totCount", totCount)
    setattr(functime, f"{name}_maxTime", maxTime)

    print(
        f"function {name} called {totCount:>8} times consuming {totTime:>8.2f} s, cur {dTime:>5.2f} s, avg {totTime / totCount:>5.2f} s, max {maxTime:>5.2f} s"
    )
