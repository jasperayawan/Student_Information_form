from models.migrations import run_migrations


def initialize_tables():
    run_migrations()
