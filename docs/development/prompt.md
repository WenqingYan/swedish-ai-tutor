# Prompt Engineering Principles

## Core Philosophy

The LLM is a **language teacher**, not a translator or summarizer. Every prompt must produce output that builds language competence.

## Prompt Design Rules

1. **Explain rather than translate** — Provide context for why Swedish uses a particular construction.
2. **Focus on SFI C/D level** — Material should be challenging but achievable for intermediate learners.
3. **Identify reusable patterns** — Every sentence should surface phrases and structures the learner will encounter again.
4. **Prefer phrases over isolated words** — Collocations and fixed expressions are more useful than single vocabulary items.
5. **Always explain why** — Grammar rules need reasoning, not just labels.
6. **Never simply list vocabulary** — Every word must have context, morphology, and usage examples.
7. **Avoid unnecessary linguistic theory** — Practical usage over academic classification.

## Required Output Structure (per sentence)

For each sentence in the transcript, the LLM must produce:

1. **Original sentence** — Exact Swedish text
2. **Chinese translation** — Natural translation, not word-by-word
3. **Key grammar** — The most important grammatical pattern in this sentence
4. **Key phrases** — Reusable multi-word expressions
5. **Vocabulary** — New or important words with full morphology
6. **Word forms** — Complete declension/conjugation tables
7. **Example sentences** — Additional usage of the identified patterns
8. **SFI notes** — Relevance to SFI exam preparation

## Morphology Requirements

### Verbs
| Form | Example |
|------|---------|
| Imperative | — |
| Infinitive | — |
| Present | — |
| Past (preteritum) | — |
| Supine | — |
| Verb group (1–4) | — |

### Nouns
| Form | Example |
|------|---------|
| en/ett | — |
| Indefinite singular | — |
| Definite singular | — |
| Indefinite plural | — |
| Definite plural | — |

### Adjectives
| Form | Example |
|------|---------|
| en-form | — |
| ett-form | — |
| Plural/definite | — |
| Comparative | — |
| Superlative | — |

**Never omit morphology.** Incomplete word entries are worse than no entries.

## Prompt Storage

- All prompts stored in `/prompts/` directory
- One file per prompt version (e.g., `v1/sentence_analysis.txt`)
- Prompts are plain text with `{{variable}}` placeholders
- No prompts hardcoded in Python source files
