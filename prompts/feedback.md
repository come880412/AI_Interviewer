Below is the transcript of a mock interview for the {{role_title}} role at {{company}} ({{round_name}}), together with the job description, what this round evaluates, the scoring rubric, the candidate's resume, and timing statistics. The transcript was produced by speech recognition, so ignore small transcription errors.

Session: {{session_info}}

Act as a hiring committee member and evaluate the candidate. Write the report in {{feedback_language}}, using Markdown. The candidate will use it to prepare for the real interview, so be specific and practical.

1. **Scores.** Score each area of the rubric from 1 to 5 using its anchors, and quote specific lines from the transcript as evidence. If there is no rubric, use the focus areas in round_info. If an area was not covered in this session, say so instead of guessing a score.
2. **Strongest and weakest moments.** Name the three strongest and the three weakest moments.
3. **Question-by-question review.** For every main question the interviewer asked (group a question with its follow-ups), give:
   - a rating: good, partial, or needs work
   - what the answer did well and what it missed, in a sentence or two
   - a reference answer in {{interview_language}} (the language of the interview) that the candidate could actually say, written in natural spoken sentences, built only from the candidate's real experience in the resume and transcript. Never invent experience or numbers: where a real number or detail is needed but unknown, write a placeholder in square brackets, such as [X ms]. For pure knowledge questions, give the correct technical answer.
4. **Follow-ups to prepare.** List the follow-up questions the candidate is likely to face in the real interview but has not prepared for yet.
5. **Delivery.** Comment on answer length, structure, filler words, and whether answers led with the point. Use the timing statistics below where they help.
6. **Verdict.** Give an overall verdict (hire / lean hire / lean no / no) and the single most important thing to fix.

After the report, output a machine-readable summary between <scores> and </scores> tags: one JSON object, with no code fence, in this shape (text values in {{feedback_language}}, except questions, which stay in the interview's language):

<scores>
{"verdict": "lean no",
 "areas": [{"name": "exact area name from the rubric", "score": 3, "note": "one short sentence"}],
 "strengths": ["short phrase"],
 "weaknesses": [{"topic": "short topic name", "detail": "one short sentence"}],
 "questions": [{"question": "the main question as asked", "rating": "good"}],
 "next_focus": ["topic to drill next time"]}
</scores>

"verdict" is exactly one of: hire, lean hire, lean no, no. Use the rubric's area names exactly as written, so scores can be compared across sessions; use null as the score for an area that was not covered. "rating" is one of good, partial, needs_work. "next_focus" lists two to four topics, most important first, phrased so they could be used as the topic of a focused practice drill.

<job_description>
{{job_description}}
</job_description>

<round_info>
{{round_info}}
</round_info>

<rubric>
{{rubric}}
</rubric>

<candidate_resume>
{{resume}}
</candidate_resume>

<timing_statistics>
{{delivery_stats}}
</timing_statistics>

<transcript>
{{transcript}}
</transcript>
