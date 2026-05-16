# Project Setup Guide

This guide provides step-by-step instructions for setting up and running the RuEnDeeplGoogleTranslator application locally.

## 📦 Prerequisites

Before starting, ensure you have the following installed on your system:

*   **Python 3.x:** The application requires a modern Python environment.
*   **Required Libraries:** The project relies on several external Python libraries.

## ⚙️ Installation Steps

1.  **Clone the Repository:**
    ```bash
    git clone [repository-url]
    cd RuEnDeeplGoogleTranslator
    ```

2.  **Install Dependencies:**
    Navigate to the project root directory and install all required Python packages.
    ```bash
    pip install -r requirements.txt
    ```
    *(Note: If `requirements.txt` is not available, you may need to manually install dependencies listed in `setup.py` or the project documentation.)*

3.  **Set Up Environment Variables:**
    The application requires API keys for external services (DeepL, Google, etc.). These must be set as environment variables for the application to function correctly.

    *   **DeepL API Key:** Set `DEEPL_API_KEY`
    *   **Google API Key:** Set `GOOGLE_API_KEY`
    *   **Yandex API Key:** Set `YANDEX_API_KEY`

    **Example (Windows Command Prompt):**
    ```bash
    set DEEPL_API_KEY="your_deepl_api_key"
    set GOOGLE_API_KEY="your_google_api_key"
    set YANDEX_API_KEY="your_yandex_api_key"
    ```
    *Remember to replace the placeholders with your actual keys.*

## ▶️ Running the Application

The application can be launched using the provided batch script:

1.  **Run the Launcher:**
    Execute the `run.bat` file located in the project root directory.
    ```bash
    .\run.bat
    ```
    This script handles initializing the necessary components and launching the main UI window.

2.  **Deployment (Optional):**
    For creating a standalone installer, use the deployment scripts:
    *   `deployment/install.bat`: Runs the installer setup.
    *   `deployment/run.bat`: Runs the packaged application.

## ⚠️ Troubleshooting

*   **API Key Errors:** If the application fails to connect to a service, verify that the corresponding environment variable is set correctly and that the key is active.
*   **Dependency Errors:** Ensure your Python environment is clean and that all dependencies were installed successfully using `pip install -r requirements.txt`.
