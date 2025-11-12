# Vertex AI Model Deployments for HFT Trading Agents

# Model Registry for storing trained models
resource "google_vertex_ai_model" "deepseek_momentum" {
  project  = var.project_id
  location = var.region
  name     = "deepseek-momentum-v1"
  display_name = "DeepSeek Momentum Agent"
  description = "High-conviction momentum trading agent powered by DeepSeek-V3"

  container_spec {
    image_uri = "${var.region}-docker.pkg.dev/${var.project_id}/hft-models/deepseek-agent:latest"
    command   = ["python", "serve.py"]
    args      = ["--model_type", "deepseek-v3"]
  }

  metadata_schema_uri = "gs://google-cloud-aiplatform/schema/trainingjob/definition/custom_task_1.0.0.yaml"
  training_pipeline    = google_vertex_ai_training_pipeline.deepseek_training.id

  labels = {
    agent_type = "momentum"
    risk_level = "medium"
    specialization = "trend_following"
  }
}

resource "google_vertex_ai_model" "qwen_adaptive" {
  project  = var.project_id
  location = var.region
  name     = "qwen-adaptive-v1"
  display_name = "Qwen Adaptive Agent"
  description = "Adaptive mean-reversion trading agent powered by Qwen2.5-7B"

  container_spec {
    image_uri = "${var.region}-docker.pkg.dev/${var.project_id}/hft-models/qwen-agent:latest"
    command   = ["python", "serve.py"]
    args      = ["--model_type", "qwen-7b"]
  }

  metadata_schema_uri = "gs://google-cloud-aiplatform/schema/trainingjob/definition/custom_task_1.0.0.yaml"
  training_pipeline    = google_vertex_ai_training_pipeline.qwen_training.id

  labels = {
    agent_type = "mean_reversion"
    risk_level = "low"
    specialization = "arbitrage"
  }
}

resource "google_vertex_ai_model" "fingpt_alpha" {
  project  = var.project_id
  location = var.region
  name     = "fingpt-alpha-v1"
  display_name = "FinGPT Alpha Agent"
  description = "Fundamental-driven trading agent using sentiment analysis"

  container_spec {
    image_uri = "${var.region}-docker.pkg.dev/${var.project_id}/hft-models/fingpt-agent:latest"
    command   = ["python", "serve.py"]
    args      = ["--model_type", "fingpt"]
  }

  metadata_schema_uri = "gs://google-cloud-aiplatform/schema/trainingjob/definition/custom_task_1.0.0.yaml"
  training_pipeline    = google_vertex_ai_training_pipeline.fingpt_training.id

  labels = {
    agent_type = "fundamental"
    risk_level = "medium"
    specialization = "sentiment"
  }
}

resource "google_vertex_ai_model" "lagllama_degenerate" {
  project  = var.project_id
  location = var.region
  name     = "lagllama-degenerate-v1"
  display_name = "Lag-Llama Degenerate Agent"
  description = "High-volatility degenerate trader using time-series forecasting"

  container_spec {
    image_uri = "${var.region}-docker.pkg.dev/${var.project_id}/hft-models/lagllama-agent:latest"
    command   = ["python", "serve.py"]
    args      = ["--model_type", "lagllama"]
  }

  metadata_schema_uri = "gs://google-cloud-aiplatform/schema/trainingjob/definition/custom_task_1.0.0.yaml"
  training_pipeline    = google_vertex_ai_training_pipeline.lagllama_training.id

  labels = {
    agent_type = "high_volatility"
    risk_level = "high"
    specialization = "time_series"
  }
}

# Endpoint deployments for online prediction
resource "google_vertex_ai_endpoint" "deepseek_endpoint" {
  project  = var.project_id
  location = var.region
  name     = "deepseek-momentum-endpoint"
  display_name = "DeepSeek Momentum Trading Endpoint"
  description = "Online prediction endpoint for momentum trading signals"

  labels = {
    agent = "deepseek"
    purpose = "trading_signals"
    environment = "production"
  }
}

resource "google_vertex_ai_endpoint" "qwen_endpoint" {
  project  = var.project_id
  location = var.region
  name     = "qwen-adaptive-endpoint"
  display_name = "Qwen Adaptive Trading Endpoint"
  description = "Online prediction endpoint for adaptive trading signals"

  labels = {
    agent = "qwen"
    purpose = "trading_signals"
    environment = "production"
  }
}

resource "google_vertex_ai_endpoint" "fingpt_endpoint" {
  project  = var.project_id
  location = var.region
  name     = "fingpt-alpha-endpoint"
  display_name = "FinGPT Alpha Trading Endpoint"
  description = "Online prediction endpoint for fundamental trading signals"

  labels = {
    agent = "fingpt"
    purpose = "trading_signals"
    environment = "production"
  }
}

resource "google_vertex_ai_endpoint" "lagllama_endpoint" {
  project  = var.project_id
  location = var.region
  name     = "lagllama-degenerate-endpoint"
  display_name = "Lag-Llama Degenerate Trading Endpoint"
  description = "Online prediction endpoint for high-volatility trading signals"

  labels = {
    agent = "lagllama"
    purpose = "trading_signals"
    environment = "production"
  }
}

# Deploy models to endpoints
resource "google_vertex_ai_endpoint_deployment" "deepseek_deployment" {
  project     = var.project_id
  location    = var.region
  endpoint    = google_vertex_ai_endpoint.deepseek_endpoint.name
  model       = google_vertex_ai_model.deepseek_momentum.name
  display_name = "DeepSeek Momentum Deployment"

  traffic_split {
    deployed_model_id = google_vertex_ai_endpoint_deployment.deepseek_deployment.deployed_model_id
    traffic_percentage = 100
  }

  dedicated_resources {
    machine_spec {
      machine_type = "n1-standard-4"
      accelerator_type = "NVIDIA_TESLA_T4"
      accelerator_count = 1
    }
    min_replica_count = 1
    max_replica_count = 3
  }
}

resource "google_vertex_ai_endpoint_deployment" "qwen_deployment" {
  project     = var.project_id
  location    = var.region
  endpoint    = google_vertex_ai_endpoint.qwen_endpoint.name
  model       = google_vertex_ai_model.qwen_adaptive.name
  display_name = "Qwen Adaptive Deployment"

  traffic_split {
    deployed_model_id = google_vertex_ai_endpoint_deployment.qwen_deployment.deployed_model_id
    traffic_percentage = 100
  }

  dedicated_resources {
    machine_spec {
      machine_type = "n1-standard-4"
      accelerator_type = "NVIDIA_TESLA_T4"
      accelerator_count = 1
    }
    min_replica_count = 1
    max_replica_count = 3
  }
}

resource "google_vertex_ai_endpoint_deployment" "fingpt_deployment" {
  project     = var.project_id
  location    = var.region
  endpoint    = google_vertex_ai_endpoint.fingpt_endpoint.name
  model       = google_vertex_ai_model.fingpt_alpha.name
  display_name = "FinGPT Alpha Deployment"

  traffic_split {
    deployed_model_id = google_vertex_ai_endpoint_deployment.fingpt_deployment.deployed_model_id
    traffic_percentage = 100
  }

  dedicated_resources {
    machine_spec {
      machine_type = "n1-standard-4"
      accelerator_type = "NVIDIA_TESLA_T4"
      accelerator_count = 1
    }
    min_replica_count = 1
    max_replica_count = 3
  }
}

resource "google_vertex_ai_endpoint_deployment" "lagllama_deployment" {
  project     = var.project_id
  location    = var.region
  endpoint    = google_vertex_ai_endpoint.lagllama_endpoint.name
  model       = google_vertex_ai_model.lagllama_degenerate.name
  display_name = "Lag-Llama Degenerate Deployment"

  traffic_split {
    deployed_model_id = google_vertex_ai_endpoint_deployment.lagllama_deployment.deployed_model_id
    traffic_percentage = 100
  }

  dedicated_resources {
    machine_spec {
      machine_type = "n1-standard-8"
      accelerator_type = "NVIDIA_TESLA_T4"
      accelerator_count = 1
    }
    min_replica_count = 1
    max_replica_count = 5  # Higher capacity for degenerate trading
  }
}

# Training pipelines (placeholders - would be populated with actual training jobs)
resource "google_vertex_ai_training_pipeline" "deepseek_training" {
  project     = var.project_id
  location    = var.region
  display_name = "DeepSeek Momentum Training Pipeline"
  training_task_definition = "gs://google-cloud-aiplatform/schema/trainingjob/definition/custom_task_1.0.0.yaml"
  training_task_inputs = jsonencode({
    worker_pool_specs = [{
      machine_spec = {
        machine_type = "n1-standard-8"
        accelerator_type = "NVIDIA_TESLA_T4"
        accelerator_count = 1
      }
      replica_count = 1
      container_spec = {
        image_uri = "${var.region}-docker.pkg.dev/${var.project_id}/vertex-ai-training/deepseek-trainer:latest"
        command = ["python", "train.py"]
        args = ["--model_type", "deepseek", "--specialization", "momentum"]
      }
    }]
  })

  labels = {
    model_type = "deepseek"
    training_type = "momentum_trading"
  }
}

resource "google_vertex_ai_training_pipeline" "qwen_training" {
  project     = var.project_id
  location    = var.region
  display_name = "Qwen Adaptive Training Pipeline"
  training_task_definition = "gs://google-cloud-aiplatform/schema/trainingjob/definition/custom_task_1.0.0.yaml"
  training_task_inputs = jsonencode({
    worker_pool_specs = [{
      machine_spec = {
        machine_type = "n1-standard-8"
        accelerator_type = "NVIDIA_TESLA_T4"
        accelerator_count = 1
      }
      replica_count = 1
      container_spec = {
        image_uri = "${var.region}-docker.pkg.dev/${var.project_id}/vertex-ai-training/qwen-trainer:latest"
        command = ["python", "train.py"]
        args = ["--model_type", "qwen", "--specialization", "adaptive"]
      }
    }]
  })

  labels = {
    model_type = "qwen"
    training_type = "adaptive_trading"
  }
}

resource "google_vertex_ai_training_pipeline" "fingpt_training" {
  project     = var.project_id
  location    = var.region
  display_name = "FinGPT Alpha Training Pipeline"
  training_task_definition = "gs://google-cloud-aiplatform/schema/trainingjob/definition/custom_task_1.0.0.yaml"
  training_task_inputs = jsonencode({
    worker_pool_specs = [{
      machine_spec = {
        machine_type = "n1-standard-8"
        accelerator_type = "NVIDIA_TESLA_T4"
        accelerator_count = 1
      }
      replica_count = 1
      container_spec = {
        image_uri = "${var.region}-docker.pkg.dev/${var.project_id}/vertex-ai-training/fingpt-trainer:latest"
        command = ["python", "train.py"]
        args = ["--model_type", "fingpt", "--specialization", "fundamental"]
      }
    }]
  })

  labels = {
    model_type = "fingpt"
    training_type = "fundamental_trading"
  }
}

resource "google_vertex_ai_training_pipeline" "lagllama_training" {
  project     = var.project_id
  location    = var.region
  display_name = "Lag-Llama Degenerate Training Pipeline"
  training_task_definition = "gs://google-cloud-aiplatform/schema/trainingjob/definition/custom_task_1.0.0.yaml"
  training_task_inputs = jsonencode({
    worker_pool_specs = [{
      machine_spec = {
        machine_type = "n1-standard-16"
        accelerator_type = "NVIDIA_TESLA_T4"
        accelerator_count = 2
      }
      replica_count = 1
      container_spec = {
        image_uri = "${var.region}-docker.pkg.dev/${var.project_id}/vertex-ai-training/lagllama-trainer:latest"
        command = ["python", "train.py"]
        args = ["--model_type", "lagllama", "--specialization", "degenerate"]
      }
    }]
  })

  labels = {
    model_type = "lagllama"
    training_type = "high_volatility_trading"
  }
}
