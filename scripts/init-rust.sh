#!/bin/bash
# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~

# Install Rust
curl https://sh.rustup.rs -sSf | sh

. $HOME/.cargo/env

# Add WASM target
rustup target add wasm32-unknown-unknown

# Install wasm-pack (standard tool for Rust -> WASM + JS glue)
cargo install wasm-pack
