import boto3
import os
import time
from dotenv import load_dotenv

load_dotenv()

logs = boto3.client(
    'logs',
    region_name=os.getenv("AWS_REGION", "ap-south-1"),
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
)

log_group = "/aws/lambda/sankatmitra-corridor-lambda"

try:
    streams_response = logs.describe_log_streams(
        logGroupName=log_group,
        orderBy='LastEventTime',
        descending=True,
        limit=1
    )
    
    if streams_response['logStreams']:
        stream_name = streams_response['logStreams'][0]['logStreamName']
        print(f"Latest Stream: {stream_name}")
        
        # Read the last 20 events
        events_response = logs.get_log_events(
            logGroupName=log_group,
            logStreamName=stream_name,
            limit=20,
            startFromHead=False
        )
        print("\n--- LAST OUTPUT ---")
        for event in events_response['events']:
            print(event['message'].strip())
            
    else:
        print("No log streams found.")
except Exception as e:
    print(f"Error reading logs: {e}")
