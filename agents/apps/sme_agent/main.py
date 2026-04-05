from __future__ import annotations

from dotenv import load_dotenv

from bedrock_agentcore import BedrockAgentCoreApp

from agentic_solution.services.sme import build_runtime

load_dotenv()

app = BedrockAgentCoreApp()
runtime = build_runtime()


@app.entrypoint
def invoke(payload: dict, context=None) -> dict:
    return runtime.handle(payload)


if __name__ == "__main__":
    app.run()
