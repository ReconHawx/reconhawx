# Event Handler Tests

Run event-handler unit tests with:

```bash
cd /path/to/recon
source venv/bin/activate
PYTHONPATH=src/event-handler python -m pytest src/event-handler/tests/ -v
```

Note: Event-handler tests use the `app` package from `src/event-handler/app`, which conflicts with the API's `app` package. Run them separately from API tests.
