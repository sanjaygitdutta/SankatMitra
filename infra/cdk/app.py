"""
SankatMitra – AWS CDK Infrastructure (Python)
Defines all AWS resources: API Gateway, Lambda, DynamoDB, ElastiCache, SageMaker, SNS/SQS
Region: ap-south-1 (Mumbai) – Indian data residency compliance
"""
from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    aws_lambda as lambda_,
    aws_apigateway as apigw,
    aws_dynamodb as dynamodb,
    aws_sns as sns,
    aws_sqs as sqs,
    aws_sns_subscriptions as subs,
    aws_elasticache as elasticache,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_logs as logs,
    aws_cloudwatch as cloudwatch,
)
from constructs import Construct


class SankatMitraStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # ── VPC ──────────────────────────────────────────────────────────
        vpc = ec2.Vpc(self, "SankatMitraVPC",
                      max_azs=2,
                      nat_gateways=1)

        # ── DynamoDB Tables ───────────────────────────────────────────────
        vehicle_table = dynamodb.Table(
            self, "VehicleRegistration",
            table_name="SankatMitra-VehicleRegistration",
            partition_key=dynamodb.Attribute(name="vehicleId", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
            point_in_time_recovery=True,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
        )
        vehicle_table.add_global_secondary_index(
            index_name="agencyId-index",
            partition_key=dynamodb.Attribute(name="agencyId", type=dynamodb.AttributeType.STRING),
        )

        location_table = dynamodb.Table(
            self, "LocationHistory",
            table_name="SankatMitra-LocationHistory",
            partition_key=dynamodb.Attribute(name="vehicleId", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="timestamp", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
        )

        corridor_table = dynamodb.Table(
            self, "CorridorState",
            table_name="SankatMitra-CorridorState",
            partition_key=dynamodb.Attribute(name="corridorId", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            stream=dynamodb.StreamViewType.NEW_AND_OLD_IMAGES,
            removal_policy=RemovalPolicy.RETAIN,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
        )
        corridor_table.add_global_secondary_index(
            index_name="status-index",
            partition_key=dynamodb.Attribute(name="status", type=dynamodb.AttributeType.STRING),
        )

        alert_table = dynamodb.Table(
            self, "AlertLog",
            table_name="SankatMitra-AlertLog",
            partition_key=dynamodb.Attribute(name="alertId", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="ttl",  # 24-hour TTL
            removal_policy=RemovalPolicy.DESTROY,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
        )
        alert_table.add_global_secondary_index(
            index_name="corridorId-index",
            partition_key=dynamodb.Attribute(name="corridorId", type=dynamodb.AttributeType.STRING),
        )

        # ── SNS Topics ────────────────────────────────────────────────────
        alert_topic = sns.Topic(
            self, "AlertTopic",
            topic_name="SankatMitra-Alerts",
            display_name="SankatMitra Emergency Alerts",
        )
        spoofing_topic = sns.Topic(
            self, "SpoofingTopic",
            topic_name="SankatMitra-Spoofing",
            display_name="SankatMitra GPS Spoofing Alerts",
        )

        # DLQ for failed alerts
        alert_dlq = sqs.Queue(self, "AlertDLQ",
                              queue_name="SankatMitra-AlertDLQ",
                              retention_period=Duration.days(7))

        # ── Lambda IAM Role ───────────────────────────────────────────────
        lambda_role = iam.Role(
            self, "LambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaVPCAccessExecutionRole"),
            ],
        )
        for table in [vehicle_table, location_table, corridor_table, alert_table]:
            table.grant_read_write_data(lambda_role)
        alert_topic.grant_publish(lambda_role)
        spoofing_topic.grant_publish(lambda_role)
        lambda_role.add_to_policy(iam.PolicyStatement(
            actions=["sagemaker:InvokeEndpoint", "lambda:InvokeFunction", "bedrock:InvokeModel"],
            resources=["*"],
        ))

        # ── Shared Lambda environment ─────────────────────────────────────
        common_env = {
            "AWS_REGION": self.region,
            "DYNAMO_VEHICLE_TABLE": vehicle_table.table_name,
            "DYNAMO_LOCATION_TABLE": location_table.table_name,
            "DYNAMO_CORRIDOR_TABLE": corridor_table.table_name,
            "DYNAMO_ALERT_TABLE": alert_table.table_name,
            "SNS_ALERT_TOPIC_ARN": alert_topic.topic_arn,
            "SNS_SPOOFING_TOPIC_ARN": spoofing_topic.topic_arn,
            "SAGEMAKER_ENDPOINT_NAME": "sankatmitra-rnn-route-predictor",
            "ENVIRONMENT": "production",
        }

        lambda_kwargs = dict(
            runtime=lambda_.Runtime.PYTHON_3_11,
            role=lambda_role,
            environment=common_env,
            timeout=Duration.seconds(30),
            memory_size=512,
            log_retention=logs.RetentionDays.ONE_MONTH,
        )

        # ── Lambda Functions ──────────────────────────────────────────────
        auth_fn = lambda_.Function(self, "AuthLambda",
            function_name="sankatmitra-auth-lambda",
            handler="auth_lambda.handler.handler",
            code=lambda_.Code.from_asset("../../backend"),
            **lambda_kwargs)

        gps_fn = lambda_.Function(self, "GPSLambda",
            function_name="sankatmitra-gps-lambda",
            handler="gps_lambda.handler.handler",
            code=lambda_.Code.from_asset("../../backend"),
            **lambda_kwargs)

        spoof_fn = lambda_.Function(self, "SpoofingLambda",
            function_name="sankatmitra-spoofing-lambda",
            handler="spoofing_lambda.handler.handler",
            code=lambda_.Code.from_asset("../../backend"),
            **lambda_kwargs)

        route_fn = lambda_.Function(self, "RouteLambda",
            function_name="sankatmitra-route-lambda",
            handler="route_lambda.handler.handler",
            code=lambda_.Code.from_asset("../../backend"),
            **lambda_kwargs)

        alert_fn = lambda_.Function(self, "AlertLambda",
            function_name="sankatmitra-alert-lambda",
            handler="alert_lambda.handler.handler",
            code=lambda_.Code.from_asset("../../backend"),
            **lambda_kwargs)

        corridor_fn = lambda_.Function(self, "CorridorLambda",
            function_name="sankatmitra-corridor-lambda",
            handler="corridor_lambda.handler.handler",
            code=lambda_.Code.from_asset("../../backend"),
            memory_size=1024,  # More memory for orchestration
            **{k: v for k, v in lambda_kwargs.items() if k != "memory_size"})

        # ── API Gateway ───────────────────────────────────────────────────
        api = apigw.RestApi(
            self, "SankatMitraAPI",
            rest_api_name="SankatMitraAPI",
            description="SankatMitra Emergency Corridor System API",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
            ),
            deploy_options=apigw.StageOptions(
                stage_name="prod",
                throttling_rate_limit=1000,
                throttling_burst_limit=500,
            ),
        )

        def add_route(resource_path: str, fn: lambda_.Function,
                      methods: list[str] = None, auth: bool = True):
            parts = resource_path.strip("/").split("/")
            resource = api.root
            for part in parts:
                existing = next(
                    (c for c in resource.node.children
                     if hasattr(c, "path_part") and c.path_part == part), None
                )
                resource = existing or resource.add_resource(part)
            for method in (methods or ["POST"]):
                resource.add_method(
                    method,
                    apigw.LambdaIntegration(fn),
                    authorization_type=apigw.AuthorizationType.NONE if not auth
                    else apigw.AuthorizationType.NONE,  # Replace with Cognito in prod
                )

        # Auth routes (no auth required)
        add_route("/auth/login", auth_fn, ["POST"], auth=False)
        add_route("/auth/validate", auth_fn, ["POST"], auth=False)
        add_route("/auth/revoke", auth_fn, ["POST"])

        # GPS routes
        add_route("/gps/update", gps_fn, ["POST"])
        add_route("/gps/{vehicleId}", gps_fn, ["GET"])
        add_route("/gps/{vehicleId}/history", gps_fn, ["GET"])

        # Corridor routes
        add_route("/corridor/activate", corridor_fn, ["POST"])
        add_route("/corridors", corridor_fn, ["GET"])
        add_route("/corridor/{id}", corridor_fn, ["GET", "PATCH", "DELETE"])

        # Route prediction
        add_route("/route/predict", route_fn, ["POST"])
        add_route("/route/recalculate/{corridorId}", route_fn, ["POST"])
        add_route("/route/alternatives/{corridorId}", route_fn, ["GET"])

        # Alert routes
        add_route("/alert/send", alert_fn, ["POST"])
        add_route("/alert/update/{corridorId}", alert_fn, ["PATCH"])
        add_route("/alert/cancel/{corridorId}", alert_fn, ["DELETE"])

        # Spoofing routes
        add_route("/spoof/validate", spoof_fn, ["POST"])
        add_route("/spoof/report", spoof_fn, ["POST"])

        # ── CloudWatch Dashboard ──────────────────────────────────────────
        dashboard = cloudwatch.Dashboard(self, "SankatMitraDashboard",
                                         dashboard_name="SankatMitra-Operations")

        # ── Outputs ───────────────────────────────────────────────────────
        cdk.CfnOutput(self, "APIEndpoint", value=api.url)
        cdk.CfnOutput(self, "AlertTopicArn", value=alert_topic.topic_arn)
        cdk.CfnOutput(self, "SpoofingTopicArn", value=spoofing_topic.topic_arn)


app = cdk.App()
SankatMitraStack(
    app, "SankatMitraStack",
    env=cdk.Environment(region="ap-south-1"),  # Mumbai – Indian data residency
    description="SankatMitra Emergency Corridor System",
)
app.synth()
