from app import create_app, db

app = create_app()


def initialize_prototype_database(application):
    if not application.config["PROTOTYPE_MODE"]:
        return

    from app.seed import seed_demo_data

    with application.app_context():
        db.create_all()
        seed_demo_data()


initialize_prototype_database(app)
