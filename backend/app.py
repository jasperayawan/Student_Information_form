from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.students import router as student_router
from models.init_tables import initialize_tables

app = FastAPI()

origins = [
    "http://127.0.0.1:5500",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*", "null"],
    allow_methods=["*"],
    allow_headers=["*"],
)

initialize_tables()
app.include_router(student_router)
