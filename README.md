# Student Information System

> A lightweight RESTful API for managing student records built with Python, FastAPI, Pydantic, and Unicorn, featuring all CRUD Operations.

## Features

* **Create:** Add new student information with validation.
* **Read:** Retrieve a list of all students or fetch a single student by ID.
* **Update:** Modify existing student details.
* **Delete:** Remove student records from database.
* **Data Validation:** Uses Pydantic models ensure strick type safety and schema validation.

## Prerequisites

Before you begin, ensure you have the following installed on you system:
* [Python](https://www.python.org/) (v3.9 or higher recommended)
* `pip` (Python package manager)

## Installation & Setup

```
Follow these steps to set up and run the project locally:

1. Clone Repository
git clone https://github.com/jasperayawan/Student_Information_form

2. Create and activate a virtual environment(env)
python -m venv venv
.venv\Scripts\Activate.ps1

3. Installtion dependencies
pip install fastapi uvicorn pydantic

```

## Start the development server using Uvicorn
```
uvicorn app:app --reload

```