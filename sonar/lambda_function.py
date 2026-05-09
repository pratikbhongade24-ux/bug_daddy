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

    response = ssm.send_command(
        InstanceIds=[instance_id],
        DocumentName="AWS-RunShellScript",
        Comment="Run BugDaddy SonarQube scan",
        Parameters={"commands": [scan_command]},
        CloudWatchOutputConfig={"CloudWatchOutputEnabled": True},
    )
    return {"commandId": response["Command"]["CommandId"]}
