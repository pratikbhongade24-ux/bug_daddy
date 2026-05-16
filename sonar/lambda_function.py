import os
import time

import boto3


def lambda_handler(event, context):
    region = os.environ.get("AWS_REGION", "ap-south-1")
    instance_id = os.environ["SONAR_INSTANCE_ID"]
    scan_command = os.environ.get("SONAR_SCAN_COMMAND", "/opt/sonarqube/run-scan.sh")
    wait_seconds = int(os.environ.get("SONAR_SSM_WAIT_SECONDS", "240"))

    ec2 = boto3.client("ec2", region_name=region)
    ssm = boto3.client("ssm", region_name=region)

    state = ec2.describe_instances(InstanceIds=[instance_id])["Reservations"][0]["Instances"][0]["State"]["Name"]
    if state == "stopped":
        ec2.start_instances(InstanceIds=[instance_id])
        ec2.get_waiter("instance_running").wait(InstanceIds=[instance_id])
    elif state not in {"running", "pending"}:
        raise RuntimeError(f"Sonar runner is in unsupported state: {state}")

    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        info = ssm.describe_instance_information(
            Filters=[{"Key": "InstanceIds", "Values": [instance_id]}]
        ).get("InstanceInformationList", [])
        if info and info[0].get("PingStatus") == "Online":
            break
        time.sleep(10)
    else:
        raise TimeoutError(f"SSM did not become online for {instance_id}")

    sonar_session_id = event.get("sonar_session_id", "")
    api_base_url = os.environ.get("BUGDADDY_API_BASE_URL", "")
    execution_secret = os.environ.get("AGENT_EXECUTION_LOG_SECRET", "")

    env_prefix = ""
    if sonar_session_id:
        env_prefix += f"SONAR_SESSION_ID={sonar_session_id} "
    if api_base_url:
        env_prefix += f"BUGDADDY_API_BASE_URL={api_base_url} "
    if execution_secret:
        env_prefix += f"AGENT_EXECUTION_LOG_SECRET={execution_secret} "

    command = f"nohup env {env_prefix}{scan_command} > /var/log/sonar-scan.log 2>&1 &" if env_prefix else f"nohup {scan_command} > /var/log/sonar-scan.log 2>&1 &"

    response = ssm.send_command(
        InstanceIds=[instance_id],
        DocumentName="AWS-RunShellScript",
        Comment="Run BugDaddy SonarQube scan",
        Parameters={"commands": [command]},
        TimeoutSeconds=60,
        CloudWatchOutputConfig={"CloudWatchOutputEnabled": True},
    )
    return {"commandId": response["Command"]["CommandId"]}
