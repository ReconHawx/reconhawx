#!/usr/bin/env bash

# Check if WORKER_COMMAND is set
if [ -z "$WORKER_COMMAND" ]; then
    command_wrapper.py "$@"
else
    # If the command contains shell operators (|, >, <, etc.), execute with bash -c
    if [[ "$WORKER_COMMAND" =~ [\|\>\<\&] ]]; then
        command_wrapper.py "bash -c '$WORKER_COMMAND'"
    else
        command_wrapper.py "$WORKER_COMMAND"
    fi
fi 