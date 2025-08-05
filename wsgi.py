import app

app = getattr(app, 'app')

if __name__ == "__main__":
    app.run()