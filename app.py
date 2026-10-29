import secrets
import time
from resume_improver import improve_resume
import json
import os
import re
from xml.sax.saxutils import escape

from fastapi import HTTPException
from fastapi.responses import Response

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

import json
import os
import re
import secrets

from fastapi import Form, Request
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from pwdlib import PasswordHash

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from auth_db import SessionLocal, User, Analysis

from ats_scorer import score_resume
from io import BytesIO
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pypdf import PdfReader

from matcher import analyze_match

BASE_DIR = Path(__file__).resolve().parent
MAX_FILE_SIZE = 5 * 1024 * 1024

app = FastAPI(title="AI Resume & Job Matcher")

SESSION_SECRET = os.environ.get("SESSION_SECRET")
if not SESSION_SECRET:
    # Development fallback only. Set SESSION_SECRET in production.
    SESSION_SECRET = secrets.token_urlsafe(32)

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    same_site="lax",
    https_only=False,  # Local development only; use True behind HTTPS.
)

password_hasher = PasswordHash.recommended()


def current_user(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return None

    with SessionLocal() as db:
        return db.get(User, user_id)


def get_owned_analysis(user_id: int, analysis_id: int):
    with SessionLocal() as db:
        return db.scalar(
            select(Analysis).where(
                Analysis.id == analysis_id,
                Analysis.user_id == user_id,
            )
        )

# Temporary in-memory report storage; no database required.
REPORT_CACHE = {}
REPORT_TTL_SECONDS = 30 * 60
REPORT_CACHE_LIMIT = 100


def save_report(result: dict) -> str:
    """Save a report temporarily and return its unguessable ID."""
    now = time.time()

    # Remove expired reports.
    expired_ids = [
        report_id
        for report_id, item in REPORT_CACHE.items()
        if now - item["created_at"] > REPORT_TTL_SECONDS
    ]

    for report_id in expired_ids:
        REPORT_CACHE.pop(report_id, None)

    # Keep memory usage bounded.
    while len(REPORT_CACHE) >= REPORT_CACHE_LIMIT:
        oldest_id = min(
            REPORT_CACHE,
            key=lambda key: REPORT_CACHE[key]["created_at"],
        )
        REPORT_CACHE.pop(oldest_id, None)

    report_id = secrets.token_urlsafe(24)

    REPORT_CACHE[report_id] = {
        "created_at": now,
        "result": result,
    }

    return report_id

app.mount(
    "/static",
    StaticFiles(directory=BASE_DIR / "static"),
    name="static",
)

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))




@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse("/login", status_code=303)

    with SessionLocal() as db:
        user = db.get(User, user_id)
        if not user:
            request.session.clear()
            return RedirectResponse("/login", status_code=303)
        username = user.username

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "result": None,
            "error": None,
            "report_id": None,
            "username": username,
        },
    )


@app.post("/analyze", response_class=HTMLResponse)
async def analyze_resume(
    request: Request,
    resume: UploadFile = File(...),
    job_description: str = Form(...),
):
    # 1. Authentication
    user_id = request.session.get("user_id")

    if not user_id:
        await resume.close()
        return RedirectResponse("/login", status_code=303)

    result = None
    error = None
    report_id = None
    analysis_id = None

    try:
        # 2. Verify that the logged-in user exists
        with SessionLocal() as db:
            user = db.get(User, user_id)

            if not user:
                request.session.clear()
                await resume.close()
                return RedirectResponse("/login", status_code=303)

            username = user.username

        # 3. Validate the uploaded file
        if (
            not resume.filename
            or Path(resume.filename).suffix.lower() != ".pdf"
        ):
            raise HTTPException(
                status_code=400,
                detail="Please upload a PDF resume.",
            )

        if not job_description.strip():
            raise HTTPException(
                status_code=400,
                detail="Please enter a job description.",
            )

        pdf_bytes = await resume.read(MAX_FILE_SIZE + 1)

        if len(pdf_bytes) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail="PDF must be 5 MB or smaller.",
            )

        if not pdf_bytes.startswith(b"%PDF-"):
            raise HTTPException(
                status_code=400,
                detail="Invalid PDF file.",
            )

        # 4. Extract resume text
        try:
            reader = PdfReader(BytesIO(pdf_bytes))

            if reader.is_encrypted:
                raise HTTPException(
                    status_code=400,
                    detail="Password-protected PDFs are not supported.",
                )

            resume_text = "\n".join(
                page.extract_text() or ""
                for page in reader.pages[:20]
            )

        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail="Could not read this PDF.",
            ) from exc

        if not resume_text.strip():
            raise HTTPException(
                status_code=400,
                detail="No readable text found. Scanned PDFs need OCR.",
            )

        # 5. Existing semantic resume-job matching
        result = analyze_match(resume_text, job_description)

        # 6. Existing ATS score
        result["ats"] = score_resume(resume_text)

        # 7. NEW: Resume improvement suggestions
        improvement_report = improve_resume(
            resume_text=resume_text,
            job_description=job_description,
        )

        # Keep the full improvement report in the saved result
        result["improvement"] = improvement_report

        # 8. Combine suggestions from all analyzers
        suggestions = list(result.get("suggestions", []))
        suggestions.extend(result["ats"].get("suggestions", []))
        suggestions.extend(improvement_report.get("suggestions", []))

        if result.get("missing"):
            suggestions.append(
                "Add missing job skills only if you genuinely have those skills."
            )

        if result.get("semantic_missing"):
            suggestions.append(
                "Describe relevant projects and experience more clearly."
            )

        result["suggestions"] = list(dict.fromkeys(suggestions))
        result["filename"] = Path(resume.filename).name

        # 9. Save successful analysis to the logged-in user's history
        with SessionLocal() as db:
            history_item = Analysis(
                user_id=user_id,
                filename=result["filename"][:255],
                semantic_score=int(result.get("score", 0)),
                ats_score=int(result.get("ats", {}).get("score", 0)),
                result_json=json.dumps(result),
            )

            db.add(history_item)
            db.commit()
            db.refresh(history_item)
            analysis_id = history_item.id

        # 10. Create the downloadable PDF report once
        report_id = save_report(result)

    except HTTPException as exc:
        error = exc.detail

    except ValueError as exc:
        error = str(exc)

    except Exception:
        error = (
            "Analysis failed. Check the terminal for the actual error "
            "and verify your NLP dependencies and model availability."
        )

    finally:
        await resume.close()

    # 11. Render the existing analysis page
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "result": result,
            "error": error,
            "report_id": report_id,
            "analysis_id": analysis_id,
            "username": username if "username" in locals() else None,
        },
    )


def add_pdf_bullets(story, title, items, styles, limit=20):
    """Add a safe, readable list to the PDF."""
    story.append(Paragraph(escape(title), styles["Heading2"]))
    story.append(Spacer(1, 4))

    if not items:
        story.append(Paragraph("None detected.", styles["BodyText"]))
    else:
        for item in items[:limit]:
            if isinstance(item, dict):
                text = item.get("requirement", "")
                similarity = item.get("similarity")
                if similarity is not None:
                    text = f"{text} (similarity: {similarity}%)"
            else:
                text = str(item)

            story.append(
                Paragraph(
                    "&#8226; " + escape(text),
                    styles["ReportBody"],
                )
            )

    if len(items) > limit:
        story.append(
            Paragraph(
                f"Showing first {limit} items.",
                styles["Italic"],
            )
        )

    story.append(Spacer(1, 10))


@app.get("/download-report/{report_id}")
async def download_report(report_id: str):
    # Find a report generated by a recent successful analysis.
    saved = REPORT_CACHE.get(report_id)

    if not saved:
        raise HTTPException(
            status_code=404,
            detail="Report not found or expired. Please analyze your resume again.",
        )

    if time.time() - saved["created_at"] > REPORT_TTL_SECONDS:
        REPORT_CACHE.pop(report_id, None)
        raise HTTPException(
            status_code=404,
            detail="Report expired. Please analyze your resume again.",
        )

    result = saved["result"]
    ats = result.get("ats", {})

    pdf_buffer = BytesIO()

    document = SimpleDocTemplate(
        pdf_buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="Resume Analysis Report",
        author="AI Resume & Job Matcher",
    )

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="ReportBody",
            parent=styles["BodyText"],
            fontSize=9,
            leading=13,
            spaceAfter=5,
            wordWrap="LTR",
        )
    )

    story = [
        Paragraph("Resume Analysis Report", styles["Title"]),
        Spacer(1, 8),
        Paragraph(
            "AI Resume &amp; Job Matcher",
            styles["Heading2"],
        ),
        Paragraph(
            "Resume file: " + escape(str(result.get("filename", "Uploaded resume"))),
            styles["BodyText"],
        ),
        Spacer(1, 14),
    ]

    # Main scores
    story.append(Paragraph("Overall Scores", styles["Heading1"]))
    score_data = [
        ["Metric", "Score"],
        ["ATS Resume Score", f'{ats.get("score", 0)}/100'],
        ["Semantic Match Score", f'{result.get("score", 0)}%'],
        ["Resume Word Count", str(ats.get("word_count", 0))],
    ]

    score_table = Table(score_data, colWidths=[105 * mm, 45 * mm])
    score_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1D3557")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F8FAFC")),
                ("PADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.extend([score_table, Spacer(1, 16)])

    # ATS breakdown
    story.append(Paragraph("ATS Score Breakdown", styles["Heading1"]))
    breakdown = [["Category", "Points", "Details"]]

    for name, item in ats.get("checks", {}).items():
        details = item.get("details", "")
        if isinstance(details, dict):
            details = ", ".join(
                f"{key}: {'Found' if value else 'Not detected'}"
                for key, value in details.items()
            )
        elif isinstance(details, list):
            details = ", ".join(str(value) for value in details)
        else:
            details = str(details)

        breakdown.append(
            [
                Paragraph(escape(str(name)), styles["ReportBody"]),
                f'{item.get("score", 0)}/{item.get("max_score", 0)}',
                Paragraph(escape(details), styles["ReportBody"]),
            ]
        )

    breakdown_table = Table(
        breakdown,
        colWidths=[43 * mm, 23 * mm, 84 * mm],
        repeatRows=1,
    )
    breakdown_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend([breakdown_table, Spacer(1, 16)])

    # Skill lists
    add_pdf_bullets(
        story, "Matched Skills", result.get("matched", []), styles
    )
    add_pdf_bullets(
        story, "Missing Job Skills", result.get("missing", []), styles
    )

    # Semantic requirement lists
    add_pdf_bullets(
        story,
        "Semantically Matched Requirements",
        result.get("semantic_matched", []),
        styles,
    )
    add_pdf_bullets(
        story,
        "Requirements to Review",
        result.get("semantic_missing", []),
        styles,
    )

    # Improvement suggestions
    add_pdf_bullets(
        story,
        "Improvement Suggestions",
        result.get("suggestions", []),
        styles,
    )

    story.append(Spacer(1, 10))
    story.append(
        Paragraph(
            escape(
                ats.get(
                    "disclaimer",
                    "Scores are estimates and do not guarantee hiring outcomes.",
                )
            ),
            styles["Italic"],
        )
    )

    document.build(story)
    pdf_bytes = pdf_buffer.getvalue()
    pdf_buffer.close()

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="resume_analysis_report.pdf"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.get("/health")
async def health():
    return {"status": "ok", "app": "AI Resume & Job Matcher"}


@app.get("/register")
async def register_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/", status_code=303)

    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="templates")
    return templates.TemplateResponse(
        request=request,
        name="auth.html",
        context={"mode": "register", "error": None},
    )


@app.post("/register")
async def register_user(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
):
    username = username.strip()
    email = email.strip().lower()

    if not re.fullmatch(r"[A-Za-z0-9_]{3,50}", username):
        return await auth_error(request, "register",
            "Username must be 3–50 letters, numbers or underscores.")

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return await auth_error(request, "register",
            "Enter a valid email address.")

    if len(password) < 12:
        return await auth_error(request, "register",
            "Password must be at least 12 characters long.")

    with SessionLocal() as db:
        existing = db.scalar(
            select(User).where(
                (User.username == username) | (User.email == email)
            )
        )
        if existing:
            return await auth_error(
                request, "register",
                "Username or email is already registered.",
            )

        user = User(
            username=username,
            email=email,
            password_hash=password_hasher.hash(password),
        )
        db.add(user)

        try:
            db.commit()
            db.refresh(user)
            user_id = user.id
        except IntegrityError:
            db.rollback()
            return await auth_error(
                request, "register",
                "Username or email is already registered.",
            )

    request.session.clear()
    request.session["user_id"] = user_id
    return RedirectResponse("/", status_code=303)


@app.get("/login")
async def login_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/", status_code=303)

    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="templates")
    return templates.TemplateResponse(
        request=request,
        name="auth.html",
        context={"mode": "login", "error": None},
    )


@app.post("/login")
async def login_user(
    request: Request,
    username_or_email: str = Form(...),
    password: str = Form(...),
):
    identity = username_or_email.strip()

    with SessionLocal() as db:
        user = db.scalar(
            select(User).where(
                (User.username == identity)
                | (User.email == identity.lower())
            )
        )

        if not user or not password_hasher.verify(
            password, user.password_hash
        ):
            return await auth_error(
                request, "login",
                "Invalid username/email or password.",
            )

        user_id = user.id

    request.session.clear()
    request.session["user_id"] = user_id
    return RedirectResponse("/", status_code=303)


@app.post("/logout")
async def logout_user(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


async def auth_error(request: Request, mode: str, message: str):
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="templates")
    return templates.TemplateResponse(
        request=request,
        name="auth.html",
        context={"mode": mode, "error": message},
        status_code=400,
    )


@app.get("/history", response_class=HTMLResponse)
async def analysis_history(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/login", status_code=303)

    with SessionLocal() as db:
        user = db.get(User, user_id)
        if not user:
            request.session.clear()
            return RedirectResponse("/login", status_code=303)

        records = db.scalars(
            select(Analysis)
            .where(Analysis.user_id == user_id)
            .order_by(Analysis.created_at.desc())
        ).all()

        history = [
            {
                "id": item.id,
                "filename": item.filename,
                "semantic_score": item.semantic_score,
                "ats_score": item.ats_score,
                "created_at": item.created_at,
            }
            for item in records
        ]

    return templates.TemplateResponse(
        request=request,
        name="history.html",
        context={"history": history, "username": user.username},
    )


@app.get("/history/{analysis_id}", response_class=HTMLResponse)
async def view_history_item(request: Request, analysis_id: int):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/login", status_code=303)

    with SessionLocal() as db:
        record = db.scalar(
            select(Analysis).where(
                Analysis.id == analysis_id,
                Analysis.user_id == user_id,
            )
        )

        if not record:
            raise HTTPException(status_code=404, detail="Analysis not found.")

        result = json.loads(record.result_json)
        record_info = {
            "id": record.id,
            "filename": record.filename,
            "created_at": record.created_at,
            "ats_score": record.ats_score,
            "semantic_score": record.semantic_score,
        }

    return templates.TemplateResponse(
        request=request,
        name="history_detail.html",
        context={"result": result, "record": record_info},
    )


@app.get("/history/{analysis_id}/download")
async def download_history_pdf(request: Request, analysis_id: int):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/login", status_code=303)

    with SessionLocal() as db:
        record = db.scalar(
            select(Analysis).where(
                Analysis.id == analysis_id,
                Analysis.user_id == user_id,
            )
        )

        if not record:
            raise HTTPException(status_code=404, detail="Analysis not found.")

        result = json.loads(record.result_json)

    report_id = save_report(result)
    return RedirectResponse(
        f"/download-report/{report_id}",
        status_code=303,
    )


