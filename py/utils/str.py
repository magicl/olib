# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~


def str_to_long_int(v: str) -> int:
    """Convert a 7 bit string to a long int"""
    ret = 0
    for c in v:
        ret <<= 7
        ret += ord(c)
    return ret


def long_int_to_str(v: int) -> str:
    """Convert a long int to a string"""
    ret = []
    while v > 0:
        ret.append(chr(v & 0x7F))
        v >>= 7
    return ''.join(reversed(ret))
