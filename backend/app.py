from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from routers.auth import router as auth_router
from routers.students import router as student_router
from routers.instructors import router as instructor_router
from routers.courses import router as course_router
from routers.subjects import router as subject_router
from routers.classrooms import router as classroom_router
from routers.schedule import router as schedule_router
from routers.enrollments import router as enrollment_router
from routers.users import router as user_router
from routers.dashboard import router as dashboard_router
from models.init_tables import initialize_tables

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="Paulino Dari National High School")

origins = [
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "null",  # index.html opened directly from disk
]

# Authentication uses a bearer token header (not cookies), so a fixed list
# of local origins is enough.
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

initialize_tables()


# Make browsers re-check frontend files on every load (a cheap 304 when
# unchanged), so updated pages never run stale cached JavaScript.
@app.middleware("http")
async def no_stale_frontend(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/app"):
        response.headers["Cache-Control"] = "no-cache"
    return response


for router in (auth_router, student_router, instructor_router, course_router, subject_router,
               classroom_router, schedule_router, enrollment_router, user_router, dashboard_router):
    app.include_router(router)

# The frontend is also served by the API at http://127.0.0.1:8000/app/
app.mount("/app", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse("/app/")
