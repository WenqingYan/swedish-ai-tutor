# v1 — Design Document

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Pipeline Runner                        │
│                       (main.py → run)                         │
└──────────┬──────────┬──────────┬──────────┬─────────────────┘
           │          │          │          │
           ▼          ▼          ▼          ▼
    ┌───────────┐ ┌────────┐ ┌────────┐ ┌──────────┐
    │SR Fetcher │ │Whisper │ │Sentence│ │  Notion  │
    │           │ │Transcr.│ │Analyzer│ │ Exporter │
    └───────────┘ └────────┘ └────────┘ └──────────┘
           │                      │
           ▼                      ▼
    ┌───────────┐          ┌───────────┐
    │ Audio     │          │ Local     │
    │ Cache     │          │ SQLite DB │
    │ (./data/) │          │(vocab,    │
    └───────────┘          │ articles) │
                           └───────────┘
```

## Module Design

### 1. SR Fetcher (`services/sr_fetcher.py`)

**Responsibility:** Retrieve episode metadata and download audio from SR API.

**Interface:**
```python
class SRFetcher:
    async def get_latest_episode(self, date: date | None = None) -> Episode | None
    async def download_audio(self, episode: Episode) -> Path
```

**Data model:**
```python
class Episode(BaseModel):
    id: int
    title: str
    description: str
    publish_date: datetime
    audio_url: str
    duration_seconds: int
    url: str
```

**API endpoint:** `GET https://api.sr.se/api/v2/episodes/index?programid=493&format=json&size=5`

### 2. Transcriber (`services/transcriber.py`)

**Responsibility:** Convert audio file to Swedish text.

**Interface:**
```python
class Transcriber(Protocol):
    async def transcribe(self, audio_path: Path) -> Transcript

class WhisperAPITranscriber:
    async def transcribe(self, audio_path: Path) -> Transcript
```

**Data model:**
```python
class Transcript(BaseModel):
    full_text: str
    segments: list[TranscriptSegment]

class TranscriptSegment(BaseModel):
    text: str
    start: float
    end: float
```

### 3. Sentence Analyzer (`services/sentence_analyzer.py`)

**Responsibility:** Send sentences to LLM with analysis prompt, parse structured response.

**Interface:**
```python
class SentenceAnalyzer:
    async def analyze_sentence(self, sentence: str) -> SentenceAnalysis
    async def analyze_transcript(self, transcript: Transcript) -> list[SentenceAnalysis]
```

**Data model:**
```python
class SentenceAnalysis(BaseModel):
    original: str
    translation: str
    grammar: GrammarNote
    phrases: list[Phrase]
    vocabulary: list[VocabularyEntry]
    examples: list[str]
    sfi_notes: str

class VocabularyEntry(BaseModel):
    word: str
    pos: str
    meaning: str
    morphology: dict  # Verb/Noun/Adjective forms
```

### 4. Notion Exporter (`exporters/notion_exporter.py`)

**Responsibility:** Transform a Lesson into a formatted Notion page.

**Interface:**
```python
class NotionExporter:
    async def create_lesson_page(self, lesson: Lesson) -> str  # returns page URL
    async def page_exists(self, episode_id: int) -> bool
```

**Notion page structure:**
```
📖 2026-07-14 — Klartext
├── 📋 Episode Info (callout: date, duration, audio link)
├── 📝 Summary (episode description)
├── 🔤 Sentences
│   ├── [Toggle] Sentence 1: "..."
│   │   ├── Translation
│   │   ├── Grammar
│   │   ├── Phrases
│   │   ├── Vocabulary (table)
│   │   └── SFI Notes
│   ├── [Toggle] Sentence 2: "..."
│   └── ...
└── 📊 Today's New Words (summary table)
```

### 5. Lesson Model (`models/lesson.py`)

```python
class Lesson(BaseModel):
    episode: Episode
    transcript: Transcript
    analyses: list[SentenceAnalysis]
    generated_at: datetime
    new_words_count: int
    known_words_count: int
```

## Data Flow

1. `SRFetcher.get_latest_episode()` → `Episode`
2. `SRFetcher.download_audio(episode)` → `Path`
3. `Transcriber.transcribe(audio_path)` → `Transcript`
4. `SentenceAnalyzer.analyze_transcript(transcript)` → `list[SentenceAnalysis]`
5. Assemble `Lesson` from all components
6. `NotionExporter.create_lesson_page(lesson)` → Notion URL
7. Log success, cleanup temp audio file

## Configuration

```python
class Settings(BaseSettings):
    # SR API
    sr_program_id: int = 493
    sr_api_base: str = "https://api.sr.se/api/v2"

    # OpenAI
    openai_api_key: str
    openai_model: str = "gpt-4o"
    whisper_model: str = "whisper-1"

    # Notion
    notion_api_key: str
    notion_parent_page_id: str

    # Local
    data_dir: Path = Path("./data")
    db_path: Path = Path("./data/vocabulary.db")
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
```

## Error Handling Strategy

| Stage | Failure Mode | Recovery |
|-------|-------------|----------|
| SR API | Network error / no episode | Retry 3x, then exit cleanly |
| Audio download | Partial download | Retry with resume, verify file size |
| Whisper | API error | Retry 3x, save audio for manual retry |
| Sentence analysis | LLM timeout/error | Retry per-sentence, skip after 3 failures |
| Notion | API rate limit / error | Save lesson JSON locally, retry on next run |
