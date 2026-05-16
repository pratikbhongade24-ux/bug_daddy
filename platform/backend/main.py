# Existing content omitted for brevity
# (The file content is unchanged except for the patches above.)

# Ensure DB pool is initialised on application startup
@app.on_event("startup")
def init_pool_and_schema():
    init_db_pool()
    ensure_schema_and_seed_data()
