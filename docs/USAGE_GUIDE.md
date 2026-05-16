# How to Use the Translator Application

This guide walks through the main features and usage flow of the RuEnDeeplGoogleTranslator application.

## 🚀 Getting Started

1.  **Launch the Application:** Run the application using the `run.bat` script (see [SETUP_GUIDE.md](docs/SETUP_GUIDE.md)).
2.  **Input Text:** The main chat window (`ui/chat_window.py`) is where you input the text you wish to translate.
3.  **Select Languages:** Use the language selectors to define the source language (Source) and the target language (Target).

## 🌐 Translation Workflow

1.  **Enter Text:** Type or paste the text into the input area.
2.  **Choose Translator:** Select your preferred translation service (DeepL, Google, Yandex) from the settings or the main UI controls.
3.  **Translate:** Click the 'Translate' button.
4.  **Review Results:** The translated text will appear in the results pane, often with options to view the source and target texts side-by-side.

## ✨ Advanced Features

### 1. Switching Translators
The application supports multiple backend services. You can switch between them in the settings window (`ui/settings_window.py`) to compare translations or use the service that performs best for a specific language pair.

### 2. History Management
All successful translations are automatically saved to the history panel. You can review past translations and easily re-use them without re-entering the text.

### 3. AI Integration (Advanced)
For context-aware translation or summarization, the application integrates advanced AI services:
*   **RAG Engine:** Allows the translator to reference external documents or knowledge bases before translating, ensuring the output is contextually accurate.
*   **Speech Input:** The application supports voice input (via `services/ai/whisper.py`), allowing you to speak the text you want translated.

## 💡 Tips and Best Practices

*   **Language Codes:** Always verify the language codes used in the settings to ensure accurate translation.
*   **API Limits:** Be mindful of the rate limits imposed by the external APIs (DeepL, Google, etc.).
*   **Troubleshooting:** If a feature fails, check the console output for specific error messages related to API keys or network connectivity.
