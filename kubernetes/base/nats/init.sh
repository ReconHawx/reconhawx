#!/bin/sh

# Wait for NATS to be ready
sleep 2

# Function to check if stream exists
stream_exists() {
    nats stream info "$1" --server=nats://localhost:4222 > /dev/null 2>&1
    return $?
}

# Create TASKS stream if it doesn't exist
# if ! stream_exists "TASKS"; then
#     nats stream add TASKS \
#         --subjects "tasks.pending" \
#         --retention limits \
#         --max-msgs 10000 \
#         --max-bytes 104857600 \
#         --storage memory \
#         --replicas 1 \
#         --discard old \
#         --server=nats://localhost:4222
#     echo "Created TASKS stream"
# fi

# Create OUTPUTS stream if it doesn't exist
if ! stream_exists "OUTPUTS"; then
    nats stream add OUTPUTS \
        --subjects "tasks.output.>" \
        --retention limits \
        --max-msgs 10000 \
        --max-bytes 104857600 \
        --storage memory \
        --replicas 1 \
        --discard old \
        --server=nats://localhost:4222
    echo "Created OUTPUTS stream"
fi

# Add any additional streams needed by checking the task_queue_client.py setup method
# These streams are derived from the TaskQueueClient.setup() method in task_queue_client.py 