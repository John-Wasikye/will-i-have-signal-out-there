# Contributing

These rules apply to every change, including changes made with AI help.

## Tests come first

1. Write a test for the behavior you want. Keep it small and name it after the behavior.
2. Run it and watch it fail. The failure must come from the missing behavior, not from a typo or a missing import.
3. Write the least code that makes the test pass.
4. Run the whole suite, then lint.
5. Tidy the code. The tests must still pass.

Never change a test just to make it pass. If a test is wrong, say so in the commit message and explain the correction.

## Code a person can review

- Every function does one thing and has a name that says what it does.
- No dead code, unused imports, commented-out blocks or placeholder functions that pretend to work.
- Comments explain why, not what. Remove any comment that repeats the code.
- A reviewer should be able to rebuild a file from its tests and its docstring alone.
- Changes stay small. One change, one reason, one commit.
- Every external tool or version is pinned, and the reason for each non-obvious choice goes in the docs.

## Writing and documentation

- Use plain sentences. Avoid em dashes and spaced hyphens used as dashes. Use commas, colons or full stops.
- Explain new terms the first time they appear.
- Timestamps in code and data are UTC.

## Keys and secrets

- No key, password or token goes in code, tests, docs or GitHub. Keys live in AWS Parameter Store.
- Tests use fake values that are clearly fake.

## Running the checks

See the README, section "Run the checks yourself".
