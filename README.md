# Sales CRM

Leads + follow-ups for ECO, Pipe, B Wall and PI. Streamlit + Supabase.

- Run locally: `run.bat` (or `streamlit run app.py`)
- First login: `admin` / `changeme` (you must change it right away)
- Database: run `supabase_schema.sql` once in the Supabase SQL Editor; put
  `SUPABASE_URL` and `SUPABASE_KEY` (secret key) in `.streamlit/secrets.toml`
- Tests: set `CRM_SQLITE=<path to a test .db>` so the live database is never touched
- Company list, products, stages, sources: `core/config.py`
