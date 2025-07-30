#!/usr/bin/env bash

printf "\e[36mpostCreateCommand\e[0m\n"
uname -a

pushd airflow
uv sync --dev
popd
