import json
import logging
import os
import sys

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handler(event, context):
    try:
        curr_dir = os.getcwd()
        task_root = os.environ.get('LAMBDA_TASK_ROOT', 'N/A')
        ls_root = os.listdir(task_root) if task_root != 'N/A' else []
        
        import sys, os
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        
        try:
            import mitrashared
            import mitrashared.config
            import mitrashared.models
            import mitrashared.security
            
            # Direct imports as in auth_handler.py
            from mitrashared.config import get_settings
            from mitrashared.models import AuthResult, Credentials, TokenValidation
            from mitrashared.security import create_access_token, verify_token
            
            import_status = "Successfully imported all auth_handler dependencies"
        except Exception as e:
            import_status = f"Import Error: {str(e)}"
            logger.exception("Diagnostic import failed")
            
        logger.info(f"IMPORT_STATUS: {import_status}")
        
        return {
            "statusCode": 200,
            "body": json.dumps({
                "ls": ls_root,
                "sys_path": sys.path,
                "task_root": task_root,
                "event": event
            })
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": str(e)
        }
