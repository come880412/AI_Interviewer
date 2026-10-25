You are helping a candidate set up a realistic mock interview. From the job description, the notes the candidate has about this round, and the candidate's resume, draft the files the mock interviewer will use.

Company: {{company}}
Role: {{role_title}}
Round: {{round_name}}
Interviewer: {{interviewer_name}}, {{interviewer_title}}
Length: {{duration_minutes}} minutes
Language for the rubric: {{feedback_language}}

Write each file between its tags, in this order:

<round_info>
English. Follow this layout:
Format (from the notes): what this round covers, how long it is, who interviews, and the parts to touch within the time.

Where the candidate's resume meets the JD, and where it doesn't (use this to choose what to probe):
- Strong overlap: specific resume items that match specific JD requirements.
- Gaps to test: JD requirements the resume does not clearly show.
- Motivation: what to probe about why the candidate wants this role.

About the interviewer: only what the notes say about them (background, what they care about, how they talk). If the notes say nothing, write that it is unknown and that the interviewer should be professional and concrete.
</round_info>

<question_bank>
English. Group questions under a plain heading per part of the round (no Markdown symbols on headings), five to eight questions per part, each a "- " bullet. Ground them in the JD and the resume: name the candidate's actual projects and the company's actual products where possible.
</question_bank>

<rubric>
Written in {{feedback_language}}. One "## " heading per area this round evaluates (four to six areas, matching the parts of the round). Under each heading, three bullets describing concretely what a 5, a 3 and a 1 look like for this role, for example "- 5: ...". Keep area names short; they are used to compare scores across practice sessions.
</rubric>

<company_info>
English. "- " bullets of facts about the company, its product, team and way of working that the interviewer could use when the candidate asks questions. Use only facts stated in the JD or the notes; never add outside knowledge or guesses. If there is little to say, keep it short.
</company_info>

<hotwords>
One term per line, 15 to 30 terms: company and product names, acronyms and technical terms from the JD and the resume that speech recognition is likely to mishear. No bullets or commas.
</hotwords>

Output only these five tagged sections.

<job_description>
{{job_description}}
</job_description>

<round_notes>
{{notes}}
</round_notes>

<candidate_resume>
{{resume}}
</candidate_resume>
