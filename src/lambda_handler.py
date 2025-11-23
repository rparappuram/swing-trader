"""AWS Lambda handler for live trading execution.

This module provides the Lambda entry point for automated trading.
The Lambda function is triggered on a schedule (e.g., market close) and
executes all trading strategies.
"""
import json
import logging
import os
from typing import Dict, Any

# Configure logging for Lambda
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Import must happen after setting up logging
from src.runners.live import LiveRunner


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """AWS Lambda handler function.
    
    This function is called by AWS Lambda when triggered. It initializes
    the live trading runner and executes strategies.
    
    Args:
        event: Lambda event object (contains trigger information)
        context: Lambda context object (contains runtime information)
        
    Returns:
        Dictionary with execution results and status
    """
    logger.info("="*80)
    logger.info("Lambda function invoked")
    logger.info(f"Function name: {context.function_name}")
    logger.info(f"Request ID: {context.request_id}")
    logger.info(f"Remaining time: {context.get_remaining_time_in_millis()}ms")
    logger.info("="*80)
    
    try:
        # Initialize live runner
        # Note: Environment variables should be set in Lambda configuration
        logger.info("Initializing LiveRunner")
        runner = LiveRunner()
        
        # Run strategies
        logger.info("Executing strategies...")
        results = runner.run_strategies()
        
        # Prepare response
        response = {
            'statusCode': 200,
            'body': {
                'message': 'Strategies executed successfully',
                'results': results
            }
        }
        
        logger.info("Lambda function completed successfully")
        return response
        
    except Exception as e:
        logger.error(f"Error in Lambda execution: {e}")
        logger.exception(e)
        
        # Return error response
        return {
            'statusCode': 500,
            'body': {
                'message': 'Error executing strategies',
                'error': str(e)
            }
        }


def local_test():
    """Test function for local execution.
    
    This allows you to test the Lambda handler locally before deployment.
    Run with: python src/lambda_handler.py
    """
    import sys
    from pathlib import Path
    
    # Add project root to path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    
    # Mock Lambda context
    class MockContext:
        function_name = "swing-trader-local-test"
        request_id = "local-test-request-id"
        
        def get_remaining_time_in_millis(self):
            return 300000  # 5 minutes
    
    # Mock event
    event = {
        'source': 'local-test',
        'time': '2024-01-01T16:00:00Z'
    }
    
    # Call handler
    result = lambda_handler(event, MockContext())
    
    # Print result
    print("\n" + "="*80)
    print("LAMBDA HANDLER RESULT")
    print("="*80)
    print(json.dumps(result, indent=2))
    print("="*80 + "\n")


if __name__ == '__main__':
    # Run local test when executed directly
    local_test()
