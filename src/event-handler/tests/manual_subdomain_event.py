#!/usr/bin/env python3
"""
Test script to manually trigger a subdomain creation event
"""

import asyncio
import json
import os
import sys
import time

from nats.aio.client import Client as NATS


EVENTS_STREAM = os.getenv("EVENTS_STREAM", "EVENTS")
SUBJECT = "events.assets.subdomain.created"  # Match API published format
NATS_URL = os.getenv("NATS_URL", os.getenv("NATS_URL_DEV", "nats://nats:4222"))


async def main():
    nc = NATS()
    await nc.connect(NATS_URL)
    js = nc.jetstream()

    # Create subdomain creation event payload (matching API format)
    payload = {
        "event": "asset.batch_created",
        "asset_type": "subdomain",
        "program_name": os.getenv("PROGRAM_NAME", "h3xit"),
        "count": 1,
        "processing_mode": "small_batch",
        "assets": [{
            "record_id": "test_123",
            "name": "test.h3xit.com",
            "program_name": os.getenv("PROGRAM_NAME", "h3xit")
        }],
        "batch_id": "test_subdomain_batch_123"
    }

    print(f"Publishing subdomain creation event...")
    print(f"Subject: {SUBJECT}")
    print(f"Payload: {json.dumps(payload, indent=2)}")

    data = json.dumps(payload).encode()
    ack = await js.publish(SUBJECT, data)
    print(f"✅ Published to {SUBJECT} seq={ack.seq}")

    await nc.drain()


async def test_receive_event():
    """Test receiving events from NATS"""
    nc = NATS()
    await nc.connect(NATS_URL)
    js = nc.jetstream()

    # Subscribe to events
    sub = await js.pull_subscribe("events.>", "test_consumer")
    print("Subscribed to events.> - waiting for messages...")

    try:
        # Fetch messages with timeout
        msgs = await sub.fetch(10, timeout=5.0)
        print(f"Received {len(msgs)} messages")

        for msg in msgs:
            print(f"Subject: {msg.subject}")
            try:
                payload = json.loads(msg.data.decode())
                print(f"Payload: {json.dumps(payload, indent=2)}")
                await msg.ack()
            except json.JSONDecodeError as e:
                print(f"Failed to decode payload: {e}")

    except asyncio.TimeoutError:
        print("No messages received within timeout")

    await nc.drain()


async def test_notifier_processing():
    """Test the full notifier processing of subdomain events"""
    import logging
    import os
    logging.basicConfig(level=logging.DEBUG)

    # Handler definitions are loaded from the API (INTERNAL_SERVICE_API_KEY + API_URL).

    # Import notifier components
    sys.path.append('.')
    from app.main import SimpleNotifierApp
    from app.config import NotifierConfig

    # Create a test notifier with minimal config
    cfg = NotifierConfig()
    cfg.nats_url = NATS_URL
    cfg.nats_stream = EVENTS_STREAM
    cfg.nats_subject_pattern = "events.>"
    cfg.enable_event_handlers = True
    cfg.enable_batch_processing = True
    cfg.log_level = "DEBUG"

    app = SimpleNotifierApp()
    app.cfg = cfg

    print("Starting test notifier...")

    # Start a task to publish a test event after a short delay
    async def publish_test_event():
        await asyncio.sleep(2)  # Wait for notifier to start
        nc = NATS()
        await nc.connect(NATS_URL)
        js = nc.jetstream()

        # Use the exact payload structure from the NATS stream
        payload = {
            "event": "asset.batch_created",
            "asset_type": "subdomain",
            "program_name": "h3xit",
            "count": 1,
            "processing_mode": "small_batch",
            "assets": [{
                "record_id": "f99a11e5-f748-4375-937d-1cc06e5d5a87",
                "name": "h3x.it",
                "program_name": "h3xit"
            }],
            "batch_id": "subdomain_created_batch_1756493019"
        }

        data = json.dumps(payload).encode()
        ack = await js.publish(SUBJECT, data)
        print(f"Published test event to {SUBJECT}, seq={ack.seq}")
        await nc.drain()

    # Start the publisher task
    publish_task = asyncio.create_task(publish_test_event())

    try:
        # Start the notifier (this will run for about 10 seconds)
        await asyncio.wait_for(app.start(), timeout=10.0)
    except asyncio.TimeoutError:
        print("Test completed (timeout reached)")
    except KeyboardInterrupt:
        print("Test interrupted")

    publish_task.cancel()
    try:
        await publish_task
    except asyncio.CancelledError:
        pass


async def test_discord_template_substitution():
    """Test Discord notification template substitution"""
    import sys
    import os
    sys.path.append('.')

    from app.event_handlers import DiscordNotificationAction

    # Test config with template
    config = {
        "webhook_url": "{program_settings.discord_webhook_url}",
        "title_template": "Test: {program_name}",
        "description_template": "Event: {event}",
        "color": 3447003
    }

    # Test event data with program settings
    event_data = {
        "program_name": "h3xit",
        "event": "test_event",
        "program_settings": {
            "discord_webhook_url": "https://discord.com/api/webhooks/123456789/test_webhook_url"
        }
    }

    # Create action and test template substitution
    action = DiscordNotificationAction(config)

    # Test webhook URL substitution
    webhook_url = action._substitute_templates(action.webhook_url_template, event_data)
    print(f"Original template: {action.webhook_url_template}")
    print(f"Substituted webhook URL: {webhook_url}")
    print(f"Expected: {event_data['program_settings']['discord_webhook_url']}")

    # Test embed creation
    embed = action._create_embed(event_data)
    print(f"Embed title: {embed['title']}")
    print(f"Embed description: {embed['description']}")

    # Verify substitutions worked
    assert webhook_url == event_data['program_settings']['discord_webhook_url'], f"Webhook URL substitution failed: got {webhook_url}"
    assert embed['title'] == "Test: h3xit", f"Title substitution failed: got {embed['title']}"
    assert embed['description'] == "Event: test_event", f"Description substitution failed: got {embed['description']}"

    print("✅ All template substitutions working correctly!")


async def test_discord_batch_template_substitution():
    """Test Discord notification batch template substitution without actually sending to Discord"""
    import sys
    import os
    sys.path.append('.')

    from app.event_handlers import DiscordNotificationAction, AssetFilterCondition

    # Test config with batch templates (like in handlers.yaml)
    config = {
        "webhook_url": "{program_settings.discord_webhook_url}",
        "batch_title_template": "🟡 New subdomain discovered!",
        "batch_description_template": "**Domains:** {domain_list}",
        "color": 16776960  # Yellow
    }

    # Create action with asset filter condition (batch mode)
    action = DiscordNotificationAction(config)
    # Add asset filter condition manually for testing
    asset_filter = AssetFilterCondition({
        "asset_field": "assets",
        "filter_field": "ip",
        "filter_operator": "not_exists",
        "batch_mode": True
    })
    action.conditions = [asset_filter]

    # Test event data with assets (simulating real event)
    event_data = {
        "program_name": "h3xit",
        "event": "asset.batch_created",
        "program_settings": {
            "discord_webhook_url": "https://discord.com/api/webhooks/123456789/test_webhook_url"
        },
        "assets": [
            {"name": "test1.h3xit.com", "ip": None},  # Should be included (no IP)
            {"name": "test2.h3xit.com"},              # Should be included (no IP field)
            {"name": "test3.h3xit.com", "ip": "1.2.3.4"}  # Should be excluded (has IP)
        ]
    }

    # Test the batch processing method directly (this creates the batch variables)
    result = await action._execute_with_batch_filter(event_data, asset_filter)

    print(f"Action success: {result.success}")
    print(f"Action message: {result.message}")
    print(f"Filtered count: {result.data.get('filtered_count', 'N/A')}")
    print(f"Batch mode: {result.data.get('batch_mode', 'N/A')}")

    if result.data.get('embed'):
        embed = result.data['embed']
        print(f"Embed title: {embed['title']}")
        print(f"Embed description: {embed['description']}")
        print(f"Embed color: {embed['color']}")

        # Verify batch processing worked correctly
        assert embed['title'] == "🟡 New subdomain discovered!", f"Batch title template failed: got {embed['title']}"
        assert "test1.h3xit.com" in embed['description'], f"Domain list not found in description: {embed['description']}"
        assert "test2.h3xit.com" in embed['description'], f"Domain list not found in description: {embed['description']}"
        assert "test3.h3xit.com" not in embed['description'], f"Domain with IP should not be included: {embed['description']}"
        assert embed['color'] == 16776960, f"Color should be yellow: got {embed['color']}"

        # Verify domain_list was properly substituted
        expected_description = "**Domains:** test1.h3xit.com, test2.h3xit.com"
        assert embed['description'] == expected_description, f"Description should be '{expected_description}' but got '{embed['description']}'"

    print("✅ All batch template substitutions with asset filtering working correctly!")


async def test_discord_full_batch_processing():
    """Test the complete Discord notification batch processing (same as above but with different name for clarity)"""
    await test_discord_batch_template_substitution()


async def test_workflow_list_expansion():
    """Test workflow trigger action template substitution with list expansion"""
    import sys
    import os
    sys.path.append('.')

    from app.event_handlers import WorkflowTriggerAction, AssetFilterCondition

    # Test config matching the handlers.yaml workflow trigger
    config = {
        "workflow_name": "event_triggered_workflow",
        "api_url": "http://api:8000",
        "api_key": "test_key",
        "endpoint": "run",
        "use_custom_payload": True,
        "parameters": {
            "workflow_name": "event_triggered_workflow",
            "program_name": "{program_name}",
            "description": "Event triggered workflow for subdomains without IPs",
            "steps": [{
                "name": "step_1",
                "tasks": [{
                    "name": "resolve_domain",
                    "force": True,
                    "params": {},
                    "task_type": "resolve_domain",
                    "input_mapping": {
                        "domains": "inputs.input_1"
                    }
                }]
            }],
            "variables": {},
            "inputs": {
                "input_1": {
                    "type": "direct",
                    "values": ["{domain_list_array}"],  # This should expand to individual domains
                    "value_type": "domains"
                }
            },
            "workflow_definition_id": ""
        }
    }

    # Create action with asset filter condition (batch mode)
    action = WorkflowTriggerAction(config)
    asset_filter = AssetFilterCondition({
        "asset_field": "assets",
        "filter_field": "ip",
        "filter_operator": "not_exists",
        "batch_mode": True
    })
    action.conditions = [asset_filter]

    # Test event data with multiple assets
    event_data = {
        "program_name": "h3xit",
        "event": "asset.batch_created",
        "assets": [
            {"name": "test1.h3xit.com", "ip": None},  # Should be included
            {"name": "test2.h3xit.com"},              # Should be included
            {"name": "test3.h3xit.com", "ip": "1.2.3.4"}  # Should be excluded
        ]
    }

    # Test the template substitution directly by checking the batch variables and payload creation
    # First, let's manually create the batch variables like the action would
    assets = event_data.get('assets', [])
    filtered_assets = [asset for asset in assets if action._asset_matches_workflow_filter(asset, asset_filter)]

    domain_names = [asset.get("name", "unknown") for asset in filtered_assets]
    batch_vars = {
        "filtered_count": len(filtered_assets),
        "total_count": len(assets),
        "filtered_assets": filtered_assets,
        "domain_list": ", ".join(domain_names),  # For string contexts (Discord messages)
        "domain_list_array": domain_names,       # For list contexts (workflow inputs)
        "ip_list": ", ".join([str(asset.get("ip", "no-ip")) for asset in filtered_assets]),
    }

    print(f"Filtered assets: {len(filtered_assets)}")
    print(f"Domain names: {domain_names}")
    print(f"Batch vars domain_list: {batch_vars['domain_list']}")
    print(f"Batch vars domain_list_array: {batch_vars['domain_list_array']}")

    # Verify the filtering worked correctly
    assert len(filtered_assets) == 2, f"Expected 2 filtered assets, got {len(filtered_assets)}"
    assert "test1.h3xit.com" in [a["name"] for a in filtered_assets], "test1.h3xit.com should be included"
    assert "test2.h3xit.com" in [a["name"] for a in filtered_assets], "test2.h3xit.com should be included"
    assert "test3.h3xit.com" not in [a["name"] for a in filtered_assets], "test3.h3xit.com should be excluded"

    # Test the template substitution directly
    template_context = dict(event_data)
    template_context.update(batch_vars)

    # Test the list expansion in the workflow parameters
    parameters = config["parameters"]
    substituted_params = action._substitute_templates(parameters, template_context)

    inputs = substituted_params.get('inputs', {})
    input_1 = inputs.get('input_1', {})
    values = input_1.get('values', [])

    print(f"Substituted workflow inputs.input_1.values: {values}")
    print(f"Values type: {type(values)}")
    print(f"Individual values: {[v for v in values]}")

    # Verify the list expansion worked correctly
    assert isinstance(values, list), f"Values should be a list, got {type(values)}"
    assert len(values) == 2, f"Expected 2 domains in values, got {len(values)}: {values}"
    assert "test1.h3xit.com" in values, f"test1.h3xit.com not found in values: {values}"
    assert "test2.h3xit.com" in values, f"test2.h3xit.com not found in values: {values}"
    assert "test3.h3xit.com" not in values, f"test3.h3xit.com should not be included: {values}"

    print("✅ Workflow list expansion working correctly!")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "receive":
        asyncio.run(test_receive_event())
    elif len(sys.argv) > 1 and sys.argv[1] == "test_notifier":
        asyncio.run(test_notifier_processing())
    elif len(sys.argv) > 1 and sys.argv[1] == "test_templates":
        asyncio.run(test_discord_template_substitution())
    elif len(sys.argv) > 1 and sys.argv[1] == "test_batch_templates":
        asyncio.run(test_discord_batch_template_substitution())
    elif len(sys.argv) > 1 and sys.argv[1] == "test_full_batch":
        asyncio.run(test_discord_full_batch_processing())
    elif len(sys.argv) > 1 and sys.argv[1] == "test_workflow_expansion":
        asyncio.run(test_workflow_list_expansion())
    else:
        asyncio.run(main())
