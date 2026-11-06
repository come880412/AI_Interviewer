Rewrite a LeetCode problem the way a coding interviewer would write it in a shared document at the start of an interview. Real interview problems are underspecified on purpose: the candidate is expected to ask clarifying questions, and the interviewer answers them from the full statement below. Underspecified means the constraints and edge cases are missing, not the task: after reading it, the candidate should know exactly what problem to solve.

Write:
- "statement": a short paragraph of two to four plain sentences, the way an interviewer types a problem into a shared document. Say what the inputs are and what they represent, what to compute and what to return, and define every term the task depends on (what counts as an island, what a valid sequence is). If the original is set in a scenario (a store, a game, a network), keep it. Use the parameter names from the function signature, so the candidate can fill in the starter code. Do not change the problem: every detail you leave out must still be true of the original.
- "examples": one or two examples taken from the original, simplest first, each with "input" and "output" strings in the original's notation and an "explanation" of one short sentence saying why the output is right ("" if it is obvious). Add a second example only when it shows the task from another angle, such as a larger input or a different shape of answer. Never pick or explain an example in a way that settles a left-out detail: no example whose point is duplicates, reusing an element, ties, empty input or no answer. Check each example: if a candidate who got a left-out detail wrong would expect a different output for it (in Two Sum, nums = [3,2,4], target = 6 tells them an element cannot be used twice), leave it out; one example is fine.
- "left_out": every detail of the original you did not write, one short fact per item, so the interviewer can answer clarifying questions truthfully. Always include every constraint (input sizes, value ranges, lengths), every guarantee ("exactly one answer exists", "the input is sorted", "all values are distinct"), how edge cases behave (empty input, ties, duplicates, no answer), output details (order, format, what to return when there is no answer), and any follow-up.

Leave out of "statement" and the explanations: constraints and input sizes, value ranges, guarantees and assumptions, edge-case rules, output order, follow-ups, and anything that hints at the technique (do not mention data structures, algorithms or complexity unless the task itself is about one, such as "implement an LRU cache"). Keep a rule in "statement" only when the task is meaningless without it, such as "adjacent means horizontally or vertically" for a grid problem; a candidate could still ask about it.

Write in English. Reply with only the JSON object, no prose and no code fence:
{"statement": "...", "examples": [{"input": "...", "output": "...", "explanation": "..."}], "left_out": ["...", "..."]}

Function signature:
{signature}

The full LeetCode statement:
<statement>
{problem}
</statement>
