### flash-refactor

breaks code into chunks, uses `gemini-2.0-flash-thinking-exp-01-21` to pick relevant chunks, then uses `gemini-2.0-pro-exp-02-05` to rewrite those chunks

Works pretty damn well

Usage:

```sh
pip install google-genai python-dotenv prompt-toolkit

python refactor.py file1.txt file2.py
# will ask what change to make with input()
# modifies files in-place
```


Inspired by Victor Taelin's `AI-scripts`
