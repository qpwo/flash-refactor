### flash-refactor

breaks code into chunks, uses `gemini-2.0-flash-thinking-exp-01-21` to pick relevant chunks, then uses `gemini-2.0-pro-exp-02-05` to rewrite those chunks

Works pretty damn well. You can post successes or failures in [the discussions](https://github.com/qpwo/flash-refactor/discussions)

Executables:

- `refactor`: breaks files into chunks, picks which chunks to edit, then rewrites them (best for bulk operations)
- `flash-direct`: just does one-step rewrite of all provided files (best for simple changes)
- `flash-q`: ask questions about files
- `flash-plan`: write a plan first, then execute it (best for tricky changes)

Usage:

```sh
git clone https://github.com/qpwo/flash-refactor ~/git/flash-refactor
echo 'export PATH="$HOME/git/flash-refactor:$PATH' >> ~/.bashrc
echo 'GEMINI_API_KEY=...' > ~/git/flash-refactor/.env
pip install google-genai python-dotenv prompt-toolkit


refactor file1.ts file2.py
# will ask what change to make with input()
# modifies files in-place

# handy:
refactor $(find . -name "*.c")
```


Inspired by Victor Taelin's [aoe](https://github.com/VictorTaelin/AI-scripts/blob/main/aoe.mjs)

---

Sometimes it works better to write a plan then rewrite entire files. That's what `refactor-plan.py` does.
