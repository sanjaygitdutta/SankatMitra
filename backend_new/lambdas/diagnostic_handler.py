import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handler(event, context):
    logger.info("DIAGNOSTIC_HANDLER_CALLED")
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*"
        },
        "body": json.dumps({
            "status": "DIAGNOSTIC_OK",
            "message": "Lambda successfully executed without shared dependencies"
        })
    }
