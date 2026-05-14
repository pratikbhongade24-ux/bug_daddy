import os
import time
import boto3

# Module-level AWS clients (reuse across Lambda invocations)
_REGION = os.environ.get("AWS_REGION", "ap-south-1")
_EC2_CLIENT = boto3.client("ec2", region_name=_REGION)
_SSM_CLIENT = boto3.client("ssm", region_name=_REGION)


def lambda_handler(event, context):
    # Per-invocation environment variables
    instance_id = os.environ["SONAR_INSTANCE_ID"]
    scan_command = os.environ.get("SONAR_SCAN_COMMAND", "/opt/sonarqube/run-scan.sh")
    wait_seconds = int(os.environ.get("SONAR_SSM_WAIT_SECONDS", "240"))

    ec2 = _EC2_CLIENT
    ssm = _SSM_CLIENT

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

    response = ssm.send_command(
        InstanceIds=[instance_id],
        DocumentName="AWS-RunShellScript",
        Comment="Run BugDaddy SonarQube scan",
        Parameters={"commands": [f"nohup {scan_command} > /var/log/sonar-scan.log 2>&1 &"]},
        TimeoutSeconds=60,
        CloudWatchOutputConfig={"CloudWatchOutputEnabled": True},
    )
    return {"commandId": response["Command"]["CommandId"]}
