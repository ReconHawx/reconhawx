#!/bin/bash
set -e

# Configure AWS CLI if credentials are provided
if [ -n "$AWS_ACCESS_KEY_ID" ] && [ -n "$AWS_SECRET_ACCESS_KEY" ]; then
    echo "Configuring AWS CLI credentials..."
    aws configure set aws_access_key_id "$AWS_ACCESS_KEY_ID"
    aws configure set aws_secret_access_key "$AWS_SECRET_ACCESS_KEY"

    if [ -n "$AWS_DEFAULT_REGION" ]; then
        aws configure set region "$AWS_DEFAULT_REGION"
        echo "AWS CLI configured with region: $AWS_DEFAULT_REGION"
    else
        echo "AWS CLI configured (no region specified)"
    fi
else
    echo "No AWS credentials provided, skipping AWS CLI configuration"
fi

# Execute the main application
exec python run-workflow.py "$@"
