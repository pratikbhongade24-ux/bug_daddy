import os
import importlib

# Determine which microservice to load based on an environment variable.
# Expected format: e.g., "AutoDebit" for the AutoDebitService.
SERVICE = os.getenv("SERVICE_NAME")
if not SERVICE:
    raise RuntimeError("SERVICE_NAME environment variable is not set for Lambda wrapper")

# Construct the module path to the service's lambda_function.
# The directory layout is microservices/<ServiceName>Service/lambda_function.py
module_path = f"microservices.{SERVICE}Service.lambda_function"
try:
    service_mod = importlib.import_module(module_path)
except ModuleNotFoundError as exc:
    raise ImportError(f"Could not import module '{module_path}'. Ensure the SERVICE_NAME is correct and the package is included in the deployment zip.") from exc

# Expose the lambda_handler expected by AWS Lambda.
lambda_handler = getattr(service_mod, "lambda_handler")
