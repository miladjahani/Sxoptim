# SimSXCu Web Simulator - Digital Twin

This repository contains the source code for the SimSXCu Web Simulator, a digital twin for simulating copper solvent extraction circuits. The application is built entirely with HTML, JavaScript, and Python (running in the browser via Pyodide), making it perfectly suited for deployment as a static website on services like GitHub Pages.

## Features

- **Multiple Circuit Configurations:** Simulate 18 different solvent extraction circuits (Scenarios A through R).
- **Two Simulation Modes:**
    1.  **Optimization:** Calculate the required organic concentration (v/v%) to achieve a target stripping ratio.
    2.  **Plant Calculation:** Simulate plant performance based on a fixed organic concentration.
- **Interactive Interface:** A modern, responsive user interface built with Tailwind CSS.
- **Scientific Backend:** The core simulation logic is written in Python and uses `numpy` and `scipy` for accurate calculations.
- **In-Browser Execution:** The Python backend runs directly in the browser using Pyodide, eliminating the need for a server.
- **Data Visualization:** Results are displayed with an interactive McCabe-Thiele diagram using Plotly.js.

## How to Deploy to GitHub Pages

This application can be easily deployed as a GitHub Pages website.

1.  **Push to GitHub:** Ensure all the files (`index.html`, `backend.py`, and this `README.md`) are committed and pushed to a GitHub repository.
2.  **Enable GitHub Pages:**
    - In your repository, go to **Settings**.
    - In the left sidebar, click on **Pages**.
    - Under "Build and deployment", for the **Source**, select **Deploy from a branch**.
    - Select the branch you want to deploy from (e.g., `main` or `master`).
    - For the folder, select `/ (root)`.
    - Click **Save**.

GitHub will build and deploy your site. It might take a few minutes. Once deployed, you can access your live application at the URL provided in the GitHub Pages settings (usually `https://<your-username>.github.io/<your-repository-name>/`).

## Local Development

To run the. application locally, you need a simple web server to serve the files. Most modern code editors have extensions for this (e.g., "Live Server" for VS Code). You can also use Python's built-in HTTP server:

1.  Open your terminal in the project's root directory.
2.  Run the command: `python -m http.server`
3.  Open your web browser and navigate to `http://localhost:8000`.

This will launch the application locally.
