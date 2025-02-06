from collections import defaultdict
import os
import sys
import re  # Import the regex module

import dotenv
import google.generativeai as genai
from google.generativeai.generative_models import GenerativeModel
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.styles import Style

dotenv.load_dotenv("/home/ubuntu/git/newthing/server/.env")  # Load environment variables
genai.configure(api_key=os.environ["GEMINI_API_KEY"])


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


def read_file_content(file_path: str) -> str:
    with open(file_path, "r") as f:
        return f.read()


ChunkId = str  # file_path::chunk_number
Chunk = str
Chunks = dict[str, Chunk]  # chunk_id -> chunk_content


def chunk_code(file_path: str, file_content: str) -> Chunks:
    """Chunks the code based on indentation, with a minimum chunk size."""
    min_chunk_size = 5

    was_indented = False
    chunks: Chunks = {}
    c: list[str] = []
    line_number = 0

    for line in file_content.splitlines():
        line_number += 1
        c.append(line)
        is_indented = line.strip() and (line.startswith(" ") or line.startswith("\t"))
        if was_indented and not is_indented and len(c) >= min_chunk_size:
            chunk_id = f"{file_path}::{10 * (1 + len(chunks))}"
            chunks[chunk_id] = "\n".join(c)
            c = []
        was_indented = is_indented

    # Add the last chunk if it exists
    if c:
        chunk_id = f"{file_path}::{10 * (1 + len(chunks))}"
        chunks[chunk_id] = "\n".join(c)

    return chunks


def format_chunks_xml(chunks: Chunks) -> str:
    """Formats code chunks into XML with chunk-content tags."""
    return "\n\n".join(f'<chunk-content id="{chunk_id}">\n{chunk_content}\n</chunk-content>' for chunk_id, chunk_content in chunks.items())


def stream_print(response) -> str:
    """Helper function to print a streamed response from the model."""
    coll = []
    for chunk in response:
        print(chunk.text, end="", flush=True)
        coll.append(chunk.text)
    print()  # Newline after the complete response
    return "".join(coll)


def identify_relevant_chunks(model: GenerativeModel, chunks: Chunks, requested_change: str) -> list[ChunkId]:
    """Asks the AI to identify relevant chunks that need modification using regex."""
    prompt = f"""I have the following code chunks.  Please think step by step and identify which chunks need to be changed to implement the following: "{requested_change}".  Only list the chunks that require changes.  Think carefully about it for a long time before you answer.

{format_chunks_xml(chunks)}

Output your final answer in XML like this:
<final-answer>
<chunk-ref id="..."/>
<chunk-ref id="..."/>
</final-answer>

Again, the requested change is: "{requested_change}"."""
    print("Identifying Relevant Chunks Prompt:")
    print(prompt)
    print("Identifying Relevant Chunks Response:")
    full_response_text = stream_print(model.generate_content(prompt, stream=True))

    chunk_ids = []
    final_answer_match = re.search(r"<final-answer>(.*?)</final-answer>", full_response_text, re.DOTALL)
    if final_answer_match:
        final_answer_xml = final_answer_match.group(1)
        chunk_ref_matches = re.finditer(r'<chunk-ref id="([^"]*)"/>', final_answer_xml)
        for match in chunk_ref_matches:
            chunk_id = match.group(1)
            if chunk_id:
                chunk_ids.append(chunk_id)
    return chunk_ids


def rewrite_chunks(model: GenerativeModel, chunks: Chunks, requested_change: str) -> Chunks:
    """Asks the AI to rewrite the specified chunks, generating all at once, using regex."""

    prompt = f"""Rewrite the following code chunks to implement the change: "{requested_change}".
Think carefully about it step-by-step before you answer.

{format_chunks_xml(chunks)}

Output the updated code within XML tags, like this:

<final-answer>
<rewritten-chunk id="[chunk_id_1]">
...
</rewritten-chunk>
<rewritten-chunk id="[chunk_id_2]">
...
</rewritten-chunk>
...
</final-answer>

Again, the requested change is: "{requested_change}"."""
    print("Rewrite Chunks Prompt:")
    print(prompt)

    response = model.generate_content(prompt, stream=True)
    print("Rewrite Chunks Response:")
    full_response_text = stream_print(response)

    rewritten_chunks = {}
    final_answer_match = re.search(r"<final-answer>(.*?)</final-answer>", full_response_text, re.DOTALL)
    if final_answer_match:
        final_answer_xml = final_answer_match.group(1)
        rewritten_chunk_matches = re.finditer(r'<rewritten-chunk id="([^"]*)">\n(.*?)\n</rewritten-chunk>', final_answer_xml, re.DOTALL)
        for match in rewritten_chunk_matches:
            chunk_id = match.group(1)
            rewritten_content = match.group(2)
            if chunk_id:
                rewritten_chunks[chunk_id] = rewritten_content

    return rewritten_chunks


def apply_changes(original_chunks: Chunks, rewritten_chunks: Chunks) -> None:
    """Applies the rewritten chunks back to the original files."""

    # Merge original and rewritten chunks, with rewritten taking precedence
    all_chunks = {**original_chunks, **rewritten_chunks}
    sorted_chunk_ids = sorted(all_chunks.keys(), key=lambda chunk_id: int(chunk_id.split("::")[1]))
    new_full_content = defaultdict(list)
    for chunk_id in sorted_chunk_ids:
        file_path = chunk_id.split("::")[0]
        new_full_content[file_path].append(all_chunks[chunk_id])
    for file_path, new_chunks in new_full_content.items():
        with open(file_path, "w") as f:
            f.write("\n".join(new_chunks))


if __name__ == "__main__":
    # main()
    # def main() -> None:
    """Main function to orchestrate the code refactoring process."""
    if len(sys.argv) < 2:
        raise Exception("Usage: python refactor.py <file1> <file2> ...")

    file_paths = sys.argv[1:]
    requested_change = multiline_input("Enter the desired code change")

    original_chunks = {}
    for file_path in file_paths:
        file_content = read_file_content(file_path)
        chunks = chunk_code(file_path, file_content)
        original_chunks.update(chunks)

    flash_model = genai.GenerativeModel("gemini-2.0-flash-thinking-exp-01-21")  # Could also use "models/gemini-1.5-flash-002"
    relevant_chunk_ids = identify_relevant_chunks(flash_model, original_chunks, requested_change)

    if not relevant_chunk_ids:
        raise Exception("No relevant chunks found for modification.")

    print("relevant chunk ids:", relevant_chunk_ids)
    relevant_chunks = {chunk_id: original_chunks[chunk_id] for chunk_id in relevant_chunk_ids}

    rewrite_model = genai.GenerativeModel("gemini-2.0-pro-exp-02-05")  # Use gemini-pro for rewriting
    rewritten_chunks = rewrite_chunks(rewrite_model, relevant_chunks, requested_change)
    # print(rewritten_chunks)
    apply_changes(original_chunks, rewritten_chunks)
