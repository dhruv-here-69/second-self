# Streamlit Deployment Plan

This document outlines the steps required to deploy the "Second Self" project on Streamlit Community Cloud.

## 1. Prerequisites
- A GitHub account with the project code pushed to a public or private repository.
- A [Streamlit Community Cloud](https://streamlit.io/cloud) account linked to your GitHub account.

## 2. Pre-Deployment Preparation

### 2.1 Dependencies
Ensure that the `requirements.txt` file is up-to-date and pushed to the repository. The current `requirements.txt` includes all necessary dependencies:
- `streamlit`
- `groq`
- `sentence-transformers`
- `python-dotenv`
- ...and others.

### 2.2 Environment Variables (Secrets)
The project relies on a `.env` file for API keys (e.g., Groq API keys) and configuration. 
> [!IMPORTANT]
> Do **NOT** commit your `.env` file to the GitHub repository. Instead, ensure `.env` is listed in `.gitignore`.

You will need to configure these secrets directly in the Streamlit Cloud dashboard during deployment.

## 3. Deployment Steps

1. **Log in** to [Streamlit Community Cloud](https://share.streamlit.io/).
2. Click on the **"New app"** button.
3. **Connect to GitHub** (if not already connected) and authorize Streamlit.
4. Fill in the deployment details:
   - **Repository**: Select your GitHub repository (e.g., `username/second-self`).
   - **Branch**: Choose the branch you want to deploy (usually `main` or `master`).
   - **Main file path**: Enter `app.py`.
   - **App URL**: Choose a custom URL for your app (optional).
5. **Configure Secrets**:
   - Before clicking "Deploy", click on **"Advanced settings..."**.
   - Under the **"Secrets"** section, paste the contents of your `.env` file using the TOML format. 
   ```toml
   # Example format for Streamlit secrets
   GROQ_API_KEY = "your-api-key-here"
   # Add other variables from your .env file
   ```
   - Click **Save**.
6. Click **"Deploy!"**.

## 4. Post-Deployment Verification
- Watch the build logs to ensure all packages from `requirements.txt` install successfully.
- Once the app is live, test the core functionalities (e.g., chatting, classification, graph building) to ensure they work correctly with the provided API keys.
- If there are errors, check the **"Manage app"** -> **"Logs"** section in the bottom right corner of the deployed app.

> [!TIP]
> Any future pushes to the selected branch in GitHub will automatically trigger a re-deployment of your Streamlit app.
