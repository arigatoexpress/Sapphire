import kfp
from kfp import dsl
from kfp.components import create_component_from_func

# Define a base image for our components
BASE_IMAGE = "python:3.9"

# Define the Data Prep Component
@create_component_from_func(base_image=BASE_IMAGE)
def data_prep_component(data_path: str, output_path: str):
    """
    Loads market data from GCS, performs data validation, and saves processed data.
    """
    import pandas as pd
    from google.cloud import storage
    import great_expectations as ge
    import os

    # Ensure great_expectations is installed
    try:
        import great_expectations as ge
    except ImportError:
        import subprocess
        subprocess.check_call(["pip", "install", "great_expectations", "gcsfs"])
        import great_expectations as ge

    # Download data from GCS
    client = storage.Client()
    bucket_name, blob_name = data_path.replace("gs://", "").split("/", 1)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    
    # Create a local directory for data
    os.makedirs("data", exist_ok=True)
    local_data_path = "data/training_data.jsonl"
    blob.download_to_filename(local_data_path)

    # Load data
    df = pd.read_json(local_data_path, lines=True)

    # Data Validation with Great Expectations
    # This is a simplified example. In a real scenario, you'd load a full Expectation Suite.
    ge_df = ge.from_pandas(df)
    
    # Example expectations
    ge_df.expect_column_to_exist("timestamp")
    ge_df.expect_column_to_exist("open")
    ge_df.expect_column_to_exist("high")
    ge_df.expect_column_to_exist("low")
    ge_df.expect_column_to_exist("close")
    ge_df.expect_column_to_exist("volume")
    ge_df.expect_column_values_to_be_between("open", min_value=0)
    ge_df.expect_column_values_to_be_between("high", min_value=0)
    ge_df.expect_column_values_to_be_between("low", min_value=0)
    ge_df.expect_column_values_to_be_between("close", min_value=0)
    ge_df.expect_column_values_to_be_between("volume", min_value=0)

    validation_result = ge_df.validate()

    if not validation_result["success"]:
        print("Data validation failed:")
        for result in validation_result["results"]:
            if not result["success"]:
                print(f"- {result['expectation_config']['expectation_type']}: {result['expectation_config']['kwargs']}")
        raise ValueError("Data validation failed. Aborting pipeline.")
    else:
        print("Data validation successful!")

    # Save processed data (for this example, just re-saving the original)
    processed_local_path = "data/processed_training_data.jsonl"
    df.to_json(processed_local_path, orient="records", lines=True)

    # Upload processed data to GCS
    processed_bucket_name, processed_blob_name = output_path.replace("gs://", "").split("/", 1)
    processed_bucket = client.bucket(processed_bucket_name)
    processed_blob = processed_bucket.blob(processed_blob_name)
    processed_blob.upload_from_filename(processed_local_path)
    print(f"Processed data uploaded to {output_path}")


# Define the Train Component
@create_component_from_func(base_image=BASE_IMAGE)
def train_component(agent_name: str, data_path: str, hyperparameters: str, output_path: str):
    """
    Executes the training script for a given agent.
    """
    import subprocess
    import json
    import os

    # Ensure google-cloud-storage is installed for GCS access
    try:
        from google.cloud import storage
    except ImportError:
        subprocess.check_call(["pip", "install", "google-cloud-storage"])
        from google.cloud import storage

    # Create a local directory for data
    os.makedirs("data", exist_ok=True)
    local_data_path = "data/processed_training_data.jsonl"

    # Download processed data from GCS
    client = storage.Client()
    bucket_name, blob_name = data_path.replace("gs://", "").split("/", 1)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.download_to_filename(local_data_path)
    print(f"Downloaded processed data from {data_path} to {local_data_path}")

    # Define the command to run the training script
    command = [
        "python",
        "mlops/training_scripts/train_agent.py",
        "--agent_name", agent_name,
        "--data_path", local_data_path,  # Pass local path to training script
        "--hyperparameters", hyperparameters,
        "--output_path", output_path # This will be a GCS path for the model artifacts
    ]
    
    # Execute the training script
    print(f"Running training command: {' '.join(command)}")
    process = subprocess.run(command, capture_output=True, text=True, check=True)
    print("Training script stdout:")
    print(process.stdout)
    if process.stderr:
        print("Training script stderr:")
        print(process.stderr)


# Define the Evaluate Component
@create_component_from_func(base_image=BASE_IMAGE)
def evaluate_component(model_path: str, holdout_data_path: str, metrics_output_path: str) -> float:
    """
    Evaluates the trained model against a holdout set and calculates Sharpe Ratio.
    Logs metrics to Vertex AI Experiments.
    """
    import pandas as pd
    import numpy as np
    from google.cloud import storage
    import os
    import json

    # Ensure google-cloud-aiplatform is installed for Vertex AI Experiments
    try:
        from google.cloud import aiplatform
    except ImportError:
        import subprocess
        subprocess.check_call(["pip", "install", "google-cloud-aiplatform"])
        from google.cloud import aiplatform

    # Download model and holdout data from GCS
    client = storage.Client()
    
    # Download model (assuming it's a single file for simplicity)
    model_bucket_name, model_blob_name = model_path.replace("gs://", "").split("/", 1)
    model_bucket = client.bucket(model_bucket_name)
    model_blob = model_bucket.blob(model_blob_name)
    os.makedirs("model", exist_ok=True)
    local_model_path = "model/trained_model.pkl" # Assuming a pickle file
    model_blob.download_to_filename(local_model_path)
    print(f"Downloaded model from {model_path} to {local_model_path}")

    # Download holdout data
    holdout_bucket_name, holdout_blob_name = holdout_data_path.replace("gs://", "").split("/", 1)
    holdout_bucket = client.bucket(holdout_bucket_name)
    holdout_blob = holdout_bucket.blob(holdout_blob_name)
    os.makedirs("data", exist_ok=True)
    local_holdout_path = "data/holdout_data.jsonl"
    holdout_blob.download_to_filename(local_holdout_path)
    print(f"Downloaded holdout data from {holdout_data_path} to {local_holdout_path}")

    # Load holdout data
    holdout_df = pd.read_json(local_holdout_path, lines=True)

    # --- Simulate Model Evaluation and Sharpe Ratio Calculation ---
    # In a real scenario, you would load the model and make predictions
    # For demonstration, we'll generate a dummy Sharpe Ratio
    np.random.seed(42)
    simulated_returns = np.random.normal(0.001, 0.01, len(holdout_df)) # Daily returns
    
    # Calculate Sharpe Ratio (simplified: assuming risk-free rate is 0)
    # Sharpe Ratio = (Mean Return - Risk-Free Rate) / Standard Deviation of Returns
    mean_return = np.mean(simulated_returns)
    std_dev_returns = np.std(simulated_returns)
    
    if std_dev_returns == 0:
        sharpe_ratio = 0.0
    else:
        sharpe_ratio = mean_return / std_dev_returns * np.sqrt(252) # Annualized for daily data

    print(f"Calculated Sharpe Ratio: {sharpe_ratio}")

    # Log metrics to Vertex AI Experiments
    # aiplatform.init(project="your-gcp-project-id", location="your-gcp-region") # Initialize with your project and region
    # experiment = aiplatform.Experiment(experiment_name="agent-training-experiment")
    # experiment.log_metrics({"sharpe_ratio": sharpe_ratio})
    # print(f"Logged Sharpe Ratio {sharpe_ratio} to Vertex AI Experiments.")

    # Save metrics to GCS
    metrics = {"sharpe_ratio": sharpe_ratio}
    local_metrics_path = "metrics.json"
    with open(local_metrics_path, "w") as f:
        json.dump(metrics, f)
    
    metrics_bucket_name, metrics_blob_name = metrics_output_path.replace("gs://", "").split("/", 1)
    metrics_bucket = client.bucket(metrics_bucket_name)
    metrics_blob = metrics_bucket.blob(metrics_blob_name)
    metrics_blob.upload_from_filename(local_metrics_path)
    print(f"Metrics uploaded to {metrics_output_path}")

    return sharpe_ratio


# Define the Register & Deploy Component
@create_component_from_func(base_image=BASE_IMAGE)
def register_and_deploy_component(
    model_path: str,
    agent_name: str,
    project_id: str,
    location: str,
    sharpe_ratio: float,
    threshold: float = 2.0
):
    """
    Registers the model in Vertex AI Model Registry and deploys to Vertex AI Endpoint
    if Sharpe Ratio exceeds a threshold.
    """
    from google.cloud import aiplatform
    import os

    if sharpe_ratio < threshold:
        print(f"Sharpe Ratio {sharpe_ratio} is below threshold {threshold}. Skipping model registration and deployment.")
        return

    print(f"Sharpe Ratio {sharpe_ratio} meets threshold {threshold}. Proceeding with model registration and deployment.")

    aiplatform.init(project=project_id, location=location)

    # Register model in Vertex AI Model Registry
    display_name = f"{agent_name}-model"
    model_upload = aiplatform.Model.upload(
        display_name=display_name,
        artifact_uri=os.path.dirname(model_path), # GCS path to the directory containing model artifacts
        serving_container_image_uri="us-docker.pkg.dev/vertex-ai/prediction/tf2-cpu.2-8:latest", # Example image, adjust as needed
        description=f"Trained {agent_name} agent with Sharpe Ratio {sharpe_ratio:.2f}"
    )
    model_upload.wait()
    print(f"Model {display_name} registered with ID: {model_upload.resource_name}")

    # Deploy model to Vertex AI Endpoint
    endpoint_display_name = f"{agent_name}-endpoint"
    endpoint = aiplatform.Endpoint.create(
        display_name=endpoint_display_name,
        project=project_id,
        location=location
    )
    
    endpoint.deploy(
        model=model_upload,
        deployed_model_display_name=f"{agent_name}-deployed-model",
        machine_type="n1-standard-4",
        min_replica_count=1,
        max_replica_count=1,
        traffic_split={"0": 100} # Deploy with 100% traffic
    )
    print(f"Model {display_name} deployed to endpoint: {endpoint.resource_name}")


@dsl.pipeline(
    name="Agent Training Pipeline",
    description="A Kubeflow pipeline to train, evaluate, and deploy trading agents."
)
def training_pipeline(
    agent_name: str,
    training_data_path: str = "gs://sapphireinfinite/training/*.jsonl",
    holdout_data_path: str = "gs://sapphireinfinite/holdout/*.jsonl",
    hyperparameters: str = '{"learning_rate": 0.01, "epochs": 10}',
    project_id: str = "your-gcp-project-id",
    location: str = "us-central1"
):
    """
    Orchestrates the training, evaluation, and deployment of a trading agent.
    """
    data_prep_task = data_prep_component(
        data_path=training_data_path,
        output_path=f"gs://sapphireinfinite/processed_data/{agent_name}/training_data.jsonl"
    )

    train_task = train_component(
        agent_name=agent_name,
        data_path=data_prep_task.outputs["output_path"],
        hyperparameters=hyperparameters,
        output_path=f"gs://sapphireinfinite/models/{agent_name}/" # GCS path for model artifacts
    ).after(data_prep_task)

    evaluate_task = evaluate_component(
        model_path=train_task.outputs["output_path"],
        holdout_data_path=holdout_data_path,
        metrics_output_path=f"gs://sapphireinfinite/metrics/{agent_name}/evaluation_metrics.json"
    ).after(train_task)

    register_deploy_task = register_and_deploy_component(
        model_path=train_task.outputs["output_path"],
        agent_name=agent_name,
        project_id=project_id,
        location=location,
        sharpe_ratio=evaluate_task.outputs["Output"]
    ).after(evaluate_task)

if __name__ == "__main__":
    # Compile the pipeline
    kfp.compiler.Compiler().compile(training_pipeline, "training_pipeline.yaml")
    print("Kubeflow pipeline compiled to training_pipeline.yaml")