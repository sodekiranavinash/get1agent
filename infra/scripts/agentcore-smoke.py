#!/usr/bin/env python3
"""Direct Bedrock AgentCore Code Interpreter smoke test.

Mirrors what the code-interpreter Lambda does (start session -> invoke code ->
stop session) so the real error is visible without CloudWatch.

Run with the bundled boto3/botocore (matches the Lambda):
    PYTHONPATH=backend/services/code-interpreter/dist \
      CODE_INTERPRETER_REGION=ap-south-1 \
      python3 infra/scripts/agentcore-smoke.py

Env:
    CODE_INTERPRETER_REGION                default ap-south-1
    CODE_INTERPRETER_IDENTIFIER            default aws.codeinterpreter.v1
    CODE_INTERPRETER_SESSION_TIMEOUT_SECONDS default 900
    CODE                                   default 'print("Jai Ganesha")'
"""

from __future__ import annotations

import json
import os
import uuid

import boto3
from botocore.config import Config

REGION = (
    os.environ.get("CODE_INTERPRETER_REGION")
    or os.environ.get("AWS_REGION")
    or "ap-south-1"
)
IDENTIFIER = os.environ.get("CODE_INTERPRETER_IDENTIFIER", "aws.codeinterpreter.v1")
TTL = int(os.environ.get("CODE_INTERPRETER_SESSION_TIMEOUT_SECONDS", "900"))
CODE = os.environ.get("CODE", 'print("Jai Ganesha")')


def main() -> int:
    print(f"region={REGION} identifier={IDENTIFIER} boto3={boto3.__version__}")
    client = boto3.client(
        "bedrock-agentcore",
        region_name=REGION,
        config=Config(
            connect_timeout=10,
            read_timeout=60,
            retries={"max_attempts": 2, "mode": "standard"},
        ),
    )

    session_id = None
    try:
        response = client.start_code_interpreter_session(
            codeInterpreterIdentifier=IDENTIFIER,
            name="smoke-" + uuid.uuid4().hex[:8],
            sessionTimeoutSeconds=TTL,
            clientToken=str(uuid.uuid4()),
        )
        session_id = response["sessionId"]
        print("sessionId:", session_id)

        result = client.invoke_code_interpreter(
            codeInterpreterIdentifier=IDENTIFIER,
            sessionId=session_id,
            name="executeCode",
            arguments={"language": "python", "code": CODE},
        )
        for event in result.get("stream", []):
            print("event:", json.dumps(event, default=str))
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {type(exc).__name__}: {exc}")
        aws_response = getattr(exc, "response", None)
        if aws_response:
            print("aws:", json.dumps(aws_response, default=str))
        return 1
    finally:
        if session_id:
            try:
                client.stop_code_interpreter_session(
                    codeInterpreterIdentifier=IDENTIFIER, sessionId=session_id
                )
                print("stopped session")
            except Exception as exc:  # noqa: BLE001
                print(f"stop failed: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
