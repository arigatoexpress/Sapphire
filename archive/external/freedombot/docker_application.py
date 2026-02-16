##docker application##
import boto3
import json
import time

# AWS SQS configuration
sqs = boto3.client('sqs', region_name='your_aws_region') # Replace with your region
queue_url = 'your_sqs_queue_url'  # Replace with your SQS queue URL

def process_message(message):
    """
    Processes a message received from SQS.
    This is where your trade execution logic goes.
    """
    try:
        data = json.loads(message['Body'])
        print(f"Received message: {data}")

        # Extract relevant data from the message
        strategy = data.get('strategy')
        price = data.get('price')

        # Implement your trade execution logic here
        # ... (e.g., interact with a cryptocurrency exchange API) ...

        print(f"Trade executed for strategy: {strategy}, price: {price}")

    except Exception as e:
        print(f"Error processing message: {e}")

def poll_sqs():
    """
    Continuously polls the SQS queue for new messages.
    """
    while True:
        try:
            response = sqs.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=1,  # Get one message at a time
                WaitTimeSeconds=20  # Long polling (wait up to 20 seconds for a message)
            )

            if 'Messages' in response:
                for message in response['Messages']:
                    process_message(message)

                    # Delete the message from the queue after processing
                    receipt_handle = message['ReceiptHandle']
                    sqs.delete_message(
                        QueueUrl=queue_url,
                        ReceiptHandle=receipt_handle
                    )
        except Exception as e:
            print(f"Error polling SQS: {e}")

        time.sleep(5)  # Wait for a short time before polling again

if __name__ == "__main__":
    poll_sqs()