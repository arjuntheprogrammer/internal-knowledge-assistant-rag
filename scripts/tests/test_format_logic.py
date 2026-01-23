
import json


def test_string_format_with_json():
    schema = {
        "type": "object",
        "properties": {"foo": {"type": "string"}}
    }
    schema_json = json.dumps(schema, indent=2)

    # This will FAIL
    prompt_text = "Context: {context_str}\n\nSchema:\n" + schema_json
    try:
        print("Attempting naive format...")
        prompt_text.format(context_str="Some context")
    except KeyError as e:
        print(f"Caught expected KeyError: {e}")

    # This will WORK
    doubled_json = schema_json.replace("{", "{{").replace("}", "}}")
    prompt_text_ok = "Context: {context_str}\n\nSchema:\n" + doubled_json
    try:
        print("Attempting format with doubled braces...")
        formatted = prompt_text_ok.format(context_str="Some context")
        print("Success!")
        # print(formatted)
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    test_string_format_with_json()
