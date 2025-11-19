Deploying Resume Analyzer to Render (Docker)

Overview

- This repo contains a Dockerfile configured to install system packages required for OCR (poppler-utils, tesseract-ocr) and to run the FastAPI app using Uvicorn.
- Use Render's Docker service so the platform builds your image from the provided `Dockerfile` and exposes the container on the provided `$PORT`.

Steps

1. Push your repository to GitHub (branch `main` or whichever branch you prefer).

2. In Render dashboard:

   - Click "New" → "Web Service".
   - Connect to your GitHub account and select the repo `Resume-Screening`.
   - For "Environment", choose "Docker" (Render will detect and build the `Dockerfile`).
   - For branch, use `main`.
   - Set Plan: `starter` (or choose based on your needs).
   - Add environment variables if needed (optional):
     - `DEV_RELOAD` = `false` (turn on `true` for development reload).
   - Create the service and wait for the build + deploy logs to complete.

3. Verify service:

   - The service URL will be shown in the Render dashboard. Test the health endpoint:

     curl https://<your-service>.onrender.com/health

   - To parse a resume (example):

     curl -X POST "https://<your-service>.onrender.com/analyze-resume" \
      -H "Content-Type: multipart/form-data" \
      -F "file=@/path/to/resume.pdf"

Notes & Recommendations

- OCR: The provided `Dockerfile` installs `tesseract-ocr` and `poppler-utils`, so the OCR fallback (pytesseract + pdf2image) should work in this container.
- Resource limits: If you expect large PDFs or heavy CPU use (OCR or model inference), choose a larger plan and increase the concurrency/workers.
- Logging: Use the Render dashboard logs to debug build errors or runtime exceptions. If the container fails during startup, inspect the build logs to ensure dependencies installed correctly.
- Startup: The Dockerfile runs `uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}` so the app listens on the port Render provides.

Troubleshooting

- Build fails due to missing system libs: check the Dockerfile and add needed apt packages.
- Tesseract errors: confirm the tesseract language packs installation or adjust TESSDATA_PREFIX if necessary.
- If you do not need OCR, you can remove the poppler/tesseract apt lines to reduce image size.

Optional: CI/CD

- To auto-deploy on every merge to `main`, enable automatic deploys in the Render service settings.
- For secrets, add them via Render's Environment settings rather than committing to the repo.

If you'd like, I can:

- Add a GitHub Actions workflow that triggers a Render deploy using a Render API key (requires secret in GitHub).
- Trim `requirements.txt` by removing DB packages like `pymysql` if you will never use a database.
