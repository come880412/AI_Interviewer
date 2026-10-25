Below is text extracted from a resume file. Extraction from PDF or Word often breaks lines in the middle of sentences, splits hyphenated words, mixes up the order of columns, and leaves page numbers or headers behind.

Rewrite it as a clean plain-text resume in exactly this layout:

```
Full Name — City, Country

Summary
One paragraph.

Experience

Company — City, Country (Mon. YYYY – Mon. YYYY)

Job Title (Mon. YYYY – Mon. YYYY)
- One bullet per achievement, on a single line.

Skills
- Category: item, item, item

Education
- School — Degree, Field, Mon. YYYY – Mon. YYYY. Extra details.
```

Add any other sections the resume has (for example Projects, Publications, Awards) after these, with their original names. Section names are plain words on their own line, with no Markdown symbols such as # or **. Leave out contact details (email, phone, links).

Rules:
- Keep every fact exactly as written: names, titles, dates, numbers, metrics, technologies. Do not add, infer, embellish, or summarize anything, and do not drop any content other than contact details and leftover page furniture.
- Only fix what extraction broke: rejoin broken lines and words, restore the reading order, and normalize bullets to "- ".
- Keep the resume's original language.
- Output only the resume, with no introduction, notes, or code fences.

<resume_text>
{{resume_text}}
</resume_text>
