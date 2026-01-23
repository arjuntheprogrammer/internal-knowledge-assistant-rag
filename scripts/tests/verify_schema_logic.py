
import json
import os
import sys

# Mocking the necessary parts to test the logic


class LLMOutput:
    @staticmethod
    def model_json_schema():
        return {
            "title": "LLMOutput",
            "type": "object",
            "properties": {
                "answer_md": {"type": "string"},
                "intent": {"enum": ["casual", "rag"]},
            }
        }


def test_schema_replacement():
    prompt_path = "/Users/arjungupta/Development/extra/internal-knowledge-assistant/prompts/output_schema.md"
    with open(prompt_path, "r") as f:
        prompt_text = f.read()

    schema_json = json.dumps(LLMOutput.model_json_schema(), indent=2)
    schema_instr = prompt_text.replace("{{SCHEMA}}", schema_json)

    if "{{SCHEMA}}" in prompt_text:
        print("SUCCESS: {{SCHEMA}} found in prompt text.")
    else:
        print("FAILURE: {{SCHEMA}} NOT found in prompt text.")

    if schema_json in schema_instr:
        print("SUCCESS: Dynamic schema successfully injected.")
    else:
        print("FAILURE: Dynamic schema NOT injected.")


if __name__ == "__main__":
    test_schema_replacement()
