#!/bin/bash
set -e

# Configure AWS CLI if credentials are provided
if [ -n "$AWS_ACCESS_KEY_ID" ] && [ -n "$AWS_SECRET_ACCESS_KEY" ]; then
    echo "runner-bootstrap: Configuring AWS CLI credentials..." >&2
    aws configure set aws_access_key_id "$AWS_ACCESS_KEY_ID"
    aws configure set aws_secret_access_key "$AWS_SECRET_ACCESS_KEY"

    if [ -n "$AWS_DEFAULT_REGION" ]; then
        aws configure set region "$AWS_DEFAULT_REGION"
        echo "runner-bootstrap: AWS CLI configured with region: $AWS_DEFAULT_REGION" >&2
    else
        echo "runner-bootstrap: AWS CLI configured (no region specified)" >&2
    fi
else
    echo "runner-bootstrap: No AWS credentials provided, skipping AWS CLI configuration" >&2
fi

# Execute the main application
exec python run-workflow.py "$@"
