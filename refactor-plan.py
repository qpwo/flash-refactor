#!/usr/bin/env python
"""
make a plan, then rewrite the entire files according to the plan
"""

import argparse
from datetime import datetime
import os
import os
from pathlib import Path
import re
import re

import dotenv
from google import genai
from google.genai.types import GenerateContentConfig
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.styles import Style
from termcolor import cprint

dotenv.load_dotenv()  # Load environment variables
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"], http_options={"api_version": "v1alpha"})


def stream_print(response) -> str:
    """Helper function to print a streamed response from the model."""
    coll = []
    for chunk in response:
        print(chunk.text, end="", flush=True)
        coll.append(chunk.text or "")
    print()  # Newline after the complete response
    return "".join(coll)


def line_join(*parts: str):
    "puts exactly one newline between each part"
    return "\n".join(line.strip("\n") for line in parts)


def tagged(tag: str, *children: str, **attrs):
    "xml formatting with exact one newline between each part"
    attr_str = ""
    if attrs:
        attr_str = " " + " ".join(f'{k}="{v}"' for k, v in attrs.items())
    return line_join(f"<{tag}{attr_str}>", *children, f"</{tag}>")


def between_tags(tag: str, text: str):
    "extracts text between tags"
    start_tag = f"<{tag}>"
    end_tag = f"</{tag}>"
    start = text.index(start_tag) + len(start_tag)
    end = text.index(end_tag)
    return text[start:end]


# model_name = "gemini-2.0-flash-exp"
model_name = "gemini-2.0-flash-thinking-exp-01-21"
parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
parser.add_argument("include_files", nargs="+", help="One or more file paths to include for rewriting.")
parser.add_argument(
    "-c",
    "--context",
    action="append",
    dest="context_files",
    default=[],
    help="Additional files to provide as context (will not be rewritten)",
)
parser.add_argument("-y", "--yes", action="store_true", dest="skip_clarifications", help="Skip the clarifications")


args = parser.parse_args()
print(f"{args=}")

savedir = Path("~/.gemini").expanduser()
savedir.mkdir(exist_ok=True)


def get_timestamp():
    """Returns a timestamp string in the format 'yyyy-mm-dd-hh-mm-ss'."""
    now = datetime.now()
    return now.strftime("%Y-%m-%d-%H-%M-%S")


def multiline_input(p) -> str:
    bindings = KeyBindings()

    @bindings.add(Keys.ControlD)
    def _(event):
        text = event.current_buffer.text
        event.app.exit(result=text)

    style = Style.from_dict(
        {
            # Style for the prompt
            "prompt": "fg:ansimagenta",
            # Style for the input text
            "": "fg:ansired",  # Default style for input
        }
    )

    history_file = os.path.expanduser("~/.flash-history.txt")
    session = PromptSession(
        multiline=True,
        key_bindings=bindings,
        history=FileHistory(history_file),
        style=style,
    )

    try:
        text = session.prompt([("class:prompt", f"{p} (press Ctrl+D to finish or Ctrl+C to exit):\n")], style=style)
    except KeyboardInterrupt:
        print("\nadios\n")
        import sys

        sys.exit(0)
    text = text.strip()
    print("got it")
    print(f"{text=}")

    session.history.store_string(text)
    return text


change_request = multiline_input("What to change?")
last_word = change_request.split()[-1]
if last_word.lower() == "yes":
    change_request = change_request[:-3].strip()
    args.skip_clarifications = True
if last_word.lower() == "y":
    change_request = change_request[:-3].strip()
    args.skip_clarifications = True


with open(savedir / "prompt_history.txt", "a") as f:
    f.write(f"---\n{get_timestamp()}\nPrompt:\n{change_request}\n---\n")

# ------------------------------ GENERATE PLAN --------------------------------

context_section = tagged(
    "context-files",
    tagged("note", "These files are included for context but do not need to be modified."),
    *[tagged("context-file", open(p).read(), name=p) for p in args.context_files],
)

rewrite_section = tagged(
    "files-to-modify",
    tagged("note", "These files might need to be modified."),
    *[tagged("current-file", open(p).read(), name=p) for p in args.include_files],
)

prompt1 = line_join(
    tagged("change-request", change_request),
    tagged("context-files", context_section),
    tagged("files-to-modify", rewrite_section),
    tagged("change-request-repeated", change_request),
)


sys1 = tagged(
    "system-instruction",
    f"""Write a <b>short<b/> plan for the requested code change. Do not write any code.
Just write a <b>short<b/> plan in precise language, and briefly restate the objective in your own terms.
Only mention tasks that still need to be done; don't mention tasks that are already complete.
Mention which of the provided files (if any) you <b>won't<b/> need to modify. Ignore unprovided files.
<b>Think as long as you need before you begin.<b/>
Please exclusively use XML for formatting to keep the parser happy.""",
)
if False:
    sys1 = line_join(
        sys1,
        tagged(
            "output-template",
            tagged(
                "response",
                tagged("thinking", "make sure"),
                tagged("thinking", "you always think out loud before you answer!"),
                tagged("thinking", "Always think for at least 3 paragraphs!"),
                tagged(
                    "plan",
                    tagged("task", "do this in file_1.ext"),
                    tagged("task", "do that in file_1.ext"),
                    tagged("task", "change this in file_2.ext"),
                    tagged("task", "change that in file_3.ext"),
                ),
            ),
        ),
    )


print("Generating plan...")
plan_response = stream_print(
    client.models.generate_content_stream(
        contents=prompt1,
        model="gemini-2.0-flash-thinking-exp-01-21",
        config=GenerateContentConfig(
            temperature=0.95,
            max_output_tokens=20_000,
            system_instruction=sys1,
        ),
    )
)

print("\n")
plan = between_tags("plan", plan_response)
cprint(plan + "\n", "green", attrs=["bold"])

# ------------------------------ MODIFY FILES --------------------------------


sys2 = tagged(
    "system-instruction",
    f"""You are an expert code rewriting assistant.
Your task is to rewrite the content of files according to user instructions.
After you are done rewriting all the requested files, summarize <b>what you actually did</b>.
For each file you rewrite, wrap the complete updated content in <updated-file name="filename.ext">...</updated-file> tags.
You have already generated a plan, it is included here. Follow this plan carefully.
Also abide by the user's clarifications if there are any.
Output the <b>entire</b> updated content of each modified file, not just the changes.
You may output the files in whatever order you prefer.
If you don't need to modify a file, then don't output it!
<b>Think as long as you need before writing each file.</b>
Please exclusively use XML for formatting to keep the parser happy.""",
)
if False:
    sys2 = line_join(
        sys2,
        tagged(
            "output-template",
            tagged(
                "response",
                tagged("thinking", "make sure"),
                tagged("thinking", "you always think out loud before you answer!"),
                tagged("thinking", "Always think for at least 3 paragraphs!"),
                tagged("updated-file", "only use this tag for the actual file contents", name="filename_1.ext"),
                tagged("thinking", "dont forget"),
                tagged("thinking", "to think before"),
                tagged("thinking", "you write code"),
                tagged("updated-file", "only use this tag for the actual file contents", name="filename_2.ext"),
                tagged(
                    "change-summary",
                    tagged("li", "I did this in file_1.ext"),
                    tagged("li", "I did that in file_2.ext"),
                ),
            ),
        ),
    )

prompt2 = line_join(prompt1, tagged("generated-plan", plan_response))

if args.skip_clarifications:
    clarifications = "None."
else:
    clarifications = multiline_input("Any clarifications?") or "None."

prompt2 = line_join(prompt2, tagged("clarifications", clarifications))

full_response = stream_print(
    client.models.generate_content_stream(
        contents=prompt2,
        model="gemini-2.0-flash-thinking-exp-01-21",
        config=GenerateContentConfig(
            temperature=0.95,
            max_output_tokens=60_000,
            system_instruction=sys2,
        ),
    )
)
print("\n")
# ------------------------------ SAVE FILES --------------------------------

# Regular expression to find file tags and their content
file_pattern = re.compile(r'<updated-file name="([^"]+)">(.*?)</updated-file>', re.DOTALL)

# Find and process all file matches in the response
modified_files = []
for match in file_pattern.finditer(full_response):
    filename = match.group(1)
    new_content = match.group(2).strip()

    # Verify the file is in our include_files list
    if filename not in args.include_files:
        print(f"Warning: Model attempted to modify {filename} which wasn't in the include_files list. Skipping.")
        continue

    # Write new content
    with open(filename, "w") as f:
        f.write(new_content)

    modified_files.append(filename)
    print(f"Updated {filename}")
