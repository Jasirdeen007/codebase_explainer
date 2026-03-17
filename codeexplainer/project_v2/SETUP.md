# Setup and Run (VS Code)

1. Create and activate a Python virtual environment.
2. Install requirements:
   - `pip install -r ../requirements.txt`
3. Optional full AI stack (recommended):
   - `pip install -r ../requirements-ai.txt`
4. Copy env file:
   - `cp ../codeexplainer/.env.example ../codeexplainer/.env`
5. Optional LLM reasoning (for better natural answers):
   - Set `LLM_API_KEY` and `LLM_MODEL` in `.env`
6. Apply database migrations:
   - `python manage.py migrate`
7. Run server:
   - `python manage.py runserver`
8. Open:
   - `http://127.0.0.1:8000/`

## API Endpoints

- `POST /api/upload/` upload repository zip and build index
- `GET /api/repositories/` list uploaded repositories
- `GET /api/repositories/<id>/files/` list indexed files
- `POST /api/ask/` ask question against selected repository
