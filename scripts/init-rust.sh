#!/bin/bash

# Install Rust
curl https://sh.rustup.rs -sSf | sh

# Add WASM target
rustup target add wasm32-unknown-unknown

# Install wasm-pack (standard tool for Rust -> WASM + JS glue)
cargo install wasm-pack
