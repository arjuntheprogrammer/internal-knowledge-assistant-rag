
from llama_index.core import PromptTemplate
import json


def test_prompt_template_with_json():
    schema = {
        "type": "object",
        "properties": {"foo": {"type": "string"}}
    }
    schema_json = json.dumps(schema, indent=2)

    prompt_text = "Context: {context_str}\n\nSchema:\n" + schema_json

    try:
        template = PromptTemplate(prompt_text)
        print("Template variables:", template.template_vars)
        # Try to format it
        formatted = template.format(context_str="Some context")
        print("Formatted successfully!")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    test_prompt_template_with_json()
