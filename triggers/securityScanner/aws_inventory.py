"""
AWS asset inventory and dependency graph discovery.

This module intentionally uses AWS APIs instead of browser automation for cloud
discovery. The browser layer is better used later for evidence collection and
web-app verification; infrastructure discovery should stay deterministic.
"""

from __future__ import annotations

import json
import re
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError


EDGE_TOOL = "aws_inventory"


def _asset(
    asset_type: str,
    service: str,
    asset_id: str,
    *,
    components: list[dict] | None = None,
    **metadata: Any,
) -> dict:
    return {
        "asset_type": asset_type,
        "service": service,
        "asset_id": asset_id,
        "components": components or [],
        **metadata,
    }


def _edge(
    source: str,
    target: str,
    relationship: str,
    *,
    source_type: str = "",
    target_type: str = "",
    via: str = "",
) -> dict:
    return {
        "tool": EDGE_TOOL,
        "source": source,
        "target": target,
        "relationship": relationship,
        "source_type": source_type,
        "target_type": target_type,
        "via": via,
    }


def _tool_result(
    category: str,
    status: str,
    *,
    assets: int = 0,
    edges: int = 0,
    message: str = "",
) -> dict:
    return {
        "tool": EDGE_TOOL,
        "category": category,
        "status": status,
        "assets": assets,
        "edges": edges,
        "message": message,
    }


def _client(session, name: str):
    return session.client(name)


def _safe_collect(category: str, collector, *args) -> tuple[list[dict], list[dict], dict]:
    try:
        assets, edges = collector(*args)
        return assets, edges, _tool_result(category, "ok", assets=len(assets), edges=len(edges))
    except (ClientError, BotoCoreError) as exc:
        return [], [], _tool_result(category, "error", message=str(exc)[:500])
    except Exception as exc:
        return [], [], _tool_result(category, "error", message=f"{type(exc).__name__}: {exc}"[:500])


def _arn_tail(arn: str) -> str:
    return arn.rsplit(":", 1)[-1].rsplit("/", 1)[-1] if arn else ""


def _lambda_arn_from_uri(uri: str) -> str | None:
    if not uri:
        return None
    match = re.search(r"(arn:aws[a-zA-Z-]*:lambda:[^:/]+:\d{12}:function:[A-Za-z0-9-_:.]+)", uri)
    return match.group(1) if match else None


def _resource_arns_from_state_machine(definition: str) -> set[str]:
    found: set[str] = set()
    try:
        payload = json.loads(definition)
    except Exception:
        return found

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"Resource", "QueueUrl", "TopicArn", "FunctionName", "TableName"} and isinstance(child, str):
                    found.add(child)
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)
    return found


# ---------------------------------------------------------------------------
# EC2
# ---------------------------------------------------------------------------

def get_ec2_assets(ec2_client, ssm_client) -> list[dict]:
    assets = []
    paginator = ec2_client.get_paginator("describe_instances")
    for page in paginator.paginate(
        Filters=[{"Name": "instance-state-name", "Values": ["running", "stopped"]}]
    ):
        for reservation in page.get("Reservations", []):
            for instance in reservation.get("Instances", []):
                instance_id = instance["InstanceId"]
                name = next(
                    (t["Value"] for t in instance.get("Tags", []) if t.get("Key") == "Name"),
                    instance_id,
                )
                platform = instance.get("Platform", "linux")
                ami_id = instance.get("ImageId", "")
                os_version = (
                    _ssm_os_version(ssm_client, instance_id)
                    or _ami_description(ec2_client, ami_id)
                    or "unknown"
                )
                components = [{"type": "os", "name": platform, "version": os_version}]
                components.extend(_ssm_installed_packages(ssm_client, instance_id))
                assets.append(_asset(
                    "ec2",
                    name,
                    instance_id,
                    components=components,
                    instance_id=instance_id,
                    ami_id=ami_id,
                    state=instance.get("State", {}).get("Name"),
                    vpc_id=instance.get("VpcId"),
                    subnet_id=instance.get("SubnetId"),
                    private_ip=instance.get("PrivateIpAddress"),
                    public_ip=instance.get("PublicIpAddress"),
                    security_groups=[sg.get("GroupId") for sg in instance.get("SecurityGroups", [])],
                ))
    return assets


def _ssm_os_version(ssm_client, instance_id: str) -> str | None:
    try:
        resp = ssm_client.describe_instance_information(
            Filters=[{"Key": "InstanceIds", "Values": [instance_id]}]
        )
        info = resp.get("InstanceInformationList", [])
        return info[0].get("PlatformVersion") if info else None
    except ClientError:
        return None


def _ami_description(ec2_client, ami_id: str) -> str | None:
    if not ami_id:
        return None
    try:
        resp = ec2_client.describe_images(ImageIds=[ami_id])
        images = resp.get("Images", [])
        return (images[0].get("Description") or images[0].get("Name")) if images else None
    except ClientError:
        return None


def _ssm_installed_packages(ssm_client, instance_id: str) -> list[dict]:
    entries: list[dict] = []
    next_token = None
    try:
        while True:
            kwargs = {
                "InstanceId": instance_id,
                "TypeName": "AWS:Application",
                "MaxResults": 50,
            }
            if next_token:
                kwargs["NextToken"] = next_token
            resp = ssm_client.list_inventory_entries(**kwargs)
            entries.extend(resp.get("Entries", []))
            next_token = resp.get("NextToken")
            if not next_token or len(entries) >= 1000:
                break
    except ClientError:
        return []
    return [
        {"type": "os_package", "name": e["Name"], "version": e.get("Version", "unknown")}
        for e in entries
        if e.get("Name")
    ]


# ---------------------------------------------------------------------------
# Lambda
# ---------------------------------------------------------------------------

def get_lambda_assets_and_edges(lambda_client) -> tuple[list[dict], list[dict]]:
    assets = []
    edges = []
    paginator = lambda_client.get_paginator("list_functions")
    for page in paginator.paginate():
        for fn in page.get("Functions", []):
            runtime = fn.get("Runtime", "unknown")
            package_type = fn.get("PackageType", "Zip")
            arn = fn["FunctionArn"]
            layers = [layer.get("Arn") for layer in fn.get("Layers", []) if layer.get("Arn")]
            components = [{"type": "runtime", "name": runtime, "version": _runtime_version(runtime)}]
            assets.append(_asset(
                "lambda",
                fn["FunctionName"],
                arn,
                components=components,
                function_arn=arn,
                runtime=runtime,
                package_type=package_type,
                role=fn.get("Role"),
                code_sha256=fn.get("CodeSha256"),
                layers=layers,
                vpc_config=fn.get("VpcConfig", {}),
            ))
            for layer in layers:
                edges.append(_edge(arn, layer, "uses_layer", source_type="lambda", target_type="lambda_layer"))

    try:
        event_paginator = lambda_client.get_paginator("list_event_source_mappings")
        for page in event_paginator.paginate():
            for mapping in page.get("EventSourceMappings", []):
                source_arn = mapping.get("EventSourceArn")
                target_arn = mapping.get("FunctionArn") or mapping.get("FunctionName")
                if source_arn and target_arn:
                    edges.append(_edge(source_arn, target_arn, "triggers", source_type="event_source", target_type="lambda", via="lambda_event_source_mapping"))
    except ClientError:
        pass

    return assets, edges


def _runtime_version(runtime: str) -> str:
    for prefix in ("python", "nodejs", "java", "dotnet", "ruby", "go"):
        if runtime.startswith(prefix):
            return runtime[len(prefix):].replace(".x", "")
    return runtime


# ---------------------------------------------------------------------------
# RDS
# ---------------------------------------------------------------------------

def get_rds_assets(rds_client) -> list[dict]:
    assets = []
    paginator = rds_client.get_paginator("describe_db_instances")
    for page in paginator.paginate():
        for db in page.get("DBInstances", []):
            engine = db.get("Engine", "unknown")
            version = db.get("EngineVersion", "unknown")
            assets.append(_asset(
                "rds",
                db.get("DBInstanceIdentifier", "unknown"),
                db.get("DBInstanceArn", db.get("DBInstanceIdentifier", "unknown")),
                components=[{"type": "db_engine", "name": engine, "version": version}],
                engine=engine,
                db_resource_id=db.get("DbiResourceId"),
                endpoint=(db.get("Endpoint") or {}).get("Address"),
                publicly_accessible=db.get("PubliclyAccessible"),
                storage_encrypted=db.get("StorageEncrypted"),
                vpc_security_groups=[sg.get("VpcSecurityGroupId") for sg in db.get("VpcSecurityGroups", [])],
            ))
    return assets


# ---------------------------------------------------------------------------
# API / event / container / data-plane resources
# ---------------------------------------------------------------------------

def get_apigateway_v2_assets_and_edges(apigw_client) -> tuple[list[dict], list[dict]]:
    assets, edges = [], []
    paginator = apigw_client.get_paginator("get_apis")
    for page in paginator.paginate():
        for api in page.get("Items", []):
            api_id = api.get("ApiId")
            api_arn = f"apigatewayv2:{api_id}"
            assets.append(_asset(
                "apigatewayv2",
                api.get("Name") or api_id,
                api_arn,
                protocol_type=api.get("ProtocolType"),
                api_endpoint=api.get("ApiEndpoint"),
            ))
            integrations: dict[str, dict] = {}
            try:
                integ_paginator = apigw_client.get_paginator("get_integrations")
                for integ_page in integ_paginator.paginate(ApiId=api_id):
                    for integ in integ_page.get("Items", []):
                        integrations[integ.get("IntegrationId")] = integ
            except ClientError:
                pass
            try:
                route_paginator = apigw_client.get_paginator("get_routes")
                for route_page in route_paginator.paginate(ApiId=api_id):
                    for route in route_page.get("Items", []):
                        target = route.get("Target", "")
                        integ_id = target.rsplit("/", 1)[-1] if "/" in target else target
                        integration = integrations.get(integ_id, {})
                        uri = integration.get("IntegrationUri", "")
                        lambda_arn = _lambda_arn_from_uri(uri)
                        if lambda_arn:
                            edges.append(_edge(api_arn, lambda_arn, "routes_to", source_type="apigatewayv2", target_type="lambda", via=route.get("RouteKey", "")))
                        elif uri:
                            edges.append(_edge(api_arn, uri, "routes_to", source_type="apigatewayv2", target_type="http", via=route.get("RouteKey", "")))
            except ClientError:
                pass
    return assets, edges


def get_apigateway_rest_assets_and_edges(apigw_client) -> tuple[list[dict], list[dict]]:
    assets, edges = [], []
    paginator = apigw_client.get_paginator("get_rest_apis")
    for page in paginator.paginate():
        for api in page.get("items", []):
            api_id = api.get("id")
            api_arn = f"apigateway:{api_id}"
            assets.append(_asset("apigateway", api.get("name") or api_id, api_arn, endpoint_configuration=api.get("endpointConfiguration", {})))
            try:
                resource_paginator = apigw_client.get_paginator("get_resources")
                for resource_page in resource_paginator.paginate(restApiId=api_id):
                    for resource in resource_page.get("items", []):
                        for method in (resource.get("resourceMethods") or {}).keys():
                            try:
                                integration = apigw_client.get_integration(restApiId=api_id, resourceId=resource["id"], httpMethod=method)
                            except ClientError:
                                continue
                            uri = integration.get("uri", "")
                            lambda_arn = _lambda_arn_from_uri(uri)
                            via = f"{method} {resource.get('path', '')}".strip()
                            if lambda_arn:
                                edges.append(_edge(api_arn, lambda_arn, "routes_to", source_type="apigateway", target_type="lambda", via=via))
                            elif uri:
                                edges.append(_edge(api_arn, uri, "routes_to", source_type="apigateway", target_type="http", via=via))
            except ClientError:
                pass
    return assets, edges


def get_elbv2_assets_and_edges(elb_client) -> tuple[list[dict], list[dict]]:
    assets, edges = [], []
    tg_by_lb: dict[str, list[dict]] = {}
    tg_paginator = elb_client.get_paginator("describe_target_groups")
    for page in tg_paginator.paginate():
        for tg in page.get("TargetGroups", []):
            for lb_arn in tg.get("LoadBalancerArns", []):
                tg_by_lb.setdefault(lb_arn, []).append(tg)
    lb_paginator = elb_client.get_paginator("describe_load_balancers")
    for page in lb_paginator.paginate():
        for lb in page.get("LoadBalancers", []):
            lb_arn = lb.get("LoadBalancerArn")
            assets.append(_asset(
                "load_balancer",
                lb.get("LoadBalancerName") or _arn_tail(lb_arn),
                lb_arn,
                scheme=lb.get("Scheme"),
                lb_type=lb.get("Type"),
                dns_name=lb.get("DNSName"),
            ))
            for tg in tg_by_lb.get(lb_arn, []):
                tg_arn = tg.get("TargetGroupArn")
                edges.append(_edge(lb_arn, tg_arn, "routes_to", source_type="load_balancer", target_type="target_group", via=tg.get("Protocol", "")))
                try:
                    health = elb_client.describe_target_health(TargetGroupArn=tg_arn)
                    for target in health.get("TargetHealthDescriptions", []):
                        target_id = target.get("Target", {}).get("Id")
                        if target_id:
                            edges.append(_edge(tg_arn, target_id, "targets", source_type="target_group", target_type=tg.get("TargetType", "")))
                except ClientError:
                    pass
    return assets, edges


def get_sqs_assets(sqs_client) -> list[dict]:
    assets = []
    urls = sqs_client.list_queues().get("QueueUrls", [])
    for url in urls:
        try:
            attrs = sqs_client.get_queue_attributes(QueueUrl=url, AttributeNames=["QueueArn", "KmsMasterKeyId"])
        except ClientError:
            attrs = {"Attributes": {}}
        queue_arn = attrs.get("Attributes", {}).get("QueueArn", url)
        assets.append(_asset(
            "sqs",
            url.rsplit("/", 1)[-1],
            queue_arn,
            queue_url=url,
            kms_key_id=attrs.get("Attributes", {}).get("KmsMasterKeyId"),
        ))
    return assets


def get_sns_assets_and_edges(sns_client) -> tuple[list[dict], list[dict]]:
    assets, edges = [], []
    paginator = sns_client.get_paginator("list_topics")
    for page in paginator.paginate():
        for topic in page.get("Topics", []):
            topic_arn = topic.get("TopicArn")
            assets.append(_asset("sns", _arn_tail(topic_arn), topic_arn))
            try:
                sub_paginator = sns_client.get_paginator("list_subscriptions_by_topic")
                for sub_page in sub_paginator.paginate(TopicArn=topic_arn):
                    for sub in sub_page.get("Subscriptions", []):
                        endpoint = sub.get("Endpoint")
                        protocol = sub.get("Protocol", "")
                        if endpoint:
                            edges.append(_edge(topic_arn, endpoint, "publishes_to", source_type="sns", target_type=protocol, via=protocol))
            except ClientError:
                pass
    return assets, edges


def get_eventbridge_assets_and_edges(events_client) -> tuple[list[dict], list[dict]]:
    assets, edges = [], []
    paginator = events_client.get_paginator("list_rules")
    for page in paginator.paginate():
        for rule in page.get("Rules", []):
            rule_arn = rule.get("Arn")
            assets.append(_asset("eventbridge_rule", rule.get("Name") or _arn_tail(rule_arn), rule_arn, state=rule.get("State"), schedule=rule.get("ScheduleExpression")))
            try:
                targets = events_client.list_targets_by_rule(Rule=rule["Name"], EventBusName=rule.get("EventBusName", "default"))
                for target in targets.get("Targets", []):
                    arn = target.get("Arn")
                    if arn:
                        edges.append(_edge(rule_arn, arn, "targets", source_type="eventbridge_rule", target_type="aws_resource", via=target.get("Id", "")))
            except ClientError:
                pass
    return assets, edges


def get_stepfunctions_assets_and_edges(sfn_client) -> tuple[list[dict], list[dict]]:
    assets, edges = [], []
    paginator = sfn_client.get_paginator("list_state_machines")
    for page in paginator.paginate():
        for sm in page.get("stateMachines", []):
            arn = sm.get("stateMachineArn")
            assets.append(_asset("step_function", sm.get("name") or _arn_tail(arn), arn, state_machine_type=sm.get("type")))
            try:
                desc = sfn_client.describe_state_machine(stateMachineArn=arn)
                for resource in _resource_arns_from_state_machine(desc.get("definition", "")):
                    edges.append(_edge(arn, resource, "orchestrates", source_type="step_function", target_type="aws_resource"))
            except ClientError:
                pass
    return assets, edges


def get_ecs_assets_and_edges(ecs_client) -> tuple[list[dict], list[dict]]:
    assets, edges = [], []
    cluster_paginator = ecs_client.get_paginator("list_clusters")
    for cluster_page in cluster_paginator.paginate():
        for cluster_arn in cluster_page.get("clusterArns", []):
            service_paginator = ecs_client.get_paginator("list_services")
            for service_page in service_paginator.paginate(cluster=cluster_arn):
                service_arns = service_page.get("serviceArns", [])
                if not service_arns:
                    continue
                for i in range(0, len(service_arns), 10):
                    desc = ecs_client.describe_services(cluster=cluster_arn, services=service_arns[i:i + 10])
                    for svc in desc.get("services", []):
                        service_arn = svc.get("serviceArn")
                        task_def_arn = svc.get("taskDefinition")
                        components = []
                        if task_def_arn:
                            try:
                                task_def = ecs_client.describe_task_definition(taskDefinition=task_def_arn).get("taskDefinition", {})
                                for container in task_def.get("containerDefinitions", []):
                                    image = container.get("image")
                                    if image:
                                        components.append({"type": "container_image", "name": image, "version": image.rsplit(":", 1)[-1] if ":" in image else "unknown"})
                            except ClientError:
                                pass
                        assets.append(_asset(
                            "ecs_service",
                            svc.get("serviceName") or _arn_tail(service_arn),
                            service_arn,
                            components=components,
                            cluster_arn=cluster_arn,
                            task_definition=task_def_arn,
                            desired_count=svc.get("desiredCount"),
                            running_count=svc.get("runningCount"),
                        ))
                        if task_def_arn:
                            edges.append(_edge(service_arn, task_def_arn, "runs_task_definition", source_type="ecs_service", target_type="ecs_task_definition"))
                        for lb in svc.get("loadBalancers", []):
                            tg = lb.get("targetGroupArn")
                            if tg:
                                edges.append(_edge(tg, service_arn, "targets", source_type="target_group", target_type="ecs_service"))
    return assets, edges


def get_ecr_assets(ecr_client) -> list[dict]:
    assets = []
    paginator = ecr_client.get_paginator("describe_repositories")
    for page in paginator.paginate():
        for repo in page.get("repositories", []):
            repo_arn = repo.get("repositoryArn")
            assets.append(_asset("ecr_repository", repo.get("repositoryName") or _arn_tail(repo_arn), repo_arn, repository_uri=repo.get("repositoryUri"), scan_on_push=(repo.get("imageScanningConfiguration") or {}).get("scanOnPush")))
    return assets


def get_dynamodb_assets(dynamodb_client) -> list[dict]:
    assets = []
    paginator = dynamodb_client.get_paginator("list_tables")
    for page in paginator.paginate():
        for table_name in page.get("TableNames", []):
            try:
                table = dynamodb_client.describe_table(TableName=table_name).get("Table", {})
            except ClientError:
                table = {"TableName": table_name}
            assets.append(_asset("dynamodb", table_name, table.get("TableArn", table_name), billing_mode=(table.get("BillingModeSummary") or {}).get("BillingMode"), table_status=table.get("TableStatus")))
    return assets


def get_s3_assets(s3_client, region: str) -> list[dict]:
    assets = []
    for bucket in s3_client.list_buckets().get("Buckets", []):
        name = bucket.get("Name")
        try:
            location = s3_client.get_bucket_location(Bucket=name).get("LocationConstraint") or "us-east-1"
        except ClientError:
            location = "unknown"
        if location not in {region, "unknown"}:
            continue
        assets.append(_asset("s3", name, f"arn:aws:s3:::{name}", region=location))
    return assets


def get_secrets_assets(secrets_client) -> list[dict]:
    assets = []
    paginator = secrets_client.get_paginator("list_secrets")
    for page in paginator.paginate():
        for secret in page.get("SecretList", []):
            assets.append(_asset("secretsmanager", secret.get("Name") or _arn_tail(secret.get("ARN", "")), secret.get("ARN", ""), last_changed_date=str(secret.get("LastChangedDate") or "")))
    return assets


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------

def inventory_full(region: str, session=None) -> dict:
    if session is None:
        import boto3
        session = boto3.Session(region_name=region)

    assets: list[dict] = []
    edges: list[dict] = []
    tool_results: list[dict] = []

    def add(category: str, collector, *clients):
        found_assets, found_edges, result = _safe_collect(category, collector, *clients)
        assets.extend(found_assets)
        edges.extend(found_edges)
        tool_results.append(result)
        print(f"[inventory] {category}: {result['status']} assets={result['assets']} edges={result['edges']}")

    add("ec2", lambda ec2, ssm: (get_ec2_assets(ec2, ssm), []), _client(session, "ec2"), _client(session, "ssm"))
    add("lambda", get_lambda_assets_and_edges, _client(session, "lambda"))
    add("rds", lambda rds: (get_rds_assets(rds), []), _client(session, "rds"))
    add("apigatewayv2", get_apigateway_v2_assets_and_edges, _client(session, "apigatewayv2"))
    add("apigateway", get_apigateway_rest_assets_and_edges, _client(session, "apigateway"))
    add("elbv2", get_elbv2_assets_and_edges, _client(session, "elbv2"))
    add("sqs", lambda sqs: (get_sqs_assets(sqs), []), _client(session, "sqs"))
    add("sns", get_sns_assets_and_edges, _client(session, "sns"))
    add("eventbridge", get_eventbridge_assets_and_edges, _client(session, "events"))
    add("stepfunctions", get_stepfunctions_assets_and_edges, _client(session, "stepfunctions"))
    add("ecs", get_ecs_assets_and_edges, _client(session, "ecs"))
    add("ecr", lambda ecr: (get_ecr_assets(ecr), []), _client(session, "ecr"))
    add("dynamodb", lambda dynamodb: (get_dynamodb_assets(dynamodb), []), _client(session, "dynamodb"))
    add("s3", lambda s3: (get_s3_assets(s3, region), []), _client(session, "s3"))
    add("secretsmanager", lambda secrets: (get_secrets_assets(secrets), []), _client(session, "secretsmanager"))

    return {
        "assets": assets,
        "dependencies": edges,
        "tool_results": tool_results,
        "summary": {
            "assets": len(assets),
            "dependencies": len(edges),
            "tools_ok": sum(1 for r in tool_results if r["status"] == "ok"),
            "tools_error": sum(1 for r in tool_results if r["status"] == "error"),
        },
    }


def inventory_all(region: str, session=None) -> list[dict]:
    return inventory_full(region, session=session)["assets"]
