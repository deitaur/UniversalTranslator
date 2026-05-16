# System Architecture

This document provides a detailed overview of the RuEnDeeplGoogleTranslator system architecture, describing how its various components interact to provide seamless translation services.

## 🏗️ High-Level Components

The system is designed with a modular, service-oriented architecture, separating concerns into distinct layers:

1.  **User Interface (UI):** Handles all user interactions and presentation logic.
    *   **Components:** `ui/chat_window.py`, `ui/popup_window.py`, `ui/settings_window.py`, `ui/tray_menu.py`, `ui/role_editor.py`.
    *   **Function:** Captures user input (text, source/target languages) and displays the results from the core logic.
2.  **Core Logic/Orchestration:** The central component that manages the workflow.
    *   **Components:** `main.py`, `diagnose.py`, `globals.py`.
    *   **Function:** Coordinates the flow: receives input from the UI, determines the required translation services, calls the appropriate service, and formats the output.
3.  **Translation Services:** Contains the implementations for various translation APIs.
    *   **Components:** `services/translators/deepl.py`, `services/translators/google.py`, `services/translators/yandex.py`.
    *   **Function:** Encapsulates the API interaction logic for each specific translation provider. They implement a common interface defined in `services/translators/base.py`.
4.  **AI/Advanced Services:** Handles advanced features beyond simple translation.
    *   **Components:** `services/ai/ollama.py`, `services/ai/rag_engine.py`, `services/ai/whisper.py`.
    *   **Function:** Provides capabilities like local LLM interaction (Ollama), Retrieval-Augmented Generation (RAG), and speech-to-text transcription (Whisper).
5.  **Storage/Persistence:** Manages data persistence.
    *   **Components:** `storage/history.py`, `storage/roles.py`.
    *   **Function:** Saves translation history and manages user/system roles.
6.  **Utilities:** General helper functions and utilities.
    *   **Components:** `utils/language.py`, `utils/clipboard.py`, `win32/hotkeys.py`, etc.
    *   **Function:** Provides cross-cutting concerns like language code management and OS-specific interactions.

## 🔄 Component Interaction Flow

1.  **User Input:** The user interacts with the **UI** (e.g., types text and clicks translate).
2.  **Orchestration:** The **UI** passes the request to the **Core Logic** (`main.py`).
3.  **Service Selection:** The **Core Logic** determines the best translator based on user settings or context.
4.  **Translation:** The **Core Logic** calls the specific service module (e.g., `services/translators/deepl.py`).
5.  **API Call:** The specific service module executes the API call (e.g., to the DeepL API).
6.  **Result Handling:** The service returns the translated text to the **Core Logic**.
7.  **Persistence & Display:** The **Core Logic** saves the result to **Storage** (`storage/history.py`) and passes the final output back to the **UI** for display.

## 🧩 Module Details

*   **`services/translators/base.py`:** Defines the abstract base class that all concrete translator services must inherit from, ensuring a consistent API contract.
*   **`services/ai/rag_engine.py`:** Implements the logic for querying external knowledge bases, enhancing the context of the translation or chat response.
*   **`storage/roles.py`:** Manages the structure and persistence of user roles, supporting potential multi-user environments.