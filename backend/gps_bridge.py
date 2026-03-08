def handler(event, context):
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": "{\"status\": \"DIAGNOSTIC_BRIDGE_LOADED\"}"
    }
