# Contributing

I follow these rules for every change, including changes I make with AI help.

## Tests come first

1. I write a test for the behavior I want. I keep it small and name it after the behavior.
2. I run it and watch it fail. The failure must come from the missing behavior, not from a typo or a missing import.
3. I write the least code that makes the test pass.
4. I run the whole suite, then lint.
5. I tidy the code. The tests must still pass.

I never change a test just to make it pass. If a test is wrong, I say so in the commit message and explain the correction.

## Code a person can review

- Every function does one thing and has a name that says what it does.
- No dead code, unused imports, commented-out blocks, or placeholder functions that pretend to work.
- Comments explain why, not what. I remove any comment that repeats the code.
- A reviewer should be able to rebuild a file from its tests and its docstring alone.
- Changes stay small: one change, one reason, one commit.
- Every tool and version is pinned, and I record the reason for each non-obvious choice in the docs.

## Writing and documentation

- I use plain sentences. I avoid em dashes and spaced hyphens used as dashes, and I use commas, colons or full stops instead.
- I explain new terms the first time they appear.
- Timestamps in code and data are UTC.

## Line endings

- Every text file uses LF line endings. `.gitattributes` and `.editorconfig` set this.
- On Windows, a script that writes a file must ask for LF, for example `write_text(..., newline="\n")` in Python. The default writes CRLF, which breaks shell scripts: the `\` at the end of a line stops working. Shellcheck catches this.

## Keys and secrets

- No key, password or token goes in code, tests, docs or GitHub. Keys live in AWS Parameter Store.
- Tests use fake values that are obviously fake.

## Running the checks

See the README, section "Run the checks yourself".
